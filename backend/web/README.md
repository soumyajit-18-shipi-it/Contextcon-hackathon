# Web/media implementation status

The website step, provider-independent LLM helper, and offline-testable adverse
media and copied-site steps are implemented. The engine discovers `step_site`,
`step_media`, and `step_copied_site` automatically. Timeline and explanation
remain engine placeholders.

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
they do not prove extraction truth. Media validates quotes against persisted
source text and uses code for namesake scoring. Network failures may have
unknown billable usage: the ledger records the attempted call with null HTTP
status; provider-side reconciliation is still required. Budget checks assume the
existing single worker. Concurrent callers would need atomic reservations.

URL checks reject literal private addresses and local hostnames. The external
fetch service must additionally enforce DNS and redirect restrictions.

Dependencies: Python standard library; `jsonschema` for JSON Schema validation.
Offline tests: `python -m pytest backend -q` (web tests live in backend/web/tests/).

## Adverse media increment

`steps.step_media(ctx)` delegates to `media.screen_media(ctx)`. It calls the
existing `websearch.search`, `websearch.fetch`, and `llm.llm_json` interfaces.
It returns evidence, labelled media hits, and personal-field usage for the engine
to checkpoint; it never inserts those child rows itself. The LLM helper continues
to own its existing per-call ledger writes.

### Explicit integration blocker

There is still no `backend/data/crustdata.py`, verified response sample, or real
director-profile contract in this checkout. Consequently, there is **no default
production media adapter**. Until configured, the step returns `adverse_media`
with status `unknown`, makes no provider calls, and never claims a clean screen.

`media.configure_media_adapter(adapter)` supplies a C-local normalization seam,
not a new team/provider contract. The adapter must implement:

- `search_urls(persisted_source) -> list[str]`, preserving provider order.
- `article_text(persisted_source) -> str`, decoding the full persisted article.
- `director_facts(ctx) -> dict[str, Fact]`, mapping confirmed B fields to the
  internal comparison fields documented in `MediaAdapter`.

Each `Fact(value, source_id, path)` must point to an exactly equal, same-type
value inside that run's persisted `raw_response`. Profile field names and all
provider payload formats in the tests are synthetic fixtures, not production
assumptions. Adapter methods are trusted integration code: they must not perform
extra network calls or fabricate text. Source URL, run ownership, and search
query are checked before use. Article extraction uses persisted text only,
ignoring transient fetch `data`.

Lead/B must confirm adapter mappings, source persistence, fetch API, call caching,
rate limiting, and the shared budget. A configured LLM transport with real prices
is also required. No changes were made to B's client, Lead's startup, schema,
verdict rules, configuration, or ledger integration.

### Search allocation and coverage

The default local allowance is **three web-interface calls**: a quoted director
adverse-media query, a quoted company query, then the highest-ranked unique URL
(director-query results first). This leaves a nominal two site calls and three
copied-site calls within approximately eight. It does **not** enforce that total.
Provider retries, previous steps, concurrent callers, and replay are not counted.
The local counter is returned as `coverage.web_calls`, with
`global_budget_enforced: false`. `screen_media(..., call_limit=N)` supports a
local allowance of 0–8 for tests/future wiring; the engine-facing step stays `ctx`-only.

At most five unique articles are considered even with a larger local allowance.
Unsearched queries or unfetched results produce unknown coverage, not a clean
screen. Searches returning no results produce a narrowly scoped evidence item
listing queries and persisted search source IDs. Failures, missing adapters,
invalid responses and extraction failures remain unknown. Credit exhaustion
returns the existing `hold` contract. The engine discards partial child outputs
when held, so replay safety still depends on B's cache and future LLM reuse.

### Identity and evidence policy

Only grounded attributes earn points: company/employer 40, city 20, role or
industry 15 (once), career-date fit 15, and age 10. String comparisons are exact
after case/whitespace normalization; aliases are not guessed. Career points
require employer match and an event inside a sourced start/end interval. An open
interval is not inferred from a missing end date. Age points require the same
explicit age-reference date and allow a two-year approximation tolerance.

Thresholds come from `ctx.config.rules.namesake_match` and `namesake_clear`.
Match additionally requires a sourced matching name and employer, with no proven
contradiction. Low score alone never clears a namesake. In this first increment,
the supported contradiction is an age difference greater than two years on the
same explicit date. Different cities, employers, roles, or missing fields do not
prove a different person and remain unresolved. This deliberately limits recall
until temporal/exclusive identity contracts are agreed. Age is optional: if B's
minimisation policy excludes it, no age comparison or age-based clearing occurs.

Extraction accepts only the eight specified fields. A quote must be an exact
contiguous substring of persisted article text; every non-null extracted field
must occur within that quote. Dates must already appear in ISO form. Schema
violations, invented quotes/attributes and detected instruction-like passages are
rejected. The article is capped at 10,000 UTF-8 bytes; oversized articles become
unresolved rather than being silently truncated. These strict rules will send
some legitimate articles to review.

An identity match is not proof of wrongdoing. This increment adds unknown review
evidence for matched events and does not emit automatic hard/soft severity flags.
A future approved policy must handle allegations, denials, acquittals, event
seriousness and person/event relationships before producing hard flags. Namesake
clearance means only that this article's subject was distinguished; it does not
clear the vendor. Every hit has a label and reason, including failed extractions.

