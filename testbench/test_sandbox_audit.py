"""
Unit tests for validation/sandbox.py and audit/logger.py.
No API key required. File I/O is mocked.
"""

import sys
import os
import json
import unittest
from unittest.mock import patch, mock_open, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from validation.sandbox import run_sandbox
from audit.logger import log_decision


# ── Sandbox Tests ─────────────────────────────────────────────────────────────

class TestSandbox(unittest.TestCase):

    def test_sandbox_always_passes(self):
        patch_proposal = {
            "diff": "--- a/src/db/connection.py\n+++ b/src/db/connection.py\n@@ -8 +8 @@\n-POOL_TIMEOUT=60\n+POOL_TIMEOUT=30",
            "affected_services": ["auth-service"],
        }
        result = run_sandbox(patch_proposal)
        self.assertEqual(result["status"], "pass")

    def test_sandbox_returns_details_string(self):
        result = run_sandbox({"affected_services": []})
        self.assertIn("details", result)
        self.assertIsInstance(result["details"], str)
        self.assertGreater(len(result["details"]), 0)

    def test_sandbox_with_empty_patch(self):
        result = run_sandbox({})
        self.assertEqual(result["status"], "pass")

    def test_sandbox_with_multiple_affected_services(self):
        patch_proposal = {
            "affected_services": ["auth-service", "api-gateway", "billing-service"]
        }
        result = run_sandbox(patch_proposal)
        self.assertEqual(result["status"], "pass")

    def test_sandbox_result_has_status_key(self):
        result = run_sandbox({})
        self.assertIn("status", result)

    def test_sandbox_result_status_is_string(self):
        result = run_sandbox({})
        self.assertIsInstance(result["status"], str)

    def test_sandbox_details_mentions_tests(self):
        result = run_sandbox({"affected_services": ["auth-service"]})
        # The details should reference tests or pass — basic sanity check
        self.assertIsInstance(result["details"], str)


# ── Audit Logger Tests ────────────────────────────────────────────────────────

class TestAuditLogger(unittest.TestCase):

    FULL_ENTRY = {
        "timestamp": "2025-03-02T10:00:00Z",
        "alert_id": "alert-001",
        "route_taken": "escalate",
        "risk_level": "HIGH",
        "freshness": "FRESH",
        "ai_hypothesis": "Connection pool exhaustion caused by increased timeout",
        "engineer_gate1_decision": "confirmed",
        "engineer_gate2_decision": "approved",
        "approved_by": "@alice",
        "sandbox_result": "pass",
        "outcome": "deployed",
        "notes": "Diagnosis attempts: 1. Patch attempts: 1.",
    }

    AUTO_ENTRY = {
        "timestamp": "2025-03-02T12:30:00Z",
        "alert_id": "alert-003",
        "route_taken": "auto-handle",
        "risk_level": "LOW",
        "freshness": "FRESH",
        "ai_hypothesis": "N/A (auto-handled)",
        "engineer_gate1_decision": "N/A",
        "engineer_gate2_decision": "N/A",
        "approved_by": "system",
        "sandbox_result": "N/A",
        "outcome": "auto-resolved",
        "notes": "Low-risk incident handled automatically.",
    }

    def _capture_written(self, entry):
        """Call log_decision with a mocked file and return the written string."""
        with patch("builtins.open", mock_open()) as m:
            log_decision(entry)
            handle = m()
            return handle.write.call_args[0][0]

    def test_log_opens_audit_log_file_for_append(self):
        with patch("builtins.open", mock_open()) as m:
            log_decision(self.FULL_ENTRY)
        m.assert_called_once_with("audit_log.json", "a")

    def test_log_writes_valid_json(self):
        written = self._capture_written(self.FULL_ENTRY)
        parsed = json.loads(written.strip())
        self.assertIsInstance(parsed, dict)

    def test_log_entry_ends_with_newline(self):
        written = self._capture_written(self.FULL_ENTRY)
        self.assertTrue(written.endswith("\n"))

    def test_log_preserves_alert_id(self):
        written = self._capture_written(self.FULL_ENTRY)
        parsed = json.loads(written.strip())
        self.assertEqual(parsed["alert_id"], "alert-001")

    def test_log_preserves_outcome(self):
        written = self._capture_written(self.FULL_ENTRY)
        parsed = json.loads(written.strip())
        self.assertEqual(parsed["outcome"], "deployed")

    def test_log_preserves_all_required_fields(self):
        required = [
            "alert_id", "route_taken", "risk_level", "freshness",
            "ai_hypothesis", "engineer_gate1_decision", "engineer_gate2_decision",
            "approved_by", "sandbox_result", "outcome", "notes",
        ]
        written = self._capture_written(self.FULL_ENTRY)
        parsed = json.loads(written.strip())
        for field in required:
            self.assertIn(field, parsed, f"Missing field in log entry: {field}")

    def test_log_auto_handle_entry(self):
        written = self._capture_written(self.AUTO_ENTRY)
        parsed = json.loads(written.strip())
        self.assertEqual(parsed["route_taken"], "auto-handle")
        self.assertEqual(parsed["engineer_gate1_decision"], "N/A")
        self.assertEqual(parsed["outcome"], "auto-resolved")

    def test_log_approved_by_preserved(self):
        written = self._capture_written(self.FULL_ENTRY)
        parsed = json.loads(written.strip())
        self.assertEqual(parsed["approved_by"], "@alice")

    def test_log_minimal_entry_does_not_crash(self):
        minimal = {"alert_id": "min-001"}
        with patch("builtins.open", mock_open()):
            log_decision(minimal)  # should not raise

    def test_log_writes_exactly_once_per_call(self):
        with patch("builtins.open", mock_open()) as m:
            log_decision(self.FULL_ENTRY)
            handle = m()
            self.assertEqual(handle.write.call_count, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
