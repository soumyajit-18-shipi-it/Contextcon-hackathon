# Handoff: Lead (Soumyajit) — Engine, Decisions, Integration, Submission

> Read with `00_PROJECT_BRIEF.md`. Your folders: `backend/main.py, db.py, cli.py, config.yaml, backend/engine/`.
> You own the contracts. If someone needs a change, you decide and update the brief.

## Your mission
You build the spine everyone plugs into (DB, run engine, API) and the parts judges hit hardest: **kill-and-restart (15 pts), correct verdicts on hidden tests (screening + 20 pts), the live fix (15 pts), finance (25 pts)**. You also run integration and the submission.

## Files
```
backend/db.py                 schema + helpers (WAL mode)
backend/config.yaml           limits, rules, output_fields, client settings
backend/config.py             load_config(): re-read the yaml at the start of every run
backend/engine/orchestrator.py  worker loop, steps, checkpoints, resume, ceilings
backend/engine/duplicate.py   step_duplicate (vs client records + past runs)
backend/engine/lookalike.py   step_lookalike
backend/engine/verdict.py     step_verdict (pure rules from config)
backend/engine/report.py      step_report (answers + report_md + output via B's output_map)
backend/main.py               FastAPI routes
backend/cli.py                batch runner for the hidden test sets
```

## Step 0 · 10:55–11:20 · unblock everyone (do this FIRST)
1. Read the **kickoff kit**: client name, client records, our track's request, **input + output formats**. Share it in the team chat and commit it to `docs/kickoff/`.
2. Fill `config.yaml` → `output_fields` from the kickoff output format.
3. Create the repo skeleton (folders from the brief), `.gitignore` (`.env`, `*.db`, `node_modules`), `.env.example`, `requirements.txt` (fastapi, uvicorn, httpx, rapidfuzz, pyyaml, pydantic, your LLM SDK).
4. Commit `docs/handoffs/` (all brief + handoff files). **First commit.**

## Phase 1 · 11:20–12:45 · spine (needed for the 1 PM checkpoint)

### `db.py`
Create every table in the brief. `PRAGMA journal_mode=WAL`. Helpers: `create_run`, `get_run`, `set_run_status`, `save_step(run_id, name, status, output)`, `get_steps`, `add_evidence(list)`, `get_evidence`. Use **UNIQUE(run_id, step_name)** and **UNIQUE(run_id) on approvals**. Those two constraints are your exactly-once guarantee.

### `orchestrator.py`: the resume logic (the judges kill this on stage)
```
STEPS = [("resolve",B), ("duplicate",LEAD), ("company",B), ("director",B), ("site",C),
         ("core_checks",B), ("lookalike",LEAD), ("copied_site",C), ("media",C),
         ("timeline",C), ("verdict",LEAD), ("explain",C), ("report",LEAD)]

worker loop (background task started on FastAPI startup):
  on startup: every run with status 'running' → set back to 'queued'  (crashed mid-run)
  loop: pick the oldest 'queued' run
    cfg = load_config()                       # fresh every run (hour-3 change, client changes)
    ctx = {run_id, input, outputs: {done steps' outputs from DB}, config: cfg}
    for each step not yet 'done':
        check ceilings: elapsed > time_limit_s or credits_used > credit_limit or cost_inr > cost_limit_inr
            → status 'held', reason saved, stop
        save_step(name, 'running'); output = await step(ctx)
        save_step(name, 'done', output); ctx.outputs[name] = output   # checkpoint
        after 'resolve': chosen is null and candidates > 1 → 'awaiting_candidate', stop
                         no candidates → skip to verdict (CANNOT VERIFY)
        a step returns {"hold": reason} (402, credit ceiling) → 'held', stop
        a step raises → attempts+1; retry once; then mark the step failed and continue
                        (its checks become 'unknown' → the verdict holds the run)
    after report → 'awaiting_approval'
```
Steps are safe to re-run because B's client caches per run, so a step re-run after a kill makes **zero new API calls**.

### `main.py`: routes from the brief
`POST /runs` · `GET /runs` · `GET /runs/{id}` (join run, steps, evidence, media_hits, timeline, candidates, duplicate_of, verdict, answers, explanation, personal_data, ledger totals) · `GET /sources/{id}` · `POST /runs/{id}/select-candidate` (sets chosen, re-queues) · `POST /runs/{id}/approve` (INSERT; on UNIQUE conflict → **409** with the existing decision) · `GET /ledger` · `GET /credits`. Enable CORS for D.

### Simple first versions
`step_duplicate`, `step_lookalike` → return `[]`. `step_verdict` → basic rules. `step_report` → the 4 answers + evidence list.

