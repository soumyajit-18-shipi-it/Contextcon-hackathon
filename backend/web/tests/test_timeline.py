"""Offline timeline cases; B formats are mocked only in this module."""
import asyncio
import json

import pytest

from backend import db
from backend.config import load_config
from backend.engine.orchestrator import get_step_functions
from backend.web import steps, timeline, websearch


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("VERITY_DB_PATH", str(tmp_path / "timeline.db"))
    monkeypatch.setattr(timeline, "_adapter", None)
    db.init_db()
    cfg = load_config()
    run_id = db.create_run({"name": "Fixture"}, cfg["limits"])
    with db.connect() as conn:
        conn.execute("UPDATE runs SET created_at = ? WHERE id = ?", ("2026-11-22T01:00:00+00:00", run_id))
    ctx = {"run_id": run_id, "input": {"name": "Fixture"}, "config": cfg, "outputs": {}}
    observations = []

    def add(kind, value, record_date="2026-11-22", **kwargs):
        sid = db.add_source(run_id, "fixture_record", raw_response={"fixture_value": value}, record_date=record_date)
        item = timeline.Observation(kind, value, sid, ("fixture_value",), **kwargs)
        observations.append(item)
        return item

    class Adapter:
        def observations(self, context):
            return observations
    timeline.configure_timeline_adapter(Adapter())

    def site(claimed=None, footer=None, text_extra=""):
        text = f"Since {claimed}. © {footer}. {text_extra}"
        sid = db.add_source(run_id, "web", url="https://vendor.example/", raw_response=text)
        evidence = []
        for check, value, passage in (("claimed_since_year", claimed, f"Since {claimed}"),
                                      ("footer_year", footer, f"© {footer}")):
            if value is not None:
                evidence.append({"check": check, "value": value, "passage": passage,
                                 "status": "verified", "source_id": sid})
        ctx["outputs"]["site"] = {"pages": [{"source_id": sid}], "evidence": evidence}
        return sid

    def coverage(**overrides):
        values = {"coverage_from": "2025-11-22", "coverage_until": "2026-11-22",
                  "coverage_complete": True, "coverage_channels": ["jobs", "headcount", "news"],
                  "coverage_activity_count": 0}
        values.update(overrides)
        for key, value in values.items():
            add(key, value)

    async def no_network(*args):
        pytest.fail("Timeline must not make network calls")
    monkeypatch.setattr(websearch, "search", no_network)
    monkeypatch.setattr(websearch, "fetch", no_network)
    return ctx, add, site, coverage, observations


def run(setup):
    return asyncio.run(steps.step_timeline(setup[0]))


def check(result, name):
    return next(e for e in result["evidence"] if e["check"] == name)


def test_valid_ordered_timeline_distinguishes_concepts_and_precision(setup):
    _, add, site, _, _ = setup
    add("founding", "2010-06-01")
    add("incorporation", "2013-02-01")
    add("brand_launch", "2015")
    add("prior_history", "2004")
    add("director_start", "2019-01-01")
    add("director_current_as_of", "2026-11-20")
    add("first_job_posting", "2012-01-01")
    add("headcount_change", "2026-08-01")
    site(2010, 2026)
    result = run(setup)
    dates = [timeline.date_bounds(e["date"])[0] for e in result["events"]]
    assert dates == sorted(dates)
    assert next(e for e in result["events"] if e["kind"] == "brand_launch")["date"] == "2015"
    assert all(e["flag"] == "none" for e in result["evidence"])
    assert all(e["status"] == "verified" for e in result["evidence"])
    assert result["events"][-1]["kind"] == "evaluation"
    assert result["events"][-1]["source_id"] is None


def test_genuine_age_and_footer_contradictions_have_both_sources(setup):
    setup[1]("founding", "2020")
    setup[2](2010, 2012)
    result = run(setup)
    age = check(result, "claimed_age_mismatch")
    assert age["flag"] == "hard"
    assert len(age["value"]["sources"]) == 2
    assert check(result, "footer_before_founding")["flag"] == "soft"
    assert age["passage"] == "Since 2010"


def test_configured_age_gap_boundary(setup):
    setup[1]("founding", "2020")
    setup[2](2018, 2020)
    assert check(run(setup), "claimed_age_mismatch")["flag"] == "none"
    setup[0]["config"]["rules"]["claimed_age_gap_years"] = 1
    assert check(run(setup), "claimed_age_mismatch")["flag"] == "hard"


@pytest.mark.parametrize("kind", ["incorporation", "brand_launch", "prior_history"])
def test_other_history_is_not_substituted_for_founding(setup, kind):
    setup[1](kind, "2020")
    setup[2](2000, 2000)
    result = run(setup)
    assert check(result, "claimed_age_mismatch")["status"] == "cant_verify"
    assert check(result, "footer_before_founding")["flag"] == "none"


