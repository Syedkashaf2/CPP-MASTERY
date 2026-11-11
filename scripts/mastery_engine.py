#!/usr/bin/env python3
"""Evidence-first C++ mastery documentation engine (Python stdlib only)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mastery.config import default_paths, dump_json, load_config, load_manifest, today_local
from mastery.evidence import collect_git_evidence, latest_evidence_refs, run_test_command, safe_slug
from mastery.git_sync import format_git_review
from mastery.mistakes import load_mistake_ledger, sync_mistakes_from_session
from mastery.models import load_sessions, validate_all, validate_session_record
from mastery.render import create_snapshot, rebuild_docs, render_dashboard_html
from mastery.retention import format_retention_cli, load_retention_state, sync_retention_from_session


def cmd_collect(args: argparse.Namespace) -> int:
    paths = default_paths()
    out_path, payload = collect_git_evidence(paths, label=args.label)
    print(f"Evidence saved: {out_path.relative_to(paths.root)}")
    print(
        f"Branch: {payload['branch']} | HEAD: {(payload['head'] or '')[:12]} | "
        f"Working-tree entries: {len(payload['status_porcelain'])}"
    )
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    paths = default_paths()
    raw = args.command
    if raw and raw[0] == "--":
        raw = raw[1:]
    if not raw:
        print("ERROR: Supply a shell command after --", file=sys.stderr)
        return 2
    command = " ".join(raw)
    print("Executing explicitly supplied command...")
    out_path, payload = run_test_command(paths, command)
    if payload["output"]:
        print(payload["output"])
    print(f"Test evidence saved: {out_path.relative_to(paths.root)}")
    print(f"Exit code: {payload['returncode']}")
    return 0 if payload["returncode"] == 0 else int(payload["returncode"] or 1)


def cmd_new_inbox(args: argparse.Namespace) -> int:
    paths = default_paths()
    cfg = load_config(paths)
    today = today_local(cfg).isoformat()
    topics: list[str] = []
    for raw_t in args.topics:
        for part in raw_t.replace(",", " ").split():
            if part:
                topics.append(part)
    probe = args.probe.strip() if isinstance(args.probe, str) and args.probe.strip() else None
    slug = safe_slug(args.slug or "-".join(topics))
    sid = f"{today}-{slug}"
    draft = {
        "record_type": "retention_probe" if probe else "session",
        "session_id": sid,
        "date": today,
        "topic_ids": topics,
        "task_ids": args.tasks or ([probe] if probe else ["task-description"]),
        "attempt_type": "delayed_recall" if probe else args.attempt_type,
        "parent_session_id": args.parent,
        "hint_level": "H0",
        "independence": {"level": "unassisted", "hints_used": []},
        "process_summary": {
            "problem_interpretation": "",
            "approach_derivation": "",
            "invariant_reasoning": "",
            "complexity_analysis": "",
        },
        "debugging_history": [],
        "assessment": {
            "score_percent": None,
            "dimensions": {
                "conceptual_reasoning": None,
                "mental_execution": None,
                "debugging": None,
                "independent_implementation": None,
                "transfer": None,
            },
            "proposed_mastery_label": None,
            "review_status": "pending",
            "reviewed_by_human": False,
            "reviewed_at": None,
            "summary": "",
        },
        "evidence": {
            "code_files": args.files or [],
            "commit_hash": None,
            "evidence_snapshot_refs": latest_evidence_refs(paths),
            "test_command": None,
            "test_returncode": None,
            "test_output_excerpt": None,
            "evidence_ids": [],
            "limitations": [],
        },
        "mistakes": [],
        "retention": {
            "probe_id_attempted": probe,
            "probe_outcome": "not_applicable" if not probe else None,
            "probes_scheduled": [],
        },
        "next_actions": [],
        "human_notes": "Paste Gemini assessment values, review carefully, and set review_status='accepted' + reviewed_by_human=true before import.",
    }
    dest = paths.inbox / f"session-{sid}.json"
    dump_json(dest, draft)
    print(f"Inbox draft created: {dest.relative_to(paths.root)}")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    paths = default_paths()
    src = Path(args.path).expanduser()
    if not src.is_absolute():
        src = paths.root / src
    if not src.is_file():
        print(f"ERROR: Record file not found: {src}", file=sys.stderr)
        return 1
    try:
        rec = json.loads(src.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"ERROR: Malformed JSON ({exc})", file=sys.stderr)
        return 1

    manifest = load_manifest(paths)
    sessions, read_errs = load_sessions(paths)
    if read_errs:
        print("ERROR: Existing repository has malformed session records:\n- " + "\n- ".join(read_errs), file=sys.stderr)
        return 1
    known_sids = {r.get("session_id") for _, r in sessions if isinstance(r.get("session_id"), str)}
    ret_state = load_retention_state(paths)
    known_pids = {p.get("probe_id") for p in ret_state.get("probes", []) if isinstance(p, dict)}
    ledger = load_mistake_ledger(paths)
    known_mids = {m.get("mistake_id") for m in ledger.get("mistakes", []) if isinstance(m, dict)}

    errors = validate_session_record(
        rec,
        paths,
        manifest,
        known_session_ids=known_sids,
        known_probe_ids=known_pids,
        known_mistake_ids=known_mids,
        require_accepted=not args.allow_pending,
    )
    if errors:
        print("Record rejected:\n- " + "\n- ".join(errors), file=sys.stderr)
        return 1

    dest = paths.sessions / f"{safe_slug(rec['session_id'])}.json"
    if dest.exists() or rec["session_id"] in known_sids:
        print(f"ERROR: Refusing to overwrite existing session record: {rec['session_id']}", file=sys.stderr)
        return 1

    sync_mistakes_from_session(paths, rec, manifest)
    sync_retention_from_session(paths, rec)
    dump_json(dest, rec)
    print(f"Imported reviewed record: {dest.relative_to(paths.root)}")

    rebuild_docs(paths)
    render_dashboard_html(paths)
    print("Rebuilt progress Markdown reports and HTML dashboard.")
    return 0


def cmd_rebuild(_: argparse.Namespace) -> int:
    paths = default_paths()
    written = rebuild_docs(paths)
    print(f"Rebuilt {len(written)} Markdown progress document(s) in docs/progress/.")
    return 0


def cmd_retention(args: argparse.Namespace) -> int:
    paths = default_paths()
    print(format_retention_cli(paths, due_only=args.due))
    return 0


def cmd_dashboard(_: argparse.Namespace) -> int:
    paths = default_paths()
    out = render_dashboard_html(paths)
    print(f"Dashboard updated: {out.relative_to(paths.root)}")
    return 0


def cmd_snapshot(_: argparse.Namespace) -> int:
    paths = default_paths()
    dest = create_snapshot(paths)
    print(f"Snapshot created: {dest.relative_to(paths.root)}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    paths = default_paths()
    problems = validate_all(paths, check_docs=args.check_docs)
    if problems:
        print("VALIDATION FAILED:\n- " + "\n- ".join(problems), file=sys.stderr)
        return 1
    sessions, _ = load_sessions(paths)
    print(
        f"Validation passed. Baseline hashes verified; {len(sessions)} session record(s); "
        "0 schema/reference errors."
    )
    return 0


def cmd_git_review(_: argparse.Namespace) -> int:
    paths = default_paths()
    print(format_git_review(paths))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c_p = sub.add_parser("collect", help="Capture objective Git state and tracked file hashes")
    c_p.add_argument("--label", help="Optional snapshot slug label")

    t_p = sub.add_parser("test", help="Run an explicit compiler/test command and save evidence")
    t_p.add_argument("command", nargs=argparse.REMAINDER)

    n_p = sub.add_parser("new-inbox", help="Create a pre-populated inbox draft for Gemini review")
    n_p.add_argument("--topics", nargs="+", required=True, help="Topic IDs e.g. T-023")
    n_p.add_argument("--tasks", nargs="+", help="Task IDs")
    n_p.add_argument("--probe", nargs="?", const="", default=None, help="Baseline/pending probe ID e.g. R-013")
    n_p.add_argument("--files", nargs="+", help="Code file paths relative to repo root")
    n_p.add_argument("--parent", help="Parent session ID if remediation/correction")
    n_p.add_argument("--attempt-type", default="first_attempt")
    n_p.add_argument("--slug", help="Short slug for session ID")

    i_p = sub.add_parser("import-record", help="Validate and import a reviewed JSON record")
    i_p.add_argument("path", help="Path to JSON record in .mastery/inbox/")
    i_p.add_argument("--allow-pending", action="store_true", help="Import without accepted status (staging)")

    sub.add_parser("rebuild", help="Regenerate docs/progress/*.md deterministically")

    r_p = sub.add_parser("retention", help="Display retention probe queue (short-interval vs long-term)")
    r_p.add_argument("--due", action="store_true", help="Show only due and overdue probes")

    sub.add_parser("dashboard", help="Generate docs/progress/MASTERY_DASHBOARD.html")
    sub.add_parser("snapshot", help="Create timestamped snapshot under .mastery/snapshots/")

    v_p = sub.add_parser("validate", help="Validate baseline hashes, schemas, IDs, and references")
    v_p.add_argument("--check-docs", action="store_true", help="Fail if docs/progress/*.md are out of sync")

    sub.add_parser("git-review", help="Safe read-only Git status, remote, and diff review")
    return ap


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    dispatch = {
        "collect": cmd_collect,
        "test": cmd_test,
        "new-inbox": cmd_new_inbox,
        "import-record": cmd_import,
        "rebuild": cmd_rebuild,
        "retention": cmd_retention,
        "dashboard": cmd_dashboard,
        "snapshot": cmd_snapshot,
        "validate": cmd_validate,
        "git-review": cmd_git_review,
    }
    return dispatch[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
