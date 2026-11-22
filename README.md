# Veri¯ty

Veri¯ty helps a logistics company review a new carrier or supplier before the first payment. It gathers evidence about identity, trading activity, directors, impersonation, duplicates and history; a person makes the final approval decision.

> **Pitch:** Verity checks whether a new carrier or supplier is real, trading, run by its claimed director and not a duplicate or impersonator. Every conclusion is tied to dated evidence, uncertainty stays visible, and a person approves the final decision once.

## ★ The problem and buyer

★ **Who pays today:** procurement and compliance teams at mid-size Indian 3PLs, and outside verification firms paid per vendor. They currently pay analyst time to reconcile sources that do not share a common key.

★ **Input:** the API accepts one request object with `name` (required), `website`, `director`, `claimed_year`, and `request_text`. The shape is implemented as `RunInput` in `backend/main.py`. The organizer kickoff kit's batch format and client data are not present in this repository, so no kickoff-specific mapping is claimed.

★ **Finished result:** a report with a verdict, evidence and missing information, followed by a human clear/reject decision with a required reason.

★ **Pass criteria:** expected verdict on each acceptance case in [tests/cases.md](tests/cases.md), every factual claim has a source field or passage and date, no timeout is treated as a negative finding, and an unsupported result becomes HOLD or CANNOT VERIFY. The listed cases use synthetic reserved `.example` fixtures, not live evidence; actual pass/fail results remain pending.

## ★ Architecture

![Veri¯ty architecture](docs/architecture.png)

Editable source: [docs/architecture.svg](docs/architecture.svg). The diagram reflects the documented design; the B/C data and web implementations are currently stubs in this checkout. The actual engine/API/database pieces are described below.

## Data sources and API use

★ Planned external sources from the project contract:

- Crustdata Company Identify: `POST /company/identify`
- Crustdata Company Enrich: `POST /company/enrich`
- Crustdata Person Enrich: `POST /person/enrich`
- Crustdata Person Search: `POST /person/search`
- Crustdata Company Search: `POST /company/search`
- Crustdata Job Search: `POST /job/search`
- Crustdata Web Search & Fetch: `POST /web/search/live`
- Crustdata credit balance: upstream `GET /account/credits`, exposed by this backend as `GET /credits`
- Vendor websites and public media pages returned through the web layer
- Client vendor records for duplicate checks
- LLM, planned for constrained fact extraction and explanation writing only; it does not decide checks or verdicts.

The actual `backend/data/steps.py`, `backend/data/crustdata.py`, `backend/web/steps.py`, and `backend/web/llm.py` are absent in this checkout. The above list is the contract's intended source inventory, not a claim that these requests have been made. The API does implement `GET /ledger?run_id=`; the frontend reads the returned rows and summary.

## Evidence and verdict rules

Evidence items carry `check`, `claim`, `value`, `source_id`, `field_path` or `passage`, `record_date`, `flag`, `status`, and `missing`. The frontend requests `GET /sources/{id}` and shows the stored endpoint, URL, response, retrieval date and record date. It highlights the selected field path when that path exists in the stored API response. A web source uses its passage and a text-fragment URL where supplied. If the backend has no exact field path/passage, the UI reports that limitation rather than inventing one.

The rule engine in `backend/engine/verdict.py` uses evidence and configuration:

- **CANNOT VERIFY:** company unresolved, or all core checks are `cant_verify`.
- **SUSPECTED FRONT:** at least two verified hard flags, or one verified hard flag plus the configured number of soft flags.
- **HOLD FOR REVIEW:** duplicates, multiple candidates, unresolved media, unknown key sources, failed steps, a lone hard flag or soft flags.
- **CLEARED:** company resolved, director confirmed, at least one unflagged activity fact, no hard/soft flags, and no review condition.

Every `cant_verify` item names what is missing. An errored or timed-out source is `unknown`; it is never treated as clean or absent. The report keeps uncertainty visible for human review.

## Reliability, costs and approval

Each run is processed through fixed steps and checkpointed in SQLite. The worker requeues interrupted `running` runs at startup and skips saved completed steps. A failed step is retried once by the engine; after two failures its evidence is `unknown`. Time, credit and INR ceilings are read from `backend/config.yaml` and checked before each step. Provider-specific 429 wait behavior and per-run cache behavior depend on the currently absent data client and are not implemented or verified in this checkout. A provider 402 should hold the run according to the contract.

