"""Kill drill: prove a run survives a hard kill and repeats no paid call.

    .venv/Scripts/python scripts/kill_drill.py server            # API: kill the server mid-run, restart, resume
    .venv/Scripts/python scripts/kill_drill.py server --kill-at media
    .venv/Scripts/python scripts/kill_drill.py cli               # CLI: kill mid-batch, re-run the same command

Each drill uses a fresh database (drill_server.db / drill_cli.db, git-ignored) and makes REAL Crustdata
calls: about 6-7 credits per company. The kill is a hard kill (TerminateProcess on Windows = kill -9):
no cleanup code runs, exactly like pulling the plug.

What it prints at the end:
  - every ledger row of the run, marked BEFORE / AFTER the kill
  - the repeat check: the same (endpoint, request) answered twice for one run = a repeated call
  - the resume events from the event log, and (server drill) a second approval refused with 409
Honest limit: a call that is in flight at the exact moment of the kill never got its answer stored,
so it is made again after the restart. The drill kills right AFTER a call is recorded to show the normal case.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PY = sys.executable
TERMINAL = {"awaiting_approval", "done", "held", "failed", "awaiting_candidate", "awaiting_input"}


def say(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def fresh_env(db_name: str) -> dict:
    db_path = ROOT / db_name
    for suffix in ("", "-wal", "-shm"):
        Path(f"{db_path}{suffix}").unlink(missing_ok=True)
    env = {**os.environ, "VERITY_DB_PATH": str(db_path), "VERITY_LOG_PATH": str(ROOT / "logs" / "drill.jsonl")}
    os.environ.update(env)          # so `from backend import db` below reads the same database
    return env


def ledger_rows(run_id):
    from backend import db
    return db.get_ledger(run_id)


def repeated_calls(run_id):
    """Same endpoint + same request answered (ok/empty) more than once for this run."""
    from backend import db
    with db.connect() as conn:
        return [dict(r) for r in conn.execute(
            """SELECT endpoint, request_json, COUNT(*) AS times FROM sources
               WHERE run_id = ? AND kind = 'crustdata' AND status IN ('ok', 'empty')
               GROUP BY endpoint, request_json HAVING COUNT(*) > 1""", (run_id,))]


def report(run_id, killed_after_id):
    from backend import db
    print("\n================ LEDGER for run", run_id, "================")
    for row in ledger_rows(run_id):
        when = "BEFORE kill" if row["id"] <= killed_after_id else "AFTER restart"
        print(f"  #{row['id']:<3} {when:13} {row['provider']:9} {str(row['endpoint_or_model']):20} "
              f"credits={row['credits']:<5} http={row['http_status']}")
    totals = db.ledger_summary(run_id)
    print(f"  total: {totals['calls']} calls, {totals['credits']} credits")
    repeats = repeated_calls(run_id)
    print("\n================ REPEAT CHECK ================")
    print("  repeated calls: NONE" if not repeats else f"  REPEATED: {json.dumps(repeats, indent=1)}")
    resume = [e["event"] for e in db.get_events(run_id) if e["event"] in ("resumed_after_restart", "run_resumed")]
    print("  resume events:", resume)
    run = db.get_run(run_id)
    print(f"  final status: {run['status']} ({run['status_reason']})")
    return not repeats


def wait_until(predicate, timeout_s, what):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            result = predicate()
        except Exception:      # e.g. the fresh database has no tables yet: not ready
            result = None
        if result:
            return result
        time.sleep(0.25)
    raise SystemExit(f"timed out waiting for: {what}")


# The paid call each step makes, so we can kill right after the step's first call is recorded.
STEP_ENDPOINT = {"resolve": "/company/identify", "company": "/company/enrich", "director": "/person/enrich",
                 "site": "/web/enrich/live", "core_checks": "/job/search", "media": "/web/search/live"}


def target_call_recorded(run_id, step):
    """The ledger id of the step's first recorded call, once the step is running; else None."""
    from backend import db
    run = db.get_run(run_id)
    if not run or run["current_step"] != step or run["status"] != "running":
        return None
    with db.connect() as conn:
        return conn.execute("SELECT MAX(id) FROM ledger WHERE run_id = ? AND endpoint_or_model = ?",
                            (run_id, STEP_ENDPOINT[step])).fetchone()[0]


