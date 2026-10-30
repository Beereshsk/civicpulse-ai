# Limitations and responsible use

## AI and evidence

- No LLM or embedding API is configured in the current workspace. Category suggestions, summaries, risk cues, duplicate candidates, and brief copy therefore use deterministic local code. An optional OpenAI-compatible server-side adapter exists; it is opt-in and has not been verified against a live provider here.
- Text rules can miss idioms, multilingual reports, context, sarcasm, and hazards not covered by the configured terms. A category suggestion is not a verified fact. Rule confidence is a heuristic, not a calibrated probability.
- Safety terms trigger human review. No safety term is not evidence that a report is safe; missing details should be verified by a person.
- Action briefs count saved records in code. They use a template, cite the included report IDs, and cannot establish a shared cause.

## Priority scoring

- Safety, severity, impact, and age use simple heuristic scores and prototype weights (40/25/20/15). These are not validated public policy, service-level commitments, or a substitute for dispatcher judgment.
- Severity and impact infer signals from report wording, not inspection. Age grows linearly to its cap at 14 days. Scores will shift as records age, and the thresholds are illustrative.
- The score supports triage only. Review the component values and original report before acting, especially for safety-related descriptions.

## Duplicate matching

- The fallback combines character similarity, token overlap, same-category compatibility, and distance where coordinates exist. The threshold is configurable in `intelligence.py` and scores are not probabilities.
- It has no semantic embeddings, language normalization, address geocoding, calibrated evaluation set, or shared-cause model. Similar locations/categories alone do not produce candidates without a text signal.
- Operator link/dismiss decisions are stored as a separate record; source reports and their history are preserved. The current UI records decisions but does not merge reports.

## Geographic analysis

- Seed report coordinates are deliberately fictional and displayed on a labeled schematic grid, not on a live map. They must not be read as real geography or an actual civic hotspot.
- Clustering is a greedy 500 m radius grouping with a minimum of three located reports. Results can depend on seed order and do not prove a common cause. Reports without coordinates are excluded.
- Newly submitted coordinates are accepted as supplied; the app does not geocode or verify them.

## Security and operations

- The prototype binds to `127.0.0.1` by default and has no authentication or role authorization. Operator write routes and demo reset are therefore suitable only for a trusted local session. Do not expose it to a public or shared network.
- Citizen tracking IDs are unique demo tokens, but there is no rate limiting, abuse detection, retention policy, consent workflow, or hardened privacy/security review.
- Images are stored under `static/uploads`; there is no malware scanning or production object storage. Use only fictional demo images.
- SQLite is a local single-machine store. There is no backup, multi-user conflict handling, encryption at rest, government integration, deployment pipeline, or production monitoring.
- Error messages are intended for a local prototype. Review and harden validation, authorization, logging, and retention before any real-world use.
