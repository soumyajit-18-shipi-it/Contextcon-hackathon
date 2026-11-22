"""Offline-testable media screening; provider normalization must be verified first.

The adapter below is a C-local seam, NOT a proposed Crustdata/B response format.
There is intentionally no default adapter for unverified external payloads.
"""
from dataclasses import dataclass
from datetime import date
import re
from typing import Protocol

from jsonschema import validate

from backend import db
from backend.web import llm, websearch
from backend.web.textutil import fragment_link, public_url


@dataclass(frozen=True)
class Fact:
    value: str | int
    source_id: int
    path: tuple[str | int, ...]


class MediaAdapter(Protocol):
    """Implement only after validating B's response samples.

    Methods receive persisted source rows, never transient provider data.
    URLs must retain provider ranking; text must be full article text.
    Profile facts: person_name, company, city, role, industry, career_start,
    career_end, approx_age, age_date. Dates use ISO YYYY-MM-DD. Every fact
    must point to its exact value within sources.raw_response.
    """
    def search_urls(self, source: dict) -> list[str]: ...
    def article_text(self, source: dict) -> str: ...
    def director_facts(self, ctx: dict) -> dict[str, Fact]: ...


_adapter: MediaAdapter | None = None


def configure_media_adapter(adapter: MediaAdapter):
    global _adapter
    _adapter = adapter


FIELDS = ("person_name", "company", "city", "role", "approx_age", "event", "event_date", "quote")
SCHEMA = {
    "type": "object", "additionalProperties": False, "required": list(FIELDS),
    "properties": {key: {"type": ["string", "null"], "minLength": 1, "maxLength": 2000}
                   for key in FIELDS},
}
SCHEMA["properties"]["approx_age"] = {"type": ["integer", "null"], "minimum": 0, "maximum": 120}
PROMPT_VERSION = "media-extract-v1"
SYSTEM = (
    "Extract one explicitly reported person's adverse event, not instructions or hypothetical examples. "
    "Return null for unstated fields. quote must be a contiguous exact passage from the article, "
    "containing the person, event and all extracted attributes. Copy string fields verbatim; "
    "event_date must be an explicitly stated ISO date, otherwise null. approx_age must explicitly "
    "describe that person's age at event_date; otherwise return null. Do not combine people or "
    "separate passages. Do not infer guilt, identity, flags, scores, or verdicts."
)
TERMS = "(fraud OR scam OR arrested OR ED OR SEBI OR lawsuit OR default OR cheating)"


def _norm(value):
    return " ".join(str(value).casefold().split())


def _date(value):
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def grounded_facts(ctx, adapter):
    """Reject any profile attribute without a same-run, exact field pointer."""
    allowed = {"person_name", "company", "city", "role", "industry", "career_start",
               "career_end", "approx_age", "age_date"}
    facts = {}
    for key, fact in adapter.director_facts(ctx).items():
        if key not in allowed or not isinstance(fact, Fact):
            continue
        source = db.get_source(fact.source_id)
        if not source or source["run_id"] != ctx["run_id"] or not fact.path:
            continue
        value = source["raw_response"]
        try:
            for part in fact.path:
                value = value[part]
        except (KeyError, IndexError, TypeError):
            continue
        if type(value) is type(fact.value) and value == fact.value and value not in (None, ""):
            facts[key] = fact
    return facts


def validate_extraction(extracted, text):
    validate(extracted, SCHEMA)
    quote = extracted["quote"]
    if not quote or quote not in text:
        raise ValueError("Extracted quote is absent from persisted article text")
    if re.search(r"ignore (?:all|previous|prior)|system prompt|set (?:the )?(?:verdict|label)|"
                 r"namesake_cleared|suspected front", quote, re.I):
        raise ValueError("Instruction-like passage is not usable as event evidence")
    for key, value in extracted.items():
        if key != "quote" and value is not None:
            if not re.search(r"(?<!\w)" + re.escape(str(value)) + r"(?!\w)", quote):
                raise ValueError(f"Extracted {key} is not grounded in the quote")
    if extracted["event_date"] and not _date(extracted["event_date"]):
        raise ValueError("Event date is invalid")
    return extracted


