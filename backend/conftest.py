"""Applies to every test under backend/: tests never make paid calls.

Blank keys (set before any load_dotenv(), which never overrides an existing variable) make the
Crustdata client and the LLM transport refuse to call out, so a test can't spend credits.
"""
import pytest


@pytest.fixture(autouse=True)
def no_live_api_calls(monkeypatch, tmp_path):
    for key in ("CRUSTDATA_API_KEY", "LLM_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.setenv(key, "")
    monkeypatch.setenv("VERITY_LOG_PATH", str(tmp_path / "runs.jsonl"))   # tests never write to logs/
