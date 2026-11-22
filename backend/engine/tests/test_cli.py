"""CLI tests: batch in, results out, kill + re-run resumes without duplicates. Test-only data."""
import json

import pytest

from backend import cli, db
from backend.engine import orchestrator


class Crash(BaseException):
    """Simulates kill -9 of the CLI process."""


def write_cases(tmp_path, cases):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"cases": cases}), encoding="utf-8")
    return str(path)


CASES = [
    {"id": "c1", "vendor_name": "Alpha Roadlines", "website": "alpharoadlines.in"},
    {"id": "c2", "vendor_name": "Beta Movers", "website": "betamovers.in"},
]


def count_runs():
    with db.connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]


def test_batch_writes_one_result_per_case(tmp_path):
    out = tmp_path / "results.json"
    cli.run_cli(write_cases(tmp_path, CASES), str(out))
    results = json.loads(out.read_text())["results"]
    assert [r["id"] for r in results] == ["c1", "c2"]
    assert all(r["verdict"] and r["status"] == "awaiting_approval" for r in results)


def test_rerun_reuses_runs(tmp_path):
    cases, out = write_cases(tmp_path, CASES), str(tmp_path / "results.json")
    first = cli.run_cli(cases, out)
    second = cli.run_cli(cases, out)
    assert count_runs() == 2
    assert [r["run_id"] for r in first["results"]] == [r["run_id"] for r in second["results"]]


def test_kill_mid_batch_then_rerun_resumes(tmp_path, monkeypatch):
    cases, out = write_cases(tmp_path, CASES), str(tmp_path / "results.json")
    calls, state = {}, {"crashed": False}
    real = dict(orchestrator.get_step_functions())

    def wrap(name):
        async def step(ctx):
            calls[(ctx["run_id"], name)] = calls.get((ctx["run_id"], name), 0) + 1
            if name == "media" and ctx["run_id"] == 2 and not state["crashed"]:
                state["crashed"] = True
                raise Crash()
            return await real[name](ctx)
        return step

    steps = [(name, wrap(name)) for name, _ in orchestrator.STEPS]
    monkeypatch.setattr(orchestrator, "get_step_functions", lambda: steps)

    with pytest.raises(Crash):
        cli.run_cli(cases, out)
    assert db.get_run(1)["status"] == "awaiting_approval" and db.get_run(2)["status"] == "running"

    results = cli.run_cli(cases, out)["results"]                  # same command again
    assert count_runs() == 2                                       # nothing duplicated
    assert all(r["status"] == "awaiting_approval" for r in results)
    assert calls[(1, "resolve")] == 1 and calls[(2, "resolve")] == 1   # finished steps not repeated
    assert calls[(2, "media")] == 2                                # the interrupted step ran again


def test_same_vendor_twice_in_one_file_is_two_runs_and_flagged(tmp_path):
    twice = [{"id": "a", "vendor_name": "Gamma Freight", "website": "gammafreight.in"},
             {"id": "b", "vendor_name": "Gamma Freight", "website": "gammafreight.in"}]
    results = cli.run_cli(write_cases(tmp_path, twice), str(tmp_path / "r.json"))["results"]
    assert count_runs() == 2
    assert db.get_run(results[1]["run_id"])["duplicate_of"] == f"run #{results[0]['run_id']}"


def test_unfinished_run_is_reported_as_hold_never_guessed(tmp_path):
    out = str(tmp_path / "r.json")
    cases = write_cases(tmp_path, CASES[:1])
    pairs = cli.ensure_runs(cli.load_cases(cases, cli.load_config()), cli.load_config())
    with db.connect() as conn:   # push the run over its credit ceiling before it starts
        conn.execute("UPDATE runs SET credits_used = 100000 WHERE id = ?", (pairs[0][1],))
    result = cli.run_cli(cases, out)["results"][0]
    assert result["status"] == "held" and result["verdict"] == "HOLD FOR REVIEW"
