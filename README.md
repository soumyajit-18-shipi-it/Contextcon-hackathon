# Verity

Verity checks a new carrier or supplier for an Indian 3PL **before the first rupee moves**. It shows that the vendor is real, trading and run by its director, and that it isn't a duplicate, an impersonator or a front. Every claim links to the exact record field or passage, with its date, and **a person approves the final decision, exactly once**.

Track: Trust and compliance · ContextCon 05 "Services, Replaced"

## ★ The job, and who pays for it today

Before a logistics company pays a new carrier, its procurement/compliance team, or an outside verification firm paid per vendor, checks the vendor by hand. An analyst looks across company registries, LinkedIn-style profiles, job boards, news and the vendor's own website. These sources share no common key, a slow source looks the same as a missing one, and a front can carry genuine papers. Verity does the whole job and leaves the decision to a person.

## ★ Input

- **API** `POST /runs`: structured fields (`name`, `website`, `director`, `claimed_year`), the request in the client's own words (`request_text`), or both, plus an optional `client_id`. Free text is turned into fields by the intake step: a regex finds a website, and the LLM extracts only values that literally appear in the text. With no name and no website, the run waits (`awaiting_input`) until a person adds one.
- **Batch** `python -m backend.cli --input cases.json --output results.json [--parallel 2] [--client id]`: a file of cases. The field names come from `backend/config.yaml` (`batch_format`, `input_fields`). They are temporary until the organisers' kickoff kit arrives, and remapping them is a config edit.

## ★ Finished result

For each vendor, the output has five parts:
- **A verdict:** CLEARED, SUSPECTED FRONT, HOLD FOR REVIEW or CANNOT VERIFY, with the exact rule that fired.
- **The four answers:** who runs it, how long it has existed, whether it is trading, what looks off. Each answer cites evidence ids.
- **An "I can't verify" list** saying what is missing.
- **A plain-language explanation.**
- **The decision:** a person clears or rejects the vendor with a required reason, recorded once. A second attempt is refused with 409.

The batch CLI writes the same result in the configured output format (`output_fields`).

## ★ Pass mark

1. **Correct verdict** on each test case (table below). A wrong answer is worse than CANNOT VERIFY, so the rules hold when unsure.
2. **Every claim is sourced:** a `source_id`, a `field_path` or `passage`, and a `record_date`. No source means `cant_verify` plus what's missing, and a timeout means `unknown`, never "not found".
3. **The run survives a hard kill** with no repeated paid call ([kill drill results](docs/kill_drill_results.md)).
4. **Every paid call is in the ledger,** and every run stays within its time, credit and ₹ ceilings.

## ★ Every data source we call

| Source | Endpoint | Used for |
|---|---|---|
| Crustdata Company Identify | `POST /company/identify` | Resolve by domain first, then by name. Several plausible matches means a person picks. |
| Crustdata Company Enrich | `POST /company/enrich` | Founding year, headcount and its history, web traffic, domains, leaders, HQ |
| Crustdata Person Enrich | `POST /person/enrich` | Director's current role, start date, city, number of current roles (at most 2 people) |
| Crustdata Job Search | `POST /job/search` | Hiring activity in the last 180 days |
| Crustdata Web Search | `POST /web/search/live` | News screen (`sources: ["news"]`) and copied-site exact-quote search |
| Crustdata Web Fetch | `POST /web/enrich/live` | Vendor home and About pages, and pages that share its text |
| Crustdata account | `GET /account/credits` | Balance shown in the UI (free) |
| Anthropic Claude Haiku 5.5 | Messages API | Only extracts facts (intake, news results) and writes the explanation. It never decides a flag or a verdict. |
| Client records | `clients.<id>.records_path` (JSON/CSV) | Duplicate check against the client's existing vendors |

## ★ Architecture

![Verity architecture](docs/architecture.png)

Editable source: [docs/architecture.svg](docs/architecture.svg).

**Steps.** Each vendor check runs 14 fixed steps, and each one is checkpointed in SQLite before the next starts: intake → resolve → duplicate → company → director → site → core_checks → lookalike → copied_site → media → timeline → verdict → explain → report → (person approves).

