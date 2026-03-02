"""
Unit tests for scoring modules: risk_score, freshness_score, router.
No API key required. No external dependencies.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scoring.risk_score import score_risk
from scoring.freshness_score import score_freshness
from scoring.router import route


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_alert(severity="LOW", environment="staging",
               service="reporting-service", error="minor issue"):
    return {
        "severity": severity,
        "environment": environment,
        "service": service,
        "error": error,
        "affected_files": [],
    }


def empty_deps():
    return {"depends_on": [], "depended_on_by": [], "shared_infra": []}


def make_git_history(last_reviewed=3, commit_count=2):
    commits = [
        {"hash": f"abc{i}", "author": "dev", "message": "fix",
         "files_changed": [], "days_ago": i}
        for i in range(commit_count)
    ]
    return {"last_reviewed_days_ago": last_reviewed, "recent_commits": commits}


# ── Risk Score Tests ──────────────────────────────────────────────────────────

class TestRiskScore(unittest.TestCase):

    def test_baseline_low_risk(self):
        result = score_risk(make_alert(), empty_deps())
        self.assertEqual(result["level"], "LOW")

    def test_result_always_has_level_and_reasons(self):
        result = score_risk(make_alert(), empty_deps())
        self.assertIn("level", result)
        self.assertIn("reasons", result)
        self.assertIsInstance(result["reasons"], list)
        self.assertGreater(len(result["reasons"]), 0)

    # Rule 1: severity
    def test_high_severity_triggers_high_risk(self):
        result = score_risk(make_alert(severity="HIGH"), empty_deps())
        self.assertEqual(result["level"], "HIGH")
        self.assertTrue(any("HIGH" in r for r in result["reasons"]))

    def test_critical_severity_triggers_high_risk(self):
        result = score_risk(make_alert(severity="CRITICAL"), empty_deps())
        self.assertEqual(result["level"], "HIGH")

    def test_medium_severity_does_not_trigger_high_risk_alone(self):
        result = score_risk(make_alert(severity="MEDIUM"), empty_deps())
        self.assertEqual(result["level"], "LOW")

    # Rule 2: environment
    def test_production_environment_triggers_high_risk(self):
        result = score_risk(make_alert(environment="production"), empty_deps())
        self.assertEqual(result["level"], "HIGH")
        self.assertTrue(any("production" in r for r in result["reasons"]))

    def test_staging_environment_does_not_trigger_high_risk(self):
        result = score_risk(make_alert(environment="staging"), empty_deps())
        self.assertEqual(result["level"], "LOW")

    # Rule 3: service name keywords
    def test_auth_in_service_name_triggers_high_risk(self):
        result = score_risk(make_alert(service="auth-service"), empty_deps())
        self.assertEqual(result["level"], "HIGH")

    def test_billing_in_service_name_triggers_high_risk(self):
        result = score_risk(make_alert(service="billing-api"), empty_deps())
        self.assertEqual(result["level"], "HIGH")

    def test_neutral_service_name_does_not_trigger(self):
        result = score_risk(make_alert(service="notification-service"), empty_deps())
        self.assertEqual(result["level"], "LOW")

    # Rule 4: error message keywords
    def test_connection_pool_in_error_triggers_high_risk(self):
        result = score_risk(make_alert(error="connection pool exhaustion at p99"), empty_deps())
        self.assertEqual(result["level"], "HIGH")

    def test_credential_in_error_triggers_high_risk(self):
        result = score_risk(make_alert(error="invalid credential detected"), empty_deps())
        self.assertEqual(result["level"], "HIGH")

    def test_generic_error_does_not_trigger(self):
        result = score_risk(make_alert(error="config flag deprecated, fallback active"), empty_deps())
        self.assertEqual(result["level"], "LOW")

    # Rule 5: shared infrastructure
    def test_shared_infra_triggers_high_risk(self):
        deps = {"depends_on": [], "depended_on_by": [], "shared_infra": ["postgres-primary"]}
        result = score_risk(make_alert(), deps)
        self.assertEqual(result["level"], "HIGH")

    def test_empty_shared_infra_does_not_trigger(self):
        deps = {"depends_on": ["config-service"], "depended_on_by": [], "shared_infra": []}
        result = score_risk(make_alert(), deps)
        self.assertEqual(result["level"], "LOW")

    # Rule 6: downstream blast radius
    def test_two_downstream_services_triggers_high_risk(self):
        deps = {"depends_on": [], "depended_on_by": ["api-gateway", "billing-service"], "shared_infra": []}
        result = score_risk(make_alert(), deps)
        self.assertEqual(result["level"], "HIGH")

    def test_one_downstream_service_does_not_trigger(self):
        deps = {"depends_on": [], "depended_on_by": ["api-gateway"], "shared_infra": []}
        result = score_risk(make_alert(), deps)
        self.assertEqual(result["level"], "LOW")

    def test_three_downstream_services_triggers_high_risk(self):
        deps = {"depends_on": [], "depended_on_by": ["a", "b", "c"], "shared_infra": []}
        result = score_risk(make_alert(), deps)
        self.assertEqual(result["level"], "HIGH")

    # Multiple rules
    def test_full_auth_service_alert_is_high_risk(self):
        alert = make_alert(
            severity="HIGH",
            environment="production",
            service="auth-service",
            error="connection pool exhaustion — p99 latency spike to 4200ms"
        )
        deps = {
            "depends_on": ["postgres-primary", "redis-cache"],
            "depended_on_by": ["api-gateway", "billing-service", "admin-dashboard"],
            "shared_infra": ["postgres-primary", "redis-cache"]
        }
        result = score_risk(alert, deps)
        self.assertEqual(result["level"], "HIGH")
        self.assertGreater(len(result["reasons"]), 3)


# ── Freshness Score Tests ─────────────────────────────────────────────────────

class TestFreshnessScore(unittest.TestCase):

    def test_result_has_required_keys(self):
        result = score_freshness(make_git_history())
        self.assertIn("score", result)
        self.assertIn("last_reviewed_days_ago", result)
        self.assertIn("churn_rate", result)

    def test_fresh_recent_review_low_churn(self):
        result = score_freshness(make_git_history(last_reviewed=3, commit_count=1))
        self.assertEqual(result["score"], "FRESH")

    def test_fresh_recent_review_medium_churn(self):
        result = score_freshness(make_git_history(last_reviewed=3, commit_count=3))
        self.assertEqual(result["score"], "FRESH")

    def test_stale_old_review(self):
        result = score_freshness(make_git_history(last_reviewed=15, commit_count=1))
        self.assertEqual(result["score"], "STALE")

    def test_stale_threshold_boundary_above(self):
        # 14 days is the threshold — 15 should be STALE
        result = score_freshness(make_git_history(last_reviewed=15, commit_count=0))
        self.assertEqual(result["score"], "STALE")

    def test_fresh_at_threshold_boundary(self):
        # Exactly 14 days should still be FRESH (> 14, not >= 14)
        result = score_freshness(make_git_history(last_reviewed=14, commit_count=1))
        self.assertEqual(result["score"], "FRESH")

    def test_stale_high_churn_without_recent_review(self):
        # 5+ commits = HIGH churn AND last reviewed > 7 days → STALE
        result = score_freshness(make_git_history(last_reviewed=8, commit_count=5))
        self.assertEqual(result["score"], "STALE")

    def test_fresh_high_churn_with_very_recent_review(self):
        # HIGH churn but reviewed within 7 days → FRESH
        result = score_freshness(make_git_history(last_reviewed=3, commit_count=5))
        self.assertEqual(result["score"], "FRESH")

    def test_churn_rate_low_one_commit(self):
        result = score_freshness(make_git_history(commit_count=1))
        self.assertEqual(result["churn_rate"], "LOW")

    def test_churn_rate_low_zero_commits(self):
        result = score_freshness(make_git_history(commit_count=0))
        self.assertEqual(result["churn_rate"], "LOW")

    def test_churn_rate_medium(self):
        result = score_freshness(make_git_history(commit_count=3))
        self.assertEqual(result["churn_rate"], "MEDIUM")

    def test_churn_rate_high(self):
        result = score_freshness(make_git_history(commit_count=5))
        self.assertEqual(result["churn_rate"], "HIGH")

    def test_churn_rate_high_many_commits(self):
        result = score_freshness(make_git_history(commit_count=10))
        self.assertEqual(result["churn_rate"], "HIGH")

    def test_last_reviewed_days_preserved_in_output(self):
        result = score_freshness(make_git_history(last_reviewed=7))
        self.assertEqual(result["last_reviewed_days_ago"], 7)


# ── Router Tests ──────────────────────────────────────────────────────────────

class TestRouter(unittest.TestCase):

    def _risk(self, level):
        return {"level": level, "reasons": [f"test reason for {level}"]}

    def _freshness(self, score, days=3):
        return {"score": score, "last_reviewed_days_ago": days, "churn_rate": "LOW"}

    def test_low_risk_fresh_routes_to_auto_handle(self):
        result = route(self._risk("LOW"), self._freshness("FRESH"))
        self.assertEqual(result["route"], "auto-handle")

    def test_high_risk_fresh_routes_to_escalate(self):
        result = route(self._risk("HIGH"), self._freshness("FRESH"))
        self.assertEqual(result["route"], "escalate")

    def test_low_risk_stale_routes_to_escalate(self):
        result = route(self._risk("LOW"), self._freshness("STALE", days=20))
        self.assertEqual(result["route"], "escalate")

    def test_high_risk_stale_routes_to_escalate(self):
        result = route(self._risk("HIGH"), self._freshness("STALE", days=20))
        self.assertEqual(result["route"], "escalate")

    def test_result_contains_risk_level(self):
        result = route(self._risk("HIGH"), self._freshness("FRESH"))
        self.assertEqual(result["risk_level"], "HIGH")

    def test_result_contains_freshness(self):
        result = route(self._risk("LOW"), self._freshness("STALE"))
        self.assertEqual(result["freshness"], "STALE")

    def test_result_contains_explanation_string(self):
        result = route(self._risk("HIGH"), self._freshness("STALE"))
        self.assertIn("explanation", result)
        self.assertIsInstance(result["explanation"], str)
        self.assertGreater(len(result["explanation"]), 0)

    def test_escalate_explanation_mentions_risk(self):
        result = route(self._risk("HIGH"), self._freshness("FRESH"))
        self.assertIn("HIGH", result["explanation"].upper())

    def test_escalate_explanation_mentions_stale(self):
        result = route(self._risk("LOW"), self._freshness("STALE", days=20))
        self.assertIn("STALE", result["explanation"].upper())

    def test_auto_handle_explanation_mentions_low_and_fresh(self):
        result = route(self._risk("LOW"), self._freshness("FRESH"))
        self.assertIn("LOW", result["explanation"].upper())
        self.assertIn("FRESH", result["explanation"].upper())


if __name__ == "__main__":
    unittest.main(verbosity=2)
