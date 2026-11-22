"""Synthetic sources only; no production provider response formats asserted."""
import asyncio

import pytest

from backend import db
from backend.config import load_config
from backend.engine.orchestrator import get_step_functions
from backend.web import copied_site as copy, steps, websearch
from backend.web.textutil import distinctive_sentences


S1 = "Our refrigerated wagons record individual pallet temperatures every ninety seconds throughout overnight mountain crossings."
S2 = "Each coastal depot maintains numbered ceramic seals and photographs every container before dispatching inland deliveries."
S3 = "The dispatch office reconciles river crossing permits against vehicle manifests before assigning a scheduled departure."
S4 = "Our railway terminals use calibrated optical scanners to measure unusual cargo dimensions before loading each wagon."


class Budget:
    def __init__(self, remaining):
        self.remaining = remaining
        self.reserved = 0

    async def reserve(self, run_id):
        if self.remaining <= 0:
            return False
        self.remaining -= 1
        self.reserved += 1
        return True


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("VERITY_DB_PATH", str(tmp_path / "copy.db"))
    monkeypatch.setattr(copy, "_adapter", None)
    monkeypatch.setattr(copy, "_budget", None)
    db.init_db()
    cfg = load_config()
    inp = {"name": "Fixture Carrier", "website": "https://vendor.example/"}
    ctx = {"run_id": db.create_run(inp, cfg["limits"]), "input": inp, "config": cfg, "outputs": {}}
    state = {"urls": [], "texts": {}, "calls": [], "search_status": "empty", "fetch_status": "ok",
             "owners": {}, "unknown_business": False}

    def site(text):
        source_id = db.add_source(ctx["run_id"], "fixture", url=inp["website"],
                                  raw_response={"fixture_text": text})
        ctx["outputs"]["site"] = {"pages": [{"status": "ok", "url": inp["website"],
                                               "source_id": source_id, "text": text}]}
    site(S1)

    class Adapter:
        def search_urls(self, source):
            return source["raw_response"]["fixture_urls"]

        def page_text(self, source):
            return source["raw_response"]["fixture_text"]

        def unrelated_business(self, ctx, source):
            if state["unknown_business"]:
                return None
            owner = state["owners"].get(source["url"], source["url"])
            return copy.UnrelatedBusiness(owner, "This is an independently operated fixture business.")

    async def search(run_id, query):
        state["calls"].append(("search", query))
        urls = state["urls"].get(query, []) if isinstance(state["urls"], dict) else state["urls"]
        sid = db.add_source(run_id, "fixture", request={"query": query}, raw_response={
            "fixture_urls": urls, "snippet": S1 + " " + S2})
        return {"status": state["search_status"], "source_id": sid, "data": {"snippet": S1}}

    async def fetch(run_id, url):
        state["calls"].append(("fetch", url))
        if state.get("raise_fetch"):
            raise TimeoutError()
        sid = db.add_source(state.get("source_run", run_id), "fixture", url=state.get("source_url", url),
                            raw_response={"fixture_text": state["texts"].get(url, "Unrelated page text.") +
                                          " This is an independently operated fixture business."},
                            record_date="2026-05-03")
        return {"status": state["fetch_status"], "source_id": sid, "data": {"snippet": S1}}

    monkeypatch.setattr(websearch, "search", search)
    monkeypatch.setattr(websearch, "fetch", fetch)
    budget = Budget(8)
    adapter = Adapter()
    copy.configure_copied_site(adapter, budget)
    return ctx, state, site, budget, adapter


def run(setup):
    return asyncio.run(steps.step_copied_site(setup[0]))


def found(setup, urls, texts):
    setup[1].update(urls=urls, texts=texts, search_status="ok")


def test_honest_site_empty_search_is_scoped_not_proof_of_originality(setup):
    result = run(setup)
    assert result["coverage"]["complete"]
    assert result["evidence"][0]["flag"] == "none"
    assert "does not prove originality" in result["evidence"][0]["claim"]
    assert result["queries"] == ['"' + S1 + '"']


