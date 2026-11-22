"""Cost ledger: one row per paid call (Crustdata or LLM), and the run's running totals.

Every caller goes through record(), so credits and rupees are added up in exactly one place.
"""
from backend import db
from backend.config import load_config


def inr_per_credit() -> float:
    return float(load_config()["pricing"]["inr_per_credit"])


def record(run_id, provider, endpoint_or_model, prompt_version=None, credits=0.0, tokens_in=0,
           tokens_out=0, cost_inr=None, latency_ms=0, http_status=None) -> float:
    """Write one ledger row and add its credits/rupees to the run. Returns the rupee cost.
    For Crustdata calls, leave cost_inr=None: it is credits x pricing.inr_per_credit (config)."""
    if cost_inr is None:
        cost_inr = credits * inr_per_credit()
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO ledger (run_id, provider, endpoint_or_model, prompt_version, credits, tokens_in,
                                   tokens_out, cost_inr, latency_ms, http_status, ts)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, provider, endpoint_or_model, prompt_version, credits, tokens_in, tokens_out,
             cost_inr, latency_ms, http_status, db.now()),
        )
        if run_id is not None:
            conn.execute("UPDATE runs SET credits_used = credits_used + ?, cost_inr = cost_inr + ? WHERE id = ?",
                         (credits, cost_inr, run_id))
    return cost_inr


def run_totals(run_id: int) -> dict:
    return db.ledger_summary(run_id)
