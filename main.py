# Entry point — orchestrates the full Codex Guardian pipeline in order:
# alert → context → scoring → route → Gate 0 compliance → diagnose →
# gate1 → patch → gate2 → sandbox → log

import json
import sys

from context.bundle import build_context_bundle
from scoring.risk_score import score_risk
from scoring.freshness_score import score_freshness
from scoring.router import route
from gates.gate0_compliance import run_gate0
from codex.diagnose import diagnose
from codex.patch import generate_patch
from gates.gate1_ui import run_gate1
from gates.gate2_ui import run_gate2
from validation.sandbox import run_sandbox
from audit.logger import log_decision


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _header(title):
    """Print a clear stage header to terminal for demo readability."""
    print("\n" + "═" * 72)
    print(f"  STEP: {title}")
    print("═" * 72)


def _load_alert(alert_index=0):
    """
    Load a single alert from input/alert.json.
    The file contains an array of alerts; use alert_index to select one.
    """
    with open("input/alert.json", "r") as f:
        alerts = json.load(f)

    if alert_index >= len(alerts):
        print(f"[MAIN] ERROR: alert_index {alert_index} out of range. File has {len(alerts)} alerts.")
        sys.exit(1)

    alert = alerts[alert_index]
    print(f"[MAIN] Loaded alert: [{alert['id']}] {alert['service']} — {alert['error']}")
    print(f"       Severity: {alert['severity']} | Environment: {alert['environment']}")
    return alert


# ─────────────────────────────────────────────────────────────
# GATE 2 ADAPTER
# ─────────────────────────────────────────────────────────────

def _adapt_patch_for_gate2(patch_proposal):
    """
    gate2_ui.py expects blast_radius as a dict with keys 'level', 'services_touched',
    'files_touched', and 'notes'. The data contract (and codex/patch.py) returns
    blast_radius as a plain string. This adapter wraps it into the required shape.
    Also maps 'explanation' -> 'reasoning' since gate2_ui.py looks for 'reasoning'.
    """
    blast_str = patch_proposal.get("blast_radius", "")
    adapted = dict(patch_proposal)
    adapted["blast_radius"] = {
        "level": "HIGH" if any(
            w in blast_str.lower() for w in ["critical", "high", "major"]
        ) else "MEDIUM",
        "services_touched": patch_proposal.get("affected_services", []),
        "files_touched": [],
        "notes": blast_str,
    }
    adapted["reasoning"] = patch_proposal.get("explanation", "")
    return adapted


# ─────────────────────────────────────────────────────────────
# SECOND APPROVER PROMPT
# ─────────────────────────────────────────────────────────────

def _collect_second_approver(gate2_result):
    """
    Prompt for a second engineer's approval when compliance requires it.
    Called after the primary Gate 2 approval when compliance_result
    has requires_second_approver=True.

    Returns:
        dict: { "approved_by": str, "rationale": str, "decision": str }
              or None if the second approver rejects (caller handles pipeline halt).
    """
    print("\n" + "=" * 72)
    print("GATE 2 — SECOND APPROVER REQUIRED (compliance policy POL-001)")
    print("=" * 72)
    print("This patch touches a high-trust service and requires a second engineer sign-off.")
    print(f"Primary approver: {gate2_result.get('approved_by', '@unknown')}")
    print(f"Primary rationale: {gate2_result.get('rationale', '')}")
    print("-" * 72)

    second_approver = input("Second approver handle (must differ from primary): ").strip() or "@unknown"

    while True:
        decision = input("Type 'approve' to confirm, or 'reject' to block: ").strip().lower()
        if decision in ("approve", "reject"):
            rationale = input(f"1-line rationale (why {decision}?): ").strip()
            if not rationale:
                print("Rationale cannot be empty. Try again.")
                continue
            # Normalize to "approved"/"rejected" to match gate1_ui/gate2_ui convention
            normalized = "approved" if decision == "approve" else "rejected"
            return {
                "approved_by": second_approver,
                "rationale":   rationale,
                "decision":    normalized,
            }
        print("Invalid input. Type exactly 'approve' or 'reject'.")


