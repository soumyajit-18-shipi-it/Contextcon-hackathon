"""Anthropic transport for llm_json (backend/web/llm.py). Model + prices come from config.yaml -> llm.

The model only extracts facts and writes text; it never decides a flag or a verdict.
Structured output (output_config.format = json_schema) makes it return JSON matching the caller's schema.
"""
import os

import anthropic

from backend.config import load_config
from backend.web import llm


def _api_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("LLM_API_KEY")


async def transport(request: dict) -> dict:
    """llm.py's contract: request {model, system, user, schema, max_output_tokens}
    -> {text, tokens_in, tokens_out, http_status}. Never raises for API errors."""
    try:
        async with anthropic.AsyncAnthropic(api_key=_api_key(), max_retries=1, timeout=20) as client:
            response = await client.messages.create(
                model=request["model"],
                max_tokens=request["max_output_tokens"],
                system=request["system"],
                messages=[{"role": "user", "content": request["user"]}],
                output_config={"effort": "low",
                               "format": {"type": "json_schema", "schema": request["schema"]}},
            )
    except anthropic.APIStatusError as e:
        return {"text": "", "tokens_in": 0, "tokens_out": 0, "http_status": e.status_code}
    except anthropic.APIConnectionError:
        return {"text": "", "tokens_in": 0, "tokens_out": 0, "http_status": None}
    text = "".join(block.text for block in response.content if block.type == "text")
    return {"text": text, "tokens_in": response.usage.input_tokens,
            "tokens_out": response.usage.output_tokens, "http_status": 200}


def configure_llm() -> bool:
    """Called at startup (API + CLI). Without a key, llm_json raises LLMUnavailable and steps degrade
    to cant_verify; nothing pretends an LLM answer exists."""
    if not _api_key():
        print("[llm] no LLM key in .env: LLM steps will report 'unavailable'")
        return False
    cfg = load_config()
    usd_to_inr = cfg["pricing"]["usd_to_inr"]
    llm.configure(transport, model=cfg["llm"]["model"],
                  input_inr_per_million=cfg["llm"]["usd_per_mtok_in"] * usd_to_inr,
                  output_inr_per_million=cfg["llm"]["usd_per_mtok_out"] * usd_to_inr,
                  max_output_tokens=cfg["llm"]["max_output_tokens"])
    return True
