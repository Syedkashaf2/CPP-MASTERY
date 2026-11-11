# CPP-MASTERY — System Architecture & User Guide

**Language Standard:** C++17
**Automation Engine:** `scripts/mastery_engine.py` (Python 3.10+, standard library only)
**Governing Baseline:** `docs/baseline/` (Audit date: `2026-11-11`)

---

## 1. System Layers (Strict Separation of Truth)

| Layer | Path | Mutable? | Purpose |
|---|---|---|---|
| **1. Immutable Baseline** | `docs/baseline/*.md`, `.mastery/baseline_manifest.json` | No (SHA-256 locked) | Historical audit (`A–L`), cognitive state ledger (`C0.1–C10`), and Protocol V2.1 |
| **2. Session Truth** | `.mastery/records/sessions/*.json` | Append-only | Reviewed session, correction, and retention probe records (`M-020+`, `E-042+`) |
| **3. Objective Evidence** | `.mastery/evidence/*.json` | Machine-generated | Git branch/HEAD/status/file hashes and explicit C++ compile/test outputs |
| **4. Gemini Inbox** | `.mastery/inbox/*.json` | Untrusted staging | AI-generated JSON drafts (`review_status: "pending"`) awaiting human approval |
| **5. Generated Views** | `docs/progress/*.md`, `docs/progress/MASTERY_DASHBOARD.html` | Auto-generated | Reproducible projections rendered by `rebuild` and `dashboard` |
| **6. Retention Queue** | `.mastery/records/retention_state.json` | Engine-managed | Active delayed-recall probes (`R-009`–`R-016` seeded, plus `R-017+`) |
| **7. Snapshots** | `.mastery/snapshots/<UTC>/` | Timestamped copies | Point-in-time archives of generated reports, dashboard, and ledgers |

---

## 2. Gemini Assessment Workflow (Review-First, Zero Secrets)

The engine never scrapes private Gemini conversations and stores zero API keys in the repository.

1. **Collect objective evidence:**
   ```bash
   python3 scripts/mastery_engine.py collect
   python3 scripts/mastery_engine.py test -- 'g++ -std=c++17 -Wall -Wextra -Wpedantic solutions/Q1.cpp -o build/Q1.out && ./build/Q1.out'
   ```
2. **Generate an inbox draft (optional helper):**
   ```bash
   python3 scripts/mastery_engine.py new-inbox --topics T-023 --probe R-013 --files solutions/Q1.cpp
   ```
3. **Ask Gemini to assess:** Provide Gemini with `prompts/GEMINI_SESSION_ASSESSOR.md`, your session transcript, your C++ code, and the objective output from `.mastery/evidence/`. Paste Gemini's single JSON object into `.mastery/inbox/<file>.json`.
4. **Human review:** Verify every field using `prompts/SESSION_REVIEW_CHECKLIST.md`. Set:
   - `"review_status": "accepted"`
   - `"reviewed_by_human": true`
   - `"reviewed_at": "YYYY-MM-DDTHH:MM:SS+05:30"`
5. **Import & regenerate:**
   ```bash
   python3 scripts/mastery_engine.py import-record .mastery/inbox/<file>.json
   python3 scripts/mastery_engine.py validate --check-docs
   ```
   `import-record` automatically syncs `.mastery/records/mistake_ledger.json`, updates the retention ladder in `.mastery/records/retention_state.json`, rebuilds `docs/progress/*.md`, and refreshes `docs/progress/MASTERY_DASHBOARD.html`.

*Optional future API note:* If a direct Gemini API wrapper is ever added locally, it must read credentials solely from a local environment variable (e.g., `GEMINI_API_KEY`), never commit secrets, and still write drafts into `.mastery/inbox/` with `"review_status": "pending"`.

---

## 3. Retention Algorithm (`[1, 3, 7, 14, 30]` Days)

- **Seeded baseline probes:** `R-009` through `R-016` from `CPP_COGNITIVE_STATE_LEDGER.md` Section C7 (`R-001`–`R-008` remain historical short-interval records).
- **Two strictly separated tiers:**
  - **Short-interval (`< 7 days`):** `+1d` and `+3d` checks. Passing does **not** set `retention_verified: true`.
  - **Long-term (`>= 7 days`):** `+7d`, `+14d`, and `+30d` checks. `retention_verified: true` is granted **only** when passed unassisted (`hint_level == "H0"`).
- **Advancement vs. Reset:**
  - Passing a probe at `H0` schedules the next interval tier (`1 -> 3 -> 7 -> 14 -> 30`).
  - Failing or using `H1–H4` assistance resets the topic back to `+1d`.

---

## 4. VS Code Tasks

Open `CPP-MASTERY` in VS Code (WSL Ubuntu) and run **Terminal -> Run Task**:
- `Mastery: Collect Git Evidence`
- `Mastery: Compile & Test Active C++ File (C++17)` (default test task)
- `Mastery: Create Inbox Assessment Draft`
- `Mastery: Import Reviewed Session Record`
- `Mastery: Check Retention Probes`
- `Mastery: Rebuild Documentation`
- `Mastery: Update Dashboard`
- `Mastery: Create Snapshot`
- `Mastery: Validate Records & Tests`
- `Mastery: Prepare Git Review`

---

## 5. GitHub CI & Review-First Sync

- CI workflow: `.github/workflows/mastery-validation.yml` runs Python syntax checks, `unittest`, `validate --check-docs` (baseline SHA-256 verification + schemas + duplicate/reference checks + generated doc sync), and `g++ -std=c++17` syntax checks.
- Local review before committing:
  ```bash
  python3 scripts/mastery_engine.py git-review
  git status --short
  git diff
  ```
