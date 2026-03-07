# gates/gate1_ui.py
"""
Gate 1 UI (CLI): Engineer validates the AI diagnosis.

Design goals:
- Fast (~30 seconds)
- Enough info for a genuine decision (not rubber-stamp)
- Engineer can confirm OR reject + inject correction/context

Phase 4 additions:
- Reasoning chain display (read-only) before decision
- Clarification layer: type '?' to ask GPT-4 a follow-up question
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

def _format_percent(confidence: float) -> str:
    try:
        return f"{float(confidence) * 100:.0f}%"
    except Exception:
        return "N/A"


def _display_reasoning_chain(reasoning_chain: List[Dict[str, Any]]) -> None:
    """Print the AI's step-by-step reasoning chain (read-only) before decision."""
    if not reasoning_chain:
        return
    print("\nAI reasoning chain (read-only):")
    print("-" * 72)
    for step in reasoning_chain:
        n   = step.get("step", "?")
        obs = step.get("observation", "")
        inf = step.get("inference", "")
        ev  = step.get("evidence", "")
        print(f"  Step {n}: {obs}")
        print(f"    -> {inf}")
        print(f"    Evidence field: {ev}")
    print("-" * 72)


def _ask_clarification(question: str, diagnosis_result: Dict[str, Any]) -> str:
    """
    Call GPT-4.1 to answer an engineer question about this diagnosis.
    Returns the answer string, or a graceful error message on failure.
    """
    try:
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        context = json.dumps(
            {
                "hypotheses":      diagnosis_result.get("hypotheses", []),
                "reasoning_chain": diagnosis_result.get("reasoning_chain", []),
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
                        "You are helping an on-call engineer understand an AI-generated "
                        "incident diagnosis. Answer their question concisely (2-4 sentences). "
                        "Be specific and direct. Reference the diagnosis context provided."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Diagnosis context:\n{context}\n\n"
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

def run_gate1(diagnosis_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Input: diagnosis_result dict (see data contracts):
      {
        "hypotheses": [
          { "id": int, "description": str, "confidence": float, "reasoning": str,
            "uncertainty_flags": [str] }
        ],
        "context_freshness_warning": bool,
        "reasoning_chain": [
          { "step": int, "observation": str, "inference": str, "evidence": str }
        ]
      }

    Output: gate1_result dict:
      {
        "decision":               "confirmed" | "rejected",
        "selected_hypothesis_id": int,
        "correction":             str,
        "approved_by":            str,
        "clarification_log":      [{"question": str, "answer": str}]
      }
    """
    print("\n" + "=" * 72)
    print("GATE 1 — VALIDATE DIAGNOSIS  (target: ~30 seconds)")
    print("=" * 72)

    clarification_log: List[Dict[str, str]] = []

    if diagnosis_result.get("context_freshness_warning"):
        print("Warning: Context may be stale (recent human review is missing).\n")

    hypotheses: List[Dict[str, Any]] = diagnosis_result.get("hypotheses", [])

    if not hypotheses:
        print("No hypotheses returned by AI. Escalate to manual investigation.")
        engineer = input("Enter your handle (e.g., @keefe): ").strip() or "@unknown"
        return {
            "decision":               "rejected",
            "selected_hypothesis_id": -1,
            "correction":             "No hypotheses returned. Manual triage required.",
            "approved_by":            engineer,
            "clarification_log":      clarification_log,
        }

    # Phase 4: show reasoning chain before hypotheses
    _display_reasoning_chain(diagnosis_result.get("reasoning_chain", []))

    print("AI hypotheses:\n")
    for idx, h in enumerate(hypotheses, start=1):
        hid       = h.get("id", idx)
        desc      = h.get("description", "(no description)")
        conf      = _format_percent(h.get("confidence", 0.0))
        reasoning = h.get("reasoning", "(no reasoning provided)")
        flags     = h.get("uncertainty_flags", [])

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
    print('  - Type "r" to REJECT ALL and provide a correction/context.')
    print('  - Type "?" to ask a clarification question.\n')

    engineer = input("Enter your handle (e.g., @keefe): ").strip() or "@unknown"

    while True:
        choice = input(
            "Confirm hypothesis number, 'r' to reject, or '?' to clarify: "
        ).strip().lower()

        # Phase 4: clarification layer
        if choice == "?":
            question = input("Your question: ").strip()
            if question:
                print("\n[Clarification] Asking AI...")
                answer = _ask_clarification(question, diagnosis_result)
                print(f"\n  Answer: {answer}\n")
                clarification_log.append({"question": question, "answer": answer})
            continue

        if choice == "r":
            correction = input("Correction/context (1-2 sentences): ").strip()
            if not correction:
                print("Correction cannot be empty. Try again.")
                continue
            return {
                "decision":               "rejected",
                "selected_hypothesis_id": -1,
                "correction":             correction,
                "approved_by":            engineer,
                "clarification_log":      clarification_log,
            }

        if choice.isdigit():
            n = int(choice)
            if 1 <= n <= len(hypotheses):
                selected_id = int(hypotheses[n - 1].get("id", n))
                return {
                    "decision":               "confirmed",
                    "selected_hypothesis_id": selected_id,
                    "correction":             "",
                    "approved_by":            engineer,
                    "clarification_log":      clarification_log,
                }

        print(f"Invalid input. Enter 1-{len(hypotheses)}, 'r', or '?'.")