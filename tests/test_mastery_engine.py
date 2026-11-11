"""Unit tests for the C++ Mastery Automation Engine (stdlib unittest only)."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from mastery.config import EnginePaths, dump_json, load_json, load_manifest  # noqa: E402
from mastery.mistakes import sync_mistakes_from_session  # noqa: E402
from mastery.models import validate_all, validate_session_record  # noqa: E402
from mastery.render import create_snapshot, rebuild_docs, render_dashboard_html  # noqa: E402
from mastery.retention import load_retention_state, sync_retention_from_session  # noqa: E402


def _make_valid_session(
    session_id: str = "2026-11-12-t023-test",
    date: str = "2026-11-12",
    topic_ids: list[str] | None = None,
    attempt_type: str = "first_attempt",
    hint_level: str = "H0",
    indep_level: str = "unassisted",
    probe_id: str | None = None,
    probe_outcome: str | None = "not_applicable",
) -> dict:
    return {
        "record_type": "retention_probe" if probe_id else "session",
        "session_id": session_id,
        "date": date,
        "topic_ids": topic_ids or ["T-023"],
        "task_ids": [probe_id or "task-1"],
        "attempt_type": attempt_type,
        "parent_session_id": None,
        "hint_level": hint_level,
        "independence": {"level": indep_level, "hints_used": [] if hint_level == "H0" else ["hint 1"]},
        "process_summary": {
            "problem_interpretation": "Understood constraints.",
            "approach_derivation": "Derived sliding window.",
            "invariant_reasoning": "Window valid after while.",
            "complexity_analysis": "O(N) time, O(1) space.",
        },
        "debugging_history": [],
        "assessment": {
            "score_percent": 95,
            "dimensions": {
                "conceptual_reasoning": 5,
                "mental_execution": 5,
                "debugging": None,
                "independent_implementation": 5,
                "transfer": 5,
            },
            "proposed_mastery_label": None,
            "review_status": "accepted",
            "reviewed_by_human": True,
            "reviewed_at": "2026-11-12T04:00:00+05:30",
            "summary": "Clean H0 implementation.",
        },
        "evidence": {
            "code_files": [],
            "commit_hash": None,
            "evidence_snapshot_refs": [],
            "test_command": None,
            "test_returncode": None,
            "test_output_excerpt": None,
            "evidence_ids": [],
            "limitations": [],
        },
        "mistakes": [],
        "retention": {
            "probe_id_attempted": probe_id,
            "probe_outcome": probe_outcome,
            "probes_scheduled": [],
        },
        "next_actions": [],
        "human_notes": "",
    }


class MasteryEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for sub in ("docs/baseline", "docs/progress", ".mastery/records/sessions", ".mastery/snapshots", "schemas"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)
        for src in (REPO_ROOT / "docs/baseline").glob("*.md"):
            shutil.copy2(src, self.root / "docs/baseline" / src.name)
        for src in (REPO_ROOT / "schemas").glob("*.json"):
            shutil.copy2(src, self.root / "schemas" / src.name)
        shutil.copy2(REPO_ROOT / ".mastery/config.json", self.root / ".mastery/config.json")
        shutil.copy2(REPO_ROOT / ".mastery/baseline_manifest.json", self.root / ".mastery/baseline_manifest.json")
        shutil.copy2(REPO_ROOT / ".mastery/records/mistake_ledger.json", self.root / ".mastery/records/mistake_ledger.json")
        shutil.copy2(REPO_ROOT / ".mastery/records/retention_state.json", self.root / ".mastery/records/retention_state.json")
        self.paths = EnginePaths(self.root)
        rebuild_docs(self.paths)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_baseline_integrity_passes_and_detects_tampering(self) -> None:
        self.assertEqual(validate_all(self.paths, check_docs=True), [])
        target = self.root / "docs/baseline/CPP_COGNITIVE_STATE_LEDGER.md"
        target.write_text(target.read_text(encoding="utf-8") + "\n<!-- tampered -->\n", encoding="utf-8")
        errs = validate_all(self.paths)
        self.assertTrue(any("baseline file modified" in e for e in errs))

    def test_rejects_pending_or_inconsistent_independence(self) -> None:
        manifest = load_manifest(self.paths)
        rec = _make_valid_session()
        rec["assessment"]["review_status"] = "pending"
        errs = validate_session_record(rec, self.paths, manifest, require_accepted=True)
        self.assertTrue(any("human review gate" in e for e in errs))

        rec2 = _make_valid_session(hint_level="H2", indep_level="unassisted")
        errs2 = validate_session_record(rec2, self.paths, manifest)
        self.assertTrue(any("cannot claim independence.level == 'unassisted'" in e for e in errs2))

    def test_rejects_correction_without_parent_and_broken_refs(self) -> None:
        manifest = load_manifest(self.paths)
        rec = _make_valid_session(attempt_type="remediation")
        rec["record_type"] = "correction"
        errs = validate_session_record(rec, self.paths, manifest, known_session_ids=set())
        self.assertTrue(any("parent_session_id" in e for e in errs))

        rec_bad_topic = _make_valid_session(topic_ids=["T-999"])
        errs_t = validate_session_record(rec_bad_topic, self.paths, manifest)
        self.assertTrue(any("unknown topic_id" in e for e in errs_t))

        rec_bad_file = _make_valid_session()
        rec_bad_file["evidence"]["code_files"] = ["solutions/DOES_NOT_EXIST.cpp"]
        errs_f = validate_session_record(rec_bad_file, self.paths, manifest)
        self.assertTrue(any("does not exist" in e for e in errs_f))

    def test_detects_duplicate_session_ids_and_historical_collisions(self) -> None:
        manifest = load_manifest(self.paths)
        r1 = _make_valid_session(session_id="2026-11-12-dup")
        r2 = _make_valid_session(session_id="2026-11-12-dup")
        dump_json(self.paths.sessions / "a.json", r1)
        dump_json(self.paths.sessions / "b.json", r2)
        errs = validate_all(self.paths)
        self.assertTrue(any("duplicate session_id" in e for e in errs))

        rec_hist = _make_valid_session()
        rec_hist["evidence"]["evidence_ids"] = ["E-001"]
        rec_hist["mistakes"] = [
            {
                "mistake_id": "M-003",
                "root_cause": "test",
                "observable_symptom": "test",
                "correction": "test",
                "status": "open",
            }
        ]
        errs_h = validate_session_record(rec_hist, self.paths, manifest)
        self.assertTrue(any("E-001" in e for e in errs_h))
        self.assertTrue(any("M-003" in e for e in errs_h))

    def test_retention_ladder_and_short_vs_long_term_verification(self) -> None:
        # Short-interval R-009 (+1d) passed H0 -> does NOT mark retention_verified, schedules +3d R-017
        rec_short = _make_valid_session(
            session_id="2026-11-12-r009",
            topic_ids=["T-003"],
            attempt_type="delayed_recall",
            probe_id="R-009",
            probe_outcome="passed",
        )
        state = sync_retention_from_session(self.paths, rec_short)
        r009 = next(p for p in state["probes"] if p["probe_id"] == "R-009")
        self.assertEqual(r009["status"], "completed_passed")
        self.assertFalse(r009["retention_verified"])  # <7d cannot be long-term verified
        r017 = next(p for p in state["probes"] if p["probe_id"] == "R-017")
        self.assertEqual(r017["interval_days"], 3)
        self.assertEqual(r017["scheduled_date"], "2026-11-15")

        # Long-term R-013 (+7d) passed H0 -> sets retention_verified=True and schedules +14d R-018
        rec_long = _make_valid_session(
            session_id="2026-11-18-r013",
            date="2026-11-18",
            topic_ids=["T-023"],
            attempt_type="delayed_recall",
            probe_id="R-013",
            probe_outcome="passed",
        )
        state2 = sync_retention_from_session(self.paths, rec_long)
        r013 = next(p for p in state2["probes"] if p["probe_id"] == "R-013")
        self.assertEqual(r013["status"], "completed_passed")
        self.assertTrue(r013["retention_verified"])
        r018 = next(p for p in state2["probes"] if p["probe_id"] == "R-018")
        self.assertEqual(r018["interval_days"], 14)
        self.assertEqual(r018["tier"], "long_term")

        # Assisted pass on R-014 resets back to +1d and does NOT verify retention
        rec_assisted = _make_valid_session(
            session_id="2026-11-18-r014",
            date="2026-11-18",
            topic_ids=["T-020"],
            attempt_type="delayed_recall",
            hint_level="H2",
            indep_level="minimal_hint",
            probe_id="R-014",
            probe_outcome="assisted",
        )
        state3 = sync_retention_from_session(self.paths, rec_assisted)
        r014 = next(p for p in state3["probes"] if p["probe_id"] == "R-014")
        self.assertEqual(r014["status"], "completed_assisted")
        self.assertFalse(r014["retention_verified"])
        r019 = next(p for p in state3["probes"] if p["probe_id"] == "R-019")
        self.assertEqual(r019["interval_days"], 1)

    def test_mistake_ledger_auto_id_and_recurrence(self) -> None:
        manifest = load_manifest(self.paths)
        rec = _make_valid_session(session_id="2026-11-12-m020")
        rec["mistakes"] = [
            {
                "mistake_id": "auto",
                "taxonomy_class": "Update-Ordering Fault",
                "original_incorrect_reasoning": "Checked before update",
                "root_cause": "Inverted loop sequence",
                "observable_symptom": "Wrong final element",
                "correction": "Update state first",
                "reproduced_independently": False,
                "recurrence_of": "M-019",
                "related_concepts": ["T-022"],
                "status": "open",
            }
        ]
        ledger = sync_mistakes_from_session(self.paths, rec, manifest)
        self.assertEqual(len(ledger["mistakes"]), 1)
        m = ledger["mistakes"][0]
        self.assertEqual(m["mistake_id"], "M-020")
        self.assertTrue(m["recurred"])
        self.assertEqual(m["recurs_from_baseline_id"], "M-019")

    def test_rebuild_reproducibility_dashboard_and_snapshot(self) -> None:
        first = {k: (self.paths.progress / k).read_text(encoding="utf-8") for k in rebuild_docs(self.paths)}
        second = {k: (self.paths.progress / k).read_text(encoding="utf-8") for k in rebuild_docs(self.paths)}
        self.assertEqual(first, second)
        self.assertEqual(validate_all(self.paths, check_docs=True), [])

        dash = render_dashboard_html(self.paths)
        self.assertTrue(dash.is_file())
        self.assertIn("C++ Mastery Evidence Dashboard", dash.read_text(encoding="utf-8"))

        snap = create_snapshot(self.paths)
        self.assertTrue((snap / "snapshot_meta.json").is_file())
        self.assertTrue((snap / "MASTERY_DASHBOARD.html").is_file())
        meta = load_json(snap / "snapshot_meta.json")
        self.assertEqual(meta["session_record_count"], 0)


if __name__ == "__main__":
    unittest.main()
