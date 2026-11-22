"""Duplicate check tests. All vendors below are made up and exist only in this test file."""
import asyncio

from fastapi.testclient import TestClient

from backend import db
from backend.config import load_config
from backend.engine import orchestrator
from backend.engine.duplicate import step_duplicate
from backend.main import app


def add_vendor(name, domain=None, director=None):
    with db.connect() as conn:
        conn.execute("INSERT INTO client_vendors (client_id, name, domain, director) VALUES ('default', ?, ?, ?)",
                     (name, domain, director))


def run_duplicate(inp, chosen=None):
    run_id = db.create_run(inp, load_config()["limits"])
    ctx = {"run_id": run_id, "client_id": "default", "input": inp, "config": load_config(),
           "outputs": {"resolve": {"chosen": chosen or {"name": inp["name"], "domain": inp.get("website")}}}}
    return asyncio.run(step_duplicate(ctx))


def checks(out):
    return {e["check"]: e for e in out["evidence"]}


def test_same_domain_is_exact_duplicate_and_blocks_clearing():
    add_vendor("Shree Ganesh Roadways Pvt Ltd", "shreeganeshroadways.in", "Amit Verma")
    out = run_duplicate({"name": "Shree Ganesh Roadways", "website": "https://www.shreeganeshroadways.in/about"})
    assert checks(out)["duplicate_exact"]["flag"] == "hard"
    assert out["duplicate_of"].startswith("client vendor #")


def test_same_director_and_similar_name_is_likely_duplicate():
    add_vendor("Shree Ganesh Roadways Pvt Ltd", "sgroadways.com", "Amit Verma")
    out = run_duplicate({"name": "Shree Ganesh Roadway", "website": "shreeganesh-roadway.in", "director": "Verma Amit"})
    e = checks(out)["duplicate_likely"]
    assert e["flag"] == "soft" and e["field_path"] == "director"
    assert out["duplicate_of"] is None          # likely, not certain: a person decides


def test_similar_name_other_director_is_lookalike_name():
    add_vendor("Bharat Freight Carriers", "bharatfreight.in", "Ravi Shah")
    out = run_duplicate({"name": "Bharat Freight Carrier", "website": "bharat-freight-carrier.com",
                         "director": "Someone Else"})
    assert checks(out)["lookalike_name"]["flag"] == "soft"


def test_unrelated_vendor_is_not_a_duplicate():
    add_vendor("Bharat Freight Carriers", "bharatfreight.in", "Ravi Shah")
    out = run_duplicate({"name": "Coastal Cold Chain", "website": "coastalcoldchain.in"})
    e = checks(out)["duplicate"]
    assert out["matches"] == [] and e["status"] == "verified" and e["flag"] == "none"


def test_no_client_records_is_cant_verify_not_clean():
    out = run_duplicate({"name": "Coastal Cold Chain", "website": "coastalcoldchain.in"})
    e = checks(out)["duplicate"]
    assert e["status"] == "cant_verify" and "client records not loaded" in e["missing"]


def test_submitted_twice_matches_the_earlier_run():
    run_duplicate({"name": "Coastal Cold Chain", "website": "coastalcoldchain.in"})       # run 1
    out = run_duplicate({"name": "Coastal Cold Chain", "website": "coastalcoldchain.in"})  # run 2
    assert checks(out)["duplicate_past_run"]["flag"] == "soft"
    assert out["duplicate_of"] == "run #1"


def test_unresolvable_vendor_on_client_books_still_holds_as_duplicate(monkeypatch):
    add_vendor("Shree Ganesh Roadways Pvt Ltd", "shreeganeshroadways.in", "Amit Verma")

    async def nothing_found(ctx):
        return {"by_domain": None, "by_name": None, "candidates": [], "chosen": None, "match_confidence": None}

    steps = [(n, nothing_found if n == "resolve" else f) for n, f in orchestrator.get_step_functions()]
    monkeypatch.setattr(orchestrator, "get_step_functions", lambda: steps)
    run_id = db.create_run({"name": "SG Roadways", "website": "shreeganeshroadways.in"}, load_config()["limits"])
    asyncio.run(orchestrator.drain_queue())
    v = db.get_verdict(run_id)
    assert (v["verdict"], v["flags"]["rule"]) == ("HOLD FOR REVIEW", "1_exact_duplicate")
    assert db.get_run(run_id)["duplicate_of"]


def test_duplicate_run_holds_and_cannot_be_cleared_via_api():
    add_vendor("Shree Ganesh Roadways Pvt Ltd", "shreeganeshroadways.in", "Amit Verma")
    run_id = db.create_run({"name": "Shree Ganesh Roadways", "website": "shreeganeshroadways.in"},
                           load_config()["limits"])
    asyncio.run(orchestrator.drain_queue())
    run = db.get_run(run_id)
    assert run["status"] == "awaiting_approval" and run["duplicate_of"]
    assert db.get_verdict(run_id)["verdict"] == "HOLD FOR REVIEW"   # B/C still stubbed: core checks cant_verify

    client = TestClient(app)   # no `with`: the background worker is not started
    r = client.post(f"/runs/{run_id}/approve", json={"decision": "clear", "reason": "looks fine", "user": "lead"})
    assert r.status_code == 409 and "duplicate" in r.text
    r = client.post(f"/runs/{run_id}/approve", json={"decision": "reject", "reason": "already a vendor", "user": "lead"})
    assert r.status_code == 200
