# Codex Guardian
AI-assisted incident response with human-in-the-loop oversight.

> **AI processes. Humans decide.**

## Overview

Codex Guardian is a CLI pipeline that compresses production incidents into clarity. It uses GPT-4.1 to generate root cause hypotheses and patch proposals, but keeps human engineers in control at every escalation and deployment decision.

## Pipeline

```
Alert → Context Ingestion → Risk Score → Freshness Score → Router
  ↓ (escalate)                                              ↓ (auto-handle)
Gate 1: Validate Diagnosis                           Auto-resolved + audit log
  ↓ (confirmed)
Patch Generation
  ↓
Gate 2: Approve Fix
  ↓ (approved)
Sandbox Validation
  ↓
Deploy + Audit Log
```

**Routing logic:**
- `LOW` risk + `FRESH` context → auto-handled, no gates triggered
- `HIGH` risk or `STALE` context → escalated through Gate 1 and Gate 2

Engineers can reject at Gate 1 (inject a correction → AI re-diagnoses) or Gate 2 (inject feedback → AI regenerates the patch). Sandbox failures also loop back to re-diagnosis.

## Project Structure

```
main.py                     # Pipeline orchestrator
input/alert.json            # Sample alerts (HIGH / MEDIUM / LOW severity)
context/
  bundle.py                 # Merges all three context sources
  git_history.py            # Recent commits + last review date
  dependency_graph.py       # Service dependencies + shared infra
  org_context.py            # Team notes, constraints, injectable context
scoring/
  risk_score.py             # Rules-based HIGH/LOW risk classifier
  freshness_score.py        # FRESH/STALE context scorer
  router.py                 # Routes to auto-handle or escalate
codex/
  diagnose.py               # GPT-4.1 → 2–3 root cause hypotheses (JSON)
  patch.py                  # GPT-4.1 → minimal unified diff patch (JSON)
gates/
  gate1_ui.py               # CLI: engineer confirms/rejects AI diagnosis (~30s)
  gate2_ui.py               # CLI: engineer approves/rejects patch (~60–90s)
validation/
  sandbox.py                # Simulated sandbox test runner
audit/
  logger.py                 # Appends every decision to audit_log.json
```

## Setup

1. Copy `.env.example` to `.env` and add your OpenAI API key:
   ```
   OPENAI_API_KEY=sk-...
   ```
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run the pipeline:
   ```
   python main.py        # Alert 0 — HIGH risk, auth-service (triggers both gates)
   python main.py 2      # Alert 2 — LOW risk, notification-service (auto-handled)
   ```

## Sample Alerts

| Index | Service              | Severity | Environment | Route       |
|-------|----------------------|----------|-------------|-------------|
| 0     | auth-service         | HIGH     | production  | escalate    |
| 1     | reporting-service    | MEDIUM   | production  | escalate    |
| 2     | notification-service | LOW      | staging     | auto-handle |

## Human Gates

### Gate 1 — Validate Diagnosis (~30 seconds)
The AI presents 2–3 ranked hypotheses with confidence scores, reasoning, and uncertainty flags. The engineer either confirms one or rejects all and provides a correction. A rejection injects the engineer's context back into the AI's next diagnosis pass.

### Gate 2 — Approve Fix (~60–90 seconds)
The AI presents a unified diff, blast radius summary (level, services/files touched), uncertainty flags, and plain-English reasoning. The engineer must type `approve` or `reject` with a one-line rationale. Approval requires explicit accountability. Rejection injects feedback into the next patch generation attempt.

## Audit Log

Every pipeline run appends a structured entry to `audit_log.json` containing: alert ID, route taken, risk level, context freshness, AI hypothesis, Gate 1 and Gate 2 decisions, approver handle, sandbox result, and outcome.

## Dependencies

- `openai` — GPT-4.1 for diagnosis and patch generation
- `python-dotenv` — loads `OPENAI_API_KEY` from `.env`
