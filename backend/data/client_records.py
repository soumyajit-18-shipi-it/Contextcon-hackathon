"""Load the client's existing vendor list into client_vendors (used by the duplicate check).

File: config client.records_path, JSON (a list, or {"vendors": [...]}) or CSV. Column names are mapped
through config client.record_fields, so a new kickoff format is a config edit. The file is re-read when
its content changes (organisers may update it mid-build); unchanged content keeps row ids stable.
"""
import csv
import io
import json
from pathlib import Path

from backend import db
from backend.engine.names import normalize_domain

_loaded = {}   # (client_id, path) -> text last loaded


def parse_records(text: str, path: str, fields: dict) -> list[dict]:
    """File text -> [{name, domain, director, gstin, other}] using the configured column names."""
    if path.lower().endswith(".csv"):
        rows = list(csv.DictReader(io.StringIO(text)))
    else:
        data = json.loads(text)
        rows = data.get("vendors", []) if isinstance(data, dict) else data
    vendors = []
    for row in rows:
        vendor = {ours: (row.get(theirs) or None) for ours, theirs in fields.items()}
        vendor["domain"] = normalize_domain(vendor.get("domain"))
        vendor["other"] = row
        if vendor.get("name") or vendor.get("domain"):
            vendors.append(vendor)
    return vendors


def load_client_records(cfg: dict, client_id: str = "default") -> int:
    """Replace this client's rows with the file's contents if the file changed. Returns vendors on file."""
    path = Path(cfg["client"]["records_path"])
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8-sig")
    vendors = parse_records(text, str(path), cfg["client"]["record_fields"])
    if _loaded.get((client_id, str(path))) == text:
        return len(vendors)
    with db.connect() as conn:
        conn.execute("DELETE FROM client_vendors WHERE client_id = ?", (client_id,))
        for v in vendors:
            conn.execute(
                "INSERT INTO client_vendors (client_id, name, domain, director, gstin, other_json) VALUES (?, ?, ?, ?, ?, ?)",
                (client_id, v.get("name"), v.get("domain"), v.get("director"), v.get("gstin"), json.dumps(v["other"])),
            )
    _loaded[(client_id, str(path))] = text
    return len(vendors)
