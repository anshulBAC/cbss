"""
Unit tests for gates/gate0_compliance.py.

Tests every policy rule independently, hard-block behaviour, restriction
injection, second-approver flag, and the policy_reasoning audit chain.

No API key required. policies.yaml is loaded from the real file; a helper
also builds minimal in-memory policy dicts for isolated rule tests.
"""

import sys
import os
import unittest
import tempfile
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gates.gate0_compliance import run_gate0


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _write_temp_policy(rules, freeze_active=False, freeze_reason="Test freeze"):
    """Write a minimal policies.yaml to a temp file and return the path."""
    data = {
        "freeze_window": {
            "active": freeze_active,
            "reason": freeze_reason,
        },
        "rules": rules,
    }
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    )
    yaml.dump(data, tmp)
    tmp.close()
    return tmp.name


def _alert(**overrides):
    base = {
        "id": "alert-test",
        "service": "notification-service",
        "severity": "LOW",
        "environment": "staging",
        "error": "minor issue",
        "affected_files": ["src/config/flags.py"],
    }
    base.update(overrides)
    return base


def _route(level="LOW", freshness="FRESH"):
    return {"route": "escalate", "risk_level": level, "freshness": freshness,
            "explanation": "test"}


def _bundle(shared_infra=None):
    return {
        "alert": _alert(),
        "dependencies": {
            "depends_on": [],
            "depended_on_by": [],
            "shared_infra": shared_infra or [],
        },
        "git_history": {"recent_commits": [], "last_reviewed_days_ago": 3},
        "org_context": {"team_notes": [], "known_constraints": [], "injected_context": []},
    }


# ─────────────────────────────────────────────────────────────
# RESULT SHAPE
# ─────────────────────────────────────────────────────────────

class TestComplianceResultShape(unittest.TestCase):

    def test_result_has_required_keys(self):
        path = _write_temp_policy([])
        result = run_gate0(_alert(), _route(), _bundle(), policies_path=path)
        for key in ["proceed", "flags", "restrictions",
                    "requires_second_approver", "policy_reasoning"]:
            self.assertIn(key, result)

    def test_proceed_is_bool(self):
        path = _write_temp_policy([])
        result = run_gate0(_alert(), _route(), _bundle(), policies_path=path)
        self.assertIsInstance(result["proceed"], bool)

    def test_flags_is_list(self):
        path = _write_temp_policy([])
        result = run_gate0(_alert(), _route(), _bundle(), policies_path=path)
        self.assertIsInstance(result["flags"], list)

    def test_restrictions_is_list(self):
        path = _write_temp_policy([])
        result = run_gate0(_alert(), _route(), _bundle(), policies_path=path)
        self.assertIsInstance(result["restrictions"], list)

    def test_policy_reasoning_is_list(self):
        path = _write_temp_policy([])
        result = run_gate0(_alert(), _route(), _bundle(), policies_path=path)
        self.assertIsInstance(result["policy_reasoning"], list)

    def test_empty_rules_proceeds(self):
        path = _write_temp_policy([])
        result = run_gate0(_alert(), _route(), _bundle(), policies_path=path)
        self.assertTrue(result["proceed"])
        self.assertEqual(result["flags"], [])

    def test_policy_reasoning_entry_has_required_keys(self):
        rule = {
            "id": "POL-T01", "rule": "Test rule",
            "condition": {"type": "severity_match", "severities": ["HIGH"]},
            "restriction": "test restriction",
            "hard_block": False, "requires_second_approver": False,
        }
        path = _write_temp_policy([rule])
        result = run_gate0(_alert(), _route(), _bundle(), policies_path=path)
        entry = result["policy_reasoning"][0]
        for key in ["rule_id", "rule", "triggered", "reason", "restriction_injected"]:
            self.assertIn(key, entry)

    def test_all_rules_appear_in_policy_reasoning_even_if_not_triggered(self):
        rules = [
            {"id": "R1", "rule": "r1", "condition": {"type": "severity_match",
             "severities": ["CRITICAL"]}, "restriction": "r", "hard_block": False,
             "requires_second_approver": False},
            {"id": "R2", "rule": "r2", "condition": {"type": "severity_match",
             "severities": ["HIGH"]}, "restriction": "r", "hard_block": False,
             "requires_second_approver": False},
        ]
        path = _write_temp_policy(rules)
        result = run_gate0(_alert(severity="LOW"), _route(), _bundle(), policies_path=path)
        self.assertEqual(len(result["policy_reasoning"]), 2)


