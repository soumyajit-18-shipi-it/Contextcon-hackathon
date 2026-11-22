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
