"""Configuration, repository path layout, and baseline manifest helpers."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

UTC = dt.timezone.utc


@dataclass(frozen=True)
class EnginePaths:
    """Resolved filesystem paths for a CPP-MASTERY repository."""

    root: Path

    @property
    def state(self) -> Path:
        return self.root / ".mastery"

    @property
    def config(self) -> Path:
        return self.state / "config.json"

    @property
    def baseline_manifest(self) -> Path:
        return self.state / "baseline_manifest.json"

    @property
    def inbox(self) -> Path:
        return self.state / "inbox"

    @property
    def sessions(self) -> Path:
        return self.state / "records" / "sessions"

    @property
    def mistake_ledger(self) -> Path:
        return self.state / "records" / "mistake_ledger.json"

    @property
    def retention_state(self) -> Path:
        return self.state / "records" / "retention_state.json"

    @property
    def evidence(self) -> Path:
        return self.state / "evidence"

    @property
    def snapshots(self) -> Path:
        return self.state / "snapshots"

    @property
    def templates(self) -> Path:
        return self.state / "templates"

    @property
    def schemas(self) -> Path:
        return self.root / "schemas"

    @property
    def progress(self) -> Path:
        return self.root / "docs" / "progress"


def default_paths() -> EnginePaths:
    return EnginePaths(Path(__file__).resolve().parents[2])


def now_utc_iso() -> str:
    return dt.datetime.now(UTC).replace(microsecond=0).isoformat()


def today_local(config: dict[str, Any] | None = None) -> dt.date:
    tz_name = (config or {}).get("timezone", "Asia/Kolkata")
    if ZoneInfo is not None:
        try:
            return dt.datetime.now(ZoneInfo(tz_name)).date()
        except Exception:
            pass
    return dt.datetime.now(UTC).date()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_config(paths: EnginePaths) -> dict[str, Any]:
    cfg = load_json(paths.config)
    if not isinstance(cfg, dict):
        raise ValueError(f"Missing or invalid config file: {paths.config}")
    return cfg


def load_manifest(paths: EnginePaths) -> dict[str, Any]:
    manifest = load_json(paths.baseline_manifest)
    if not isinstance(manifest, dict):
        raise ValueError(f"Missing or invalid baseline manifest: {paths.baseline_manifest}")
    return manifest
