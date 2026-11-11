"""Configurable delayed-recall scheduler (1, 3, 7, 14, 30 days) with short vs long-term split."""
from __future__ import annotations

import datetime as dt
from typing import Any

from .config import EnginePaths, dump_json, load_config, load_json, today_local

DEFAULT_INTERVALS = [1, 3, 7, 14, 30]


def load_retention_state(paths: EnginePaths) -> dict[str, Any]:
    data = load_json(paths.retention_state)
    if not isinstance(data, dict):
        return {
            "schema_version": "1.0.0",
            "next_probe_number": 17,
            "baseline_completed_short_interval": [f"R-{i:03d}" for i in range(1, 9)],
            "probes": [],
        }
    return data


def save_retention_state(paths: EnginePaths, state: dict[str, Any]) -> None:
    dump_json(paths.retention_state, state)


def tier_for_interval(interval_days: int, long_term_threshold: int = 7) -> str:
    return "long_term" if interval_days >= long_term_threshold else "short_interval"


def next_interval_days(current_days: int, intervals: list[int]) -> int | None:
    ordered = sorted(set(intervals))
    for step in ordered:
        if step > current_days:
            return step
    return None


def effective_probe_timing(probe: dict[str, Any], today: dt.date) -> str:
    status = probe.get("status", "scheduled")
    if status in ("completed_passed", "completed_failed", "completed_assisted", "waived"):
        return status
    try:
        due = dt.date.fromisoformat(probe["scheduled_date"])
    except Exception:
        return status
    if due < today:
        return "overdue"
    if due == today:
        return "due"
    return "scheduled"


def _alloc_probe_id(state: dict[str, Any], existing_ids: set[str]) -> str:
    num = int(state.get("next_probe_number", 17))
    pid = f"R-{num:03d}"
    while pid in existing_ids:
        num += 1
        pid = f"R-{num:03d}"
    state["next_probe_number"] = num + 1
    existing_ids.add(pid)
    return pid


def sync_retention_from_session(paths: EnginePaths, rec: dict[str, Any]) -> dict[str, Any]:
    """Update retention queue on session import; never verify long-term retention without H0 >=7d."""
    cfg = load_config(paths)
    intervals = list(cfg.get("retention_intervals_days", DEFAULT_INTERVALS))
    long_term_threshold = int(cfg.get("long_term_threshold_days", 7))
    state = load_retention_state(paths)
    probes: list[dict[str, Any]] = state.setdefault("probes", [])
    by_id = {p["probe_id"]: p for p in probes if isinstance(p, dict) and "probe_id" in p}
    existing_ids = set(by_id.keys()) | set(state.get("baseline_completed_short_interval", []))

    sid = rec["session_id"]
    sess_date = dt.date.fromisoformat(rec["date"])
    hint_level = rec.get("hint_level", "unknown")
    hints_used = list(rec.get("independence", {}).get("hints_used", []))
    ev_ids = rec.get("evidence", {}).get("evidence_ids", [])
    src_ev = ev_ids[0] if ev_ids else sid

    ret_block = rec.get("retention", {})
    attempted_id = ret_block.get("probe_id_attempted")
    outcome = ret_block.get("probe_outcome")

    # 1) Update an attempted retention probe if specified
    if attempted_id and attempted_id in by_id:
        target = by_id[attempted_id]
        target["completed_date"] = rec["date"]
        target["completed_session_id"] = sid
        target["hint_level"] = None if hint_level == "unknown" else hint_level
        target["hints_used"] = hints_used
        target["independent_result"] = rec.get("assessment", {}).get("summary", "")

        passed_unassisted = outcome == "passed" and hint_level == "H0"
        if passed_unassisted:
            target["status"] = "completed_passed"
            target["retention_verified"] = target["tier"] == "long_term"
            next_days = next_interval_days(int(target["interval_days"]), intervals)
            if next_days is not None:
                new_id = _alloc_probe_id(state, existing_ids)
                probes.append(
                    {
                        "probe_id": new_id,
                        "topic_id": target["topic_id"],
                        "source_evidence_id": src_ev,
                        "source_session_id": sid,
                        "probe_type": target.get("probe_type", "Delayed Recall"),
                        "task_summary": f"Follow-up {next_days}d cold retrieval for {target['topic_id']} (after {attempted_id}).",
                        "interval_days": next_days,
                        "tier": tier_for_interval(next_days, long_term_threshold),
                        "scheduled_date": (sess_date + dt.timedelta(days=next_days)).isoformat(),
                        "status": "scheduled",
                        "completed_date": None,
                        "completed_session_id": None,
                        "hint_level": None,
                        "hints_used": [],
                        "independent_result": None,
                        "retention_verified": False,
                    }
                )
        elif outcome == "assisted" or (outcome == "passed" and hint_level in ("H1", "H2", "H3", "H4")):
            target["status"] = "completed_assisted"
            target["retention_verified"] = False
            reset_days = intervals[0] if intervals else 1
            new_id = _alloc_probe_id(state, existing_ids)
            probes.append(
                {
                    "probe_id": new_id,
                    "topic_id": target["topic_id"],
                    "source_evidence_id": src_ev,
                    "source_session_id": sid,
                    "probe_type": "Unassisted Re-Probe",
                    "task_summary": f"Reset +{reset_days}d H0 retrieval for {target['topic_id']} after assisted attempt ({attempted_id}).",
                    "interval_days": reset_days,
                    "tier": tier_for_interval(reset_days, long_term_threshold),
                    "scheduled_date": (sess_date + dt.timedelta(days=reset_days)).isoformat(),
                    "status": "scheduled",
                    "completed_date": None,
                    "completed_session_id": None,
                    "hint_level": None,
                    "hints_used": [],
                    "independent_result": None,
                    "retention_verified": False,
                }
            )
        elif outcome == "failed":
            target["status"] = "completed_failed"
            target["retention_verified"] = False
            reset_days = intervals[0] if intervals else 1
            new_id = _alloc_probe_id(state, existing_ids)
            probes.append(
                {
                    "probe_id": new_id,
                    "topic_id": target["topic_id"],
                    "source_evidence_id": src_ev,
                    "source_session_id": sid,
                    "probe_type": "Post-Failure Re-Probe",
                    "task_summary": f"Reset +{reset_days}d retrieval for {target['topic_id']} after failed probe ({attempted_id}).",
                    "interval_days": reset_days,
                    "tier": tier_for_interval(reset_days, long_term_threshold),
                    "scheduled_date": (sess_date + dt.timedelta(days=reset_days)).isoformat(),
                    "status": "scheduled",
                    "completed_date": None,
                    "completed_session_id": None,
                    "hint_level": None,
                    "hints_used": [],
                    "independent_result": None,
                    "retention_verified": False,
                }
            )

    # 2) Add any explicitly scheduled probes from the session record
    explicit_topics: set[str] = set()
    for ps in ret_block.get("probes_scheduled", []):
        if not isinstance(ps, dict):
            continue
        tid = ps.get("topic_id")
        due_str = ps.get("due_date")
        if not tid or not due_str:
            continue
        explicit_topics.add(tid)
        due_date = dt.date.fromisoformat(due_str)
        days = int(ps.get("interval_days") or max(1, (due_date - sess_date).days))
        raw_pid = ps.get("probe_id")
        pid = raw_pid if raw_pid and raw_pid not in existing_ids else _alloc_probe_id(state, existing_ids)
        existing_ids.add(pid)
        probes.append(
            {
                "probe_id": pid,
                "topic_id": tid,
                "source_evidence_id": src_ev,
                "source_session_id": sid,
                "probe_type": "Session Follow-up",
                "task_summary": ps.get("task_summary") or f"Delayed check for {tid} from {sid}",
                "interval_days": days,
                "tier": tier_for_interval(days, long_term_threshold),
                "scheduled_date": due_str,
                "status": "scheduled",
                "completed_date": None,
                "completed_session_id": None,
                "hint_level": None,
                "hints_used": [],
                "independent_result": None,
                "retention_verified": False,
            }
        )

    # 3) Auto-schedule initial +1d probe for new session topics that lack an active open probe
    if rec.get("record_type") in ("session", "correction") and intervals:
        open_topics = {
            p["topic_id"]
            for p in probes
            if p.get("status") in ("scheduled", "due", "overdue")
        }
        first_days = intervals[0]
        for tid in rec.get("topic_ids", []):
            if tid not in open_topics and tid not in explicit_topics:
                pid = _alloc_probe_id(state, existing_ids)
                probes.append(
                    {
                        "probe_id": pid,
                        "topic_id": tid,
                        "source_evidence_id": src_ev,
                        "source_session_id": sid,
                        "probe_type": "Auto-Scheduled +1d",
                        "task_summary": f"Cold retrieval check for {tid} practiced in {sid}.",
                        "interval_days": first_days,
                        "tier": tier_for_interval(first_days, long_term_threshold),
                        "scheduled_date": (sess_date + dt.timedelta(days=first_days)).isoformat(),
                        "status": "scheduled",
                        "completed_date": None,
                        "completed_session_id": None,
                        "hint_level": None,
                        "hints_used": [],
                        "independent_result": None,
                        "retention_verified": False,
                    }
                )
                open_topics.add(tid)

    save_retention_state(paths, state)
    return state


