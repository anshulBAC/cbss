#!/usr/bin/env python3
"""
Codex Guardian — Demo Runner
Runs Scenario A (alert-004, index 3) then Scenario B (alert-003, index 2).

Usage:
    python demo_run.py           # run both scenarios
    python demo_run.py --clear   # wipe audit_log.json first, then run both
    python demo_run.py 3         # run only alert index 3 (Scenario A)
    python demo_run.py 2         # run only alert index 2 (Scenario B)
    python demo_run.py --clear 3 # clear log then run one scenario
"""

import argparse
import os
import sys

# ── Paths ────────────────────────────────────────────────────
ROOT      = os.path.dirname(os.path.abspath(__file__))
AUDIT_LOG = os.path.join(ROOT, "audit_log.json")

# Demo scenario order: A (index 3 — full escalation) → B (index 2 — auto-handle)
SCENARIOS = [
    {"index": 3, "label": "Scenario A", "alert": "alert-004",
     "desc": "auth-service | HIGH | production | 3 compliance flags | second approver"},
    {"index": 2, "label": "Scenario B", "alert": "alert-003",
     "desc": "notification-service | LOW | staging | auto-handle"},
]


def clear_audit_log():
    open(AUDIT_LOG, "w").close()
    print(f"\n  ✓  audit_log.json cleared\n")


def divider(label):
    bar = "─" * 60
    print(f"\n{bar}")
    print(f"  {label}")
    print(f"{bar}\n")


def run_scenario(scenario):
    divider(f"{scenario['label']}  ·  {scenario['alert']}  ·  {scenario['desc']}")
    # Import here so the module's own sys.path setup runs inside the project root
    os.chdir(ROOT)
    from main import run_pipeline
    run_pipeline(scenario["index"])


def main():
    parser = argparse.ArgumentParser(
        description="Codex Guardian demo runner — Scenario A (index 3) and Scenario B (index 2)"
    )
    parser.add_argument(
        "alert_index",
        nargs="?",
        type=int,
        choices=[2, 3],
        help="Run a single scenario by alert index (2 or 3). Omit to run both.",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear audit_log.json before running.",
    )
    args = parser.parse_args()

    print()
    print("  ⬡  Codex Guardian — Demo Runner")
    print("       Scenario A: python main.py 3  (alert-004, full escalation)")
    print("       Scenario B: python main.py 2  (alert-003, auto-handle)")

    if args.clear:
        clear_audit_log()

    if args.alert_index is not None:
        # Single scenario
        scenario = next(s for s in SCENARIOS if s["index"] == args.alert_index)
        run_scenario(scenario)
    else:
        # Both scenarios in recommended order
        for scenario in SCENARIOS:
            run_scenario(scenario)

    print()
    divider("Demo complete")
    print("  Audit log: python audit/audit_viewer.py --all")
    print("  Dashboard: http://localhost:8080\n")


if __name__ == "__main__":
    main()
