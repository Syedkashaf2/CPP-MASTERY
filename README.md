# CPP-MASTERY

Evidence-driven C++17 foundation mastery, mistake forensics, and delayed-retention tracking system.

## Core Design Principles

1. **Three separate dimensions:** Learning coverage, demonstrated competence, and long-term retention are never merged into a single percentage.
2. **Immutable historical baseline:** `docs/baseline/` files are locked via SHA-256 checksums in `.mastery/baseline_manifest.json` and never overwritten.
3. **Human-gated Gemini assessment:** Gemini outputs a structured JSON draft into `.mastery/inbox/`; you inspect it against `prompts/SESSION_REVIEW_CHECKLIST.md` before importing into `.mastery/records/sessions/`.
4. **Review-first Git synchronization:** The engine collects evidence, validates integrity, and displays diffs; you explicitly stage, commit, and push.

## Quick Commands

```bash
python3 scripts/mastery_engine.py collect
python3 scripts/mastery_engine.py test -- 'g++ -std=c++17 -Wall -Wextra -Wpedantic solutions/Q1.cpp -o build/Q1.out && ./build/Q1.out'
python3 scripts/mastery_engine.py new-inbox --topics T-023 --probe R-013 --files solutions/Q1.cpp
python3 scripts/mastery_engine.py import-record .mastery/inbox/<file>.json
python3 scripts/mastery_engine.py retention
python3 scripts/mastery_engine.py rebuild
python3 scripts/mastery_engine.py dashboard
python3 scripts/mastery_engine.py validate --check-docs
python3 scripts/mastery_engine.py git-review
```

See [DOCS.md](./DOCS.md) for the complete system architecture, Gemini workflow, VS Code tasks, and retention rules.
