# Entry point — orchestrates the full Codex Guardian pipeline in order:
# alert → context → scoring → route → diagnose → gate1 → patch → gate2 → sandbox → log

import json
import sys

from context.bundle import build_context_bundle
from scoring.risk_score import score_risk
from scoring.freshness_score import score_freshness
from scoring.router import route
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

        # Jump straight to step 11
        _write_audit(
            alert=alert,
            route_decision=route_decision,
            risk_result=risk_result,
            freshness_result=freshness_result,
            ai_hypothesis="N/A (auto-handled)",
            engineer_gate1_decision="N/A",
            engineer_gate2_decision="N/A",
            approved_by="system",
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
            # Find the confirmed hypothesis object by its ID
            selected_id = gate1_result["selected_hypothesis_id"]
            for h in diagnosis_result["hypotheses"]:
                if h["id"] == selected_id:
                    confirmed_hypothesis = h
                    break

            if confirmed_hypothesis is None:
                # Fallback: just take the first hypothesis
                confirmed_hypothesis = diagnosis_result["hypotheses"][0]

            engineer_gate1_decision = "confirmed"
            approved_by = gate1_result["approved_by"]
            print(f"\n  ✓ Gate 1 passed — hypothesis {selected_id} confirmed by {approved_by}")

        else:
            # Engineer rejected — inject correction and re-diagnose
            correction = gate1_result["correction"]
            engineer_gate1_decision = "corrected"
            approved_by = gate1_result["approved_by"]
            print(f"\n  ✗ Gate 1 rejected — injecting correction and re-diagnosing...")
            print(f"    Correction: {correction}")

            # Append correction to org_context so the AI sees it on next pass
            context_bundle["org_context"]["injected_context"].append(
                f"[Gate 1 engineer correction] {correction}"
            )

    # ── STEP 8 + 9: Patch Generation (with Gate 2 rejection loop) ──
    patch_proposal = None
    gate2_result = None
    patch_attempts = 0

    while gate2_result is None or gate2_result["decision"] == "rejected":

        # If we've looped back here from a sandbox fail, confirmed_hypothesis
        # is already set from Gate 1 — the context_bundle now has the failure note.
        # If we're looping due to Gate 2 rejection, same applies.

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

            # Append feedback to context so AI improves its next patch
            context_bundle["org_context"]["injected_context"].append(
                f"[Gate 2 engineer feedback on rejected patch] {feedback}"
            )
        else:
            engineer_gate2_decision = "approved"
            approved_by = gate2_result["approved_by"]
            print(f"\n  ✓ Gate 2 passed — patch approved by {approved_by}")

    # ── STEP 10: Sandbox Validation ───────────────────────────
    _header("STEP 10 — Sandbox Validation")
    sandbox_result = run_sandbox(patch_proposal)

    if sandbox_result["status"] == "fail":
        print(f"\n  ✗ Sandbox FAILED: {sandbox_result['details']}")
        print("  → Injecting failure details and returning to diagnosis...")

        # Inject failure context and restart from diagnosis
        context_bundle["org_context"]["injected_context"].append(
            f"[Sandbox failure] {sandbox_result['details']} — patch was rejected by sandbox."
        )

        # Reset gate state and re-enter the full diagnosis loop
        confirmed_hypothesis = None
        gate2_result = None

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
        ai_hypothesis=ai_hypothesis_summary,
        engineer_gate1_decision=engineer_gate1_decision,
        engineer_gate2_decision=engineer_gate2_decision,
        approved_by=approved_by,
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
    print("\n  Pipeline complete. Audit log updated.")
    print("═" * 72 + "\n")


# ─────────────────────────────────────────────────────────────
# AUDIT HELPER
# ─────────────────────────────────────────────────────────────

def _write_audit(
    alert, route_decision, risk_result, freshness_result,
    ai_hypothesis, engineer_gate1_decision, engineer_gate2_decision,
    approved_by, sandbox_result, outcome, notes
):
    """Assemble and write the audit entry for this pipeline run."""
    _header("STEP 11 — Write Audit Log")

    from datetime import datetime, timezone

    audit_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "alert_id": alert["id"],
        "route_taken": route_decision["route"],
        "risk_level": route_decision["risk_level"],
        "freshness": route_decision["freshness"],
        "ai_hypothesis": ai_hypothesis,
        "engineer_gate1_decision": engineer_gate1_decision,
        "engineer_gate2_decision": engineer_gate2_decision,
        "approved_by": approved_by,
        "sandbox_result": sandbox_result["status"] if sandbox_result else "N/A",
        "outcome": outcome,
        "notes": notes,
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