# ─────────────────────────────────────────────────────────────
# POL-001 — service_name_match
# ─────────────────────────────────────────────────────────────

class TestServiceNameMatch(unittest.TestCase):

    def _rule(self, services, hard_block=False, requires_second=True):
        return {
            "id": "POL-001",
            "rule": "High-trust service requires 2-person approval",
            "condition": {"type": "service_name_match", "services": services},
            "restriction": "2-person approval required",
            "hard_block": hard_block,
            "requires_second_approver": requires_second,
        }

    def test_triggers_for_auth_service(self):
        path = _write_temp_policy([self._rule(["auth-service"])])
        result = run_gate0(_alert(service="auth-service"), _route(), _bundle(), policies_path=path)
        self.assertTrue(result["policy_reasoning"][0]["triggered"])
        self.assertIn("POL-001", result["flags"][0])

    def test_does_not_trigger_for_other_service(self):
        path = _write_temp_policy([self._rule(["auth-service"])])
        result = run_gate0(_alert(service="notification-service"), _route(), _bundle(), policies_path=path)
        self.assertFalse(result["policy_reasoning"][0]["triggered"])
        self.assertEqual(result["flags"], [])

    def test_sets_requires_second_approver(self):
        path = _write_temp_policy([self._rule(["auth-service"], requires_second=True)])
        result = run_gate0(_alert(service="auth-service"), _route(), _bundle(), policies_path=path)
        self.assertTrue(result["requires_second_approver"])

    def test_does_not_set_requires_second_approver_if_not_triggered(self):
        path = _write_temp_policy([self._rule(["auth-service"], requires_second=True)])
        result = run_gate0(_alert(service="other-service"), _route(), _bundle(), policies_path=path)
        self.assertFalse(result["requires_second_approver"])

    def test_soft_block_does_not_set_proceed_false(self):
        path = _write_temp_policy([self._rule(["auth-service"], hard_block=False)])
        result = run_gate0(_alert(service="auth-service"), _route(), _bundle(), policies_path=path)
        self.assertTrue(result["proceed"])

    def test_hard_block_sets_proceed_false(self):
        path = _write_temp_policy([self._rule(["auth-service"], hard_block=True)])
        result = run_gate0(_alert(service="auth-service"), _route(), _bundle(), policies_path=path)
        self.assertFalse(result["proceed"])

    def test_restriction_injected_when_triggered(self):
        path = _write_temp_policy([self._rule(["auth-service"])])
        result = run_gate0(_alert(service="auth-service"), _route(), _bundle(), policies_path=path)
        self.assertEqual(len(result["restrictions"]), 1)
        self.assertIn("2-person", result["restrictions"][0])

    def test_restriction_empty_when_not_triggered(self):
        path = _write_temp_policy([self._rule(["auth-service"])])
        result = run_gate0(_alert(service="other"), _route(), _bundle(), policies_path=path)
        self.assertEqual(result["restrictions"], [])

    def test_multiple_services_in_list(self):
        path = _write_temp_policy([self._rule(["auth-service", "payments-service"])])
        result_auth = run_gate0(_alert(service="auth-service"), _route(), _bundle(), policies_path=path)
        result_pay = run_gate0(_alert(service="payments-service"), _route(), _bundle(), policies_path=path)
        self.assertTrue(result_auth["policy_reasoning"][0]["triggered"])
        self.assertTrue(result_pay["policy_reasoning"][0]["triggered"])


