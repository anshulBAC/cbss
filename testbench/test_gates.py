"""
Phase 4 tests for gate1_ui and gate2_ui.

Covers:
  Gate 1:
    - reasoning chain display (backward compat: absent, empty, present)
    - clarification_log always in output
    - '?' triggers _ask_clarification and logs entry
    - empty question after '?' does not log or call API
    - multiple clarifications accumulated
    - clarification_log present in all return paths
    - clarification API failure returns graceful string

  Gate 2:
    - reasoning chain display (backward compat)
    - compliance check display (backward compat)
    - diff depth 'd' option toggles view
    - invalid depth choice defaults to "2"
    - clarification_log always in output
    - '?' triggers clarification and logs entry
    - clarification_log present in approved and rejected paths
    - clarification API failure returns graceful string
    - all existing keys still present in output (backward compat)

No real API key required — all OpenAI calls are mocked.
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gates.gate1_ui import run_gate1, _ask_clarification as gate1_clarify
from gates.gate2_ui import run_gate2, _ask_clarification as gate2_clarify, _diff_stats


# ── Shared fixtures ───────────────────────────────────────────────────────────

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
            "reasoning": "Cleanup moved to background worker 5 days ago.",
            "uncertainty_flags": [],
        },
    ],
    "context_freshness_warning": False,
    "reasoning_chain": [
        {
            "step": 1,
            "observation": "alert.error shows connection pool exhaustion",
            "inference": "Resource exhaustion, not logic bug",
            "evidence": "alert.error",
        },
        {
            "step": 2,
            "observation": "git_history.recent_commits[0] doubled POOL_TIMEOUT",
            "inference": "Timeout increase halves throughput",
            "evidence": "git_history.recent_commits[0]",
        },
    ],
}

SAMPLE_PATCH = {
    "diff": (
        "--- a/src/db/connection.py\n"
        "+++ b/src/db/connection.py\n"
        "@@ -8 +8 @@\n"
        "-POOL_TIMEOUT = 60\n"
        "+POOL_TIMEOUT = 30"
    ),
    "reasoning": "Revert timeout increase to restore pool capacity.",
    "blast_radius": {
        "level": "MEDIUM",
        "services_touched": ["api-gateway", "billing-service"],
        "files_touched": ["src/db/connection.py"],
        "notes": "Touches shared postgres connection pool.",
    },
    "uncertainty_flags": [],
    "reasoning_chain": [
        {
            "step": 1,
            "observation": "git_history.recent_commits[0] increased POOL_TIMEOUT",
            "decision": "Revert to 30s",
            "trade_off": "Slow queries >30s will fail",
        },
        {
            "step": 2,
            "observation": "dependencies.shared_infra includes postgres-primary",
            "decision": "Minimal change only",
            "trade_off": "Shared infra means blast radius is real",
        },
    ],
    "compliance_check": {
        "flags_reviewed": [],
        "assessment": "No compliance flags found.",
        "patch_is_compliant": True,
    },
}


def _mock_openai_answer(text="The connection pool is exhausted because timeout doubled."):
    """Return a mock OpenAI client whose completion returns `text`."""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = text
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


# ══════════════════════════════════════════════════════════════════════════════
# GATE 1 — Phase 4 tests
# ══════════════════════════════════════════════════════════════════════════════

class TestGate1ReasoningChain(unittest.TestCase):
    """Reasoning chain display is read-only; it must not affect gate output shape."""

    def test_no_reasoning_chain_key_does_not_crash(self):
        """Backward compat: diagnosis without 'reasoning_chain' should work fine."""
        no_chain = {k: v for k, v in SAMPLE_DIAGNOSIS.items() if k != "reasoning_chain"}
        with patch("builtins.input", side_effect=["@alice", "1"]):
            result = run_gate1(no_chain)
        self.assertEqual(result["decision"], "confirmed")

    def test_empty_reasoning_chain_does_not_crash(self):
        empty_chain = dict(SAMPLE_DIAGNOSIS, reasoning_chain=[])
        with patch("builtins.input", side_effect=["@alice", "1"]):
            result = run_gate1(empty_chain)
        self.assertEqual(result["decision"], "confirmed")

    def test_reasoning_chain_present_does_not_affect_decision(self):
        with patch("builtins.input", side_effect=["@alice", "2"]):
            result = run_gate1(SAMPLE_DIAGNOSIS)
        self.assertEqual(result["selected_hypothesis_id"], 2)

    def test_reasoning_chain_present_does_not_affect_rejection(self):
        with patch("builtins.input", side_effect=["@alice", "r", "Redis OOM is the cause"]):
            result = run_gate1(SAMPLE_DIAGNOSIS)
        self.assertEqual(result["decision"], "rejected")
        self.assertEqual(result["correction"], "Redis OOM is the cause")


class TestGate1ClarificationLog(unittest.TestCase):
    """clarification_log must always be present and correctly populated."""

    def test_clarification_log_empty_when_no_questions_asked_confirm(self):
        with patch("builtins.input", side_effect=["@alice", "1"]):
            result = run_gate1(SAMPLE_DIAGNOSIS)
        self.assertIn("clarification_log", result)
        self.assertEqual(result["clarification_log"], [])

    def test_clarification_log_empty_when_no_questions_asked_reject(self):
        with patch("builtins.input", side_effect=["@alice", "r", "manual correction"]):
            result = run_gate1(SAMPLE_DIAGNOSIS)
        self.assertIn("clarification_log", result)
        self.assertEqual(result["clarification_log"], [])

    def test_clarification_log_present_in_no_hypothesis_path(self):
        empty_diag = {"hypotheses": [], "context_freshness_warning": False}
        with patch("builtins.input", side_effect=["@alice"]):
            result = run_gate1(empty_diag)
        self.assertIn("clarification_log", result)
        self.assertIsInstance(result["clarification_log"], list)

    def test_question_mark_triggers_clarification_and_logs_entry(self):
        with patch("openai.OpenAI", return_value=_mock_openai_answer("Pool is exhausted.")):
            with patch("builtins.input", side_effect=[
                "@alice",
                "?", "Why is the pool exhausted?",
                "1",
            ]):
                result = run_gate1(SAMPLE_DIAGNOSIS)
        self.assertEqual(result["decision"], "confirmed")
        self.assertEqual(len(result["clarification_log"]), 1)
        self.assertEqual(result["clarification_log"][0]["question"], "Why is the pool exhausted?")
        self.assertEqual(result["clarification_log"][0]["answer"], "Pool is exhausted.")

    def test_clarification_log_on_reject_path(self):
        with patch("openai.OpenAI", return_value=_mock_openai_answer("It's the timeout.")):
            with patch("builtins.input", side_effect=[
                "@alice",
                "?", "What caused this?",
                "r", "My correction",
            ]):
                result = run_gate1(SAMPLE_DIAGNOSIS)
        self.assertEqual(result["decision"], "rejected")
        self.assertEqual(len(result["clarification_log"]), 1)
        self.assertEqual(result["clarification_log"][0]["question"], "What caused this?")

    def test_multiple_clarifications_accumulated(self):
        with patch("openai.OpenAI", return_value=_mock_openai_answer("Answer.")):
            with patch("builtins.input", side_effect=[
                "@alice",
                "?", "Question 1",
                "?", "Question 2",
                "1",
            ]):
                result = run_gate1(SAMPLE_DIAGNOSIS)
        self.assertEqual(len(result["clarification_log"]), 2)
        self.assertEqual(result["clarification_log"][0]["question"], "Question 1")
        self.assertEqual(result["clarification_log"][1]["question"], "Question 2")

    def test_empty_question_not_logged_and_no_api_call(self):
        with patch("openai.OpenAI", return_value=_mock_openai_answer()) as mock_ctor:
            with patch("builtins.input", side_effect=[
                "@alice",
                "?", "",   # empty question
                "1",
            ]):
                result = run_gate1(SAMPLE_DIAGNOSIS)
        # No API call should have been made
        mock_ctor.return_value.chat.completions.create.assert_not_called()
        self.assertEqual(result["clarification_log"], [])

    def test_clarification_api_failure_returns_graceful_string(self):
        """If OpenAI raises, _ask_clarification returns a graceful error, not an exception."""
        failing_client = MagicMock()
        failing_client.chat.completions.create.side_effect = Exception("timeout")
        with patch("openai.OpenAI", return_value=failing_client):
            with patch("builtins.input", side_effect=[
                "@alice",
                "?", "Will this fix work?",
                "1",
            ]):
                result = run_gate1(SAMPLE_DIAGNOSIS)
        self.assertEqual(result["decision"], "confirmed")
        self.assertEqual(len(result["clarification_log"]), 1)
        self.assertIn("unavailable", result["clarification_log"][0]["answer"].lower())

    def test_output_still_has_all_original_keys(self):
        """Phase 4 must not drop any key from the original gate1 contract."""
        with patch("builtins.input", side_effect=["@alice", "1"]):
            result = run_gate1(SAMPLE_DIAGNOSIS)
        for key in ["decision", "selected_hypothesis_id", "correction", "approved_by",
                    "clarification_log"]:
            self.assertIn(key, result)


# ══════════════════════════════════════════════════════════════════════════════
# GATE 2 — Phase 4 tests
# ══════════════════════════════════════════════════════════════════════════════

class TestGate2ReasoningChainAndCompliance(unittest.TestCase):
    """Reasoning chain and compliance check are read-only display; must not affect output."""

    def test_no_reasoning_chain_does_not_crash(self):
        no_chain = {k: v for k, v in SAMPLE_PATCH.items() if k != "reasoning_chain"}
        with patch("builtins.input", side_effect=["@alice", "approve", "ok"]):
            result = run_gate2(no_chain)
        self.assertEqual(result["decision"], "approved")

    def test_empty_reasoning_chain_does_not_crash(self):
        empty = dict(SAMPLE_PATCH, reasoning_chain=[])
        with patch("builtins.input", side_effect=["@alice", "approve", "ok"]):
            result = run_gate2(empty)
        self.assertEqual(result["decision"], "approved")

    def test_no_compliance_check_does_not_crash(self):
        no_cc = {k: v for k, v in SAMPLE_PATCH.items() if k != "compliance_check"}
        with patch("builtins.input", side_effect=["@alice", "approve", "ok"]):
            result = run_gate2(no_cc)
        self.assertEqual(result["decision"], "approved")

    def test_non_compliant_flag_does_not_block_gate(self):
        """Gate 2 human authority is final — AI non-compliant flag must not block."""
        flagged = dict(SAMPLE_PATCH)
        flagged["compliance_check"] = {
            "flags_reviewed": ["freeze window active"],
            "assessment": "Patch may violate freeze.",
            "patch_is_compliant": False,
        }
        with patch("builtins.input", side_effect=["@alice", "approve", "accepted risk"]):
            result = run_gate2(flagged)
        self.assertEqual(result["decision"], "approved")


class TestGate2DiffDepth(unittest.TestCase):
    """'d' in the decision loop triggers diff re-display; does not block approve/reject."""

    def test_d_then_approve_works(self):
        with patch("builtins.input", side_effect=[
            "@alice",
            "d", "2",        # change diff depth to normal
            "approve", "ok",
        ]):
            result = run_gate2(SAMPLE_PATCH)
        self.assertEqual(result["decision"], "approved")

    def test_d_depth_3_then_reject_works(self):
        with patch("builtins.input", side_effect=[
            "@alice",
            "d", "3",
            "reject", "too risky",
        ]):
            result = run_gate2(SAMPLE_PATCH)
        self.assertEqual(result["decision"], "rejected")

    def test_invalid_depth_choice_does_not_crash(self):
        with patch("builtins.input", side_effect=[
            "@alice",
            "d", "9",        # invalid — should default to "2"
            "approve", "ok",
        ]):
            result = run_gate2(SAMPLE_PATCH)
        self.assertEqual(result["decision"], "approved")

    def test_multiple_d_calls_before_approve(self):
        with patch("builtins.input", side_effect=[
            "@alice",
            "d", "1",
            "d", "3",
            "d", "2",
            "approve", "all views checked",
        ]):
            result = run_gate2(SAMPLE_PATCH)
        self.assertEqual(result["rationale"], "all views checked")

    def test_existing_approve_flow_unchanged(self):
        """Verify original approve flow (no 'd') still works — backward compat."""
        with patch("builtins.input", side_effect=["@alice", "approve", "low traffic window"]):
            result = run_gate2(SAMPLE_PATCH)
        self.assertEqual(result["decision"], "approved")
        self.assertEqual(result["rationale"], "low traffic window")

    def test_existing_reject_flow_unchanged(self):
        with patch("builtins.input", side_effect=["@alice", "reject", "peak hours"]):
            result = run_gate2(SAMPLE_PATCH)
        self.assertEqual(result["decision"], "rejected")


class TestGate2ClarificationLog(unittest.TestCase):
    """clarification_log must always be present and correctly populated."""

    def test_clarification_log_empty_on_approve(self):
        with patch("builtins.input", side_effect=["@alice", "approve", "ok"]):
            result = run_gate2(SAMPLE_PATCH)
        self.assertIn("clarification_log", result)
        self.assertEqual(result["clarification_log"], [])

    def test_clarification_log_empty_on_reject(self):
        with patch("builtins.input", side_effect=["@alice", "reject", "too risky"]):
            result = run_gate2(SAMPLE_PATCH)
        self.assertIn("clarification_log", result)
        self.assertEqual(result["clarification_log"], [])

    def test_question_mark_triggers_clarification_and_logs(self):
        with patch("openai.OpenAI", return_value=_mock_openai_answer("Reverts timeout.")):
            with patch("builtins.input", side_effect=[
                "@alice",
                "?", "What does this patch actually do?",
                "approve", "understood",
            ]):
                result = run_gate2(SAMPLE_PATCH)
        self.assertEqual(result["decision"], "approved")
        self.assertEqual(len(result["clarification_log"]), 1)
        self.assertEqual(result["clarification_log"][0]["question"],
                         "What does this patch actually do?")
        self.assertEqual(result["clarification_log"][0]["answer"], "Reverts timeout.")

    def test_clarification_on_reject_path(self):
        with patch("openai.OpenAI", return_value=_mock_openai_answer("High blast radius.")):
            with patch("builtins.input", side_effect=[
                "@alice",
                "?", "How wide is the blast radius?",
                "reject", "too wide",
            ]):
                result = run_gate2(SAMPLE_PATCH)
        self.assertEqual(result["decision"], "rejected")
        self.assertEqual(len(result["clarification_log"]), 1)

    def test_multiple_clarifications_accumulated(self):
        with patch("openai.OpenAI", return_value=_mock_openai_answer("Answer.")):
            with patch("builtins.input", side_effect=[
                "@alice",
                "?", "Question A",
                "?", "Question B",
                "approve", "ok",
            ]):
                result = run_gate2(SAMPLE_PATCH)
        self.assertEqual(len(result["clarification_log"]), 2)
        questions = [e["question"] for e in result["clarification_log"]]
        self.assertIn("Question A", questions)
        self.assertIn("Question B", questions)

    def test_empty_question_not_logged(self):
        with patch("openai.OpenAI", return_value=_mock_openai_answer()) as mock_ctor:
            with patch("builtins.input", side_effect=[
                "@alice",
                "?", "",
                "approve", "ok",
            ]):
                result = run_gate2(SAMPLE_PATCH)
        mock_ctor.return_value.chat.completions.create.assert_not_called()
        self.assertEqual(result["clarification_log"], [])

    def test_clarification_api_failure_graceful(self):
        failing = MagicMock()
        failing.chat.completions.create.side_effect = Exception("network error")
        with patch("openai.OpenAI", return_value=failing):
            with patch("builtins.input", side_effect=[
                "@alice",
                "?", "Will this break prod?",
                "approve", "ok",
            ]):
                result = run_gate2(SAMPLE_PATCH)
        self.assertEqual(result["decision"], "approved")
        self.assertEqual(len(result["clarification_log"]), 1)
        self.assertIn("unavailable", result["clarification_log"][0]["answer"].lower())

    def test_output_has_all_required_keys(self):
        """Phase 4 must not drop any key from the original gate2 contract."""
        with patch("builtins.input", side_effect=["@alice", "approve", "ok"]):
            result = run_gate2(SAMPLE_PATCH)
        for key in ["decision", "rationale", "approved_by", "clarification_log"]:
            self.assertIn(key, result)


class TestDiffStatsHelper(unittest.TestCase):
    """Unit tests for _diff_stats to verify stats parsing."""

    def test_counts_additions_and_deletions(self):
        diff = "--- a/file.py\n+++ b/file.py\n-old line\n+new line"
        stats = _diff_stats(diff)
        self.assertIn("+1", stats)
        self.assertIn("-1", stats)

    def test_extracts_file_name(self):
        diff = "--- a/src/db/connection.py\n+++ b/src/db/connection.py\n-x\n+y"
        stats = _diff_stats(diff)
        self.assertIn("connection.py", stats)

    def test_empty_diff_returns_string(self):
        stats = _diff_stats("")
        self.assertIsInstance(stats, str)

    def test_no_changes_shows_zero_counts(self):
        diff = "--- a/file.py\n+++ b/file.py"
        stats = _diff_stats(diff)
        self.assertIn("+0", stats)
        self.assertIn("-0", stats)


if __name__ == "__main__":
    unittest.main(verbosity=2)