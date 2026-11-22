"""GET /stats tests (test-only runs)."""
import asyncio

from fastapi.testclient import TestClient

from backend import db
from backend.config import load_config
from backend.engine import orchestrator
from backend.main import app


def test_stats_measures_finished_runs_and_marks_placeholders():
    for name, credits, seconds in (("Alpha Roadlines", 4.0, 30.0), ("Beta Movers", 8.0, 50.0)):
        run_id = db.create_run({"name": name}, load_config()["limits"])
        asyncio.run(orchestrator.drain_queue())
        with db.connect() as conn:   # stand-in for what the ledger adds during a real run
            conn.execute("UPDATE runs SET credits_used = ?, elapsed_s = ? WHERE id = ?", (credits, seconds, run_id))
    db.create_run({"name": "Still Queued"}, load_config()["limits"])   # not finished: not measured

    s = TestClient(app).get("/stats").json()
    assert s["runs_measured"] == 2
    assert s["credits_per_check"] == {"avg": 6.0, "max": 8.0}
    assert s["seconds_per_check"] == {"avg": 40.0, "max": 50.0}
    assert s["verdicts"] == {"CANNOT VERIFY": 2} and s["runs_by_status"]["queued"] == 1
    assert "inr_per_credit" in s["pricing"]["placeholders"] and "placeholder" in s["note"]
