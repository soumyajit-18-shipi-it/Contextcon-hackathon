"""Crustdata client. EVERY Crustdata call in Verity goes through call().

call() never raises. It always returns a SourceResult:
    {status: ok|empty|timeout|error|rate_limited|no_credits, data, source_id, credits, latency_ms}
and every outcome is stored: one `sources` row (request + raw response) and one `ledger` row per HTTP attempt.

Rules (from the docs + our brief):
  - headers: authorization: Bearer <CRUSTDATA_API_KEY>, x-api-version: 2025-11-01
  - per-endpoint rate limits (requests/minute) below; 20 s timeout; up to 2 retries on timeout/5xx
  - 429 -> wait x-ratelimit-reset, retry  |  402 -> no_credits, never retry  |  401/403 -> error, never retry
  - "empty" (no match) is a real answer and is NOT the same as "timeout"
  - per-run cache: the same (run, endpoint, payload) that already succeeded returns the stored source
    with no new call -> re-running a step after a kill costs zero credits
  - credit ceiling checked before calling; cost read from the X-Credits-Used header
"""
import asyncio
import json
import os
import time
from collections import deque

import httpx

from backend import db
from backend.data import ledger

BASE_URL = "https://api.crustdata.com"
API_VERSION = "2025-11-01"
TIMEOUT_S = 20
RETRIES = 2
# Live web search/fetch is slower than the data endpoints (observed 7-25 s on 2026-11-22), so it gets longer.
ENDPOINT_TIMEOUT_S = {"/web/search/live": 40, "/web/enrich/live": 40}

RATE_LIMITS = {  # requests per minute, per endpoint (Crustdata defaults)
    "/company/identify": 30, "/company/search": 30, "/person/search": 30, "/job/search": 30,
    "/company/enrich": 15, "/person/enrich": 15,
    "/web/search/live": 10, "/web/enrich/live": 10,
}
# Rough credits per call, used ONLY to stop before a call would break the run's credit ceiling.
ESTIMATED_CREDITS = {"/company/identify": 0.2, "/company/enrich": 5, "/person/enrich": 7,
                     "/person/search": 1, "/company/search": 1, "/job/search": 1,
                     "/web/search/live": 1, "/web/enrich/live": 1}

_recent_calls: dict[str, deque] = {}


def _result(status, data=None, source_id=None, credits=0.0, latency_ms=0) -> dict:
    return {"status": status, "data": data, "source_id": source_id, "credits": credits, "latency_ms": latency_ms}


async def _wait_for_rate_limit(endpoint: str):
    """Sliding 60-second window per endpoint. Check-and-append has no await in between, so it is safe
    with several asyncio workers."""
    limit = RATE_LIMITS.get(endpoint, 10)
    calls = _recent_calls.setdefault(endpoint, deque())
    while True:
        now = time.monotonic()
        while calls and now - calls[0] >= 60:
            calls.popleft()
        if len(calls) < limit:
            calls.append(now)
            return
        await asyncio.sleep(60 - (now - calls[0]) + 0.05)


def _reset_wait_seconds(response: httpx.Response) -> float:
    """x-ratelimit-reset may be seconds-to-wait or a unix timestamp; cap the wait at 60 s."""
    try:
        value = float(response.headers.get("x-ratelimit-reset", "5"))
    except ValueError:
        value = 5
    wait = value - time.time() if value > 1e9 else value
    return min(max(wait, 1), 60)


def _is_empty(data) -> bool:
    """No match / no results. (A failed web fetch also counts as empty: the page returned nothing.)"""
    if isinstance(data, list):
        if not data:
            return True
        if all(isinstance(d, dict) and "matches" in d for d in data):
            return all(not d["matches"] for d in data)
        if all(isinstance(d, dict) and "success" in d for d in data):
            return not any(d["success"] for d in data)
        return False
    if isinstance(data, dict):
        for key in ("results", "job_listings", "profiles", "companies"):
            if key in data:
                return not data[key]
    return data is None


