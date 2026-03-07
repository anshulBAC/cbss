# gates/gate2_ui.py
"""
Gate 2 UI (CLI): Engineer approves or rejects the proposed patch.

Design goals:
- Deliberate (~60-90 seconds)
- Make risk/impact visible
- Force explicit human accountability (typed approval + rationale)

Phase 4 additions:
- Reasoning chain display (read-only) before decision
- Compliance check summary display
- Diff depth options: default=collapsed (stats), type 'd' in loop to re-view
- Clarification layer: type '?' to ask GPT-4 a question about the patch
- clarification_log captured in output
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import openai
from dotenv import load_dotenv

load_dotenv()


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _diff_stats(diff: str) -> str:
    """Return a one-line stats summary of a unified diff."""
    lines = diff.split("\n")
    additions = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    deletions = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    files     = [l[4:] for l in lines if l.startswith("+++ ")]
    files_str = f"  Files: {', '.join(files)}" if files else ""
    return f"+{additions} / -{deletions} lines{('  ' + files_str) if files_str else ''}"


def _display_diff(diff: str, depth: str = "1") -> None:
    """
    Display the diff at the requested depth.

    depth "1" — stats only (collapsed, default)
    depth "2" — unified diff (normal)
    depth "3" — unified diff with line numbers (expanded)
    """
    print(f"\nProposed diff  [depth={depth}]  (type 'd' at decision prompt to change view):")
    print("-" * 72)

    if depth == "1":
        print(f"  {_diff_stats(diff)}")

    elif depth == "3":
        for i, line in enumerate(diff.split("\n"), start=1):
            print(f"  {i:>3}  {line}")

    else:  # "2" or anything unrecognised
        print(diff)

    print("-" * 72)


def _display_reasoning_chain(reasoning_chain: List[Dict[str, Any]]) -> None:
    """Print the AI's patch reasoning chain (read-only)."""
    if not reasoning_chain:
        return
    print("\nAI patch reasoning chain (read-only):")
    print("-" * 72)
    for step in reasoning_chain:
        n          = step.get("step", "?")
        obs        = step.get("observation", "")
        decision   = step.get("decision", "")
        trade_off  = step.get("trade_off", "")
        print(f"  Step {n}: {obs}")
        print(f"    -> Decision: {decision}")
        print(f"    Trade-off:   {trade_off}")
    print("-" * 72)


def _display_compliance_check(compliance_check: Dict[str, Any]) -> None:
    """Print the AI's self-compliance assessment."""
    if not compliance_check:
        return
    compliant  = compliance_check.get("patch_is_compliant", True)
    assessment = compliance_check.get("assessment", "")
    flags      = compliance_check.get("flags_reviewed", [])
    status     = "COMPLIANT" if compliant else "NON-COMPLIANT (review required)"
    print(f"\nAI compliance self-check: {status}")
    if flags:
        print(f"  Flags reviewed: {', '.join(flags)}")
    if assessment:
        print(f"  Assessment: {assessment}")


def _ask_clarification(question: str, patch_result: Dict[str, Any]) -> str:
    """
    Call GPT-4.1 to answer an engineer question about this patch.
    Returns the answer string, or a graceful error message on failure.
    """
    try:
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        context = json.dumps(
            {
                "diff":             patch_result.get("diff", ""),
                "reasoning":        patch_result.get("reasoning", ""),
                "blast_radius":     patch_result.get("blast_radius", {}),
                "reasoning_chain":  patch_result.get("reasoning_chain", []),
                "compliance_check": patch_result.get("compliance_check", {}),
            },
            indent=2,
        )
        response = client.chat.completions.create(
            model="gpt-4.1",
            max_tokens=300,
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are helping an on-call engineer evaluate a proposed code patch "
                        "for a production incident. Answer their question concisely (2-4 sentences). "
                        "Be specific and direct. Reference the patch context provided."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Patch context:\n{context}\n\n"
                        f"Engineer question: {question}"
                    ),
                },
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"(Clarification unavailable: {e})"


# ─────────────────────────────────────────────────────────────
# MAIN GATE
# ─────────────────────────────────────────────────────────────

