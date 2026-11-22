"""Client-records loader + output mapping tests (test-only data)."""
import json

import pytest

from backend import db
from backend.config import load_config
from backend.data import client_records
from backend.data.output_map import build_output


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("VERITY_DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    client_records._loaded.clear()


def cfg_with(path):
    cfg = load_config()
    cfg["client"] = {**cfg["client"], "records_path": str(path)}
    return cfg


def test_loads_json_and_normalises_domain(tmp_path):
    f = tmp_path / "vendors.json"
    f.write_text(json.dumps({"vendors": [{"name": "Alpha Roadlines", "website": "https://www.AlphaRoadlines.in/",
                                          "director": "A. Shah"}]}))
    assert client_records.load_client_records(cfg_with(f)) == 1
    row = db.get_client_vendors()[0]
    assert (row["name"], row["domain"], row["director"]) == ("Alpha Roadlines", "alpharoadlines.in", "A. Shah")


def test_loads_csv(tmp_path):
    f = tmp_path / "vendors.csv"
    f.write_text("name,website,director,gstin\nBeta Movers,betamovers.com,B. Rao,\n")
    assert client_records.load_client_records(cfg_with(f)) == 1
    assert db.get_client_vendors()[0]["domain"] == "betamovers.com"


def test_reloads_only_when_file_changes(tmp_path):
    f = tmp_path / "vendors.json"
    f.write_text(json.dumps([{"name": "Alpha Roadlines", "website": "alpharoadlines.in"}]))
    client_records.load_client_records(cfg_with(f))
    first_id = db.get_client_vendors()[0]["id"]
    client_records.load_client_records(cfg_with(f))
    assert db.get_client_vendors()[0]["id"] == first_id            # unchanged file: same row ids
    f.write_text(json.dumps([{"name": "Alpha Roadlines", "website": "alpharoadlines.in"},
                             {"name": "Gamma Freight", "website": "gammafreight.in"}]))
    assert client_records.load_client_records(cfg_with(f)) == 2     # changed file: reloaded


def test_missing_file_loads_nothing(tmp_path):
    assert client_records.load_client_records(cfg_with(tmp_path / "nope.json")) == 0


DATA = {
    "input": {"name": "Alpha Roadlines", "website": "alpharoadlines.in"},
    "verdict": {"verdict": "HOLD FOR REVIEW", "rule": "5_required_check_missing", "reasons": ["news screen not completed"]},
    "answers": {"who_runs_it": {"text": "A. Shah is currently Director at Alpha Roadlines [#3]", "evidence_ids": [3]},
                "cannot_verify": [{"check": "adverse_media", "missing": "search failed", "evidence_id": 9}],
                "sources": [{"evidence_id": 3, "check": "director_current_role", "source_id": 5,
                             "field_path": "x.title", "passage": None, "record_date": "2026-11-01"}]},
    "run": {"id": 4, "status": "awaiting_approval", "status_reason": "report ready"},
}


def test_build_output_paths_and_functions():
    out = build_output(DATA, load_config()["output_fields"])
    assert out["verdict"] == "HOLD FOR REVIEW" and out["vendor_name"] == "Alpha Roadlines"
    assert out["who_runs_it"] == "A. Shah is currently Director at Alpha Roadlines [#3]"   # plain text, no dict
    assert out["status_text"] == "held for approval" and out["run_id"] == 4
    assert out["cannot_verify"] == ["adverse_media: search failed"]
    assert out["sources"] == ["[#3] director_current_role: source 5, x.title, record date 2026-11-01"]


def test_new_output_field_is_one_config_line():
    fields = {**load_config()["output_fields"], "decision_rule": "verdict.rule"}
    assert build_output(DATA, fields)["decision_rule"] == "5_required_check_missing"
