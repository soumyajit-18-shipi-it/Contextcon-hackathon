# Web/media implementation status

This first increment implements Member C's website step and provider-independent
LLM helper. The engine discovers `step_site` automatically. Copied-site, media,
timeline, and explanation steps still use the engine's explicit placeholders.

## Integration

- `websearch.search(run_id, query)` delegates to Member B's
  `backend.data.crustdata.call(run_id, endpoint, payload)`.
- `fetch` requires `CRUSTDATA_WEB_FETCH_ENDPOINT` and sends `{"urls": [url]}`.
  Confirm both against the kickoff spec before enabling. The supplied handoff
  conflates search and retrieval; live API compatibility has not been verified.
- Missing client, invalid response, and failed fetches are never reported as
  successful checks. Credit exhaustion returns the engine's `hold` contract.
- The website step makes at most two fetch calls: home and a same-host About
  link, or `/about`. Each year claim retains the passage and persisted source.
  A copyright year is a website statement, not evidence of incorporation.
- `llm.configure` accepts an async provider transport, model, explicit INR token
  prices, and token caps. The transport receives system/user/schema and must
  enforce those caps. Return `{text, tokens_in, tokens_out, http_status}`.
  There is deliberately no default paid provider. JSON Schema validation retries
  malformed output once, recording both attempts and updating the run total.
- Steps return evidence; only the engine checkpoints evidence rows. URL and
  retrieval metadata survive in step output; persisted source rows provide them
  for the current evidence-table schema.

## Limits and remaining work

No live provider calls have been made. Member B's client must supply caching,
rate limits, retries, source persistence, and Crustdata accounting. The eight-call
shared web budget and media prioritisation remain to be integrated with that
client before implementing later checks. About-page fallback is limited to one
request. Page normalization supports explicit text/html/content/markdown fields;
confirm the real response shape with the kickoff kit.

LLM request delimiters and system instructions reduce prompt-injection risk;
they do not prove extraction truth. Later steps must verify quotes against source
text and use code for namesake scoring and flags. Network failures may have
unknown billable usage: the ledger records the attempted call with null HTTP
status; provider-side reconciliation is still required. Budget checks assume the
existing single worker. Concurrent callers would need atomic reservations.

URL checks reject literal private addresses and local hostnames. The external
fetch service must additionally enforce DNS and redirect restrictions.

Dependencies: Python standard library; `jsonschema` for JSON Schema validation.
Offline tests: `python -m pytest tests/test_web.py backend/engine/tests -q`.
