# Handoff: Member D — Test Cases, Frontend & Delivery

> Read `00_PROJECT_BRIEF.md` first (idea, rules, contracts, backend API). Your folders: `frontend/`, `tests/`, `docs/`, `README.md`.
> Contracts change only through the Lead.

## Your mission
Organizers and judges experience Verity through your screens, README, diagram and video. Screening checks the **README, diagram and logs**; the finals score **Ethics** (explanations, personal data, approvals) and **Finance** (cost per job). A lot of that is visible only through your work. You also own the submission package, the one deadline we can't miss.

## Phase 0 · now → 11:20 · test cases FIRST
`tests/cases.md`: input, **expected result**, key facts, why. Dated **after 1 Sep 2026** where possible. Use the kickoff kit's client request + formats. Everyone adds; you own it.
1. Honest established carrier/supplier → CLEARED
2. Honest firm with `.in` + `.com` → look-alike must PASS
3. Director with a common name + a negative article about someone else → namesake cleared
4. Name only, several matches (vague) → held, a person picks
5. Made-up company / dead domain → CANNOT VERIFY (not "front")
6. Look-alike of a big logistics brand → SUSPECTED FRONT / HOLD
7. Founded after Sep 2026 but claims an old founding year → flagged
8. **Duplicate:** same vendor as one in the client's records (or submitted twice) → HOLD as duplicate, no second approval
Ask B for real recent companies (Company Search). Write each case in the **kickoff input format** too, so the Lead's CLI can run them all.

## Phase 1 · 11:20–12:45 · skeleton (needed for 1 PM)
Next.js (App Router) + Tailwind; backend URL from `NEXT_PUBLIC_API_URL`. **Mock the contract JSON locally until the Lead's API is up**, then switch.
1. **`/` New check**: vendor name*, website, director, claimed founding year, free-text request → `POST /runs` → `/runs/[id]`
2. **`/runs/[id]`**: poll `GET /runs/{id}` every 2 s while queued/running. Step list with status · credits and ₹ used vs limit · elapsed vs time limit · verdict + report when done.

## Phase 2 · 1:00–2:15 · the report (most important screen)
1. **Verdict badge:** CLEARED ✅ / SUSPECTED FRONT 🚩 / HOLD FOR REVIEW ⚠️ / CANNOT VERIFY ❔ + one-line reason
2. **4 answers:** Who runs it · How long it has existed · Is it trading · What looks off
3. **Explanation box** (from C): why, what would resolve it, namesakes cleared. Each sentence links to its evidence card.
4. **Evidence cards** grouped: Identity / Activity / Director / Duplicate / Domain / Website / Media / Timeline. Each card: claim, value, flag chip (hard red / soft amber / none grey), status chip (verified / can't verify / unknown), record date, **View source**. `cant_verify` shows "I can't verify: <missing>". `unknown` shows "Source timed out, retried 2×, held for a person".
5. **Source viewer** (`GET /sources/{id}`): API record → pretty JSON, **`field_path` highlighted and scrolled into view**, endpoint, retrieved date, record date. Web record → link `url#:~:text=...` + the passage quoted + retrieved date.
6. **Approval bar** (awaiting_approval): Clear vendor / Reject + **required reason** → `POST /runs/{id}/approve`. 409 → "Already decided by X at T". The decision stays visible.
7. **Candidate picker** (awaiting_candidate) and a **duplicate banner** ("Matches existing vendor X in client records" → link).

**2:15:** help the Lead submit on the portal.
**~1:15 requirement change:** if it adds an output field, show it on the report.

## Phase 3 · 2:30–4:30
- **Media panel:** each hit with title, link, label (match / namesake cleared / unresolved) + reason. Namesake cleared looks reassuring (green).
- **Copied-site panel**, **look-alike panel** (vendor domain vs official domain + score), **timeline** (a sorted list is fine; anomalies in red)
- **Personal data panel (Ethics):** table from `personal_data` with person, field, source, purpose + note "Only fields needed for this check are stored."
- **Ledger tab:** calls with provider, endpoint/model, credits, tokens, ₹, latency, status. Totals: "This check: 142 credits · ₹3.10 · 41 s" (this is the Finance proof) + Crustdata balance from `/credits`.
- **`/history`:** runs, verdict, decision, date; duplicates link to earlier runs.

Keep the UI clean, compliance-tool style, every fact one click from its source. No animation work before 4:30.

## Delivery: your top priority after 4:30
**Architecture diagram** (start 3:30, Excalidraw/Mermaid → `docs/architecture.png`). It **must show:** components, data flow, **where the data calls happen (Crustdata endpoints, LLM), approvals, retries/timeouts, the cost ledger, checkpoint/resume**.
`UI / CLI → FastAPI → Run engine (steps + checkpoints, ceilings) → Crustdata + LLM (via retrying client → sources + ledger) → checks → verdict rules → explanation → Human approval (exactly once) → output in kickoff format`

**README.md** (skeleton by 2:30, final by 5:30), with the organizer-required items marked ★:
1. ★ The job + **who pays for it today** (3PL compliance/procurement teams, verification firms paid per vendor)
2. ★ **Input** (kickoff format) · ★ **Finished result** (vendor cleared/rejected with evidence on file) · ★ **Pass mark** (e.g. correct verdict per test case; wrong < cannot verify; every claim sourced)
3. ★ **Every data source called** (each Crustdata endpoint, web, LLM, client records) (B's input)
4. ★ Architecture diagram
5. How sources/claims link (field + date) · verdict rules · cannot verify · timeouts
6. Ceilings, ledger, crash/resume, exactly-once approvals
7. **Ethics:** data minimisation, personal-data log, namesake protection, approvals, explanations, no contact with real people, retention
8. **Finance:** buyer, ₹ price, **measured cost per check** (from the ledger), comparison with the manual cost (the Lead provides numbers)
9. **Test results: expected vs actual** (the Lead fills in 4:30–5:00)
10. Approaches considered + why we chose this one (Lead) · known limits · next steps
11. Setup / run (UI + CLI) + env vars (B) · open-source credits · team + who built what · "repo history starts at kickoff; nothing written beforehand"

**2-min demo video** (record 5:00–5:30, Loom/unlisted YouTube, link in README):
1. 0:00–0:15 Problem: "A 3PL pays a new carrier. Is it real? Fronts carry genuine papers."
2. 0:15–0:45 Honest carrier → CLEARED; click a claim → exact field; namesake cleared
3. 0:45–1:15 Front / look-alike / duplicate → flags with evidence
4. 1:15–1:35 Kill the server mid-run → restart → it resumes, nothing repeats
5. 1:35–2:00 Person approves with a reason (once) · ledger: credits, ₹, time per check
**Live system only. No mocks shown as live.**

## Done means
- [ ] Test cases written in both readable and kickoff formats
- [ ] Every evidence card opens its exact source
- [ ] cannot-verify / unknown / duplicate / candidate states all visible
- [ ] Approval works once; the second attempt shows already decided
- [ ] Personal-data panel + ledger totals visible
- [ ] README (all ★ items) + diagram + video committed **before 6:00 PM**

## Don'ts
No fake data in the final build or video · don't block on the backend (mock the contract) · polish last
