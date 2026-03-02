"""
Integration tests for Codex Guardian.

Tests the full scoring + routing chain, the diagnose → Gate 1 flow, and the
patch → Gate 2 flow using mocked OpenAI responses and mocked CLI input.

No real API key required — all external calls are intercepted.
"""

import sys
import os
import json
import unittest
from unittest.mock import patch, MagicMock, mock_open

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Load fixtures ─────────────────────────────────────────────────────────────

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

with open(os.path.join(FIXTURES, "diagnosis_response.json")) as f:
    MOCK_DIAGNOSIS = json.load(f)

with open(os.path.join(FIXTURES, "patch_response.json")) as f:
    MOCK_PATCH = json.load(f)

# ── Shared test data ──────────────────────────────────────────────────────────

LOW_RISK_ALERT = {
    "id": "alert-003",
    "service": "notification-service",
    "severity": "LOW",
    "error": "Deprecated config flag detected — fallback mode engaged",
    "affected_files": ["src/config/flags.py"],
    "environment": "staging",
}

HIGH_RISK_ALERT = {
    "id": "alert-001",
    "service": "auth-service",
    "severity": "HIGH",
    "error": "Connection pool exhaustion — p99 latency spike to 4200ms",
    "affected_files": ["src/db/connection.py", "src/auth/session.py"],
    "environment": "production",
}

LOW_RISK_DEPS = {
    "service": "notification-service",
    "depends_on": ["config-service"],
    "depended_on_by": [],
    "shared_infra": [],
}

HIGH_RISK_DEPS = {
    "service": "auth-service",
    "depends_on": ["postgres-primary", "redis-cache", "user-service"],
    "depended_on_by": ["api-gateway", "billing-service", "admin-dashboard"],
    "shared_infra": ["postgres-primary", "redis-cache"],
}

FRESH_GIT_HISTORY = {
    "recent_commits": [
        {
            "hash": "a1b2c3d",
            "author": "sarah.chen",
            "message": "fix: increase connection pool timeout from 30s to 60s",
            "files_changed": ["src/db/connection.py"],
            "days_ago": 2,
        }
    ],
    "last_reviewed_days_ago": 3,
}

STALE_GIT_HISTORY = {
    "recent_commits": [
        {"hash": f"x{i}", "author": "dev", "message": "chore: update",
         "files_changed": [], "days_ago": i}
        for i in range(5)
    ],
    "last_reviewed_days_ago": 20,
}

SAMPLE_CONTEXT_BUNDLE = {
    "alert": HIGH_RISK_ALERT,
    "git_history": FRESH_GIT_HISTORY,
    "dependencies": HIGH_RISK_DEPS,
    "org_context": {
        "team_notes": ["Auth team is mid-sprint"],
        "known_constraints": ["Connection pool max is 20"],
        "injected_context": [],
    },
}


# ── Routing Integration Tests ─────────────────────────────────────────────────

class TestRoutingIntegration(unittest.TestCase):
    """Verify the scoring + routing chain produces the correct route for each scenario."""

    def _run_routing(self, alert, deps, git_history):
        from scoring.risk_score import score_risk
        from scoring.freshness_score import score_freshness
        from scoring.router import route
        risk = score_risk(alert, deps)
        freshness = score_freshness(git_history)
        return risk, freshness, route(risk, freshness)

    def test_low_risk_staging_routes_to_auto_handle(self):
        risk, freshness, routing = self._run_routing(
            LOW_RISK_ALERT, LOW_RISK_DEPS, FRESH_GIT_HISTORY
        )
        self.assertEqual(risk["level"], "LOW")
        self.assertEqual(freshness["score"], "FRESH")
        self.assertEqual(routing["route"], "auto-handle")

    def test_high_risk_production_routes_to_escalate(self):
        risk, freshness, routing = self._run_routing(
            HIGH_RISK_ALERT, HIGH_RISK_DEPS, FRESH_GIT_HISTORY
        )
        self.assertEqual(risk["level"], "HIGH")
        self.assertEqual(routing["route"], "escalate")

    def test_stale_context_escalates_even_when_low_risk(self):
        risk, freshness, routing = self._run_routing(
            LOW_RISK_ALERT, LOW_RISK_DEPS, STALE_GIT_HISTORY
        )
        self.assertEqual(freshness["score"], "STALE")
        self.assertEqual(routing["route"], "escalate")

    def test_high_risk_stale_escalates_with_both_reasons(self):
        risk, freshness, routing = self._run_routing(
            HIGH_RISK_ALERT, HIGH_RISK_DEPS, STALE_GIT_HISTORY
        )
        self.assertEqual(routing["route"], "escalate")
        explanation = routing["explanation"].upper()
        self.assertIn("HIGH", explanation)
        self.assertIn("STALE", explanation)

    def test_route_result_has_all_keys(self):
        from scoring.risk_score import score_risk
        from scoring.freshness_score import score_freshness
        from scoring.router import route
        risk = score_risk(HIGH_RISK_ALERT, HIGH_RISK_DEPS)
        freshness = score_freshness(FRESH_GIT_HISTORY)
        result = route(risk, freshness)
        for key in ["route", "risk_level", "freshness", "explanation"]:
            self.assertIn(key, result)


