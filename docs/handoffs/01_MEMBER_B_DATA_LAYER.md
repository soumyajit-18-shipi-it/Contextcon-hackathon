# Handoff: Member B — Data Layer

> Read `00_PROJECT_BRIEF.md` first (idea, rules, contracts, schema). Your folder: `backend/data/`.
> Contracts change only through the Lead. **The kickoff kit's formats override our placeholders.**

## Your mission
Every call to Crustdata goes through you, and you prove the vendor is **real, trading and run by its director**. You also load the **client's records** and map our results into the **kickoff output format**. If your layer never fails silently and every fact is tied to a field and a date, we score on correctness and robustness.

## Files
```
backend/data/crustdata.py      async client (used by C for web search too)
backend/data/ledger.py         record() + run_totals() (used by everyone, incl. LLM calls)
backend/data/client_records.py load the client's vendor list from the kickoff kit → client_vendors table
backend/data/steps.py          step_resolve, step_company, step_director, step_core_checks
backend/data/normalize.py      domain + company-name normalisation (shared with the Lead)
backend/data/output_map.py     our verdict/evidence → kickoff output format (fields from config)
```

## Phase 1 · until 12:45 (needed for 1 PM)

**1. Test calls (by 11:30):** one call per endpoint (identify, company enrich, person enrich, job search, web search). Post the **real field names** in the team chat and `NOTES.md`: domain, founded year, headcount + history, leadership, web traffic, person's current employers + start dates, cost field, record refresh date.

**2. `crustdata.py`:** `async def call(run_id, endpoint, payload, method="POST") -> SourceResult`
- Base URL + both headers; key from env `CRUSTDATA_API_KEY`
- Per-endpoint rate limiter: identify/search/job 30/min, enrich 15/min, web 10/min
- Timeout 20 s, retry ×2 with backoff on timeout/5xx · **429** → sleep `x-ratelimit-reset` then retry · **402** → `no_credits`, no retry · 401/403 → `error` with a clear message · empty → `empty` (≠ timeout)
- Every response → `sources` row (request, raw response, retrieved_at, record_date = the record's refresh date if given) + `ledger` row (credits from the response, latency, status) → return `source_id`
- **Per-run cache:** same (run_id, endpoint, payload) with an ok source → return it, no new call. **This is what makes kill-and-restart cost nothing and repeat nothing.**
- Check credits before calling: if `run.credits_used + estimate > credit_limit` → return `status="error", data={"reason":"credit_ceiling"}` (the engine holds the run)

**3. `ledger.py`:** `record(run_id, provider, endpoint_or_model, prompt_version=None, credits=0, tokens_in=0, tokens_out=0, cost_inr=0, latency_ms=0, http_status=None)` → also updates `runs.credits_used` and `runs.cost_inr`. Put the ₹-per-credit rate in config (the Lead finds it on Crustdata's pricing page).

**4. `client_records.py`:** load the client's vendor/carrier list from the kickoff kit into `client_vendors` (name, normalised name, domain, director, GSTIN or any ID given). **Reload when the file changes**, since organizers may update client records mid-build.

**5. Steps:**
- `step_resolve(ctx)`: Identify by **domain first**, then by **name**. Return `{by_domain, by_name, candidates, chosen|null, match_confidence}`. Several plausible candidates for a name-only input → `chosen=null` (the engine asks a person to pick). Nothing found → empty (→ CANNOT VERIFY). **Return `by_name` separately**, because the Lead's look-alike check uses it.
- `step_company(ctx)`: Company Enrich on the chosen entity → needed fields + source_id per field.
- `step_director(ctx)`: director from input, else the top leader from enrich → Person Enrich (max 2 people, because of credits). **Keep only: name, current title + employer, start date, city, count of current roles.** Log each kept field in `personal_data_log` (purpose = "vendor director verification").

**12:30:** hand these to the Lead for the first end-to-end run.

## Phase 2 · 1:00–2:15 · `step_core_checks(ctx)` → evidence list
Every item: `source_id` + `field_path` + `record_date`. Missing → `cant_verify` + `missing`. Timed out → `unknown`.
| check | logic | flag on failure |
|---|---|---|
| `domain_matches_record` | website domain = the record's domain (normalised) | hard |
| `name_location_consistent` | Identify vs Enrich agree | soft |
| `headcount_present` | headcount > 0 | soft |
| `headcount_trend` | any change in the last 12 months | soft |
| `hiring_activity` | Job Search: postings in the last 6 months | soft |
| `web_traffic` | non-trivial traffic (if the field exists) | soft |
| `director_current_role` | profile shows a **current** role at this company | hard if it shows a different current employer · cant_verify if no profile |
| `director_tenure_fits` | start ≤ company age, not < N days ago (config) | soft |
| `nominee_pattern` | ≥ N concurrent current roles (config) | hard |
| `founded_year` | fact with its source (for the timeline) | none |
Honest firms: missing optional data = soft at most. **Only contradictions are hard.** Thresholds come from `ctx.config.rules`.

**`output_map.py`:** turn the verdict + evidence into the **exact kickoff output format** using `config.output_fields`. When the hour-3 change adds a field, it should only take a config entry + a small mapping function.

## Phase 3 · 2:30–4:30
- `GET /account/credits` helper (the Lead exposes it as `/credits`)
- Give C the founded date, headcount history, director start date and first job posting for the timeline
- Find **real test cases** with Company Search (companies founded after Sep 2026, small headcount; real carriers/logistics firms) → add to `tests/cases.md` with the expected answers
- Kill test with the Lead: kill mid-run → restart → **zero repeated API calls** (check the ledger)

## Done means
- [ ] `call()` never raises; every outcome is a status
- [ ] Every call has a sources row + ledger row with credits and ₹
- [ ] 429/timeout retry and 402 stop both work
- [ ] Every evidence item has source + field + date, or cant_verify + what's missing
- [ ] Re-running a step makes zero new calls
- [ ] Output matches the kickoff format exactly
- [ ] Only minimal personal fields stored, each logged

## Don'ts
LLM never decides a check · timeout is never "empty" · don't enrich every leader · never commit keys · never hard-code client data

## README section (by 5:30)
Setup + env vars · every data source/endpoint and why · rate-limit/retry/cache design · data minimisation · known data limits
