"""SQLite storage for Verity (WAL mode).

Exactly-once guarantees live in the schema:
  steps     UNIQUE(run_id, step_name)  -> a step has one row; re-running it overwrites, never duplicates
  approvals UNIQUE(run_id)             -> a second decision on the same run is rejected by the database
"""
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id     TEXT NOT NULL DEFAULT 'default',
    input_json    TEXT NOT NULL,
    input_hash    TEXT,
    status        TEXT NOT NULL,   -- queued|running|held|awaiting_candidate|awaiting_approval|done|failed
    status_reason TEXT,            -- why it is held / failed / waiting
    current_step  TEXT,
    duplicate_of  TEXT,            -- set by step_duplicate; blocks approving a known vendor again
    time_limit_s  REAL NOT NULL,
    credit_limit  REAL NOT NULL,
    cost_limit_inr REAL NOT NULL,
    credits_used  REAL NOT NULL DEFAULT 0,
    cost_inr      REAL NOT NULL DEFAULT 0,
    elapsed_s     REAL NOT NULL DEFAULT 0,  -- seconds spent working (not counting crash downtime)
    created_at    TEXT NOT NULL,
    started_at    TEXT,
    updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS steps (
    run_id      INTEGER NOT NULL,
    step_name   TEXT NOT NULL,
    status      TEXT NOT NULL,     -- running|done|skipped|failed
    output_json TEXT,
    attempts    INTEGER NOT NULL DEFAULT 0,
    updated_at  TEXT NOT NULL,
    UNIQUE(run_id, step_name)
);
CREATE TABLE IF NOT EXISTS sources (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER,
    kind         TEXT NOT NULL,    -- crustdata|web|client_record|...
    endpoint     TEXT,
    url          TEXT,
    request_json TEXT,
    raw_response TEXT,
    retrieved_at TEXT NOT NULL,
    record_date  TEXT,
    status       TEXT,             -- ok|empty|timeout|error|rate_limited|no_credits (API sources)
    http_status  INTEGER
);
CREATE TABLE IF NOT EXISTS evidence (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL,
    step_name   TEXT,
    "check"     TEXT NOT NULL,
    claim       TEXT,
    value       TEXT,
    source_id   INTEGER,
    field_path  TEXT,
    passage     TEXT,
    record_date TEXT,
    flag        TEXT NOT NULL DEFAULT 'none',   -- hard|soft|none
    status      TEXT NOT NULL,                  -- verified|cant_verify|unknown
    missing     TEXT
);
CREATE TABLE IF NOT EXISTS ledger (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id            INTEGER,
    provider          TEXT NOT NULL,
    endpoint_or_model TEXT,
    prompt_version    TEXT,
    credits           REAL DEFAULT 0,
    tokens_in         INTEGER DEFAULT 0,
    tokens_out        INTEGER DEFAULT 0,
    cost_inr          REAL DEFAULT 0,
    latency_ms        INTEGER,
    http_status       INTEGER,
    ts                TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS media_hits (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         INTEGER NOT NULL,
    url            TEXT,
    title          TEXT,
    extracted_json TEXT,
    match_score    REAL,
    label          TEXT,   -- match|namesake_cleared|unresolved
    reason         TEXT,
    source_id      INTEGER
);
CREATE TABLE IF NOT EXISTS client_vendors (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id  TEXT NOT NULL DEFAULT 'default',
    name       TEXT,
    domain     TEXT,
    director   TEXT,
    gstin      TEXT,
    other_json TEXT
);
CREATE TABLE IF NOT EXISTS personal_data_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id    INTEGER NOT NULL,
    person    TEXT,
    field     TEXT,
    source_id INTEGER,
    purpose   TEXT
);
CREATE TABLE IF NOT EXISTS approvals (
    run_id   INTEGER NOT NULL UNIQUE,
    decision TEXT NOT NULL,   -- clear|reject
    reason   TEXT NOT NULL,
    user     TEXT NOT NULL,
    ts       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER,
    ts          TEXT NOT NULL,
    event       TEXT NOT NULL,   -- step_start|step_end|step_error|checkpoint|status|ceiling|approval|run_created|...
    step        TEXT,
    detail_json TEXT
);
CREATE TABLE IF NOT EXISTS verdicts (
    run_id       INTEGER NOT NULL UNIQUE,
    verdict      TEXT,
    flags_json   TEXT,
    answers_json TEXT,
    explanation  TEXT,
    report_md    TEXT,
    output_json  TEXT
);
"""

EVIDENCE_STATUSES = {"verified", "cant_verify", "unknown"}
EVIDENCE_FLAGS = {"hard", "soft", "none"}


# ---------- connection ----------

def db_path() -> str:
    return os.environ.get("VERITY_DB_PATH", "verity.db")


@contextmanager
def connect():
    """One short-lived connection per call: commit on success, roll back on error."""
    conn = sqlite3.connect(db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")   # readers never block the writer
        conn.executescript(SCHEMA)
        # Databases created before these columns existed get them added (CREATE IF NOT EXISTS won't).
        existing = {r["name"] for r in conn.execute("PRAGMA table_info(sources)")}
        for column, kind in (("status", "TEXT"), ("http_status", "INTEGER")):
            if column not in existing:
                conn.execute(f"ALTER TABLE sources ADD COLUMN {column} {kind}")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _loads(text):
    return json.loads(text) if text else None


def _row(row):
    return dict(row) if row else None


# ---------- runs ----------

def create_run(input_data: dict, limits: dict, client_id="default", input_hash=None) -> int:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO runs (client_id, input_json, input_hash, status, time_limit_s, credit_limit,
                                 cost_limit_inr, created_at, updated_at)
               VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?)""",
            (client_id, json.dumps(input_data), input_hash, limits["time_limit_s"],
             limits["credit_limit"], limits["cost_limit_inr"], now(), now()),
        )
        return cur.lastrowid


