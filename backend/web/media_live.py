"""Live adverse-media screen (owned by C; Lead's version for live runs). Reuses C's grounding,
quote validation, namesake scoring and evidence format from media.py.

  1. Up to 2 searches: "<director>" and "<company>" with adverse terms (web-call budget from config).
  2. Each result's title + snippet (stored in the search source) is the text. Code pre-filters:
     only results that mention our director/company AND contain an adverse word go to the LLM.
  3. The LLM only EXTRACTS: who the subject is, whether they are named as the ACCUSED (not a victim
     or a bystander), the event, and an exact quote. Code decides everything else:
       - person accused, same name as our director -> C's score_identity: match / namesake_cleared / unresolved
       - our company named as accused            -> unresolved (a person must review the allegation)
       - victim / unrelated / no event            -> not a hit
  4. No hits -> one verified item "no adverse media in N results" citing the searches.
     A failed search -> unknown (never "clean").
"""
import asyncio
import re
from types import SimpleNamespace

from backend.web import adapters, llm, websearch
from backend.web.media import TERMS, _evidence, _hold, _norm, _source, grounded_facts, score_identity

PROMPT_VERSION = "media-live-v1"
ADVERSE_WORDS = re.compile(r"\b(fraud\w*|scam\w*|arrest\w*|ED|SEBI|lawsuit\w*|defaulted|defaulter\w*|cheat\w*|launder\w*|"
                           r"FIR|raid\w*|probe\w*|charged|chargesheet\w*|convict\w*|penalt\w*|banned|absconding|forg\w*)\b",
                           re.IGNORECASE)
FIELDS = ["subject_name", "subject_type", "accused", "event", "event_date", "city", "role", "company", "quote"]
SCHEMA = {
    "type": "object", "additionalProperties": False, "required": FIELDS,
    "properties": {**{f: {"type": "string"} for f in FIELDS}, "accused": {"type": "boolean"}},
}
SYSTEM = (
    "You read one search result (title and snippet). Report the main person or company it says did something "
    "wrong. subject_type is 'person' or 'company'. accused is true only if the text says that subject is accused, "
    "charged, arrested, fined, sued or convicted; false if the subject is a victim, a warning issuer, or not "
    "accused. event: the wrongdoing as stated, else empty. event_date: an explicit ISO date (YYYY-MM-DD), else "
    "empty. city, role, company: only if stated for that subject, else empty. quote: one contiguous exact passage "
    "copied from the text that names the subject and the event. Copy values verbatim. Use empty strings for "
    "anything not stated. Do not judge identity, flags or verdicts."
)


def _mentions(text: str, name: str | None) -> bool:
    return bool(name) and _norm(name) in _norm(text)


def _words(text: str) -> str:
    """Words only, lower-case: so curly vs straight quotes or dashes don't break an exact-quote check."""
    return " ".join(re.findall(r"\w+", text.casefold()))


