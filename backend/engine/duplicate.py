"""Duplicate check: is this vendor already in the client's records, or checked in an earlier run?

Against each client vendor (first rule that matches wins), thresholds from config.yaml -> rules:
  same normalised domain                           -> duplicate_exact  (hard, blocks clearing)
  same director + name score >= duplicate_name_match -> duplicate_likely (soft -> HOLD)
  name score >= lookalike_name_min, other director -> lookalike_name   (soft -> HOLD, both shown)
Against earlier runs:
  same domain                                      -> duplicate_past_run (soft; blocks clearing
                                                      unless that earlier run was rejected)
Duplicates send the run to HOLD FOR REVIEW. They are never counted as signs of a front
(config verdict_rules.review_only_checks): being a known vendor is not fraud.
"""
from backend import db
from backend.engine import stubs
from backend.engine.names import name_score, normalize_domain, same_person


def _our_domains(ctx) -> set[str]:
    chosen = (ctx["outputs"].get("resolve") or {}).get("chosen") or {}
    domains = {normalize_domain(ctx["input"].get("website")),
               normalize_domain(chosen.get("domain") or chosen.get("primary_domain"))}
    return {d for d in domains if d}


def _our_director(ctx) -> str | None:
    if ctx["input"].get("director"):
        return ctx["input"]["director"]
    profiles = (ctx["outputs"].get("director") or {}).get("profiles") or []
    return profiles[0].get("name") if profiles else None


def _evidence(check, claim, value, source_id, field_path, flag):
    return {"check": check, "claim": claim, "value": value, "source_id": source_id,
            "field_path": field_path, "passage": None, "record_date": None,
            "flag": flag, "status": "verified", "missing": None}


def match_client_vendor(vendor: dict, our_name, our_domains, our_director, rules) -> dict | None:
    """Pure: compare one client vendor with our input. Returns a match or None."""
    their_domain = normalize_domain(vendor.get("domain"))
    score = name_score(our_name, vendor.get("name"))
    if their_domain and their_domain in our_domains:
        return {"type": "duplicate_exact", "flag": "hard", "field_path": "domain", "score": score,
                "claim": f"Already a client vendor: {vendor['name']} ({their_domain})"}
    if same_person(our_director, vendor.get("director")) and score >= rules["duplicate_name_match"]:
        return {"type": "duplicate_likely", "flag": "soft", "field_path": "director", "score": score,
                "claim": f"Likely the same as client vendor {vendor['name']}: same director, name {score:.0f}% similar"}
    if score >= rules["lookalike_name_min"]:
        return {"type": "lookalike_name", "flag": "soft", "field_path": "name", "score": score,
                "claim": f"Name is {score:.0f}% similar to client vendor {vendor['name']} "
                         f"({their_domain or 'no domain on file'}) but the domain is different or unknown"}
    return None


async def step_duplicate(ctx):
    run_id, cfg, rules = ctx["run_id"], ctx["config"], ctx["config"]["rules"]
    loaded = stubs.owned_or_stub("backend.data.client_records", "load_client_records")(cfg, ctx["client_id"])
    vendors = db.get_client_vendors(ctx["client_id"])
    our_name, our_domains, our_director = ctx["input"].get("name"), _our_domains(ctx), _our_director(ctx)

    matches, evidence, duplicate_of = [], [], None

    for vendor in vendors:
        m = match_client_vendor(vendor, our_name, our_domains, our_director, rules)
        if not m:
            continue
        source_id = db.find_or_add_source(run_id, "client_record", f"client_vendors/{vendor['id']}", vendor)
        matches.append({**m, "vendor_id": vendor["id"], "name": vendor["name"], "domain": vendor["domain"],
                        "source_id": source_id})
        evidence.append(_evidence(m["type"], m["claim"], vendor.get(m["field_path"]), source_id,
                                  m["field_path"], m["flag"]))
        if m["type"] == "duplicate_exact" and duplicate_of is None:
            duplicate_of = f"client vendor #{vendor['id']} {vendor['name']}"

    # Earlier runs only (id < this run), so the answer doesn't change when this step is re-run.
    past_runs = [r for r in db.list_runs() if r["id"] < run_id]
    for past in past_runs:
        past_domain = normalize_domain((past["input"] or {}).get("website"))
        if not past_domain or past_domain not in our_domains:
            continue
        source_id = db.find_or_add_source(run_id, "past_run", f"runs/{past['id']}", past)
        claim = (f"Same domain already checked in run #{past['id']} "
                 f"(status {past['status']}, decision {past['decision'] or 'none yet'})")
        matches.append({"type": "duplicate_past_run", "run_id": past["id"], "domain": past_domain,
                        "claim": claim, "source_id": source_id})
        evidence.append(_evidence("duplicate_past_run", claim, past_domain, source_id, "input.website", "soft"))
        if past["decision"] != "reject" and duplicate_of is None:
            duplicate_of = f"run #{past['id']}"

    if not matches:
        checked = {"client_vendors_checked": len(vendors), "past_runs_checked": len(past_runs),
                   "domains_compared": sorted(our_domains)}
        source_id = db.find_or_add_source(run_id, "client_record", "client_vendors?summary", checked)
        if vendors:
            evidence.append(_evidence("duplicate", f"Not a duplicate of any of {len(vendors)} client vendors "
                                      f"or {len(past_runs)} earlier runs", checked, source_id,
                                      "client_vendors_checked", "none"))
        else:
            evidence.append({**_evidence("duplicate", "Not already a client vendor", checked, source_id,
                                         "client_vendors_checked", "none"),
                             "status": "cant_verify",
                             "missing": f"client records not loaded ({cfg['client']['records_path']})"})

    return {"matches": matches, "duplicate_of": duplicate_of, "client_records_loaded": loaded,
            "evidence": evidence}
