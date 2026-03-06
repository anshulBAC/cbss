"""
Unit tests for context modules: git_history, dependency_graph, org_context, bundle.
Updated for Phase 1 — stubs are now alert-aware and parameterised by service/files.
No API key required. No external dependencies.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from context.git_history import get_git_history
from context.dependency_graph import get_dependency_graph
from context.org_context import get_org_context
from context.bundle import build_context_bundle


# ── Git History Tests ─────────────────────────────────────────────────────────

class TestGitHistory(unittest.TestCase):

    # --- Shape contract (must always hold) ---

    def test_returns_dict(self):
        result = get_git_history(["src/db/connection.py"])
        self.assertIsInstance(result, dict)

    def test_has_recent_commits_key(self):
        result = get_git_history(["src/db/connection.py"])
        self.assertIn("recent_commits", result)
        self.assertIsInstance(result["recent_commits"], list)

    def test_has_last_reviewed_days_ago(self):
        result = get_git_history([])
        self.assertIn("last_reviewed_days_ago", result)
        self.assertIsInstance(result["last_reviewed_days_ago"], int)

    def test_last_reviewed_is_non_negative(self):
        result = get_git_history([])
        self.assertGreaterEqual(result["last_reviewed_days_ago"], 0)

    def test_commits_have_required_fields(self):
        result = get_git_history(["src/db/connection.py"])
        for commit in result["recent_commits"]:
            self.assertIn("hash", commit)
            self.assertIn("author", commit)
            self.assertIn("message", commit)
            self.assertIn("days_ago", commit)
            self.assertIn("files_changed", commit)

    def test_commit_days_ago_is_numeric(self):
        result = get_git_history(["src/db/connection.py"])
        for commit in result["recent_commits"]:
            self.assertIsInstance(commit["days_ago"], (int, float))

    def test_commit_files_changed_is_list(self):
        result = get_git_history(["src/db/connection.py"])
        for commit in result["recent_commits"]:
            self.assertIsInstance(commit["files_changed"], list)

    # --- Alert-awareness (new behaviour) ---

    def test_connection_file_returns_relevant_commits(self):
        result = get_git_history(["src/db/connection.py"])
        self.assertGreater(len(result["recent_commits"]), 0)
        # All returned commits should reference the affected file
        for commit in result["recent_commits"]:
            self.assertIn("src/db/connection.py", commit["files_changed"])

    def test_session_file_returns_relevant_commits(self):
        result = get_git_history(["src/auth/session.py"])
        self.assertGreater(len(result["recent_commits"]), 0)
        for commit in result["recent_commits"]:
            self.assertIn("src/auth/session.py", commit["files_changed"])

    def test_multiple_files_returns_commits_for_each(self):
        result = get_git_history(["src/db/connection.py", "src/auth/session.py"])
        files_touched = [
            f for commit in result["recent_commits"]
            for f in commit["files_changed"]
        ]
        self.assertIn("src/db/connection.py", files_touched)
        self.assertIn("src/auth/session.py", files_touched)

    def test_unknown_file_returns_empty_commits(self):
        result = get_git_history(["src/unknown/random.py"])
        self.assertEqual(result["recent_commits"], [])

    def test_empty_file_list_returns_empty_commits(self):
        result = get_git_history([])
        self.assertEqual(result["recent_commits"], [])

    def test_commits_sorted_most_recent_first(self):
        result = get_git_history(["src/db/connection.py"])
        days = [c["days_ago"] for c in result["recent_commits"]]
        self.assertEqual(days, sorted(days))

    def test_no_duplicate_commits_for_overlapping_files(self):
        result = get_git_history(["src/db/connection.py", "src/db/connection.py"])
        hashes = [c["hash"] for c in result["recent_commits"]]
        self.assertEqual(len(hashes), len(set(hashes)))

    # --- Service-aware review recency ---

    def test_auth_service_review_recency(self):
        result = get_git_history([], service="auth-service")
        self.assertEqual(result["last_reviewed_days_ago"], 3)

    def test_reporting_service_review_recency(self):
        result = get_git_history([], service="reporting-service")
        self.assertEqual(result["last_reviewed_days_ago"], 18)

    def test_notification_service_review_recency(self):
        result = get_git_history([], service="notification-service")
        self.assertEqual(result["last_reviewed_days_ago"], 7)

    def test_unknown_service_returns_default_recency(self):
        result = get_git_history([], service="unknown-service")
        self.assertIsInstance(result["last_reviewed_days_ago"], int)
        self.assertGreaterEqual(result["last_reviewed_days_ago"], 0)

    def test_no_service_arg_returns_default_recency(self):
        result = get_git_history([])
        self.assertIsInstance(result["last_reviewed_days_ago"], int)


# ── Dependency Graph Tests ────────────────────────────────────────────────────

class TestDependencyGraph(unittest.TestCase):

    # --- Shape contract ---

    def test_returns_dict(self):
        result = get_dependency_graph("auth-service")
        self.assertIsInstance(result, dict)

    def test_has_service_key(self):
        result = get_dependency_graph("auth-service")
        self.assertIn("service", result)

    def test_has_depends_on(self):
        result = get_dependency_graph("auth-service")
        self.assertIn("depends_on", result)
        self.assertIsInstance(result["depends_on"], list)

    def test_has_depended_on_by(self):
        result = get_dependency_graph("auth-service")
        self.assertIn("depended_on_by", result)
        self.assertIsInstance(result["depended_on_by"], list)

    def test_has_shared_infra(self):
        result = get_dependency_graph("auth-service")
        self.assertIn("shared_infra", result)
        self.assertIsInstance(result["shared_infra"], list)

    def test_all_values_are_strings(self):
        result = get_dependency_graph("auth-service")
        for key in ["depends_on", "depended_on_by", "shared_infra"]:
            for item in result[key]:
                self.assertIsInstance(item, str)

    # --- Alert-awareness (new behaviour) ---

    def test_auth_service_has_correct_dependencies(self):
        result = get_dependency_graph("auth-service")
        self.assertIn("postgres-primary", result["depends_on"])
        self.assertIn("redis-cache", result["depends_on"])
        self.assertIn("user-service", result["depends_on"])

    def test_auth_service_has_correct_dependents(self):
        result = get_dependency_graph("auth-service")
        self.assertIn("api-gateway", result["depended_on_by"])
        self.assertIn("billing-service", result["depended_on_by"])

    def test_auth_service_has_shared_infra(self):
        result = get_dependency_graph("auth-service")
        self.assertIn("postgres-primary", result["shared_infra"])
        self.assertIn("redis-cache", result["shared_infra"])

    def test_reporting_service_has_correct_dependencies(self):
        result = get_dependency_graph("reporting-service")
        self.assertIn("postgres-replica", result["depends_on"])
        self.assertIn("data-warehouse", result["depends_on"])

    def test_notification_service_has_no_dependents(self):
        result = get_dependency_graph("notification-service")
        self.assertEqual(result["depended_on_by"], [])

    def test_notification_service_has_no_shared_infra(self):
        result = get_dependency_graph("notification-service")
        self.assertEqual(result["shared_infra"], [])

    def test_unknown_service_returns_empty_graph(self):
        result = get_dependency_graph("unknown-service")
        self.assertEqual(result["depends_on"], [])
        self.assertEqual(result["depended_on_by"], [])
        self.assertEqual(result["shared_infra"], [])

    def test_service_key_matches_input(self):
        result = get_dependency_graph("reporting-service")
        self.assertEqual(result["service"], "reporting-service")

    def test_mutation_does_not_affect_registry(self):
        # Modifying the returned list should not corrupt future calls
        result1 = get_dependency_graph("auth-service")
        result1["depends_on"].append("injected-service")
        result2 = get_dependency_graph("auth-service")
        self.assertNotIn("injected-service", result2["depends_on"])


# ── Org Context Tests ─────────────────────────────────────────────────────────

class TestOrgContext(unittest.TestCase):

    def test_returns_dict(self):
        result = get_org_context()
        self.assertIsInstance(result, dict)

    def test_has_team_notes(self):
        result = get_org_context()
        self.assertIn("team_notes", result)
        self.assertIsInstance(result["team_notes"], list)

    def test_has_known_constraints(self):
        result = get_org_context()
        self.assertIn("known_constraints", result)
        self.assertIsInstance(result["known_constraints"], list)

    def test_has_injected_context(self):
        result = get_org_context()
        self.assertIn("injected_context", result)
        self.assertIsInstance(result["injected_context"], list)

    def test_team_notes_are_strings(self):
        result = get_org_context()
        for note in result["team_notes"]:
            self.assertIsInstance(note, str)

    def test_known_constraints_are_strings(self):
        result = get_org_context()
        for constraint in result["known_constraints"]:
            self.assertIsInstance(constraint, str)

    def test_injected_context_starts_empty(self):
        result = get_org_context()
        self.assertEqual(result["injected_context"], [])

    def test_injected_context_is_mutable(self):
        result = get_org_context()
        result["injected_context"].append("Gate 1 engineer correction: Redis OOM is the cause")
        self.assertIn("Gate 1 engineer correction: Redis OOM is the cause", result["injected_context"])

    def test_injected_context_can_hold_multiple_entries(self):
        result = get_org_context()
        result["injected_context"].append("correction 1")
        result["injected_context"].append("gate2 feedback: defer deployment")
        self.assertEqual(len(result["injected_context"]), 2)


# ── Context Bundle Tests ──────────────────────────────────────────────────────

class TestContextBundle(unittest.TestCase):

    def _auth_alert(self):
        return {
            "id": "alert-001",
            "service": "auth-service",
            "severity": "HIGH",
            "error": "Connection pool exhaustion",
            "affected_files": ["src/db/connection.py", "src/auth/session.py"],
            "environment": "production",
        }

    def _notification_alert(self):
        return {
            "id": "alert-003",
            "service": "notification-service",
            "severity": "LOW",
            "error": "Deprecated config flag",
            "affected_files": ["src/config/flags.py"],
            "environment": "staging",
        }

    # --- Shape contract ---

    def test_bundle_returns_dict(self):
        result = build_context_bundle(self._auth_alert())
        self.assertIsInstance(result, dict)

    def test_bundle_contains_required_keys(self):
        result = build_context_bundle(self._auth_alert())
        for key in ["alert", "git_history", "dependencies", "org_context"]:
            self.assertIn(key, result)

    def test_bundle_alert_matches_input(self):
        alert = self._auth_alert()
        result = build_context_bundle(alert)
        self.assertEqual(result["alert"]["id"], "alert-001")
        self.assertEqual(result["alert"]["service"], "auth-service")

    def test_bundle_contains_git_commits(self):
        result = build_context_bundle(self._auth_alert())
        self.assertIn("recent_commits", result["git_history"])

    def test_bundle_contains_dependency_keys(self):
        result = build_context_bundle(self._auth_alert())
        self.assertIn("depends_on", result["dependencies"])
        self.assertIn("depended_on_by", result["dependencies"])

    def test_bundle_contains_org_context(self):
        result = build_context_bundle(self._auth_alert())
        self.assertIn("injected_context", result["org_context"])

    # --- Alert-awareness in bundle ---

    def test_bundle_git_history_scoped_to_affected_files(self):
        result = build_context_bundle(self._auth_alert())
        files_touched = [
            f for commit in result["git_history"]["recent_commits"]
            for f in commit["files_changed"]
        ]
        # Should reference the actual affected files, not generic ones
        self.assertTrue(
            any("connection.py" in f or "session.py" in f for f in files_touched)
        )

    def test_bundle_dependencies_scoped_to_service(self):
        result = build_context_bundle(self._auth_alert())
        self.assertIn("postgres-primary", result["dependencies"]["depends_on"])

    def test_bundle_notification_service_has_different_deps(self):
        auth_result = build_context_bundle(self._auth_alert())
        notif_result = build_context_bundle(self._notification_alert())
        # Different services should produce different dependency graphs
        self.assertNotEqual(
            auth_result["dependencies"]["depends_on"],
            notif_result["dependencies"]["depends_on"],
        )

    def test_bundle_notification_commits_scoped_to_flags_file(self):
        result = build_context_bundle(self._notification_alert())
        files_touched = [
            f for commit in result["git_history"]["recent_commits"]
            for f in commit["files_changed"]
        ]
        # flags.py commits should appear, not connection.py
        self.assertTrue(
            all("flags.py" in f for f in files_touched) if files_touched else True
        )

    def test_bundle_review_recency_scoped_to_service(self):
        auth_result = build_context_bundle(self._auth_alert())
        notif_result = build_context_bundle(self._notification_alert())
        # Should return different review recency for different services
        self.assertNotEqual(
            auth_result["git_history"]["last_reviewed_days_ago"],
            notif_result["git_history"]["last_reviewed_days_ago"],
        )

    def test_bundle_injected_context_starts_empty(self):
        result = build_context_bundle(self._auth_alert())
        self.assertEqual(result["org_context"]["injected_context"], [])

    def test_bundle_injected_context_is_mutable(self):
        result = build_context_bundle(self._auth_alert())
        result["org_context"]["injected_context"].append("test injection")
        self.assertIn("test injection", result["org_context"]["injected_context"])

    def test_bundle_works_with_minimal_alert(self):
        minimal = {"id": "min-001", "service": "unknown-service", "affected_files": []}
        result = build_context_bundle(minimal)
        self.assertIn("alert", result)
        self.assertIn("git_history", result)
        self.assertEqual(result["dependencies"]["depends_on"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)