## Evidence and verdict rules (plain code, thresholds in `config.yaml`)

| # | Rule | Verdict |
|---|---|---|
| 0 | The company lookup itself failed (source down) | HOLD FOR REVIEW. Unknown is never "not found". |
| 1 | Same domain as a client vendor (exact duplicate) | HOLD FOR REVIEW, and clearing is refused by the API |
| 2 | Not resolved, or every core fact is `cant_verify` | CANNOT VERIFY, with the list of what's missing |
| 3 | 2+ hard flags, or 1 hard + 2 soft, counted as **distinct checks**. Duplicates never count. | SUSPECTED FRONT |
| 4 | A duplicate, a pending candidate pick, a key source `unknown`, an unresolved news hit, a failed step, any hard flag, or any soft flag | HOLD FOR REVIEW |
| 5 | Resolved, director confirmed, active, no flags, **and** every check in `required_for_clear` (the news screen) verified | CLEARED, otherwise HOLD "news screen not completed" |
| 6 | Anything else | HOLD FOR REVIEW. We never guess. |

**Only contradictions are hard flags,** for example a named director whose profile shows other current employers, a domain that belongs to a different company, or a claimed founding year more than 2 years older than the record. Missing optional data is soft at most.

**News screen.** Two news searches run, one for the director and one for the company, each with adverse terms. Code keeps only the results that mention our director or company *and* contain an adverse word. The LLM then extracts the subject, whether they are named as **accused** (as opposed to a victim), the event and an exact quote. Code decides the rest:
- A person who is accused goes through namesake scoring (employer, city, role and dates against the director's profile) and comes out as `match`, `namesake_cleared` (with the contradicting fact) or `unresolved`.
- The company itself named as accused is `unresolved`, so a person reviews it.
- Victims and warnings are not hits.

## Reliability, cost and approval

- **Ceilings:** every step first checks the run's limits (300 s of work, 300 credits, ₹25) and holds the run if one is used up. A run may make at most 8 web calls, 2 of them reserved for the news screen.
- **The Crustdata client:**
  - **Rate limits:** per endpoint (identify/search/job 30 a minute, enrich 15, web 10).
  - **Timeouts and errors:** a 20 s timeout, then up to 2 retries.
  - **429:** waits for `x-ratelimit-reset`, then retries.
  - **402:** holds the run, with no retry.
  - **Cache:** a per-run cache, so a step re-run after a kill makes **no new paid call**.
- **The ledger:** every Crustdata and LLM call writes a ledger row (credits from `X-Credits-Used`, tokens, ₹, latency, HTTP status) and a source row (request, raw response, retrieval date, record date).
- **Crash recovery:** on startup, runs left `running` go back to the queue and continue from their last checkpoint. The CLI resumes the same runs by a hash of each case. See the [kill drill results](docs/kill_drill_results.md).
- **Approval exactly once:** `UNIQUE(run_id)` on approvals. A second decision gets 409, and a known duplicate can't be cleared.
- **The event log:** every step's start, end, duration and retries, plus checkpoints, status changes, ceilings, resumes and approvals, go to `GET /runs/{id}/events` and `logs/runs.jsonl`.

## ★ Ethics

- **Data minimisation:** for directors we keep only name, current title, employer, start date, city and the number of current roles. Each field used is logged in `personal_data_log` with its source and purpose, and shown in the UI.
- **Namesakes:** a negative article is never shown next to the director without its label (`match`, `namesake_cleared` or `unresolved`) and the reason. Only news sources count as adverse media, not forum posts or social complaints.
- **The model never decides:** the LLM only extracts and writes. Its text sits between untrusted-data delimiters, and a value is kept only if it appears in the source text.
- **A person decides:** every clear or reject is made by a person with a reason, and is final.
- **No contact:** the system never contacts real people.
- **★ Retention:** no deletion job is implemented yet. Before processing real personal data, an operator must set a retention period, for example 90 days after the decision, and delete `sources`, `personal_data_log` and `evidence` rows after it.

## ★ Finance

- **Buyer:** procurement and compliance teams at mid-size 3PLs, later banks and payment firms onboarding merchants. They pay per vendor checked.
- **Measured cost per check** (`GET /stats`, live runs): full checks cost **6.4–9.4 Crustdata credits** and take **250–300 s** at today's API latency (T2 7.43, T6 6.43, T7 9.43, Delhivery 8.43). A name that resolves to nothing stops early at about 0.2 credits. LLM cost is about ₹0.02 per call, 33 calls for ₹0.64 in the batch, at the placeholder exchange rate. Live numbers: `GET /stats`.
- **₹ per credit is an UNCONFIRMED ASSUMPTION.** Crustdata publishes no public price per credit, and the team hasn't received one in writing. `pricing.inr_per_credit` is a placeholder (`inr_per_credit_is_placeholder: true`), so **every rupee figure for Crustdata is unconfirmed**. Only the credit counts are measured. LLM cost uses Anthropic's list price ($0.10 / $0.50 per million tokens, [source](https://platform.claude.com/docs/en/about-claude/pricing)) and a placeholder exchange rate.
- **Price and manual comparison:** a per-vendor price and the cost of an analyst doing this by hand will be added only with a sourced figure.

## ★ Test results: expected vs actual (live runs, 2026-11-22)

Inputs: [tests/cases.live.json](tests/cases.live.json). Run with `--client demo_3pl`, whose records file [tests/client_records.demo.json](tests/client_records.demo.json) is a labelled **demo stand-in** until the kickoff kit's client records arrive. Full cases: [tests/cases.md](tests/cases.md).

| # | Case (live data) | Expected | Actual | |
|---|---|---|---|---|
| T1 | Delhivery, delhivery.com | CLEARED | **CLEARED** in three separate live runs: a clean run on a fresh database (8.43 credits, 256 s, "No adverse media about Mohit Tandon or Delhivery in 10 search results") and **both kill-drill batches** ([docs/kill_drill_results.md](docs/kill_drill_results.md)), including the one that was killed and resumed. In `verity_cases.db` (run 1) the same run was re-run 3× while rules were being fixed. Its work time adds up across re-runs, so it hit the 300 s ceiling and shows **held** (`time ceiling: 302s used of 300s`). | ✅ |
| T2 | Shadowfax, shadowfax.in, director "Abhishek Bansal" | CLEARED, or HOLD if a namesake can't be cleared | **CLEARED**: director confirmed, active, news screen verified | ✅ |
| T3 | "Blue Dart Express" on a made-up look-alike domain | HOLD FOR REVIEW | **HOLD**: the domain doesn't resolve, the name has 5 possible companies, so a person picks before the look-alike check runs | ✅ |
| T4 | Made-up "Blue Banyan Haulage" | CANNOT VERIFY | **CANNOT VERIFY**: "company could not be resolved from the name or website given" | ✅ |
| T5 | "Shree Logistics", name only | A person picks the company | **HOLD** (`awaiting_candidate`): 2 possible companies | ✅ |
| T6 | TCI Express (in the client records) | HOLD, exact duplicate | **HOLD**, rule `1_exact_duplicate`: "Already a client vendor: TCI Express Limited (tciexpress.in)". Its news search also timed out (`unknown`); the duplicate rule decides first either way, and the API refuses to clear it. | ✅ |
| T7 | Porter, claims 2001 | HOLD (claimed_age_mismatch) | **HOLD**, rule `4_needs_review`: "Website history year 2001 compared with verified founding 2014" (hard). The label says "website", but the 2001 claim came from the client's request (`claimed_year`, stored as a client-request source). The news screen was verified: no adverse media in 9 results. | ✅ |

**Wrong answers found on live data, and fixed by making the rules more cautious (no special cases):**
- **T7 first came out as SUSPECTED FRONT.** The "director" picked had the title *"Founder's Office"*, and their student-society and YouTube roles counted as 5 "current roles", which tripped the nominee pattern. Now leaders are matched on whole-word titles, excluding office, assistant and intern roles, and the nominee pattern counts only directorship-type roles, not advisor, investor or member roles.
- **T4 first waited for a candidate pick.** The only matches were 0.6-confidence fuzzy hits like "Blue Banyan Yoga". Now matches below `resolve_candidate_min_confidence` (0.7) are shown as weak matches, never offered as the company.
- **T1 and T2 first held on a news search timeout.** Unknown is never treated as clean, so they had to hold. Web search now has a 40 s timeout, and the per-run web budget counts only answered calls.
- **News screen:** a customer's forum complaint would HOLD every large carrier, so adverse media now means news sources only (`rules.media_sources`).

## Hour-3 requirement change

Not received in writing by the team at the time of freeze.

## Demo video

Demo video: <link>

## Approaches considered

1. **One LLM agent with tools:** flexible, but not reproducible and open to prompt injection from vendor websites. Rejected.
2. **A fixed checkpointed pipeline, rules in config, the LLM only for extraction and writing:** chosen. It's explainable, gives the same verdict for the same evidence, and survives restarts.
3. **An LLM planner choosing which checks to run:** future work, to save credits on obvious cases.

## Known limits

- **Kickoff formats:** the kickoff kit's input and output formats and the real client records are not in the repo yet. The mappings are config-only and temporary.
- **Honest `.in`/`.com` pair:** if Crustdata neither lists nor resolves the `.in` domain, the vendor gets one hard look-alike flag. That means HOLD, never SUSPECTED FRONT.
- **Namesake clearing:** clearing needs a contradicting fact. Snippets rarely state age or employer, so most same-name stories stay `unresolved` and go to a person.
- **Copied-site:** different hosts are treated as different businesses, because shared ownership isn't resolved. Pages without 12–30-word sentences can't be checked, which gives `unknown`; this check is not required for clearing.
- **Rupee costs:** rupee figures are assumptions until the rate per credit is confirmed.
- **Kill timing:** a call that is in flight at the exact moment of a kill is made again after the restart. Finished calls never are.

## Next steps

Watcher-based re-screening of approved vendors, MCA/GST registry as a second identity source, batch onboarding, a deletion job for retention, and per-client billing using `client_id`, which is already on every run.

## Setup and run

```sh
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt    # macOS/Linux: .venv/bin/pip
cp .env.example .env        # CRUSTDATA_API_KEY, LLM_API_KEY (Anthropic), CRUSTDATA_WEB_FETCH_ENDPOINT=/web/enrich/live
.venv/Scripts/python -m uvicorn backend.main:app --port 8000
cd frontend && npm install && NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev    # http://localhost:3000
```

- **Batch:** `.venv/Scripts/python -m backend.cli --input tests/cases.live.json --output results.json --parallel 2 --client demo_3pl`
- **Kill drill:** `.venv/Scripts/python scripts/kill_drill.py server --kill-at media` and `... cli`
- **Tests (offline, no paid calls):** `.venv/Scripts/python -m pytest -q backend`
- **Frontend checks:** `npm run build` (includes type check and lint)
- **Environment variables:** `CRUSTDATA_API_KEY`, `LLM_API_KEY` or `ANTHROPIC_API_KEY`, `CRUSTDATA_WEB_FETCH_ENDPOINT`, `VERITY_DB_PATH`, `VERITY_LOG_PATH`, `NEXT_PUBLIC_API_URL`. Never commit `.env`.

## ★ Open-source credits and team

- **Backend:** FastAPI, Uvicorn, httpx, RapidFuzz, PyYAML, Pydantic, python-dotenv, jsonschema, Anthropic SDK, pytest.
- **Frontend:** Next.js, React, TypeScript, Tailwind CSS, PostCSS, Autoprefixer, ESLint.
- **Team:**
  - Soumyajit (Lead): engine, API, DB, verdict rules, duplicate/look-alike, CLI, intake, events/stats, kill drill. Also completed Member B's data layer and the live web adapters.
  - Member C (Abhipsa Parida): web retrieval, LLM helper, media/namesake scoring, copied-site, timeline, explanation.
  - Member D (Raviuday): frontend, test cases, README and diagram first drafts, demo script.

Repository history starts at the kickoff commit; nothing was written beforehand.
