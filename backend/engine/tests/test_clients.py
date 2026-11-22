"""Per-client config tests. A temporary config with a made-up second client; nothing real."""
import asyncio
import json

import pytest
import yaml
from fastapi.testclient import TestClient

from backend import cli, config, db
from backend.engine import orchestrator
from backend.engine.verdict import decide
from backend.main import app


@pytest.fixture
def two_clients(tmp_path, monkeypatch):
    cfg = yaml.safe_load(config.CONFIG_PATH.read_text(encoding="utf-8"))
    cfg["clients"]["strict_bank"] = {
        "name": "Strict Bank", "records_path": str(tmp_path / "bank.csv"),
        "record_fields": {"name": "vendor", "domain": "url", "director": "md", "gstin": "gstin"},
        "limits": {"credit_limit": 50},
        "verdict_rules": {"required_for_clear": ["adverse_media", "copied_site"]},
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_PATH", path)


def test_client_overrides_only_what_it_sets(two_clients):
    base, bank = config.load_config(), config.load_config("strict_bank")
    assert bank["limits"]["credit_limit"] == 50 and bank["limits"]["time_limit_s"] == base["limits"]["time_limit_s"]
    assert bank["verdict_rules"]["required_for_clear"] == ["adverse_media", "copied_site"]
    assert bank["verdict_rules"]["front_min_hard"] == base["verdict_rules"]["front_min_hard"]
    assert bank["client"]["id"] == "strict_bank" and bank["client"]["record_fields"]["name"] == "vendor"
    assert base["client"]["id"] == "default"


def test_same_evidence_different_client_rules(two_clients):
    evidence = [{"id": i, "check": c, "claim": c, "flag": "none", "status": "verified", "missing": None}
                for i, c in enumerate(["director_current_role", "headcount_present", "adverse_media"])]
    outputs = {"resolve": {"chosen": {"name": "X"}}}
    assert decide(evidence, outputs, [], config.load_config())["verdict"] == "CLEARED"
    assert decide(evidence, outputs, [], config.load_config("strict_bank"))["verdict"] == "HOLD FOR REVIEW"


def test_run_uses_its_clients_limits(two_clients):
    client = TestClient(app)
    run_id = client.post("/runs", json={"name": "Alpha Roadlines", "client_id": "strict_bank"}).json()["id"]
    asyncio.run(orchestrator.drain_queue())
    run = db.get_run(run_id)
    assert run["client_id"] == "strict_bank" and run["credit_limit"] == 50
    assert "client_id" not in run["input"]


def test_unknown_client_is_rejected(two_clients):
    r = TestClient(app).post("/runs", json={"name": "Alpha Roadlines", "client_id": "nobody"})
    assert r.status_code == 400 and "unknown client" in r.text


def test_cli_keeps_clients_apart(two_clients, tmp_path):
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps({"cases": [{"id": "c1", "vendor_name": "Alpha Roadlines"}]}), encoding="utf-8")
    cli.run_cli(str(cases), str(tmp_path / "a.json"))
    cli.run_cli(str(cases), str(tmp_path / "b.json"), client_id="strict_bank")
    with db.connect() as conn:
        rows = conn.execute("SELECT client_id FROM runs ORDER BY id").fetchall()
    assert [r["client_id"] for r in rows] == ["default", "strict_bank"]   # same case, two clients, two runs
