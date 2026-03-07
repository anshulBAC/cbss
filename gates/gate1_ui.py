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
from rich.console import Console
from rich.panel import Panel
from rich import box

load_dotenv()

console = Console()


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
    steps_text = ""
    for step in reasoning_chain:
        n   = step.get("step", "?")
        obs = step.get("observation", "")
        inf = step.get("inference", "")
        ev  = step.get("evidence", "")
        steps_text += f"[bold]Step {n}:[/bold] {obs}\n"
        steps_text += f"  [dim]→ {inf}[/dim]\n"
        steps_text += f"  [dim]Evidence: {ev}[/dim]\n\n"
    console.print(Panel(steps_text.rstrip(), title="[bold]AI Reasoning Chain[/bold] [dim](read-only)[/dim]", box=box.ROUNDED))


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
    console.print()
    console.print(Panel(
        "[bold white]GATE 1 — VALIDATE DIAGNOSIS[/bold white]\n[dim]Target: ~30 seconds[/dim]",
        style="bold blue", box=box.HEAVY,
    ))

    clarification_log: List[Dict[str, str]] = []

    if diagnosis_result.get("context_freshness_warning"):
        console.print(Panel("⚠️  Context may be stale (recent human review is missing).", style="bold yellow"))

    hypotheses: List[Dict[str, Any]] = diagnosis_result.get("hypotheses", [])

    if not hypotheses:
        console.print(Panel("No hypotheses returned by AI. Escalate to manual investigation.", style="red"))
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

    console.print("\n[bold]AI Hypotheses:[/bold]\n")
    for idx, h in enumerate(hypotheses, start=1):
        hid       = h.get("id", idx)
        desc      = h.get("description", "(no description)")
        conf_raw  = h.get("confidence", 0.0)
        conf      = _format_percent(conf_raw)
        reasoning = h.get("reasoning", "(no reasoning provided)")
        flags     = h.get("uncertainty_flags", [])

        try:
            conf_val = float(conf_raw)
        except Exception:
            conf_val = 0.0
        conf_color = "green" if conf_val >= 0.70 else "yellow" if conf_val >= 0.40 else "red"

        flags_text = (
            f"[yellow]{', '.join(str(x) for x in flags)}[/yellow]"
            if flags else "[green]none[/green]"
        )
        content = (
            f"[bold]Hypothesis ID:[/bold] {hid}  |  "
            f"[bold]Confidence:[/bold] [{conf_color}]{conf}[/{conf_color}]\n\n"
            f"[bold]Summary:[/bold] {desc}\n\n"
            f"[bold]Reasoning:[/bold] {reasoning}\n\n"
            f"[bold]Uncertainty flags:[/bold] {flags_text}"
        )
        console.print(Panel(content, title=f"[bold]#{idx}[/bold]", box=box.ROUNDED))

    console.print("\n[bold]Your decision:[/bold]")
    console.print("  • Type a number [bold](e.g., 1)[/bold] to [green]CONFIRM[/green] a hypothesis.")
    console.print('  • Type [bold]"r"[/bold] to [red]REJECT ALL[/red] and provide a correction/context.')
    console.print('  • Type [bold]"?"[/bold] to ask a clarification question.\n')

    engineer = input("Enter your handle (e.g., @keefe): ").strip() or "@unknown"

    while True:
        choice = input(
            "Confirm hypothesis number, 'r' to reject, or '?' to clarify: "
        ).strip().lower()

        # Phase 4: clarification layer
        if choice == "?":
            question = input("Your question: ").strip()
            if question:
                console.print("\n[dim][Clarification] Asking AI...[/dim]")
                answer = _ask_clarification(question, diagnosis_result)
                console.print(Panel(f"[italic]{answer}[/italic]", title="[bold]AI Answer[/bold]", box=box.ROUNDED))
                clarification_log.append({"question": question, "answer": answer})
            continue

        if choice == "r":
            correction = input("Correction/context (1-2 sentences): ").strip()
            if not correction:
                console.print("[red]Correction cannot be empty. Try again.[/red]")
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

        console.print(f"[red]Invalid input. Enter 1-{len(hypotheses)}, 'r', or '?'.[/red]")