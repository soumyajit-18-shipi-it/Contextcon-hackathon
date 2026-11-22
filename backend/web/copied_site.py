"""Grounded text-overlap checks with explicit, unconfigured integration seams."""
from dataclasses import dataclass
import re
from typing import Protocol
from urllib.parse import urlsplit

from backend import db
from backend.web import websearch
from backend.web.textutil import distinctive_sentences, fragment_link, public_url


@dataclass(frozen=True)
class UnrelatedBusiness:
    """Adapter-confirmed independent owner, with supporting page passage.

    Different hosts alone do not establish unrelated businesses. The integration
    must resolve affiliations before returning this assessment; otherwise None.
    business_id is a stable owner identifier, shared by that owner's domains.
    """
    business_id: str
    passage: str


class CopyAdapter(Protocol):
    """C-local seam, not a Crustdata payload contract. No network calls here."""
    def search_urls(self, source: dict) -> list[str]: ...
    def page_text(self, source: dict) -> str: ...
    def unrelated_business(self, ctx: dict, source: dict) -> UnrelatedBusiness | None: ...


class CallBudget(Protocol):
    """Integration hook: atomically reserve one remaining call BEFORE dispatch.

    The implementation must coordinate all run steps/retries to enforce a global
    ceiling. No such implementation exists here; tests supply a local fake.
    """
    async def reserve(self, run_id: int) -> bool: ...


_adapter = None
_budget = None


def configure_copied_site(adapter: CopyAdapter, budget: CallBudget | None = None):
    global _adapter, _budget
    _adapter, _budget = adapter, budget


EXCLUDED = (
    "linkedin.com", "crunchbase.com", "indiamart.com", "justdial.com", "tracxn.com",
    "zaubacorp.com", "tofler.in", "tofler.com", "glassdoor.com", "glassdoor.co.in",
    "ambitionbox.com", "facebook.com", "instagram.com", "twitter.com", "x.com",
    "youtube.com", "youtu.be", "tiktok.com", "reddit.com", "pinterest.com", "threads.net",
)
TEMPLATE = re.compile(r"\blorem\s+ipsum\b|\byour\s+company\s+name\b", re.I)


def _host(url):
    return (urlsplit(public_url(url)).hostname or "").lower().rstrip(".").removeprefix("www.")


def excluded_url(url, vendor_hosts):
    host = _host(url)
    return any(host == d or host.endswith("." + d) for d in EXCLUDED) or any(
        host == d or host.endswith("." + d) or d.endswith("." + host) for d in vendor_hosts)


def _source(source_id, run_id, url=None):
    source = db.get_source(source_id) if source_id else None
    if not source or source["run_id"] != run_id:
        raise ValueError("Missing or cross-run source")
    if url and public_url(source.get("url") or "") != public_url(url):
        raise ValueError("Source URL mismatch")
    return source


def _evidence(claim, source=None, passage=None, *, status="unknown", flag="none", value=None):
    source = source or {}
    return {"check": "copied_site", "claim": claim, "value": value,
            "source_id": source.get("id"), "field_path": None if passage else "raw_response",
            "passage": passage, "url": source.get("url"),
            "record_date": source.get("record_date"), "retrieved_at": source.get("retrieved_at"),
            "passage_url": fragment_link(source["url"], passage) if passage and source.get("url") else None,
            "status": status, "flag": flag, "missing": claim if status != "verified" else None}


def _hold(result):
    return result.get("status") == "no_credits" or (
        isinstance(result.get("data"), dict) and result["data"].get("reason") == "credit_ceiling")


def independent_count(overlaps):
    """Maximum distinct sentence/independent owner matching (at most 3 sentences)."""
    graph = {}
    for item in overlaps:
        graph.setdefault(item["sentence"], set()).add(item["business_id"])
    def count(sentences, used):
        if not sentences:
            return 0
        first, *rest = sentences
        return max([count(rest, used)] + [1 + count(rest, used | {owner})
                                        for owner in graph[first] - used])
    return count(list(graph), set())