async def screen_media_live(ctx):
    run_id, cfg = ctx["run_id"], ctx["config"]
    rules, per_query = cfg["rules"], cfg["rules"]["media_results_per_query"]
    budget = adapters.LedgerWebBudget(cfg["limits"]["web_calls_per_run"])
    output = {"evidence": [], "media_hits": [], "personal_data": [], "queries": [],
              "coverage": {"results_seen": 0, "results_assessed": 0, "web_calls": 0}}
    unknowns = []

    facts = grounded_facts(ctx, SimpleNamespace(director_facts=adapters.director_facts))
    person = facts["person_name"].value if "person_name" in facts else ctx["input"].get("director")
    company = ctx["input"].get("name") or ((ctx["outputs"].get("company") or {}).get("name"))
    output["personal_data"] = [{"person": person, "field": k, "source_id": f.source_id,
                                "purpose": "adverse media identity comparison"} for k, f in facts.items()]

    queries = []
    for name in (person, company):
        literal = " ".join(re.findall(r"\w+", str(name or "")))
        if literal and f'"{literal}" {TERMS}' not in queries:
            queries.append(f'"{literal}" {TERMS}')
    if not queries:
        output["evidence"].append(_evidence("No director or company name to screen"))
        return output

    searched, candidates = [], []
    for query in queries:
        if not await budget.reserve(run_id):
            unknowns.append(("Web-call budget exhausted before all media searches", None))
            break
        result = await websearch.search(run_id, query, sources=rules["media_sources"])
        output["queries"].append(query)
        output["coverage"]["web_calls"] += 1
        if _hold(result):
            return {**output, "hold": "Credits unavailable during media search"}
        if result["status"] not in ("ok", "empty"):
            unknowns.append((f"Media search {result['status']}: not the same as no results", None))
            continue
        source = _source(result, run_id)
        searched.append(source)
        for i, r in enumerate(adapters.search_results(source)[:per_query]):
            output["coverage"]["results_seen"] += 1
            text = f"{r.get('title') or ''}. {r.get('snippet') or ''}"
            if ADVERSE_WORDS.search(text) and (_mentions(text, person) or _mentions(text, company)):
                candidates.append((source, i, r, text))   # adverse-looking AND about our director/company
    output["coverage"]["results_assessed"] = len(candidates)

    async def extract(text):
        """LLM reads one result; returns its extraction, or an error label. Never raises."""
        try:
            x = await llm.llm_json(run_id, "adverse_media_live", SYSTEM, text, SCHEMA, PROMPT_VERSION)
        except llm.LLMUnavailable:
            return "LLM unavailable: an adverse-looking result could not be assessed"
        except Exception:
            return "LLM call failed or timed out: an adverse-looking result could not be assessed"
        if not x.get("accused") or not x.get("event"):
            return x                                       # nobody accused: no quote needed, not a hit
        if not x.get("quote") or _words(x["quote"]) not in _words(text):   # same words, same order
            return "The model's quote was not found in the result text, so the result could not be assessed"
        return x

    extractions = await asyncio.gather(*(extract(text) for _, _, _, text in candidates))
    for (source, i, r, text), x in zip(candidates, extractions):
        if isinstance(x, str):
            unknowns.append((x, source))
            continue
        if not x["accused"] or not x["event"]:
            continue                                      # victim / warning / no wrongdoing stated: not a hit
        if x["subject_type"] == "company" and _mentions(x["subject_name"], company):
            label, score = "unresolved", 0
            reason = f"Company named as accused: {x['event']}. A person must review the allegation and its outcome."
        elif x["subject_type"] == "person" and _mentions(x["subject_name"], person):
            article = {"person_name": x["subject_name"], "company": x["company"] or None, "city": x["city"] or None,
                       "role": x["role"] or None, "event_date": x["event_date"] or None, "approx_age": None}
            score, label, reason = score_identity(article, facts, rules)
        else:
            continue                                      # accused someone else
        output["media_hits"].append({"url": r.get("url"), "title": r.get("title"), "extracted": x,
                                     "match_score": score, "label": label, "reason": reason, "source_id": source["id"]})
        output["evidence"].append({**_evidence(reason, source, status="verified" if label != "unresolved" else "unknown",
                                               passage=x["quote"], value={"label": label, "score": score, "url": r.get("url")}),
                                   "field_path": f"results[{i}]"})

    for reason, source in unknowns:
        output["evidence"].append(_evidence(reason, source))
    if not output["media_hits"] and not unknowns and searched:
        n = output["coverage"]["results_seen"]
        output["evidence"].append({**_evidence(
            f"No adverse media about {person or 'the director'} or {company} in {n} search results "
            f"({output['coverage']['results_assessed']} adverse-looking results checked)",
            searched[0], status="verified", value={"queries": output["queries"], "source_ids": [s["id"] for s in searched]}),
            "field_path": "results"})
    return output
