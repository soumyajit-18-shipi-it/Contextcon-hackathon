# Member D completion audit

Audit date: 2026-11-22. Reviewed `docs/handoffs/00_PROJECT_BRIEF.md`, `README.md`, `NOTES.md`, `tests/cases.md`, all repository paths under `frontend/`, `backend/`, `tests/` and `docs/`, `docs/architecture.svg`, the FastAPI routes, SQLite schema/helpers, orchestrator, verdict/report code and current Git status. Neither `AUDIT.md` nor `FINAL_AUDIT.md` exists. Existing work was retained; no backend contracts, schema or business rules were changed.

**Post-merge note (2026-11-22):** the matrix below records the audit before pulling `origin/main`. Upstream subsequently added the Crustdata client and data checks, website retrieval/LLM helper, duplicate/look-alike logic, CLI, client-record loader, output mapping, events and stats. Those items are no longer absent; the append-only update at the end records their current state. Copied-site/media/namesake/timeline/explanation steps and the final kickoff schema remain incomplete.

**Meaning of statuses:** COMPLETE means implemented and verified in this checkout. PARTIAL means UI/docs/engine support exists but integration or verification is incomplete. BLOCKED means required data or an owned component from another member is absent. MISSING means no deliverable exists.

## Requirement matrix

| Member D requirement | Status | Evidence / remaining work |
|---|---|---|
| Read project brief and inspect existing repo/contracts | COMPLETE | Read brief and actual FastAPI, DB, engine, config and frontend/test/docs files. |
| `/` new check fields, validation, POST `/runs`, redirect | PARTIAL | `frontend/app/page.tsx` uses the actual `RunInput` and typed API client; build/route and backend POST route verified separately. Browser-driven form submission/redirect remains unverified. |
| Central typed API client, base URL, errors and timeout | COMPLETE | `frontend/lib/api.ts`; requests time out after 15 seconds and surface HTTP errors. |
| `/runs/[id]` polling and status | PARTIAL | Polls every 2 seconds while `queued`/`running`, stops on other states, displays step status/current step, limits, spend, time and failed attempts. Browser-driven polling against the service remains unverified; B/C live data steps are absent. |
| Four answer cards and all four verdict labels/reasons | PARTIAL | Uses real `GET /runs/{id}` response; needs a live report from B/C to verify populated content. |
| Explanation and evidence links | PARTIAL | Links cited evidence IDs in structured explanations and `#id` text citations. Member C explanation contract/output is absent; uncited sentences cannot safely be linked by inference. |
| Evidence categories, statuses, flags and dates | PARTIAL | Cards render known evidence and group by check names. Real evidence naming and populated rows need B/C integration. |
| Source viewer: API JSON, field path, web passage, dates/link | PARTIAL | Uses `GET /sources/{id}` and clicked evidence's path/passage; renders response and field highlight, scrolls to it, and creates a web text fragment. Backend source rows do not expose a title or `field_path`, so those depend on clicked evidence; actual API records are not yet available to test. |
| Candidate selection | PARTIAL | Renders candidates and posts `{index}` to the implemented route. Live candidate response unavailable. |
| Duplicate banner/link | PARTIAL | Banner renders `duplicate_of`; match-source/earlier-run links render only if the API supplies `source_id`/`run_id`. Current list/detail contract does not supply a vendor record URL, and duplicate implementation is a stub. |
| Approval/reject, reviewer/reason, HTTP 409, persistent decision | PARTIAL | Form requires reviewer and 3+ character reason, posts the existing schema, surfaces 409 details, and keeps returned approval visible after `done`. Backend route and 409 were verified with TestClient; browser interaction is unverified. |
| Media, copied-site, look-alike, timeline panels | PARTIAL | Components consume contract fields/evidence; B/C/Lead implementations are stubs or absent, so no real result can populate or verify them. |
| Personal data panel and minimisation | PARTIAL | UI renders person/field/source/purpose and required minimisation note. DB getter/schema exist, but B's data steps/logging and minimisation were not present for audit. |
| Ethics: namesake labeling, unknown handling, explanations, reasons, no real-person contact | PARTIAL | UI uses media labels (namesake-cleared is green), treats `unknown` as a timeout/review state, and requires reviewer plus reason. No contact action exists. C's namesake/explanation outputs and B's minimized data logging are absent, so the end-to-end ethics behavior remains unverified. |
| Ledger rows and totals | PARTIAL | UI calls implemented `GET /ledger?run_id=`, renders provider/endpoint/credits/tokens/INR/latency/HTTP status/timestamp and totals. No real calls/ledger measurements exist in this checkout. |
| Crustdata balance | PARTIAL | UI calls implemented `/credits`; balance response is displayed as returned JSON to avoid inventing provider field names. Upstream helper is absent; route returns unavailable stub. |
| `/history` | PARTIAL | Calls `GET /runs`, then uses existing `GET /runs/{id}` for the latest 50 detail records to find duplicate run links when `duplicate_matches` supplies `run_id`. Current duplicate step is a stub and `duplicate_of` names a client vendor, so client-record links remain unavailable. |
| Eight required test cases | COMPLETE | All eight are documented with API-shaped inputs, expected verdict, key evidence, flags and rationale in `tests/cases.md`. Synthetic `.example` inputs are explicitly labelled. |
| Executable case inputs | PARTIAL / BLOCKED | `tests/cases.inputs.json` is exactly an array of `RunInput` POST bodies. The instructed `backend/cli.py`, kickoff format and kickoff kit are absent, so no actual CLI format can be supplied or claimed. |
| Case results expected vs actual | BLOCKED | No live data/check modules or client records; no actual verdicts may be claimed from `.example` fixtures. |
| Architecture source and PNG | PARTIAL | Editable `docs/architecture.svg` and readable 1500×900 `docs/architecture.png` exist. Diagram labels planned data/web calls and states current checkout's data/web modules are stubs; its detailed flow is the documented design, not live external-call evidence. |
| README organizer sections | PARTIAL | README covers required headings and marks organizer items. Measured costs, manual-cost comparison, retention period, kickoff schemas, test actuals, video URL and exact external calls are marked pending where unavailable. |
| Demo script | COMPLETE | `docs/DEMO_SCRIPT.md` contains the requested two-minute sequence and live-only warning. |
| Demo video | BLOCKED | No live integrated system or hosted recording resource/video URL. README and script mark it pending. |
| Frontend production build / typecheck | COMPLETE | `npm run typecheck` and `npm run build` pass. Built routes `/`, `/history`, `/runs/123` returned 200. |
| Frontend lint | COMPLETE | Added ESLint config and `npm run lint`; latest check reports no warnings or errors. Next 15 notes `next lint` is deprecated for Next.js 16. |
| Backend tests | COMPLETE | `PYTHONPATH=. pytest -q`: 10 passed. These validate engine behavior, not external API or UI actions. |
| API route integration checks | COMPLETE | Installed declared requirements into ignored `.venv`; FastAPI TestClient verified POST/GET run, candidate selection, source lookup, ledger, credits route, approval, persisted decision and second-approval HTTP 409 using temporary SQLite. No external provider call was made. |
| Frontend-to-backend interactive browser testing | BLOCKED | Browser automation JS tool is unavailable. Routes were HTTP-checked and API behavior was exercised directly, but no browser-driven form interaction was run. No mocked data was added to production paths. |
| Security audit of JS dependencies | PARTIAL | `npm install` reported two advisories (1 moderate, 1 high); `npm audit --omit=dev` could not resolve `registry.npmjs.org`, so exact advisories could not be checked. |
| Repository history statement | PARTIAL | README describes the visible kickoff-period baseline; historical authenticity cannot be independently established from this Member D audit. |

