"""Crustdata adapters for C's web steps (owned by C; written by the Lead to unblock live runs).

They read PERSISTED source rows only (sources.raw_response), using the real Crustdata shapes:
  web search  POST /web/search/live  -> {"results": [{"title", "url", "snippet", "position"}, ...]}
  web fetch   POST /web/enrich/live  -> [{"success", "url", "title", "content" (HTML), "timestamp"}]
  person enrich (director step)      -> [{"matches": [{"person_data": {"basic_profile": ..., "experience": ...}}]}]
"""
from urllib.parse import urlsplit

from backend import db
from backend.web.copied_site import UnrelatedBusiness
from backend.web.media import Fact
from backend.web.textutil import page_text

WEB_ENDPOINTS = ("/web/search/live", "/web/enrich/live")


def search_results(source: dict) -> list[dict]:
    raw = source.get("raw_response")
    return (raw.get("results") or []) if isinstance(raw, dict) else []


def fetched_html(source: dict) -> str:
    raw = source.get("raw_response")
    if isinstance(raw, list) and raw and isinstance(raw[0], dict) and raw[0].get("success"):
        return raw[0].get("content") or ""
    return raw if isinstance(raw, str) else ""


class LedgerWebBudget:
    """Per-run web-call ceiling (config limits.web_calls_per_run), counted from the ledger, so it holds
    across steps, retries and restarts. Cached answers write no ledger row, so they cost nothing here."""

    def __init__(self, limit: int):
        self.limit = limit

    def used(self, run_id: int) -> int:
        with db.connect() as conn:
            return conn.execute(
                f"SELECT COUNT(*) FROM ledger WHERE run_id = ? AND endpoint_or_model IN ({','.join('?' * len(WEB_ENDPOINTS))})",
                (run_id, *WEB_ENDPOINTS)).fetchone()[0]

    async def reserve(self, run_id: int) -> bool:
        return self.used(run_id) < self.limit


class CrustdataCopyAdapter:
    """Copied-site seam: result URLs from a search source, page text from a fetch source.
    Owner of a foreign page = its host (minus www). Different hosts are treated as different
    businesses; that is a stated limit (shared ownership across domains is not resolved)."""

    def search_urls(self, source: dict) -> list[str]:
        return [r["url"] for r in search_results(source) if isinstance(r.get("url"), str)]

    def page_text(self, source: dict) -> str:
        return page_text(fetched_html(source))[0]

    def unrelated_business(self, ctx: dict, source: dict):
        text = self.page_text(source)
        host = (urlsplit(source.get("url") or "").hostname or "").removeprefix("www.")
        if not host or not text:
            return None
        return UnrelatedBusiness(business_id=host, passage=text[:80])


def director_facts(ctx: dict) -> dict:
    """The first director profile, as Facts that point at exact paths in its Person Enrich source."""
    profiles = (ctx["outputs"].get("director") or {}).get("profiles") or []
    company_id = (ctx["outputs"].get("company") or {}).get("company_id")
    if not profiles or not profiles[0].get("source_id"):
        return {}
    source = db.get_source(profiles[0]["source_id"])
    try:
        person = source["raw_response"][0]["matches"][0]["person_data"]
    except (KeyError, IndexError, TypeError):
        return {}
    base = (0, "matches", 0, "person_data")
    facts = {}
    name = (person.get("basic_profile") or {}).get("name")
    if name:
        facts["person_name"] = Fact(name, source["id"], base + ("basic_profile", "name"))
    city = ((person.get("basic_profile") or {}).get("location") or {}).get("city")
    if city:
        facts["city"] = Fact(city, source["id"], base + ("basic_profile", "location", "city"))
    current = ((person.get("experience") or {}).get("employment_details") or {}).get("current") or []
    for i, role in enumerate(current):
        if role.get("crustdata_company_id") == company_id:
            path = base + ("experience", "employment_details", "current", i)
            if role.get("name"):
                facts["company"] = Fact(role["name"], source["id"], path + ("name",))
            if role.get("title"):
                facts["role"] = Fact(role["title"], source["id"], path + ("title",))
            break
    return facts
