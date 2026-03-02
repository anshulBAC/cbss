"""
Unit tests for gate UIs: gate1_ui, gate2_ui.
Uses unittest.mock to simulate CLI input — no API key required.
"""

import sys
import os
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gates.gate1_ui import run_gate1
from gates.gate2_ui import run_gate2


# ── Sample data ───────────────────────────────────────────────────────────────

SAMPLE_DIAGNOSIS = {
    "hypotheses": [
        {
            "id": 1,
            "description": "Connection pool exhaustion caused by increased timeout",
            "confidence": 0.85,
            "reasoning": "Recent commit doubled pool timeout, halving effective capacity.",
            "uncertainty_flags": ["no real-time metrics available"],
        },
        {
            "id": 2,
            "description": "Background session cleanup worker failing silently",
            "confidence": 0.60,
            "reasoning": "Cleanup moved to background worker 5 days ago; worker may be lagging.",
            "uncertainty_flags": [],
        },
    ],
    "context_freshness_warning": False,
}

SAMPLE_PATCH = {
    "diff": "--- a/src/db/connection.py\n+++ b/src/db/connection.py\n@@ -8 +8 @@\n-POOL_TIMEOUT = 60\n+POOL_TIMEOUT = 30",
    "reasoning": "Revert timeout increase to restore pool capacity.",
    "blast_radius": {
        "level": "MEDIUM",
        "services_touched": ["api-gateway", "billing-service"],
        "files_touched": ["src/db/connection.py"],
        "notes": "Touches shared postgres connection pool.",
    },
    "uncertainty_flags": [],
}


# ── Gate 1 Tests ──────────────────────────────────────────────────────────────

class TestGate1UI(unittest.TestCase):

    def test_confirm_hypothesis_1(self):
        with patch("builtins.input", side_effect=["@alice", "1"]):
            result = run_gate1(SAMPLE_DIAGNOSIS)
        self.assertEqual(result["decision"], "confirmed")
        self.assertEqual(result["selected_hypothesis_id"], 1)
        self.assertEqual(result["approved_by"], "@alice")
        self.assertEqual(result["correction"], "")

    def test_confirm_hypothesis_2(self):
        with patch("builtins.input", side_effect=["@bob", "2"]):
            result = run_gate1(SAMPLE_DIAGNOSIS)
        self.assertEqual(result["decision"], "confirmed")
        self.assertEqual(result["selected_hypothesis_id"], 2)

    def test_reject_with_correction(self):
        with patch("builtins.input", side_effect=["@alice", "r", "Redis OOM is the real cause"]):
            result = run_gate1(SAMPLE_DIAGNOSIS)
        self.assertEqual(result["decision"], "rejected")
        self.assertEqual(result["selected_hypothesis_id"], -1)
        self.assertEqual(result["correction"], "Redis OOM is the real cause")
        self.assertEqual(result["approved_by"], "@alice")

    def test_invalid_number_then_valid(self):
        # 99 and 0 are out of range; 1 is valid
        with patch("builtins.input", side_effect=["@alice", "99", "0", "1"]):
            result = run_gate1(SAMPLE_DIAGNOSIS)
        self.assertEqual(result["decision"], "confirmed")
        self.assertEqual(result["selected_hypothesis_id"], 1)

    def test_no_hypotheses_auto_rejects(self):
        empty_diagnosis = {"hypotheses": [], "context_freshness_warning": False}
        with patch("builtins.input", side_effect=["@alice"]):
            result = run_gate1(empty_diagnosis)
        self.assertEqual(result["decision"], "rejected")
        self.assertEqual(result["selected_hypothesis_id"], -1)
        self.assertIn("Manual triage", result["correction"])

    def test_freshness_warning_does_not_crash(self):
        stale = dict(SAMPLE_DIAGNOSIS, context_freshness_warning=True)
        with patch("builtins.input", side_effect=["@alice", "1"]):
            result = run_gate1(stale)
        self.assertEqual(result["decision"], "confirmed")

    def test_empty_handle_defaults_to_unknown(self):
        with patch("builtins.input", side_effect=["", "1"]):
            result = run_gate1(SAMPLE_DIAGNOSIS)
        self.assertEqual(result["approved_by"], "@unknown")

    def test_empty_correction_retries(self):
        # Empty correction causes the loop to restart from "confirm/reject" prompt
        with patch("builtins.input", side_effect=["@alice", "r", "", "r", "valid correction text"]):
            result = run_gate1(SAMPLE_DIAGNOSIS)
        self.assertEqual(result["decision"], "rejected")
        self.assertEqual(result["correction"], "valid correction text")

    def test_result_always_has_required_keys(self):
        with patch("builtins.input", side_effect=["@alice", "1"]):
            result = run_gate1(SAMPLE_DIAGNOSIS)
        for key in ["decision", "selected_hypothesis_id", "correction", "approved_by"]:
            self.assertIn(key, result)

    def test_single_hypothesis_confirm(self):
        single = {
            "hypotheses": [
                {"id": 1, "description": "Only hypothesis", "confidence": 0.9,
                 "reasoning": "Obvious.", "uncertainty_flags": []}
            ],
            "context_freshness_warning": False,
        }
        with patch("builtins.input", side_effect=["@alice", "1"]):
            result = run_gate1(single)
        self.assertEqual(result["selected_hypothesis_id"], 1)


