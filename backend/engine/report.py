"""Report step: the 4 answers, a markdown report and the kickoff-format output.

Every answer only repeats evidence items and cites their ids. No new claims are made here.
"""
import importlib

from backend import db
from backend.engine import stubs

ACTIVITY = ["headcount_present", "headcount_trend", "hiring_activity", "web_traffic"]


def _load_build_output():
    """B owns the mapping to the kickoff format; use the stub until backend/data/output_map.py exists."""
    try:
        output_map = importlib.import_module("backend.data.output_map")
    except ModuleNotFoundError as e:
        if e.name != "backend.data.output_map":   # the file exists but is broken: show that error
            raise
        return stubs.build_output
    return getattr(output_map, "build_output", stubs.build_output)


def _answer(items, empty_text):
    """Join the claims of the given evidence items, citing their ids."""
    if not items:
        return {"text": empty_text, "evidence_ids": []}
    text = "; ".join(f"{e['claim']}: {e['value']} [#{e['id']}]" for e in items)
    return {"text": text, "evidence_ids": [e["id"] for e in items]}


def build_answers(evidence: list[dict]) -> dict:
    verified = [e for e in evidence if e["status"] == "verified"]
    return {
        "who_runs_it": _answer([e for e in verified if e["check"] == "director_current_role"],
                               "I can't verify who runs it."),
        "how_long_it_has_existed": _answer([e for e in verified if e["check"] == "founded_year"],
                                           "I can't verify when it was founded."),
        "is_it_trading": _answer([e for e in verified if e["check"] in ACTIVITY and e["flag"] == "none"],
                                 "I can't verify that it is trading."),
        "what_looks_off": _answer([e for e in evidence if e["flag"] in ("hard", "soft")], "Nothing flagged."),
        "cannot_verify": [{"check": e["check"], "missing": e["missing"], "evidence_id": e["id"]}
                          for e in evidence if e["status"] in ("cant_verify", "unknown")],
        "sources": [{"evidence_id": e["id"], "check": e["check"], "source_id": e["source_id"],
                     "field_path": e["field_path"], "passage": e["passage"], "record_date": e["record_date"]}
                    for e in verified],
    }


def build_report_md(run: dict, verdict: dict, answers: dict, explanation, stub_steps: list[str]) -> str:
    lines = [f"# Vendor check: {run['input'].get('name')}", "",
             f"**Verdict: {verdict['verdict']}** (rule `{verdict['rule']}`)", ""]
    lines += [f"- {r}" for r in verdict["reasons"]]
    if stub_steps:
        lines += ["", f"> Not yet implemented (stubbed, nothing checked): {', '.join(stub_steps)}"]
    lines += ["", "## Answers"]
    for key in ["who_runs_it", "how_long_it_has_existed", "is_it_trading", "what_looks_off"]:
        lines.append(f"- **{key.replace('_', ' ').capitalize()}:** {answers[key]['text']}")
    if answers["cannot_verify"]:
        lines += ["", "## I can't verify"]
        lines += [f"- {c['check']}: {c['missing']} [#{c['evidence_id']}]" for c in answers["cannot_verify"]]
    if explanation:
        lines += ["", "## Explanation", str(explanation)]
    lines += ["", "## Sources"]
    lines += [f"- [#{s['evidence_id']}] {s['check']}: source {s['source_id']}, "
              f"{s['field_path'] or s['passage']}, record date {s['record_date']}" for s in answers["sources"]]
    return "\n".join(lines)


async def step_report(ctx):
    run_id = ctx["run_id"]
    run = db.get_run(run_id)
    evidence = db.get_evidence(run_id)
    verdict = ctx["outputs"]["verdict"]
    explanation = (ctx["outputs"].get("explain") or {}).get("explanation")
    stub_steps = [name for name, out in ctx["outputs"].items() if out.get("stub")]

    answers = build_answers(evidence)
    report_md = build_report_md(run, verdict, answers, explanation, stub_steps)
    output = _load_build_output()(
        {"input": run["input"], "verdict": verdict, "answers": answers, "run": run},
        ctx["config"]["output_fields"],
    )
    db.save_verdict(run_id, verdict["verdict"], verdict, answers, explanation, report_md, output)
    return {"verdict": verdict["verdict"], "stub_steps": stub_steps, "output": output}
