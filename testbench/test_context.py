"""
Unit tests for context modules: git_history, dependency_graph, org_context, bundle.
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

    def test_last_reviewed_is_positive(self):
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

    def test_empty_file_list_still_returns_history(self):
        result = get_git_history([])
        self.assertIn("recent_commits", result)

    def test_multiple_files_still_returns_history(self):
        result = get_git_history(["src/db/connection.py", "src/auth/session.py"])
        self.assertIn("recent_commits", result)


# ── Dependency Graph Tests ────────────────────────────────────────────────────

class TestDependencyGraph(unittest.TestCase):

    def test_returns_dict(self):
        result = get_dependency_graph("auth-service")
        self.assertIsInstance(result, dict)

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

    def test_depends_on_contains_strings(self):
        result = get_dependency_graph("auth-service")
        for item in result["depends_on"]:
            self.assertIsInstance(item, str)

    def test_depended_on_by_contains_strings(self):
        result = get_dependency_graph("auth-service")
        for item in result["depended_on_by"]:
            self.assertIsInstance(item, str)


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

    def _sample_alert(self):
        return {
            "id": "test-001",
            "service": "auth-service",
            "severity": "HIGH",
            "error": "connection pool exhaustion",
            "affected_files": ["src/db/connection.py"],
            "environment": "production",
        }

    def test_bundle_returns_dict(self):
        result = build_context_bundle(self._sample_alert())
        self.assertIsInstance(result, dict)

    def test_bundle_contains_alert(self):
        alert = self._sample_alert()
        result = build_context_bundle(alert)
        self.assertIn("alert", result)

    def test_bundle_alert_matches_input(self):
        alert = self._sample_alert()
        result = build_context_bundle(alert)
        self.assertEqual(result["alert"]["id"], "test-001")
        self.assertEqual(result["alert"]["service"], "auth-service")

    def test_bundle_contains_git_history(self):
        result = build_context_bundle(self._sample_alert())
        self.assertIn("git_history", result)
        self.assertIn("recent_commits", result["git_history"])

    def test_bundle_contains_dependencies(self):
        result = build_context_bundle(self._sample_alert())
        self.assertIn("dependencies", result)
        self.assertIn("depends_on", result["dependencies"])

    def test_bundle_contains_org_context(self):
        result = build_context_bundle(self._sample_alert())
        self.assertIn("org_context", result)
        self.assertIn("injected_context", result["org_context"])

    def test_bundle_injected_context_is_mutable_list(self):
        result = build_context_bundle(self._sample_alert())
        result["org_context"]["injected_context"].append("test injection")
        self.assertIn("test injection", result["org_context"]["injected_context"])

    def test_bundle_works_with_minimal_alert(self):
        minimal_alert = {"id": "min-001", "service": "svc", "affected_files": []}
        result = build_context_bundle(minimal_alert)
        self.assertIn("alert", result)
        self.assertIn("git_history", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
