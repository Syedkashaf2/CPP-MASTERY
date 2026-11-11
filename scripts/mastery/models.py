"""Strict validation, duplicate-ID detection, reference checks, and baseline integrity."""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from .config import EnginePaths, load_config, load_json, load_manifest, sha256_file

VALID_RECORD_TYPES = ("session", "correction", "retention_probe")
VALID_ATTEMPT_TYPES = (
    "first_attempt",
    "remediation",
    "transfer",
    "delayed_recall",
    "correction",
    "mixed",
    "unknown",
)
VALID_HINT_LEVELS = ("H0", "H1", "H2", "H3", "H4", "unknown")
VALID_INDEPENDENCE_LEVELS = (
    "unassisted",
    "minimal_hint",
    "scaffolded",
    "assisted",
    "unknown",
)
VALID_DIMENSIONS = (
    "conceptual_reasoning",
    "mental_execution",
    "debugging",
    "independent_implementation",
    "transfer",
)
VALID_REVIEW_STATUSES = ("pending", "accepted", "rejected", "needs_revision")
VALID_MISTAKE_STATUSES = (
    "open",
    "remediation_in_progress",
    "corrected_awaiting_retest",
    "resolved_verified_delayed",
)
VALID_PROBE_STATUSES = (
    "scheduled",
    "due",
    "overdue",
    "completed_passed",
    "completed_failed",
    "completed_assisted",
    "waived",
)
VALID_PROBE_OUTCOMES = ("passed", "failed", "assisted", "not_applicable", None)
SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9._-]+$")
TOPIC_ID_RE = re.compile(r"^T-\d{3}$")
MISTAKE_ID_RE = re.compile(r"^M-\d{3,}$")
PROBE_ID_RE = re.compile(r"^R-\d{3,}$")


