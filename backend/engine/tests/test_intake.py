"""Intake tests. The LLM is faked here; no paid calls."""
import asyncio

from fastapi.testclient import TestClient

from backend import db
from backend.config import load_config
from backend.engine import orchestrator
from backend.engine.intake import step_intake
from backend.main import app
from backend.web import llm


def ctx(inp):
    run_id = db.create_run(inp, load_config()["limits"])
    return {"run_id": run_id, "input": inp, "outputs": {}, "config": load_config(), "client_id": "default"}


def fake_llm(monkeypatch, answer):
    calls = []

    async def llm_json(run_id, purpose, system, user, schema, prompt_version):
        calls.append(prompt_version)
        return answer
    monkeypatch.setattr(llm, "llm_json", llm_json)
    return calls


def test_structured_fields_are_kept_and_no_llm_needed(monkeypatch):
    calls = fake_llm(monkeypatch, {})
    out = asyncio.run(step_intake(ctx({"name": "Alpha Roadlines", "website": "alpharoadlines.in",
                                        "director": "A. Shah", "claimed_year": 2012})))
    assert out["input"]["name"] == "Alpha Roadlines" and calls == [] and out["llm"] == "not needed"


def test_free_text_regex_then_llm(monkeypatch):
    text = "Please onboard Beta Movers (betamovers.com), run by Ravi Rao, in business since 2014."
    calls = fake_llm(monkeypatch, {"name": "Beta Movers", "website": "", "director": "Ravi Rao", "claimed_year": "2014"})
    out = asyncio.run(step_intake(ctx({"request_text": text})))
    assert out["input"]["website"] == "betamovers.com" and out["how"]["website"] == "regex"
    assert out["input"]["name"] == "Beta Movers" and out["how"]["name"] == "llm"
    assert out["input"]["claimed_year"] == 2014 and calls == ["intake-v1"]


def test_llm_value_not_in_the_text_is_dropped(monkeypatch):
    fake_llm(monkeypatch, {"name": "Gamma Freight", "website": "", "director": "Invented Person", "claimed_year": ""})
    out = asyncio.run(step_intake(ctx({"request_text": "New carrier: Gamma Freight for the Chennai lane"})))
    assert out["input"]["name"] == "Gamma Freight" and not out["input"].get("director")


def test_nothing_usable_waits_for_input(monkeypatch):
    fake_llm(monkeypatch, {"name": "", "website": "", "director": "", "claimed_year": ""})
    out = asyncio.run(step_intake(ctx({"request_text": "We need a new carrier for next month"})))
    assert "await_input" in out


def test_llm_unavailable_still_uses_regex():
    out = asyncio.run(step_intake(ctx({"request_text": "check deltacargo.in please"})))   # no LLM configured in tests
    assert out["input"]["website"] == "deltacargo.in" and out["llm"].startswith("unavailable")


def test_awaiting_input_then_person_adds_name(monkeypatch):
    fake_llm(monkeypatch, {"name": "", "website": "", "director": "", "claimed_year": ""})
    client = TestClient(app)
    run_id = client.post("/runs", json={"request_text": "We need a new carrier"}).json()["id"]
    asyncio.run(orchestrator.drain_queue())
    assert db.get_run(run_id)["status"] == "awaiting_input"
    assert client.post(f"/runs/{run_id}/input", json={"name": "Epsilon Logistics"}).status_code == 200
    asyncio.run(orchestrator.drain_queue())
    run = db.get_run(run_id)
    assert run["status"] == "awaiting_approval" and run["input"]["name"] == "Epsilon Logistics"


def test_post_runs_needs_something_to_go_on():
    assert TestClient(app).post("/runs", json={"director": "Someone"}).status_code == 422
