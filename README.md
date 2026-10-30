# CivicPulse AI

**From complaints to action.** A local civic-operations prototype for the PromptWars × ASTRA AI for Civic Impact hackathon. It demonstrates citizen intake, transparent issue analysis, operator review, hotspot signals, action briefs, and citizen-visible progress using fictional reports.

## Run locally

Requirements: Python 3.9+ (developed with Python 3.13). The application uses only Python's standard library; there is no package install step or frontend build step.

```powershell
python app.py
```

Open <http://127.0.0.1:8000>. Stop the server with Ctrl+C. On first launch, CivicPulse creates `civicpulse.sqlite3` and seeds 45 fictional records. To use another port or database path:

```powershell
$env:PORT = "8080"
$env:CIVICPULSE_DB = "$PWD\civicpulse-demo.sqlite3"
python app.py
```

Use **Reset demo** in the report queue to restore the original synthetic records and remove new records or operator changes. The reset is intentionally destructive to this local demo database and asks for confirmation first.

## What works

- **Capture:** description, category, landmark/address, optional coordinates, optional PNG/JPG/WebP image (2 MB maximum), field validation, saved confirmation, unique report reference and tracking ID.
- **Understand:** keyword categorization, concise summary, severity/impact/urgency signals, confidence, uncertainty text, safety review flag, and weighted priority breakdown. Without opt-in provider credentials, this stage uses the deterministic local engine.
- **Duplicates:** transparent lexical overlap, category compatibility, and distance signals. Similarity is a score, not a probability or verdict. Operators can link or dismiss candidates; original reports remain intact.
- **Reveal:** live statistics from SQLite records, trend and category charts, a synthetic coordinate grid, nearby report clusters, and an evidence-counted template brief with supporting report IDs.
- **Act:** operator can assign a department, update status, add private internal notes, publish citizen-visible updates, record resolution detail, inspect history, and record duplicate decisions.
- **Track:** citizens look up a saved report using its tracking ID. The server returns a field allowlist and public updates only; internal notes and the operator history are not returned.

## Architecture

```text
Browser UI (static HTML/CSS/JS)
        │ JSON over same-origin HTTP
Python stdlib ThreadingHTTPServer (app.py)
   ├── SQLite persistence (reports, activity, duplicate decisions)
   ├── civic_engine/ (typed model adapter and independent analysis modules)
   └── seed_data.py (repeatable fictional demo records)
```

The optional server-side OpenAI-compatible adapter is in `civic_engine/llm.py`. It only sends requests when `CIVICPULSE_LLM_ENABLED=1`, `CIVICPULSE_LLM_API_KEY`, and `CIVICPULSE_LLM_MODEL` are all set. `CIVICPULSE_LLM_BASE_URL` optionally changes the compatible endpoint. The current environment has no provider configuration, so reports and briefs use local rules/templates. A real provider call has not been verified in this workspace.

Set these environment variables in the server process to opt in (never put the key in browser code):

```powershell
$env:CIVICPULSE_LLM_ENABLED = "1"
$env:CIVICPULSE_LLM_API_KEY = "your-server-side-key"
$env:CIVICPULSE_LLM_MODEL = "your-compatible-model"
# Optional for an OpenAI-compatible provider:
$env:CIVICPULSE_LLM_BASE_URL = "https://provider.example/v1"
python app.py
```

The adapter has an 8-second request timeout. Missing credentials, timeout, provider errors, and malformed JSON fall back to local summaries/templates. Priority values and duplicate matches are always calculated in application code.

Priority uses normalized component scores from 0-100 and weights safety 40%, severity 25%, potential impact 20%, and complaint age 15%. The application computes contributions and rounds the sum half-up (so 64.5 becomes 65). Labels use prototype thresholds: Critical 85+, High 65-84, Medium 35-64, Low under 35. A possible immediate safety hazard is flagged for human review. See [LIMITATIONS.md](LIMITATIONS.md) for the decision boundaries and non-production scope.

## Automated checks

```powershell
python -m unittest discover -s tests -v
```

Tests cover the weighted score and safety flag, rule categorization, duplicate behavior, hotspot and brief evidence, status validation, seeded API counts, citizen submission, operator updates, and public/private field separation.

## Five-minute demo script

1. **0:00–0:35 — Reveal:** open the dashboard. Point out that totals are computed from 45 saved synthetic reports, and call out the prototype scoring caveat.
2. **0:35–1:20 — Find a signal:** open Report queue, filter priority to High or Critical, and inspect a hazard. Show the individual factor contributions, safety review flag, and candidate similarity explanations.
3. **1:20–2:00 — Place and evidence:** return to Overview. Select a hotspot and walk through its report count, unresolved/high-priority counts, evidence IDs, and uncertainty note. Explain that the grid coordinates and pattern are synthetic.
4. **2:00–3:00 — Citizen capture:** submit a report for “A deep pothole near the north school crossing creates a hazard” at “Fictional Cedar Lane.” Choose Roads and potholes. Copy the displayed `TRK-…` tracking ID.
5. **3:00–4:10 — Operator action:** open the new report in the queue, assign Public Works, set In Progress, add an internal note and a separate public update. Save and show the activity history.
6. **4:10–4:45 — Citizen follow-up:** open Track a report and enter the copied tracking ID. Confirm the citizen sees In Progress and the public update, while the internal note is absent.
7. **4:45–5:00 — Close honestly:** state that this workspace uses deterministic rules and template brief output; no live LLM call, city system, or map service is connected.

## Scope

This is a local hackathon demo, not a deployed civic service. The local operator routes have no authentication and must not be exposed to a network. Read [LIMITATIONS.md](LIMITATIONS.md) before interpreting scores or demo geography.