## Concrete blockers / owner inputs

1. **Lead:** `backend/cli.py`, kickoff input/output schema and client records; duplicate logic and list/detail run-link fields; real cost-per-check and manual-review comparison; verdict/test actuals.
2. **Member B:** Crustdata client/check steps, retries/rate limits, credits helper, call ledger population, source metadata and personal-data minimisation/logging.
3. **Member C:** web/LLM steps, copied-site/media/namesake/timeline outputs, explanation output with evidence IDs, web source metadata.
4. **Environment/organizer:** provide kickoff kit/client records, actual provider credentials and recording/hosting access; browser automation is not available in this session.

No synthetic fixture facts are wired into frontend live responses. Do not present any fixture as a real company check. The current backend stubs intentionally return CANNOT VERIFY rather than fabricating clearance.

## Post-merge reclassification

| Requirement | Current status after `origin/main` merge | Evidence / remaining work |
|---|---|---|
| Crustdata client and core company/director/activity checks | PARTIAL | `backend/data/crustdata.py` and `backend/data/steps.py` are implemented with retry/rate-limit/cache/source/ledger logic. Current-rule live acceptance results and browser integration remain unverified. |
| Duplicate and look-alike checks | PARTIAL | Lead implementations are present. Client records are configurable, but organizer records and the final client mapping/schema are absent. |
| Website retrieval and LLM transport/helper | PARTIAL | Website step and Anthropic transport/helper exist. They require credentials and verified provider results; they do not complete media, copied-site, timeline or explanation steps. |
| CLI and output mapping | PARTIAL | `backend/cli.py` and config-driven `output_map` are present. `tests/cases.cli.json` uses the repository's temporary map, not a verified organizer kickoff file. |
| Personal-data log and ledger | PARTIAL | Schema/helpers and data-step writes exist. Privacy policy/retention and real current-rule cost measurements remain pending; configured rupee conversion rates are placeholders. |
| Architecture | COMPLETE for the implemented shape | SVG/PNG updated to distinguish implemented client/CLI/site retrieval from remaining stubs. |
| Live media/namesake/copy/timeline/explanation and demo | BLOCKED | These steps remain stubs; no live demo should be recorded until integrated and tested. |

Added `tests/cases.cli.json` as a CLI-compatible set under the current temporary `backend/config.yaml` mapping. It is synthetic and must not be presented as the organizer's final kickoff input or live data. The merge audit ran the frontend checks and the expanded backend suite; results are recorded in `FINAL_DELIVERY_AUDIT.md` after completion.
