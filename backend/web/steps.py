"""Member C steps. Return evidence for atomic checkpointing by the engine."""
import re

from backend import db
from backend.web import websearch
from backend.web.textutil import about_url, fragment_link, page_text, public_url


async def step_media(ctx):
    """Live news screen on Crustdata web search (backend/web/media_live.py).
    An explicitly configured media adapter (C's offline tests) uses C's original screen."""
    from backend.web import media
    if media._adapter is not None:
        return await media.screen_media(ctx)
    from backend.web.media_live import screen_media_live
    return await screen_media_live(ctx)


async def step_copied_site(ctx):
    """C's copied-site check with the Crustdata adapter. It may use the run's web budget minus the calls
    reserved for the news screen, which runs after it and must not be starved.
    An explicitly configured adapter (C's offline tests) is used as configured."""
    from backend.web import copied_site
    from backend.web.adapters import CrustdataCopyAdapter, LedgerWebBudget
    from backend.web.copied_site import screen_copied_site
    if copied_site._adapter is not None:
        return await screen_copied_site(ctx)
    limits = ctx["config"]["limits"]
    budget = LedgerWebBudget(limits["web_calls_per_run"] - limits["media_web_calls"])
    return await screen_copied_site(ctx, adapter=CrustdataCopyAdapter(), budget=budget)


async def step_timeline(ctx):
    """C's timeline fed by the Crustdata timeline adapter (founding, claimed year, director dates, activity).
    An explicitly configured adapter (C's offline tests) is used as configured."""
    from backend.web import timeline
    from backend.web.adapters import CrustdataTimelineAdapter
    if timeline._adapter is not None:
        return timeline.build_timeline(ctx)
    return timeline.build_timeline(ctx, adapter=CrustdataTimelineAdapter())


async def step_explain(ctx):
    from backend.web.explain import explain_verdict
    return await explain_verdict(ctx)


def _content(data):
    """Accept only explicit full-page fields; snippets are not page content."""
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        return _content(data[0]) if len(data) == 1 else ""
    if isinstance(data, dict):
        for key in ("text", "html", "content", "markdown"):
            if isinstance(data.get(key), str):
                return data[key]
        for key in ("data", "results", "pages"):
            if key in data:
                return _content(data[key])
    return ""


async def step_site(ctx):
    output = {"pages": [], "footer_year": None, "claimed_since_year": None, "evidence": []}
    website = ctx["input"].get("website")
    if not website:
        chosen = ctx["outputs"].get("resolve", {}).get("chosen") or {}
        website = chosen.get("domain")
    try:
        home = public_url(website or "")
    except ValueError:
        output["evidence"].append(_missing("cant_verify", "No valid vendor website supplied"))
        return output
    url = home
    for index in range(2):
        result = await websearch.fetch(ctx["run_id"], url)
        if result["status"] == "no_credits":
            return {"hold": "Crustdata credits exhausted during website retrieval"}
        data = result.get("data") or {}
        if isinstance(data, dict) and data.get("reason") == "credit_ceiling":
            return {"hold": "Credit ceiling reached during website retrieval"}
        text, links = page_text(_content(data)) if result["status"] == "ok" else ("", [])
        source_id = result.get("source_id")
        source = db.get_source(source_id) if source_id else None
        page = {"url": url, "text": text, "source_id": source_id,
                "status": result["status"], "retrieved_at": (source or {}).get("retrieved_at")}
        output["pages"].append(page)
        if not text or not source:
            status = "cant_verify" if result["status"] in {"ok", "empty"} else "unknown"
            reason = f"{url}: page content or persisted source unavailable ({result['status']})"
            prior = next((e for e in output["evidence"] if e["check"] == "site"), None)
            if prior:
                prior["missing"] += "; " + reason
                if status == "unknown":
                    prior["status"] = status
            else:
                output["evidence"].append(_missing(status, reason))
        else:
            for key, pattern in (
                ("footer_year", r"(?:©|copyright)\s*((?:19|20)\d{2})"),
                ("claimed_since_year", r"(?:since|established(?:\s+in)?|founded(?:\s+in)?)\s+((?:19|20)\d{2})"),
            ):
                match = re.search(pattern, text, re.I)
                if match:
                    year = int(match.group(1))
                    if output[key] is None:
                        output[key] = year
                    output["evidence"].append({
                        "check": key, "claim": f"Website states {match.group(0)}", "value": year,
                        "source_id": source_id, "field_path": None, "passage": match.group(0),
                        "record_date": source.get("record_date"), "retrieved_at": source["retrieved_at"],
                        "url": url, "passage_url": fragment_link(url, match.group(0)),
                        "flag": "none", "status": "verified", "missing": None,
                    })
        if index == 0:
            url = about_url(home, links)
    return output


def _missing(status, reason):
    return {"check": "site", "claim": "Website retrieval incomplete", "value": None,
            "source_id": None, "field_path": None, "passage": None, "record_date": None,
            "status": status, "flag": "none", "missing": reason}