def run_gate2(
    patch_result: Dict[str, Any],
    risk_score:   Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Input:
      patch_result dict (expected shape):
        {
          "diff":             str,
          "reasoning":        str,
          "blast_radius":     {"level": str, "services_touched": [str],
                               "files_touched": [str], "notes": str},
          "uncertainty_flags": [str],
          "reasoning_chain":  [{"step": int, "observation": str,
                                "decision": str, "trade_off": str}],
          "compliance_check": {"flags_reviewed": [str], "assessment": str,
                                "patch_is_compliant": bool}
        }

      risk_score (optional):
        {"overall": str, "freshness": str, "why": str}

    Output (gate2_result):
      {
        "decision":          "approved" | "rejected",
        "rationale":         str,
        "approved_by":       str,
        "clarification_log": [{"question": str, "answer": str}]
      }
    """
    print("\n" + "=" * 72)
    print("GATE 2 — APPROVE PATCH (human authority boundary)")
    print("=" * 72)

    clarification_log: List[Dict[str, str]] = []

    # Optional risk routing summary
    if risk_score:
        print(f"Risk tier: {risk_score.get('overall', 'N/A')}  |  "
              f"Freshness: {risk_score.get('freshness', 'N/A')}")
        why = risk_score.get("why")
        if why:
            print(f"Risk rationale: {why}")
        print("-" * 72)

    blast    = patch_result.get("blast_radius", {}) or {}
    flags    = patch_result.get("uncertainty_flags", []) or []
    diff     = patch_result.get("diff", "(no diff provided)")
    reasoning = patch_result.get("reasoning", "(no reasoning provided)")

    # Blast radius summary
    level    = blast.get("level", "N/A")
    services = blast.get("services_touched", []) or []
    files_t  = blast.get("files_touched", []) or []
    notes    = blast.get("notes", "")

    print("Patch summary:")
    print(f"  Blast radius level: {level}")
    if services:
        print(f"  Services touched: {', '.join(services)}")
    if files_t:
        print(f"  Files touched: {', '.join(files_t)}")
    if notes:
        print(f"  Notes: {notes}")

    if flags:
        print(f"\nUncertainty flags: {', '.join(str(x) for x in flags)}")

    print(f"\nAI reasoning (plain):\n  {reasoning}")

    # Phase 4: reasoning chain + compliance check
    _display_reasoning_chain(patch_result.get("reasoning_chain", []))
    _display_compliance_check(patch_result.get("compliance_check", {}))

    # Phase 4: diff — collapsed by default; engineer types 'd' in loop to re-view
    diff_depth = "1"
    _display_diff(diff, depth=diff_depth)

    print("\nDecision check (human judgment required):")
    print("  Consider timing + business impact vs deployment risk.")
    print("  Example: peak hours, market open, major release window, on-call capacity.\n")

    approver = input("Enter your handle (e.g., @keefe): ").strip() or "@unknown"

    while True:
        decision = input(
            "Type 'approve', 'reject', '?' to clarify, or 'd' to change diff view: "
        ).strip().lower()

        # Phase 4: diff depth toggle
        if decision == "d":
            depth_choice = input(
                "Diff view depth — [1] stats only  [2] unified diff  [3] line numbers: "
            ).strip() or "2"
            diff_depth = depth_choice if depth_choice in ("1", "2", "3") else "2"
            _display_diff(diff, depth=diff_depth)
            continue

        # Phase 4: clarification layer
        if decision == "?":
            question = input("Your question: ").strip()
            if question:
                print("\n[Clarification] Asking AI...")
                answer = _ask_clarification(question, patch_result)
                print(f"\n  Answer: {answer}\n")
                clarification_log.append({"question": question, "answer": answer})
            continue

        if decision == "approve":
            rationale = input("1-line rationale (why approve now?): ").strip()
            if not rationale:
                print("Rationale cannot be empty. Try again.")
                continue
            return {
                "decision":          "approved",
                "rationale":         rationale,
                "approved_by":       approver,
                "clarification_log": clarification_log,
            }

        if decision == "reject":
            rationale = input("1-line rationale (why reject / what to do next?): ").strip()
            if not rationale:
                print("Rationale cannot be empty. Try again.")
                continue
            return {
                "decision":          "rejected",
                "rationale":         rationale,
                "approved_by":       approver,
                "clarification_log": clarification_log,
            }

        print("Invalid input. Type 'approve', 'reject', '?', or 'd'.")