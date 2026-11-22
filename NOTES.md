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
