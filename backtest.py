#!/usr/bin/env python3
"""
Codex Guardian — Backtest Runner

Runs the pipeline non-interactively by monkey-patching gate UI functions
with auto-responders. All gate decisions are pre-scripted so the pipeline
completes without any human input.

Usage:
    python backtest.py              # runs all alerts (0, 1, 2, 3) sequentially
    python backtest.py 0 2          # runs alert indexes 0 and 2 only
    python backtest.py --list       # show available alerts

The dashboard will show live stage progression at http://localhost:8080
as each run executes. All results are appended to audit_log.json.
"""

import json
import sys
import time

# ── Auto-responders for Gate 1 and Gate 2 ─────────────────────────────────────

def _auto_gate1(diagnosis_result):
    """
    Simulate an engineer confirming the highest-confidence hypothesis at Gate 1.
    Prints what a real engineer would see, then returns a scripted confirmation.
    """
    hypotheses = diagnosis_result.get("hypotheses", [])
    if not hypotheses:
        print("  [BACKTEST] Gate 1: No hypotheses — auto-skipping.")
        return {"decision": "confirmed", "selected_hypothesis_id": "h1",
                "approved_by": "@backtest", "clarification_log": []}

    # Pick the hypothesis with the highest confidence
    best = max(hypotheses, key=lambda h: h.get("confidence", 0))
    hid  = best.get("id", hypotheses[0]["id"])

    print(f"\n  [BACKTEST] Gate 1 — auto-confirming hypothesis {hid} "
          f"(confidence: {best.get('confidence', '?')}%)")
    print(f"             {best.get('summary', best.get('description', ''))[:80]}")

    return {
        "decision":               "confirmed",
        "selected_hypothesis_id": hid,
        "approved_by":            "@backtest",
        "clarification_log":      [],
    }


def _auto_gate2(patch_proposal):
    """
    Simulate an engineer approving a patch at Gate 2.
    Prints a summary of what's being approved, then returns a scripted approval.
    """
    print(f"\n  [BACKTEST] Gate 2 — auto-approving patch")
    br = patch_proposal.get("blast_radius", {})
    if isinstance(br, dict):
        print(f"             Blast radius: {br.get('level','?')} — "
              f"{', '.join(br.get('services_touched', [])) or 'none'}")
    reasoning = patch_proposal.get("reasoning", patch_proposal.get("explanation", ""))
    if reasoning:
        print(f"             Reasoning: {str(reasoning)[:80]}")

    return {
        "decision":          "approved",
        "approved_by":       "@backtest",
        "rationale":         "Auto-approved by backtest runner.",
        "clarification_log": [],
    }


# ── Monkey-patch gate UIs before importing main ───────────────────────────────

import gates.gate1_ui as _g1
import gates.gate2_ui as _g2

_g1.run_gate1 = _auto_gate1
_g2.run_gate2 = _auto_gate2

# Now import main — it will use the patched functions
import main as _main

# Also patch second-approver prompt so it never blocks
def _auto_second_approver(gate2_result):
    primary = gate2_result.get("approved_by", "@backtest")
    second  = "@backtest2"
    print(f"\n  [BACKTEST] Second approver ({second}) — auto-approving.")
    return {"approved_by": second, "rationale": "Auto-approved by backtest runner.",
            "decision": "approved"}

_main._collect_second_approver = _auto_second_approver


# ── CLI ───────────────────────────────────────────────────────────────────────

def _load_alerts():
    with open("input/alert.json", "r") as f:
        return json.load(f)


def _list_alerts():
    alerts = _load_alerts()
    print("\n  Available alerts:")
    for i, a in enumerate(alerts):
        print(f"    [{i}] {a['id']}  {a['service']}  {a['severity']}  {a['environment']}")
        print(f"        {a['error'][:70]}")
    print()


def run_backtest(indexes):
    alerts = _load_alerts()
    total  = len(indexes)
    print(f"\n  ╔══════════════════════════════════════════════════════════════╗")
    print(f"  ║  Codex Guardian Backtest — {total} alert(s)                        ║")
    print(f"  ╚══════════════════════════════════════════════════════════════╝\n")

    for n, idx in enumerate(indexes, 1):
        if idx >= len(alerts):
            print(f"  [BACKTEST] Skipping index {idx} — out of range (max {len(alerts)-1})")
            continue

        a = alerts[idx]
        print(f"\n  ┌─ Run {n}/{total}: [{a['id']}] {a['service']} ({a['severity']}) ─")
        t0 = time.time()
        try:
            _main.run_pipeline(alert_index=idx)
        except Exception as e:
            print(f"\n  [BACKTEST] Run {n} failed: {e}")
        elapsed = time.time() - t0
        print(f"  └─ Completed in {elapsed:.1f}s\n")

        # Brief pause between runs so dashboard can catch the latest entry
        if n < total:
            time.sleep(1)

    print("  ✓ Backtest complete. Check http://localhost:8080 for results.\n")


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--list" in args:
        _list_alerts()
        sys.exit(0)

    if args:
        try:
            indexes = [int(a) for a in args]
        except ValueError:
            print(f"Usage: python backtest.py [alert_index ...] [--list]")
            sys.exit(1)
    else:
        # Default: run all alerts
        alerts  = _load_alerts()
        indexes = list(range(len(alerts)))

    run_backtest(indexes)
