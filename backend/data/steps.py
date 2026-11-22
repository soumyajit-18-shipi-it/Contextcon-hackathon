"""Data steps (Crustdata): resolve -> company -> director -> core_checks.

Every evidence item cites the Crustdata source row it came from (source_id), the exact JSON path in
that response (field_path) and the record's date. Missing data is cant_verify (with what's missing);
a source that timed out or errored makes the step raise, so the engine retries once and then records
'unknown'. Only contradictions are hard flags. Thresholds come from config.yaml -> rules.
"""
import re
from datetime import date, datetime, timedelta

from backend.data import crustdata
from backend.engine.names import name_score, normalize_domain, same_person

HOLD_STATUSES = {"no_credits"}
FAILED_STATUSES = {"timeout", "error", "rate_limited"}
# A leader / directorship title (whole words), excluding junior or non-executive roles that contain those words
# ("Founder's Office", "Assistant to the Director", "Advisor", "Investor").
LEADER_TITLE = re.compile(r"\b(co-?founder|founder|ceo|chief executive|managing director|director|md|proprietor|owner|"
                          r"partner|president|chairman|chairperson)\b", re.IGNORECASE)
NOT_LEADER = re.compile(r"\b(office|intern|assistant|associate|advisor|adviser|investor|mentor|member|player|creator|"
                        r"volunteer|student)\b", re.IGNORECASE)


def is_leader_title(title) -> bool:
    return bool(title) and bool(LEADER_TITLE.search(title)) and not NOT_LEADER.search(title)


# ---------------- helpers ----------------

class SourceUnavailable(Exception):
    """A source timed out or errored: the engine retries, then records 'unknown' (never 'not found')."""


def _stop_reason(result) -> str | None:
    """Return a hold reason if the run must stop (credits gone / credit ceiling)."""
    if result["status"] in HOLD_STATUSES:
        return "Crustdata credits exhausted (402)"
    if isinstance(result.get("data"), dict) and result["data"].get("reason") == "credit_ceiling":
        return "run credit ceiling reached"
    return None


def _ev(check, claim, value, source_id, field_path, record_date, flag="none", status="verified", missing=None):
    return {"check": check, "claim": claim, "value": value, "source_id": source_id, "field_path": field_path,
            "passage": None, "record_date": record_date, "flag": flag, "status": status, "missing": missing}


def _missing(check, claim, missing, source_id=None, flag="none"):
    return _ev(check, claim, None, source_id, None, None, flag=flag, status="cant_verify", missing=missing)


def _company_from_match(match: dict, index: int, source_id: int, entry: int = 0) -> dict:
    """Identify/enrich match -> the company shape lookalike/duplicate expect."""
    data = match["company_data"]
    info = data.get("basic_info") or {}
    return {
        "name": info.get("name"), "domain": normalize_domain(info.get("primary_domain")),
        "primary_domain": info.get("primary_domain"), "all_domains": info.get("all_domains") or [],
        "company_id": data.get("crustdata_company_id"), "year_founded": info.get("year_founded"),
        "employee_count_range": info.get("employee_count_range"), "website": info.get("website"),
        "confidence": match.get("confidence_score"), "source_id": source_id,
        "field_path": f"[{entry}].matches[{index}].company_data.basic_info.primary_domain", "record_date": None,
    }


def _first_match(data) -> dict | None:
    try:
        return data[0]["matches"][0]
    except (KeyError, IndexError, TypeError):
        return None


def _day(value) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


# ---------------- resolve ----------------

