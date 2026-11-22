"""Look-alike tests. Every company here is invented for the test ("Swiftora", "Kaveri Movers", ...)."""
import asyncio

from backend.config import load_config
from backend.engine.lookalike import assess, step_lookalike
from backend.engine.names import brand_key, domain_label

MAX_EDIT = load_config()["rules"]["lookalike_max_edit"]

SWIFTORA = {"name": "Swiftora Logistics", "domain": "swiftora.com", "all_domains": ["swiftora.com"],
            "company_id": 101, "source_id": 7, "field_path": "basic_info.primary_domain", "record_date": "2026-11-01"}


def test_normalisation():
    assert domain_label("https://www.abc-logistics.co.in/about") == "abc-logistics"
    assert brand_key("swift0ra-logistics-india") == "swiftora"
    assert brand_key("rnaersk") == "maersk"


def test_honest_in_com_pair_listed_on_record_passes():
    acme = {"name": "Acme Carriers", "domain": "acmecarriers.com",
            "all_domains": ["acmecarriers.com", "acmecarriers.in"], "company_id": 5, "source_id": 1}
    assert assess("acmecarriers.in", acme, None, MAX_EDIT)["result"] == "pass"


def test_honest_in_com_pair_same_company_by_domain_passes():
    acme_by_name = {"name": "Acme Carriers", "domain": "acmecarriers.com", "company_id": 5, "source_id": 1}
    acme_by_domain = {"name": "Acme Carriers", "domain": "acmecarriers.com", "company_id": 5, "source_id": 2}
    assert assess("acmecarriers.in", acme_by_name, acme_by_domain, MAX_EDIT)["result"] == "pass"


def test_brand_lookalike_with_digit_swap_and_filler_is_flagged():
    finding = assess("swift0ra-logistics.in", SWIFTORA, None, MAX_EDIT)
    assert finding["result"] == "impersonation" and finding["official_domain"] == "swiftora.com"


def test_one_letter_typo_is_flagged():
    assert assess("swiftorra.com", SWIFTORA, None, MAX_EDIT)["result"] == "impersonation"


def test_name_and_domain_pointing_to_unrelated_companies_is_soft():
    kaveri = {"name": "Kaveri Movers", "domain": "kaverimovers.in", "company_id": 202, "source_id": 9}
    assert assess("kaverimovers.in", SWIFTORA, kaveri, MAX_EDIT)["result"] == "mismatch"


def test_no_website_is_nothing_to_compare():
    assert assess(None, SWIFTORA, None, MAX_EDIT)["result"] == "nothing_to_compare"


def test_step_emits_hard_evidence_with_source():
    ctx = {"run_id": 1, "input": {"name": "Swiftora Logistics", "website": "swift0ra-logistics.in"},
           "config": load_config(),
           "outputs": {"resolve": {"chosen": {"name": "Swiftora Logistics"}, "by_name": SWIFTORA, "by_domain": None}}}
    e = asyncio.run(step_lookalike(ctx))["evidence"][0]
    assert (e["check"], e["flag"], e["status"]) == ("lookalike_domain", "hard", "verified")
    assert e["source_id"] == 7 and e["field_path"] == "basic_info.primary_domain" and e["record_date"]