# ---------------- server drill ----------------

def start_server(env, port):
    log = open(ROOT / "logs" / "drill_server.log", "a", encoding="utf-8")
    proc = subprocess.Popen([PY, "-m", "uvicorn", "backend.main:app", "--port", str(port)], cwd=ROOT, env=env,
                            stdout=log, stderr=subprocess.STDOUT)
    wait_until(lambda: _up(port), 30, "server to start")
    return proc


def _up(port):
    try:
        return httpx.get(f"http://127.0.0.1:{port}/stats", timeout=1).status_code == 200
    except httpx.HTTPError:
        return False


def server_drill(args):
    env = fresh_env("drill_server.db")
    (ROOT / "logs").mkdir(exist_ok=True)
    base = f"http://127.0.0.1:{args.port}"
    say("starting server")
    server = start_server(env, args.port)
    run_id = httpx.post(f"{base}/runs", json={"name": args.name, "website": args.website}).json()["id"]
    say(f"run #{run_id} submitted ({args.name}); waiting for the '{args.kill_at}' step to record a call")
    last_call = wait_until(lambda: target_call_recorded(run_id, args.kill_at), args.timeout, f"{args.kill_at} step")
    server.kill()                       # hard kill: no shutdown code runs
    server.wait()
    say(f"KILLED the server during '{args.kill_at}' (last recorded call: ledger #{last_call})")
    from backend import db
    say(f"run #{run_id} status in the database right after the kill: {db.get_run(run_id)['status']}")

    say("restarting server (it re-queues runs left 'running' and resumes from the last checkpoint)")
    server = start_server(env, args.port)
    wait_until(lambda: db.get_run(run_id)["status"] in TERMINAL, args.timeout, "run to finish")
    ok = report(run_id, last_call)

    print("\n================ APPROVE TWICE ================")
    body = {"decision": "reject", "reason": "kill drill test decision", "user": "drill"}
    first = httpx.post(f"{base}/runs/{run_id}/approve", json=body)
    second = httpx.post(f"{base}/runs/{run_id}/approve", json={**body, "decision": "clear"})
    print(f"  first: HTTP {first.status_code}   second: HTTP {second.status_code} (expect 200 then 409)")
    server.kill()
    say("PASS" if ok and second.status_code == 409 else "CHECK THE OUTPUT ABOVE")


# ---------------- CLI drill ----------------

def cli_drill(args):
    env = fresh_env("drill_cli.db")
    (ROOT / "logs").mkdir(exist_ok=True)
    cases = ROOT / "scripts" / "drill_cases.json"
    out = ROOT / "logs" / "drill_results.json"
    cmd = [PY, "-m", "backend.cli", "--input", str(cases), "--output", str(out)]
    say(f"starting CLI batch: {cases.name}")
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env)
    from backend import db
    # Kill once run 1 is finished and run 2 has recorded a call in the target step.
    last_call = wait_until(lambda: db.get_run(1) and db.get_run(1)["status"] in TERMINAL and db.get_run(2)
                           and target_call_recorded(2, args.kill_at), args.timeout, "mid-batch point")
    proc.kill()
    proc.wait()
    say(f"KILLED the CLI mid-batch (run 2 in '{args.kill_at}', last recorded call: ledger #{last_call})")
    with db.connect() as conn:
        before = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    say(f"runs in the database after the kill: {before}. Re-running the SAME command.")
    subprocess.run(cmd, cwd=ROOT, env=env, check=True)
    with db.connect() as conn:
        after = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    print(f"\n  runs before re-run: {before}, after: {after} (must be equal: nothing duplicated)")
    ok = after == before
    for run_id in range(1, after + 1):
        ok = report(run_id, last_call) and ok
    print(f"\n  results file: {out}")
    say("PASS" if ok else "CHECK THE OUTPUT ABOVE")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=["server", "cli"])
    parser.add_argument("--kill-at", default="director", help="step to kill during (default: director)")
    parser.add_argument("--name", default="Delhivery")
    parser.add_argument("--website", default="https://www.delhivery.com")
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    server_drill(args) if args.mode == "server" else cli_drill(args)


if __name__ == "__main__":
    main()
