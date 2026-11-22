# NOTES

## Member C implementation increment — 2026-11-22

- Added website retrieval adapter, deterministic HTML/text helpers, source-linked
  year extraction, and an injectable JSON Schema validated LLM helper.
- Preserved atomic engine checkpointing: steps return evidence instead of writing
  evidence rows. Timeouts remain unknown and 402 outcomes hold the run.
- Integration is pending Member B's client, confirmed fetch endpoint/payload, and
  a configured LLM transport with sourced pricing. No paid/live calls made.
- Later media, copied-site, timeline, and explanation steps remain explicit stubs.
- Added offline tests for provenance, timeout/empty separation, credit exhaustion,
  URL filtering, malformed LLM JSON retries, accounting, and budget prevention.
- Validation: 23 tests passed (tests/test_web.py and tests/test_engine.py) in a
  project-local virtual environment using Python 3.12; git diff --check passed.
  Python 3.11 and live provider compatibility still need validation.
- Before pushing: merged the latest origin/main without conflicts; all 56 web
  and engine tests passed. Updated the documented command for the moved engine tests.

Everyone appends here: what we tried, what worked, what broke. Newest at the bottom. Prefix with your name.

## Lead (Soumyajit)

- 2026-11-22 Step 0: repo skeleton, .gitignore (.env, *.db, node_modules), .env.example, requirements.txt, handoffs committed to docs/handoffs/.
- Kickoff kit not in the repo yet -> output_fields in config.yaml are placeholders until docs/kickoff/ lands.
- Phase 1 spine done: db.py (WAL, UNIQUE(run_id, step_name), UNIQUE(run_id) approvals), orchestrator (checkpoint per step, resume, ceilings, retry once), main.py (all routes), verdict rules v1, report v1.
- Stubs: B/C steps fall back to backend/engine/stubs.py until they define step_<name> in backend/data/steps.py / backend/web/steps.py. Stubs return cant_verify + "STUB" -> verdict CANNOT VERIFY (never a fake CLEARED).
- Contract additions: steps RETURN evidence / media_hits / personal_data in their output dict; the engine saves them atomically with the checkpoint (steps must not insert these rows themselves, or a re-run duplicates them). A step returns {"hold": reason} to stop the run (e.g. 402).
- Tried `from backend.data import output_map` for the stub fallback -> raises ImportError, not ModuleNotFoundError; fixed with importlib.import_module. Caught by tests.
- Time ceiling counts work time (runs.elapsed_s), not wall clock, so a kill + restart on stage doesn't push a run over the limit.
- Windows: pytest's default temp dir was locked in our sandbox; use --basetemp=<writable dir> if you hit WinError 5.
- First end-to-end run (stubs): POST /runs -> 13 steps -> awaiting_approval, CANNOT VERIFY; approve once OK, second approve -> 409.
- Phase 2 duplicate: client vendors (exact domain = hard + blocks clearing; same director + name >= 90 = soft; name >= 85 = look-alike name, soft) and earlier runs (same domain = soft; blocks clearing unless that run was rejected). Client records load via B's client_records.load_client_records(cfg, client_id) or the stub (JSON list at config client.records_path).
- Phase 2 look-alike: brand_key (drop TLD/hyphens/filler words, 0->o 1->l rn->m) + Levenshtein <= lookalike_max_edit or brand contained -> hard. Safeguards: name's record lists the vendor domain, or name + website resolve to the same company. Known limit: honest .in/.com pair where Crustdata knows neither the .in domain nor lists it -> 1 hard -> HOLD (cautious, never FRONT alone). Not done: checking the official site links to the vendor domain (needs one more fetch).
- Verdict: FRONT counts DISTINCT checks and excludes duplicate checks (verdict_rules.review_only_checks). Bug this prevents: exact duplicate (hard) + one other hard would have called a known client vendor a front.
- Normalisation lives in backend/engine/names.py; B can import it instead of writing a second copy in backend/data/normalize.py.
- Verdict order changed: an exact domain match with a client vendor -> HOLD FOR REVIEW (rule 1_exact_duplicate) BEFORE cannot verify, so a vendor already on the client's books is never reported as merely "cannot verify". The duplicate step now also runs when the company can't be resolved (local records, zero API cost). Rules renumbered 0-6.
- Batch CLI: `python -m backend.cli --input cases.json --output results.json [--parallel 2]`. Each case is keyed by sha256(case id + input) -> same run on a re-run, so kill + re-run resumes and never duplicates. Results file is rewritten atomically after every run. Runs that stop early (ceiling, candidate pick, error) are reported as HOLD FOR REVIEW with the reason, never guessed. Input/output shapes are TEMPORARY; remap only in config.yaml (batch_format, input_fields, output_fields).
- Don't point the CLI and the API server at the same DB at once: both re-queue 'running' runs on start. Use VERITY_DB_PATH to separate them.