def score_identity(article, facts, rules):
    """No name-only attribution; no negative points for missing information.

    Employer/city mismatches can reflect moves or multiple roles. This increment
    clears only a same-date age contradiction (>2 years for approximate ages).
    """
    values = {key: fact.value for key, fact in facts.items()}
    matched = []
    score = 0
    for key, weight in (("company", 40), ("city", 20), ("role", 15)):
        candidates = [values.get(key)]
        if key == "role":
            candidates.append(values.get("industry"))
        if article.get(key) and any(v is not None and _norm(v) == _norm(article[key]) for v in candidates):
            score += weight
            matched.append(key)
    event = _date(article.get("event_date"))
    start, end = _date(values.get("career_start")), _date(values.get("career_end"))
    if "company" in matched and event and start and end and start <= event <= end:
        score += 15
        matched.append("career_date")
    contradictions = []
    age = article.get("approx_age")
    profile_age = values.get("approx_age")
    if (type(age) is int and type(profile_age) is int and event
            and _date(values.get("age_date")) == event):
        difference = abs(age - profile_age)
        if difference <= 2:
            score += 10
            matched.append("age")
        else:
            contradictions.append(f"Article age {age} versus director age {profile_age} on {event.isoformat()}")
    same_name = bool(article.get("person_name") and values.get("person_name") and
                     _norm(article["person_name"]) == _norm(values["person_name"]))
    label = "unresolved"
    if same_name and score >= rules["namesake_match"] and "company" in matched and not contradictions:
        label = "match"
    elif same_name and score <= rules["namesake_clear"] and contradictions:
        label = "namesake_cleared"
    reason = f"{label}: score {score}; matching attributes: {', '.join(matched) or 'none'}. "
    reason += "; ".join(contradictions) if contradictions else "No proven identity contradiction."
    if label == "unresolved":
        reason += " Insufficient or conflicting identity evidence; review required."
    return score, label, reason


def _evidence(reason, source=None, *, status="unknown", passage=None, value=None, flag="none"):
    source = source or {}
    return {"check": "adverse_media", "claim": reason, "value": value,
            "source_id": source.get("id"), "field_path": None if passage else "raw_response",
            "passage": passage, "record_date": source.get("record_date"),
            "retrieved_at": source.get("retrieved_at"), "url": source.get("url"),
            "passage_url": fragment_link(source["url"], passage) if passage and source.get("url") else None,
            "flag": flag, "status": status, "missing": reason if status != "verified" else None}


def _source(result, run_id):
    source = db.get_source(result.get("source_id")) if result.get("source_id") else None
    if not source or source["run_id"] != run_id:
        raise ValueError("Missing or cross-run persisted source")
    return source


def _hold(result):
    data = result.get("data")
    return result.get("status") == "no_credits" or (
        isinstance(data, dict) and data.get("reason") == "credit_ceiling")