def test_one_verified_overlap_soft_with_both_sources_and_exact_passage(setup):
    ctx, state, _, _, _ = setup
    found(setup, ["https://other.example/"], {"https://other.example/": S1})
    result = run(setup)
    evidence = result["evidence"][0]
    assert evidence["flag"] == "soft" and evidence["status"] == "verified"
    assert evidence["passage"] == S1
    assert evidence["url"] == "https://other.example/"
    assert evidence["retrieved_at"] and evidence["record_date"] == "2026-05-03"
    assert "#:~:text=" in evidence["passage_url"]
    value = evidence["value"]
    assert S1 in db.get_source(value["vendor_source_id"])["raw_response"]["fixture_text"]
    assert S1 in db.get_source(evidence["source_id"])["raw_response"]["fixture_text"]
    assert "Text also appears on" in evidence["claim"]
    assert db.get_evidence(ctx["run_id"]) == []
    db.finish_step(ctx["run_id"], "copied_site", "done", result)
    assert len(db.get_evidence(ctx["run_id"])) == 1


def test_two_independent_sentences_and_businesses_hard(setup):
    setup[2](S1 + "\n" + S2)
    a, b = "https://first.example/", "https://second.example/"
    found(setup, {'"' + S1 + '"': [a], '"' + S2 + '"': [b]}, {a: S1, b: S2})
    result = run(setup)
    assert result["coverage"]["complete"]
    assert len(result["overlaps"]) == 2
    assert all(e["flag"] == "hard" for e in result["evidence"])


def test_same_sentence_on_two_sites_is_not_two_independent_overlaps(setup):
    a, b = "https://first.example/", "https://second.example/"
    found(setup, [a, b], {a: S1, b: S1})
    assert all(e["flag"] == "soft" for e in run(setup)["evidence"])


def test_same_owner_across_domains_cannot_escalate(setup):
    setup[2](S1 + "\n" + S2)
    a, b = "https://first.example/", "https://second.example/"
    found(setup, {'"' + S1 + '"': [a], '"' + S2 + '"': [b]}, {a: S1, b: S2})
    setup[1]["owners"] = {a: "one-owner", b: "one-owner"}
    assert all(e["flag"] == "soft" for e in run(setup)["evidence"])


@pytest.mark.parametrize("marker", ["Lorem ipsum", "Your Company Name"])
def test_explicit_template_requires_no_network_budget(setup, marker):
    setup[2](marker)
    setup[3].remaining = 0
    result = run(setup)
    assert result["evidence"][0]["flag"] == "hard"
    assert result["evidence"][0]["passage"] == marker
    assert setup[1]["calls"] == []


@pytest.mark.parametrize("url", [
    "https://vendor.example/", "https://www.vendor.example/about", "https://blog.vendor.example/",
    "https://linkedin.com/", "https://in.linkedin.com/", "https://crunchbase.com/",
    "https://indiamart.com/", "https://justdial.com/", "https://tracxn.com/", "https://zaubacorp.com/",
    "https://tofler.in/", "https://glassdoor.co.in/", "https://ambitionbox.com/",
    "https://facebook.com/", "https://instagram.com/", "https://x.com/", "https://youtube.com/",
])
def test_own_domain_and_directories_never_fetched(setup, url):
    found(setup, [url], {url: S1})
    result = run(setup)
    assert result["overlaps"] == []
    assert [kind for kind, _ in setup[1]["calls"]] == ["search"]


def test_domain_exclusions_use_boundaries():
    assert not copy.excluded_url("https://linkedin.com.other.example/", {"vendor.example"})
    assert not copy.excluded_url("https://notvendor.example/", {"vendor.example"})


@pytest.mark.parametrize("status", ["timeout", "error", "rate_limited"])
def test_failed_search_is_unknown(setup, status):
    setup[1]["search_status"] = status
    result = run(setup)
    assert result["evidence"][0]["status"] == "unknown"
    assert not result["coverage"]["complete"]


def test_zero_remaining_shared_budget_makes_no_calls(setup):
    setup[3].remaining = 0
    result = run(setup)
    assert setup[1]["calls"] == []
    assert result["coverage"]["web_calls"] == 0
    assert "budget" in result["evidence"][0]["missing"]


def test_remaining_budget_consumed_by_search_does_not_allow_fetch(setup):
    found(setup, ["https://other.example/"], {"https://other.example/": S1})
    setup[3].remaining = 1
    result = run(setup)
    assert len(setup[1]["calls"]) == setup[3].reserved == 1
    assert result["overlaps"] == []
    assert result["evidence"][0]["status"] == "unknown"