# ─────────────────────────────────────────────────────────────
# POL-002 — freeze_window_active
# ─────────────────────────────────────────────────────────────

class TestFreezeWindowActive(unittest.TestCase):

    def _rule(self, hard_block=True):
        return {
            "id": "POL-002",
            "rule": "Production deploys blocked during freeze",
            "condition": {"type": "freeze_window_active", "environment": "production"},
            "restriction": "Freeze window is active",
            "hard_block": hard_block,
            "requires_second_approver": False,
        }

    def test_triggers_when_freeze_active_and_production(self):
        path = _write_temp_policy([self._rule()], freeze_active=True)
        result = run_gate0(_alert(environment="production"), _route(), _bundle(), policies_path=path)
        self.assertTrue(result["policy_reasoning"][0]["triggered"])

    def test_does_not_trigger_when_freeze_inactive(self):
        path = _write_temp_policy([self._rule()], freeze_active=False)
        result = run_gate0(_alert(environment="production"), _route(), _bundle(), policies_path=path)
        self.assertFalse(result["policy_reasoning"][0]["triggered"])

    def test_does_not_trigger_when_not_production(self):
        path = _write_temp_policy([self._rule()], freeze_active=True)
        result = run_gate0(_alert(environment="staging"), _route(), _bundle(), policies_path=path)
        self.assertFalse(result["policy_reasoning"][0]["triggered"])

    def test_hard_blocks_when_freeze_active_and_production(self):
        path = _write_temp_policy([self._rule(hard_block=True)], freeze_active=True)
        result = run_gate0(_alert(environment="production"), _route(), _bundle(), policies_path=path)
        self.assertFalse(result["proceed"])

    def test_no_hard_block_when_freeze_inactive(self):
        path = _write_temp_policy([self._rule(hard_block=True)], freeze_active=False)
        result = run_gate0(_alert(environment="production"), _route(), _bundle(), policies_path=path)
        self.assertTrue(result["proceed"])


# ─────────────────────────────────────────────────────────────
# POL-003 — file_pattern_match
# ─────────────────────────────────────────────────────────────

class TestFilePatternMatch(unittest.TestCase):

    def _rule(self):
        return {
            "id": "POL-003",
            "rule": "DB connection config changes require DBA sign-off",
            "condition": {"type": "file_pattern_match", "patterns": ["connection.py", "db/"]},
            "restriction": "DBA sign-off required",
            "hard_block": False,
            "requires_second_approver": False,
        }

    def test_triggers_for_connection_py(self):
        path = _write_temp_policy([self._rule()])
        result = run_gate0(
            _alert(affected_files=["src/db/connection.py"]), _route(), _bundle(), policies_path=path
        )
        self.assertTrue(result["policy_reasoning"][0]["triggered"])

    def test_triggers_for_db_path(self):
        path = _write_temp_policy([self._rule()])
        result = run_gate0(
            _alert(affected_files=["src/db/models.py"]), _route(), _bundle(), policies_path=path
        )
        self.assertTrue(result["policy_reasoning"][0]["triggered"])

    def test_does_not_trigger_for_unrelated_file(self):
        path = _write_temp_policy([self._rule()])
        result = run_gate0(
            _alert(affected_files=["src/config/flags.py"]), _route(), _bundle(), policies_path=path
        )
        self.assertFalse(result["policy_reasoning"][0]["triggered"])

    def test_does_not_trigger_for_empty_affected_files(self):
        path = _write_temp_policy([self._rule()])
        result = run_gate0(
            _alert(affected_files=[]), _route(), _bundle(), policies_path=path
        )
        self.assertFalse(result["policy_reasoning"][0]["triggered"])

    def test_multiple_files_only_one_needs_to_match(self):
        path = _write_temp_policy([self._rule()])
        result = run_gate0(
            _alert(affected_files=["src/auth/session.py", "src/db/connection.py"]),
            _route(), _bundle(), policies_path=path,
        )
        self.assertTrue(result["policy_reasoning"][0]["triggered"])