def load_sessions(paths: EnginePaths) -> tuple[list[tuple[Path, dict[str, Any]]], list[str]]:
    """Load all session JSON records; never silently ignore malformed files."""
    records: list[tuple[Path, dict[str, Any]]] = []
    read_errors: list[str] = []
    if not paths.sessions.exists():
        return records, read_errors
    for path in sorted(paths.sessions.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            read_errors.append(f"{path.relative_to(paths.root)}: malformed JSON ({exc})")
            continue
        if not isinstance(data, dict):
            read_errors.append(f"{path.relative_to(paths.root)}: top-level JSON must be an object")
            continue
        records.append((path, data))
    return records, read_errors


def validate_baseline_integrity(paths: EnginePaths, manifest: dict[str, Any]) -> list[str]:
    """Verify immutable baseline files exist and match locked SHA-256 digests."""
    problems: list[str] = []
    items = manifest.get("immutable_baseline_files", [])
    if not isinstance(items, list) or not items:
        return ["baseline_manifest.json missing immutable_baseline_files"]
    for entry in items:
        rel = entry.get("path", "")
        expected = entry.get("sha256", "")
        target = paths.root / rel
        if not target.is_file():
            problems.append(f"missing immutable baseline file: {rel}")
            continue
        actual = sha256_file(target)
        if actual != expected:
            problems.append(
                f"baseline file modified ({rel}): expected sha256 {expected}, got {actual}"
            )
    return problems


def _is_valid_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        dt.date.fromisoformat(value)
        return True
    except ValueError:
        return False


def validate_session_record(
    rec: dict[str, Any],
    paths: EnginePaths,
    manifest: dict[str, Any],
    *,
    known_session_ids: set[str] | None = None,
    known_probe_ids: set[str] | None = None,
    known_mistake_ids: set[str] | None = None,
    require_accepted: bool = False,
) -> list[str]:
    """Validate one session/correction/retention_probe record against schema and protocol rules."""
    errors: list[str] = []
    reserved = manifest.get("reserved_ids", {})
    valid_topics = set(reserved.get("topics", []))
    hist_mistakes = set(reserved.get("historical_mistakes", []))
    hist_evidence = set(reserved.get("historical_evidence", []))
    hist_completed_probes = set(reserved.get("historical_completed_probes", []))
    valid_mastery_labels = set(manifest.get("mastery_labels", []))
    valid_taxonomy = set(manifest.get("taxonomy_classes", []))

    required = [
        "record_type",
        "session_id",
        "date",
        "topic_ids",
        "task_ids",
        "attempt_type",
        "hint_level",
        "independence",
        "assessment",
        "evidence",
        "retention",
    ]
    for key in required:
        if key not in rec:
            errors.append(f"missing required field: {key}")

    rtype = rec.get("record_type")
    if rtype not in VALID_RECORD_TYPES:
        errors.append(f"record_type must be one of {VALID_RECORD_TYPES}")

    sid = rec.get("session_id")
    if not isinstance(sid, str) or len(sid) < 3 or not SESSION_ID_RE.match(sid):
        errors.append("session_id must be >= 3 chars matching [a-zA-Z0-9._-]+")

    if not _is_valid_date(rec.get("date")):
        errors.append("date must be YYYY-MM-DD")

    topics = rec.get("topic_ids")
    if not isinstance(topics, list) or not topics:
        errors.append("topic_ids must be a non-empty array")
    else:
        for tid in topics:
            if not isinstance(tid, str) or not TOPIC_ID_RE.match(tid):
                errors.append(f"invalid topic_id format: {tid!r}")
            elif valid_topics and tid not in valid_topics:
                errors.append(f"unknown topic_id not in baseline registry: {tid}")

    tasks = rec.get("task_ids")
    if not isinstance(tasks, list) or any(not isinstance(t, str) or not t.strip() for t in tasks):
        errors.append("task_ids must be an array of non-empty strings")

    attempt_type = rec.get("attempt_type")
    if attempt_type not in VALID_ATTEMPT_TYPES:
        errors.append(f"attempt_type must be one of {VALID_ATTEMPT_TYPES}")

    parent_sid = rec.get("parent_session_id")
    if (rtype == "correction" or attempt_type == "remediation") and not parent_sid:
        errors.append("correction/remediation record must specify parent_session_id")
    if parent_sid is not None:
        if not isinstance(parent_sid, str) or not parent_sid.strip():
            errors.append("parent_session_id must be a non-empty string or null")
        elif known_session_ids is not None and parent_sid not in known_session_ids:
            errors.append(f"broken reference: parent_session_id {parent_sid!r} does not exist")
        elif sid == parent_sid:
            errors.append("parent_session_id cannot reference the record itself")

    hint_level = rec.get("hint_level")
    if hint_level not in VALID_HINT_LEVELS:
        errors.append(f"hint_level must be one of {VALID_HINT_LEVELS}")

    indep = rec.get("independence")
    if not isinstance(indep, dict):
        errors.append("independence must be an object")
    else:
        ilev = indep.get("level")
        if ilev not in VALID_INDEPENDENCE_LEVELS:
            errors.append(f"independence.level must be one of {VALID_INDEPENDENCE_LEVELS}")
        hints_used = indep.get("hints_used", [])
        if not isinstance(hints_used, list) or any(not isinstance(h, str) for h in hints_used):
            errors.append("independence.hints_used must be an array of strings")
        if hint_level == "H0" and ilev != "unassisted":
            errors.append("hint_level H0 requires independence.level == 'unassisted'")
        if hint_level in ("H1", "H2", "H3", "H4") and ilev == "unassisted":
            errors.append(f"hint_level {hint_level} cannot claim independence.level == 'unassisted'")
        if hint_level == "H0" and hints_used:
            errors.append("hint_level H0 cannot have non-empty hints_used")

    assess = rec.get("assessment")
    if not isinstance(assess, dict):
        errors.append("assessment must be an object")
    else:
        score = assess.get("score_percent")
        if score is not None and (
            isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 100
        ):
            errors.append("assessment.score_percent must be 0..100 or null")
        dims = assess.get("dimensions")
        if not isinstance(dims, dict):
            errors.append("assessment.dimensions must be an object")
        else:
            for dim_k, dim_v in dims.items():
                if dim_k not in VALID_DIMENSIONS:
                    errors.append(f"unknown assessment dimension: {dim_k}")
                if dim_v is not None and (
                    isinstance(dim_v, bool)
                    or not isinstance(dim_v, (int, float))
                    or not 0 <= dim_v <= 5
                ):
                    errors.append(f"assessment.dimensions.{dim_k} must be 0..5 or null")
        rstat = assess.get("review_status")
        if rstat not in VALID_REVIEW_STATUSES:
            errors.append(f"assessment.review_status must be one of {VALID_REVIEW_STATUSES}")
        if require_accepted and rstat != "accepted":
            errors.append("human review gate: assessment.review_status must be 'accepted' before import")
        if rstat == "accepted" and assess.get("reviewed_by_human") is not True:
            errors.append("assessment.reviewed_by_human must be true when review_status is 'accepted'")
        prop_label = assess.get("proposed_mastery_label")
        if prop_label is not None and valid_mastery_labels and prop_label not in valid_mastery_labels:
            errors.append(f"unknown proposed_mastery_label: {prop_label!r}")

    ev = rec.get("evidence")
    if not isinstance(ev, dict):
        errors.append("evidence must be an object")
    else:
        for cf in ev.get("code_files", []):
            if not isinstance(cf, str) or not cf.strip():
                errors.append("evidence.code_files entries must be non-empty relative paths")
                continue
            p = (paths.root / cf).resolve()
            if not str(p).startswith(str(paths.root.resolve())):
                errors.append(f"evidence.code_files path escapes repository: {cf}")
            elif not p.exists():
                errors.append(f"broken reference: evidence.code_files path does not exist: {cf}")
        for eid in ev.get("evidence_ids", []):
            if eid in hist_evidence:
                errors.append(f"collision with reserved historical evidence ID: {eid}")

    mistakes = rec.get("mistakes", [])
    if not isinstance(mistakes, list):
        errors.append("mistakes must be an array")
    else:
        all_known_mistakes = set(hist_mistakes)
        if known_mistake_ids:
            all_known_mistakes |= known_mistake_ids
        for idx, m in enumerate(mistakes):
            if not isinstance(m, dict):
                errors.append(f"mistakes[{idx}] must be an object")
                continue
            for req_m in ("root_cause", "observable_symptom", "correction", "status"):
                if not m.get(req_m):
                    errors.append(f"mistakes[{idx}] missing required field: {req_m}")
            mid = m.get("mistake_id")
            if mid not in (None, "auto"):
                if not isinstance(mid, str) or not MISTAKE_ID_RE.match(mid):
                    errors.append(f"mistakes[{idx}].mistake_id invalid format: {mid!r}")
                elif mid in hist_mistakes:
                    errors.append(f"mistakes[{idx}] collides with reserved historical mistake ID: {mid}")
            rec_of = m.get("recurrence_of")
            if rec_of is not None:
                if not isinstance(rec_of, str) or not MISTAKE_ID_RE.match(rec_of):
                    errors.append(f"mistakes[{idx}].recurrence_of invalid format: {rec_of!r}")
                elif rec_of not in all_known_mistakes:
                    errors.append(f"broken reference: mistakes[{idx}].recurrence_of {rec_of!r} unknown")
            tax = m.get("taxonomy_class")
            if tax and valid_taxonomy and tax not in valid_taxonomy:
                errors.append(f"mistakes[{idx}].taxonomy_class unknown: {tax!r}")
            mstat = m.get("status")
            if mstat not in VALID_MISTAKE_STATUSES:
                errors.append(f"mistakes[{idx}].status must be one of {VALID_MISTAKE_STATUSES}")
            if mstat == "resolved_verified_delayed" and m.get("reproduced_independently") is not True:
                errors.append(
                    f"mistakes[{idx}] cannot be resolved_verified_delayed without reproduced_independently == true"
                )

    ret = rec.get("retention")
    if not isinstance(ret, dict):
        errors.append("retention must be an object")
    else:
        p_attempted = ret.get("probe_id_attempted")
        if p_attempted is not None:
            if not isinstance(p_attempted, str) or not PROBE_ID_RE.match(p_attempted):
                errors.append(f"retention.probe_id_attempted invalid format: {p_attempted!r}")
            elif p_attempted in hist_completed_probes:
                errors.append(f"cannot overwrite historical completed probe: {p_attempted}")
            elif known_probe_ids is not None and p_attempted not in known_probe_ids:
                errors.append(f"broken reference: retention.probe_id_attempted {p_attempted!r} not in retention queue")
        if ret.get("probe_outcome") not in VALID_PROBE_OUTCOMES:
            errors.append(f"retention.probe_outcome must be one of {VALID_PROBE_OUTCOMES}")
        if rtype == "retention_probe" and not p_attempted:
            errors.append("retention_probe record must specify retention.probe_id_attempted")
        for idx, ps in enumerate(ret.get("probes_scheduled", [])):
            if not isinstance(ps, dict):
                errors.append(f"retention.probes_scheduled[{idx}] must be an object")
                continue
            ptid = ps.get("topic_id")
            if not isinstance(ptid, str) or (valid_topics and ptid not in valid_topics):
                errors.append(f"retention.probes_scheduled[{idx}] invalid topic_id: {ptid!r}")
            if not _is_valid_date(ps.get("due_date")):
                errors.append(f"retention.probes_scheduled[{idx}] due_date must be YYYY-MM-DD")

    return errors


def validate_mistake_ledger(ledger: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    reserved = manifest.get("reserved_ids", {})
    hist_mistakes = set(reserved.get("historical_mistakes", []))
    valid_topics = set(reserved.get("topics", []))
    valid_taxonomy = set(manifest.get("taxonomy_classes", []))

    if not isinstance(ledger, dict):
        return ["mistake_ledger.json must be an object"]
    mistakes = ledger.get("mistakes")
    if not isinstance(mistakes, list):
        return ["mistake_ledger.json.mistakes must be an array"]

    seen: set[str] = set()
    for idx, m in enumerate(mistakes):
        if not isinstance(m, dict):
            errors.append(f"mistake_ledger.mistakes[{idx}] must be an object")
            continue
        mid = m.get("mistake_id")
        if not isinstance(mid, str) or not MISTAKE_ID_RE.match(mid):
            errors.append(f"mistake_ledger.mistakes[{idx}] invalid mistake_id: {mid!r}")
        elif mid in hist_mistakes:
            errors.append(f"mistake_ledger collides with historical ID: {mid}")
        elif mid in seen:
            errors.append(f"duplicate mistake_id in mistake_ledger: {mid}")
        else:
            seen.add(mid)
        for tid in m.get("topic_ids", []):
            if valid_topics and tid not in valid_topics:
                errors.append(f"mistake_ledger {mid} references unknown topic {tid}")
        tax = m.get("taxonomy_class")
        if valid_taxonomy and tax not in valid_taxonomy:
            errors.append(f"mistake_ledger {mid} unknown taxonomy_class: {tax!r}")
        if m.get("status") not in VALID_MISTAKE_STATUSES:
            errors.append(f"mistake_ledger {mid} invalid status: {m.get('status')!r}")
        if m.get("status") == "resolved_verified_delayed" and m.get("reproduced_independently") is not True:
            errors.append(
                f"mistake_ledger {mid} cannot be resolved_verified_delayed without reproduced_independently == true"
            )
    return errors


def validate_retention_state(state: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    reserved = manifest.get("reserved_ids", {})
    hist_completed = set(reserved.get("historical_completed_probes", []))
    valid_topics = set(reserved.get("topics", []))

    if not isinstance(state, dict):
        return ["retention_state.json must be an object"]
    probes = state.get("probes")
    if not isinstance(probes, list):
        return ["retention_state.json.probes must be an array"]

    seen: set[str] = set()
    for idx, p in enumerate(probes):
        if not isinstance(p, dict):
            errors.append(f"retention_state.probes[{idx}] must be an object")
            continue
        pid = p.get("probe_id")
        if not isinstance(pid, str) or not PROBE_ID_RE.match(pid):
            errors.append(f"retention_state.probes[{idx}] invalid probe_id: {pid!r}")
        elif pid in hist_completed:
            errors.append(f"retention_state collides with historical completed probe: {pid}")
        elif pid in seen:
            errors.append(f"duplicate probe_id in retention_state: {pid}")
        else:
            seen.add(pid)
        tid = p.get("topic_id")
        if not isinstance(tid, str) or (valid_topics and tid not in valid_topics):
            errors.append(f"retention_state {pid} references unknown topic: {tid!r}")
        if not _is_valid_date(p.get("scheduled_date")):
            errors.append(f"retention_state {pid} invalid scheduled_date")
        days = p.get("interval_days")
        if not isinstance(days, int) or days < 1:
            errors.append(f"retention_state {pid} interval_days must be positive integer")
        else:
            expected_tier = "short_interval" if days < 7 else "long_term"
            if p.get("tier") != expected_tier:
                errors.append(f"retention_state {pid} tier must be {expected_tier} for interval {days}d")
        if p.get("status") not in VALID_PROBE_STATUSES:
            errors.append(f"retention_state {pid} invalid status: {p.get('status')!r}")
        if p.get("retention_verified") is True:
            if p.get("tier") != "long_term" or p.get("status") != "completed_passed" or p.get("hint_level") != "H0":
                errors.append(
                    f"retention_state {pid}: retention_verified=true allowed only for long_term (>=7d) H0 passed probes"
                )
    return errors


def validate_all(paths: EnginePaths, *, check_docs: bool = False) -> list[str]:
    """Run full repository validation and return a list of errors (empty means valid)."""
    problems: list[str] = []
    try:
        load_config(paths)
        manifest = load_manifest(paths)
    except Exception as exc:
        return [str(exc)]

    problems.extend(validate_baseline_integrity(paths, manifest))

    # Validate JSON schema files themselves parse cleanly
    if paths.schemas.exists():
        for sp in sorted(paths.schemas.glob("*.json")):
            try:
                json.loads(sp.read_text(encoding="utf-8"))
            except Exception as exc:
                problems.append(f"{sp.relative_to(paths.root)}: malformed schema JSON ({exc})")

    sessions, read_errs = load_sessions(paths)
    problems.extend(read_errs)

    ledger = load_json(paths.mistake_ledger)
    if ledger is None:
        problems.append("missing .mastery/records/mistake_ledger.json")
        known_mistakes: set[str] = set()
    else:
        problems.extend(validate_mistake_ledger(ledger, manifest))
        known_mistakes = {
            m.get("mistake_id")
            for m in ledger.get("mistakes", [])
            if isinstance(m, dict) and isinstance(m.get("mistake_id"), str)
        }

    ret_state = load_json(paths.retention_state)
    if ret_state is None:
        problems.append("missing .mastery/records/retention_state.json")
        known_probes: set[str] = set()
    else:
        problems.extend(validate_retention_state(ret_state, manifest))
        known_probes = {
            p.get("probe_id")
            for p in ret_state.get("probes", [])
            if isinstance(p, dict) and isinstance(p.get("probe_id"), str)
        }

    all_sids = {r.get("session_id") for _, r in sessions if isinstance(r.get("session_id"), str)}
    seen_sids: set[str] = set()
    seen_eids: set[str] = set()
    seen_session_mids: set[str] = set()

    for path, rec in sessions:
        rel = path.relative_to(paths.root)
        sid = rec.get("session_id")
        if sid in seen_sids:
            problems.append(f"{rel}: duplicate session_id {sid!r}")
        elif isinstance(sid, str):
            seen_sids.add(sid)

        for eid in rec.get("evidence", {}).get("evidence_ids", []):
            if eid in seen_eids:
                problems.append(f"{rel}: duplicate evidence_id {eid!r}")
            else:
                seen_eids.add(eid)

        for m in rec.get("mistakes", []):
            if isinstance(m, dict):
                mid = m.get("mistake_id")
                if isinstance(mid, str) and mid != "auto":
                    if mid in seen_session_mids:
                        problems.append(f"{rel}: duplicate mistake_id across sessions {mid!r}")
                    else:
                        seen_session_mids.add(mid)

        errs = validate_session_record(
            rec,
            paths,
            manifest,
            known_session_ids=all_sids,
            known_probe_ids=known_probes,
            known_mistake_ids=known_mistakes,
            require_accepted=False,
        )
        problems.extend(f"{rel}: {e}" for e in errs)

    if check_docs:
        from .render import render_markdown_outputs

        expected_docs = render_markdown_outputs(paths)
        for filename, expected_text in expected_docs.items():
            target = paths.progress / filename
            if not target.exists():
                problems.append(f"generated doc missing: docs/progress/{filename}")
            else:
                actual_text = target.read_text(encoding="utf-8")
                if actual_text != expected_text:
                    problems.append(
                        f"generated doc out of date: docs/progress/{filename} (run 'rebuild')"
                    )

    return problems