def _record_date(data) -> str | None:
    """The record's own refresh date, if the response has one (enrich: company_data/person_data.updated_at)."""
    try:
        match = data[0]["matches"][0]
        record = match.get("company_data") or match.get("person_data") or {}
        return record.get("updated_at")
    except (KeyError, IndexError, TypeError):
        return None


def _headers() -> dict:
    return {"authorization": f"Bearer {os.environ.get('CRUSTDATA_API_KEY', '')}",
            "x-api-version": API_VERSION, "content-type": "application/json"}


async def call(run_id, endpoint: str, payload: dict | None, method: str = "POST") -> dict:
    request_json = json.dumps(payload, sort_keys=True, default=str)

    # 1. Per-run cache: already answered for this run -> no new call, no new credits.
    if run_id is not None:
        cached = db.find_cached_source(run_id, endpoint, request_json)
        if cached:
            return _result(cached["status"], cached["raw_response"], cached["id"], 0.0, 0)

    # 2. Credit ceiling: don't start a call the run can't afford.
    if run_id is not None:
        run = db.get_run(run_id)
        if run and run["credits_used"] + ESTIMATED_CREDITS.get(endpoint, 1) > run["credit_limit"]:
            return _result("error", {"reason": "credit_ceiling"})

    if not os.environ.get("CRUSTDATA_API_KEY"):
        return _result("error", {"reason": "CRUSTDATA_API_KEY is not set"})

    # 3. Call with retries.
    status, data, http_status, total_credits, started = "error", None, None, 0.0, time.monotonic()
    for attempt in range(1 + RETRIES):
        await _wait_for_rate_limit(endpoint)
        attempt_started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=ENDPOINT_TIMEOUT_S.get(endpoint, TIMEOUT_S)) as client:
                response = await client.request(method, BASE_URL + endpoint, headers=_headers(),
                                                content=request_json if payload is not None else None)
        except httpx.TimeoutException:
            status, data, http_status = "timeout", {"reason": f"no answer within {ENDPOINT_TIMEOUT_S.get(endpoint, TIMEOUT_S)}s"}, None
            ledger.record(run_id, "crustdata", endpoint, latency_ms=_ms(attempt_started))
            await asyncio.sleep(attempt + 1)
            continue
        except httpx.HTTPError as e:
            status, data, http_status = "error", {"reason": f"network error: {type(e).__name__}"}, None
            ledger.record(run_id, "crustdata", endpoint, latency_ms=_ms(attempt_started))
            await asyncio.sleep(attempt + 1)
            continue

        http_status = response.status_code
        credits = float(response.headers.get("x-credits-used") or 0)
        total_credits += credits
        ledger.record(run_id, "crustdata", endpoint, credits=credits, latency_ms=_ms(attempt_started),
                      http_status=http_status)
        try:
            data = response.json()
        except ValueError:
            data = {"raw_text": response.text[:2000]}

        if http_status == 200:
            status = "empty" if _is_empty(data) else "ok"
            break
        if http_status == 404:                      # documented as "no data found"
            status = "empty"
            break
        if http_status == 429:
            status = "rate_limited"
            await asyncio.sleep(_reset_wait_seconds(response))
            continue
        if http_status == 402:                      # credits gone: retrying can't help
            status = "no_credits"
            break
        if http_status in (401, 403, 400):          # our key/request is wrong: retrying can't help
            status = "error"
            break
        status = "error"                            # 5xx: retry
        await asyncio.sleep(attempt + 1)

    # 4. Store what came back (also failures, so the audit trail is complete).
    source_id = db.add_source(run_id, "crustdata", endpoint=endpoint, url=BASE_URL + endpoint,
                              request=payload, raw_response=data,
                              record_date=_record_date(data) if status == "ok" else None,
                              status=status, http_status=http_status)
    return _result(status, data, source_id, total_credits, _ms(started))


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


async def get_credits() -> dict:
    """Remaining balance. GET /account/credits is free."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            response = await client.get(BASE_URL + "/account/credits", headers=_headers())
        if response.status_code != 200:
            return {"status": "error", "http_status": response.status_code}
        account = response.json().get("account", {})
        return {"status": "ok", "credits": account.get("credits"), "account": account}
    except httpx.HTTPError as e:
        return {"status": "error", "reason": type(e).__name__}
