# Acceptance cases

**Fixture notice (2026-11-22):** `docs/kickoff/` contains only `.gitkeep`, and no client-record fixture is available. The cases below use reserved `.example` domains and synthetic names. They are not live-company records and cannot establish real outcomes. The input objects in `cases.inputs.json` use the actual `RunInput` fields from `backend/main.py` and can be submitted individually to `POST /runs`. `cases.cli.json` uses the currently implemented CLI format and the temporary `input_fields` mapping in `backend/config.yaml`; it is runnable by `python -m backend.cli --input tests/cases.cli.json --output /tmp/verity-results.json`, but is not represented as the organizer's final kickoff schema. `cases.json` holds expected-result metadata alongside the API request bodies. Running the CLI makes provider calls when credentials are configured; these reserved fixtures are for behavior/format validation and are not live company results.

## T1 — Established carrier clears on complete evidence

- **Input (RunInput):** `{"name":"Northstar Freight Services","website":"https://northstarfreight.example","director":"Kavita Rao","claimed_year":2008,"request_text":"Onboard as a regional carrier"}`
- **Expected verdict:** CLEARED, only if the required identity, director and activity facts are verified and no flags remain.
- **Expected key evidence:** resolved entity/domain agreement; current director role; founded year; at least one unflagged activity fact.
- **Important flags:** none. Missing or timed-out key evidence must lower certainty to HOLD/CANNOT VERIFY per the engine; never force CLEARED.
- **Why:** absence of optional data is not a fraud signal; the engine clears only after the required facts are supported.

## T2 — Honest firm with `.in` and `.com` properties

- **Input:** `{"name":"Deccan Components","website":"https://deccancomponents.in","director":"Meera Shah","claimed_year":2012,"request_text":"Supplier onboarding; verify the relationship between .in and .com properties"}`
- **Expected verdict:** CLEARED if both domains are linked to the same company and other required facts pass.
- **Expected key evidence:** company record/website evidence explicitly links the `.in` and `.com` domains; director current role and activity verified.
- **Important flags:** no look-alike flag from TLD difference alone. Unproven relationship is unknown/soft and requires review.
- **Why:** alternate legitimate domains should pass when the evidence ties them to one entity.

## T3 — Common-name director and an unrelated negative article

- **Input:** `{"name":"Meridian Transport","website":"https://meridian-transport.example","director":"Rajesh Kumar","claimed_year":2014,"request_text":"Verify director; distinguish common-name media matches"}`
- **Expected verdict:** CLEARED if all core checks pass and the article is explicitly `namesake_cleared`; otherwise HOLD for unresolved media.
- **Expected key evidence:** negative article passage and extracted subject context; a contradictory city, employer, role or career date; readable namesake-clearing reason.
- **Important flags:** cleared namesake is not an adverse-media hard flag. Unresolved identity match remains a hold.
- **Why:** a shared name does not prove the director is the subject of the article.

## T4 — Name-only request with several candidates

- **Input:** `{"name":"Apex Logistics","request_text":"Name-only onboarding request; several possible companies may match"}`
- **Expected verdict/status:** HOLD FOR REVIEW / `awaiting_candidate` until a person selects a candidate.
- **Expected key evidence:** candidate list with distinguishing identifiers (domain, location, company description where returned).
- **Important flags:** ambiguity; do not automatically choose the top result.
- **Why:** the request does not uniquely identify a legal entity.

## T5 — Made-up company or dead domain

- **Input:** `{"name":"Blue Banyan Haulage","website":"https://no-such-domain.invalid","request_text":"Verify proposed carrier"}`
- **Expected verdict:** CANNOT VERIFY if the company cannot be resolved; never SUSPECTED FRONT merely because lookup/site evidence is absent.
- **Expected key evidence:** resolve attempt/source status; missing identity and domain facts with explicit `cant_verify` reason, or `unknown` if a provider timed out.
- **Important flags:** no hard fraud flag from absence. Unknown source must remain unknown.
- **Why:** no record is not evidence of deception.

## T6 — Possible look-alike of a major logistics brand

- **Input:** `{"name":"DHL Logistics India","website":"https://dhl-logistics-india.example","request_text":"Verify whether this vendor is related to the established logistics brand"}`
- **Expected verdict:** HOLD FOR REVIEW for one evidenced hard concern; SUSPECTED FRONT only when actual evidence meets the configured threshold (two hard flags, or one hard plus two soft).
- **Expected key evidence:** name-resolved company vs domain-resolved company, official brand domain, normalized similarity, and any evidence of affiliation/authorization.
- **Important flags:** possible impersonation may be hard; do not infer affiliation or a front from the name alone.
- **Why:** the verdict engine's rules require corroborating flags before a SUSPECTED FRONT result.

## T7 — Entity first evidenced after September 2026, claiming an old founding year

- **Input:** `{"name":"FutureRoute Carriers","website":"https://futureroute.example","claimed_year":2014,"request_text":"Check claimed founding year against dated records"}`
- **Expected verdict:** timeline anomaly flagged; HOLD or SUSPECTED FRONT only according to the actual evidence and configured threshold.
- **Expected key evidence:** source record/first activity dated after `2026-09-01`, claimed year 2014, and the calculated age gap with dates attached.
- **Important flags:** age mismatch is a timeline concern. A later record date alone is not conclusive proof the entity was founded later.
- **Why:** the discrepancy needs investigation and should not be silently cleared; the source must actually support the timeline assertion.

## T8 — Duplicate vendor in client records or repeat submission

- **Input:** `{"name":"Existing Vendor Transport","website":"https://existing-vendor.example","request_text":"Duplicate onboarding fixture"}`
- **Expected verdict/status:** HOLD FOR REVIEW as duplicate; clearing must be blocked for an already-approved client vendor and repeated approval must return HTTP 409.
- **Expected key evidence:** client-record source row (or same normalized domain) and the matched vendor identity. A prior run should be linked if one exists.
- **Important flags:** duplicate; no second approval. Existing approval remains visible.
- **Why:** onboarding the same vendor again must not create a second independent clearance.

### Result recording

| Case | Expected | Actual |
|---|---|---|
| T1 | CLEARED only with all stated checks verified; otherwise cautious HOLD/CANNOT VERIFY | Not run against live sources; B/C data integrations absent |
| T2 | CLEARED only when `.in` and `.com` are evidenced as the same firm | Not run against live sources; B/C data integrations absent |
| T3 | CLEARED if innocent namesake is evidenced/cleared and core checks pass; otherwise HOLD | Not run against live sources; C media integration absent |
| T4 | HOLD / `awaiting_candidate` | Not run through API; data resolution absent |
| T5 | CANNOT VERIFY if unresolved; timeout remains unknown | Not run against live sources; B data integration absent |
| T6 | HOLD on one hard flag; FRONT only at configured threshold | Not run against live sources; look-alike implementation absent |
| T7 | Timeline anomaly flagged; verdict follows supported evidence/thresholds | Not run against live sources; timeline integration absent |
| T8 | HOLD duplicate; no duplicate approval | Not run against client records; duplicate implementation/data absent |

These are explicit pending outcomes, not successful or failed live checks. Synthetic fixture facts must never be inserted into a live run or represented as provider results.
