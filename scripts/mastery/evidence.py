"""Objective repository evidence collection and explicit C++ compilation/test capture."""
from __future__ import annotations

import datetime as dt
import re
import subprocess
from pathlib import Path
from typing import Any

from .config import UTC, EnginePaths, dump_json, now_utc_iso, sha256_file


def run_subprocess(cmd: list[str], cwd: Path, timeout: int = 120) -> dict[str, Any]:
    try:
        proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=timeout)
        return {
            "command": cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-12000:],
            "stderr": proc.stderr[-12000:],
        }
    except Exception as exc:
        return {"command": cmd, "returncode": None, "stdout": "", "stderr": str(exc)}


def git(paths: EnginePaths, *args: str) -> dict[str, Any]:
    return run_subprocess(["git", *args], cwd=paths.root)


def git_root(paths: EnginePaths) -> Path | None:
    res = git(paths, "rev-parse", "--show-toplevel")
    if res["returncode"] != 0:
        return None
    return Path(res["stdout"].strip()).resolve()


def safe_slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:55] or "session"


def collect_git_evidence(paths: EnginePaths, label: str | None = None) -> tuple[Path, dict[str, Any]]:
    """Collect objective Git state, working-tree changes, and SHA-256 tracked file manifest."""
    if git_root(paths) != paths.root.resolve():
        raise SystemExit("ERROR: Not at the top level of the existing Git repository.")

    status = git(paths, "status", "--porcelain=v1", "-uall")
    head = git(paths, "rev-parse", "HEAD")
    branch = git(paths, "branch", "--show-current")
    remotes = git(paths, "remote", "-v")
    diff_stat = git(paths, "diff", "--stat")
    tracked = git(paths, "ls-files")
    recent = git(paths, "log", "-10", "--date=iso-strict", "--pretty=format:%H%x09%ad%x09%s")

    manifest_files: list[dict[str, Any]] = []
    if tracked["returncode"] == 0:
        for rel in tracked["stdout"].splitlines():
            target = paths.root / rel
            if target.is_file():
                manifest_files.append(
                    {"path": rel, "bytes": target.stat().st_size, "sha256": sha256_file(target)}
                )

    payload: dict[str, Any] = {
        "captured_at": now_utc_iso(),
        "label": label,
        "repository_root": str(paths.root),
        "branch": branch["stdout"].strip() if branch["returncode"] == 0 else None,
        "head": head["stdout"].strip() if head["returncode"] == 0 else None,
        "status_porcelain": status["stdout"].splitlines() if status["returncode"] == 0 else [],
        "diff_stat": diff_stat["stdout"].strip() if diff_stat["returncode"] == 0 else "",
        "remotes": remotes["stdout"].splitlines() if remotes["returncode"] == 0 else [],
        "recent_commits": recent["stdout"].splitlines() if recent["returncode"] == 0 else [],
        "tracked_file_manifest": manifest_files,
        "note": "Objective repository snapshot only; not an independent learning or mastery assessment.",
    }
    stamp = dt.datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = f"-{safe_slug(label)}" if label else ""
    out_path = paths.evidence / f"{stamp}{suffix}-git.json"
    dump_json(out_path, payload)
    return out_path, payload


def run_test_command(paths: EnginePaths, command: str) -> tuple[Path, dict[str, Any]]:
    """Execute an explicitly supplied compiler/test shell command and save objective output."""
    proc = subprocess.run(
        command,
        cwd=paths.root,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=300,
    )
    payload: dict[str, Any] = {
        "captured_at": now_utc_iso(),
        "command": command,
        "returncode": proc.returncode,
        "output": proc.stdout[-20000:],
        "note": "Objective command execution output only; not a mastery verification.",
    }
    stamp = dt.datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = paths.evidence / f"{stamp}-test.json"
    dump_json(out_path, payload)
    return out_path, payload


def latest_evidence_refs(paths: EnginePaths, limit: int = 3) -> list[str]:
    if not paths.evidence.exists():
        return []
    files = sorted(paths.evidence.glob("*.json"), reverse=True)[:limit]
    return [str(p.relative_to(paths.root)) for p in files]
