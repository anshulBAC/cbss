# Codex Guardian
AI-assisted incident response with human-in-the-loop oversight.

> **AI processes. Humans decide.**

## Overview

Codex Guardian is a pipeline that compresses production incidents into clarity. It uses GPT-4.1 to generate root cause hypotheses and patch proposals, but keeps human engineers in control at every escalation and deployment decision. A browser-based command center provides real-time visibility into every pipeline run, routing decision, and gate outcome.

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
server.py                   # Dashboard HTTP server (localhost:8080)
dashboard/
  index.html                # Browser-based command center (live audit, KPIs, pipeline view)
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
4. (Optional) Start the dashboard in a second terminal:
   ```
   python server.py
   # Open http://localhost:8080
   ```

## Dashboard

`python server.py` starts a lightweight HTTP server at `http://localhost:8080`. The dashboard auto-refreshes every 3 seconds and shows:

- **KPI strip** — total incidents, auto-resolved, escalated, human approvals, patch success rate
- **Pipeline diagram** — visual 9-stage flow with escalation vs. auto-handle fork
- **Routing Policy** — justification for why low-risk auto-resolution is safe
- **Latest Incident** — full journey visualization (ALERT → GATE 1 → GATE 2 → SANDBOX → OUTCOME)
- **Audit Log** — all historical runs with color-coded badges, most recent first

No build step required. Zero extra dependencies beyond the standard library.

## Sample Alerts

| Index | Service              | Severity | Environment | Route       |
|-------|----------------------|----------|-------------|-------------|
| 0     | auth-service         | HIGH     | production  | escalate    |
| 1     | reporting-service    | MEDIUM   | production  | escalate    |
| 2     | notification-service | LOW      | staging     | auto-handle |

## Human Gates

### Gate 1 — Validate Diagnosis (~30 seconds)
The AI presents 2–3 ranked hypotheses with confidence scores, reasoning, and uncertainty flags. The engineer either confirms one or rejects all and provides a correction. A rejection injects the engineer's context back into the AI's next diagnosis pass. Engineers can type `?` to ask the AI a follow-up clarification question.

### Gate 2 — Approve Fix (~60–90 seconds)
The AI presents a unified diff, blast radius summary (level, services/files touched), uncertainty flags, and plain-English reasoning. The engineer must type `approve` or `reject` with a one-line rationale. Approval requires explicit accountability. Rejection injects feedback into the next patch generation attempt.

## Auto-Handle Rationale

When the risk classifier returns `LOW` and context freshness is `FRESH`, the system resolves the incident without triggering human gates. This is safe because:

1. **Blast radius is bounded** — risk rules confirm no auth, payment, or cross-service impact
2. **Context is verified fresh** — recent human review and low commit churn reduce stale-context risk
3. **Failures are isolated** — a faulty low-risk patch cannot cascade to unrelated services by definition
4. **Nothing is silent** — every auto-resolution is logged to `audit_log.json` and visible in the dashboard; engineers can review or override at any time

## Audit Log

Every pipeline run appends a structured entry to `audit_log.json` containing: alert ID, route taken, risk level, context freshness, AI hypothesis, Gate 1 and Gate 2 decisions, approver handle, sandbox result, and outcome.

## Dependencies

- `openai` — GPT-4.1 for diagnosis and patch generation
- `python-dotenv` — loads `OPENAI_API_KEY` from `.env`
- `rich` — terminal formatting for CLI output
- `server.py` uses Python standard library only (no extra install needed)