async def step_resolve(ctx):
    """Identify by domain first (strongest), then by name. Several plausible name matches -> a person picks."""
    run_id, rules = ctx["run_id"], ctx["config"]["rules"]
    name, domain = ctx["input"].get("name"), normalize_domain(ctx["input"].get("website"))
    by_domain, by_name, name_matches, failures = None, None, [], []

    if domain:
        r = await crustdata.call(run_id, "/company/identify", {"domains": [domain], "fields": ["basic_info"]})
        if _stop_reason(r):
            return {"hold": _stop_reason(r)}
        if r["status"] in FAILED_STATUSES:
            failures.append(f"identify by domain: {r['status']}")
        elif r["status"] == "ok":
            by_domain = _company_from_match(_first_match(r["data"]), 0, r["source_id"])

    if name:
        r = await crustdata.call(run_id, "/company/identify", {"names": [name], "fields": ["basic_info"]})
        if _stop_reason(r):
            return {"hold": _stop_reason(r)}
        if r["status"] in FAILED_STATUSES:
            failures.append(f"identify by name: {r['status']}")
        elif r["status"] == "ok":
            matches = r["data"][0]["matches"]
            name_matches = [_company_from_match(m, i, r["source_id"]) for i, m in enumerate(matches)]
            name_matches.sort(key=lambda c: c["confidence"] or 0, reverse=True)
            by_name = name_matches[0] if name_matches else None

    if failures and not by_domain and not name_matches:
        raise SourceUnavailable("; ".join(failures))   # unknown, not "not found"

    plausible = [c for c in name_matches if (c["confidence"] or 0) >= rules["resolve_min_confidence"]]
    possible = [c for c in name_matches if (c["confidence"] or 0) >= rules["resolve_candidate_min_confidence"]]
    weak = [c for c in name_matches if c not in possible]   # fuzzy name hits: shown, never offered as "the company"
    if by_domain:
        chosen, candidates = by_domain, []
    elif len(plausible) == 1:
        chosen, candidates = plausible[0], []
    else:   # several plausible, or only possible matches: a person picks. None possible -> not found
        chosen, candidates = None, (plausible or possible)[: rules["max_candidates"]]
    return {"by_domain": by_domain, "by_name": by_name, "candidates": candidates, "chosen": chosen,
            "weak_matches": weak[: rules["max_candidates"]],
            "match_confidence": chosen["confidence"] if chosen else None,
            "chosen_by": "domain" if by_domain else ("name" if chosen else None), "lookup_failures": failures}


# ---------------- company ----------------

ENRICH_FIELDS = ["basic_info", "headcount", "people", "locations", "web_traffic"]


def _leaders(people: dict, base: str) -> list[dict]:
    """Everyone in founders/cxos/decision_makers with what we need to pick and enrich a director."""
    out = []
    for group in ("founders", "cxos", "decision_makers"):
        for i, p in enumerate(people.get(group) or []):
            profile = p.get("basic_profile") or {}
            out.append({"name": profile.get("name"), "title": profile.get("current_title"), "group": group,
                        "person_id": p.get("crustdata_person_id"), "updated_at": p.get("updated_at"),
                        "profile_url": ((p.get("social_handles") or {}).get("professional_network_identifier")
                                        or {}).get("profile_url"),
                        "field_path": f"{base}.people.{group}[{i}].basic_profile.name"})
    return out


