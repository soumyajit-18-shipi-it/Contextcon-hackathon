"""Verdict rules. Plain code, no LLM. Every threshold comes from config.yaml (verdict_rules).

Rules are checked top to bottom; the first that matches decides:
  0. the company lookup itself failed (source down)       -> HOLD FOR REVIEW   (unknown is never "not found")
  1. same domain as a client vendor (exact duplicate)     -> HOLD FOR REVIEW   (even if nothing else verifies;
                                                             the API also refuses to clear it)
  2. not resolved, or every core fact is cant_verify      -> CANNOT VERIFY
  3. hard >= 2, or 1 hard + soft >= 2                     -> SUSPECTED FRONT
     (counted as DISTINCT checks, so one check can never make a front on its own;
      duplicate flags never count here: a known vendor is not a fraud, it goes to HOLD)
  4. duplicate | candidates pending | key source unknown |
     unresolved media hit | failed step | any hard | soft -> HOLD FOR REVIEW
  5. resolved + director confirmed + active + no hard     -> CLEARED, but only if every check in
     verdict_rules.required_for_clear is verified; if not -> HOLD FOR REVIEW ("news screen not completed")
  6. anything else                                        -> HOLD FOR REVIEW   (never guess)
"""
from backend import db

CLEARED = "CLEARED"
FRONT = "SUSPECTED FRONT"
HOLD = "HOLD FOR REVIEW"
CANNOT = "CANNOT VERIFY"

# Plain-language reason when a check that must pass before clearing hasn't been verified.
REQUIRED_CHECK_REASONS = {"adverse_media": "news screen not completed",
                          "copied_site": "website originality check not completed"}


def _ids(items):
    return [e["id"] for e in items]


def decide(evidence: list[dict], outputs: dict, media_hits: list[dict], cfg: dict) -> dict:
    """Pure function: same evidence + config -> same verdict."""
    vr = cfg["verdict_rules"]
    resolve = outputs.get("resolve") or {}
    duplicate = outputs.get("duplicate") or {}

    hard = [e for e in evidence if e["flag"] == "hard" and e["status"] == "verified"]
    soft = [e for e in evidence if e["flag"] == "soft"]
    # For SUSPECTED FRONT: leave out review-only checks (duplicates), count each check once.
    front_hard = [e for e in hard if e["check"] not in vr["review_only_checks"]]
    front_soft = [e for e in soft if e["check"] not in vr["review_only_checks"]]
    n_front_hard = len({e["check"] for e in front_hard})
    n_front_soft = len({e["check"] for e in front_soft})
    core = [e for e in evidence if e["check"] in vr["core_checks"]]
    unknown_key = [e for e in evidence if e["check"] in vr["unknown_key_checks"] and e["status"] == "unknown"]
    failed_steps = [name for name, out in outputs.items() if out.get("failed")]
    unresolved_media = [h for h in media_hits if h.get("label") == "unresolved"]

    def passed(e):
        return e["status"] == "verified" and e["flag"] == "none"

    resolved = bool(resolve.get("chosen"))
    director_confirmed = any(e["check"] == "director_current_role" and passed(e) for e in evidence)
    active = any(e["check"] in vr["activity_checks"] and passed(e) for e in evidence)

    def result(verdict, rule, reasons, items):
        return {"verdict": verdict, "rule": rule, "reasons": reasons, "evidence_ids": _ids(items),
                "facts": {"resolved": resolved, "director_confirmed": director_confirmed, "active": active,
                          "hard": len(hard), "soft": len(soft),
                          "front_hard_checks": n_front_hard, "front_soft_checks": n_front_soft}}

    # 0. The lookup failed (timeout/error) -> we don't know, so a person looks.
    if "resolve" in failed_steps:
        return result(HOLD, "0_lookup_failed", ["Company lookup failed (source unavailable); not the same as not found"], [])

    # 1. Already a client vendor (same domain): a person must look, whatever else we could or couldn't verify.
    exact_duplicates = [e for e in evidence if e["check"] == "duplicate_exact" and e["status"] == "verified"]
    if exact_duplicates:
        reasons = [f"duplicate of {duplicate.get('duplicate_of') or 'an existing client vendor'}: {e['claim']}"
                   for e in exact_duplicates]
        reasons += [f"also flagged: {e['claim']}" for e in hard + soft if e not in exact_duplicates]
        return result(HOLD, "1_exact_duplicate", reasons, exact_duplicates)

    # 2. Can't identify the company, or none of the core facts has a record.
    if not resolved or all(e["status"] == "cant_verify" for e in core):
        missing = [f"{e['check']}: {e['missing']}" for e in core if e["status"] == "cant_verify"]
        if not resolved:
            missing.insert(0, "company could not be resolved from the name or website given")
        if duplicate.get("duplicate_of"):
            missing.append(f"also matches an earlier check: {duplicate['duplicate_of']}")
        return result(CANNOT, "2_not_resolved_or_no_core_facts", missing, core)

    # 3. Enough independent, verified red flags.
    if n_front_hard >= vr["front_min_hard"] or (
            n_front_hard == 1 and n_front_soft >= vr["front_one_hard_min_soft"]):
        return result(FRONT, "3_hard_flags", [e["claim"] for e in front_hard + front_soft], front_hard + front_soft)

    # 4. Something a person must look at.
    reasons, items = [], []
    if duplicate.get("duplicate_of") or duplicate.get("matches"):
        reasons.append(f"possible duplicate of an existing vendor: {duplicate.get('duplicate_of') or 'see matches'}")
    if resolve.get("candidates") and not resolved:
        reasons.append("several possible companies; a person must pick one")
    for e in unknown_key:
        reasons.append(f"{e['check']}: source timed out or errored (unknown)")
    items += unknown_key
    if unresolved_media:
        reasons.append(f"{len(unresolved_media)} news hit(s) could not be matched or cleared")
    for name in failed_steps:
        reasons.append(f"step '{name}' failed; its checks are unknown")
    if hard:
        reasons += [f"hard flag: {e['claim']}" for e in hard]
        items += hard
    if soft:
        reasons += [f"soft flag: {e['claim']}" for e in soft]
        items += soft
    if reasons:
        return result(HOLD, "4_needs_review", reasons, items)

    # 5. Everything needed to clear is verified, including every check in verdict_rules.required_for_clear.
    if resolved and director_confirmed and active and not hard:
        verified_checks = {e["check"] for e in evidence if e["status"] == "verified"}
        not_done = [c for c in vr.get("required_for_clear", []) if c not in verified_checks]
        if not_done:
            return result(HOLD, "5_required_check_missing",
                          [REQUIRED_CHECK_REASONS.get(c, f"required check '{c}' not completed") for c in not_done],
                          [e for e in evidence if e["check"] in not_done])
        confirming = [e for e in evidence if passed(e)]
        return result(CLEARED, "5_all_verified", ["company resolved, director confirmed, active, no flags"], confirming)

    # 6. Not enough to clear -> never guess.
    return result(HOLD, "6_not_enough_to_clear",
                  [f"director confirmed: {director_confirmed}, active: {active}"], [])


async def step_verdict(ctx):
    run_id = ctx["run_id"]
    return decide(db.get_evidence(run_id), ctx["outputs"], db.get_media_hits(run_id), ctx["config"])
