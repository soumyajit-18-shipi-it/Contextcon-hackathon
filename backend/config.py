"""Load config.yaml. Called at the start of every run, so edits apply without a restart."""
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).parent / "config.yaml"

REQUIRED_SECTIONS = ["limits", "rules", "verdict_rules", "output_fields", "client"]


def load_config() -> dict:
    """Read config.yaml fresh from disk and check the required sections exist."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    missing = [s for s in REQUIRED_SECTIONS if s not in cfg]
    if missing:
        raise ValueError(f"config.yaml is missing sections: {missing}")
    return cfg
