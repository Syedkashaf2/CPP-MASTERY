"""Three-dimensional learning analytics (coverage, competence, and retention kept separate)."""
from __future__ import annotations

import datetime as dt
from collections import Counter
from typing import Any

from .config import EnginePaths, load_config, load_manifest, load_json
from .mistakes import aggregate_mistake_patterns, load_mistake_ledger
from .models import load_sessions
from .retention import load_retention_state, split_probes_by_tier


def _latest_source_date(
    manifest: dict[str, Any], sessions: list[tuple[Any, dict[str, Any]]], ret_state: dict[str, Any]
) -> str:
    dates = [str(manifest.get("baseline_date", "2026-11-11"))]
    for _, rec in sessions:
        if isinstance(rec.get("date"), str):
            dates.append(rec["date"])
    for p in ret_state.get("probes", []):
        if isinstance(p.get("completed_date"), str):
            dates.append(p["completed_date"])
    return max(dates)


def build_analytics(paths: EnginePaths, reference_date: dt.date | None = None) -> dict[str, Any]:
    """Compute strictly non-conflated metrics across coverage, competence, and retention."""
    cfg = load_config(paths)
    manifest = load_manifest(paths)
    sessions, _ = load_sessions(paths)
    ledger = load_mistake_ledger(paths)
    ret_state = load_retention_state(paths)

    ref_date = reference_date or dt.date.fromisoformat(_latest_source_date(manifest, sessions, ret_state))
    tiers = split_probes_by_tier(ret_state, ref_date)

    # Dimension 1: Learning coverage (baseline topics + session touches)
    session_topics: Counter[str] = Counter()
    for _, rec in sessions:
        for tid in rec.get("topic_ids", []):
            session_topics[tid] += 1

    baseline_topics = manifest.get("topics", [])
    studied_count = sum(1 for t in baseline_topics if t.get("coverage") == "studied")
    partial_count = sum(1 for t in baseline_topics if t.get("coverage") == "partial")
    not_studied_count = sum(1 for t in baseline_topics if t.get("coverage") == "not_studied")

    # Dimension 2: Demonstrated competence (strictly separate attempt & hint categories)
    attempt_counts: Counter[str] = Counter()
    hint_counts: Counter[str] = Counter()
    first_attempt_h0 = 0
    transfer_h0 = 0
    delayed_h0 = 0
    assisted_total = 0
    remediated_total = 0

    scored_h0: list[float] = []
    scored_assisted: list[float] = []

    for _, rec in sessions:
        atype = rec.get("attempt_type", "unknown")
        hlev = rec.get("hint_level", "unknown")
        attempt_counts[atype] += 1
        hint_counts[hlev] += 1
        score = rec.get("assessment", {}).get("score_percent")

        if hlev == "H0":
            if atype == "first_attempt":
                first_attempt_h0 += 1
            elif atype == "transfer":
                transfer_h0 += 1
            elif atype == "delayed_recall":
                delayed_h0 += 1
            if isinstance(score, (int, float)):
                scored_h0.append(float(score))
        elif hlev in ("H1", "H2", "H3", "H4"):
            assisted_total += 1
            if isinstance(score, (int, float)):
                scored_assisted.append(float(score))

        if atype == "remediation" or rec.get("record_type") == "correction":
            remediated_total += 1

    # Dimension 3: Retention (short-interval <7d vs long-term >=7d)
    short_probes = tiers["short_interval"]
    long_probes = tiers["long_term"]
    baseline_short_completed = len(ret_state.get("baseline_completed_short_interval", []))
    new_short_passed = sum(1 for p in short_probes if p.get("status") == "completed_passed")
    long_term_verified = sum(1 for p in long_probes if p.get("retention_verified") is True)
    short_pending = [p for p in short_probes if p.get("status") in ("scheduled", "due", "overdue")]
    long_pending = [p for p in long_probes if p.get("status") in ("scheduled", "due", "overdue")]

    # Mistakes & taxonomy
    mistakes = ledger.get("mistakes", [])
    open_mistakes = [m for m in mistakes if m.get("status") != "resolved_verified_delayed"]
    recurring_mistakes = [m for m in mistakes if m.get("recurred")]
    taxonomy_patterns = aggregate_mistake_patterns(ledger, manifest)

    # Snapshots list
    snapshots: list[dict[str, Any]] = []
    if paths.snapshots.exists():
        for d in sorted(paths.snapshots.iterdir(), reverse=True):
            meta = load_json(d / "snapshot_meta.json")
            if d.is_dir() and isinstance(meta, dict):
                snapshots.append({"name": d.name, **meta})

    return {
        "source_as_of": _latest_source_date(manifest, sessions, ret_state),
        "reference_date": ref_date.isoformat(),
        "timezone": cfg.get("timezone", "Asia/Kolkata"),
        "manifest": manifest,
        "sessions": sessions,
        "ledger": ledger,
        "retention_state": ret_state,
        "coverage": {
            "total_topics": len(baseline_topics),
            "studied": studied_count,
            "partial": partial_count,
            "not_studied": not_studied_count,
            "session_touches": dict(session_topics),
        },
        "competence": {
            "total_sessions": len(sessions),
            "attempt_counts": dict(attempt_counts),
            "hint_counts": dict(hint_counts),
            "first_attempt_h0": first_attempt_h0,
            "transfer_h0": transfer_h0,
            "delayed_h0": delayed_h0,
            "assisted_total": assisted_total,
            "remediated_total": remediated_total,
            "mean_h0_score": round(sum(scored_h0) / len(scored_h0), 1) if scored_h0 else None,
            "mean_assisted_score": (
                round(sum(scored_assisted) / len(scored_assisted), 1) if scored_assisted else None
            ),
        },
        "retention": {
            "baseline_short_completed": baseline_short_completed,
            "new_short_passed": new_short_passed,
            "short_pending": short_pending,
            "short_all": short_probes,
            "long_term_verified": long_term_verified,
            "long_pending": long_pending,
            "long_all": long_probes,
        },
        "mistakes": {
            "all_new": mistakes,
            "open_new": open_mistakes,
            "recurring_new": recurring_mistakes,
            "taxonomy_patterns": taxonomy_patterns,
        },
        "snapshots": snapshots,
    }