# ── Gate 2 Tests ──────────────────────────────────────────────────────────────

class TestGate2UI(unittest.TestCase):

    def test_approve_returns_correct_structure(self):
        with patch("builtins.input", side_effect=["@alice", "approve", "low traffic window"]):
            result = run_gate2(SAMPLE_PATCH)
        self.assertEqual(result["decision"], "approved")
        self.assertEqual(result["rationale"], "low traffic window")
        self.assertEqual(result["approved_by"], "@alice")

    def test_reject_returns_correct_structure(self):
        with patch("builtins.input", side_effect=["@alice", "reject", "peak hours — defer to 2am"]):
            result = run_gate2(SAMPLE_PATCH)
        self.assertEqual(result["decision"], "rejected")
        self.assertEqual(result["rationale"], "peak hours — defer to 2am")
        self.assertEqual(result["approved_by"], "@alice")

    def test_invalid_input_then_approve(self):
        # "yes", "APPROVE", "Approve" are all invalid; only lowercase "approve" works
        with patch("builtins.input", side_effect=["@alice", "yes", "APPROVE", "approve", "looks good"]):
            result = run_gate2(SAMPLE_PATCH)
        self.assertEqual(result["decision"], "approved")

    def test_empty_rationale_retries(self):
        # Empty rationale causes the loop to restart from "approve/reject" prompt
        with patch("builtins.input", side_effect=["@alice", "approve", "", "approve", "non-empty rationale"]):
            result = run_gate2(SAMPLE_PATCH)
        self.assertEqual(result["rationale"], "non-empty rationale")

    def test_empty_handle_defaults_to_unknown(self):
        with patch("builtins.input", side_effect=["", "approve", "rationale"]):
            result = run_gate2(SAMPLE_PATCH)
        self.assertEqual(result["approved_by"], "@unknown")

    def test_with_optional_risk_score_context(self):
        risk_score = {"overall": "HIGH", "freshness": "FRESH", "why": "auth-service in production"}
        with patch("builtins.input", side_effect=["@alice", "approve", "understood the risk"]):
            result = run_gate2(SAMPLE_PATCH, risk_score=risk_score)
        self.assertEqual(result["decision"], "approved")

    def test_result_always_has_required_keys(self):
        with patch("builtins.input", side_effect=["@alice", "approve", "rationale"]):
            result = run_gate2(SAMPLE_PATCH)
        for key in ["decision", "rationale", "approved_by"]:
            self.assertIn(key, result)

    def test_reject_empty_rationale_retries(self):
        # Empty rationale causes the loop to restart from "approve/reject" prompt
        with patch("builtins.input", side_effect=["@alice", "reject", "", "reject", "valid reject reason"]):
            result = run_gate2(SAMPLE_PATCH)
        self.assertEqual(result["decision"], "rejected")
        self.assertEqual(result["rationale"], "valid reject reason")

    def test_patch_with_no_blast_radius_does_not_crash(self):
        minimal_patch = {
            "diff": "--- a/file.py\n+++ b/file.py",
            "reasoning": "fix",
            "blast_radius": {},
            "uncertainty_flags": [],
        }
        with patch("builtins.input", side_effect=["@alice", "approve", "minimal patch, safe"]):
            result = run_gate2(minimal_patch)
        self.assertEqual(result["decision"], "approved")

    def test_patch_with_uncertainty_flags_does_not_crash(self):
        flagged_patch = dict(SAMPLE_PATCH, uncertainty_flags=["no test coverage", "large blast radius"])
        with patch("builtins.input", side_effect=["@alice", "approve", "accepted risk"]):
            result = run_gate2(flagged_patch)
        self.assertEqual(result["decision"], "approved")


if __name__ == "__main__":
    unittest.main(verbosity=2)
