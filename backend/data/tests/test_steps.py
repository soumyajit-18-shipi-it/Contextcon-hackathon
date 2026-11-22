"""Data step tests with FAKE Crustdata responses (shapes copied from real responses; values invented)."""
import asyncio

import pytest

from backend import db
from backend.config import load_config
from backend.data import crustdata, steps


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("VERITY_DB_PATH", str(tmp_path / "t.db"))
    db.init_db()


def company(cid, name, domain, conf=1.0, year=2015):
    return {"confidence_score": conf, "company_data": {"crustdata_company_id": cid, "basic_info": {
        "name": name, "primary_domain": domain, "all_domains": [domain], "year_founded": year}}}


def fake_api(monkeypatch, responses):
    """responses: {(endpoint, key): data}; key = first identifier in the payload."""
    calls = []

    async def call(run_id, endpoint, payload, method="POST"):
        key = next(iter(v[0] for k, v in payload.items() if isinstance(v, list) and k != "fields"), None)
        calls.append((endpoint, key))
        data = responses.get((endpoint, key))
        if data is None:
            return {"status": "empty", "data": [], "source_id": 1, "credits": 0, "latency_ms": 1}
        if data == "timeout":
            return {"status": "timeout", "data": None, "source_id": 1, "credits": 0, "latency_ms": 1}
        return {"status": "ok", "data": data, "source_id": 7, "credits": 0.2, "latency_ms": 1}
    monkeypatch.setattr(crustdata, "call", call)
    return calls


def ctx(inp, outputs=None):
    run_id = db.create_run(inp, load_config()["limits"])
    return {"run_id": run_id, "input": inp, "outputs": outputs or {}, "config": load_config(), "client_id": "default"}


def test_resolve_prefers_domain(monkeypatch):
    fake_api(monkeypatch, {
        ("/company/identify", "acmefreight.in"): [{"matches": [company(1, "Acme Freight", "acmefreight.in")]}],
        ("/company/identify", "Acme Freight"): [{"matches": [company(1, "Acme Freight", "acmefreight.in")]}]})
    out = asyncio.run(steps.step_resolve(ctx({"name": "Acme Freight", "website": "https://acmefreight.in"})))
    assert out["chosen"]["company_id"] == 1 and out["chosen_by"] == "domain"
    assert out["by_name"]["source_id"] == 7 and out["by_name"]["field_path"].endswith("primary_domain")


def test_resolve_vague_name_asks_a_person(monkeypatch):
    fake_api(monkeypatch, {("/company/identify", "Shree Transport"): [{"matches": [
        company(1, "Shree Transport Co", "shreetransport.in", 0.95), company(2, "Shree Transports", "shreetrans.com", 0.93)]}]})
    out = asyncio.run(steps.step_resolve(ctx({"name": "Shree Transport"})))
    assert out["chosen"] is None and len(out["candidates"]) == 2


def test_resolve_nothing_found_is_empty_not_failure(monkeypatch):
    fake_api(monkeypatch, {})
    out = asyncio.run(steps.step_resolve(ctx({"name": "Nonexistent Movers", "website": "nonexistentmovers.in"})))
    assert out["chosen"] is None and out["candidates"] == []


def test_resolve_timeout_raises_so_engine_records_unknown(monkeypatch):
    fake_api(monkeypatch, {("/company/identify", "Acme"): "timeout"})
    with pytest.raises(steps.SourceUnavailable):
        asyncio.run(steps.step_resolve(ctx({"name": "Acme"})))


def person(current):
    return [{"matches": [{"person_data": {"basic_profile": {"name": "Ravi Kumar", "location": {"city": "Pune"}},
                                          "experience": {"employment_details": {"current": current}}}}]}]


COMPANY_OUT = {"company_id": 1, "name": "Acme Freight", "primary_domain": "acmefreight.in", "year_founded": 2015,
               "source_id": 3, "leaders": [{"name": "Ravi Kumar", "title": "Founder & CEO", "group": "founders",
                                            "person_id": 9, "profile_url": "https://www.linkedin.com/in/ravi",
                                            "updated_at": "2026-11-01T00:00:00Z", "field_path": "x"}]}