async def step_company(ctx):
    run_id, rules = ctx["run_id"], ctx["config"]["rules"]
    chosen = ctx["outputs"]["resolve"]["chosen"]
    r = await crustdata.call(run_id, "/company/enrich",
                             {"crustdata_company_ids": [chosen["company_id"]], "fields": ENRICH_FIELDS})
    if _stop_reason(r):
        return {"hold": _stop_reason(r)}
    if r["status"] in FAILED_STATUSES:
        raise SourceUnavailable(f"company enrich: {r['status']}")
    if r["status"] == "empty":
        return {"evidence": [_missing("founded_year", "Founding year on record", "company enrich returned no record",
                                      r["source_id"])]}

    sid, base = r["source_id"], "[0].matches[0].company_data"
    cd = _first_match(r["data"])["company_data"]
    info, headcount = cd.get("basic_info") or {}, cd.get("headcount") or {}
    series = headcount.get("timeseries") or []
    record_date = series[-1]["date"] if series else None   # enrich has no updated_at; latest data point
    evidence = []

    year = info.get("year_founded")
    evidence.append(_ev("founded_year", f"Founded in {year} (company record)", year, sid,
                        f"{base}.basic_info.year_founded", record_date) if year else
                    _missing("founded_year", "Founding year on record", "no founding year in the company record", sid))

    total = headcount.get("total")
    if total is None:
        evidence.append(_missing("headcount_present", "Has employees on record", "no headcount in the record", sid))
    else:
        evidence.append(_ev("headcount_present", f"{total} employees on record", total, sid,
                            f"{base}.headcount.total", record_date, flag="none" if total > 0 else "soft"))

    if len(series) >= 2:
        cutoff = _day(series[-1]["date"]) - timedelta(days=30 * rules["headcount_trend_months"])
        window = [p for p in series if (_day(p["date"]) or cutoff) >= cutoff] or series[-2:]
        first, last = window[0]["employee_count"], window[-1]["employee_count"]
        changed = len({p["employee_count"] for p in window}) > 1
        evidence.append(_ev("headcount_trend",
                            f"Headcount {first} -> {last} over {rules['headcount_trend_months']} months"
                            + ("" if changed else " (no change at all)"),
                            {"from": first, "to": last}, sid, f"{base}.headcount.timeseries", record_date,
                            flag="none" if changed else "soft"))
    else:
        evidence.append(_missing("headcount_trend", "Headcount changes over time", "no headcount history", sid))

    traffic = ((cd.get("web_traffic") or {}).get("domain_traffic") or {})
    return {
        "company_id": cd.get("crustdata_company_id"), "name": info.get("name"),
        "primary_domain": info.get("primary_domain"), "all_domains": info.get("all_domains") or [],
        "year_founded": year, "headcount_total": total, "growth_yoy_pct": (headcount.get("growth_percent") or {}).get("yoy"),
        "headcount_timeseries": series[-13:], "web_traffic": {d: t.get("monthly_visitors") for d, t in traffic.items()},
        "locations": {k: (cd.get("locations") or {}).get(k) for k in ("headquarters", "city", "state", "country")},
        "leaders": _leaders(cd.get("people") or {}, base), "source_id": sid, "record_date": record_date,
        "evidence": evidence,
    }


# ---------------- director ----------------

def _pick_directors(ctx, leaders: list[dict], limit: int) -> tuple[list[dict], bool]:
    """The named director if the client gave one, else the top leaders. Returns (people, named_by_client)."""
    named = ctx["input"].get("director")
    with_url = [p for p in leaders if p["profile_url"]]
    if named:
        return [p for p in with_url if same_person(named, p["name"])][:1], True
    def rank(p):
        return (p["group"] != "founders", not is_leader_title(p["title"]))
    picked, seen = [], set()
    for p in sorted(with_url, key=rank):
        if p["person_id"] not in seen and is_leader_title(p["title"]):
            picked.append(p)
            seen.add(p["person_id"])
    return picked[:limit], False


