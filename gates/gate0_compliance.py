# gates/gate0_compliance.py
"""
Gate 0 — Compliance Check.

Runs before any AI work begins. Evaluates the incoming alert and routing
decision against the rules defined in policies.yaml.

Design goals:
- Non-technical team members can edit policies.yaml without touching code
- Every rule is checked and recorded — triggered OR not — for the audit trail
- Hard-block rules halt the pipeline immediately; soft rules inject restrictions
- Restrictions flow into context_bundle.org_context.injected_context so the
  AI sees them before generating any hypothesis or patch

Input:
    alert          (dict) — the alert payload from alert.json
    route_decision (dict) — output of scoring/router.py
    context_bundle (dict) — full context bundle; used for shared_infra check

Output (compliance_result):
{
    "proceed":    bool,
    "flags":      [str],          # short human-readable labels for triggered rules
    "restrictions": [str],        # injected into org_context.injected_context
    "requires_second_approver": bool,
    "policy_reasoning": [
        {
            "rule_id":              str,
            "rule":                 str,
            "triggered":            bool,
            "reason":               str,
            "restriction_injected": str,   # empty str if rule not triggered
        }
    ],
}
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import yaml


_POLICIES_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "policies.yaml")


def _load_policies(path: str = _POLICIES_PATH) -> Dict[str, Any]:
    """Load and parse policies.yaml. Raises FileNotFoundError if missing."""
    with open(path, "r") as f:
        return yaml.safe_load(f)


# ─────────────────────────────────────────────────────────────
# CONDITION EVALUATORS
# ─────────────────────────────────────────────────────────────

def _eval_service_name_match(condition: Dict, alert: Dict, **_) -> tuple[bool, str]:
    service = alert.get("service", "")
    targets = [s.lower() for s in condition.get("services", [])]
    matched = service.lower() in targets
    if matched:
        return True, f"Service '{service}' is in restricted service list: {condition['services']}"
    return False, f"Service '{service}' is not in restricted service list — rule does not apply"


def _eval_severity_match(condition: Dict, alert: Dict, **_) -> tuple[bool, str]:
    severity = alert.get("severity", "").upper()
    targets = [s.upper() for s in condition.get("severities", [])]
    matched = severity in targets
    if matched:
        return True, f"Alert severity '{severity}' matches restricted levels: {condition['severities']}"
    return False, f"Alert severity '{severity}' is not in restricted levels — rule does not apply"


def _eval_environment_match(condition: Dict, alert: Dict, **_) -> tuple[bool, str]:
    env = alert.get("environment", "").lower()
    target = condition.get("environment", "").lower()
    matched = env == target
    if matched:
        return True, f"Alert environment '{env}' matches restricted environment '{target}'"
    return False, f"Alert environment '{env}' does not match '{target}' — rule does not apply"


def _eval_file_pattern_match(condition: Dict, alert: Dict, **_) -> tuple[bool, str]:
    patterns = condition.get("patterns", [])
    affected_files = alert.get("affected_files", [])
    for fpath in affected_files:
        for pattern in patterns:
            if pattern in fpath:
                return (
                    True,
                    f"Affected file '{fpath}' matches restricted pattern '{pattern}'",
                )
    return (
        False,
        f"No affected files match restricted patterns {patterns} — rule does not apply",
    )


def _eval_shared_infra_present(
    condition: Dict, alert: Dict, context_bundle: Dict, **_
) -> tuple[bool, str]:
    deps = context_bundle.get("dependencies", {})
    shared_infra = deps.get("shared_infra", [])
    if shared_infra:
        return (
            True,
            f"Alert touches shared infrastructure: {', '.join(shared_infra)}",
        )
    return False, "No shared infrastructure detected — rule does not apply"


def _eval_freeze_window_active(
    condition: Dict, alert: Dict, policies: Dict, **_
) -> tuple[bool, str]:
    freeze = policies.get("freeze_window", {})
    active = freeze.get("active", False)
    target_env = condition.get("environment", "production").lower()
    alert_env = alert.get("environment", "").lower()

    if not active:
        return False, "Deploy freeze window is not currently active — rule does not apply"
    if alert_env != target_env:
        return (
            False,
            f"Alert environment '{alert_env}' is not '{target_env}' — freeze window does not apply",
        )
    reason = freeze.get("reason", "Freeze window active")
    return True, f"Deploy freeze is ACTIVE for '{target_env}' environment. Reason: {reason}"


# ─────────────────────────────────────────────────────────────
# DISPATCH TABLE
# ─────────────────────────────────────────────────────────────

_CONDITION_EVALUATORS = {
    "service_name_match":   _eval_service_name_match,
    "severity_match":       _eval_severity_match,
    "environment_match":    _eval_environment_match,
    "file_pattern_match":   _eval_file_pattern_match,
    "shared_infra_present": _eval_shared_infra_present,
    "freeze_window_active": _eval_freeze_window_active,
}


# ─────────────────────────────────────────────────────────────
# MAIN FUNCTION
# ─────────────────────────────────────────────────────────────

def run_gate0(
    alert: Dict[str, Any],
    route_decision: Dict[str, Any],
    context_bundle: Dict[str, Any],
    policies_path: str = _POLICIES_PATH,
) -> Dict[str, Any]:
    """
    Evaluate the alert against all policy rules in policies.yaml.

    Args:
        alert:          Alert payload from alert.json
        route_decision: Output of scoring/router.py
        context_bundle: Full context bundle (needed for shared_infra check)
        policies_path:  Override path for policies.yaml (used in tests)

    Returns:
        compliance_result dict (see module docstring for full shape)
    """
    print("\n[GATE 0] Running compliance check against policies.yaml...")

    policies = _load_policies(policies_path)
    rules: List[Dict] = policies.get("rules", [])

    proceed = True
    flags: List[str] = []
    restrictions: List[str] = []
    requires_second_approver = False
    policy_reasoning: List[Dict[str, Any]] = []

    for rule_def in rules:
        rule_id = rule_def.get("id", "UNKNOWN")
        rule_text = rule_def.get("rule", "")
        condition = rule_def.get("condition", {})
        restriction_text = rule_def.get("restriction", "").strip()
        hard_block = rule_def.get("hard_block", False)
        req_second = rule_def.get("requires_second_approver", False)

        ctype = condition.get("type", "")
        evaluator = _CONDITION_EVALUATORS.get(ctype)

        if evaluator is None:
            # Unknown condition type — skip with a warning
            reason = f"Unknown condition type '{ctype}' — rule skipped"
            triggered = False
        else:
            triggered, reason = evaluator(
                condition=condition,
                alert=alert,
                context_bundle=context_bundle,
                route_decision=route_decision,
                policies=policies,
            )

        if triggered:
            flags.append(f"[{rule_id}] {rule_text}")
            restrictions.append(f"[{rule_id}] {restriction_text}")
            if hard_block:
                proceed = False
                print(f"[GATE 0] ❌ HARD BLOCK — {rule_id}: {rule_text}")
            else:
                print(f"[GATE 0] ⚠️  Flag — {rule_id}: {rule_text}")
            if req_second:
                requires_second_approver = True
        else:
            print(f"[GATE 0] ✅ Pass — {rule_id}: {rule_text}")

        policy_reasoning.append(
            {
                "rule_id":              rule_id,
                "rule":                 rule_text,
                "triggered":            triggered,
                "reason":               reason,
                "restriction_injected": restriction_text if triggered else "",
            }
        )

    if proceed:
        if flags:
            print(
                f"[GATE 0] Compliance check complete — {len(flags)} flag(s), "
                f"pipeline may proceed with restrictions."
            )
        else:
            print("[GATE 0] Compliance check complete — no flags. Pipeline proceeds normally.")
    else:
        print(
            f"[GATE 0] COMPLIANCE BLOCKED — "
            f"{sum(1 for r in policy_reasoning if r['triggered'] and _is_hard_block(r['rule_id'], rules))} "
            f"hard block(s) triggered. Pipeline halted."
        )

    return {
        "proceed":                 proceed,
        "flags":                   flags,
        "restrictions":            restrictions,
        "requires_second_approver": requires_second_approver,
        "policy_reasoning":        policy_reasoning,
    }


def _is_hard_block(rule_id: str, rules: List[Dict]) -> bool:
    """Helper: return True if the given rule_id has hard_block=True."""
    for r in rules:
        if r.get("id") == rule_id:
            return r.get("hard_block", False)
    return False