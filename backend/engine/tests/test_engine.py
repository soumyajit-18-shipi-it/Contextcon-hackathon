"""Engine tests (Lead). Mock data lives only here. Run: .venv/Scripts/python -m pytest -q backend"""
import asyncio

import pytest

from backend import db
from backend.config import load_config
from backend.engine import orchestrator
from backend.engine.verdict import decide

INPUT = {"name": "Test Carrier Pvt Ltd", "website": "testcarrier.in"}


class Crash(BaseException):
    """Simulates kill -9: not an Exception, so the engine can't catch it."""


def new_run():
    return db.create_run(INPUT, load_config()["limits"])


def counted_steps(overrides=None):
    """Real step functions (stubs for B/C), wrapped to count calls. overrides: {name: func}."""
    calls = {}
    steps = []
    for name, func in orchestrator.get_step_functions():
        func = (overrides or {}).get(name, func)

        async def wrapper(ctx, _name=name, _func=func):
            calls[_name] = calls.get(_name, 0) + 1
            return await _func(ctx)
        steps.append((name, wrapper))
    return steps, calls


def test_full_run_with_stubs_reaches_approval_with_cannot_verify():
    run_id = new_run()
    asyncio.run(orchestrator.drain_queue())
    run = db.get_run(run_id)
    assert run["status"] == "awaiting_approval"
    verdict = db.get_verdict(run_id)
    assert verdict["verdict"] == "CANNOT VERIFY"          # stubs never produce a fake "CLEARED"
    assert "STUB" in verdict["report_md"] or "stubbed" in verdict["report_md"]
    assert len(db.get_steps(run_id)) == len(orchestrator.STEPS)


def test_resume_after_kill_skips_finished_steps(monkeypatch):
    run_id = new_run()
    state = {"crashed": False}

    async def director_that_dies_once(ctx):
        if not state["crashed"]:
            state["crashed"] = True
            raise Crash()
        return {"profiles": []}

    steps, calls = counted_steps({"director": director_that_dies_once})
    monkeypatch.setattr(orchestrator, "get_step_functions", lambda: steps)

    with pytest.raises(Crash):
        asyncio.run(orchestrator.drain_queue())
    assert db.get_run(run_id)["status"] == "running"      # killed mid-run

    assert db.requeue_interrupted_runs() == [run_id]      # what startup does
    asyncio.run(orchestrator.drain_queue())

    assert db.get_run(run_id)["status"] == "awaiting_approval"
    assert calls["resolve"] == 1 and calls["company"] == 1   # finished before the kill -> not re-run
    assert calls["director"] == 2                             # the interrupted step runs again
    checks = [e["check"] for e in db.get_evidence(run_id)]
    assert len(checks) == len(set(checks))                    # no duplicated evidence


def test_step_failing_twice_is_unknown_and_verdict_holds(monkeypatch):
    run_id = new_run()

    async def boom(ctx):
        raise ValueError("source down")

    async def good_core(ctx):   # mock data: enough verified facts that only the failure blocks CLEARED
        return {"evidence": [
            {"check": "director_current_role", "claim": "director current role", "value": "Director",
             "source_id": 1, "field_path": "x", "status": "verified", "flag": "none"},
            {"check": "headcount_present", "claim": "headcount", "value": 40,
             "source_id": 1, "field_path": "y", "status": "verified", "flag": "none"},
        ]}

    steps, calls = counted_steps({"media": boom, "core_checks": good_core})
    monkeypatch.setattr(orchestrator, "get_step_functions", lambda: steps)
    asyncio.run(orchestrator.drain_queue())

    assert calls["media"] == 2                                # retried once
    assert db.get_verdict(run_id)["verdict"] == "HOLD FOR REVIEW"
    assert any(e["status"] == "unknown" for e in db.get_evidence(run_id))


def test_several_candidates_waits_for_a_person(monkeypatch):
    run_id = new_run()

    async def vague(ctx):
        return {"by_domain": None, "by_name": None, "candidates": [{"name": "A"}, {"name": "B"}],
                "chosen": None, "match_confidence": 0.4}

    steps, _ = counted_steps({"resolve": vague})
    monkeypatch.setattr(orchestrator, "get_step_functions", lambda: steps)
    asyncio.run(orchestrator.drain_queue())
    assert db.get_run(run_id)["status"] == "awaiting_candidate"


def test_not_found_skips_to_cannot_verify(monkeypatch):
    run_id = new_run()

    async def nothing(ctx):
        return {"by_domain": None, "by_name": None, "candidates": [], "chosen": None, "match_confidence": None}

    steps, calls = counted_steps({"resolve": nothing})
    monkeypatch.setattr(orchestrator, "get_step_functions", lambda: steps)
    asyncio.run(orchestrator.drain_queue())
    assert "company" not in calls                             # skipped, no API spend
    assert db.get_verdict(run_id)["verdict"] == "CANNOT VERIFY"


def test_credit_ceiling_holds_the_run():
    run_id = new_run()
    with db.connect() as conn:
        conn.execute("UPDATE runs SET credits_used = 100000 WHERE id = ?", (run_id,))
    asyncio.run(orchestrator.drain_queue())
    run = db.get_run(run_id)
    assert run["status"] == "held" and "credit ceiling" in run["status_reason"]


# ---------- verdict rules (pure function) ----------

def ev(i, check, flag="none", status="verified"):
    return {"id": i, "check": check, "claim": check, "flag": flag, "status": status, "missing": None}


RESOLVED = {"resolve": {"chosen": {"name": "X"}}}


def test_verdict_cleared():
    evidence = [ev(1, "director_current_role"), ev(2, "headcount_present"), ev(3, "domain_matches_record"),
                ev(4, "adverse_media")]
    assert decide(evidence, RESOLVED, [], load_config())["verdict"] == "CLEARED"


def test_verdict_front_needs_two_hard():
    evidence = [ev(1, "domain_matches_record", "hard"), ev(2, "nominee_pattern", "hard"),
                ev(3, "headcount_present")]
    assert decide(evidence, RESOLVED, [], load_config())["verdict"] == "SUSPECTED FRONT"


def test_verdict_one_hard_alone_holds():
    evidence = [ev(1, "nominee_pattern", "hard"), ev(2, "director_current_role"), ev(3, "headcount_present")]
    assert decide(evidence, RESOLVED, [], load_config())["verdict"] == "HOLD FOR REVIEW"


def test_verdict_unknown_key_source_holds():
    evidence = [ev(1, "director_current_role"), ev(2, "headcount_present"),
                ev(3, "adverse_media", status="unknown")]
    assert decide(evidence, RESOLVED, [], load_config())["verdict"] == "HOLD FOR REVIEW"