def split_probes_by_tier(
    state: dict[str, Any], today: dt.date | None = None
) -> dict[str, list[dict[str, Any]]]:
    ref_day = today or dt.date.today()
    short_term: list[dict[str, Any]] = []
    long_term: list[dict[str, Any]] = []
    for p in state.get("probes", []):
        item = dict(p)
        item["effective_status"] = effective_probe_timing(p, ref_day)
        if p.get("tier") == "long_term":
            long_term.append(item)
        else:
            short_term.append(item)
    short_term.sort(key=lambda x: (x.get("scheduled_date", ""), x.get("probe_id", "")))
    long_term.sort(key=lambda x: (x.get("scheduled_date", ""), x.get("probe_id", "")))
    return {"short_interval": short_term, "long_term": long_term}


def format_retention_cli(paths: EnginePaths, due_only: bool = False) -> str:
    cfg = load_config(paths)
    today = today_local(cfg)
    state = load_retention_state(paths)
    tiers = split_probes_by_tier(state, today)
    lines = [f"# Retention Probe Queue (as of {today.isoformat()})", ""]

    for title, key in [
        ("Short-Interval Probes (< 7 days)", "short_interval"),
        ("Long-Term Retention Probes (>= 7 days)", "long_term"),
    ]:
        lines.append(f"## {title}")
        items = tiers[key]
        if due_only:
            items = [x for x in items if x["effective_status"] in ("due", "overdue")]
        else:
            items = [x for x in items if x["effective_status"] in ("scheduled", "due", "overdue")]
        if not items:
            lines.append("_None pending._\n")
            continue
        lines.append("| Probe | Topic | Interval | Scheduled | Timing | Task |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for x in items:
            lines.append(
                f"| {x['probe_id']} | {x['topic_id']} | +{x['interval_days']}d | "
                f"{x['scheduled_date']} | {x['effective_status'].upper()} | {x.get('task_summary', '')} |"
            )
        lines.append("")
    return "\n".join(lines)
