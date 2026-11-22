"""Intake: turn the client's request (structured fields and/or free text) into our input fields.

  1. Fields the client filled in are kept as they are, never overwritten.
  2. A website in the free text is found with a regex.
  3. Other missing fields: the LLM extracts them (llm_json, prompt_version below, logged to the ledger).
     A value is only kept if it literally appears in the client's text, so nothing is invented.
  4. No name and no website after all that -> the run waits (awaiting_input) and says what's missing.
"""
import re

from backend import db
from backend.web import llm

PROMPT_VERSION = "intake-v1"
FIELDS = ["name", "website", "director", "claimed_year"]
URL_RE = re.compile(r"\b(?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:co\.in|com|in|net|org|io|co|biz|info)\b(?:/\S*)?",
                    re.IGNORECASE)

SCHEMA = {
    "type": "object",
    "properties": {f: {"type": "string"} for f in FIELDS},
    "required": FIELDS,
    "additionalProperties": False,
}
SYSTEM = ("You read a logistics company's request to onboard a new vendor (a carrier or supplier). "
          "Return the vendor's company name, website, director's name and the year the vendor claims it was founded, "
          "copied exactly as written in the request. Use an empty string for anything the request does not state. "
          "Never guess or complete a value.")


def _appears_in(value: str, text: str) -> bool:
    return bool(value) and value.strip().lower() in text.lower()


async def step_intake(ctx):
    run_id, text = ctx["run_id"], (ctx["input"].get("request_text") or "").strip()
    merged = dict(ctx["input"])
    how = {f: "given" for f in FIELDS if merged.get(f) not in (None, "")}

    if text and "website" not in how:
        match = URL_RE.search(text)
        if match:
            merged["website"], how["website"] = match.group(0), "regex"

    llm_status, source_id = "not needed", None
    missing = [f for f in FIELDS if f not in how]
    if text and missing:
        source_id = db.find_or_add_source(run_id, "client_request", f"runs/{run_id}/request_text", text)
        try:
            extracted = await llm.llm_json(run_id, "intake", SYSTEM, text, SCHEMA, PROMPT_VERSION)
            llm_status = "used"
            for field in missing:
                value = (extracted.get(field) or "").strip()
                if _appears_in(value, text):          # never accept a value that isn't in the client's words
                    merged[field], how[field] = value, "llm"
        except llm.LLMUnavailable as e:
            llm_status = f"unavailable: {e}"

    if isinstance(merged.get("claimed_year"), str):
        year = re.search(r"(?:19|20)\d{2}", merged["claimed_year"])
        merged["claimed_year"] = int(year.group(0)) if year else None

    output = {"input": merged, "how": how, "llm": llm_status, "source_id": source_id}
    if not merged.get("name") and not merged.get("website"):
        output["await_input"] = "Need the vendor's name or website: neither was given nor found in the request."
    return output
