"""Verity API. Start: .venv/Scripts/uvicorn backend.main:app --port 8000

The run engine starts as a background task with the API and resumes interrupted runs.
Routes are plain `def` (FastAPI runs them in a thread pool) because SQLite calls are blocking.
"""
import asyncio
import importlib
import sqlite3
from contextlib import asynccontextmanager
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend import db
from backend.config import load_config
from backend.engine import orchestrator

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    worker = asyncio.create_task(orchestrator.worker_loop())
    yield
    worker.cancel()


app = FastAPI(title="Verity", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------- request bodies ----------

class RunInput(BaseModel):
    name: str = Field(min_length=1)
    website: str | None = None
    director: str | None = None
    claimed_year: int | None = None
    request_text: str | None = None


class CandidateChoice(BaseModel):
    index: int = Field(ge=0)


class Approval(BaseModel):
    decision: Literal["clear", "reject"]
    reason: str = Field(min_length=3)     # a person always says why
    user: str = Field(min_length=1)


# ---------- helpers ----------

def _run_or_404(run_id: int) -> dict:
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(404, f"run {run_id} not found")
    return run


# ---------- routes ----------

@app.post("/runs")
def create_run(body: RunInput):
    run_id = db.create_run(body.model_dump(), load_config()["limits"])
    return {"id": run_id, "status": "queued"}


@app.get("/runs")
def list_runs():
    return db.list_runs()


@app.get("/runs/{run_id}")
def get_run(run_id: int):
    run = _run_or_404(run_id)
    outputs = db.get_step_outputs(run_id)
    verdict = db.get_verdict(run_id)
    resolve = outputs.get("resolve") or {}
    return {
        "run": run,
        "steps": db.get_steps(run_id),
        "evidence": db.get_evidence(run_id),
        "media_hits": db.get_media_hits(run_id),
        "timeline": (outputs.get("timeline") or {}).get("events", []),
        "candidates": resolve.get("candidates", []) if run["status"] == "awaiting_candidate" else None,
        "duplicate_of": run["duplicate_of"],
        "duplicate_matches": (outputs.get("duplicate") or {}).get("matches", []),
        "lookalike": (outputs.get("lookalike") or {}).get("findings", []),
        "verdict": verdict["flags"] if verdict else outputs.get("verdict"),
        "answers": verdict["answers"] if verdict else None,
        "explanation": verdict["explanation"] if verdict else None,
        "report_md": verdict["report_md"] if verdict else None,
        "output": verdict["output"] if verdict else None,
        "approval": db.get_approval(run_id),
        "personal_data": db.get_personal_data(run_id),
        "ledger_summary": db.ledger_summary(run_id),
    }


@app.get("/sources/{source_id}")
def get_source(source_id: int):
    source = db.get_source(source_id)
    if source is None:
        raise HTTPException(404, f"source {source_id} not found")
    return source


@app.post("/runs/{run_id}/select-candidate")
def select_candidate(run_id: int, body: CandidateChoice):
    run = _run_or_404(run_id)
    if run["status"] != "awaiting_candidate":
        raise HTTPException(409, f"run is '{run['status']}', not waiting for a candidate")
    resolve = db.get_step_outputs(run_id)["resolve"]
    if body.index >= len(resolve["candidates"]):
        raise HTTPException(400, f"index must be below {len(resolve['candidates'])}")
    resolve["chosen"] = resolve["candidates"][body.index]
    resolve["chosen_by"] = "person"                      # recorded: a human picked this company
    db.update_step_output(run_id, "resolve", resolve)
    db.set_run_status(run_id, "queued", f"candidate {body.index} picked, continuing")
    return {"id": run_id, "status": "queued", "chosen": resolve["chosen"]}


@app.post("/runs/{run_id}/approve")
def approve(run_id: int, body: Approval):
    run = _run_or_404(run_id)
    existing = db.get_approval(run_id)
    if existing:
        raise HTTPException(409, {"message": "already decided", "approval": existing})
    if run["status"] != "awaiting_approval":
        raise HTTPException(409, f"run is '{run['status']}', not awaiting approval")
    if body.decision == "clear" and run["duplicate_of"]:
        raise HTTPException(409, f"duplicate of existing vendor {run['duplicate_of']}; cannot clear it again")
    try:
        db.add_approval(run_id, body.decision, body.reason, body.user)
    except sqlite3.IntegrityError:                       # two clicks at the same moment: the DB lets one win
        raise HTTPException(409, {"message": "already decided", "approval": db.get_approval(run_id)})
    return {"id": run_id, "status": "done", "approval": db.get_approval(run_id)}


@app.get("/ledger")
def ledger(run_id: int | None = None):
    rows = db.get_ledger(run_id)
    return {"rows": rows, "summary": db.ledger_summary(run_id) if run_id is not None else None}


@app.get("/credits")
async def credits():
    """Crustdata balance via B's client (GET /account/credits is free)."""
    try:
        crustdata = importlib.import_module("backend.data.crustdata")
    except ModuleNotFoundError as e:
        if e.name != "backend.data.crustdata":
            raise
        crustdata = None
    get_credits = getattr(crustdata, "get_credits", None)
    if get_credits is None:   # STUB – owned by B
        return {"status": "unavailable", "reason": "STUB: backend/data/crustdata.get_credits not implemented yet"}
    return await get_credits()