def test_recent_director_and_threshold(setup):
    setup[1]("director_start", "2026-11-01")
    setup[1]("director_current_as_of", "2026-11-20")
    assert check(run(setup), "director_recent")["flag"] == "soft"
    setup[0]["config"]["rules"]["director_recent_days"] = 21
    assert check(run(setup), "director_recent")["flag"] == "none"


@pytest.mark.parametrize("start,current", [("2026", "2026-11-20"), ("2026-11-01", "2026-01-01"),
                                           ("2026-11-01", None)])
def test_incomplete_or_stale_director_not_flagged(setup, start, current):
    setup[1]("director_start", start)
    if current:
        setup[1]("director_current_as_of", current)
    item = check(run(setup), "director_recent")
    assert item["flag"] == "none" and item["status"] in {"unknown", "cant_verify"}


def test_stale_record_cannot_confirm_recent_director(setup):
    setup[1]("director_start", "2026-11-01")
    setup[1]("director_current_as_of", "2026-11-20", record_date="2020-01-01")
    assert check(run(setup), "director_recent")["status"] == "unknown"


def test_inactivity_requires_full_current_coverage_and_explicit_zero(setup):
    setup[1]("first_job_posting", "2020-01-01")
    assert check(run(setup), "inactive_12m")["flag"] == "none"
    setup[3]()
    result = check(run(setup), "inactive_12m")
    assert result["flag"] == "soft" and result["status"] == "verified"
    assert len(result["value"]["sources"]) == 5


@pytest.mark.parametrize("changes", [
    {"coverage_complete": False}, {"coverage_activity_count": 1},
    {"coverage_channels": ["jobs"]}, {"coverage_from": "2026-05-01"},
    {"coverage_until": "2026-11-01"}, {"coverage_channels": [{}]},
])
def test_incomplete_coverage_never_proves_inactivity(setup, changes):
    setup[3](**changes)
    item = check(run(setup), "inactive_12m")
    assert item["flag"] == "none" and item["status"] == "unknown"


def test_stale_coverage_refresh_blocks_inactivity(setup):
    setup[3]()
    with db.connect() as conn:
        conn.execute("UPDATE sources SET record_date = '2025-01-01'")
    assert check(run(setup), "inactive_12m")["status"] == "unknown"


def test_recent_signal_prevents_inactivity_even_with_claimed_zero(setup):
    setup[3]()
    setup[1]("headcount_change", "2026-11-01")
    assert check(run(setup), "inactive_12m")["flag"] == "none"


def test_imprecise_activity_crossing_window_is_unknown(setup):
    setup[3]()
    setup[1]("first_job_posting", "2025")
    assert check(run(setup), "inactive_12m")["status"] == "unknown"


@pytest.mark.parametrize("relation", ["acquisition", "rebrand", "formerly_known_as"])
def test_verified_legitimate_predecessor_downgrades_age_gap(setup, relation):
    setup[1]("founding", "2020")
    setup[2](2000, 2026)
    setup[1]("predecessor_confirmed", True)
    setup[1]("predecessor_relation", relation)
    setup[1]("predecessor_since", "1995")
    item = check(run(setup), "claimed_age_mismatch")
    assert item["flag"] == "soft" and relation in item["claim"]
    assert len(item["value"]["sources"]) == 5


def test_unsupported_website_rebranding_claim_does_not_downgrade(setup):
    setup[1]("founding", "2020")
    setup[2](2000, 2026, "Formerly known as Fixture Old; acquired by Fixture New.")
    assert check(run(setup), "claimed_age_mismatch")["flag"] == "hard"


def test_website_self_attestation_is_not_independent_predecessor_proof(setup):
    setup[1]("founding", "2020")
    sid = setup[2](2000, 2026)
    raw = {"text": "Since 2000. © 2026", "confirmed": True, "relation": "rebrand", "since": "1995"}
    with db.connect() as conn:
        conn.execute("UPDATE sources SET raw_response = ? WHERE id = ?", (json.dumps(raw), sid))
    setup[4].extend([timeline.Observation(k, raw[p], sid, (p,)) for k, p in (
        ("predecessor_confirmed", "confirmed"), ("predecessor_relation", "relation"), ("predecessor_since", "since"))])
    assert check(run(setup), "claimed_age_mismatch")["flag"] == "hard"


@pytest.mark.parametrize("value", [None, "", "unknown", "01/02/2020", "2020-02-30", "2099-01-01", True, {}])
def test_malformed_or_future_founding_is_unknown(setup, value):
    setup[1]("founding", value)
    setup[2](2000, 2026)
    item = check(run(setup), "claimed_age_mismatch")
    assert item["status"] == "unknown" and item["flag"] == "none"


def test_conflicting_founding_retained_but_not_used_for_flags(setup):
    setup[1]("founding", "2000")
    setup[1]("founding", "2020")
    setup[2](1990, 2026)
    result = run(setup)
    assert check(result, "claimed_age_mismatch")["status"] == "unknown"
    assert all("conflicting" in e["label"] for e in result["events"] if e["kind"] == "founding")