async def step_director(ctx):
    run_id, rules = ctx["run_id"], ctx["config"]["rules"]
    company = ctx["outputs"].get("company") or {}
    if not company.get("company_id"):
        return {"profiles": [], "evidence": [_missing("director_current_role", "Director currently runs the company",
                                                      "no company record to take the leadership from")]}
    people, named_by_client = _pick_directors(ctx, company.get("leaders") or [], rules["max_directors"])
    if not people:
        why = (f"'{ctx['input']['director']}' is not among the company's leaders on record" if named_by_client
               else "no leader with a public profile on the company record")
        return {"profiles": [], "evidence": [_missing("director_current_role", "Director currently runs the company", why,
                                                      company.get("source_id"))]}

    profiles, evidence, personal = [], [], []
    for person in people:
        r = await crustdata.call(run_id, "/person/enrich", {"professional_network_profile_urls": [person["profile_url"]],
                                                            "fields": ["basic_profile", "experience"]})
        if _stop_reason(r):
            return {"hold": _stop_reason(r)}
        if r["status"] in FAILED_STATUSES:
            raise SourceUnavailable(f"person enrich: {r['status']}")
        if r["status"] == "empty":
            evidence.append(_missing("director_current_role", f"{person['name']} currently runs the company",
                                     "person profile not found", r["source_id"]))
            continue
        sid, base, record_date = r["source_id"], "[0].matches[0].person_data", person.get("updated_at")
        pd = _first_match(r["data"])["person_data"]
        profile = pd.get("basic_profile") or {}
        current = ((pd.get("experience") or {}).get("employment_details") or {}).get("current") or []
        here = next(((i, c) for i, c in enumerate(current)
                     if c.get("crustdata_company_id") == company["company_id"]
                     or normalize_domain(c.get("company_website_domain")) == normalize_domain(company.get("primary_domain"))),
                    (None, None))
        idx, role = here
        name = profile.get("name") or person["name"]

        # Data minimisation: keep only these fields.
        kept = {"name": name, "title": role.get("title") if role else None, "employer": role.get("name") if role else None,
                "start_date": role.get("start_date") if role else None,
                "city": (profile.get("location") or {}).get("city") or (profile.get("location") or {}).get("raw"),
                "current_roles": len(current), "source_id": sid, "person_id": person["person_id"]}
        profiles.append(kept)
        personal += [{"person": name, "field": f, "source_id": sid, "purpose": "vendor director verification"}
                     for f in ("name", "title", "employer", "start_date", "city", "current_roles") if kept[f] is not None]

        if role:
            evidence.append(_ev("director_current_role",
                                f"{name} is currently {role.get('title')} at {role.get('name')} (since {str(role.get('start_date'))[:10]})",
                                {"title": role.get("title"), "employer": role.get("name")}, sid,
                                f"{base}.experience.employment_details.current[{idx}].title", record_date))
            start = _day(role.get("start_date"))
            founded = company.get("year_founded")
            if start and founded and start.year < founded - 1:
                evidence.append(_ev("director_tenure_fits", f"{name} started in {start.year}, before the company was founded ({founded})",
                                    str(start), sid, f"{base}.experience.employment_details.current[{idx}].start_date",
                                    record_date, flag="soft"))
            elif start and (date.today() - start).days < rules["director_recent_days"]:
                evidence.append(_ev("director_tenure_fits", f"{name} joined only {(date.today() - start).days} days ago",
                                    str(start), sid, f"{base}.experience.employment_details.current[{idx}].start_date",
                                    record_date, flag="soft"))
            elif start:
                evidence.append(_ev("director_tenure_fits", f"{name} has been in the role since {start}", str(start), sid,
                                    f"{base}.experience.employment_details.current[{idx}].start_date", record_date))
        elif current and named_by_client:
            # The client named this person and the profile shows other current employers only: a contradiction.
            others = ", ".join(c.get("name") or "?" for c in current[:3])
            evidence.append(_ev("director_current_role", f"{name}'s profile shows current employer(s) {others}, not this company",
                                others, sid, f"{base}.experience.employment_details.current", record_date, flag="hard"))
        else:
            evidence.append(_missing("director_current_role", f"{name} currently runs the company",
                                     "profile shows no current role at this company", sid))

        # Nominee pattern counts DIRECTORSHIP-type roles only (advisor/investor/member roles are normal for founders).
        directorships = sum(1 for c in current if is_leader_title(c.get("title")))
        many = directorships >= rules["nominee_roles"]
        evidence.append(_ev("nominee_pattern", f"{name} holds {directorships} current directorship-type roles "
                            f"({len(current)} current roles in total)"
                            + (f" (>= {rules['nominee_roles']}: possible nominee)" if many else ""),
                            directorships, sid, f"{base}.experience.employment_details.current", record_date,
                            flag="hard" if many else "none"))

    return {"profiles": profiles, "evidence": evidence, "personal_data": personal}


# ---------------- core checks (cross-checks between sources) ----------------