# ─────────────────────────────────────────────────────────────
# POL-004 — shared_infra_present
# ─────────────────────────────────────────────────────────────

class TestSharedInfraPresent(unittest.TestCase):

    def _rule(self):
        return {
            "id": "POL-004",
            "rule": "Patches touching shared infra require blast radius review",
            "condition": {"type": "shared_infra_present"},
            "restriction": "Shared infra blast radius review required",
            "hard_block": False,
            "requires_second_approver": False,
        }

    def test_triggers_when_shared_infra_present(self):
        path = _write_temp_policy([self._rule()])
        bundle = _bundle(shared_infra=["postgres-primary", "redis-cache"])
        result = run_gate0(_alert(), _route(), bundle, policies_path=path)
        self.assertTrue(result["policy_reasoning"][0]["triggered"])

    def test_does_not_trigger_when_shared_infra_empty(self):
        path = _write_temp_policy([self._rule()])
        result = run_gate0(_alert(), _route(), _bundle(shared_infra=[]), policies_path=path)
        self.assertFalse(result["policy_reasoning"][0]["triggered"])

    def test_restriction_mentions_infra_names(self):
        path = _write_temp_policy([self._rule()])
        bundle = _bundle(shared_infra=["postgres-primary"])
        result = run_gate0(_alert(), _route(), bundle, policies_path=path)
        self.assertIn("postgres-primary", result["policy_reasoning"][0]["reason"])


# ─────────────────────────────────────────────────────────────
# POL-005 — severity_match
# ─────────────────────────────────────────────────────────────

class TestSeverityMatch(unittest.TestCase):

    def _rule(self, severities, hard_block=True):
        return {
            "id": "POL-005",
            "rule": "CRITICAL alerts are hard-blocked",
            "condition": {"type": "severity_match", "severities": severities},
            "restriction": "CRITICAL alert — manual escalation required",
            "hard_block": hard_block,
            "requires_second_approver": False,
        }

    def test_triggers_for_critical(self):
        path = _write_temp_policy([self._rule(["CRITICAL"])])
        result = run_gate0(_alert(severity="CRITICAL"), _route(), _bundle(), policies_path=path)
        self.assertTrue(result["policy_reasoning"][0]["triggered"])

    def test_does_not_trigger_for_high(self):
        path = _write_temp_policy([self._rule(["CRITICAL"])])
        result = run_gate0(_alert(severity="HIGH"), _route(), _bundle(), policies_path=path)
        self.assertFalse(result["policy_reasoning"][0]["triggered"])

    def test_hard_blocks_on_critical(self):
        path = _write_temp_policy([self._rule(["CRITICAL"], hard_block=True)])
        result = run_gate0(_alert(severity="CRITICAL"), _route(), _bundle(), policies_path=path)
        self.assertFalse(result["proceed"])
        self.assertEqual(len(result["flags"]), 1)

    def test_case_insensitive_severity_matching(self):
        path = _write_temp_policy([self._rule(["critical"])])
        result = run_gate0(_alert(severity="CRITICAL"), _route(), _bundle(), policies_path=path)
        self.assertTrue(result["policy_reasoning"][0]["triggered"])


# ─────────────────────────────────────────────────────────────
# MULTI-RULE SCENARIOS
# ─────────────────────────────────────────────────────────────

