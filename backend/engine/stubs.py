"""Placeholder steps for B (backend/data/steps.py) and C (backend/web/steps.py).

The orchestrator uses a stub ONLY when the owner's function doesn't exist yet. As soon as B or C
defines step_<name> in their own module, theirs is used automatically. Nobody edits this file.

Stubs never invent data: every check comes back 'cant_verify' with "STUB" in `missing`,
and every output carries "stub": True so the report lists which steps were not real.
"""
import importlib
import sys


def owned_or_stub(module_name: str, func_name: str):
    """The owner's function if their module defines it, else the stub of the same name here."""
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as e:
        if e.name != module_name:   # the owner's file exists but one of ITS imports is broken: show that
            raise
        module = None
    return getattr(module, func_name, None) or getattr(sys.modules[__name__], func_name)


def _not_implemented(check: str, owner: str, claim: str) -> dict:
    return {
        "check": check, "claim": claim, "value": None,
        "source_id": None, "field_path": None, "passage": None, "record_date": None,
        "flag": "none", "status": "cant_verify",
        "missing": f"STUB: {owner}'s step is not implemented yet, so no source was checked",
    }


# ---------------- STUB – owned by B (backend/data/steps.py) ----------------

async def step_resolve(ctx):
    """STUB – owned by B. Real version: Company Identify by domain, then by name.
    Shape: {by_domain, by_name, candidates, chosen|null, match_confidence}.
    The stub echoes the input as `chosen` (marked stub) so the rest of the pipeline runs;
    it is NOT a resolution, and core checks stay cant_verify -> the verdict is CANNOT VERIFY."""
    inp = ctx["input"]
    return {
        "stub": True,
        "by_domain": None,
        "by_name": None,
        "candidates": [],
        "chosen": {"name": inp.get("name"), "domain": inp.get("website"), "stub": True},
        "match_confidence": None,
    }


async def step_company(ctx):
    """STUB – owned by B. Real version: Company Enrich -> fields + source_id per field."""
    return {"stub": True, "fields": {}}


async def step_director(ctx):
    """STUB – owned by B. Real version: Person Enrich (max 2), minimal fields, personal_data rows."""
    return {"stub": True, "profiles": [], "personal_data": []}


async def step_core_checks(ctx):
    """STUB – owned by B. Real version: the evidence table in B's handoff."""
    checks = ["domain_matches_record", "name_location_consistent", "headcount_present", "headcount_trend",
              "hiring_activity", "web_traffic", "director_current_role", "director_tenure_fits",
              "nominee_pattern", "founded_year"]
    return {"stub": True,
            "evidence": [_not_implemented(c, "B", f"core check: {c}") for c in checks]}


# ---------------- STUB – owned by C (backend/web/steps.py) ----------------

async def step_site(ctx):
    """STUB – owned by C. Real version: fetch home + about page."""
    return {"stub": True, "pages": [], "footer_year": None, "claimed_since_year": None}


async def step_copied_site(ctx):
    """STUB – owned by C. Real version: exact-quote search of distinctive sentences."""
    return {"stub": True,
            "evidence": [_not_implemented("copied_site", "C", "website text is original")]}


async def step_media(ctx):
    """STUB – owned by C. Real version: adverse media search + namesake scoring -> media_hits."""
    return {"stub": True, "media_hits": [],
            "evidence": [_not_implemented("adverse_media", "C", "no adverse media about the director")]}


async def step_timeline(ctx):
    """STUB – owned by C. Real version: dated events + timeline checks."""
    return {"stub": True, "events": [], "evidence": []}


async def step_explain(ctx):
    """STUB – owned by C. Real version: llm_json plain-language explanation citing evidence ids."""
    return {"stub": True, "explanation": None}
