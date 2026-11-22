# Test cases (live)

Machine-readable inputs: [cases.live.json](cases.live.json) (CLI format from `config.yaml`). Run them with:

```sh
.venv/Scripts/python -m backend.cli --input tests/cases.live.json --output results.json --parallel 2 --client demo_3pl
```

`demo_3pl` uses [client_records.demo.json](client_records.demo.json), a labelled **demo stand-in** for the client's vendor list until the kickoff kit's records arrive. Every case uses real, live Crustdata and web data. The expected result was written from the rules *before* running. Actual results are in the README table.

Rule for fixing a wrong answer: make the rules more cautious; never special-case a vendor.

## T1: Honest, established carrier
- **Input:** Delhivery, `https://www.delhivery.com`
- **Expected:** CLEARED. The company resolves by domain, the director's current role is verified, activity is verified (headcount, hiring, traffic), the news screen is verified and nothing is flagged.
- **Why:** proves an honest firm can pass, and that clearing needs a completed news screen.

## T2: Director with a common name
- **Input:** Shadowfax, `https://www.shadowfax.in`, director "Abhishek Bansal"
- **Expected:** CLEARED if no news story names this director or company as accused. HOLD if a same-name story can't be cleared (unresolved).
- **Why:** namesake protection. A story about another "Abhishek Bansal" must never count against this director without its label and reason.

## T3: Look-alike of a big logistics brand
- **Input:** "Blue Dart Express" on the made-up domain `bluedart-express-india.com`
- **Expected:** HOLD FOR REVIEW. Look-alike hard flag ("possible impersonation of Blue Dart, official domain bluedart.com") plus a soft "domain not on the company record". SUSPECTED FRONT only if a second independent hard flag, or two softs, appear.
- **Why:** impersonation is caught with evidence, but one check alone never makes a front.

## T4: Made-up company, dead domain
- **Input:** "Blue Banyan Haulage Pvt Ltd" on `bluebanyanhaulage-carriers.in`
- **Expected:** CANNOT VERIFY, listing what is missing. Never SUSPECTED FRONT just because data is absent.

## T5: Name only, several possible companies
- **Input:** "Shree Logistics", no website
- **Expected:** waits for a person to pick the company (`awaiting_candidate`). The CLI reports this as HOLD FOR REVIEW with that reason. If Crustdata returns only one plausible match, the run continues normally.

## T6: Duplicate of an existing client vendor
- **Input:** TCI Express, `https://www.tciexpress.in`. The domain is in the demo client records.
- **Expected:** HOLD FOR REVIEW, rule `1_exact_duplicate` ("Already a client vendor: TCI Express Limited"). The API refuses to clear it, and a second decision gets 409.

## T7: Claims an older founding year than the record
- **Input:** Porter, `https://porter.in`, `claimed_year: 2001`. The request says "operated since 2001".
- **Expected:** `claimed_age_mismatch` hard (claim 2001 vs the record's founding year, gap over 2 years), so HOLD FOR REVIEW. It's soft instead if a source says "formerly known as / acquired by / rebranded".

## Offline tests
The rules, engine, data steps and web steps also have offline tests with fake API responses: `.venv/Scripts/python -m pytest -q backend` (no paid calls).