class TestMultiRuleScenarios(unittest.TestCase):

    def test_multiple_flags_collected_when_multiple_rules_triggered(self):
        rules = [
            {
                "id": "R1", "rule": "auth rule",
                "condition": {"type": "service_name_match", "services": ["auth-service"]},
                "restriction": "auth restriction", "hard_block": False,
                "requires_second_approver": False,
            },
            {
                "id": "R2", "rule": "file rule",
                "condition": {"type": "file_pattern_match", "patterns": ["connection.py"]},
                "restriction": "file restriction", "hard_block": False,
                "requires_second_approver": False,
            },
        ]
        path = _write_temp_policy(rules)
        result = run_gate0(
            _alert(service="auth-service", affected_files=["src/db/connection.py"]),
            _route(), _bundle(), policies_path=path,
        )
        self.assertEqual(len(result["flags"]), 2)
        self.assertEqual(len(result["restrictions"]), 2)
        self.assertTrue(result["proceed"])  # no hard blocks

    def test_one_hard_block_fails_whole_pipeline_even_with_soft_flags(self):
        rules = [
            {
                "id": "SOFT", "rule": "soft rule",
                "condition": {"type": "service_name_match", "services": ["auth-service"]},
                "restriction": "soft restriction", "hard_block": False,
                "requires_second_approver": False,
            },
            {
                "id": "HARD", "rule": "hard rule",
                "condition": {"type": "severity_match", "severities": ["HIGH"]},
                "restriction": "hard restriction", "hard_block": True,
                "requires_second_approver": False,
            },
        ]
        path = _write_temp_policy(rules)
        result = run_gate0(
            _alert(service="auth-service", severity="HIGH"), _route(), _bundle(), policies_path=path
        )
        self.assertFalse(result["proceed"])
        self.assertEqual(len(result["flags"]), 2)

    def test_requires_second_approver_false_when_no_rule_sets_it(self):
        rules = [
            {
                "id": "R1", "rule": "no-second rule",
                "condition": {"type": "severity_match", "severities": ["LOW"]},
                "restriction": "r", "hard_block": False,
                "requires_second_approver": False,
            },
        ]
        path = _write_temp_policy(rules)
        result = run_gate0(_alert(severity="LOW"), _route(), _bundle(), policies_path=path)
        self.assertFalse(result["requires_second_approver"])

    def test_requires_second_approver_true_when_any_triggered_rule_sets_it(self):
        rules = [
            {
                "id": "R1", "rule": "second required",
                "condition": {"type": "service_name_match", "services": ["auth-service"]},
                "restriction": "r", "hard_block": False,
                "requires_second_approver": True,
            },
            {
                "id": "R2", "rule": "second not required",
                "condition": {"type": "severity_match", "severities": ["LOW"]},
                "restriction": "r", "hard_block": False,
                "requires_second_approver": False,
            },
        ]
        path = _write_temp_policy(rules)
        result = run_gate0(_alert(service="auth-service", severity="LOW"), _route(), _bundle(), policies_path=path)
        self.assertTrue(result["requires_second_approver"])

    def test_restriction_injected_field_empty_when_rule_not_triggered(self):
        rules = [
            {
                "id": "R1", "rule": "not triggered",
                "condition": {"type": "severity_match", "severities": ["CRITICAL"]},
                "restriction": "critical restriction", "hard_block": False,
                "requires_second_approver": False,
            },
        ]
        path = _write_temp_policy(rules)
        result = run_gate0(_alert(severity="LOW"), _route(), _bundle(), policies_path=path)
        self.assertEqual(result["policy_reasoning"][0]["restriction_injected"], "")

    def test_restriction_injected_field_populated_when_rule_triggered(self):
        rules = [
            {
                "id": "R1", "rule": "triggered",
                "condition": {"type": "severity_match", "severities": ["HIGH"]},
                "restriction": "high severity restriction", "hard_block": False,
                "requires_second_approver": False,
            },
        ]
        path = _write_temp_policy(rules)
        result = run_gate0(_alert(severity="HIGH"), _route(), _bundle(), policies_path=path)
        self.assertIn("high severity restriction", result["policy_reasoning"][0]["restriction_injected"])

    def test_policy_reasoning_length_matches_rule_count(self):
        rules = [
            {"id": f"R{i}", "rule": f"rule {i}",
             "condition": {"type": "severity_match", "severities": ["CRITICAL"]},
             "restriction": "r", "hard_block": False, "requires_second_approver": False}
            for i in range(5)
        ]
        path = _write_temp_policy(rules)
        result = run_gate0(_alert(), _route(), _bundle(), policies_path=path)
        self.assertEqual(len(result["policy_reasoning"]), 5)


