# Verity: Project Brief (v2, replaces all earlier handoff files)

**Event:** ContextCon 05 · "Services, Replaced" · **Track: Trust and compliance**
**Code freeze: 6:00 PM. Hard deadline.** · **Lead:** Soumyajit

## The idea
**The job today:** before a logistics company pays a new carrier or supplier, its compliance/procurement team (or an outside verification firm, paid per vendor) checks that the vendor is real, actually trading, run by the person who claims to run it, and not a front, a duplicate or an impersonator. Analysts do this by hand across sources that share no common key. A slow source looks like a missing one, and a front can carry genuine papers.

**Verity does the whole job.** Our client is a **mid-size Indian 3PL** (details in the kickoff kit). When it wants to onboard a new carrier or supplier, Verity:
1. Takes the request in the client's words (vendor name, website, director if known), or a batch file in the kickoff format
2. Resolves the company on **live data** (Crustdata Company Identify / Enrich, Person Enrich, Job Search, Web Search & Fetch)
3. Checks: real (identity consistent) · trading (headcount, hiring, activity) · run by its director (current role, tenure, nominee pattern) · **not a duplicate** of a vendor in the client's records · **not a look-alike/impersonator** · not a copied/template website · claimed history matches records (timeline)
4. **Screens directors against the news** and **clears innocent namesakes** with a stated reason
5. Decides with plain rules: **CLEARED / SUSPECTED FRONT / HOLD FOR REVIEW / CANNOT VERIFY**. When unsure, it never guesses ("a wrong answer counts more than cannot verify")
6. Writes a report in which **every claim links to the exact field or passage, with its date**
7. **Waits for a person to approve** clearing or rejecting the vendor (irreversible), exactly once
8. Logs every call's cost; every run has a time + cost ceiling; survives kill-and-restart

**Finished result:** a vendor cleared (or rejected) with the evidence on file.

**2-line pitch:** Verity clears a new carrier or supplier for a 3PL before the first rupee moves: it proves the vendor is real, trading, run by its director and not a duplicate, with a source for every claim. It catches fronts with evidence, clears innocent namesakes, and a person approves the final decision.

## How we're judged
**Screening (to reach the top 8–12):** hidden test set + unseen request run on our service, stop/restart test, README, diagram, logs, cost records, repo history. A wrong answer hurts more than cannot verify.
**Finals (100):** Live run 20 · Robustness (kill on stage) 15 · Design (5-min live fix + system design) 15 · **Ethics 25** · **Finance 25**

## Team split
| Member | Role | Owns |
|---|---|---|
| **Soumyajit (Lead)** | Engine + decisions | DB schema, run engine (steps, checkpoints, resume, ceilings), `config.yaml` + hot reload, verdict rules, look-alike + **duplicate vs client records**, batch CLI, backend API, integration, kill drill, finance numbers, design answers, final submission |
| **Member B** | Data layer | Crustdata client (rate limits, retries, 429/402, status), ledger, sources, client-records loader, core checks (identity / activity / director), mapping to the kickoff output format, personal-data minimisation |
| **Member C** | Web + media | Web search/fetch wrapper, LLM helper, adverse media + **namesake clearing**, copied-website check, evidence timeline, plain-language explanations, prompt-injection guard |
| **Member D** | Frontend + delivery | Test cases, Next.js UI (run, report, source viewer, approvals, candidate picker, ledger, personal-data panel), README, architecture diagram, 2-min video |

## Timeline (organizer checkpoints in bold)
| Time | Everyone |
|---|---|
| 10:55–11:20 | Read the kickoff kit together. Agree on contracts (this file). D starts test cases. B test-calls each API. |
| 11:20–12:45 | Build Phase 1. 12:45: Lead runs the first end-to-end request. |
| **1:00 PM** | **One request runs end to end** |
| ~1:15 PM | **Requirement change announced** → Lead updates config; owners adapt within 30 min |
| 1:00–2:15 | Phase 2: real checks, approvals, media, look-alike/duplicate |
| **2:15 PM** | **Submit once on the portal**, then try the hardest case → take what breaks to a mentor |
| 2:30–4:30 | Phase 3: robustness, kill/restart, extras, ethics features |
| 4:30–5:00 | Run every test case; fix bugs |
| **5:00 PM** | **Feature freeze** |
| **5:30 PM** | **README + diagram + 2-min video done** |
| **6:00 PM** | **Code freeze**: final commit |

## Rules (everyone)
- Live data for decisions; mock data only in tests. No hard-coded answers, no stored results shown as live.
- Every claim → exact field/passage + record date. No source → `cannot verify` + what's missing. Model memory is never a source.
- Person approves irreversible actions; approvals happen exactly once.
- Every Crustdata + LLM call goes in the ledger. Every run has a time + cost ceiling.
- Agents contact no real people.
- Commit small and often, `git pull` (merge). **Never force-push or rewrite history.**
- No API keys in git (`.env`). Credit every open-source library in the README.
- Everyone keeps notes in `NOTES.md` (what we tried, what worked, what broke).
- Everyone must be able to explain the verdict rules and the resume logic (live fix).

## Stack & repo
Python 3.11 · FastAPI · SQLite (WAL) · httpx · rapidfuzz · PyYAML · one LLM (JSON mode) · Next.js + Tailwind
```
backend/
  main.py  db.py  cli.py  config.yaml          (Lead)
  engine/   orchestrator, verdict, lookalike, duplicate, report   (Lead)
  data/     crustdata, ledger, client_records, steps, output_map (B)
  web/      websearch, llm, steps, textutil                       (C)
frontend/                                                          (D)
tests/cases.md   docs/architecture.png   NOTES.md   README.md
```

