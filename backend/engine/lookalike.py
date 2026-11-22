"""Look-alike / impersonation check: does the vendor's website imitate the company its NAME points to?

Uses B's resolve output: by_name (company found from the name) and by_domain (company found from
the website). Expected keys on each: name, domain|primary_domain, all_domains, company_id|crustdata_company_id,
source_id, field_path, record_date.

  1. Same company (name and website resolve to the same company, or the name's record lists
     the vendor's domain)                                   -> pass  (this is the honest .in/.com pair)
  2. Brands look alike: after normalising (drop TLD, hyphens, filler words; 0->o, 1->l, rn->m)
     edit distance <= rules.lookalike_max_edit, or the vendor domain contains the brand
                                                            -> HARD "possible impersonation of X"
  3. Name and website resolve to two unrelated companies    -> SOFT "name and website point to different companies"
  4. Nothing to compare (no website / name didn't resolve)  -> cant_verify, no flag
Not yet: also passing when X's own website links to the vendor domain (needs one extra web fetch).
"""
from rapidfuzz.distance import Levenshtein

from backend.engine.names import brand_key, domain_label, normalize_domain

MIN_BRAND_LEN = 4   # don't call "ab.in" a look-alike of everything containing "ab"


def _domain(company: dict) -> str | None:
    return normalize_domain(company.get("domain") or company.get("primary_domain"))


def _all_domains(company: dict) -> set[str]:
    domains = {normalize_domain(d) for d in company.get("all_domains") or []}
    return {d for d in domains | {_domain(company)} if d}


def _company_id(company: dict):
    return company.get("company_id") or company.get("crustdata_company_id")


def same_company(a: dict | None, b: dict | None) -> bool:
    if not a or not b:
        return False
    if _company_id(a) and _company_id(b):
        return _company_id(a) == _company_id(b)
    return bool(_domain(a)) and _domain(a) == _domain(b)


def brands_look_alike(vendor_domain: str, official_domain: str, max_edit: int) -> tuple[bool, int]:
    """Compare the brand part of two domains. Returns (look alike?, edit distance)."""
    ours, theirs = brand_key(domain_label(vendor_domain)), brand_key(domain_label(official_domain))
    if len(theirs) < MIN_BRAND_LEN or not ours:
        return False, -1
    distance = Levenshtein.distance(ours, theirs)
    return distance <= max_edit or theirs in ours, distance


def assess(vendor_domain: str | None, by_name: dict | None, by_domain: dict | None, max_edit: int) -> dict:
    """Pure decision. Returns {result: pass|impersonation|mismatch|nothing_to_compare, reason, ...}."""
    if not vendor_domain:
        return {"result": "nothing_to_compare", "reason": "no website given"}
    if not by_name:
        return {"result": "nothing_to_compare", "reason": "the name did not resolve to a company to compare with"}

    official = _domain(by_name)
    base = {"vendor_domain": vendor_domain, "official_name": by_name.get("name"), "official_domain": official}

    if vendor_domain in _all_domains(by_name):
        return {**base, "result": "pass", "via": "by_name", "field": "all_domains",
                "reason": f"{by_name.get('name')}'s own record lists {vendor_domain}"}
    if same_company(by_name, by_domain):
        return {**base, "result": "pass", "via": "by_domain", "field": None,
                "reason": f"the name and the website both resolve to {by_name.get('name')}"}
    if not official:
        return {**base, "result": "nothing_to_compare", "reason": f"no domain on record for {by_name.get('name')}"}

    alike, distance = brands_look_alike(vendor_domain, official, max_edit)
    if alike:
        return {**base, "result": "impersonation", "distance": distance, "via": "by_name", "field": None,
                "reason": f"possible impersonation of {by_name.get('name')} (official domain {official}); "
                          f"{vendor_domain} differs by {distance} character(s) after normalising"}
    if by_domain:
        return {**base, "result": "mismatch", "via": "by_domain", "field": None,
                "domain_company": by_domain.get("name"),
                "reason": f"the name points to {by_name.get('name')} ({official}) but the website "
                          f"points to {by_domain.get('name')} ({_domain(by_domain)})"}
    return {**base, "result": "pass", "via": "by_name", "field": None,
            "reason": f"{vendor_domain} does not resemble {official}"}


FLAGS = {"impersonation": ("lookalike_domain", "hard"), "mismatch": ("name_domain_mismatch", "soft"),
         "pass": ("lookalike_domain", "none")}


def to_evidence(finding: dict, by_name: dict | None, by_domain: dict | None) -> dict:
    """Turn a finding into one evidence item that cites the record it is based on."""
    if finding["result"] == "nothing_to_compare":
        return {"check": "lookalike_domain", "claim": "Website is not imitating another company",
                "value": None, "source_id": None, "field_path": None, "passage": None, "record_date": None,
                "flag": "none", "status": "cant_verify", "missing": finding["reason"]}
    check, flag = FLAGS[finding["result"]]
    record = (by_domain if finding.get("via") == "by_domain" else by_name) or {}
    return {"check": check, "claim": finding["reason"],
            "value": {k: finding.get(k) for k in ("vendor_domain", "official_name", "official_domain", "distance")},
            "source_id": record.get("source_id"),
            "field_path": record.get("field_path") or finding.get("field") or "domain",
            "passage": None, "record_date": record.get("record_date"),
            "flag": flag, "status": "verified", "missing": None}


async def step_lookalike(ctx):
    resolve = ctx["outputs"].get("resolve") or {}
    chosen = resolve.get("chosen") or {}
    vendor_domain = normalize_domain(ctx["input"].get("website") or chosen.get("domain"))
    by_name, by_domain = resolve.get("by_name"), resolve.get("by_domain")

    finding = assess(vendor_domain, by_name, by_domain, ctx["config"]["rules"]["lookalike_max_edit"])
    return {"findings": [finding], "evidence": [to_evidence(finding, by_name, by_domain)]}