def test_director_confirmed_and_minimal_personal_data(monkeypatch):
    fake_api(monkeypatch, {("/person/enrich", "https://www.linkedin.com/in/ravi"): person(
        [{"name": "Acme Freight", "title": "Founder & CEO", "start_date": "2015-04-01T00:00:00+00:00", "crustdata_company_id": 1}])})
    out = asyncio.run(steps.step_director(ctx({"name": "Acme Freight"}, {"company": COMPANY_OUT})))
    role = next(e for e in out["evidence"] if e["check"] == "director_current_role")
    assert role["flag"] == "none" and role["status"] == "verified" and role["source_id"] == 7
    assert set(out["profiles"][0]) == {"name", "title", "employer", "start_date", "city", "current_roles", "source_id", "person_id"}
    assert {p["field"] for p in out["personal_data"]} <= {"name", "title", "employer", "start_date", "city", "current_roles"}


def test_named_director_working_elsewhere_is_hard(monkeypatch):
    fake_api(monkeypatch, {("/person/enrich", "https://www.linkedin.com/in/ravi"): person(
        [{"name": "Other Co", "title": "Manager", "start_date": "2020-01-01T00:00:00+00:00", "crustdata_company_id": 55}])})
    out = asyncio.run(steps.step_director(ctx({"name": "Acme Freight", "director": "Ravi Kumar"}, {"company": COMPANY_OUT})))
    assert next(e for e in out["evidence"] if e["check"] == "director_current_role")["flag"] == "hard"


def test_many_current_roles_is_nominee_pattern(monkeypatch):
    roles = [{"name": f"Co {i}", "title": "Director", "crustdata_company_id": 100 + i} for i in range(6)]
    roles.append({"name": "Acme Freight", "title": "Director", "start_date": "2016-01-01", "crustdata_company_id": 1})
    fake_api(monkeypatch, {("/person/enrich", "https://www.linkedin.com/in/ravi"): person(roles)})
    out = asyncio.run(steps.step_director(ctx({"name": "Acme Freight"}, {"company": COMPANY_OUT})))
    assert next(e for e in out["evidence"] if e["check"] == "nominee_pattern")["flag"] == "hard"


def test_only_fuzzy_name_hits_is_not_found(monkeypatch):
    """A made-up name gets fuzzy hits (0.6). They are kept as weak_matches, but nothing is offered as the company."""
    fake_api(monkeypatch, {("/company/identify", "Blue Banyan Haulage"): [{"matches": [
        company(1, "Blue Banyan Yoga", "bluebanyanyoga.com", 0.6), company(2, "Blue Banyan Books", "bluebanyanbooks.com", 0.6)]}]})
    out = asyncio.run(steps.step_resolve(ctx({"name": "Blue Banyan Haulage"})))
    assert out["chosen"] is None and out["candidates"] == [] and len(out["weak_matches"]) == 2


def test_advisor_and_member_roles_are_not_directorships(monkeypatch):
    roles = [{"name": f"Co {i}", "title": t, "crustdata_company_id": 100 + i}
             for i, t in enumerate(["Advisor", "Investor", "Association Member", "Content Creator", "Mentor"])]
    roles.append({"name": "Acme Freight", "title": "Founder & CEO", "start_date": "2016-01-01", "crustdata_company_id": 1})
    fake_api(monkeypatch, {("/person/enrich", "https://www.linkedin.com/in/ravi"): person(roles)})
    out = asyncio.run(steps.step_director(ctx({"name": "Acme Freight"}, {"company": COMPANY_OUT})))
    assert next(e for e in out["evidence"] if e["check"] == "nominee_pattern")["flag"] == "none"


def test_founders_office_is_not_a_leader():
    assert not steps.is_leader_title("Founder's Office") and not steps.is_leader_title("Assistant to the Director")
    assert steps.is_leader_title("Co-Founder & CEO") and steps.is_leader_title("Managing Director")