# ── Diagnosis + Gate 1 Integration Tests ─────────────────────────────────────

class TestDiagnosisGate1Integration(unittest.TestCase):
    """Test diagnose() with mocked OpenAI, then feed result into run_gate1()."""

    def _mock_openai_response(self, data):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps(data)
        return mock_response

    def test_diagnose_returns_hypotheses_from_fixture(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._mock_openai_response(MOCK_DIAGNOSIS)
        )
        with patch("openai.OpenAI", return_value=mock_client):
            from codex.diagnose import diagnose
            result = diagnose(SAMPLE_CONTEXT_BUNDLE)

        self.assertIn("hypotheses", result)
        self.assertEqual(len(result["hypotheses"]), 2)
        self.assertEqual(result["hypotheses"][0]["id"], 1)
        self.assertAlmostEqual(result["hypotheses"][0]["confidence"], 0.85)

    def test_diagnose_returns_freshness_warning_flag(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._mock_openai_response(MOCK_DIAGNOSIS)
        )
        with patch("openai.OpenAI", return_value=mock_client):
            from codex.diagnose import diagnose
            result = diagnose(SAMPLE_CONTEXT_BUNDLE)

        self.assertIn("context_freshness_warning", result)
        self.assertIsInstance(result["context_freshness_warning"], bool)

    def test_diagnose_raises_on_bad_json(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock()
        mock_client.chat.completions.create.return_value.choices[0].message.content = (
            "not json at all"
        )
        with patch("openai.OpenAI", return_value=mock_client):
            from codex.diagnose import diagnose
            with self.assertRaises(RuntimeError):
                diagnose(SAMPLE_CONTEXT_BUNDLE)

    def test_diagnose_raises_on_missing_hypotheses_key(self):
        bad_response = {"context_freshness_warning": False}  # missing "hypotheses"
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._mock_openai_response(bad_response)
        )
        with patch("openai.OpenAI", return_value=mock_client):
            from codex.diagnose import diagnose
            with self.assertRaises(RuntimeError):
                diagnose(SAMPLE_CONTEXT_BUNDLE)

    def test_gate1_confirm_after_diagnose(self):
        """Full flow: diagnose → engineer confirms hypothesis 1."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._mock_openai_response(MOCK_DIAGNOSIS)
        )
        with patch("openai.OpenAI", return_value=mock_client):
            from codex.diagnose import diagnose
            diagnosis_result = diagnose(SAMPLE_CONTEXT_BUNDLE)

        from gates.gate1_ui import run_gate1
        with patch("builtins.input", side_effect=["@engineer", "1"]):
            gate1_result = run_gate1(diagnosis_result)

        self.assertEqual(gate1_result["decision"], "confirmed")
        self.assertEqual(gate1_result["selected_hypothesis_id"], 1)

    def test_gate1_rejection_with_correction_after_diagnose(self):
        """Engineer rejects AI diagnosis and injects their own context."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._mock_openai_response(MOCK_DIAGNOSIS)
        )
        with patch("openai.OpenAI", return_value=mock_client):
            from codex.diagnose import diagnose
            diagnosis_result = diagnose(SAMPLE_CONTEXT_BUNDLE)

        from gates.gate1_ui import run_gate1
        with patch("builtins.input", side_effect=["@engineer", "r", "Redis OOM — saw it in logs"]):
            gate1_result = run_gate1(diagnosis_result)

        self.assertEqual(gate1_result["decision"], "rejected")
        self.assertEqual(gate1_result["correction"], "Redis OOM — saw it in logs")

        # Verify the correction can be injected back into context bundle
        bundle = dict(SAMPLE_CONTEXT_BUNDLE)
        bundle["org_context"]["injected_context"].append(
            f"[Gate 1 engineer correction] {gate1_result['correction']}"
        )
        self.assertIn(
            "[Gate 1 engineer correction] Redis OOM — saw it in logs",
            bundle["org_context"]["injected_context"]
        )


# ── Patch Generation + Gate 2 Integration Tests ───────────────────────────────

