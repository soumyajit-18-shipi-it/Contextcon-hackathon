"""Our results -> the kickoff output format. The field list lives in config.yaml -> output_fields.

Each entry is  kickoff_field: <where the value comes from>
  "verdict.verdict"    a dotted path into {input, verdict, answers, run}
  "fn:status_text"     a small named function below (for values that need formatting)
Adding an output field = one config line, plus (only if it needs formatting) one function in COMPUTED.
"""

STATUS_TEXT = {
    "awaiting_approval": "held for approval", "done": "decided", "held": "held (limit reached or credits)",
    "awaiting_candidate": "waiting for a person to pick the company", "awaiting_input": "waiting for missing input",
    "failed": "failed", "queued": "queued", "running": "running",
}


def _path(data: dict, path: str):
    value = data
    for part in path.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def status_text(data):
    run = data.get("run") or {}
    decision = (run.get("status_reason") or "") if run.get("status") == "done" else ""
    return f"{STATUS_TEXT.get(run.get('status'), run.get('status'))}{': ' + decision if decision else ''}"


def sources_text(data):
    """One line per verified claim: what it says and exactly where it came from."""
    return [f"[#{s['evidence_id']}] {s['check']}: source {s['source_id']}, "
            f"{s.get('field_path') or s.get('passage')}, record date {s.get('record_date') or 'n/a'}"
            for s in (data.get("answers") or {}).get("sources", [])]


def cannot_verify_text(data):
    return [f"{c['check']}: {c['missing']}" for c in (data.get("answers") or {}).get("cannot_verify", [])]


def answer_text(key):
    return lambda data: ((data.get("answers") or {}).get(key) or {}).get("text")


COMPUTED = {
    "status_text": status_text,
    "sources_text": sources_text,
    "cannot_verify_text": cannot_verify_text,
    "who_runs_it": answer_text("who_runs_it"),
    "how_long_it_has_existed": answer_text("how_long_it_has_existed"),
    "is_it_trading": answer_text("is_it_trading"),
    "what_looks_off": answer_text("what_looks_off"),
}


def build_output(data: dict, output_fields: dict) -> dict:
    out = {}
    for kickoff_field, source in output_fields.items():
        if isinstance(source, str) and source.startswith("fn:"):
            out[kickoff_field] = COMPUTED[source[3:]](data)
        else:
            out[kickoff_field] = _path(data, source)
    return out
