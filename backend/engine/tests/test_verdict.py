"""Verdict rule tests on hand-made evidence (test-only data)."""
from backend.config import load_config
from backend.engine.verdict import decide

CFG = load_config()
RESOLVED = {"resolve": {"chosen": {"name": "X"}}}


def ev(i, check, flag="none", status="verified"):
    return {"id": i, "check": check, "claim": check, "flag": flag, "status": status, "missing": "x"}


def good_facts(start=100):
    """A resolved, active company with a confirmed director and a completed news screen."""
    return [ev(start, "director_current_role"), ev(start + 1, "headcount_present"),
            ev(start + 2, "domain_matches_record"), ev(start + 3, "adverse_media")]


def test_cleared_needs_the_news_screen():
    without_media = [e for e in good_facts() if e["check"] != "adverse_media"]
    v = decide(without_media, RESOLVED, [], CFG)
    assert (v["verdict"], v["rule"]) == ("HOLD FOR REVIEW", "5_required_check_missing")
    assert v["reasons"] == ["news screen not completed"]


def test_news_screen_not_verified_is_still_hold():
    evidence = [e for e in good_facts() if e["check"] != "adverse_media"] + [ev(9, "adverse_media", status="cant_verify")]
    assert decide(evidence, RESOLVED, [], CFG)["reasons"] == ["news screen not completed"]


def test_required_for_clear_is_config():
    cfg = {**CFG, "verdict_rules": {**CFG["verdict_rules"], "required_for_clear": ["adverse_media", "copied_site"]}}
    v = decide(good_facts(), RESOLVED, [], cfg)
    assert v["verdict"] == "HOLD FOR REVIEW" and v["reasons"] == ["website originality check not completed"]


def test_one_hard_plus_two_soft_is_front():
    evidence = good_facts() + [ev(1, "lookalike_domain", "hard"), ev(2, "hiring_activity", "soft"),
                               ev(3, "director_recent", "soft")]
    v = decide(evidence, RESOLVED, [], CFG)
    assert v["verdict"] == "SUSPECTED FRONT" and v["rule"] == "3_hard_flags"
    assert set(v["evidence_ids"]) == {1, 2, 3}             # the exact evidence behind the verdict


def test_same_check_twice_is_not_a_front():
    evidence = good_facts() + [ev(1, "copied_site", "hard"), ev(2, "copied_site", "hard")]
    assert decide(evidence, RESOLVED, [], CFG)["verdict"] == "HOLD FOR REVIEW"


def test_duplicate_is_hold_never_front():
    evidence = good_facts() + [ev(1, "duplicate_exact", "hard"), ev(2, "nominee_pattern", "hard")]
    outputs = {**RESOLVED, "duplicate": {"duplicate_of": "client vendor #1 X", "matches": [{}]}}
    v = decide(evidence, outputs, [], CFG)
    assert v["verdict"] == "HOLD FOR REVIEW"
    assert any("duplicate" in r for r in v["reasons"])


def test_exact_duplicate_beats_cannot_verify():
    """Nothing else verifies (core checks cant_verify, not even resolved), but the domain is a client vendor's."""
    evidence = [ev(1, "duplicate_exact", "hard"), ev(2, "director_current_role", status="cant_verify"),
                ev(3, "domain_matches_record", status="cant_verify")]
    outputs = {"resolve": {"chosen": None, "candidates": []},
               "duplicate": {"duplicate_of": "client vendor #4 Shree Ganesh Roadways", "matches": [{}]}}
    v = decide(evidence, outputs, [], CFG)
    assert (v["verdict"], v["rule"]) == ("HOLD FOR REVIEW", "1_exact_duplicate")
    assert v["evidence_ids"] == [1] and "client vendor #4" in v["reasons"][0]


def test_unverified_duplicate_claim_does_not_trigger_rule_1():
    evidence = [ev(1, "duplicate_exact", "hard", status="cant_verify")]
    assert decide(evidence, {"resolve": {"chosen": None}}, [], CFG)["verdict"] == "CANNOT VERIFY"


def test_duplicate_alone_blocks_cleared():
    outputs = {**RESOLVED, "duplicate": {"duplicate_of": "run #1", "matches": [{}]}}
    assert decide(good_facts(), outputs, [], CFG)["verdict"] == "HOLD FOR REVIEW"


def test_unresolved_media_hit_holds():
    media = [{"label": "unresolved"}]
    assert decide(good_facts(), RESOLVED, media, CFG)["verdict"] == "HOLD FOR REVIEW"


def test_namesake_cleared_does_not_block():
    media = [{"label": "namesake_cleared"}]
    assert decide(good_facts(), RESOLVED, media, CFG)["verdict"] == "CLEARED"


def test_not_resolved_is_cannot_verify():
    v = decide([], {"resolve": {"chosen": None, "candidates": []}}, [], CFG)
    assert v["verdict"] == "CANNOT VERIFY" and "could not be resolved" in v["reasons"][0]


def test_lookup_failed_is_hold_not_cannot_verify():
    v = decide([], {"resolve": {"failed": True}}, [], CFG)
    assert v["verdict"] == "HOLD FOR REVIEW" and v["rule"] == "0_lookup_failed"


def test_missing_activity_is_hold_not_cleared():
    evidence = [ev(1, "director_current_role"), ev(2, "domain_matches_record")]
    assert decide(evidence, RESOLVED, [], CFG)["rule"] == "6_not_enough_to_clear"


def test_threshold_comes_from_config():
    cfg = {**CFG, "verdict_rules": {**CFG["verdict_rules"], "front_min_hard": 3}}
    evidence = good_facts() + [ev(1, "lookalike_domain", "hard"), ev(2, "nominee_pattern", "hard")]
    assert decide(evidence, RESOLVED, [], CFG)["verdict"] == "SUSPECTED FRONT"
    assert decide(evidence, RESOLVED, [], cfg)["verdict"] == "HOLD FOR REVIEW"
