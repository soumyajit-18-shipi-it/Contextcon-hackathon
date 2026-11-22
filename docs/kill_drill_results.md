# Kill drill results (2026-11-22, live Crustdata + Anthropic)

Script: [scripts/kill_drill.py](../scripts/kill_drill.py). The kill is a hard kill (TerminateProcess on Windows, the equivalent of `kill -9`), so no cleanup code runs.

## 1. API server, killed during the news screen (`--kill-at media`): **PASS**

```
[16:19:18] starting server
[16:19:27] run #1 submitted (Delhivery); waiting for the 'media' step to record a call
[16:22:11] KILLED the server during 'media' (last recorded call: ledger #10)
[16:22:11] run #1 status in the database right after the kill: running
[16:22:11] restarting server (it re-queues runs left 'running' and resumes from the last checkpoint)

================ LEDGER for run 1 ================
  #1   BEFORE kill   crustdata /company/identify    credits=0.2   http=200
  #2   BEFORE kill   crustdata /company/identify    credits=0.0   http=429
  #3   BEFORE kill   crustdata /company/identify    credits=0.2   http=200
  #4   BEFORE kill   crustdata /company/enrich      credits=2.0   http=200
  #5   BEFORE kill   crustdata /person/enrich       credits=1.0   http=200
  #6   BEFORE kill   crustdata /person/enrich       credits=1.0   http=200
  #7   BEFORE kill   crustdata /web/enrich/live     credits=1.0   http=200
  #8   BEFORE kill   crustdata /web/enrich/live     credits=1.0   http=200
  #9   BEFORE kill   crustdata /job/search          credits=0.03  http=200
  #10  BEFORE kill   crustdata /web/search/live     credits=0.0   http=None
  #11  AFTER restart crustdata /web/search/live     credits=0.0   http=None
  #12  AFTER restart crustdata /web/search/live     credits=0.0   http=None
  #13  AFTER restart crustdata /web/search/live     credits=1.0   http=200
  #14  AFTER restart crustdata /web/search/live     credits=0.0   http=None
  #15  AFTER restart crustdata /web/search/live     credits=1.0   http=200
  #16  AFTER restart llm       claude-haiku-5-5     credits=0.0   http=200
  #17  AFTER restart llm       claude-haiku-5-5     credits=0.0   http=200
  #18  AFTER restart llm       claude-haiku-5-5     credits=0.0   http=200
  #19  AFTER restart llm       claude-haiku-5-5     credits=0.0   http=200
  total: 19 calls, 8.43 credits

================ REPEAT CHECK ================
  repeated calls: NONE
  resume events: ['resumed_after_restart', 'run_resumed']
  final status: awaiting_approval (report ready, waiting for a person to clear or reject)

================ APPROVE TWICE ================
  first: HTTP 200   second: HTTP 409 (expect 200 then 409)
[16:23:56] PASS
```

