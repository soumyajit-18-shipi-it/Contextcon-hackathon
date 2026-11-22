"""Run engine: runs each vendor check as a fixed list of steps, with a checkpoint after every step.

Resume logic (what the judges test by killing the server):
  1. On startup, any run still marked 'running' was interrupted -> set back to 'queued'.
  2. When a run is picked up, every step already finished in the DB is skipped.
  3. A step that was mid-flight when we died has no 'done' row, so it simply runs again.
     B's Crustdata client caches per run, so that re-run makes zero new API calls.
"""
import asyncio
import inspect
import time
import traceback

from backend import db
from backend.config import load_config
from backend.engine import stubs

# (step name, module that owns it). The function is always called step_<name>.
STEPS = [
    ("resolve", "backend.data.steps"),        # B
    ("duplicate", "backend.engine.duplicate"),  # Lead
    ("company", "backend.data.steps"),        # B
    ("director", "backend.data.steps"),       # B
    ("site", "backend.web.steps"),            # C
    ("core_checks", "backend.data.steps"),    # B
    ("lookalike", "backend.engine.lookalike"),  # Lead
    ("copied_site", "backend.web.steps"),     # C
    ("media", "backend.web.steps"),           # C
    ("timeline", "backend.web.steps"),        # C
    ("verdict", "backend.engine.verdict"),    # Lead
    ("explain", "backend.web.steps"),         # C
    ("report", "backend.engine.report"),      # Lead
]

# If the company can't be found at all, these are skipped and we go straight to the verdict.
SKIP_WHEN_NOT_FOUND = ["duplicate", "company", "director", "site", "core_checks",
                       "lookalike", "copied_site", "media", "timeline"]

POLL_SECONDS = 1.0


def get_step_functions() -> list[tuple[str, callable]]:
    """The owner's step_<name> function, or the stub if they haven't written it yet."""
    return [(name, stubs.owned_or_stub(module, f"step_{name}")) for name, module in STEPS]


def check_ceilings(run_id: int) -> str | None:
    """Return a reason if the run has used up its time, credits or rupees, else None."""
    run = db.get_run(run_id)
    if run["elapsed_s"] > run["time_limit_s"]:
        return f"time ceiling: {run['elapsed_s']:.0f}s used of {run['time_limit_s']:.0f}s"
    if run["credits_used"] > run["credit_limit"]:
        return f"credit ceiling: {run['credits_used']:.1f} credits used of {run['credit_limit']:.0f}"
    if run["cost_inr"] > run["cost_limit_inr"]:
        return f"cost ceiling: Rs {run['cost_inr']:.2f} used of Rs {run['cost_limit_inr']:.2f}"
    return None


async def _call(func, ctx):
    """Steps may be async or plain functions."""
    result = func(ctx)
    if inspect.isawaitable(result):
        result = await result
    return result


def _as_dict(output) -> dict:
    """Steps return a dict. A bare list is treated as a list of evidence items."""
    if output is None:
        return {}
    if isinstance(output, list):
        return {"evidence": output}
    return output


async def run_step(run_id: int, step_name: str, func, ctx) -> tuple[dict | None, str | None]:
    """Run one step, retrying once on an exception. Returns (output, error)."""
    error = None
    for attempt in (1, 2):
        db.start_step(run_id, step_name)
        run = db.get_run(run_id)
        time_left = max(run["time_limit_s"] - run["elapsed_s"], 1)
        started = time.monotonic()
        try:
            output = await asyncio.wait_for(_call(func, ctx), timeout=time_left)
            return _as_dict(output), None
        except Exception as e:   # a kill (KeyboardInterrupt/SIGKILL) is NOT caught: the run stays 'running'
            error = f"{type(e).__name__}: {e}"
            print(f"[run {run_id}] step {step_name} attempt {attempt} failed: {error}")
        finally:
            db.add_elapsed(run_id, time.monotonic() - started)
    return None, error


def failed_output(step_name: str, error: str) -> dict:
    """A step that failed twice: its result is 'unknown' (never 'not found'), so the verdict holds."""
    return {
        "failed": True,
        "error": error,
        "evidence": [{
            "check": f"{step_name}_step",
            "claim": f"The {step_name} step could not complete",
            "value": None, "source_id": None, "field_path": None, "passage": None, "record_date": None,
            "flag": "none", "status": "unknown", "missing": f"step failed twice: {error}",
        }],
    }


async def process_run(run_id: int):
    """Run (or resume) one vendor check until it finishes or has to stop."""
    cfg = load_config()                           # fresh every run: config edits apply immediately
    db.set_run_limits(run_id, cfg["limits"])
    run = db.get_run(run_id)
    outputs = db.get_step_outputs(run_id)         # steps already checkpointed before a crash
    ctx = {"run_id": run_id, "client_id": run["client_id"], "input": run["input"],
           "outputs": outputs, "config": cfg}

    for step_name, func in get_step_functions():
        if step_name in outputs:                  # checkpointed -> skip (this is the resume)
            continue

        resolve = outputs.get("resolve")
        if resolve is not None and not resolve.get("chosen"):
            if resolve.get("candidates"):         # several possible companies: a person must pick
                db.set_run_status(run_id, "awaiting_candidate",
                                  f"{len(resolve['candidates'])} possible companies, pick one")
                return
            if step_name in SKIP_WHEN_NOT_FOUND:  # nothing found: go straight to the verdict
                outputs[step_name] = {"skipped": "company not resolved"}
                db.finish_step(run_id, step_name, "skipped", outputs[step_name])
                continue

        reason = check_ceilings(run_id)
        if reason:
            db.set_run_status(run_id, "held", reason)
            return

        db.mark_run_started(run_id, step_name)
        output, error = await run_step(run_id, step_name, func, ctx)

        if error is not None:                     # failed twice: record 'unknown' and carry on
            output = failed_output(step_name, error)
            db.finish_step(run_id, step_name, "failed", output)
            outputs[step_name] = output
            continue

        if output.get("hold"):                    # e.g. credits ran out (402): stop, don't checkpoint
            db.finish_step(run_id, step_name, "held", {"hold": output["hold"]})
            db.set_run_status(run_id, "held", output["hold"])
            return

        db.finish_step(run_id, step_name, "done", output)   # CHECKPOINT
        outputs[step_name] = output
        if step_name == "duplicate" and output.get("duplicate_of"):
            db.set_duplicate_of(run_id, output["duplicate_of"])

    db.set_run_status(run_id, "awaiting_approval", "report ready, waiting for a person to clear or reject")


async def drain_queue():
    """Process queued runs until none are left (used by the CLI and tests)."""
    while (run := db.next_queued_run()) is not None:
        await _safe_process(run["id"])


async def _safe_process(run_id: int):
    try:
        await process_run(run_id)
    except Exception as e:   # unexpected engine error: fail the run visibly, keep the worker alive
        traceback.print_exc()
        db.set_run_status(run_id, "failed", f"engine error: {type(e).__name__}: {e}")


async def worker_loop():
    """Background worker started with the API. One run at a time, oldest first."""
    resumed = db.requeue_interrupted_runs()
    if resumed:
        print(f"[worker] resuming interrupted runs: {resumed}")
    while True:
        run = db.next_queued_run()
        if run is None:
            await asyncio.sleep(POLL_SECONDS)
            continue
        await _safe_process(run["id"])
