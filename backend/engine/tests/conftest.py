"""Shared test setup: every test gets its own empty SQLite database. Mock data lives only in tests."""
import pytest

from backend import db
from backend.engine import orchestrator, stubs


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("VERITY_DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


@pytest.fixture(autouse=True)
def offline_data_and_web_steps(monkeypatch):
    """Engine tests exercise the engine, so B's and C's steps run as the offline stubs here.
    (Their real steps have their own tests with fake API responses.)"""
    def stubbed():
        return [(name, getattr(stubs, f"step_{name}") if module.startswith(("backend.data", "backend.web"))
                 else stubs.owned_or_stub(module, f"step_{name}"))
                for name, module in orchestrator.STEPS]
    monkeypatch.setattr(orchestrator, "get_step_functions", stubbed)
