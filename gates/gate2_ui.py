# gates/gate2_ui.py
"""
Gate 2 UI (CLI): Engineer approves or rejects the proposed patch.

Design goals:
- Deliberate (~60–90 seconds)
- Make risk/impact visible
- Force explicit human accountability (typed approval + rationale)
"""

from __future__ import annotations

from typing import Any, Dict


def run_gate2(patch_result: Dict[str, Any], risk_score: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Input:
      patch_result dict (expected shape):
        {
          "diff": str,
          "reasoning": str,
          "blast_radius": {
             "level": "LOW"|"MEDIUM"|"HIGH",
             "services_touched": [str],
             "files_touched": [str],
             "notes": str
          },
          "uncertainty_flags": [str]
        }

      risk_score (optional):
        {
          "overall": "LOW"|"MEDIUM"|"HIGH",
          "freshness": "OK"|"STALE",
          "why": str
        }

    Output (gate2_result):
      {
        "decision": "approved" | "rejected",
        "rationale": str,
        "approved_by": str
      }
    """
    print("\n" + "=" * 72)
    print("GATE 2 — APPROVE PATCH (human authority boundary)")
    print("=" * 72)

    # Show risk routing summary if available
    if risk_score:
        print(f"Risk tier: {risk_score.get('overall', 'N/A')}  |  Freshness: {risk_score.get('freshness', 'N/A')}")
        why = risk_score.get("why")
        if why:
            print(f"Risk rationale: {why}")
        print("-" * 72)

    diff = patch_result.get("diff", "(no diff provided)")
    reasoning = patch_result.get("reasoning", "(no reasoning provided)")
    blast = patch_result.get("blast_radius", {}) or {}
    flags = patch_result.get("uncertainty_flags", []) or []

    level = blast.get("level", "N/A")
    services = blast.get("services_touched", []) or []
    files = blast.get("files_touched", []) or []
    notes = blast.get("notes", "")

    print("Patch summary:")
    print(f"  Blast radius level: {level}")
    if services:
        print(f"  Services touched: {', '.join(services)}")
    if files:
        print(f"  Files touched: {', '.join(files)}")
    if notes:
        print(f"  Notes: {notes}")

    if flags:
        print(f"\n⚠️  Uncertainty flags: {', '.join(str(x) for x in flags)}")

    print("\nAI reasoning (plain):")
    print(f"  {reasoning}")

    print("\nProposed diff:")
    print("-" * 72)
    print(diff)
    print("-" * 72)

    # The key: business trade-off prompt (human judgment)
    print("\nDecision check (human judgment required):")
    print("  Consider timing + business impact vs deployment risk.")
    print("  Example: peak hours, market open, major release window, on-call capacity.\n")

    approver = input("Enter your handle (e.g., @keefe): ").strip() or "@unknown"

    while True:
        decision = input("Type 'approve' to proceed, or 'reject' to block: ").strip().lower()

        if decision == "approve":
            rationale = input("1-line rationale (why approve now?): ").strip()
            if not rationale:
                print("Rationale cannot be empty. Try again.")
                continue
            return {"decision": "approved", "rationale": rationale, "approved_by": approver}

        if decision == "reject":
            rationale = input("1-line rationale (why reject / what to do next?): ").strip()
            if not rationale:
                print("Rationale cannot be empty. Try again.")
                continue
            return {"decision": "rejected", "rationale": rationale, "approved_by": approver}

        print("Invalid input. Type exactly 'approve' or 'reject'.")