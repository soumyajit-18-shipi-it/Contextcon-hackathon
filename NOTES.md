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

## Member D

- 2026-11-22 Repo audit: project brief is in `docs/handoffs/00_PROJECT_BRIEF.md`; kickoff formats/client records are still absent. API routes and response shape are implemented in `backend/main.py`; B/C step modules and CLI are not present yet.
- Added API-shaped Next.js UI for new runs, polling/report/evidence/source viewing, candidate selection, approval, ledger/personal data, and history. Uses live API only; no frontend mock data.
- Added behavioral test scenarios in Markdown and JSON. `.example` inputs are reserved fixtures because dated live Company Search results and the kickoff format were unavailable; do not present them as live-company cases.
- Added README and architecture SVG. Finance measurements, actual endpoint inventory, live expected-vs-actual results, kickoff mapping, retention policy and demo video still need integration inputs / completion.
- 2026-11-22 Member D follow-up: re-inspected backend/main.py, db.py, orchestrator, verdict/report modules and repository paths. Confirmed no `backend/cli.py`, no B/C step clients, no kickoff assets, and `/sources/{id}` has no field_path field (the UI supplies it from clicked evidence).
- Reworked test docs for all eight scenarios with expected evidence/flags/reasons. `tests/cases.inputs.json` uses exactly the `RunInput` POST fields; it is not represented as a CLI format because no CLI exists. Synthetic reserved `.example` fixtures only.
- Rebuilt UI integration around typed `frontend/lib/api.ts`, two-second active-run polling, error handling, source inspection, report/progress, candidates, persistent approval result, media/lookalike/copied-site/timeline panels, personal-data table, per-call ledger and history.
- Added `docs/DEMO_SCRIPT.md`; video remains pending and must use live runs.
- Added `docs/architecture.png` (1500x900) from editable SVG. Native Swift/AppKit converted it after `sips` could not decode SVG; visual inspection showed the architecture labels and flow.
- Checks: `PYTHONPATH=. pytest -q` passed (10 passed). `python3 -m json.tool` passed for both case JSON files; `git diff --check` passed. Initial bare `pytest -q` could not import `backend`, and `python3 -m pytest` had no pytest module; setting `PYTHONPATH=.` fixed the environment issue.
- Frontend: `npm install` completed and generated `frontend/package-lock.json`; added `@types/react` / `@types/node` after the first typecheck identified their absence. `npm run typecheck` passes. Final `npm run build` passes on Next.js 15.5.29. `npm run start -- --hostname 127.0.0.1 --port 3005` started successfully and GET checks for `/`, `/history`, `/runs/123` returned 200. Interactive browser verification was unavailable because the browser JS tool was not exposed.
- Backend integration smoke check attempted with `VERITY_DB_PATH=/tmp/verity-member-d-api.db uvicorn backend.main:app --port 8013`; it could not start because FastAPI is not installed in the environment. `pytest` covers engine behavior (10 passed) but no live API routes or frontend actions were exercised.
- `npm install` reported two dependency advisories (1 moderate, 1 high). `npm audit --omit=dev` could not reach `registry.npmjs.org` (DNS failure), so advisory details could not be confirmed. No forced package upgrade was applied.
- User-facing reviewer name is requested by the approval form instead of attributing the decision to a hardcoded identity. Missing source field paths, kickoff format/client records, duplicate vendor detail links and absent backend features are documented rather than fabricated.
- 2026-11-22 final D pass: created `REMAINING_WORK.md` with COMPLETE/PARTIAL/BLOCKED classifications across all Member D obligations. Installed `requirements.txt` into ignored `.venv` (Python 3.13); API TestClient smoke passed for POST/GET run, candidate selection, source lookup, ledger/credits routes, approval persistence and second approval 409 using `/tmp/verity-final-api-check.db`. No external provider was called.
- Latest backend check: `PYTHONPATH=. .venv/bin/pytest -q` passed (10 passed); all 8 request objects validated with `backend.main.RunInput`; both JSON files parse.
- Added ESLint configuration and `npm run lint`; lint, `npm run typecheck` and latest production `npm run build` all pass. Next lint emits only its Next 16 deprecation notice. Latest production route requests `/`, `/history`, `/runs/123` each returned 200.
- Re-exported and inspected `docs/architecture.png` (1500×900); labels distinguish implemented API/engine/checkpoint/approval behavior from planned CLI/provider/data/web integrations.
- The prior note that API smoke was blocked is superseded: the initial Uvicorn attempt used the system interpreter without FastAPI; the workspace virtualenv resolved that. Frontend interactive/browser checks remain blocked because browser automation is unavailable. Real provider calls and case verdicts remain blocked by absent B/C modules, client records and kickoff data.
- `npm install` reports 2 advisories (one moderate, one high); `npm audit --omit=dev` failed DNS resolution to the npm registry. Do not claim clean dependency audit.
- Fixed candidate selection to restart run polling after the API requeues the selected run; ledger rows now refresh with run polling, and ledger/credits request failures are visible. Rechecked typecheck and lint after these changes; both pass.
- Final acceptance check after implementation: frontend typecheck/lint/build pass, backend 10 tests pass, eight request fixtures validate and JSON parse, and `git diff --check` passes. The final diagram includes each planned Crustdata endpoint and marks CLI, LLM and external data/web calls as planned/unavailable in this checkout.
- 2026-11-22 final delivery audit: checked the handoff in `docs/handoffs/00_PROJECT_BRIEF.md`, actual FastAPI routes, UI API client, case fixtures, README and diagrams. Corrected the architecture node to label kickoff output mapping as a stub and regenerated/visually checked the 1500×900 PNG.
- Re-ran frontend `npm run typecheck`, `npm run lint`, and `npm run build` successfully; backend `PYTHONPATH=. .venv/bin/pytest -q` passed 10 tests. Eight case JSON request bodies validate as `RunInput`; both JSON files parse; `git diff --check` passes.
- Production route smoke returned HTTP 200 for `/`, `/history`, `/runs/123`. An isolated TestClient smoke passed run list/detail, source, ledger, credits, candidate selection, first approval and second approval 409, with no external provider calls. Browser console/visual interaction and frontend tests remain unavailable/not configured.
- Secret-pattern scan found no common API-key/private-key patterns. No commit made. See `FINAL_DELIVERY_AUDIT.md` for verified scope, blockers, exact submission actions and workspace Git status.