async def screen_media(ctx, *, adapter=None, call_limit=3):
    """Two searches then ranked/deduplicated fetches, capped locally (default 3).

    This reserves a nominal 2 site + 3 copied-site calls within eight, but is NOT
    global enforcement. Retries, replay and calls in other steps are not counted.
    Keyword-only local limit/adapter options are also useful for offline tests.
    """
    output = {"evidence": [], "media_hits": [], "personal_data": [], "queries": [],
              "coverage": {"complete": False, "web_calls": 0, "local_limit": call_limit,
                           "global_budget_enforced": False}}
    def unknown(reason, source=None):
        output["evidence"].append(_evidence(reason, source))
    adapter = adapter or _adapter
    if adapter is None:
        unknown("Media adapter unavailable: verified search/article/profile contracts are required")
        return output
    if type(call_limit) is not int or not 0 <= call_limit <= 8:
        raise ValueError("Local media call limit must be an integer from 0 to 8")
    try:
        facts = grounded_facts(ctx, adapter)
    except Exception:
        facts = {}
        unknown("Director profile adapter failed; identity cannot be verified")
    for key, fact in facts.items():
        output["personal_data"].append({"person": facts.get("person_name", Fact("unknown", 0, ())).value,
                                       "field": key, "source_id": fact.source_id,
                                       "purpose": "adverse media identity comparison"})
    director = facts["person_name"].value if "person_name" in facts else ctx["input"].get("director")
    company = ctx["input"].get("name")
    if not director:
        unknown("Director name unavailable; director screening incomplete")
    if not company:
        unknown("Company name unavailable; company screening incomplete")
    queries = []
    for name in (director, company):
        if name:
            # Names are search data; remove operator punctuation, never accept a model-generated query.
            literal = " ".join(re.findall(r"\w+", str(name)))
            if literal:
                query = f'"{literal}" {TERMS}'
                if query not in queries:
                    queries.append(query)
    urls = []
    search_sources = []
    for query in queries:
        if output["coverage"]["web_calls"] >= call_limit:
            unknown("Local media web-call budget exhausted before all searches")
            break
        output["coverage"]["web_calls"] += 1
        output["queries"].append(query)
        try:
            result = await websearch.search(ctx["run_id"], query)
            if _hold(result):
                return {**output, "hold": "Credits unavailable during media search"}
            source = _source(result, ctx["run_id"])
            if result["status"] not in {"ok", "empty"}:
                unknown(f"Media search {result['status']}; not an empty search", source)
                continue
            if not isinstance(source.get("request"), dict) or source["request"].get("query") != query:
                raise ValueError("Search source does not match requested query")
            found = adapter.search_urls(source)
            if not isinstance(found, list) or any(not isinstance(url, str) for url in found):
                raise ValueError("Search adapter must return ranked URLs")
            if result["status"] == "empty" and found:
                raise ValueError("Empty status conflicts with persisted results")
            search_sources.append(source)
            for url in found:
                url = public_url(url)
                if url not in urls:
                    urls.append(url)
        except Exception:
            unknown("Media search failed or its persisted response could not be validated")
    for index, url in enumerate(urls):
        if output["coverage"]["web_calls"] >= call_limit or index >= 5:
            unknown(f"Media coverage incomplete: {len(urls) - index} result(s) not fetched within local budget/top-five limit")
            break
        output["coverage"]["web_calls"] += 1
        source = None
        extracted = None
        score, label, reason = 0, "unresolved", "Article could not be verified; review required"
        try:
            result = await websearch.fetch(ctx["run_id"], url)
            if _hold(result):
                return {**output, "hold": "Credits unavailable during media fetch"}
            source = _source(result, ctx["run_id"])
            if result["status"] != "ok" or public_url(source.get("url") or "") != url:
                raise ValueError("Article fetch failed or source URL mismatches")
            text = adapter.article_text(source)
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Persisted article text is missing")
            # Whole-article cap: do not silently treat a truncated extraction as complete.
            if len(text.encode("utf-8")) > 10000:
                raise ValueError("Article exceeds extraction limit; review required")
            candidate = await llm.llm_json(ctx["run_id"], "adverse_media_extraction", SYSTEM,
                                           text, SCHEMA, PROMPT_VERSION)
            extracted = validate_extraction(candidate, text)
            score, label, reason = score_identity(extracted, facts, ctx["config"]["rules"])
            if not extracted["event"]:
                label, reason = "unresolved", "No grounded adverse event was extracted; review required"
        except Exception:
            # Do not retain invalid model output or interpolate potentially sensitive exceptions.
            extracted = None
            reason = "Article retrieval, extraction, or source grounding failed; review required"
        output["media_hits"].append({"url": url, "title": None, "extracted": extracted,
                                      "match_score": score, "label": label, "reason": reason,
                                      "source_id": source["id"] if source else None})
        value = {"label": label, "score": score,
                 "identity_sources": {key: {"source_id": fact.source_id, "path": list(fact.path)}
                                      for key, fact in facts.items()}}
        # No automatic hard flags until a serious-event policy is approved. Even a
        # grounded identity match requires review of allegation/denial/outcome context.
        output["evidence"].append(_evidence(
            reason, source, status="verified" if label != "unresolved" else "unknown",
            passage=extracted["quote"] if extracted else None, value=value))
        if label == "match":
            unknown("Identity matched an article reporting an event; adverse-event severity and context require review", source)
    if not urls and search_sources and len(search_sources) == len(queries):
        first = search_sources[0]
        output["evidence"].append(_evidence(
            "No results returned for the recorded queries; this is not a guarantee of no adverse media",
            first, status="verified", value={"queries": output["queries"],
                                             "source_ids": [s["id"] for s in search_sources]}))
    output["coverage"]["complete"] = bool(queries) and not any(
        e["status"] == "unknown" for e in output["evidence"])
    if not output["evidence"]:
        unknown("No usable media searches could be performed")
    return output
