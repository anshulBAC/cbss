# Demo Script — Codex Guardian (Competition)

## Goal (10 seconds)
"We're not building an AI that replaces engineers.
We're building an AI system that **amplifies human judgment** at the exact moments where mistakes are most costly."

Key line:
**AI processes. Humans decide.**

---

## Setup (5 seconds)
"We'll run two alerts: one high-risk production incident and one low-risk staging warning.
Watch how the system routes differently — and keep an eye on the dashboard updating live."

Before you start:
- Terminal 1: `python main.py` (the CLI pipeline)
- Terminal 2: `python server.py` (dashboard at http://localhost:8080)
- Browser: open the dashboard, position side-by-side with terminal if screen allows

---

## Demo Run 1 — High Risk Production Incident (2–3 minutes)

### 1) Alert arrives
"An alert fires from production. Without Codex Guardian, an engineer would spend 45–90 minutes reading logs and dashboards.
With Codex Guardian, we compress chaos into clarity."

Point to:
- Service = auth-service
- Severity = HIGH
- Environment = production

### 2) Risk + freshness routing
"The system evaluates risk and context freshness.
This alert is **high-risk** because it touches authentication and production."

Say:
"This triggers **two gates**: one lightweight to validate the diagnosis, one heavyweight to approve the fix."

### 3) Gate 1 (Lightweight) — Validate Diagnosis
"Gate 1 exists because if the diagnosis is wrong, everything downstream is wasted effort."

Callout:
- AI shows 2–3 hypotheses with confidence scores + reasoning chain
- Uncertainty flags surface what the AI doesn't know
- Engineer can type `?` to ask a follow-up clarification question

Now emphasize:
"The human is asked a simple question:
**Does this match anything you've seen before? Any context I should know?**"

Do:
- Confirm a hypothesis OR reject and inject correction

Say:
"This is fast, but it changes the AI's downstream reasoning."

### 4) Patch generation + sandbox mindset
"Now the AI proposes a patch and summarizes blast radius.
We assume the AI can be wrong — so we force explicit human judgment at the decision boundary."

### 5) Gate 2 (Heavyweight) — Approve Patch
"This is the authority boundary: AI cannot deploy."

Point to:
- diff (syntax-highlighted, collapsible depth)
- blast radius summary (level + services/files affected)
- uncertainty flags
- business trade-off prompt

Say:
"The engineer must explicitly approve or reject and type a rationale.
That keeps accountability human-owned."

Complete:
- Approve with a one-line rationale

### 6) Switch to dashboard (10 seconds)
"While that ran — here's the management view."

Point to:
- New entry appeared in the audit log table
- KPI strip updated: escalated count, human approvals, 100% sandbox pass rate
- Latest Incident card shows the full journey: ALERT → GATE 1 confirmed → GATE 2 approved → SANDBOX pass → DEPLOYED
- Every decision is timestamped and attributable

### 7) Wrap Run 1 (10 seconds)
"Result: AI did the heavy lifting — logs, hypotheses, diff drafting — but human judgment remained central at escalation and deployment."

---

## Demo Run 2 — Low Risk Staging Warning (45–60 seconds)

### 1) Alert arrives
"Now we run a low-risk staging warning."

Point to:
- Severity = LOW
- Environment = staging
- Single file touched

### 2) Routing
"The system classifies this as low risk + fresh context.
No gates. No interruption. Auto-handled."

**Point to the AUTO-HANDLE panel** (green box in CLI output):
- Risk Level: LOW ✓
- Context: FRESH ✓ (reviewed recently, low churn)
- Human Gates: NOT REQUIRED
- Rationale: blast radius is bounded, context is verified, nothing is silent

Say:
"This is how we keep friction low. Humans intervene only when their input changes outcomes."

Say:
"And critically — auto-resolutions are never silent. Every one is logged. Visible in the dashboard. Reviewable and overridable at any time."

### 3) Switch to dashboard (5 seconds)
Point to:
- Auto-resolved count ticks up
- Audit log shows AUTO-HANDLE route with no gate columns

---

## Q&A Talking Points

**"Why is auto-handling safe for low-risk incidents?"**
> Three reasons: the risk classifier confirms no blast radius to auth, billing, or cross-service dependencies. Context freshness is verified — recent human review and low commit churn. And nothing is silent — every auto-resolution is audited and engineers can review or override at any time. The dashboard makes that visible.

**"What stops the AI from making a bad low-risk patch?"**
> The sandbox still runs. If it fails, the incident re-enters the escalation path automatically. Auto-handle is not unconditional — it's conditional on both the risk classifier and sandbox validation.

**"How does Gate 1 prevent wasted work?"**
> If the AI diagnosis is wrong, the engineer rejects it and injects a one-line correction. That context is fed back into the next diagnosis pass — so the AI incorporates human knowledge before generating a patch. You don't patch the wrong problem.

**"Who is accountable for a deployed patch?"**
> The approver on record. Gate 2 requires the engineer to type `approve` and provide an explicit rationale. That's logged with their handle in the audit trail. The AI proposes; a human owns the decision.

**"Could this scale to a real SOC?"**
> Yes. The scoring, routing, and gate logic are all policy-configurable. The audit log format is append-only JSON — easy to ship to a SIEM. The dashboard can point to any audit_log.json. The CLI + browser split maps naturally to engineer workstations and ops screens.

---

## Closing (15 seconds)
"Most AI systems try to increase autonomy.
Codex Guardian increases leverage **without surrendering control**.

It reduces cognitive overload so senior engineers apply judgment where it matters most:
- Diagnosis validation
- Escalation decisions
- Deployment approval

**AI processes. Humans decide.**"