def test_matching_snippet_without_page_overlap_never_flags(setup):
    found(setup, ["https://other.example/"], {"https://other.example/": "An entirely different sentence."})
    result = run(setup)
    assert result["overlaps"] == []
    assert result["evidence"][0]["flag"] == "none"


@pytest.mark.parametrize("change", [
    {"fetch_status": "timeout"}, {"raise_fetch": True}, {"source_run": 999},
    {"source_url": "https://vendor.example/"}, {"unknown_business": True},
])
def test_inaccessible_or_unrelated_status_unverified_is_unknown(setup, change):
    found(setup, ["https://other.example/"], {"https://other.example/": S1})
    setup[1].update(change)
    result = run(setup)
    assert result["overlaps"] == []
    assert result["evidence"][0]["status"] == "unknown"


def test_site_output_must_match_persisted_text(setup):
    setup[0]["outputs"]["site"]["pages"][0]["text"] = "Your Company Name"
    result = run(setup)
    assert all(e["flag"] == "none" and e["status"] == "unknown" for e in result["evidence"])


def test_select_at_most_three_distinctive_sentences(setup):
    setup[2]("\n".join([S1, S2, S3, S4]))
    assert run(setup)["sentences"] == [S1, S2, S3]
    assert len(setup[1]["calls"]) == 3


def test_filter_generic_marketing_and_word_bounds():
    generic = "We are your trusted partner providing innovative solutions and customer satisfaction around the world."
    assert distinctive_sentences(generic) == []
    assert distinctive_sentences("© Copyright " + S1) == []
    assert distinctive_sentences("Our cookies improve your experience while we process your personal data for marketing purposes.") == []
    assert distinctive_sentences("short sentence.") == []
    assert distinctive_sentences(" ".join(["word"] * 31)) == []
    assert distinctive_sentences(S1) == [S1]


def test_reuse_fetched_page_between_queries(setup):
    setup[2](S1 + "\n" + S2)
    found(setup, ["https://other.example/"], {"https://other.example/": S1 + "\n" + S2})
    result = run(setup)
    assert len(result["overlaps"]) == 2
    assert len(setup[1]["calls"]) == 3  # two searches, one fetch
    assert all(e["flag"] == "soft" for e in result["evidence"])


def test_missing_adapter_and_budget_are_explicit(setup, monkeypatch):
    monkeypatch.setattr(copy, "_adapter", None)
    assert run(setup)["evidence"][0]["status"] == "unknown"
    monkeypatch.setattr(copy, "_adapter", setup[4])
    monkeypatch.setattr(copy, "_budget", None)
    assert run(setup)["evidence"][0]["status"] == "unknown"
    assert setup[1]["calls"] == []


def test_engine_auto_discovers_copied_step():
    assert dict(get_step_functions())["copied_site"] is steps.step_copied_site


def test_credits_exhausted_returns_hold(setup):
    setup[1]["search_status"] = "no_credits"
    assert "hold" in run(setup)


def test_partial_overlap_preserved_with_unknown_remaining_search(setup):
    setup[2](S1 + "\n" + S2)
    found(setup, ["https://other.example/"], {"https://other.example/": S1})
    setup[3].remaining = 2
    result = run(setup)
    assert len(result["overlaps"]) == 1
    assert any(e["status"] == "verified" and e["flag"] == "soft" for e in result["evidence"])
    assert any(e["status"] == "unknown" for e in result["evidence"])
    assert not result["coverage"]["complete"]


def test_ungrounded_business_assessment_cannot_flag(setup, monkeypatch):
    found(setup, ["https://other.example/"], {"https://other.example/": S1})
    monkeypatch.setattr(setup[4], "unrelated_business", lambda ctx, source:
                        copy.UnrelatedBusiness("other-owner", "Invented supporting passage"))
    result = run(setup)
    assert result["overlaps"] == []
    assert result["evidence"][0]["status"] == "unknown"


def test_missing_site_pages_is_unknown(setup):
    setup[0]["outputs"] = {}
    result = run(setup)
    assert result["evidence"][0]["status"] == "unknown"
    assert setup[1]["calls"] == []


def test_fetch_credit_exhaustion_holds(setup):
    found(setup, ["https://other.example/"], {})
    setup[1]["fetch_status"] = "no_credits"
    assert "hold" in run(setup)
