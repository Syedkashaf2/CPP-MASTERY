# Mastery State Storage

- `baseline_manifest.json` locks SHA-256 hashes and reserved historical IDs from `docs/baseline/`. Do not alter.
- `inbox/` holds untrusted Gemini JSON drafts awaiting human review (`.gitignored`).
- `records/sessions/` holds immutable, human-reviewed session, correction, and retention probe records (source of truth).
- `records/mistake_ledger.json` tracks new mistakes (`M-020+`), recurring patterns, and verification status.
- `records/retention_state.json` tracks delayed-recall probes (`R-009`..`R-016` seeded from baseline + `R-017+`).
- `evidence/` holds objective machine-collected Git snapshots and explicitly executed C++ compile/test logs (`.gitignored`).
- `snapshots/` holds timestamped copies of generated reports and dashboard HTML (`.gitignored`).
- `templates/` holds clean JSON templates for sessions and retention policy.

## Rules
- Never put API keys, credentials, or secrets anywhere in `.mastery/`.
- Never hand-edit generated files under `docs/progress/` as the source of truth; edit or import records and run `python3 scripts/mastery_engine.py rebuild`.
- Never modify the immutable historical baseline files under `docs/baseline/`.