What this shows:
- **The kill:** right after the kill, the run is still `running` in the database. On restart the server logs `resumed_after_restart` and the run continues from its last checkpoint (`run_resumed`).
- **No repeated calls:** every call that finished before the kill (#1–#9: identify, enrich, person enrich, site fetch, job search) was **not made again**. The repeat check (same endpoint and request answered twice) found none. Rows #11–#15 are the news searches: the one in flight at the kill (#10) had timed out without an answer, so it was retried. That is the documented limit: only finished calls are cached.
- **Rate limiting:** a 429 on identify (#2) was handled by waiting for `x-ratelimit-reset` and retrying.
- **Approval exactly once:** the first approval got HTTP 200, the second got HTTP 409.

## 2. Batch CLI, killed mid-batch (`cli --kill-at director`): **PASS**

```
[17:07:04] starting CLI batch: drill_cases.json
[17:08:48] KILLED the CLI mid-batch (run 2 in 'director', last recorded call: ledger #18)
[17:08:48] runs in the database after the kill: 2. Re-running the SAME command.
resuming interrupted runs: [2]
2 cases -> runs [1, 2]
[drill-1] run #1: CLEARED (awaiting_approval)
[drill-2] run #2: HOLD FOR REVIEW (awaiting_approval)
wrote C:\Users\soumy\OneDrive - BIRLA INSTITUTE OF TECHNOLOGY and SCIENCE\Desktop\Contextcon-hackathon\logs\drill_results.json
  runs before re-run: 2, after: 2 (must be equal: nothing duplicated)
================ LEDGER for run 1 ================
  #1   BEFORE kill   crustdata /company/identify    credits=0.2   http=200
  #2   BEFORE kill   crustdata /company/identify    credits=0.2   http=200
  #3   BEFORE kill   crustdata /company/enrich      credits=2.0   http=200
  #4   BEFORE kill   crustdata /person/enrich       credits=1.0   http=200
  #5   BEFORE kill   crustdata /person/enrich       credits=1.0   http=200
  #6   BEFORE kill   crustdata /web/enrich/live     credits=1.0   http=200
  #7   BEFORE kill   crustdata /web/enrich/live     credits=1.0   http=200
  #8   BEFORE kill   crustdata /job/search          credits=0.03  http=200
  #9   BEFORE kill   crustdata /web/search/live     credits=1.0   http=200
  #10  BEFORE kill   crustdata /web/search/live     credits=1.0   http=200
  #11  BEFORE kill   llm       claude-haiku-5-5     credits=0.0   http=200
  #12  BEFORE kill   llm       claude-haiku-5-5     credits=0.0   http=200
  #13  BEFORE kill   llm       claude-haiku-5-5     credits=0.0   http=200
  #14  BEFORE kill   llm       claude-haiku-5-5     credits=0.0   http=200
  total: 14 calls, 8.43 credits
================ REPEAT CHECK ================
  repeated calls: NONE
  resume events: []
  final status: awaiting_approval (report ready, waiting for a person to clear or reject)
================ LEDGER for run 2 ================
  #15  BEFORE kill   crustdata /company/identify    credits=0.2   http=200
  #16  BEFORE kill   crustdata /company/identify    credits=0.2   http=200
  #17  BEFORE kill   crustdata /company/enrich      credits=2.0   http=200
  #18  BEFORE kill   crustdata /person/enrich       credits=1.0   http=200
  #19  AFTER restart crustdata /person/enrich       credits=1.0   http=200
  #20  AFTER restart crustdata /web/enrich/live     credits=1.0   http=200
  #21  AFTER restart crustdata /web/enrich/live     credits=1.0   http=200
  #22  AFTER restart crustdata /job/search          credits=0.03  http=200
  #23  AFTER restart crustdata /web/search/live     credits=0.0   http=200
  #24  AFTER restart crustdata /web/search/live     credits=1.0   http=200
  #25  AFTER restart llm       claude-haiku-5-5     credits=0.0   http=200
  total: 11 calls, 7.43 credits
================ REPEAT CHECK ================
  repeated calls: NONE
  resume events: ['resumed_after_restart', 'run_resumed']
  final status: awaiting_approval (report ready, waiting for a person to clear or reject)
  results file: C:\Users\soumy\OneDrive - BIRLA INSTITUTE OF TECHNOLOGY and SCIENCE\Desktop\Contextcon-hackathon\logs\drill_results.json
[17:09:59] PASS
```

What this shows:
- **The kill:** the CLI process was hard-killed while run 2 was in the `director` step, right after its first Person Enrich call (#18). Run 1 had already finished.
- **The re-run:** re-running the **same command** resumed only run 2 (`resuming interrupted runs: [2]`), and the run count stayed at 2, so nothing was duplicated.
- **No repeated calls:** the repeat check is NONE for both runs. The first director lookup came from the per-run cache. The Person Enrich after the restart (#19) is the *second* director, a different request.
- **Results:** Delhivery CLEARED and Blue Dart held for review (`logs/drill_results.json`).
- **Earlier attempts:** two earlier live attempts didn't reach a kill point. In the first, Crustdata timeouts held both runs at 16:39. In the second, the single-call `company` step finished between polls. The automated test `backend/engine/tests/test_cli.py::test_kill_mid_batch_then_rerun_resumes` covers the same path offline.

## How to repeat on stage
1. `.venv/Scripts/python -m uvicorn backend.main:app --port 8000` and submit a vendor in the UI.
2. While the run page shows `director` or `media`, close the server window (or end the task).
3. Start the server again. The console prints `resuming interrupted runs: [id]`, and the run page carries on.
4. Show `GET /ledger?run_id=<id>`: each finished call appears once. Show `GET /runs/<id>/events`: `resumed_after_restart` → `run_resumed` with `steps_already_done`.
