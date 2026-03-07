"""
Unit tests for audit/audit_viewer.py.

Covers:
  - load_entries: missing file, empty file, valid entries, malformed lines
  - find_by_id: match, no match, case-insensitive, multiple matches
  - render_entry: all fields rendered, missing optional fields, no crash
  - render_summary_table: empty, single, multiple entries
  - main() CLI: --all, --id, --tail, --log, --no-summary,
                no args (help), missing log, no matching id,
                empty log returns 0, bad log path returns 1

No real API key required. File I/O is mocked or uses tempfiles.
"""

import sys
import os
import io
import json
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from audit.audit_viewer import (
    load_entries,
    find_by_id,
    render_entry,
    render_summary_table,
    main,
)


# ── Shared fixtures ───────────────────────────────────────────────────────────

def _make_entry(
    alert_id="alert-001",
    route="escalate",
    risk="HIGH",
    freshness="FRESH",
    outcome="deployed",
    approved_by="@alice",
    **kwargs,
):
    base = {
        "timestamp":                "2025-03-02T10:00:00+00:00",
        "alert_id":                 alert_id,
        "route_taken":              route,
        "risk_level":               risk,
        "freshness":                freshness,
        "ai_hypothesis":            "Connection pool exhaustion caused by timeout doubling",
        "engineer_gate1_decision":  "confirmed",
        "engineer_gate2_decision":  "approved",
        "approved_by":              approved_by,
        "sandbox_result":           "pass",
        "outcome":                  outcome,
        "notes":                    "Diagnosis attempts: 1. Patch attempts: 1.",
        "compliance_flags":         [],
        "compliance_reasoning":     [],
        "diagnosis_reasoning_chain": [
            {"step": 1, "observation": "alert.error shows pool exhaustion",
             "inference": "Resource issue", "evidence": "alert.error"},
        ],
        "patch_reasoning_chain": [
            {"step": 1, "observation": "git_history shows timeout doubled",
             "decision": "Revert to 30s", "trade_off": "Slow queries will fail"},
        ],
        "gate1_clarifications":  [],
        "gate2_clarifications":  [],
        "second_approver":       "N/A",
    }
    base.update(kwargs)
    return base


def _make_auto_entry():
    return _make_entry(
        alert_id="alert-003",
        route="auto-handle",
        risk="LOW",
        freshness="FRESH",
        outcome="auto-resolved",
        approved_by="system",
        ai_hypothesis="N/A (auto-handled)",
        engineer_gate1_decision="N/A",
        engineer_gate2_decision="N/A",
        sandbox_result="N/A",
        notes="Low-risk incident handled automatically.",
        diagnosis_reasoning_chain=[],
        patch_reasoning_chain=[],
    )


def _make_compliance_entry():
    return _make_entry(
        compliance_flags=["2-person approval required for auth-service patches"],
        compliance_reasoning=[
            {"rule_id": "POL-001", "rule_name": "2-person approval",
             "triggered": True, "why": "service is auth-service"},
            {"rule_id": "POL-002", "rule_name": "Freeze window",
             "triggered": False, "why": "freeze_active is False"},
        ],
        second_approver="@bob",
    )


