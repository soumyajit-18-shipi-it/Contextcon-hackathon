"""Event log tests: every run leaves a structured trail (table + JSON lines file)."""
import asyncio
import json
import os

import pytest
from fastapi.testclient import TestClient

from backend import db
from backend.config import load_config
from backend.engine import orchestrator
from backend.main import app


class Crash(BaseException):
    pass


def kinds(run_id):
    return [e["event"] for e in db.get_events(run_id)]


def test_full_run_logs_steps_checkpoints_and_status():
    client = TestClient(app)
    run_id = client.post("/runs", json={"name": "Alpha Roadlines", "website": "alpharoadlines.in"}).json()["id"]
    asyncio.run(orchestrator.drain_queue())
    events = db.get_events(run_id)
    assert events[0]["event"] == "run_created"
    assert kinds(run_id).count("step_start") == len(orchestrator.STEPS)
    assert all("duration_ms" in e["detail"] for e in events if e["event"] == "step_end")
    assert events[-1]["event"] == "status" and events[-1]["detail"]["status"] == "awaiting_approval"

    client.post(f"/runs/{run_id}/approve", json={"decision": "reject", "reason": "test reason", "user": "lead"})
    client.post(f"/runs/{run_id}/approve", json={"decision": "clear", "reason": "again", "user": "lead"})
    assert "approval" in kinds(run_id) and "approval_refused" in kinds(run_id)

    api_events = client.get(f"/runs/{run_id}/events").json()
    assert len(api_events) == len(events) + 2        # + the approval, + the refused second attempt
    lines = [json.loads(l) for l in open(os.environ["VERITY_LOG_PATH"], encoding="utf-8")]
    assert {l["event"] for l in lines} >= {"run_created", "step_start", "step_end", "checkpoint", "approval"}


def test_retry_and_resume_are_logged(monkeypatch):
    run_id = db.create_run({"name": "Beta Movers"}, load_config()["limits"])
    state = {"media_calls": 0}
    real = dict(orchestrator.get_step_functions())

    async def flaky_media(ctx):
        state["media_calls"] += 1
        if state["media_calls"] == 1:
            raise ValueError("source down")
        if state["media_calls"] == 2:
            raise Crash()
        return await real["media"](ctx)

    steps = [(n, flaky_media if n == "media" else f) for n, f in real.items()]
    monkeypatch.setattr(orchestrator, "get_step_functions", lambda: steps)
    with pytest.raises(Crash):
        asyncio.run(orchestrator.drain_queue())
    db.requeue_interrupted_runs()
    asyncio.run(orchestrator.drain_queue())

    errors = [e for e in db.get_events(run_id) if e["event"] == "step_error"]
    assert errors[0]["step"] == "media" and errors[0]["detail"]["will_retry"] is True
    assert "resumed_after_restart" in kinds(run_id) and "run_resumed" in kinds(run_id)


def test_ceiling_is_logged():
    run_id = db.create_run({"name": "Gamma Freight"}, load_config()["limits"])
    with db.connect() as conn:
        conn.execute("UPDATE runs SET credits_used = 100000 WHERE id = ?", (run_id,))
    asyncio.run(orchestrator.drain_queue())
    assert "ceiling" in kinds(run_id)