**12:45:** run test case 1 end to end with B's and C's steps (stub any that aren't ready) → **commit "first end-to-end run"**. ✅ 1 PM checkpoint.

## ~1:15 · requirement change
Read it, decide what changes (config field? output field? lower limit?), update `config.yaml` + the brief, tell each owner their part. Aim for 30 minutes. Note it in `NOTES.md`.

## Phase 2 · 1:00–2:15

### `verdict.py`: pure function, all thresholds from config
```
facts: resolved?, director_confirmed?, active? (any activity check verified)
hard = evidence with flag hard (verified only) ; soft = flag soft
unknown_key = any of [domain_matches_record, director_current_role, adverse_media] is 'unknown'
1. not resolved, or core facts all cant_verify          → CANNOT VERIFY (list what's missing)
2. hard >= 2, or (hard == 1 and soft >= 2)               → SUSPECTED FRONT
3. duplicate found | candidates pending | unknown_key |
   unresolved media hit | hard == 1 | soft >= 1          → HOLD FOR REVIEW (list reasons)
4. resolved & director_confirmed & active & hard == 0    → CLEARED
5. anything else                                         → HOLD FOR REVIEW   (never guess)
```
Save `flags_json` = the exact rule that fired + the evidence ids (the explanation and the judges use this).

### `duplicate.py`: `step_duplicate(ctx)` (hidden-test hard case!)
Compare the input + resolved entity against `client_vendors` and past runs:
- same normalised domain → **exact duplicate** (hard: "already a client vendor: X")
- same director + similar name (rapidfuzz ≥ 90) → **likely duplicate** (soft) → HOLD
- similar name only (85–90) with a different domain → **look-alike name** (soft) → HOLD, with both shown
Evidence `source_id` = the client-record row (add a `sources` row of kind `client_record`). Duplicate → set `duplicate_of` and **block a second approval**.

### `lookalike.py`: `step_lookalike(ctx)`
- From resolve: `by_name` (company the name points to) vs `by_domain`.
- If `by_name` is an established company whose domain ≠ the vendor domain: normalise both (strip TLD, hyphens, filler words: india, global, logistics, transport, solutions, group, pvt, ltd; map 0→o, 1→l, rn→m) → rapidfuzz/edit distance ≤ `lookalike_max_edit`, or contains the brand token → **hard** "possible impersonation of X (official domain y)".
- Safeguard: if X's record lists the vendor domain, or X's site links to it → pass.
- Name and domain resolve to two different companies (not similar) → soft.

### Approval
The approval handler checks `duplicate_of` and the run status. A decision → `runs.status='done'`. Reject requires a reason. Log the user.

**2:10:** push everything → **2:15 submit on the portal** → run the hardest case (vague name or duplicate) → take what breaks to a mentor.

## Phase 3 · 2:30–4:30

### `cli.py`: batch runner for screening
`python -m backend.cli --input cases.json --output results.json [--parallel 2]`
Reads the kickoff input format → creates runs → runs the orchestrator in-process until each is done/held/awaiting → writes the kickoff output format (via B's `output_map`) incl. verdict, sources, `cannot verify` items, and "held for approval" status. Re-running the same command after a kill resumes the same runs (store an input hash → run_id map), so **no duplicates**.

### Kill drill (practise 3×; it happens on stage)
Start a run → `kill -9` the server during `director`/`media` → restart → check: the run resumes from the next step · ledger shows **no repeated calls** · approvals never duplicate. Also kill the CLI mid-batch and re-run it. Record a short clip for D's video.

### Integration + tuning
Run every case in `tests/cases.md` through the CLI. Fix wrong verdicts by **making rules more cautious**, never by special-casing a test (no hard-coding). Fill in the expected vs actual table.

## Phase 4 · 4:30–5:30
- **5:00 feature freeze**: call it.
- README parts you write:
  - **Approaches considered:** (1) single LLM agent with tools: flexible but not reproducible, can be prompt-injected → rejected · (2) fixed pipeline + config rules + LLM only for extraction/writing → **chosen** · (3) LLM planner choosing checks → future (cheaper)
  - **Test results table**, known limits, next steps (Watcher re-screening, MCA registry as a second source, batch onboarding)
  - **Finance:** buyer · **measured cost per check** from the ledger (avg credits × ₹/credit from Crustdata pricing + LLM ₹) · proposed ₹ price per vendor · comparison with manual analyst time · real, sourced numbers only
- Check D's diagram shows the data calls, approvals, retries, ledger, checkpoints.

## Phase 5 · 5:30–6:00
Repo check: code, README (all ★ items), `docs/architecture.png`, video link, `NOTES.md`, no keys committed. **Final commit by 5:55.**

## Finals prep (learn these)
- **Pitch (3 min):** problem → live run → kill on stage → approval → cost per check
- **Live fix:** most likely a rule/threshold/output-field change → it's in `config.yaml` or `verdict.py`. Know both by heart.
- **100× volume:** queue + many workers · Postgres · shared rate limiters (Redis) · cross-run cache with freshness dates · batch onboarding
- **Second client:** `client_id` everywhere · per-client config · separate records · per-client ledger/billing
- **Ethics:** data minimisation + personal-data log · namesake protection · a person approves with a reason · plain explanations · no real contact
- **Finance:** cost per check from the ledger, price, buyer, why they'd pay

## Your checklist
- [ ] 11:20 kickoff kit shared, config + skeleton committed
- [ ] 12:45 first end-to-end run committed
- [ ] ~1:45 requirement change handled
- [ ] 2:15 portal submission
- [ ] 3:30 CLI runs the whole test file
- [ ] 4:00 kill drill passed 3×
- [ ] 5:00 feature freeze; test table filled
- [ ] 5:55 final commit