def get_run(run_id: int) -> dict | None:
    with connect() as conn:
        run = _row(conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone())
    if run:
        run["input"] = _loads(run.pop("input_json"))
    return run


def list_runs() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT r.id, r.input_json, r.status, r.status_reason, r.created_at, r.updated_at,
                      r.credits_used, r.cost_inr, r.duplicate_of, v.verdict, a.decision
               FROM runs r
               LEFT JOIN verdicts v ON v.run_id = r.id
               LEFT JOIN approvals a ON a.run_id = r.id
               ORDER BY r.id DESC"""
        ).fetchall()
    runs = []
    for row in rows:
        run = dict(row)
        run["input"] = _loads(run.pop("input_json"))
        match = re.match(r"run #(\d+)", run["duplicate_of"] or "")   # repeat submission -> link to the earlier run
        run["duplicate_run_id"] = int(match.group(1)) if match else None
        runs.append(run)
    return runs


def set_run_status(run_id: int, status: str, reason: str | None = None):
    with connect() as conn:
        conn.execute(
            "UPDATE runs SET status = ?, status_reason = ?, updated_at = ? WHERE id = ?",
            (status, reason, now(), run_id),
        )
    log_event(run_id, "status", status=status, reason=reason)   # every status change is in the event log


def mark_run_started(run_id: int, step_name: str):
    """Set status running + current step; record started_at the first time only."""
    with connect() as conn:
        conn.execute(
            """UPDATE runs SET status = 'running', status_reason = NULL, current_step = ?,
                      started_at = COALESCE(started_at, ?), updated_at = ? WHERE id = ?""",
            (step_name, now(), now(), run_id),
        )


def update_run_input(run_id: int, input_data: dict):
    with connect() as conn:
        conn.execute("UPDATE runs SET input_json = ?, updated_at = ? WHERE id = ?",
                     (json.dumps(input_data), now(), run_id))


def delete_step(run_id: int, step_name: str):
    """Forget a step's checkpoint so it runs again (used after a person supplies missing input)."""
    with connect() as conn:
        conn.execute("DELETE FROM steps WHERE run_id = ? AND step_name = ?", (run_id, step_name))


def set_run_limits(run_id: int, limits: dict):
    """Apply the current config's ceilings to this run (config is re-read every run)."""
    with connect() as conn:
        conn.execute(
            "UPDATE runs SET time_limit_s = ?, credit_limit = ?, cost_limit_inr = ? WHERE id = ?",
            (limits["time_limit_s"], limits["credit_limit"], limits["cost_limit_inr"], run_id),
        )


def add_elapsed(run_id: int, seconds: float):
    with connect() as conn:
        conn.execute("UPDATE runs SET elapsed_s = elapsed_s + ? WHERE id = ?", (seconds, run_id))


def set_duplicate_of(run_id: int, duplicate_of: str | None):
    with connect() as conn:
        conn.execute("UPDATE runs SET duplicate_of = ? WHERE id = ?", (duplicate_of, run_id))


def requeue_interrupted_runs() -> list[int]:
    """Crash recovery: a run still marked 'running' was interrupted -> back to 'queued'."""
    with connect() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM runs WHERE status = 'running'")]
        conn.execute(
            "UPDATE runs SET status = 'queued', status_reason = 'resumed after restart', updated_at = ? "
            "WHERE status = 'running'",
            (now(),),
        )
    for run_id in ids:
        log_event(run_id, "resumed_after_restart")
    return ids