# ─────────────────────────────────────────────────────────────
# REAL POLICIES.YAML — INTEGRATION CHECK
# ─────────────────────────────────────────────────────────────

class TestRealPoliciesYaml(unittest.TestCase):
    """Smoke tests against the real policies.yaml to catch YAML syntax issues."""

    REAL_PATH = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "policies.yaml"
    )

    def test_real_yaml_loads_without_error(self):
        """policies.yaml must be valid YAML that gate0 can parse."""
        result = run_gate0(
            _alert(service="notification-service", severity="LOW",
                   environment="staging", affected_files=["src/config/flags.py"]),
            _route(), _bundle(), policies_path=self.REAL_PATH,
        )
        self.assertIn("proceed", result)

    def test_low_risk_staging_no_hard_block(self):
        """Low-risk staging alert should pass all rules cleanly."""
        result = run_gate0(
            _alert(service="notification-service", severity="LOW",
                   environment="staging", affected_files=["src/config/flags.py"]),
            _route(), _bundle(shared_infra=[]),
            policies_path=self.REAL_PATH,
        )
        self.assertTrue(result["proceed"])

    def test_auth_service_triggers_pol001_and_second_approver(self):
        """auth-service alert should trigger POL-001 and require second approver."""
        result = run_gate0(
            _alert(service="auth-service", environment="production",
                   severity="HIGH", affected_files=["src/db/connection.py"]),
            _route(level="HIGH"),
            _bundle(shared_infra=["postgres-primary", "redis-cache"]),
            policies_path=self.REAL_PATH,
        )
        self.assertTrue(result["requires_second_approver"])
        ids = [r["rule_id"] for r in result["policy_reasoning"] if r["triggered"]]
        self.assertIn("POL-001", ids)

    def test_critical_severity_hard_blocks(self):
        """CRITICAL alert should set proceed=False via POL-005."""
        result = run_gate0(
            _alert(severity="CRITICAL"),
            _route(), _bundle(), policies_path=self.REAL_PATH,
        )
        self.assertFalse(result["proceed"])

    def test_connection_py_triggers_pol003(self):
        """connection.py in affected_files should trigger POL-003."""
        result = run_gate0(
            _alert(affected_files=["src/db/connection.py"]),
            _route(), _bundle(), policies_path=self.REAL_PATH,
        )
        ids = [r["rule_id"] for r in result["policy_reasoning"] if r["triggered"]]
        self.assertIn("POL-003", ids)

    def test_shared_infra_triggers_pol004(self):
        """Non-empty shared_infra should trigger POL-004."""
        result = run_gate0(
            _alert(), _route(),
            _bundle(shared_infra=["postgres-primary"]),
            policies_path=self.REAL_PATH,
        )
        ids = [r["rule_id"] for r in result["policy_reasoning"] if r["triggered"]]
        self.assertIn("POL-004", ids)

    def test_freeze_off_by_default(self):
        """With freeze_window.active=false, production alerts should not be hard-blocked by POL-002."""
        result = run_gate0(
            _alert(environment="production", service="reporting-service",
                   severity="MEDIUM", affected_files=["src/reports/generator.py"]),
            _route(), _bundle(), policies_path=self.REAL_PATH,
        )
        ids_hard_blocked = [
            r["rule_id"] for r in result["policy_reasoning"]
            if r["triggered"] and "POL-002" == r["rule_id"]
        ]
        self.assertEqual(ids_hard_blocked, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)