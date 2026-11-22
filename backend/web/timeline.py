"""Deterministic source-backed timeline. No network calls or database writes."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
import re
from typing import Protocol
from urllib.parse import urlsplit

from backend import db
from backend.web.textutil import page_text


@dataclass(frozen=True)
class Observation:
    """C-local normalized fact; path indexes sources.raw_response, not B output."""
    kind: str
    value: object
    source_id: int
    path: tuple[str | int, ...] = ()
    passage: str | None = None


class TimelineAdapter(Protocol):
    """Map verified existing B outputs only; no fetching or guessed field names.

    Adapter attests entity/scope: founding is not incorporation; a predecessor
    confirmation is a legitimate linked history, not a mere mention/acquisition.
    All mapped values are independently checked against their persisted source.
    """
    def observations(self, ctx: dict) -> list[Observation]: ...


_adapter = None


def configure_timeline_adapter(adapter: TimelineAdapter):
    global _adapter
    _adapter = adapter


LABELS = {
    "founding": "Verified founding", "incorporation": "Legal incorporation (not trading start)",
    "brand_launch": "Brand launch", "prior_history": "Verified prior business history",
    "claimed_since": "Website claimed history", "footer_year": "Website copyright year",
    "director_start": "Director role start", "first_job_posting": "First recorded job posting",
    "headcount_change": "Recorded headcount change", "news": "Source-backed news event (not proof of trading)",
}
ACTIVITY = {"first_job_posting", "headcount_change", "news"}
AUXILIARY = {"director_current_as_of", "coverage_from", "coverage_until", "coverage_complete", "coverage_activity_count",
             "coverage_channels", "predecessor_confirmed", "predecessor_relation", "predecessor_since"}


def date_bounds(value):
    """Keep year precision in output; bounds exist only for conservative comparisons."""
    if type(value) is int:
        value = str(value)
    if not isinstance(value, str):
        raise ValueError("Date must be a year or ISO day")
    if re.fullmatch(r"\d{4}", value):
        return date(int(value), 1, 1), date(int(value), 12, 31), value, "year"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Ambiguous or malformed date")
    day = date.fromisoformat(value)
    return day, day, value, "day"


def _texts(raw):
    if isinstance(raw, str):
        yield raw
        yield page_text(raw)[0]
    elif isinstance(raw, dict):
        for value in raw.values():
            yield from _texts(value)
    elif isinstance(raw, list):
        for value in raw:
            yield from _texts(value)


def ground_observation(item, run_id):
    if not isinstance(item, Observation) or item.kind not in LABELS.keys() | AUXILIARY:
        raise ValueError("Unsupported timeline observation")
    source = db.get_source(item.source_id)
    if not source or source["run_id"] != run_id:
        raise ValueError("Missing or cross-run source")
    if item.path:
        value = source["raw_response"]
        for part in item.path:
            value = value[part]
        if type(value) is not type(item.value) or value != item.value:
            raise ValueError("Source field mismatch")
    elif item.passage:
        if not any(item.passage in text for text in _texts(source["raw_response"])):
            raise ValueError("Passage not found in persisted text")
        if not isinstance(item.value, (str, int)) or not re.search(
                r"(?<!\w)" + re.escape(str(item.value)) + r"(?!\w)", item.passage):
            raise ValueError("Passage does not support value")
    else:
        raise ValueError("No field path or passage")
    return {"source_id": source["id"], "field_path": "raw_response" + "".join(
        f"[{json.dumps(p)}]" for p in item.path) if item.path else None,
        "passage": item.passage, "record_date": source["record_date"],
        "retrieved_at": source["retrieved_at"], "url": source["url"]}


def _existing_observations(ctx):
    # Read evidence, never the unsourced scalar year shortcuts in site output.
    for evidence in ctx["outputs"].get("site", {}).get("evidence", []):
        if not isinstance(evidence, dict):
            continue
        kind = {"claimed_since_year": "claimed_since", "footer_year": "footer_year"}.get(evidence.get("check"))
        if kind and evidence.get("status") == "verified":
            yield Observation(kind, evidence.get("value"), evidence.get("source_id"),
                              passage=evidence.get("passage"))
    for hit in ctx["outputs"].get("media", {}).get("media_hits", []):
        if not isinstance(hit, dict):
            continue
        extracted = hit.get("extracted") or {}
        if hit.get("label") == "match" and extracted.get("event_date"):
            yield Observation("news", extracted["event_date"], hit.get("source_id"),
                              passage=extracted.get("quote"))


def build_timeline(ctx, *, adapter=None, freshness_days=90):
    """Freshness is a C-local conservative policy, not a shared config addition."""
    run = db.get_run(ctx["run_id"])
    # Persisted UTC timestamp converted explicitly to the client's timezone.
    instant = datetime.fromisoformat(run["created_at"])
    if instant.tzinfo is None:
        raise ValueError("Run creation timestamp needs a timezone")
    evaluated = instant.astimezone(timezone(timedelta(hours=5, minutes=30))).date()
    adapter = adapter or _adapter
    errors, records, events = {}, {}, []
    try:
        observations = list(_existing_observations(ctx))
    except (TypeError, AttributeError):
        observations = []
        errors["adapter"] = "Malformed existing step outputs"
    if adapter is not None:
        try:
            observations.extend(adapter.observations(ctx))
        except Exception:
            errors["adapter"] = "Timeline adapter failed"
    for item in observations:
        kind = getattr(item, "kind", "adapter")
        try:
            provenance = ground_observation(item, ctx["run_id"])
            entry = {"value": item.value, "provenance": provenance}
            if kind in LABELS or kind in {"director_current_as_of", "coverage_from", "coverage_until", "predecessor_since"}:
                lo, hi, rendered, precision = date_bounds(item.value)
                if lo > evaluated:
                    raise ValueError("Future date is not historical evidence")
                entry.update(lo=lo, hi=hi, rendered=rendered, precision=precision)
                if kind in LABELS:
                    event = {"date": rendered, "precision": precision, "kind": kind,
                             "label": LABELS[kind], "source_id": item.source_id, "provenance": provenance}
                    if event not in events:
                        events.append(event)
            records.setdefault(kind, []).append(entry)
        except Exception:
            errors[kind] = "Malformed, future, unsupported, or ungrounded source data"

    def single(kind):
        items = records.get(kind, [])
        if kind in errors or "adapter" in errors:
            return None
        if len({json.dumps(e["value"], sort_keys=True) for e in items}) > 1:
            errors[kind] = "Conflicting source values; not selecting a convenient date"
            return None
        return items[0] if items else None

    evidence = []
    def emit(check, claim, dependencies, *, flag="none", missing=None, value=None):
        refs = [e["provenance"] for e in dependencies if e]
        first = refs[0] if refs else {}
        evidence.append({"check": check, "claim": claim, "value": {"details": value, "sources": refs},
                         "source_id": first.get("source_id"), "field_path": first.get("field_path"),
                         "passage": first.get("passage"), "record_date": first.get("record_date"),
                         "url": first.get("url"), "retrieved_at": first.get("retrieved_at"),
                         "status": missing or "verified", "flag": flag if not missing else "none",
                         "missing": claim if missing else None})

    def unavailable(check, kinds, reason):
        bad = any(k in errors for k in kinds) or "adapter" in errors
        emit(check, reason, [], missing="unknown" if bad else "cant_verify")

    founding, claimed, footer = single("founding"), single("claimed_since"), single("footer_year")
    for kind in ("incorporation", "brand_launch"):
        single(kind)
    if founding and claimed:
        gap = founding["lo"].year - claimed["hi"].year
        flag = "hard" if gap > ctx["config"]["rules"]["claimed_age_gap_years"] else "none"
        deps = [claimed, founding]
        reason = f"Website history year {claimed['rendered']} compared with verified founding {founding['rendered']}"
        if flag == "hard":
            confirmed, relation, since = (single(k) for k in (
                "predecessor_confirmed", "predecessor_relation", "predecessor_since"))
            website_sources = {p.get("source_id") for p in ctx["outputs"].get("site", {}).get("pages", [])}
            website_sources.update(e["provenance"]["source_id"] for key in ("claimed_since", "footer_year")
                                   for e in records.get(key, []))
            website_hosts = {urlsplit((db.get_source(sid) or {}).get("url") or "").hostname
                             for sid in website_sources if sid}
            website_hosts.discard(None)
            def independent(entry):
                host = urlsplit(entry["provenance"].get("url") or "").hostname
                return entry["provenance"]["source_id"] not in website_sources and not any(
                    host and (host == own or host.endswith("." + own) or own.endswith("." + host))
                    for own in website_hosts)
            if (confirmed and relation and since and confirmed["value"] is True
                    and relation["value"] in {"acquisition", "rebrand", "formerly_known_as"}
                    and since["hi"].year <= claimed["lo"].year
                    and all(independent(e) for e in (confirmed, relation, since))):
                flag = "soft"
                deps.extend([confirmed, relation, since])
                reason += "; verified predecessor history supports a legitimate " + relation["value"]
        emit("claimed_age_mismatch", reason, deps, flag=flag, value={"gap_years": gap})
    else:
        unavailable("claimed_age_mismatch", ["founding", "claimed_since"],
                    "Comparable founding and claimed-history evidence missing or conflicting; incorporation/brand launch alone is not trading history")

    if founding and footer:
        emit("footer_before_founding", "Website copyright year compared with verified founding; copyright is not proof of trading",
             [footer, founding], flag="soft" if footer["hi"].year < founding["lo"].year else "none")
    else:
        unavailable("footer_before_founding", ["founding", "footer_year"], "Verified founding and footer years missing or conflicting")

    start, current = single("director_start"), single("director_current_as_of")
    if start and current:
        fresh = current["precision"] == "day" and 0 <= (evaluated - current["lo"]).days <= freshness_days
        if current["provenance"]["record_date"]:
            try:
                fresh = fresh and date_bounds(current["provenance"]["record_date"])[1] >= current["lo"]
            except ValueError:
                fresh = False
        if not fresh or current["lo"] < start["lo"]:
            emit("director_recent", "Director current-role confirmation is stale or inconsistent", [start, current], missing="unknown")
        else:
            minimum = (evaluated - min(start["hi"], evaluated)).days
            maximum = (evaluated - start["lo"]).days
            threshold = ctx["config"]["rules"]["director_recent_days"]
            if minimum < threshold <= maximum:
                emit("director_recent", "Director date precision crosses the recent-tenure threshold", [start, current], missing="unknown")
            else:
                emit("director_recent", "Verified director tenure compared with configured recent-days threshold", [start, current],
                     flag="soft" if maximum < threshold else "none", value={"min_days": minimum, "max_days": maximum})
    else:
        unavailable("director_recent", ["director_start", "director_current_as_of"], "Verified director start and current-role confirmation are required")

    try:
        cutoff = evaluated.replace(year=evaluated.year - 1)
    except ValueError:  # Leap-day anniversary uses February 28.
        cutoff = evaluated.replace(year=evaluated.year - 1, day=28)
    recent = [e for kind in ACTIVITY for e in records.get(kind, []) if e["lo"] >= cutoff and kind not in errors]
    if recent:
        latest = max(recent, key=lambda e: e["lo"])
        emit("inactive_12m", "A source-backed dated activity signal occurs within the preceding 12 months; this alone does not prove trading", [latest])
    else:
        begin, end, complete, channels, activity_count = (single(k) for k in (
            "coverage_from", "coverage_until", "coverage_complete", "coverage_channels", "coverage_activity_count"))
        needed = {"jobs", "headcount", "news"}
        coverage = [begin, end, complete, channels, activity_count]
        valid = bool(all(coverage) and begin["hi"] <= cutoff and end["lo"] == evaluated and end["precision"] == "day"
                     and complete["value"] is True and isinstance(channels["value"], list)
                     and all(isinstance(c, str) for c in channels["value"])
                     and needed.issubset(channels["value"])
                     and type(activity_count["value"]) is int and activity_count["value"] == 0)
        # Current coverage must be refreshed through the evaluation day, not merely retrieved today.
        if valid:
            try:
                valid = all(date_bounds(e["provenance"]["record_date"])[0] == evaluated
                            and date_bounds(e["provenance"]["record_date"])[3] == "day" for e in coverage)
            except (TypeError, ValueError):
                valid = False
        uncertain_activity = any(kind in errors for kind in ACTIVITY) or any(
            e["lo"] < cutoff <= e["hi"] for kind in ACTIVITY for e in records.get(kind, []))
        if valid and not uncertain_activity:
            emit("inactive_12m", "Complete dated jobs/headcount/news coverage reports no activity in the preceding 12 months",
                 coverage, flag="soft", value={"from": cutoff.isoformat(), "until": evaluated.isoformat()})
        else:
            emit("inactive_12m", "Missing, stale, conflicting, or incomplete activity coverage is not evidence of inactivity",
                 coverage, missing="unknown" if any(coverage) or uncertain_activity or "adapter" in errors else "cant_verify")

    events.append({"date": evaluated.isoformat(), "precision": "day", "kind": "evaluation",
                   "label": "Evaluation date (run creation in Asia/Calcutta; not business activity)",
                   "source_id": None, "provenance": {"table": "runs", "run_id": ctx["run_id"],
                                                       "field_path": "created_at", "value": run["created_at"]}})
    for event in events:
        if event["kind"] in errors:
            event["label"] += " (conflicting or incomplete records; not used for flags)"
    events.sort(key=lambda e: (date_bounds(e["date"])[0], e["kind"], e["source_id"] or 0))
    return {"events": events, "evidence": evidence, "evaluation_date": evaluated.isoformat(),
            "issues": errors, "integration": {"b_adapter_configured": adapter is not None,
                                              "director_freshness_days": freshness_days}}
