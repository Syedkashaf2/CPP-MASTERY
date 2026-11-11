"""Strictly read-only Git review helper (never stages, commits, resets, or pushes)."""
from __future__ import annotations

from .config import EnginePaths
from .evidence import git


def format_git_review(paths: EnginePaths) -> str:
    sections = [
        ("Repository root", ["rev-parse", "--show-toplevel"]),
        ("Branch", ["branch", "--show-current"]),
        ("Remotes", ["remote", "-v"]),
        ("Status", ["status", "--short", "--branch"]),
        ("Tracked diff summary", ["diff", "--stat"]),
        ("Recent commits", ["log", "-5", "--oneline", "--decorate"]),
    ]
    out: list[str] = []
    for title, args in sections:
        res = git(paths, *args)
        content = (res["stdout"] or res["stderr"] or "(empty)").strip()
        out.append(f"## {title}\n{content}")

    out.append(
        "\n## Manual Review Checklist\n"
        "Review-only mode: no staging, commit, push, or history mutation was performed.\n"
        "Inspect diffs carefully with `git diff` and `git status` before staging explicit paths."
    )
    return "\n\n".join(out)
