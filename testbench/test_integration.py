"""
Integration tests for Codex Guardian — Phase 2 updated.

Covers:
  - Full scoring + routing chain
  - diagnose() with mocked OpenAI — including reasoning_chain validation
  - generate_patch() with mocked OpenAI
  - Gate 1 and Gate 2 flows
  - _adapt_patch_for_gate2 adapter
  - context_freshness_warning deterministic override

No real API key required — all OpenAI calls are mocked.
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

EMPTY_GIT_HISTORY = {
    "recent_commits": [],
    "last_reviewed_days_ago": 5,
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


# ── Diagnosis Tests ───────────────────────────────────────────────────────────

class TestDiagnosisIntegration(unittest.TestCase):

    def _mock_openai(self, data):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps(data)
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        return mock_client

    # --- Shape and content ---

    def test_diagnose_returns_hypotheses_from_fixture(self):
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_DIAGNOSIS)):
            from codex.diagnose import diagnose
            result = diagnose(SAMPLE_CONTEXT_BUNDLE)
        self.assertIn("hypotheses", result)
        self.assertEqual(len(result["hypotheses"]), 2)
        self.assertEqual(result["hypotheses"][0]["id"], 1)
        self.assertAlmostEqual(result["hypotheses"][0]["confidence"], 0.85)

    def test_diagnose_returns_freshness_warning_flag(self):
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_DIAGNOSIS)):
            from codex.diagnose import diagnose
            result = diagnose(SAMPLE_CONTEXT_BUNDLE)
        self.assertIn("context_freshness_warning", result)
        self.assertIsInstance(result["context_freshness_warning"], bool)

    # --- reasoning_chain contract (new) ---

    def test_diagnose_returns_reasoning_chain(self):
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_DIAGNOSIS)):
            from codex.diagnose import diagnose
            result = diagnose(SAMPLE_CONTEXT_BUNDLE)
        self.assertIn("reasoning_chain", result)
        self.assertIsInstance(result["reasoning_chain"], list)

    def test_reasoning_chain_has_minimum_steps(self):
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_DIAGNOSIS)):
            from codex.diagnose import diagnose
            result = diagnose(SAMPLE_CONTEXT_BUNDLE)
        self.assertGreaterEqual(len(result["reasoning_chain"]), 2)

    def test_reasoning_chain_steps_have_required_keys(self):
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_DIAGNOSIS)):
            from codex.diagnose import diagnose
            result = diagnose(SAMPLE_CONTEXT_BUNDLE)
        for step in result["reasoning_chain"]:
            for key in ("step", "observation", "inference", "evidence"):
                self.assertIn(key, step, f"reasoning_chain step missing key: '{key}'")

    def test_reasoning_chain_steps_are_numbered_sequentially(self):
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_DIAGNOSIS)):
            from codex.diagnose import diagnose
            result = diagnose(SAMPLE_CONTEXT_BUNDLE)
        steps = [s["step"] for s in result["reasoning_chain"]]
        self.assertEqual(steps, list(range(1, len(steps) + 1)))

    def test_reasoning_chain_evidence_fields_are_strings(self):
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_DIAGNOSIS)):
            from codex.diagnose import diagnose
            result = diagnose(SAMPLE_CONTEXT_BUNDLE)
        for step in result["reasoning_chain"]:
            self.assertIsInstance(step["evidence"], str)
            self.assertGreater(len(step["evidence"]), 0)

    def test_reasoning_chain_fixture_cites_specific_fields(self):
        # Verify the fixture itself uses specific field paths, not generic references
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_DIAGNOSIS)):
            from codex.diagnose import diagnose
            result = diagnose(SAMPLE_CONTEXT_BUNDLE)
        evidence_fields = [s["evidence"] for s in result["reasoning_chain"]]
        # At least one step should reference git_history
        self.assertTrue(any("git_history" in e for e in evidence_fields))
        # At least one step should reference alert or dependencies or org_context
        self.assertTrue(
            any(any(src in e for src in ("alert", "dependencies", "org_context"))
                for e in evidence_fields)
        )

    # --- context_freshness_warning deterministic override ---

    def test_freshness_warning_overridden_true_when_stale(self):
        # Model returns False, but deterministic check should flip it to True
        stale_response = dict(MOCK_DIAGNOSIS, context_freshness_warning=False)
        stale_bundle = dict(
            SAMPLE_CONTEXT_BUNDLE,
            git_history=STALE_GIT_HISTORY,
        )
        with patch("openai.OpenAI", return_value=self._mock_openai(stale_response)):
            from codex.diagnose import diagnose
            result = diagnose(stale_bundle)
        self.assertTrue(result["context_freshness_warning"])

    def test_freshness_warning_true_when_no_commits(self):
        empty_bundle = dict(SAMPLE_CONTEXT_BUNDLE, git_history=EMPTY_GIT_HISTORY)
        response = dict(MOCK_DIAGNOSIS, context_freshness_warning=False)
        with patch("openai.OpenAI", return_value=self._mock_openai(response)):
            from codex.diagnose import diagnose
            result = diagnose(empty_bundle)
        self.assertTrue(result["context_freshness_warning"])

    def test_freshness_warning_false_when_fresh(self):
        response = dict(MOCK_DIAGNOSIS, context_freshness_warning=False)
        with patch("openai.OpenAI", return_value=self._mock_openai(response)):
            from codex.diagnose import diagnose
            result = diagnose(SAMPLE_CONTEXT_BUNDLE)
        self.assertFalse(result["context_freshness_warning"])

    # --- Error handling ---

    def test_diagnose_raises_on_bad_json(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices[0].message.content = (
            "not json at all"
        )
        with patch("openai.OpenAI", return_value=mock_client):
            from codex.diagnose import diagnose
            with self.assertRaises(RuntimeError):
                diagnose(SAMPLE_CONTEXT_BUNDLE)

    def test_diagnose_raises_on_missing_hypotheses_key(self):
        bad = {"context_freshness_warning": False, "reasoning_chain": []}
        with patch("openai.OpenAI", return_value=self._mock_openai(bad)):
            from codex.diagnose import diagnose
            with self.assertRaises(RuntimeError):
                diagnose(SAMPLE_CONTEXT_BUNDLE)

    def test_diagnose_raises_on_missing_reasoning_chain(self):
        bad = {"hypotheses": MOCK_DIAGNOSIS["hypotheses"], "context_freshness_warning": False}
        with patch("openai.OpenAI", return_value=self._mock_openai(bad)):
            from codex.diagnose import diagnose
            with self.assertRaises(RuntimeError):
                diagnose(SAMPLE_CONTEXT_BUNDLE)

    def test_diagnose_raises_when_chain_too_short(self):
        bad = dict(MOCK_DIAGNOSIS, reasoning_chain=[
            {"step": 1, "observation": "x", "inference": "y", "evidence": "alert.error"}
        ])
        with patch("openai.OpenAI", return_value=self._mock_openai(bad)):
            from codex.diagnose import diagnose
            with self.assertRaises(RuntimeError):
                diagnose(SAMPLE_CONTEXT_BUNDLE)

    def test_diagnose_raises_when_chain_step_missing_key(self):
        bad = dict(MOCK_DIAGNOSIS, reasoning_chain=[
            {"step": 1, "observation": "x", "inference": "y"},   # missing 'evidence'
            {"step": 2, "observation": "a", "inference": "b", "evidence": "alert.id"},
        ])
        with patch("openai.OpenAI", return_value=self._mock_openai(bad)):
            from codex.diagnose import diagnose
            with self.assertRaises(RuntimeError):
                diagnose(SAMPLE_CONTEXT_BUNDLE)

    # --- Gate 1 integration ---

    def test_gate1_confirm_after_diagnose(self):
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_DIAGNOSIS)):
            from codex.diagnose import diagnose
            diagnosis_result = diagnose(SAMPLE_CONTEXT_BUNDLE)
        from gates.gate1_ui import run_gate1
        with patch("builtins.input", side_effect=["@engineer", "1"]):
            gate1_result = run_gate1(diagnosis_result)
        self.assertEqual(gate1_result["decision"], "confirmed")
        self.assertEqual(gate1_result["selected_hypothesis_id"], 1)

    def test_gate1_rejection_injects_correction_into_context(self):
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_DIAGNOSIS)):
            from codex.diagnose import diagnose
            diagnosis_result = diagnose(SAMPLE_CONTEXT_BUNDLE)
        from gates.gate1_ui import run_gate1
        with patch("builtins.input", side_effect=["@engineer", "r", "Redis OOM — saw it in logs"]):
            gate1_result = run_gate1(diagnosis_result)
        self.assertEqual(gate1_result["decision"], "rejected")
        bundle = dict(SAMPLE_CONTEXT_BUNDLE)
        bundle["org_context"]["injected_context"].append(
            f"[Gate 1 engineer correction] {gate1_result['correction']}"
        )
        self.assertIn(
            "[Gate 1 engineer correction] Redis OOM — saw it in logs",
            bundle["org_context"]["injected_context"],
        )

    def test_injected_compliance_context_present_in_user_prompt(self):
        # Verify injected_context flows into the prompt string
        bundle = dict(SAMPLE_CONTEXT_BUNDLE)
        bundle["org_context"] = dict(bundle["org_context"])
        bundle["org_context"]["injected_context"] = ["Freeze window active until Friday"]

        captured_prompts = []

        def capture_create(**kwargs):
            captured_prompts.append(kwargs["messages"][1]["content"])
            mock_response = MagicMock()
            mock_response.choices[0].message.content = json.dumps(MOCK_DIAGNOSIS)
            return mock_response

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = capture_create

        with patch("openai.OpenAI", return_value=mock_client):
            from codex.diagnose import diagnose
            diagnose(bundle)

        self.assertTrue(
            any("Freeze window active until Friday" in p for p in captured_prompts),
            "injected_context should appear in the user prompt sent to OpenAI",
        )


# ── Patch Generation + Gate 2 Integration Tests ───────────────────────────────

class TestPatchGate2Integration(unittest.TestCase):

    def _mock_openai(self, data):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps(data)
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        return mock_client

    def _confirmed_hypothesis(self):
        return MOCK_DIAGNOSIS["hypotheses"][0]

    def test_generate_patch_returns_required_fields(self):
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_PATCH)):
            from codex.patch import generate_patch
            result = generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)
        for field in ["diff", "explanation", "blast_radius", "confidence", "affected_services"]:
            self.assertIn(field, result)

    def test_generate_patch_diff_is_string(self):
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_PATCH)):
            from codex.patch import generate_patch
            result = generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)
        self.assertIsInstance(result["diff"], str)
        self.assertGreater(len(result["diff"]), 0)

    def test_generate_patch_affected_services_is_list(self):
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_PATCH)):
            from codex.patch import generate_patch
            result = generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)
        self.assertIsInstance(result["affected_services"], list)

    def test_generate_patch_raises_on_missing_field(self):
        bad_patch = {"diff": "--- a/file", "explanation": "fix"}
        with patch("openai.OpenAI", return_value=self._mock_openai(bad_patch)):
            from codex.patch import generate_patch
            with self.assertRaises(RuntimeError):
                generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)

    def test_gate2_approve_after_patch_generation(self):
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_PATCH)):
            from codex.patch import generate_patch
            patch_proposal = generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)
        from main import _adapt_patch_for_gate2
        from gates.gate2_ui import run_gate2
        adapted = _adapt_patch_for_gate2(patch_proposal)
        with patch("builtins.input", side_effect=["@engineer", "approve", "low traffic window"]):
            gate2_result = run_gate2(adapted)
        self.assertEqual(gate2_result["decision"], "approved")
        self.assertEqual(gate2_result["rationale"], "low traffic window")

    # --- reasoning_chain contract (new) ---

    def test_patch_returns_reasoning_chain(self):
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_PATCH)):
            from codex.patch import generate_patch
            result = generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)
        self.assertIn("reasoning_chain", result)
        self.assertIsInstance(result["reasoning_chain"], list)

    def test_patch_reasoning_chain_minimum_steps(self):
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_PATCH)):
            from codex.patch import generate_patch
            result = generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)
        self.assertGreaterEqual(len(result["reasoning_chain"]), 2)

    def test_patch_reasoning_chain_steps_have_required_keys(self):
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_PATCH)):
            from codex.patch import generate_patch
            result = generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)
        for step in result["reasoning_chain"]:
            for key in ("step", "observation", "decision", "trade_off"):
                self.assertIn(key, step, f"reasoning_chain step missing key: '{key}'")

    def test_patch_reasoning_chain_numbered_sequentially(self):
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_PATCH)):
            from codex.patch import generate_patch
            result = generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)
        steps = [s["step"] for s in result["reasoning_chain"]]
        self.assertEqual(steps, list(range(1, len(steps) + 1)))

    def test_patch_reasoning_chain_trade_off_is_non_empty(self):
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_PATCH)):
            from codex.patch import generate_patch
            result = generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)
        for step in result["reasoning_chain"]:
            self.assertGreater(len(step["trade_off"]), 0,
                "trade_off should never be empty — AI must acknowledge risk")

    # --- compliance_check contract (new) ---

    def test_patch_returns_compliance_check(self):
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_PATCH)):
            from codex.patch import generate_patch
            result = generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)
        self.assertIn("compliance_check", result)

    def test_compliance_check_has_required_keys(self):
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_PATCH)):
            from codex.patch import generate_patch
            result = generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)
        cc = result["compliance_check"]
        for key in ("flags_reviewed", "assessment", "patch_is_compliant"):
            self.assertIn(key, cc, f"compliance_check missing key: '{key}'")

    def test_compliance_check_flags_reviewed_is_list(self):
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_PATCH)):
            from codex.patch import generate_patch
            result = generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)
        self.assertIsInstance(result["compliance_check"]["flags_reviewed"], list)

    def test_compliance_check_patch_is_compliant_is_bool(self):
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_PATCH)):
            from codex.patch import generate_patch
            result = generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)
        self.assertIsInstance(result["compliance_check"]["patch_is_compliant"], bool)

    def test_compliance_check_assessment_is_non_empty_string(self):
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_PATCH)):
            from codex.patch import generate_patch
            result = generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)
        self.assertIsInstance(result["compliance_check"]["assessment"], str)
        self.assertGreater(len(result["compliance_check"]["assessment"]), 0)

    def test_patch_raises_when_reasoning_chain_too_short(self):
        bad = dict(MOCK_PATCH, reasoning_chain=[
            {"step": 1, "observation": "x", "decision": "y", "trade_off": "z"}
        ])
        with patch("openai.OpenAI", return_value=self._mock_openai(bad)):
            from codex.patch import generate_patch
            with self.assertRaises(RuntimeError):
                generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)

    def test_patch_raises_when_chain_step_missing_key(self):
        bad = dict(MOCK_PATCH, reasoning_chain=[
            {"step": 1, "observation": "x", "decision": "y"},  # missing trade_off
            {"step": 2, "observation": "a", "decision": "b", "trade_off": "c"},
        ])
        with patch("openai.OpenAI", return_value=self._mock_openai(bad)):
            from codex.patch import generate_patch
            with self.assertRaises(RuntimeError):
                generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)

    def test_patch_raises_when_compliance_check_missing(self):
        bad = {k: v for k, v in MOCK_PATCH.items() if k != "compliance_check"}
        with patch("openai.OpenAI", return_value=self._mock_openai(bad)):
            from codex.patch import generate_patch
            with self.assertRaises(RuntimeError):
                generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)

    def test_patch_raises_when_compliance_check_key_missing(self):
        bad = dict(MOCK_PATCH)
        bad["compliance_check"] = {"flags_reviewed": [], "assessment": "ok"}  # missing patch_is_compliant
        with patch("openai.OpenAI", return_value=self._mock_openai(bad)):
            from codex.patch import generate_patch
            with self.assertRaises(RuntimeError):
                generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)

    def test_compliance_flags_populated_when_injected_context_present(self):
        # When injected_context has restrictions, fixture should reflect them
        # Here we test a variant fixture where flags are populated
        flagged_patch = dict(MOCK_PATCH)
        flagged_patch["compliance_check"] = {
            "flags_reviewed": ["Freeze window active until Friday", "2-person approval required"],
            "assessment": "Patch is compliant. Freeze window applies to deployments not to config changes. 2-person approval is enforced at Gate 2.",
            "patch_is_compliant": True,
        }
        with patch("openai.OpenAI", return_value=self._mock_openai(flagged_patch)):
            from codex.patch import generate_patch
            result = generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)
        self.assertEqual(len(result["compliance_check"]["flags_reviewed"]), 2)

    def test_injected_feedback_present_in_patch_user_prompt(self):
        bundle = dict(SAMPLE_CONTEXT_BUNDLE)
        bundle["org_context"] = dict(bundle["org_context"])
        bundle["org_context"]["injected_context"] = [
            "[Gate 2 engineer feedback on rejected patch] reduce blast radius — only touch connection.py"
        ]

        captured_prompts = []

        def capture_create(**kwargs):
            captured_prompts.append(kwargs["messages"][1]["content"])
            mock_response = MagicMock()
            mock_response.choices[0].message.content = json.dumps(MOCK_PATCH)
            return mock_response

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = capture_create

        with patch("openai.OpenAI", return_value=mock_client):
            from codex.patch import generate_patch
            generate_patch(self._confirmed_hypothesis(), bundle)

        self.assertTrue(
            any("reduce blast radius" in p for p in captured_prompts),
            "Gate 2 rejection feedback should appear in the patch user prompt",
        )

    def test_gate2_reject_injects_feedback_into_context(self):
        with patch("openai.OpenAI", return_value=self._mock_openai(MOCK_PATCH)):
            from codex.patch import generate_patch
            patch_proposal = generate_patch(self._confirmed_hypothesis(), SAMPLE_CONTEXT_BUNDLE)
        from main import _adapt_patch_for_gate2
        from gates.gate2_ui import run_gate2
        adapted = _adapt_patch_for_gate2(patch_proposal)
        with patch("builtins.input", side_effect=["@engineer", "reject", "peak hours — try 2am"]):
            gate2_result = run_gate2(adapted)
        self.assertEqual(gate2_result["decision"], "rejected")
        bundle = dict(SAMPLE_CONTEXT_BUNDLE)
        bundle["org_context"]["injected_context"].append(
            f"[Gate 2 engineer feedback on rejected patch] {gate2_result['rationale']}"
        )
        self.assertIn(
            "[Gate 2 engineer feedback on rejected patch] peak hours — try 2am",
            bundle["org_context"]["injected_context"],
        )


# ── Patch Adapter Tests ───────────────────────────────────────────────────────

class TestPatchAdapter(unittest.TestCase):

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
        for key in ("level", "services_touched", "files_touched", "notes"):
            self.assertIn(key, adapted["blast_radius"])

    def test_adapter_maps_explanation_to_reasoning(self):
        from main import _adapt_patch_for_gate2
        patch_proposal = {
            "diff": "", "explanation": "This is the explanation.",
            "blast_radius": "minor", "confidence": 0.5, "affected_services": [],
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
            "confidence": 0.5, "affected_services": ["auth-service", "api-gateway"],
        }
        adapted = _adapt_patch_for_gate2(patch_proposal)
        self.assertEqual(
            adapted["blast_radius"]["services_touched"],
            ["auth-service", "api-gateway"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)