### Known limits (for the README)
- Look-alike, honest .in/.com pair: if the vendor uses brand.in, the name resolves to the company with brand.com, Crustdata's record does not list brand.in in all_domains, AND identifying brand.in returns no company (or a different id), we raise ONE hard flag "possible impersonation". One hard flag alone is HOLD FOR REVIEW, never SUSPECTED FRONT, so an honest firm is held for a person, not accused. Fix not built: fetch the official site (brand.com) and pass if it links to brand.in (costs one extra web fetch per run).
- Integrated C's first increment (step_site, websearch, llm_json, textutil): 56/56 tests pass. Conventions OK (returns evidence, no evidence inserts, timeout -> unknown, 402 -> hold, calls crustdata.call(run_id, endpoint, payload)). Moved tests/test_web.py -> backend/web/tests/ (tests/ is D's).
- For C: (1) no LLM transport is configured anywhere, so llm_json always raises LLMUnavailable -> pick the provider, add the transport at startup + sourced INR token prices (explain, media extraction and intake all need it); (2) copied_site, media, timeline, explain still run as engine stubs; (3) web evidence has record_date=None (pages have none) -> D shows sources.retrieved_at instead; (4) Lead will switch llm._record to data/ledger.record() once it exists so cost totals live in one place; (5) fetch endpoint/payload gets confirmed from the Crustdata docs in the client step.

## Crustdata: real field names (probed 2026-11-22 with Delhivery, delhivery.com; 6 calls, 5.23 credits)
All calls: headers `authorization: Bearer`, `x-api-version: 2025-11-01`. Cost per call = response header `X-Credits-Used` (decimal string; 0 on errors; absent on 429). Balance: GET /account/credits -> account.credits (free).
| Endpoint | Request we send | Credits seen | Fields we use |
|---|---|---|---|
| POST /company/identify | {domains:[..]} or {names:[..]}, fields:[basic_info] | 0.2 (only if matched) | [i].matches[j].confidence_score, .company_data.crustdata_company_id, .basic_info.{name, primary_domain, all_domains[], website, year_founded, employee_count_range, company_type, status} |
| POST /company/enrich | {crustdata_company_ids:[id], fields:[basic_info, headcount, people, locations, web_traffic]} | 2.0 | company_data.basic_info.*; headcount.total, headcount.timeseries[{date, employee_count}] (204 points, last = freshness date), headcount.growth_percent.{mom,qoq,six_months,yoy,two_years}; web_traffic.domain_traffic.<domain>.monthly_visitors; locations.{headquarters, city, state, country}; people.{founders,cxos,decision_makers}[] each with crustdata_person_id, basic_profile.{name, current_title}, social_handles.professional_network_identifier.profile_url, updated_at, experience (embedded shape uses employer_name / employee_title / employee_start_date / employer_company_id). company_data.updated_at is NOT returned -> we use the last headcount.timeseries date as the record date. |
| POST /person/enrich | {professional_network_profile_urls:[url], fields:[basic_profile, experience]} | 1.0 | person_data.basic_profile.{name, location.city/state/country/raw}; experience.employment_details.current[]{name, title, start_date, crustdata_company_id, company_website_domain} (+ past[]). No updated_at returned -> record date taken from the company-enrich people entry's updated_at. |
| POST /job/search | {filters:{field:"company.basic_info.company_id", type:"=", value:id}, fields:[job_details.title, job_details.url, metadata.date_added], sorts:[{field:metadata.date_added, order:desc}], limit:1} | 0.03 | job_listings[].job_details.{title,url}, .metadata.date_added; total_count |
| POST /web/search/live | {query, sources:[news]} | 1.0 per page | results[]{source,title,url,snippet,position}; metadata.total_results. News urls are google.com/goto redirect links. |
| POST /web/enrich/live (web FETCH) | {urls:[..]} (1-10) | 1.0 | [i]{success, url, timestamp, title, content (full HTML), http_status}. CRUSTDATA_WEB_FETCH_ENDPOINT=/web/enrich/live |
- Data quirk worth knowing: a founder can hold several "current" roles (Delhivery co-founder had 4: advisor/investor elsewhere). nominee_roles threshold (5) must stay above normal founder/investor patterns.
- INCIDENT (fixed): once the real client existed, the test suite made live calls (C's step_site + CLI tests load .env) -> ~25 credits gone and tests took 147 s. backend/conftest.py now blanks both API keys for every test; suite back to 12 s with the balance unchanged.
- LLM: Anthropic (detected from the key format in .env), model claude-haiku-5-5, $0.10 / $0.50 per MTok (list price), effort low, structured output via output_config.format json_schema. usd_to_inr is a PLACEHOLDER in config.
- First real end-to-end run (12:45 checkpoint): Delhivery (delhivery.com) via POST /runs -> 13 steps -> CLEARED, 8 Crustdata calls, 6.43 credits, 77.8 s. Concern raised: it cleared without a news screen (adverse_media still a stub).
- Fix: verdict_rules.required_for_clear: [adverse_media]. A run is only CLEARED if every check in that list is verified; otherwise HOLD FOR REVIEW "news screen not completed" (rule 5_required_check_missing). copied_site can be added to the list later.
- LLM price sourced: Claude Haiku 5.5 $0.10 in / $0.50 out per MTok (prompts up to 100K tokens), https://platform.claude.com/docs/en/about-claude/pricing, checked 2026-11-22.
- Crustdata balance at 12:56 IST 2026-11-22: 15,163.48 credits (= 15,175.14 before the probe - 5.23 probe - 6.43 Delhivery run). ~37 credits used today in total, ~25 of them by the accidental live test run.
