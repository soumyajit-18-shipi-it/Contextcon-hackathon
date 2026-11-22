"""Batch runner for test sets.

    python -m backend.cli --input cases.json --output results.json [--parallel 2]

Input file -> one run per case -> the same run engine as the API, in-process -> results file.
File shapes and field names come from config.yaml (batch_format, input_fields, output_fields).

Safe to kill and re-run: each case is stored with a hash of (case id + its input). Running the
same command again finds the same runs and resumes them from their last checkpoint, so nothing is
created twice and finished steps make no new API calls. Don't run the CLI and the API server
against the same database at the same time (set VERITY_DB_PATH to keep them apart).
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from backend import db
from backend.config import load_config
from backend.engine import orchestrator, stubs
from backend.web.anthropic_transport import configure_llm

FINISHED = {"awaiting_approval", "done", "held", "awaiting_candidate", "failed"}


# ---------- input ----------

def load_cases(path: str, cfg: dict) -> list[tuple[str, dict]]:
    """Read the input file -> [(case_id, our_input)] using batch_format + input_fields."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    fmt = cfg["batch_format"]
    cases = data if isinstance(data, list) else data[fmt["cases_key"]]
    result = []
    for i, case in enumerate(cases):
        case_id = str(case.get(fmt["case_id_field"]) or f"case-{i + 1}")
        our_input = {ours: case.get(theirs) for ours, theirs in cfg["input_fields"].items()}
        if not (our_input.get("name") or our_input.get("website") or our_input.get("request_text")):
            raise ValueError(f"case {case_id}: needs a vendor name, website or request text")
        result.append((case_id, our_input))
    return result


def case_hash(case_id: str, our_input: dict, client_id: str = "default") -> str:
    """Same case id + same input -> same hash -> same run on a re-run."""
    canonical = json.dumps({"client": client_id, "case_id": case_id, "input": our_input}, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def ensure_runs(cases: list[tuple[str, dict]], cfg: dict) -> list[tuple[str, int]]:
    """Find each case's existing run, or create it. Returns [(case_id, run_id)]."""
    pairs = []
    for case_id, our_input in cases:
        h = case_hash(case_id, our_input, cfg["client"]["id"])
        existing = db.find_run_by_hash(h)
        run_id = existing["id"] if existing else db.create_run(our_input, cfg["limits"], client_id=cfg["client"]["id"], input_hash=h)
        pairs.append((case_id, run_id))
    return pairs


# ---------- processing ----------

async def process_batch(run_ids: list[int], parallel: int, on_done=None):
    """Run this batch's queued runs, `parallel` at a time."""
    queue = asyncio.Queue()
    for run_id in run_ids:
        queue.put_nowait(run_id)

    async def worker():
        while not queue.empty():
            run_id = queue.get_nowait()
            if db.get_run(run_id)["status"] == "queued":
                await orchestrator.process_run_safe(run_id)
            if on_done:
                on_done(run_id)

    await asyncio.gather(*(worker() for _ in range(max(1, parallel))))


# ---------- output ----------

def verdict_for(run: dict) -> dict:
    """The verdict to report. A run that stopped early (ceiling, candidate pick, error) has no
    verdict of its own, and we never guess, so it is reported as HOLD FOR REVIEW with the reason."""
    saved = db.get_verdict(run["id"])
    if saved:
        return saved["flags"]
    return {"verdict": "HOLD FOR REVIEW", "rule": f"run_{run['status']}",
            "reasons": [run["status_reason"] or f"run stopped with status {run['status']}"], "evidence_ids": []}


def build_results(pairs: list[tuple[str, int]], cfg: dict) -> dict:
    build_output = stubs.owned_or_stub("backend.data.output_map", "build_output")
    fmt = cfg["batch_format"]
    results = []
    for case_id, run_id in pairs:
        run = db.get_run(run_id)
        saved = db.get_verdict(run_id)
        data = {"input": run["input"], "verdict": verdict_for(run),
                "answers": saved["answers"] if saved else None, "run": run}
        results.append({fmt["case_id_field"]: case_id, **build_output(data, cfg["output_fields"])})
    return {fmt["results_key"]: results}


def write_json_atomic(path: str, data: dict):
    """Write to a temp file, then rename: a kill mid-write never leaves a half-written results file."""
    tmp = f"{path}.tmp"
    Path(tmp).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


# ---------- entry point ----------

def run_cli(input_path: str, output_path: str, parallel: int = 1, client_id: str = "default") -> dict:
    load_dotenv()
    db.init_db()
    configure_llm()
    cfg = load_config(client_id)                 # this client's formats, limits and rules
    resumed = db.requeue_interrupted_runs()      # runs killed mid-way last time -> queued again
    if resumed:
        print(f"resuming interrupted runs: {resumed}")

    pairs = ensure_runs(load_cases(input_path, cfg), cfg)
    print(f"{len(pairs)} cases -> runs {[run_id for _, run_id in pairs]}")

    def on_done(run_id):
        run = db.get_run(run_id)
        case_id = next(c for c, r in pairs if r == run_id)
        print(f"[{case_id}] run #{run_id}: {verdict_for(run)['verdict']} ({run['status']})")
        write_json_atomic(output_path, build_results(pairs, cfg))   # partial results after every run

    asyncio.run(process_batch([run_id for _, run_id in pairs], parallel, on_done))
    results = build_results(pairs, cfg)
    write_json_atomic(output_path, results)
    print(f"wrote {output_path}")
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run a batch of vendor checks.")
    parser.add_argument("--input", required=True, help="cases file (kickoff input format)")
    parser.add_argument("--output", required=True, help="results file to write")
    parser.add_argument("--parallel", type=int, default=1, help="runs at the same time (default 1)")
    parser.add_argument("--client", default="default", help="client_id from config.yaml clients (default: default)")
    args = parser.parse_args(argv)
    run_cli(args.input, args.output, args.parallel, args.client)


if __name__ == "__main__":
    main()
