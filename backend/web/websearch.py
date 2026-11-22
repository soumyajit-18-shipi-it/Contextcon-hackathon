"""Adapter to Member B's metered, cached client. No direct HTTP fallback.

Search follows the handoff contract. Fetch endpoint must be confirmed from the
kickoff API spec and configured explicitly; the handoff conflates search/fetch.
"""
import asyncio
import importlib
import os

from backend.web.textutil import public_url


def unavailable(reason, status="error"):
    return {"status": status, "data": {"reason": reason}, "source_id": None,
            "credits": 0, "latency_ms": 0}


async def _call(run_id, endpoint, payload):
    try:
        client = importlib.import_module("backend.data.crustdata")
    except ModuleNotFoundError as exc:
        if exc.name != "backend.data.crustdata":
            raise
        return unavailable("Member B's Crustdata client is not installed")
    try:
        result = await client.call(run_id, endpoint, payload)
    except (TimeoutError, asyncio.TimeoutError):
        return unavailable("Web source timed out", "timeout")
    if not isinstance(result, dict) or result.get("status") not in {
        "ok", "empty", "timeout", "error", "rate_limited", "no_credits"
    }:
        return unavailable("Invalid SourceResult from Crustdata client")
    return result


async def search(run_id, query, sources=None):
    """sources: optional Crustdata source filter, e.g. ["news"] (default: all sources)."""
    if not isinstance(query, str) or not query.strip():
        return unavailable("Search query is missing")
    payload = {"query": query, **({"sources": list(sources)} if sources else {})}
    return await _call(run_id, "/web/search/live", payload)


async def fetch(run_id, url):
    try:
        url = public_url(url)
    except (ValueError, AttributeError):
        return unavailable("Invalid public website URL")
    endpoint = os.getenv("CRUSTDATA_WEB_FETCH_ENDPOINT")
    if not endpoint:
        return unavailable("Fetch endpoint must be confirmed from the kickoff API spec")
    return await _call(run_id, endpoint, {"urls": [url]})