def next_queued_run() -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT id FROM runs WHERE status = 'queued' ORDER BY id LIMIT 1").fetchone()
    return get_run(row["id"]) if row else None


def find_run_by_hash(input_hash: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT id FROM runs WHERE input_hash = ? ORDER BY id LIMIT 1",
                           (input_hash,)).fetchone()
    return get_run(row["id"]) if row else None


# ---------- steps (checkpoints) ----------

def start_step(run_id: int, step_name: str):
    """Mark a step running and count the attempt."""
    with connect() as conn:
        conn.execute(
            """INSERT INTO steps (run_id, step_name, status, attempts, updated_at)
               VALUES (?, ?, 'running', 1, ?)
               ON CONFLICT(run_id, step_name)
               DO UPDATE SET status = 'running', attempts = attempts + 1, updated_at = excluded.updated_at""",
            (run_id, step_name, now()),
        )


def finish_step(run_id: int, step_name: str, status: str, output: dict):
    """Checkpoint: save the step output AND its evidence / media hits / personal data
    in ONE transaction. Either all of it is saved or none of it, so a crash can never
    leave half a step behind, and a re-run never duplicates evidence."""
    with connect() as conn:
        conn.execute(
            """INSERT INTO steps (run_id, step_name, status, output_json, attempts, updated_at)
               VALUES (?, ?, ?, ?, 1, ?)
               ON CONFLICT(run_id, step_name)
               DO UPDATE SET status = excluded.status, output_json = excluded.output_json,
                             updated_at = excluded.updated_at""",
            (run_id, step_name, status, json.dumps(output, default=str), now()),
        )
        _insert_evidence(conn, run_id, step_name, output.get("evidence", []))
        _insert_media_hits(conn, run_id, output.get("media_hits", []))
        _insert_personal_data(conn, run_id, output.get("personal_data", []))


def get_steps(run_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT step_name, status, attempts, updated_at FROM steps WHERE run_id = ?", (run_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_step_outputs(run_id: int) -> dict:
    """{step_name: output} for every finished step (done, skipped or failed)."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT step_name, output_json FROM steps WHERE run_id = ? AND status IN ('done','skipped','failed')",
            (run_id,),
        ).fetchall()
    return {r["step_name"]: _loads(r["output_json"]) or {} for r in rows}


def update_step_output(run_id: int, step_name: str, output: dict):
    with connect() as conn:
        conn.execute(
            "UPDATE steps SET output_json = ?, updated_at = ? WHERE run_id = ? AND step_name = ?",
            (json.dumps(output, default=str), now(), run_id, step_name),
        )


# ---------- evidence ----------

def _clean_evidence(item: dict) -> dict:
    """Enforce the evidence contract. A 'verified' claim with no source is downgraded."""
    item = dict(item)
    if item.get("status") not in EVIDENCE_STATUSES:
        item["status"] = "unknown"
    if item.get("flag") not in EVIDENCE_FLAGS:
        item["flag"] = "none"
    has_pointer = item.get("field_path") or item.get("passage")
    if item["status"] == "verified" and (item.get("source_id") is None or not has_pointer):
        item["status"] = "cant_verify"
        item["missing"] = item.get("missing") or "no source attached to this claim"
    if item["status"] == "cant_verify" and not item.get("missing"):
        item["missing"] = "not stated by the step"
    return item


def _insert_evidence(conn, run_id: int, step_name: str, items: list[dict]):
    for raw in items:
        e = _clean_evidence(raw)
        conn.execute(
            """INSERT INTO evidence (run_id, step_name, "check", claim, value, source_id, field_path,
                                     passage, record_date, flag, status, missing)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, step_name, e.get("check"), e.get("claim"), json.dumps(e.get("value"), default=str),
             e.get("source_id"), e.get("field_path"), e.get("passage"), e.get("record_date"),
             e["flag"], e["status"], e.get("missing")),
        )