## Crustdata API
Base `https://api.crustdata.com` · headers `authorization: Bearer $CRUSTDATA_API_KEY` and `x-api-version: 2025-11-01`
| API | Endpoint | /min |
|---|---|---|
| Company Identify | POST /company/identify | 30 |
| Company Enrich | POST /company/enrich | 15 |
| Person Enrich | POST /person/enrich | 15 |
| Person Search | POST /person/search | 30 |
| Company Search | POST /company/search | 30 |
| Job Search | POST /job/search | 30 |
| Web Search & Fetch | POST /web/search/live | 10 |
| Credits (free) | GET /account/credits | — |
401 key wrong · **402 credits gone, don't retry, hold run** · 403 not allowed · **429 wait `x-ratelimit-reset` then retry**. Every response reports its cost. 15,000 credits total.
⚠️ Field names below are placeholders; B posts the real ones by 11:30.

## Shared contracts (change only via the Lead)

**`config.yaml`** (reloaded at the start of every run, so the hour-3 change and client rule changes are config edits):
```
limits:   {time_limit_s: 180, credit_limit: 300, cost_limit_inr: 25}
rules:    {nominee_roles: 5, claimed_age_gap_years: 2, director_recent_days: 90,
           namesake_match: 60, namesake_clear: 25, lookalike_max_edit: 2}
output_fields: {...}    # our fields → kickoff output format
client:   {name: ..., records_path: data/client_records.json, extra_rules: [...]}
```

**Run context passed to every step:** `ctx = {run_id, input:{name, website?, director?, claimed_year?, request_text?}, outputs:{step_name: dict}, config}`

**Step order** (each output saved before the next step starts; every step must be safe to re-run):
`resolve(B) → duplicate(Lead) → company(B) → director(B) → site(C) → core_checks(B) → lookalike(Lead) → copied_site(C) → media(C) → timeline(C) → verdict(Lead) → explain(C) → report(Lead) → awaiting_approval`

**SourceResult:** `{status: ok|empty|timeout|error|rate_limited|no_credits, data, source_id, credits, latency_ms}`

**Evidence item:**
```
{check, claim, value, source_id, field_path|null, passage|null, record_date|null,
 flag: hard|soft|none, status: verified|cant_verify|unknown, missing|null}
```
`unknown` = source timed out/errored (never read as "not found"). `cant_verify` must say what's missing.

**DB tables:** `runs(id, client_id, input_json, status, current_step, time_limit_s, credit_limit, credits_used, cost_inr, started_at, updated_at)` · status ∈ queued|running|held|awaiting_candidate|awaiting_approval|done|failed
`steps(run_id, step_name, status, output_json, attempts, UNIQUE(run_id, step_name))`
`sources(id, run_id, kind, endpoint, url, request_json, raw_response, retrieved_at, record_date)`
`evidence(id, run_id, check, claim, value, source_id, field_path, passage, record_date, flag, status, missing)`
`ledger(id, run_id, provider, endpoint_or_model, prompt_version, credits, tokens_in, tokens_out, cost_inr, latency_ms, http_status, ts)`
`media_hits(id, run_id, url, title, extracted_json, match_score, label, reason, source_id)`
`client_vendors(id, client_id, name, domain, director, gstin, other_json)`
`personal_data_log(id, run_id, person, field, source_id, purpose)`
`approvals(run_id UNIQUE, decision, reason, user, ts)`
`verdicts(run_id UNIQUE, verdict, flags_json, answers_json, explanation, report_md, output_json)`

**Backend API (Lead → D):**
`POST /runs` · `GET /runs` · `GET /runs/{id}` → `{run, steps, evidence, media_hits, timeline, candidates?, duplicate_of?, verdict?, answers?, explanation?, personal_data, ledger_summary}` · `GET /sources/{id}` · `POST /runs/{id}/select-candidate` · `POST /runs/{id}/approve` (409 if already decided) · `GET /ledger?run_id=` · `GET /credits`
**CLI:** `python -m backend.cli --input cases.json --output results.json`

**Verdict rules (in config, Lead implements):**
- **CANNOT VERIFY**: company can't be resolved, or the core facts have no record
- **SUSPECTED FRONT**: 2+ hard flags, or 1 hard + 2 soft, all with evidence
- **HOLD FOR REVIEW**: 1 hard alone · soft flags only · unresolved media hit · key source `unknown` · possible duplicate · several candidates
- **CLEARED**: resolved, director confirmed, active, no hard flags, not a duplicate
- No single check can make an honest firm a front. When unsure → HOLD or CANNOT VERIFY, never a guess.

## Ethics (25 pts): built in, not bolted on
Data minimisation (director: name, current role, tenure, city only) · every personal field used goes in `personal_data_log` · namesakes never shown without their label + reason · person approves clear/reject with a reason, override logged · plain-language explanation of every verdict · no contact with real people · retention note in the README

## Finance (25 pts): Lead owns
Buyer: 3PL procurement/compliance teams (later banks and payment firms onboarding merchants) · measured cost per check from the ledger (credits × ₹/credit from Crustdata pricing + LLM tokens) · per-vendor price well above cost, well below manual analyst time · use real, sourced market numbers, no made-up figures

## Design questions (everyone learns)
**100× volume:** job queue + many workers · Postgres · shared rate limiters (Redis) · cross-run cache with freshness dates · batch onboarding
**Second client:** `client_id` everywhere · per-client config (rules, limits, output format) · separate client records · per-client ledger and billing