Only allowed extracted fields and quote are returned for articles; titles and full
article text are not copied into media hits. Identity source pointers are retained
in evidence values; personal fields used are returned for engine logging. Raw
provider article retention remains B/Lead's unresolved privacy/provenance policy.
Extra URL/retrieval/fragment metadata survives in step output, while evidence-table
rows still require the source viewer to resolve source URLs and retrieval dates.

### Tests and remaining risks

Offline tests use mocked search/fetch providers and the real JSON helper with a
mocked transport. They cover identity matches, dated namesake contradictions,
ambiguity, missing attributes, source ownership, quote/attribute grounding, empty
versus failed searches, budget limits, credits, prompt injection and engine
checkpoint/dispatch integration. No live API claims or vendor fixtures appear in
production code.

Prompt delimiters, schema and lexical grounding cannot prove semantic truth:
multiple people in a quotation, misleading articles, and sophisticated injection
remain risks. The adapter must select the intended director and preserve article
text accurately. Existing LLM unknown-billing/replay limits and Lead-owned verdict
precedence remain unchanged. No GitHub push is part of this increment.

## Copied-site increment

`steps.step_copied_site(ctx)` delegates to `copied_site.screen_copied_site(ctx)`.
It reuses `outputs.site.pages`, selecting up to three unique 12–30 word sentences
after removing cookie/copyright/privacy text and common marketing phrases. Each
selected sentence is searched as a quoted literal through `websearch.search`.
Sentences containing double quotes are skipped to avoid breaking query quoting.
Case and whitespace in passages are preserved for exact provenance checks.

### Provider and budget integration blockers

`configure_copied_site(adapter, budget)` is a C-local integration seam, not a change
to ctx, B's API, or the shared configuration. The adapter supplies ranked
`search_urls(source)`, full `page_text(source)`, and
`unrelated_business(ctx, source) -> UnrelatedBusiness | None`. All source inputs
are persisted, same-run source rows. The existing media adapter remains unchanged.
There is no production default or guessed Crustdata decoder. Adapter methods are
trusted normalization/identity code and must not perform network calls.

The unrelated-business assessment contains a stable independent-owner ID and a
supporting passage actually present on that page. The adapter must establish
business ownership and absence of vendor affiliation; different hostnames or
similar snippets do not establish independence. Unknown affiliation returns None
and makes the result unknown. Domains owned by the same business must share an ID.
This policy still requires verified integration evidence; fixture assessments are
used only in tests.

The budget hook exposes `await reserve(run_id) -> bool`. Every search and fetch
requires a successful reservation immediately before dispatch. Missing hooks,
zero remaining allowance, or reservation failures make coverage unknown and do
not dispatch that call. A failed provider call still consumes its reservation.
The hook must eventually be backed by the Lead/B shared remaining-call mechanism,
including retries and other steps. **No global mechanism is implemented here**;
`global_budget_enforced` remains false. Tests supply a finite fake remaining
budget. Current site/media steps do not use this hook and were not silently
changed to adopt it. Integration must also allocate calls between copy searches,
verification fetches and media; three search calls alone cannot verify three hits.

### Overlap evidence and flags

Vendor page text must occur in its persisted source text. Candidate pages are
fetched through `websearch.fetch`; matching snippets are never accepted as
overlap evidence. Exact sentence overlap is checked only against full persisted
page text. Previously fetched URLs are reused within the step across sentences.
Own hosts/subdomains and the handoff's directory/social domains are excluded with
hostname-boundary comparisons. Unknown aliases/affiliations need the adapter's
business assessment; redirects to a different stored URL are treated as unknown.

- One independently supported overlap: soft.
- At least two distinct sentences supported by distinct unrelated business
  owners: hard. This conservative matching rule prevents duplicated search
  results, repeated sentences, and one owner across multiple domains from
  escalating severity. Two sentences on one owner remain soft.
- Literal `lorem ipsum` or `Your Company Name` in a grounded vendor page: hard,
  with no network call required. A marker may also be a deliberate example, so
  this is a template-text flag, never a claim of fraud or direction of copying.

Claims say “Text also appears on …”; they never identify an originator. Evidence
includes the exact passage, source URL, fragment link, retrieved date, available
record date, and vendor/search/business source context. Only the engine persists
child evidence rows. Extra URL metadata remains in step output under the existing
schema, as with site/media evidence.

Search failures, inaccessible result pages, provenance mismatches, unknown
business independence and exhausted budgets produce unknown coverage. Verified
positive overlaps are retained alongside unknown coverage; partial work never
becomes a clean result. Completed negative checks say only that no overlap was
verified within those searches, not that the website is original. No suitable
sentences is unknown. Credit exhaustion returns the existing hold contract.

### Limits and verification

Boilerplate filtering is heuristic and English-focused. Exact matching can miss
rewritten text or formatting differences. The exclusion list cannot enumerate
every directory/social service or country domain. Template markers and text
reuse may be legitimate; human review remains necessary. The Lead-owned verdict
does not currently list copied_site among unknown_key_checks; unknown copy
coverage alone therefore does not guarantee HOLD. That integration decision is
documented rather than changing verdict/configuration ownership here.

Offline copied-site tests cover honest fixtures, independently supported overlaps,
owner/sentence deduplication, templates, vendor and directory exclusions, failed
searches/fetches, zero/partial budgets, fake snippets, source mismatches, caching,
word/boilerplate filters, engine dispatch and checkpoint persistence. No live
API verification or real-company originality assertion has been made.