def get_evidence(run_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM evidence WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
    items = []
    for r in rows:
        e = dict(r)
        e["value"] = _loads(e["value"])
        items.append(e)
    return items


# ---------- media hits / personal data ----------

def _insert_media_hits(conn, run_id: int, hits: list[dict]):
    for h in hits:
        conn.execute(
            """INSERT INTO media_hits (run_id, url, title, extracted_json, match_score, label, reason, source_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, h.get("url"), h.get("title"), json.dumps(h.get("extracted"), default=str),
             h.get("match_score"), h.get("label"), h.get("reason"), h.get("source_id")),
        )


def get_media_hits(run_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM media_hits WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
    hits = []
    for r in rows:
        h = dict(r)
        h["extracted"] = _loads(h.pop("extracted_json"))
        hits.append(h)
    return hits


def _insert_personal_data(conn, run_id: int, rows: list[dict]):
    for p in rows:
        conn.execute(
            "INSERT INTO personal_data_log (run_id, person, field, source_id, purpose) VALUES (?, ?, ?, ?, ?)",
            (run_id, p.get("person"), p.get("field"), p.get("source_id"), p.get("purpose")),
        )


def get_personal_data(run_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM personal_data_log WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
    return [dict(r) for r in rows]


# ---------- sources / ledger (B writes these via their client; helpers for everyone) ----------

def add_source(run_id, kind, endpoint=None, url=None, request=None, raw_response=None, record_date=None,
               status=None, http_status=None) -> int:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO sources (run_id, kind, endpoint, url, request_json, raw_response, retrieved_at,
                                    record_date, status, http_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, kind, endpoint, url, json.dumps(request, sort_keys=True, default=str),
             raw_response if isinstance(raw_response, str) or raw_response is None
             else json.dumps(raw_response, default=str),
             now(), record_date, status, http_status),
        )
        return cur.lastrowid


def find_cached_source(run_id, endpoint, request_json) -> dict | None:
    """Crustdata per-run cache: this run already got an answer (ok or empty) for this exact request."""
    with connect() as conn:
        row = conn.execute(
            """SELECT id FROM sources WHERE run_id = ? AND endpoint = ? AND request_json = ?
               AND status IN ('ok', 'empty') ORDER BY id DESC LIMIT 1""",
            (run_id, endpoint, request_json),
        ).fetchone()
    return get_source(row["id"]) if row else None


def find_or_add_source(run_id, kind, url, raw_response, record_date=None) -> int:
    """For local records (client vendors, past runs): reuse this run's existing source row for the same
    url, so re-running a step after a crash doesn't pile up identical sources."""
    with connect() as conn:
        row = conn.execute("SELECT id FROM sources WHERE run_id = ? AND kind = ? AND url = ?",
                           (run_id, kind, url)).fetchone()
    if row:
        return row["id"]
    return add_source(run_id, kind, endpoint=kind, url=url, raw_response=raw_response, record_date=record_date)


def get_source(source_id: int) -> dict | None:
    with connect() as conn:
        src = _row(conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone())
    if src:
        src["request"] = _loads(src.pop("request_json"))
        try:
            src["raw_response"] = json.loads(src["raw_response"]) if src["raw_response"] else None
        except json.JSONDecodeError:
            pass   # web pages are stored as plain text
    return src


def get_ledger(run_id: int | None = None) -> list[dict]:
    with connect() as conn:
        if run_id is None:
            rows = conn.execute("SELECT * FROM ledger ORDER BY id DESC LIMIT 500").fetchall()
        else:
            rows = conn.execute("SELECT * FROM ledger WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
    return [dict(r) for r in rows]


def ledger_summary(run_id: int) -> dict:
    with connect() as conn:
        row = conn.execute(
            """SELECT COUNT(*) AS calls, COALESCE(SUM(credits), 0) AS credits,
                      COALESCE(SUM(cost_inr), 0) AS cost_inr,
                      COALESCE(SUM(tokens_in), 0) AS tokens_in, COALESCE(SUM(tokens_out), 0) AS tokens_out
               FROM ledger WHERE run_id = ?""",
            (run_id,),
        ).fetchone()
    return dict(row)


# ---------- client records ----------

def get_client_vendors(client_id="default") -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM client_vendors WHERE client_id = ?", (client_id,)).fetchall()
    return [dict(r) for r in rows]


# ---------- verdicts ----------

def save_verdict(run_id: int, verdict: str, flags: dict, answers: dict, explanation: str | None,
                 report_md: str, output: dict):
    """Upsert, so re-running the report step after a crash overwrites instead of duplicating."""
    with connect() as conn:
        conn.execute(
            """INSERT INTO verdicts (run_id, verdict, flags_json, answers_json, explanation, report_md, output_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(run_id) DO UPDATE SET verdict = excluded.verdict, flags_json = excluded.flags_json,
                   answers_json = excluded.answers_json, explanation = excluded.explanation,
                   report_md = excluded.report_md, output_json = excluded.output_json""",
            (run_id, verdict, json.dumps(flags, default=str), json.dumps(answers, default=str),
             explanation, report_md, json.dumps(output, default=str)),
        )


def get_verdict(run_id: int) -> dict | None:
    with connect() as conn:
        v = _row(conn.execute("SELECT * FROM verdicts WHERE run_id = ?", (run_id,)).fetchone())
    if v:
        v["flags"] = _loads(v.pop("flags_json"))
        v["answers"] = _loads(v.pop("answers_json"))
        v["output"] = _loads(v.pop("output_json"))
    return v


# ---------- stats (cost per check, for the finance numbers) ----------

MEASURED_STATUSES = ("awaiting_approval", "done", "held", "awaiting_candidate", "awaiting_input", "failed")


def run_stats() -> dict:
    """Average/max credits, rupees and seconds per check over runs that finished their work, + verdict counts."""
    marks = ",".join("?" * len(MEASURED_STATUSES))
    with connect() as conn:
        agg = conn.execute(
            f"""SELECT COUNT(*) AS runs,
                       AVG(credits_used) AS avg_credits, MAX(credits_used) AS max_credits,
                       AVG(cost_inr) AS avg_inr, MAX(cost_inr) AS max_inr,
                       AVG(elapsed_s) AS avg_seconds, MAX(elapsed_s) AS max_seconds
                FROM runs WHERE status IN ({marks})""", MEASURED_STATUSES).fetchone()
        verdicts = conn.execute("SELECT verdict, COUNT(*) AS n FROM verdicts GROUP BY verdict").fetchall()
        decisions = conn.execute("SELECT decision, COUNT(*) AS n FROM approvals GROUP BY decision").fetchall()
        statuses = conn.execute("SELECT status, COUNT(*) AS n FROM runs GROUP BY status").fetchall()
        llm = conn.execute("SELECT COUNT(*) AS calls, COALESCE(SUM(cost_inr), 0) AS inr FROM ledger "
                           "WHERE provider = 'llm'").fetchone()
    a = dict(agg)
    r = lambda x: round(x, 2) if x is not None else None   # noqa: E731
    return {
        "runs_measured": a["runs"],
        "credits_per_check": {"avg": r(a["avg_credits"]), "max": r(a["max_credits"])},
        "inr_per_check": {"avg": r(a["avg_inr"]), "max": r(a["max_inr"])},
        "seconds_per_check": {"avg": r(a["avg_seconds"]), "max": r(a["max_seconds"])},
        "llm": {"calls": llm["calls"], "inr_total": r(llm["inr"])},
        "verdicts": {row["verdict"]: row["n"] for row in verdicts},
        "decisions": {row["decision"]: row["n"] for row in decisions},
        "runs_by_status": {row["status"]: row["n"] for row in statuses},
    }


# ---------- event log (table + logs/runs.jsonl) ----------

def log_path() -> str:
    return os.environ.get("VERITY_LOG_PATH", "logs/runs.jsonl")


def log_event(run_id, event: str, step: str | None = None, **detail):
    """One structured event: a row in `events` and one JSON line in logs/runs.jsonl.
    Writing the log file can never break a run."""
    row = {"ts": now(), "run_id": run_id, "event": event, "step": step, **detail}
    with connect() as conn:
        conn.execute("INSERT INTO events (run_id, ts, event, step, detail_json) VALUES (?, ?, ?, ?, ?)",
                     (run_id, row["ts"], event, step, json.dumps(detail, default=str)))
    try:
        os.makedirs(os.path.dirname(log_path()) or ".", exist_ok=True)
        with open(log_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except OSError:
        pass


def get_events(run_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM events WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
    events = []
    for r in rows:
        e = dict(r)
        e["detail"] = _loads(e.pop("detail_json"))
        events.append(e)
    return events


# ---------- approvals (exactly once) ----------

def add_approval(run_id: int, decision: str, reason: str, user: str):
    """Raises sqlite3.IntegrityError if this run already has a decision (UNIQUE(run_id))."""
    with connect() as conn:
        conn.execute(
            "INSERT INTO approvals (run_id, decision, reason, user, ts) VALUES (?, ?, ?, ?, ?)",
            (run_id, decision, reason, user, now()),
        )
        conn.execute("UPDATE runs SET status = 'done', status_reason = ?, updated_at = ? WHERE id = ?",
                     (f"{decision} by {user}", now(), run_id))
    log_event(run_id, "approval", decision=decision, reason=reason, user=user)


def get_approval(run_id: int) -> dict | None:
    with connect() as conn:
        return _row(conn.execute("SELECT * FROM approvals WHERE run_id = ?", (run_id,)).fetchone())
