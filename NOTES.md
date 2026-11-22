# NOTES

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
