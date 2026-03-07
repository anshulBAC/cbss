# audit/audit_viewer.py
"""
Audit viewer for Codex Guardian.

Reads audit_log.json (one JSON object per line) and renders a
human-readable timeline of pipeline decisions.

Usage (from project root):
    python audit/audit_viewer.py --all
    python audit/audit_viewer.py --id alert-001
    python audit/audit_viewer.py --all --log path/to/custom_audit.json
    python audit/audit_viewer.py --tail 5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────

DEFAULT_LOG_PATH = "audit_log.json"
WIDTH = 72


# ─────────────────────────────────────────────────────────────
# LOADING
# ─────────────────────────────────────────────────────────────

def load_entries(log_path: str = DEFAULT_LOG_PATH) -> List[Dict[str, Any]]:
    """
    Load all entries from audit_log.json.
    Returns an empty list if the file does not exist.
    Skips lines that are not valid JSON (with a warning).
    """
    if not os.path.exists(log_path):
        return []

    entries = []
    with open(log_path, "r") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"  [WARN] Skipping malformed line {line_num} in {log_path}",
                      file=sys.stderr)
    return entries


def find_by_id(entries: List[Dict[str, Any]], alert_id: str) -> List[Dict[str, Any]]:
    """Return all entries whose alert_id matches (case-insensitive)."""
    return [e for e in entries if e.get("alert_id", "").lower() == alert_id.lower()]


# ─────────────────────────────────────────────────────────────
# RENDERING
# ─────────────────────────────────────────────────────────────

def _section(title: str) -> None:
    print(f"\n  ── {title} {'─' * max(0, WIDTH - len(title) - 6)}")


def _field(label: str, value: Any, indent: int = 4) -> None:
    pad = " " * indent
    print(f"{pad}{label:<28} {value}")


def _render_list(items: List[str], indent: int = 6, empty_label: str = "none") -> None:
    if not items:
        print(f"{'  ' * (indent // 2)}{empty_label}")
        return
    for item in items:
        print(f"{' ' * indent}• {item}")


def _render_reasoning_chain(chain: List[Dict[str, Any]], chain_type: str = "diagnosis") -> None:
    """Render a reasoning chain in a compact readable format."""
    if not chain:
        print("      (none)")
        return
    step_keys = (
        ("observation", "inference", "evidence")
        if chain_type == "diagnosis"
        else ("observation", "decision", "trade_off")
    )
    for step in chain:
        n = step.get("step", "?")
        obs = step.get("observation", "")
        detail_key = step_keys[1]
        detail = step.get(detail_key, "")
        ev_key = step_keys[2]
        ev = step.get(ev_key, "")
        print(f"      Step {n}: {obs}")
        print(f"              → {detail}")
        if ev:
            print(f"              Evidence/Trade-off: {ev}")


def _render_clarification_log(log: List[Dict[str, str]], gate_label: str) -> None:
    if not log:
        return
    _section(f"{gate_label} Clarifications")
    for i, entry in enumerate(log, start=1):
        print(f"      Q{i}: {entry.get('question', '')}")
        print(f"      A{i}: {entry.get('answer', '')}")


def _render_compliance(flags: List[str], reasoning: List[Dict[str, Any]]) -> None:
    _section("Compliance")
    if not flags:
        print("      No compliance flags triggered.")
    else:
        print(f"      Flags ({len(flags)}):")
        _render_list(flags, indent=8)

    if reasoning:
        triggered = [r for r in reasoning if r.get("triggered")]
        not_triggered = [r for r in reasoning if not r.get("triggered")]
        if triggered:
            print(f"\n      Rules triggered ({len(triggered)}):")
            for r in triggered:
                rid  = r.get("rule_id", "?")
                name = r.get("rule_name", "")
                why  = r.get("why", "")
                print(f"        [{rid}] {name}")
                if why:
                    print(f"              {why}")
        if not_triggered:
            print(f"\n      Rules checked but not triggered: "
                  f"{', '.join(r.get('rule_id', '?') for r in not_triggered)}")


def render_entry(entry: Dict[str, Any], index: Optional[int] = None) -> None:
    """
    Render a single audit entry as a human-readable timeline block.
    """
    # ── Header ───────────────────────────────────────────────
    idx_str = f"  #{index}  " if index is not None else "  "
    outcome  = entry.get("outcome", "unknown").upper()
    alert_id = entry.get("alert_id", "unknown")
    ts       = entry.get("timestamp", "unknown")

    print("\n" + "═" * WIDTH)
    print(f"{idx_str}ALERT: {alert_id}   OUTCOME: {outcome}")
    print(f"  Timestamp: {ts}")
    print("═" * WIDTH)

    # ── Routing ──────────────────────────────────────────────
    _section("Routing")
    _field("Route taken:",      entry.get("route_taken", "N/A"))
    _field("Risk level:",       entry.get("risk_level", "N/A"))
    _field("Freshness:",        entry.get("freshness", "N/A"))

    # ── Compliance ───────────────────────────────────────────
    flags     = entry.get("compliance_flags", [])
    reasoning = entry.get("compliance_reasoning", [])
    if flags or reasoning:
        _render_compliance(flags, reasoning)
    else:
        _section("Compliance")
        print("      No compliance data recorded.")

    # ── Diagnosis ────────────────────────────────────────────
    _section("AI Diagnosis")
    _field("Hypothesis accepted:", entry.get("ai_hypothesis", "N/A"))
    diag_chain = entry.get("diagnosis_reasoning_chain", [])
    if diag_chain:
        print("      Reasoning chain:")
        _render_reasoning_chain(diag_chain, chain_type="diagnosis")

    # ── Gate 1 ───────────────────────────────────────────────
    _section("Gate 1 — Validate Diagnosis")
    _field("Engineer decision:",  entry.get("engineer_gate1_decision", "N/A"))
    _render_clarification_log(entry.get("gate1_clarifications", []), "Gate 1")

    # ── Patch ────────────────────────────────────────────────
    patch_chain = entry.get("patch_reasoning_chain", [])
    if patch_chain:
        _section("AI Patch Reasoning")
        _render_reasoning_chain(patch_chain, chain_type="patch")

    # ── Gate 2 ───────────────────────────────────────────────
    _section("Gate 2 — Approve Patch")
    _field("Engineer decision:",  entry.get("engineer_gate2_decision", "N/A"))
    _field("Approved by:",        entry.get("approved_by", "N/A"))
    second = entry.get("second_approver", "N/A")
    if second and second != "N/A":
        _field("Second approver:",  second)
    _render_clarification_log(entry.get("gate2_clarifications", []), "Gate 2")

    # ── Sandbox & Outcome ────────────────────────────────────
    _section("Sandbox & Outcome")
    _field("Sandbox result:",     entry.get("sandbox_result", "N/A"))
    _field("Final outcome:",      entry.get("outcome", "N/A"))
    _field("Notes:",              entry.get("notes", ""))

    print("─" * WIDTH)


# ─────────────────────────────────────────────────────────────
# SUMMARY TABLE
# ─────────────────────────────────────────────────────────────

def render_summary_table(entries: List[Dict[str, Any]]) -> None:
    """Print a compact summary table above the detailed entries."""
    if not entries:
        return
    print("\n" + "═" * WIDTH)
    print("  AUDIT SUMMARY")
    print("═" * WIDTH)
    header = f"  {'#':<4} {'Alert ID':<16} {'Route':<14} {'Risk':<6} {'Outcome':<20} {'Approved by'}"
    print(header)
    print("  " + "─" * (WIDTH - 2))
    for i, e in enumerate(entries, start=1):
        print(
            f"  {i:<4} "
            f"{e.get('alert_id','?'):<16} "
            f"{e.get('route_taken','?'):<14} "
            f"{e.get('risk_level','?'):<6} "
            f"{e.get('outcome','?'):<20} "
            f"{e.get('approved_by','?')}"
        )
    print("  " + "─" * (WIDTH - 2))
    print(f"  Total entries: {len(entries)}")


# ─────────────────────────────────────────────────────────────
# CLI ENTRY POINT
# ─────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    """
    Parse CLI args and render the audit log.

    Returns:
        0 on success
        1 if no log file found or no matching entries
    """
    parser = argparse.ArgumentParser(
        prog="audit_viewer",
        description="Codex Guardian — Audit Log Viewer",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Show all audit entries",
    )
    parser.add_argument(
        "--id", dest="alert_id", metavar="ALERT_ID",
        help="Show entries for a specific alert ID",
    )
    parser.add_argument(
        "--tail", type=int, metavar="N",
        help="Show the N most recent entries",
    )
    parser.add_argument(
        "--log", dest="log_path", default=DEFAULT_LOG_PATH,
        help=f"Path to audit log file (default: {DEFAULT_LOG_PATH})",
    )
    parser.add_argument(
        "--no-summary", action="store_true",
        help="Skip the summary table and show only detailed entries",
    )

    args = parser.parse_args(argv)

    # Must specify at least one display mode
    if not args.all and not args.alert_id and args.tail is None:
        parser.print_help()
        return 1

    # Load
    entries = load_entries(args.log_path)

    if not os.path.exists(args.log_path):
        print(f"[audit_viewer] Log file not found: {args.log_path}", file=sys.stderr)
        return 1

    if not entries:
        print(f"[audit_viewer] No entries found in {args.log_path}")
        return 0

    # Filter / slice
    if args.alert_id:
        entries = find_by_id(entries, args.alert_id)
        if not entries:
            print(f"[audit_viewer] No entries found for alert ID: {args.alert_id}",
                  file=sys.stderr)
            return 1

    if args.tail is not None:
        entries = entries[-args.tail:]

    # Render
    if not args.no_summary:
        render_summary_table(entries)

    for i, entry in enumerate(entries, start=1):
        render_entry(entry, index=i)

    return 0


if __name__ == "__main__":
    sys.exit(main())