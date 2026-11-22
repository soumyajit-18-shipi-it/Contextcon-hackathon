"""Timeline adapter tests: FAKE sources stored in real Crustdata shapes (no paid calls)."""
import asyncio
from datetime import date, timedelta

import pytest

from backend import db
from backend.config import load_config
from backend.web import steps


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("VERITY_DB_PATH", str(tmp_path / "t.db"))
    db.init_db()


def make_ctx(founded=2025, claimed=2005, description="Road freight carrier.", director_start="2025-03-01",
             job_day=None, headcount=(10, 12)):
    inp = {"name": "Fixture Freight", "website": "fixturefreight.in", "claimed_year": claimed}
    run_id = db.create_run(inp, load_config()["limits"])
    today = date.today()
    company_raw = [{"matches": [{"company_data": {
        "crustdata_company_id": 1,
        "basic_info": {"name": "Fixture Freight", "year_founded": founded, "description": description},
        "headcount": {"timeseries": [{"date": (today - timedelta(days=60)).isoformat(), "employee_count": headcount[0]},
                                     {"date": (today - timedelta(days=30)).isoformat(), "employee_count": headcount[1]}]},
        "people": {"founders": [{"crustdata_person_id": 9, "updated_at": (today - timedelta(days=5)).isoformat() + "T00:00:00Z"}]},
    }}]}]
    csid = db.add_source(run_id, "crustdata", endpoint="/company/enrich", raw_response=company_raw, status="ok",
                         record_date=(today - timedelta(days=1)).isoformat())
    person_raw = [{"matches": [{"person_data": {"experience": {"employment_details": {"current": [
        {"name": "Fixture Freight", "crustdata_company_id": 1, "start_date": f"{director_start}T00:00:00+00:00"}]}}}}]}]
    psid = db.add_source(run_id, "crustdata", endpoint="/person/enrich", raw_response=person_raw, status="ok")
    if job_day:
        db.add_source(run_id, "crustdata", endpoint="/job/search", status="ok",
                      raw_response={"job_listings": [{"metadata": {"date_added": f"{job_day}T10:00:00"}}], "total_count": 1})
    outputs = {
        "company": {"company_id": 1, "source_id": csid, "leaders": [{"person_id": 9, "updated_at": company_raw[0]["matches"][0]
                    ["company_data"]["people"]["founders"][0]["updated_at"]}]},
        "director": {"profiles": [{"name": "R. Kumar", "start_date": f"{director_start}T00:00:00+00:00", "source_id": psid,
                                   "person_id": 9}]},
        "site": {"pages": [], "evidence": []},
    }
    return {"run_id": run_id, "input": inp, "outputs": outputs, "config": load_config(), "client_id": "default"}


def evidence(out, check):
    return next(e for e in out["evidence"] if e["check"] == check)


def test_old_claimed_year_vs_recent_founding_is_hard():
    out = asyncio.run(steps.step_timeline(make_ctx(founded=2025, claimed=2005)))
    e = evidence(out, "claimed_age_mismatch")
    assert (e["status"], e["flag"]) == ("verified", "hard") and e["value"]["details"]["gap_years"] == 20
    assert e["source_id"]                      # cites the stored source of the claim / founding


def test_formerly_known_as_downgrades_to_soft():
    ctx = make_ctx(founded=2025, claimed=2005, description="Fixture Freight, formerly known as Old Road Lines, moves cargo.")
    e = evidence(asyncio.run(steps.step_timeline(ctx)), "claimed_age_mismatch")
    assert e["flag"] == "soft" and "formerly known as" in e["claim"]


def test_matching_years_no_flag():
    e = evidence(asyncio.run(steps.step_timeline(make_ctx(founded=2011, claimed=2011))), "claimed_age_mismatch")
    assert (e["status"], e["flag"]) == ("verified", "none")


def test_recent_director_is_soft_and_old_is_none():
    recent = (date.today() - timedelta(days=20)).isoformat()
    assert evidence(asyncio.run(steps.step_timeline(make_ctx(director_start=recent))), "director_recent")["flag"] == "soft"
    assert evidence(asyncio.run(steps.step_timeline(make_ctx(director_start="2015-01-01"))), "director_recent")["flag"] == "none"


def test_recent_activity_feeds_inactive_check():
    out = asyncio.run(steps.step_timeline(make_ctx(job_day=(date.today() - timedelta(days=3)).isoformat())))
    e = evidence(out, "inactive_12m")
    assert (e["status"], e["flag"]) == ("verified", "none")
    assert any(ev["kind"] == "latest_job_posting" for ev in out["events"])


def test_no_claim_is_cant_verify_not_a_flag():
    e = evidence(asyncio.run(steps.step_timeline(make_ctx(claimed=None))), "claimed_age_mismatch")
    assert e["status"] in ("cant_verify", "unknown") and e["flag"] == "none"