class TestPatchGate2Integration(unittest.TestCase):
    """Test generate_patch() with mocked OpenAI, then feed into run_gate2()."""

    def _mock_openai_response(self, data):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps(data)
        return mock_response

    def _confirmed_hypothesis(self):
        return MOCK_DIAGNOSIS["hypotheses"][0]

    def test_generate_patch_returns_required_fields(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._mock_openai_response(MOCK_PATCH)
        )
        with patch("openai.OpenAI", return_value=mock_client):
            from codex.patch import generate_patch
            result = generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)

        for field in ["diff", "explanation", "blast_radius", "confidence", "affected_services"]:
            self.assertIn(field, result)

    def test_generate_patch_diff_is_string(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._mock_openai_response(MOCK_PATCH)
        )
        with patch("openai.OpenAI", return_value=mock_client):
            from codex.patch import generate_patch
            result = generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)

        self.assertIsInstance(result["diff"], str)
        self.assertGreater(len(result["diff"]), 0)

    def test_generate_patch_affected_services_is_list(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._mock_openai_response(MOCK_PATCH)
        )
        with patch("openai.OpenAI", return_value=mock_client):
            from codex.patch import generate_patch
            result = generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)

        self.assertIsInstance(result["affected_services"], list)

    def test_generate_patch_raises_on_missing_field(self):
        bad_patch = {"diff": "--- a/file", "explanation": "fix"}  # missing fields
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._mock_openai_response(bad_patch)
        )
        with patch("openai.OpenAI", return_value=mock_client):
            from codex.patch import generate_patch
            with self.assertRaises(RuntimeError):
                generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)

    def test_gate2_approve_after_patch_generation(self):
        """Full flow: generate_patch → adapt for gate2 → engineer approves."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._mock_openai_response(MOCK_PATCH)
        )
        with patch("openai.OpenAI", return_value=mock_client):
            from codex.patch import generate_patch
            patch_proposal = generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)

        from main import _adapt_patch_for_gate2
        from gates.gate2_ui import run_gate2
        adapted = _adapt_patch_for_gate2(patch_proposal)

        with patch("builtins.input", side_effect=["@engineer", "approve", "low traffic window"]):
            gate2_result = run_gate2(adapted)

        self.assertEqual(gate2_result["decision"], "approved")
        self.assertEqual(gate2_result["rationale"], "low traffic window")

    def test_gate2_reject_injects_feedback_into_context(self):
        """Engineer rejects patch; feedback is added to org context for next attempt."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._mock_openai_response(MOCK_PATCH)
        )
        with patch("openai.OpenAI", return_value=mock_client):
            from codex.patch import generate_patch
            patch_proposal = generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)

        from main import _adapt_patch_for_gate2
        from gates.gate2_ui import run_gate2
        adapted = _adapt_patch_for_gate2(patch_proposal)

        with patch("builtins.input", side_effect=["@engineer", "reject", "peak hours — try 2am"]):
            gate2_result = run_gate2(adapted)

        self.assertEqual(gate2_result["decision"], "rejected")

        # Verify feedback can be injected into context for next patch attempt
        bundle = dict(SAMPLE_CONTEXT_BUNDLE)
        bundle["org_context"]["injected_context"].append(
            f"[Gate 2 engineer feedback on rejected patch] {gate2_result['rationale']}"
        )
        self.assertIn(
            "[Gate 2 engineer feedback on rejected patch] peak hours — try 2am",
            bundle["org_context"]["injected_context"]
        )


# ── Patch Adapter Tests ───────────────────────────────────────────────────────

class TestPatchAdapter(unittest.TestCase):
    """Test the _adapt_patch_for_gate2 helper in main.py."""

    def test_adapter_wraps_blast_radius_string_into_dict(self):
        from main import _adapt_patch_for_gate2
        patch_proposal = {
            "diff": "--- a/file.py\n+++ b/file.py",
            "explanation": "Fix pool timeout.",
            "blast_radius": "High impact — touches shared postgres and redis.",
            "confidence": 0.87,
            "affected_services": ["auth-service"],
        }
        adapted = _adapt_patch_for_gate2(patch_proposal)
        self.assertIsInstance(adapted["blast_radius"], dict)
        self.assertIn("level", adapted["blast_radius"])
        self.assertIn("services_touched", adapted["blast_radius"])
        self.assertIn("files_touched", adapted["blast_radius"])
        self.assertIn("notes", adapted["blast_radius"])

    def test_adapter_maps_explanation_to_reasoning(self):
        from main import _adapt_patch_for_gate2
        patch_proposal = {
            "diff": "--- a/file.py\n+++ b/file.py",
            "explanation": "This is the explanation.",
            "blast_radius": "minor",
            "confidence": 0.5,
            "affected_services": [],
        }
        adapted = _adapt_patch_for_gate2(patch_proposal)
        self.assertEqual(adapted["reasoning"], "This is the explanation.")

    def test_adapter_high_blast_radius_keyword_sets_level_high(self):
        from main import _adapt_patch_for_gate2
        patch_proposal = {
            "diff": "", "explanation": "", "confidence": 0.5,
            "affected_services": [],
            "blast_radius": "Critical infrastructure component — major risk",
        }
        adapted = _adapt_patch_for_gate2(patch_proposal)
        self.assertEqual(adapted["blast_radius"]["level"], "HIGH")

    def test_adapter_preserves_affected_services(self):
        from main import _adapt_patch_for_gate2
        patch_proposal = {
            "diff": "", "explanation": "", "blast_radius": "minor",
            "confidence": 0.5,
            "affected_services": ["auth-service", "api-gateway"],
        }
        adapted = _adapt_patch_for_gate2(patch_proposal)
        self.assertEqual(adapted["blast_radius"]["services_touched"], ["auth-service", "api-gateway"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