def _write_log(entries, tmp_file):
    """Write a list of entry dicts as JSONL to a temp file path."""
    with open(tmp_file, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


# ══════════════════════════════════════════════════════════════════════════════
# load_entries
# ══════════════════════════════════════════════════════════════════════════════

class TestLoadEntries(unittest.TestCase):

    def test_missing_file_returns_empty_list(self):
        result = load_entries("/nonexistent/path/audit.json")
        self.assertEqual(result, [])

    def test_empty_file_returns_empty_list(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp = f.name
        try:
            result = load_entries(tmp)
            self.assertEqual(result, [])
        finally:
            os.unlink(tmp)

    def test_single_valid_entry_loaded(self):
        entry = _make_entry()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(json.dumps(entry) + "\n")
            tmp = f.name
        try:
            result = load_entries(tmp)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["alert_id"], "alert-001")
        finally:
            os.unlink(tmp)

    def test_multiple_entries_all_loaded(self):
        entries = [_make_entry("alert-001"), _make_entry("alert-002"), _make_auto_entry()]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp = f.name
        try:
            _write_log(entries, tmp)
            result = load_entries(tmp)
            self.assertEqual(len(result), 3)
        finally:
            os.unlink(tmp)

    def test_malformed_line_skipped_valid_lines_loaded(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(json.dumps(_make_entry("alert-001")) + "\n")
            f.write("NOT VALID JSON\n")
            f.write(json.dumps(_make_entry("alert-002")) + "\n")
            tmp = f.name
        try:
            result = load_entries(tmp)
            self.assertEqual(len(result), 2)
            ids = [e["alert_id"] for e in result]
            self.assertIn("alert-001", ids)
            self.assertIn("alert-002", ids)
        finally:
            os.unlink(tmp)

    def test_blank_lines_ignored(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("\n")
            f.write(json.dumps(_make_entry()) + "\n")
            f.write("\n\n")
            tmp = f.name
        try:
            result = load_entries(tmp)
            self.assertEqual(len(result), 1)
        finally:
            os.unlink(tmp)

    def test_returns_list_of_dicts(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(json.dumps(_make_entry()) + "\n")
            tmp = f.name
        try:
            result = load_entries(tmp)
            self.assertIsInstance(result, list)
            self.assertIsInstance(result[0], dict)
        finally:
            os.unlink(tmp)

    def test_preserves_all_fields(self):
        entry = _make_compliance_entry()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(json.dumps(entry) + "\n")
            tmp = f.name
        try:
            result = load_entries(tmp)
            for key in entry:
                self.assertIn(key, result[0])
        finally:
            os.unlink(tmp)


# ══════════════════════════════════════════════════════════════════════════════
# find_by_id
# ══════════════════════════════════════════════════════════════════════════════

class TestFindById(unittest.TestCase):

    def setUp(self):
        self.entries = [
            _make_entry("alert-001"),
            _make_entry("alert-002"),
            _make_auto_entry(),   # alert-003
        ]

    def test_find_existing_id(self):
        result = find_by_id(self.entries, "alert-001")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["alert_id"], "alert-001")

    def test_find_nonexistent_id_returns_empty(self):
        result = find_by_id(self.entries, "alert-999")
        self.assertEqual(result, [])

    def test_case_insensitive_match(self):
        result = find_by_id(self.entries, "ALERT-001")
        self.assertEqual(len(result), 1)

    def test_mixed_case_id_match(self):
        result = find_by_id(self.entries, "Alert-003")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["alert_id"], "alert-003")

    def test_multiple_entries_same_id_returned(self):
        entries = [_make_entry("alert-001"), _make_entry("alert-001")]
        result = find_by_id(entries, "alert-001")
        self.assertEqual(len(result), 2)

    def test_empty_entries_list(self):
        result = find_by_id([], "alert-001")
        self.assertEqual(result, [])

    def test_returns_list(self):
        result = find_by_id(self.entries, "alert-001")
        self.assertIsInstance(result, list)


# ══════════════════════════════════════════════════════════════════════════════
# render_entry
# ══════════════════════════════════════════════════════════════════════════════

class TestRenderEntry(unittest.TestCase):
    """render_entry must not raise and must include key fields in output."""

    def _capture(self, entry, index=None):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            render_entry(entry, index=index)
        return buf.getvalue()

    def test_render_does_not_crash(self):
        self._capture(_make_entry())

    def test_render_includes_alert_id(self):
        out = self._capture(_make_entry("alert-001"))
        self.assertIn("alert-001", out)

    def test_render_includes_outcome(self):
        out = self._capture(_make_entry(outcome="deployed"))
        self.assertIn("DEPLOYED", out)

    def test_render_includes_route(self):
        out = self._capture(_make_entry(route="escalate"))
        self.assertIn("escalate", out)

    def test_render_includes_approved_by(self):
        out = self._capture(_make_entry(approved_by="@alice"))
        self.assertIn("@alice", out)

    def test_render_includes_risk_level(self):
        out = self._capture(_make_entry(risk="HIGH"))
        self.assertIn("HIGH", out)

    def test_render_includes_hypothesis(self):
        out = self._capture(_make_entry())
        self.assertIn("Connection pool exhaustion", out)

    def test_render_includes_gate1_decision(self):
        out = self._capture(_make_entry())
        self.assertIn("confirmed", out)

    def test_render_includes_gate2_decision(self):
        out = self._capture(_make_entry())
        self.assertIn("approved", out)

    def test_render_includes_sandbox_result(self):
        out = self._capture(_make_entry())
        self.assertIn("pass", out)

    def test_render_includes_reasoning_chain_step(self):
        out = self._capture(_make_entry())
        self.assertIn("Step 1", out)

    def test_render_compliance_flags_shown(self):
        out = self._capture(_make_compliance_entry())
        self.assertIn("POL-001", out)
        self.assertIn("2-person approval", out)

    def test_render_second_approver_shown_when_present(self):
        out = self._capture(_make_compliance_entry())
        self.assertIn("@bob", out)

    def test_render_second_approver_not_shown_when_na(self):
        # "N/A" second_approver should not clutter the output
        out = self._capture(_make_entry(second_approver="N/A"))
        # Should still render without error; N/A suppressed is OK
        self.assertIsInstance(out, str)

    def test_render_clarification_log_shown(self):
        entry = _make_entry(
            gate1_clarifications=[{"question": "Why pool?", "answer": "Timeout doubled."}]
        )
        out = self._capture(entry)
        self.assertIn("Why pool?", out)
        self.assertIn("Timeout doubled.", out)

    def test_render_auto_handled_entry(self):
        out = self._capture(_make_auto_entry())
        self.assertIn("AUTO-RESOLVED", out)
        self.assertIn("auto-handle", out)

    def test_render_with_index(self):
        out = self._capture(_make_entry(), index=3)
        self.assertIn("#3", out)

    def test_render_without_index(self):
        # Should not raise when index is None
        self._capture(_make_entry(), index=None)

    def test_render_empty_reasoning_chains_do_not_crash(self):
        entry = _make_entry(diagnosis_reasoning_chain=[], patch_reasoning_chain=[])
        self._capture(entry)

    def test_render_missing_optional_fields_do_not_crash(self):
        minimal = {"alert_id": "alert-min", "outcome": "deployed"}
        self._capture(minimal)

    def test_render_patch_chain_trade_off_shown(self):
        out = self._capture(_make_entry())
        self.assertIn("Slow queries will fail", out)


# ══════════════════════════════════════════════════════════════════════════════
# render_summary_table
# ══════════════════════════════════════════════════════════════════════════════

class TestRenderSummaryTable(unittest.TestCase):

    def _capture(self, entries):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            render_summary_table(entries)
        return buf.getvalue()

    def test_empty_list_produces_no_output(self):
        out = self._capture([])
        self.assertEqual(out, "")

    def test_single_entry_shows_alert_id(self):
        out = self._capture([_make_entry("alert-001")])
        self.assertIn("alert-001", out)

    def test_multiple_entries_all_shown(self):
        entries = [_make_entry("alert-001"), _make_entry("alert-002"), _make_auto_entry()]
        out = self._capture(entries)
        self.assertIn("alert-001", out)
        self.assertIn("alert-002", out)
        self.assertIn("alert-003", out)

    def test_total_count_shown(self):
        entries = [_make_entry("alert-001"), _make_entry("alert-002")]
        out = self._capture(entries)
        self.assertIn("2", out)

    def test_outcome_shown_in_table(self):
        out = self._capture([_make_entry(outcome="deployed")])
        self.assertIn("deployed", out)

    def test_route_shown_in_table(self):
        out = self._capture([_make_entry(route="auto-handle")])
        self.assertIn("auto-handle", out)

    def test_approved_by_shown(self):
        out = self._capture([_make_entry(approved_by="@alice")])
        self.assertIn("@alice", out)


# ══════════════════════════════════════════════════════════════════════════════
# main() CLI
# ══════════════════════════════════════════════════════════════════════════════

class TestMainCLI(unittest.TestCase):

    def setUp(self):
        """Create a temp log file with 3 entries for most tests."""
        self._tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        entries = [
            _make_entry("alert-001"),
            _make_entry("alert-002"),
            _make_auto_entry(),
        ]
        for e in entries:
            self._tmp.write(json.dumps(e) + "\n")
        self._tmp.close()
        self.log_path = self._tmp.name

    def tearDown(self):
        if os.path.exists(self.log_path):
            os.unlink(self.log_path)

    def _run(self, argv):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = main(argv)
        return code, buf.getvalue()

    # --- --all ---

    def test_all_returns_zero(self):
        code, _ = self._run(["--all", "--log", self.log_path])
        self.assertEqual(code, 0)

    def test_all_renders_all_entries(self):
        _, out = self._run(["--all", "--log", self.log_path])
        self.assertIn("alert-001", out)
        self.assertIn("alert-002", out)
        self.assertIn("alert-003", out)

    def test_all_renders_summary_table_by_default(self):
        _, out = self._run(["--all", "--log", self.log_path])
        self.assertIn("AUDIT SUMMARY", out)

    def test_all_no_summary_skips_table(self):
        _, out = self._run(["--all", "--no-summary", "--log", self.log_path])
        self.assertNotIn("AUDIT SUMMARY", out)

    # --- --id ---

    def test_id_found_returns_zero(self):
        code, _ = self._run(["--id", "alert-001", "--log", self.log_path])
        self.assertEqual(code, 0)

    def test_id_renders_correct_entry(self):
        _, out = self._run(["--id", "alert-001", "--log", self.log_path])
        self.assertIn("alert-001", out)
        self.assertNotIn("alert-002", out)

    def test_id_not_found_returns_one(self):
        code, _ = self._run(["--id", "alert-999", "--log", self.log_path])
        self.assertEqual(code, 1)

    def test_id_case_insensitive(self):
        code, out = self._run(["--id", "ALERT-001", "--log", self.log_path])
        self.assertEqual(code, 0)
        self.assertIn("alert-001", out)

    # --- --tail ---

    def test_tail_1_returns_last_entry(self):
        _, out = self._run(["--tail", "1", "--log", self.log_path])
        self.assertIn("alert-003", out)
        self.assertNotIn("alert-001", out)

    def test_tail_2_returns_last_two(self):
        _, out = self._run(["--tail", "2", "--log", self.log_path])
        self.assertIn("alert-002", out)
        self.assertIn("alert-003", out)
        self.assertNotIn("alert-001", out)

    def test_tail_larger_than_log_shows_all(self):
        _, out = self._run(["--tail", "100", "--log", self.log_path])
        self.assertIn("alert-001", out)
        self.assertIn("alert-003", out)

    # --- missing / empty log ---

    def test_missing_log_returns_one(self):
        code, _ = self._run(["--all", "--log", "/nonexistent/audit.json"])
        self.assertEqual(code, 1)

    def test_empty_log_returns_zero(self):
        empty = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        empty.close()
        try:
            code, _ = self._run(["--all", "--log", empty.name])
            self.assertEqual(code, 0)
        finally:
            os.unlink(empty.name)

    # --- no args ---

    def test_no_args_returns_one(self):
        code, _ = self._run([])
        self.assertEqual(code, 1)

    # --- custom log path ---

    def test_custom_log_path_respected(self):
        code, out = self._run(["--all", "--log", self.log_path])
        self.assertEqual(code, 0)
        self.assertIn("alert-001", out)

    # --- content correctness ---

    def test_compliance_flags_visible_in_all_output(self):
        # Write a log with a compliance entry
        tmp2 = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp2.write(json.dumps(_make_compliance_entry()) + "\n")
        tmp2.close()
        try:
            _, out = self._run(["--all", "--log", tmp2.name])
            self.assertIn("POL-001", out)
        finally:
            os.unlink(tmp2.name)

    def test_reasoning_chain_visible_in_output(self):
        _, out = self._run(["--all", "--log", self.log_path])
        self.assertIn("Step 1", out)

    def test_second_approver_visible_when_set(self):
        tmp2 = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp2.write(json.dumps(_make_compliance_entry()) + "\n")
        tmp2.close()
        try:
            _, out = self._run(["--all", "--log", tmp2.name])
            self.assertIn("@bob", out)
        finally:
            os.unlink(tmp2.name)


if __name__ == "__main__":
    unittest.main(verbosity=2)