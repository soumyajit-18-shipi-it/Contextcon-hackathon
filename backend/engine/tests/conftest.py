"""Shared test setup: every test gets its own empty SQLite database. Mock data lives only in tests."""
import pytest

from backend import db


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("VERITY_DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
