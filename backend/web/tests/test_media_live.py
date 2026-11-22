"""Live media screen tests with FAKE search results and a FAKE LLM (no paid calls)."""
import asyncio

import pytest

from backend import db
from backend.config import load_config
from backend.web import llm, media_live, websearch


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("VERITY_DB_PATH", str(tmp_path / "m.db"))
    db.init_db()


def ctx(name="Alpha Roadlines", director="Ravi Rao"):
    inp = {"name": name, "director": director}
    return {"run_id": db.create_run(inp, load_config()["limits"]), "input": inp, "outputs": {},
            "config": load_config(), "client_id": "default"}


def fake_search(monkeypatch, results_by_term, status="ok"):
    async def search(run_id, query, sources=None):
        if status != "ok":
            return {"status": status, "data": None, "source_id": None, "credits": 0, "latency_ms": 1}
        results = next((v for k, v in results_by_term.items() if k in query), [])
        raw = {"success": True, "query": query, "results": results}
        sid = db.add_source(run_id, "crustdata", endpoint="/web/search/live", request={"query": query},
                            raw_response=raw, status="ok" if results else "empty")
        from backend.data import ledger
        ledger.record(run_id, "crustdata", "/web/search/live", credits=1)
        return {"status": "ok" if results else "empty", "data": raw, "source_id": sid, "credits": 1, "latency_ms": 1}
    monkeypatch.setattr(websearch, "search", search)


def fake_llm(monkeypatch, answer):
    async def llm_json(run_id, purpose, system, user, schema, prompt_version):
        return answer(user) if callable(answer) else answer
    monkeypatch.setattr(llm, "llm_json", llm_json)


def result(title, snippet, url="https://news.example.org/a"):
    return {"title": title, "snippet": snippet, "url": url, "position": 1}


def check(out):
    return [e for e in out["evidence"] if e["check"] == "adverse_media"]


def test_nothing_adverse_is_verified_clean_with_source(monkeypatch):
    fake_search(monkeypatch, {"Alpha": [result("Alpha Roadlines opens Pune hub", "Alpha Roadlines added 40 trucks.")]})
    out = asyncio.run(media_live.screen_media_live(ctx()))
    [e] = check(out)
    assert e["status"] == "verified" and e["source_id"] and "No adverse media" in e["claim"]


def test_company_as_victim_is_not_a_hit(monkeypatch):
    text_title, text_snip = "Alpha Roadlines warns of fraud calls", "Alpha Roadlines said scammers posed as its staff."
    fake_search(monkeypatch, {"Alpha": [result(text_title, text_snip)]})
    fake_llm(monkeypatch, {"subject_name": "Alpha Roadlines", "subject_type": "company", "accused": False,
                           "event": "scammers posed as its staff", "event_date": "", "city": "", "role": "",
                           "company": "", "quote": "scammers posed as its staff"})
    out = asyncio.run(media_live.screen_media_live(ctx()))
    assert out["media_hits"] == [] and check(out)[0]["status"] == "verified"


def test_company_accused_holds_for_review(monkeypatch):
    fake_search(monkeypatch, {"Alpha": [result("Alpha Roadlines booked for fraud", "Police booked Alpha Roadlines for GST fraud.")]})
    fake_llm(monkeypatch, {"subject_name": "Alpha Roadlines", "subject_type": "company", "accused": True,
                           "event": "GST fraud", "event_date": "", "city": "", "role": "", "company": "",
                           "quote": "Police booked Alpha Roadlines for GST fraud."})
    out = asyncio.run(media_live.screen_media_live(ctx()))
    assert out["media_hits"][0]["label"] == "unresolved"
    assert check(out)[0]["status"] == "unknown" and check(out)[0]["passage"] == "Police booked Alpha Roadlines for GST fraud."


def test_search_failure_is_unknown_never_clean(monkeypatch):
    fake_search(monkeypatch, {}, status="timeout")
    out = asyncio.run(media_live.screen_media_live(ctx()))
    assert all(e["status"] == "unknown" for e in check(out))


def test_quote_not_in_text_is_unknown(monkeypatch):
    fake_search(monkeypatch, {"Ravi": [result("Ravi Rao arrested", "Ravi Rao was arrested in Delhi for cheating.")]})
    fake_llm(monkeypatch, {"subject_name": "Ravi Rao", "subject_type": "person", "accused": True, "event": "cheating",
                           "event_date": "", "city": "Delhi", "role": "", "company": "",
                           "quote": "an invented quote that is not in the text"})
    out = asyncio.run(media_live.screen_media_live(ctx()))
    assert any(e["status"] == "unknown" for e in check(out)) and out["media_hits"] == []


def test_not_accused_needs_no_quote(monkeypatch):
    fake_search(monkeypatch, {"Alpha": [result("Alpha Roadlines gets SEBI nod for IPO", "SEBI approved Alpha Roadlines' IPO.")]})
    fake_llm(monkeypatch, {"subject_name": "Alpha Roadlines", "subject_type": "company", "accused": False, "event": "",
                           "event_date": "", "city": "", "role": "", "company": "", "quote": ""})
    out = asyncio.run(media_live.screen_media_live(ctx()))
    assert out["media_hits"] == [] and [e["status"] for e in check(out)] == ["verified"]


def test_budget_exhausted_is_unknown(monkeypatch):
    fake_search(monkeypatch, {"Alpha": [result("Alpha Roadlines news", "Nothing adverse here.")]})
    c = ctx()
    c["config"] = {**c["config"], "limits": {**c["config"]["limits"], "web_calls_per_run": 0}}
    out = asyncio.run(media_live.screen_media_live(c))
    assert any(e["status"] == "unknown" and "budget" in e["claim"] for e in check(out))
