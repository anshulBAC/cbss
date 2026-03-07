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
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich import box

load_dotenv()

console = Console()


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
    if depth == "1":
        console.print(Panel(
            f"[dim]{_diff_stats(diff)}[/dim]",
            title=f"[bold]Proposed Diff[/bold] [dim]depth=1 · type 'd' to expand[/dim]",
            box=box.ROUNDED,
        ))
    elif depth == "3":
        numbered = "\n".join(f"{i:>3}  {line}" for i, line in enumerate(diff.split("\n"), start=1))
        syntax = Syntax(numbered, "diff", theme="monokai", line_numbers=False, word_wrap=True)
        console.print(Panel(syntax, title="[bold]Proposed Diff[/bold] [dim]depth=3 · line numbers[/dim]", box=box.ROUNDED))
    else:
        syntax = Syntax(diff, "diff", theme="monokai", line_numbers=False, word_wrap=True)
        console.print(Panel(syntax, title="[bold]Proposed Diff[/bold] [dim]depth=2 · unified[/dim]", box=box.ROUNDED))


def _display_reasoning_chain(reasoning_chain: List[Dict[str, Any]]) -> None:
    """Print the AI's patch reasoning chain (read-only)."""
    if not reasoning_chain:
        return
    steps_text = ""
    for step in reasoning_chain:
        n         = step.get("step", "?")
        obs       = step.get("observation", "")
        decision  = step.get("decision", "")
        trade_off = step.get("trade_off", "")
        steps_text += f"[bold]Step {n}:[/bold] {obs}\n"
        steps_text += f"  [dim]→ Decision: {decision}[/dim]\n"
        steps_text += f"  [dim]Trade-off: {trade_off}[/dim]\n\n"
    console.print(Panel(steps_text.rstrip(), title="[bold]AI Patch Reasoning Chain[/bold] [dim](read-only)[/dim]", box=box.ROUNDED))


def _display_compliance_check(compliance_check: Dict[str, Any]) -> None:
    """Print the AI's self-compliance assessment."""
    if not compliance_check:
        return
    compliant  = compliance_check.get("patch_is_compliant", True)
    assessment = compliance_check.get("assessment", "")
    flags      = compliance_check.get("flags_reviewed", [])
    status_color = "green" if compliant else "red"
    status_text  = "COMPLIANT ✓" if compliant else "NON-COMPLIANT ✗ (review required)"
    body = f"[{status_color}][bold]{status_text}[/bold][/{status_color}]"
    if flags:
        body += f"\n[bold]Flags reviewed:[/bold] {', '.join(flags)}"
    if assessment:
        body += f"\n[bold]Assessment:[/bold] {assessment}"
    console.print(Panel(body, title="[bold]AI Compliance Self-Check[/bold]", box=box.ROUNDED, border_style=status_color))


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
    console.print()
    console.print(Panel(
        "[bold white]GATE 2 — APPROVE PATCH[/bold white]\n[dim]Human authority boundary · Target: ~60–90 seconds[/dim]",
        style="bold magenta", box=box.HEAVY,
    ))

    clarification_log: List[Dict[str, str]] = []

    # Optional risk routing summary
    if risk_score:
        overall = risk_score.get("overall", "N/A")
        freshness = risk_score.get("freshness", "N/A")
        risk_color = "red" if overall == "HIGH" else "yellow" if overall == "MEDIUM" else "green"
        fresh_color = "green" if freshness == "OK" else "yellow"
        console.print(
            f"Risk tier: [{risk_color}]{overall}[/{risk_color}]  |  "
            f"Freshness: [{fresh_color}]{freshness}[/{fresh_color}]"
        )
        why = risk_score.get("why")
        if why:
            console.print(f"[dim]Risk rationale: {why}[/dim]")
        console.rule()

    blast    = patch_result.get("blast_radius", {}) or {}
    flags    = patch_result.get("uncertainty_flags", []) or []
    diff     = patch_result.get("diff", "(no diff provided)")
    reasoning = patch_result.get("reasoning", "(no reasoning provided)")

    # Blast radius panel — color by severity
    level    = blast.get("level", "N/A")
    services = blast.get("services_touched", []) or []
    files_t  = blast.get("files_touched", []) or []
    notes    = blast.get("notes", "")

    blast_color = "red" if level == "HIGH" else "yellow" if level == "MEDIUM" else "green"
    blast_body = f"[bold]Level:[/bold] [{blast_color}]{level}[/{blast_color}]"
    if services:
        blast_body += f"\n[bold]Services touched:[/bold] {', '.join(services)}"
    if files_t:
        blast_body += f"\n[bold]Files touched:[/bold] {', '.join(files_t)}"
    if notes:
        blast_body += f"\n[bold]Notes:[/bold] {notes}"
    console.print(Panel(blast_body, title="[bold]Blast Radius[/bold]", box=box.ROUNDED, border_style=blast_color))

    if flags:
        flags_body = "\n".join(f"  ⚠️  {f}" for f in flags)
        console.print(Panel(flags_body, title="[bold yellow]Uncertainty Flags[/bold yellow]", border_style="yellow", box=box.ROUNDED))

    console.print(Panel(f"[italic]{reasoning}[/italic]", title="[bold]AI Reasoning[/bold]", box=box.ROUNDED))

    # Phase 4: reasoning chain + compliance check
    _display_reasoning_chain(patch_result.get("reasoning_chain", []))
    _display_compliance_check(patch_result.get("compliance_check", {}))

    # Phase 4: diff — collapsed by default; engineer types 'd' in loop to re-view
    diff_depth = "1"
    _display_diff(diff, depth=diff_depth)

    console.print(Panel(
        "[bold]Decision check[/bold] — human judgment required:\n\n"
        "Consider timing + business impact vs deployment risk.\n"
        "[dim]Example: peak hours, market open, major release window, on-call capacity.[/dim]",
        style="bold white", box=box.ROUNDED,
    ))

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
                console.print("\n[dim][Clarification] Asking AI...[/dim]")
                answer = _ask_clarification(question, patch_result)
                console.print(Panel(f"[italic]{answer}[/italic]", title="[bold]AI Answer[/bold]", box=box.ROUNDED))
                clarification_log.append({"question": question, "answer": answer})
            continue

        if decision == "approve":
            rationale = input("1-line rationale (why approve now?): ").strip()
            if not rationale:
                console.print("[red]Rationale cannot be empty. Try again.[/red]")
                continue
            console.print(f"\n[bold green]✓ Patch APPROVED by {approver}[/bold green]")
            return {
                "decision":          "approved",
                "rationale":         rationale,
                "approved_by":       approver,
                "clarification_log": clarification_log,
            }

        if decision == "reject":
            rationale = input("1-line rationale (why reject / what to do next?): ").strip()
            if not rationale:
                console.print("[red]Rationale cannot be empty. Try again.[/red]")
                continue
            console.print(f"\n[bold red]✗ Patch REJECTED by {approver}[/bold red]")
            return {
                "decision":          "rejected",
                "rationale":         rationale,
                "approved_by":       approver,
                "clarification_log": clarification_log,
            }

        console.print("[red]Invalid input. Type 'approve', 'reject', '?', or 'd'.[/red]")