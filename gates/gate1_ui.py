# gates/gate1_ui.py
"""
Gate 1 UI (CLI): Engineer validates the AI diagnosis.

Design goals:
- Fast (~30 seconds)
- Enough info for a genuine decision (not rubber-stamp)
- Engineer can confirm OR reject + inject correction/context
"""

from __future__ import annotations

from typing import Any, Dict, List


def _format_percent(confidence: float) -> str:
    """Convert 0.0–1.0 into a clean percentage string."""
    try:
        return f"{float(confidence) * 100:.0f}%"
    except Exception:
        return "N/A"


def run_gate1(diagnosis_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Print AI hypotheses and capture engineer decision.

    Input: diagnosis_result dict (see data contracts):
      {
        "hypotheses": [
          { "id": int, "description": str, "confidence": float, "reasoning": str,
            "uncertainty_flags": [str] }
        ],
        "context_freshness_warning": bool
      }

    Output: gate1_result dict (data contract):
      {
        "decision": "confirmed" | "rejected",
        "selected_hypothesis_id": int,   # if confirmed; -1 if rejected
        "correction": str,               # if rejected; "" if confirmed
        "approved_by": str
      }
    """
    print("\n" + "=" * 72)
    print("GATE 1 — VALIDATE DIAGNOSIS  (target: ~30 seconds)")
    print("=" * 72)

    if diagnosis_result.get("context_freshness_warning"):
        print("⚠️  Context may be stale (recent human review is missing).\n")

    hypotheses: List[Dict[str, Any]] = diagnosis_result.get("hypotheses", [])
    if not hypotheses:
        print("No hypotheses returned by AI. Escalate to manual investigation.")
        engineer = input("Enter your handle (e.g., @keefe): ").strip() or "@unknown"
        return {
            "decision": "rejected",
            "selected_hypothesis_id": -1,
            "correction": "No hypotheses returned. Manual triage required.",
            "approved_by": engineer,
        }

    print("AI hypotheses:\n")

    for idx, h in enumerate(hypotheses, start=1):
        hid = h.get("id", idx)
        desc = h.get("description", "(no description)")
        conf = _format_percent(h.get("confidence", 0.0))
        reasoning = h.get("reasoning", "(no reasoning provided)")
        flags = h.get("uncertainty_flags", [])

        print(f"[{idx}] Hypothesis ID: {hid}  |  Confidence: {conf}")
        print(f"    Summary: {desc}")
        print(f"    Reasoning: {reasoning}")
        if flags:
            print(f"    Uncertainty flags: {', '.join(str(x) for x in flags)}")
        else:
            print("    Uncertainty flags: none")
        print("-" * 72)

    print("\nYour decision:")
    print("  - Type a number (e.g., 1) to CONFIRM a hypothesis.")
    print('  - Type "r" to REJECT ALL and provide a correction/context.\n')

    engineer = input("Enter your handle (e.g., @keefe): ").strip() or "@unknown"

    while True:
        choice = input("Confirm hypothesis number, or 'r' to reject: ").strip().lower()

        if choice == "r":
            correction = input("Correction/context (1–2 sentences): ").strip()
            if not correction:
                print("Correction cannot be empty. Try again.")
                continue
            return {
                "decision": "rejected",
                "selected_hypothesis_id": -1,
                "correction": correction,
                "approved_by": engineer,
            }

        if choice.isdigit():
            n = int(choice)
            if 1 <= n <= len(hypotheses):
                selected_id = int(hypotheses[n - 1].get("id", n))
                return {
                    "decision": "confirmed",
                    "selected_hypothesis_id": selected_id,
                    "correction": "",
                    "approved_by": engineer,
                }

        print(f"Invalid input. Enter 1–{len(hypotheses)} or 'r'.")