Approval requires `decision`, `reason` (at least three characters), and `user`; `approvals.run_id` is unique and a second attempt receives HTTP 409. Known duplicates cannot be cleared again through the current API. Candidate selection posts an index to `/runs/{id}/select-candidate`.

★ **Finance:** target buyer is 3PL procurement/compliance or a verification firm; pricing is intended to be per vendor. `backend/config.yaml` currently sets `inr_per_credit: 0.0`. No real integrated ledger totals or sourced manual-review cost were available in this checkout, so measured cost per check, proposed price and manual-cost comparison are **pending**. The app displays per-call provider, endpoint/model, credits, tokens, INR, latency, status and timestamp when rows exist. Do not substitute fixture or placeholder values for actual ledger data.

## ★ Ethics and personal data

The intended minimisation policy limits director data to name, current title/employer, start date, city and current-role count; used fields should be written to `personal_data_log` with source and purpose. The UI displays those logged fields with the note “Only fields needed for this check are stored.” Media results have labels; namesake-cleared results are visually distinguished and should include a reason. The backend requires a person to approve/reject with a reason. The workflow does not contact real people. Explanation quality and exact evidence citations depend on the absent Member C implementation.

★ **Retention:** no retention/deletion job or period is implemented in this checkout. A production operator must define an approved retention period and implement deletion before processing real personal data.

## ★ Test results and delivery status

| Case | Expected | Actual |
|---|---|---|
| T1–T8 | See [tests/cases.md](tests/cases.md) | Pending integration with live data steps and client records |

The reserved fixtures test behavior only and do not imply a live company check. The exact kickoff input/output and client records are absent. The backend CLI (`backend/cli.py`) is also absent; `tests/cases.inputs.json` contains request bodies matching the actual `POST /runs` schema, not a claimed CLI format. The 2-minute demo plan is at [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md); the recording is pending.

★ **Demo video:** Pending. No hosted video URL exists yet; record only after the live data/web integrations are in place. Do not show fixture or stub output as a live check.

## Approaches, limits and next steps

The chosen design is a fixed, checkpointed pipeline with code-based verdict rules and a constrained LLM role. A single LLM agent with tools would be less reproducible and more exposed to prompt injection. A planner that chooses checks could be considered later.

Known limits in this checkout: the data and web layers are stubs; no CLI or kickoff mapping/client records; no measured live cost or expected-vs-actual run results; no data-retention implementation; no recorded demo; source `field_path` is available only when attached to an evidence item (the source endpoint itself does not return it). `npm install` reported two advisories (one moderate, one high); the npm audit endpoint was unreachable from this environment, so details remain unverified. Next: complete B/C modules, obtain kickoff assets, verify actual calls and costs, exercise all cases and restart/approval flows on live data, implement retention, export/verify the diagram, and record the live demo.

## Setup and run

Backend (Python 3.11):

```sh
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
uvicorn backend.main:app --reload --port 8000
```

Frontend (Node.js):

```sh
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Frontend checks: `npm run typecheck`, `npm run lint`, and `npm run build` from `frontend/`.

Environment variables: `CRUSTDATA_API_KEY` (needed when the live data client is implemented), `LLM_API_KEY` (provider variable to be finalized by Member C), `VERITY_DB_PATH` (optional; defaults to `verity.db`), and `NEXT_PUBLIC_API_URL` (defaults in the frontend to `http://localhost:8000`). Never commit `.env` or credentials.

## ★ Open-source credits and team

Backend dependencies declared: FastAPI, Uvicorn, httpx, rapidfuzz, PyYAML, Pydantic, python-dotenv, pytest. Frontend dependencies: Next.js, React, TypeScript, Tailwind CSS, PostCSS, Autoprefixer, ESLint and `eslint-config-next`. `frontend/package-lock.json` records the frontend install; review transitive licenses before redistribution.

Soumyajit / Lead: API, DB, engine, verdict and integration. Member B: Crustdata/data/ledger/client-record layer (pending in this checkout). Member C: web/media/LLM/explanations (pending in this checkout). Member D: frontend, test cases and delivery docs.

Repository history begins with the kickoff-period baseline commit visible in Git; no claim of pre-kickoff work is made here.