def test_no_adapter_no_dates_produces_only_evaluation_and_no_flags(setup, monkeypatch):
    monkeypatch.setattr(timeline, "_adapter", None)
    result = run(setup)
    assert [e["kind"] for e in result["events"]] == ["evaluation"]
    assert all(e["flag"] == "none" for e in result["evidence"])
    assert result["integration"]["b_adapter_configured"] is True   # Lead: the live Crustdata adapter is used when none is configured


def test_matching_news_included_but_namesakes_not_vendor_activity(setup):
    ctx = setup[0]
    text = "Fixture event occurred on 2026-11-10."
    sid = db.add_source(ctx["run_id"], "web", raw_response=text, record_date="2026-11-11")
    hit = {"label": "match", "source_id": sid, "extracted": {"event_date": "2026-11-10", "quote": text}}
    ctx["outputs"]["media"] = {"media_hits": [hit]}
    assert any(e["kind"] == "news" for e in run(setup)["events"])
    hit["label"] = "namesake_cleared"
    assert not any(e["kind"] == "news" for e in run(setup)["events"])


def test_fake_passage_or_field_value_rejected(setup):
    original = setup[1]("founding", "2010")
    setup[4][:] = [timeline.Observation("founding", "2020", original.source_id, ("fixture_value",))]
    setup[2](2000, 2026)
    assert check(run(setup), "claimed_age_mismatch")["status"] == "unknown"


def test_evaluation_stable_and_no_child_rows_written(setup):
    ctx = setup[0]
    setup[1]("founding", "2010")
    setup[2](2010, 2026)
    first = run(setup)
    with db.connect() as conn:
        conn.execute("UPDATE runs SET updated_at = '2099-01-01' WHERE id = ?", (ctx["run_id"],))
    assert run(setup) == first
    assert db.get_evidence(ctx["run_id"]) == []
    assert db.get_ledger(ctx["run_id"]) == []
    db.finish_step(ctx["run_id"], "timeline", "done", first)
    assert len(db.get_evidence(ctx["run_id"])) == 4
    assert db.get_step_outputs(ctx["run_id"])["timeline"]["events"] == first["events"]
    assert dict(get_step_functions())["timeline"] is steps.step_timeline


def test_evaluation_timezone_does_not_use_host_clock(setup):
    with db.connect() as conn:
        conn.execute("UPDATE runs SET created_at = '2026-11-21T20:00:00+00:00'")
    assert run(setup)["evaluation_date"] == "2026-11-22"


def test_cross_run_source_cannot_support_founding(setup):
    item = setup[1]("founding", "2020")
    with db.connect() as conn:
        conn.execute("UPDATE sources SET run_id = 999 WHERE id = ?", (item.source_id,))
    setup[2](2000, 2026)
    assert check(run(setup), "claimed_age_mismatch")["status"] == "unknown"


def test_conflicting_website_claims_are_not_selected_for_a_hard_flag(setup):
    setup[1]("founding", "2020")
    setup[2](2000, 2026)
    sid = db.add_source(setup[0]["run_id"], "web", raw_response="Since 2020")
    setup[0]["outputs"]["site"]["evidence"].append({"check": "claimed_since_year", "value": 2020,
        "passage": "Since 2020", "source_id": sid, "status": "verified"})
    assert check(run(setup), "claimed_age_mismatch")["status"] == "unknown"


def test_adapter_failure_is_unknown(setup, monkeypatch):
    class Broken:
        def observations(self, ctx):
            raise ValueError("test")
    monkeypatch.setattr(timeline, "_adapter", Broken())
    assert all(e["status"] == "unknown" for e in run(setup)["evidence"])


def test_malformed_existing_step_output_is_unknown(setup):
    setup[0]["outputs"]["site"] = None
    assert all(e["status"] == "unknown" for e in run(setup)["evidence"])


def test_old_historical_record_is_not_automatically_discarded(setup):
    setup[1]("founding", "2010", record_date="2012-01-01")
    setup[2](2010, 2026)
    assert check(run(setup), "claimed_age_mismatch")["status"] == "verified"


def test_missing_refresh_date_prevents_inactivity_flag(setup):
    setup[3]()
    with db.connect() as conn:
        conn.execute("UPDATE sources SET record_date = NULL")
    assert check(run(setup), "inactive_12m")["status"] == "unknown"


def test_leap_day_window_uses_calendar_year(setup):
    with db.connect() as conn:
        conn.execute("UPDATE runs SET created_at = '2024-02-29T01:00:00+00:00'")
    setup[1]("headcount_change", "2023-02-28", record_date="2024-02-29")
    assert check(run(setup), "inactive_12m")["status"] == "verified"


def test_unverified_or_too_recent_predecessor_does_not_explain_gap(setup):
    setup[1]("founding", "2020")
    setup[2](2000, 2026)
    setup[1]("predecessor_confirmed", True)
    setup[1]("predecessor_relation", "acquisition")
    setup[1]("predecessor_since", "2010")
    assert check(run(setup), "claimed_age_mismatch")["flag"] == "hard"