# ─────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────

def run_pipeline(alert_index=0):
    """
    Run the full Codex Guardian pipeline for a single alert.

    Args:
        alert_index (int): Which alert to load from input/alert.json (0-indexed).
                           0 = HIGH risk (auth-service) — triggers both gates
                           2 = LOW risk (notification-service) — auto-handled
    """

    # ── STEP 1: Load alert ────────────────────────────────────
    _header("STEP 1 — Load Alert")
    alert = _load_alert(alert_index)

    # ── STEP 2: Build context bundle ─────────────────────────
    _header("STEP 2 — Build Context Bundle")
    context_bundle = build_context_bundle(alert)

    # ── STEP 3: Score decision risk ───────────────────────────
    _header("STEP 3 — Score Decision Risk")
    risk_result = score_risk(alert, context_bundle["dependencies"])
    print(f"         Risk level: {risk_result['level']}")
    for r in risk_result["reasons"]:
        print(f"         • {r}")

    # ── STEP 4: Score context freshness ───────────────────────
    _header("STEP 4 — Score Context Freshness")
    freshness_result = score_freshness(context_bundle["git_history"])
    print(
        f"         Freshness: {freshness_result['score']} | "
        f"Last reviewed: {freshness_result['last_reviewed_days_ago']}d ago | "
        f"Churn: {freshness_result['churn_rate']}"
    )

    # ── STEP 5: Route the alert ───────────────────────────────
    _header("STEP 5 — Route Alert")
    route_decision = route(risk_result, freshness_result)
    print(f"         → Routing to: {route_decision['route'].upper()}")

    # ── STEP 5.5: Gate 0 — Compliance check ──────────────────
    _header("STEP 5.5 — Gate 0: Compliance Check")
    compliance_result = run_gate0(alert, route_decision, context_bundle)

    if compliance_result["flags"]:
        print("\n  Compliance flags raised:")
        for flag in compliance_result["flags"]:
            print(f"    ⚠️  {flag}")
        print("\n  Restrictions injected into AI context:")
        for restriction in compliance_result["restrictions"]:
            # Inject each restriction so the AI sees it before diagnosing/patching
            context_bundle["org_context"]["injected_context"].append(
                f"[Compliance] {restriction}"
            )
            print(f"    → {restriction.strip()[:80]}...")

    if not compliance_result["proceed"]:
        print("\n" + "!" * 72)
        print("  COMPLIANCE BLOCKED — pipeline halted by policy hard block.")
        print("  The following rules triggered a hard block:")
        for r in compliance_result["policy_reasoning"]:
            if r["triggered"]:
                print(f"    ❌ [{r['rule_id']}] {r['rule']}")
        print("  Do not attempt an automated fix. Escalate manually.")
        print("!" * 72)

        _write_audit(
            alert=alert,
            route_decision=route_decision,
            risk_result=risk_result,
            freshness_result=freshness_result,
            compliance_result=compliance_result,
            ai_hypothesis="N/A (compliance blocked)",
            engineer_gate1_decision="N/A",
            engineer_gate2_decision="N/A",
            approved_by="system",
            second_approver_result=None,
            gate1_result=None,
            gate2_result=None,
            diagnosis_result=None,
            patch_proposal=None,
            sandbox_result={"status": "N/A", "details": "Pipeline halted by compliance gate."},
            outcome="compliance_blocked",
            notes="Hard block triggered by Gate 0 compliance check.",
        )
        return

    # Track state for audit log
    engineer_gate1_decision = "N/A"
    engineer_gate2_decision = "N/A"
    approved_by = "system"
    sandbox_result = None
    outcome = "auto-resolved"

    # ── AUTO-HANDLE PATH ──────────────────────────────────────
    if route_decision["route"] == "auto-handle":
        print("\n  [AUTO-HANDLE] Low risk + fresh context. Resolving automatically.")
        print("  [AUTO-HANDLE] No human gates required.")

        _write_audit(
            alert=alert,
            route_decision=route_decision,
            risk_result=risk_result,
            freshness_result=freshness_result,
            compliance_result=compliance_result,
            ai_hypothesis="N/A (auto-handled)",
            engineer_gate1_decision="N/A",
            engineer_gate2_decision="N/A",
            approved_by="system",
            second_approver_result=None,
            gate1_result=None,
            gate2_result=None,
            diagnosis_result=None,
            patch_proposal=None,
            sandbox_result={"status": "N/A", "details": "No patch required — auto-resolved."},
            outcome="auto-resolved",
            notes="Low-risk incident handled automatically. No human intervention.",
        )
        return

    # ── ESCALATION PATH: GATE 1 + GATE 2 ─────────────────────

    # ── STEP 6: AI Diagnosis (with rejection loop) ────────────
    diagnosis_result = None
    confirmed_hypothesis = None
    gate1_result = None
    diagnosis_attempts = 0

    while confirmed_hypothesis is None:
        diagnosis_attempts += 1
        _header(f"STEP 6 — AI Diagnosis (attempt {diagnosis_attempts})")
        diagnosis_result = diagnose(context_bundle)

        # ── STEP 7: Gate 1 — Engineer validates diagnosis ─────
        _header("STEP 7 — Gate 1: Validate Diagnosis")
        gate1_result = run_gate1(diagnosis_result)

        if gate1_result["decision"] == "confirmed":
            selected_id = gate1_result["selected_hypothesis_id"]
            for h in diagnosis_result["hypotheses"]:
                if h["id"] == selected_id:
                    confirmed_hypothesis = h
                    break

            if confirmed_hypothesis is None:
                confirmed_hypothesis = diagnosis_result["hypotheses"][0]

            engineer_gate1_decision = "confirmed"
            approved_by = gate1_result["approved_by"]
            print(f"\n  ✓ Gate 1 passed — hypothesis {selected_id} confirmed by {approved_by}")

        else:
            correction = gate1_result["correction"]
            engineer_gate1_decision = "corrected"
            approved_by = gate1_result["approved_by"]
            print(f"\n  ✗ Gate 1 rejected — injecting correction and re-diagnosing...")
            print(f"    Correction: {correction}")

            context_bundle["org_context"]["injected_context"].append(
                f"[Gate 1 engineer correction] {correction}"
            )

    # ── STEP 8 + 9: Patch Generation (with Gate 2 rejection loop) ──
    patch_proposal = None
    gate2_result = None
    second_approver_result = None
    patch_attempts = 0

    while gate2_result is None or gate2_result["decision"] == "rejected":

        patch_attempts += 1
        _header(f"STEP 8 — AI Patch Generation (attempt {patch_attempts})")
        patch_proposal = generate_patch(confirmed_hypothesis, context_bundle)

        # ── STEP 9: Gate 2 — Engineer approves fix ────────────
        _header("STEP 9 — Gate 2: Approve Fix")
        gate2_result = run_gate2(_adapt_patch_for_gate2(patch_proposal))

        if gate2_result["decision"] == "rejected":
            feedback = gate2_result.get("rationale", gate2_result.get("feedback", ""))
            engineer_gate2_decision = "rejected"
            print(f"\n  ✗ Gate 2 rejected — injecting feedback and regenerating patch...")
            print(f"    Feedback: {feedback}")

            context_bundle["org_context"]["injected_context"].append(
                f"[Gate 2 engineer feedback on rejected patch] {feedback}"
            )
        else:
            engineer_gate2_decision = "approved"
            approved_by = gate2_result["approved_by"]
            print(f"\n  ✓ Gate 2 passed — patch approved by {approved_by}")

            # ── Second approver enforcement (compliance POL-001) ──
            if compliance_result.get("requires_second_approver"):
                _header("STEP 9.1 — Second Approver Required (Compliance)")
                second_approver_result = _collect_second_approver(gate2_result)

                if second_approver_result["decision"] == "rejected":
                    print(
                        f"\n  ✗ Second approver rejected — "
                        f"injecting feedback and regenerating patch..."
                    )
                    print(f"    Feedback: {second_approver_result['rationale']}")
                    context_bundle["org_context"]["injected_context"].append(
                        f"[Second approver rejection] {second_approver_result['rationale']}"
                    )
                    # Force outer loop to continue
                    gate2_result = {"decision": "rejected",
                                    "rationale": second_approver_result["rationale"],
                                    "approved_by": second_approver_result["approved_by"]}
                else:
                    print(
                        f"\n  ✓ Second approver confirmed — "
                        f"{second_approver_result['approved_by']}"
                    )

    # ── STEP 10: Sandbox Validation ───────────────────────────
    _header("STEP 10 — Sandbox Validation")
    sandbox_result = run_sandbox(patch_proposal)

    if sandbox_result["status"] == "fail":
        print(f"\n  ✗ Sandbox FAILED: {sandbox_result['details']}")
        print("  → Injecting failure details and returning to diagnosis...")

        context_bundle["org_context"]["injected_context"].append(
            f"[Sandbox failure] {sandbox_result['details']} — patch was rejected by sandbox."
        )

        confirmed_hypothesis = None
        gate2_result = None
        second_approver_result = None

        while confirmed_hypothesis is None:
            diagnosis_attempts += 1
            _header(f"STEP 6 — AI Re-Diagnosis after sandbox fail (attempt {diagnosis_attempts})")
            diagnosis_result = diagnose(context_bundle)

            _header("STEP 7 — Gate 1: Re-Validate Diagnosis")
            gate1_result = run_gate1(diagnosis_result)

            if gate1_result["decision"] == "confirmed":
                selected_id = gate1_result["selected_hypothesis_id"]
                for h in diagnosis_result["hypotheses"]:
                    if h["id"] == selected_id:
                        confirmed_hypothesis = h
                        break
                if confirmed_hypothesis is None:
                    confirmed_hypothesis = diagnosis_result["hypotheses"][0]
                engineer_gate1_decision = "confirmed (re-run)"
                approved_by = gate1_result["approved_by"]
            else:
                correction = gate1_result["correction"]
                engineer_gate1_decision = "corrected (re-run)"
                approved_by = gate1_result["approved_by"]
                context_bundle["org_context"]["injected_context"].append(
                    f"[Gate 1 re-run correction] {correction}"
                )

        while gate2_result is None or gate2_result["decision"] == "rejected":
            patch_attempts += 1
            _header(f"STEP 8 — AI Re-Patch after sandbox fail (attempt {patch_attempts})")
            patch_proposal = generate_patch(confirmed_hypothesis, context_bundle)

            _header("STEP 9 — Gate 2: Re-Approve Fix")
            gate2_result = run_gate2(_adapt_patch_for_gate2(patch_proposal))

            if gate2_result["decision"] == "rejected":
                feedback = gate2_result.get("rationale", gate2_result.get("feedback", ""))
                engineer_gate2_decision = "rejected"
                context_bundle["org_context"]["injected_context"].append(
                    f"[Gate 2 post-sandbox-fail rejection] {feedback}"
                )
            else:
                engineer_gate2_decision = "approved"
                approved_by = gate2_result["approved_by"]

                if compliance_result.get("requires_second_approver"):
                    _header("STEP 9.1 — Second Approver Required (Compliance, re-run)")
                    second_approver_result = _collect_second_approver(gate2_result)

                    if second_approver_result["decision"] == "rejected":
                        context_bundle["org_context"]["injected_context"].append(
                            f"[Second approver rejection (re-run)] {second_approver_result['rationale']}"
                        )
                        gate2_result = {"decision": "rejected",
                                        "rationale": second_approver_result["rationale"],
                                        "approved_by": second_approver_result["approved_by"]}

        _header("STEP 10 — Sandbox Validation (retry)")
        sandbox_result = run_sandbox(patch_proposal)

    if sandbox_result["status"] == "pass":
        outcome = "deployed"
        print(f"\n  ✓ Sandbox PASSED: {sandbox_result['details']}")
    else:
        outcome = "sandbox_fail"
        print(f"\n  ✗ Sandbox still failing. Manual escalation required.")

    # ── STEP 11: Log to audit trail ───────────────────────────
    ai_hypothesis_summary = (
        confirmed_hypothesis.get("description", "unknown")
        if confirmed_hypothesis else "N/A"
    )

    _write_audit(
        alert=alert,
        route_decision=route_decision,
        risk_result=risk_result,
        freshness_result=freshness_result,
        compliance_result=compliance_result,
        ai_hypothesis=ai_hypothesis_summary,
        engineer_gate1_decision=engineer_gate1_decision,
        engineer_gate2_decision=engineer_gate2_decision,
        approved_by=approved_by,
        second_approver_result=second_approver_result,
        gate1_result=gate1_result,
        gate2_result=gate2_result,
        diagnosis_result=diagnosis_result,
        patch_proposal=patch_proposal,
        sandbox_result=sandbox_result,
        outcome=outcome,
        notes=(
            f"Diagnosis attempts: {diagnosis_attempts}. "
            f"Patch attempts: {patch_attempts}."
        ),
    )

    # ── STEP 12: Final outcome summary ────────────────────────
    _header("STEP 12 — Final Outcome")
    print(f"  Alert ID:   {alert['id']}")
    print(f"  Service:    {alert['service']}")
    print(f"  Route:      {route_decision['route']}")
    print(f"  Outcome:    {outcome.upper()}")
    print(f"  Approved by: {approved_by}")
    print(f"  Sandbox:    {sandbox_result['status'].upper()}")
    if compliance_result["flags"]:
        print(f"  Compliance flags: {len(compliance_result['flags'])}")
    if second_approver_result:
        print(f"  Second approver: {second_approver_result['approved_by']}")
    print("\n  Pipeline complete. Audit log updated.")
    print("═" * 72 + "\n")