async def step_core_checks(ctx):
    run_id, rules = ctx["run_id"], ctx["config"]["rules"]
    resolve, company = ctx["outputs"].get("resolve") or {}, ctx["outputs"].get("company") or {}
    if not company.get("company_id"):
        return {"evidence": [_missing("domain_matches_record", "Website domain is on the company record",
                                      "no company record to compare with")]}
    sid, base, record_date = company["source_id"], "[0].matches[0].company_data", company.get("record_date")
    evidence = []

    # domain_matches_record: hard only on a contradiction (the domain belongs to a DIFFERENT company).
    domain = normalize_domain(ctx["input"].get("website"))
    record_domains = {normalize_domain(d) for d in company.get("all_domains") or []} | {normalize_domain(company.get("primary_domain"))}
    by_domain = resolve.get("by_domain")
    if not domain:
        evidence.append(_missing("domain_matches_record", "Website domain is on the company record", "no website given"))
    elif domain in record_domains:
        evidence.append(_ev("domain_matches_record", f"{domain} is listed on the company record", domain, sid,
                            f"{base}.basic_info.all_domains", record_date))
    elif by_domain and by_domain.get("company_id") != company.get("company_id"):
        evidence.append(_ev("domain_matches_record", f"{domain} belongs to a different company: {by_domain.get('name')}",
                            domain, by_domain["source_id"], by_domain["field_path"], None, flag="hard"))
    else:
        evidence.append(_ev("domain_matches_record", f"{domain} is not on the company record ({company.get('primary_domain')})",
                            domain, sid, f"{base}.basic_info.all_domains", record_date, flag="soft"))

    # name_location_consistent: the name given matches the name on record.
    score = name_score(ctx["input"].get("name"), company.get("name"))
    evidence.append(_ev("name_location_consistent",
                        f"Name on record '{company.get('name')}' {'matches' if score >= rules['lookalike_name_min'] else 'differs from'} "
                        f"'{ctx['input'].get('name')}' ({score:.0f}%)", company.get("name"), sid, f"{base}.basic_info.name",
                        record_date, flag="none" if score >= rules["lookalike_name_min"] else "soft"))

    # hiring_activity: job postings in the last N days.
    since = (date.today() - timedelta(days=rules["hiring_window_days"])).isoformat()
    r = await crustdata.call(run_id, "/job/search", {
        "filters": {"op": "and", "conditions": [
            {"field": "company.basic_info.company_id", "type": "=", "value": company["company_id"]},
            {"field": "metadata.date_added", "type": "=>", "value": since}]},
        "fields": ["job_details.title", "job_details.url", "metadata.date_added"],
        "sorts": [{"field": "metadata.date_added", "order": "desc"}], "limit": 1})
    if _stop_reason(r):
        return {"hold": _stop_reason(r)}
    if r["status"] in FAILED_STATUSES:
        evidence.append(_ev("hiring_activity", "Job postings in the last months", None, None, None, None,
                            status="unknown", missing=f"job search {r['status']}"))
    elif r["status"] == "ok":
        job = r["data"]["job_listings"][0]
        evidence.append(_ev("hiring_activity", f"{r['data'].get('total_count')} job postings since {since}; latest "
                            f"'{job['job_details'].get('title')}' on {job['metadata'].get('date_added', '')[:10]}",
                            r["data"].get("total_count"), r["source_id"], "job_listings[0].metadata.date_added",
                            job["metadata"].get("date_added")))
    else:
        evidence.append(_ev("hiring_activity", f"No job postings since {since}", 0, r["source_id"], "total_count", since,
                            flag=rules["flag_no_recent_hiring"]))

    # web_traffic: non-trivial monthly visitors on any of the company's domains.
    traffic = company.get("web_traffic") or {}
    if not traffic:
        evidence.append(_missing("web_traffic", "Website has visitors", "no web traffic in the record", sid))
    else:
        top_domain, visitors = max(traffic.items(), key=lambda kv: kv[1] or 0)
        evidence.append(_ev("web_traffic", f"{top_domain}: {int(visitors or 0):,} monthly visitors", visitors, sid,
                            f"{base}.web_traffic.domain_traffic.{top_domain}.monthly_visitors", record_date,
                            flag="none" if (visitors or 0) >= rules["min_monthly_visitors"] else "soft"))
    return {"evidence": evidence}
