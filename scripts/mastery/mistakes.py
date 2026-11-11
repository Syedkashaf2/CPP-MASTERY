"""Persistent mistake ledger management, recurrence tracking, and C3 taxonomy grouping."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from .config import EnginePaths, dump_json, load_json


def load_mistake_ledger(paths: EnginePaths) -> dict[str, Any]:
    data = load_json(paths.mistake_ledger)
    if not isinstance(data, dict):
        return {
            "schema_version": "1.0.0",
            "next_mistake_number": 20,
            "baseline_reserved_range": "M-001 to M-019 (preserved read-only in docs/baseline/)",
            "mistakes": [],
        }
    return data


def save_mistake_ledger(paths: EnginePaths, ledger: dict[str, Any]) -> None:
    dump_json(paths.mistake_ledger, ledger)


def sync_mistakes_from_session(
    paths: EnginePaths, rec: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, Any]:
    """Register new session mistakes (M-020+) and track recurrences without overwriting history."""
    ledger = load_mistake_ledger(paths)
    mistakes_list: list[dict[str, Any]] = ledger.setdefault("mistakes", [])
    next_num = int(ledger.get("next_mistake_number", 20))
    hist_mistakes = set(manifest.get("reserved_ids", {}).get("historical_mistakes", []))
    by_id = {m["mistake_id"]: m for m in mistakes_list if isinstance(m, dict) and "mistake_id" in m}

    sid = rec["session_id"]
    topics = rec.get("topic_ids", [])
    tasks = rec.get("task_ids", [])

    for entry in rec.get("mistakes", []):
        if not isinstance(entry, dict):
            continue
        rec_of = entry.get("recurrence_of")
        if rec_of and rec_of in by_id:
            target = by_id[rec_of]
            target["recurred"] = True
            sessions = target.setdefault("recurrence_sessions", [])
            if sid not in sessions:
                sessions.append(sid)
            if target.get("status") == "resolved_verified_delayed":
                target["status"] = "remediation_in_progress"
                target["reproduced_independently"] = False

        raw_mid = entry.get("mistake_id")
        if raw_mid in (None, "auto"):
            mid = f"M-{next_num:03d}"
            while mid in by_id or mid in hist_mistakes:
                next_num += 1
                mid = f"M-{next_num:03d}"
            entry["mistake_id"] = mid
            next_num += 1
        else:
            mid = str(raw_mid)
            if mid.startswith("M-") and mid[2:].isdigit():
                next_num = max(next_num, int(mid[2:]) + 1)

        if mid in by_id:
            existing = by_id[mid]
            existing["recurred"] = True
            sessions = existing.setdefault("recurrence_sessions", [])
            if sid not in sessions:
                sessions.append(sid)
            existing["status"] = entry.get("status", existing.get("status", "open"))
            existing["reproduced_independently"] = bool(
                entry.get("reproduced_independently", existing.get("reproduced_independently", False))
            )
            continue

        new_entry: dict[str, Any] = {
            "mistake_id": mid,
            "source_session_id": sid,
            "topic_ids": list(topics),
            "task_ids": list(tasks),
            "taxonomy_class": entry.get(
                "taxonomy_class",
                manifest.get("taxonomy_classes", ["Update-Ordering Fault"])[0],
            ),
            "original_incorrect_reasoning": entry.get("original_incorrect_reasoning", ""),
            "root_cause": entry.get("root_cause", ""),
            "observable_symptom": entry.get("observable_symptom", ""),
            "correction": entry.get("correction", ""),
            "reproduced_independently": bool(entry.get("reproduced_independently", False)),
            "recurred": bool(rec_of is not None),
            "recurrence_sessions": [sid] if rec_of else [],
            "recurs_from_baseline_id": rec_of if rec_of in hist_mistakes else None,
            "related_concepts": list(entry.get("related_concepts", [])),
            "status": entry.get("status", "open"),
        }
        mistakes_list.append(new_entry)
        by_id[mid] = new_entry

    ledger["next_mistake_number"] = next_num
    save_mistake_ledger(paths, ledger)
    return ledger


def aggregate_mistake_patterns(
    ledger: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, dict[str, int]]:
    """Group baseline (M-001..M-019) and new (M-020+) mistakes by C3 taxonomy class."""
    groups: dict[str, dict[str, int]] = defaultdict(
        lambda: {"baseline_count": 0, "new_open": 0, "new_resolved": 0, "recurring_count": 0}
    )
    for tax in manifest.get("taxonomy_classes", []):
        _ = groups[tax]

    for bm in manifest.get("historical_mistakes_summary", []):
        tax = bm.get("taxonomy_class", "Uncategorized")
        groups[tax]["baseline_count"] += 1
        if bm.get("recurrence") in ("once", "repeated"):
            groups[tax]["recurring_count"] += 1

    for nm in ledger.get("mistakes", []):
        tax = nm.get("taxonomy_class", "Uncategorized")
        if nm.get("status") == "resolved_verified_delayed":
            groups[tax]["new_resolved"] += 1
        else:
            groups[tax]["new_open"] += 1
        if nm.get("recurred"):
            groups[tax]["recurring_count"] += 1

    return dict(groups)