async def screen_copied_site(ctx, *, adapter=None, budget=None):
    adapter = adapter or _adapter
    budget = budget or _budget
    out = {"evidence": [], "sentences": [], "overlaps": [], "queries": [],
           "coverage": {"complete": False, "web_calls": 0, "global_budget_enforced": False}}
    problems = []
    def unknown(reason, source=None):
        problems.append((reason, source))
    async def reserve():
        if budget is None or await budget.reserve(ctx["run_id"]) is not True:
            raise ValueError("Shared budget unavailable or exhausted")
        out["coverage"]["web_calls"] += 1
    if adapter is None:
        out["evidence"] = [_evidence("Copied-site adapter unavailable; verified response mappings required")]
        return out
    pages = ctx["outputs"].get("site", {}).get("pages", [])
    hosts, candidates, template_evidence = set(), {}, []
    for page in pages:
        try:
            if page.get("status") != "ok":
                raise ValueError("Vendor page was not retrieved")
            source = _source(page.get("source_id"), ctx["run_id"], page["url"])
            persisted = adapter.page_text(source)
            text = page.get("text")
            if not isinstance(text, str) or not text.strip() or not isinstance(persisted, str) or text not in persisted:
                raise ValueError("Site output text not grounded in persisted source")
            hosts.add(_host(page["url"]))
            for match in TEMPLATE.finditer(text):
                template_evidence.append(_evidence(
                    "Website contains explicit template placeholder text", source, match.group(0),
                    status="verified", flag="hard", value={"marker": match.group(0)}))
            for sentence in distinctive_sentences(text):
                candidates.setdefault(sentence, source)
        except Exception:
            unknown("Vendor page unavailable or provenance could not be validated")
    if not pages:
        unknown("No site pages available for copied-site checks")
    out["evidence"].extend(template_evidence)
    selected = list(candidates)[:3]
    out["sentences"] = selected
    search_sources, fetched = [], {}
    if not selected and not template_evidence:
        unknown("No distinctive 12–30 word sentences available; originality cannot be assessed")
    for sentence in selected:
        query = '"' + sentence + '"'
        search_source = None
        try:
            await reserve()
            out["queries"].append(query)
            result = await websearch.search(ctx["run_id"], query)
            if _hold(result):
                return {**out, "hold": "Credits unavailable during copied-site search"}
            search_source = _source(result.get("source_id"), ctx["run_id"])
            if result.get("status") not in {"ok", "empty"}:
                raise ValueError("Search failed")
            if (search_source.get("request") or {}).get("query") != query:
                raise ValueError("Search query/source mismatch")
            urls = adapter.search_urls(search_source)
            if not isinstance(urls, list) or any(not isinstance(u, str) for u in urls):
                raise ValueError("Unrecognized search response")
            if result["status"] == "empty" and urls:
                raise ValueError("Inconsistent empty search")
            search_sources.append(search_source)
        except Exception:
            unknown("Exact-quote search incomplete: provider, provenance, or remaining budget unavailable", search_source)
            continue
        for url in dict.fromkeys(urls):
            foreign = None
            try:
                url = public_url(url)
                if excluded_url(url, hosts):
                    continue
                if url not in fetched:
                    await reserve()
                    result = await websearch.fetch(ctx["run_id"], url)
                    if _hold(result):
                        return {**out, "hold": "Credits unavailable during copied-site fetch"}
                    foreign = _source(result.get("source_id"), ctx["run_id"], url)
                    if result.get("status") != "ok":
                        raise ValueError("Page inaccessible")
                    text = adapter.page_text(foreign)
                    if not isinstance(text, str) or not text.strip():
                        raise ValueError("No full source text")
                    fetched[url] = (foreign, text)
                foreign, text = fetched[url]
                # A matching snippet has no role in this decision.
                if sentence not in text:
                    continue
                business = adapter.unrelated_business(ctx, foreign)
                if (not isinstance(business, UnrelatedBusiness) or not business.business_id
                        or not business.passage or business.passage not in text):
                    raise ValueError("Business independence not established")
                out["overlaps"].append({"sentence": sentence, "business_id": business.business_id,
                    "source_id": foreign["id"], "url": url, "business_passage": business.passage,
                    "vendor_source_id": candidates[sentence]["id"], "vendor_url": candidates[sentence]["url"],
                    "search_source_id": search_source["id"]})
            except Exception:
                unknown("Result text or unrelated-business status unverified, or remaining budget exhausted", foreign)
    count = independent_count(out["overlaps"])
    flag = "hard" if count >= 2 else "soft" if count == 1 else "none"
    for overlap in out["overlaps"]:
        source = db.get_source(overlap["source_id"])
        out["evidence"].append(_evidence(
            f"Text also appears on {overlap['url']}; direction of copying is not established",
            source, overlap["sentence"], status="verified", flag=flag,
            value={**overlap, "independent_overlaps": count}))
    # Aggregate coverage problems so a missing dependency does not duplicate check rows.
    if problems:
        out["evidence"].append(_evidence("; ".join(dict.fromkeys(p[0] for p in problems)),
                                        next((p[1] for p in problems if p[1]), None)))
    out["coverage"]["complete"] = bool(selected or template_evidence) and not problems
    if not out["evidence"] and search_sources:
        out["evidence"].append(_evidence(
            "No distinctive overlaps verified within the recorded searches; this does not prove originality",
            search_sources[0], status="verified", value={"queries": out["queries"],
                "search_source_ids": [s["id"] for s in search_sources],
                "inspected_source_ids": [s[0]["id"] for s in fetched.values()]}))
    return out