# ─────────────────────────────────────────────────────────────
# AUDIT HELPER
# ─────────────────────────────────────────────────────────────

def _write_audit(
    alert, route_decision, risk_result, freshness_result,
    compliance_result,
    ai_hypothesis, engineer_gate1_decision, engineer_gate2_decision,
    approved_by, second_approver_result,
    gate1_result, gate2_result, diagnosis_result, patch_proposal,
    sandbox_result, outcome, notes
):
    """Assemble and write the audit entry for this pipeline run."""
    _header("STEP 11 — Write Audit Log")

    from datetime import datetime, timezone

    audit_entry = {
        # ── Existing fields (unchanged shape) ──
        "timestamp":                datetime.now(timezone.utc).isoformat(),
        "alert_id":                 alert["id"],
        "route_taken":              route_decision["route"],
        "risk_level":               route_decision["risk_level"],
        "freshness":                route_decision["freshness"],
        "ai_hypothesis":            ai_hypothesis,
        "engineer_gate1_decision":  engineer_gate1_decision,
        "engineer_gate2_decision":  engineer_gate2_decision,
        "approved_by":              approved_by,
        "sandbox_result":           sandbox_result["status"] if sandbox_result else "N/A",
        "outcome":                  outcome,
        "notes":                    notes,

        # ── Phase 3 — compliance fields ──
        "compliance_flags":         compliance_result.get("flags", []),
        "compliance_reasoning":     compliance_result.get("policy_reasoning", []),

        # ── Phase 2 — reasoning chains (populated when available) ──
        "diagnosis_reasoning_chain": (
            diagnosis_result.get("reasoning_chain", [])
            if diagnosis_result else []
        ),
        "patch_reasoning_chain": (
            patch_proposal.get("reasoning_chain", [])
            if patch_proposal else []
        ),

        # ── Phase 4 — clarification logs (empty until Phase 4 built) ──
        "gate1_clarifications": (
            gate1_result.get("clarification_log", [])
            if gate1_result else []
        ),
        "gate2_clarifications": (
            gate2_result.get("clarification_log", [])
            if gate2_result else []
        ),

        # ── Phase 3 — second approver ──
        "second_approver": (
            second_approver_result.get("approved_by", "N/A")
            if second_approver_result else "N/A"
        ),
    }

    log_decision(audit_entry)


# ─────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Usage:
    #   python main.py        → runs alert index 0 (HIGH risk, auth-service)
    #   python main.py 2      → runs alert index 2 (LOW risk, notification-service)

    index = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    run_pipeline(alert_index=index)