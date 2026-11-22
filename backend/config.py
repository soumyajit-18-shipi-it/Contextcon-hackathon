"""Load config.yaml. Called at the start of every run, so edits apply without a restart.

load_config(client_id) returns the shared settings with that client's overrides applied, plus
cfg["client"] = the client's own block (name, records file, ...).
"""
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).parent / "config.yaml"

REQUIRED_SECTIONS = ["limits", "rules", "verdict_rules", "batch_format", "input_fields", "output_fields", "clients"]
# Sections a client block may override (key by key).
OVERRIDABLE = ["limits", "rules", "verdict_rules", "batch_format", "input_fields", "output_fields"]


class UnknownClient(ValueError):
    pass


def load_config(client_id: str = "default") -> dict:
    """Read config.yaml fresh from disk, check it, and apply the client's overrides."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    missing = [s for s in REQUIRED_SECTIONS if s not in cfg]
    if missing:
        raise ValueError(f"config.yaml is missing sections: {missing}")
    if client_id not in cfg["clients"]:
        raise UnknownClient(f"unknown client '{client_id}' (known: {sorted(cfg['clients'])})")
    client = cfg["clients"][client_id] or {}
    for section in OVERRIDABLE:
        cfg[section] = {**cfg[section], **(client.get(section) or {})}
    cfg["client"] = {"id": client_id, **{k: v for k, v in client.items() if k not in OVERRIDABLE}}
    return cfg
