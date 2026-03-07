# Demo Script — Codex Guardian (Competition)

## Goal (10 seconds)
“We’re not building an AI that replaces engineers.  
We’re building an AI system that **amplifies human judgment** at the exact moments where mistakes are most costly.”

Key line:
**AI processes. Humans decide.**

---

## Setup (5 seconds)
“We’ll run two alerts: one high-risk production incident and one low-risk staging warning.  
Watch how the system routes differently.”

---

## Demo Run 1 — High Risk Production Incident (2–3 minutes)

### 1) Alert arrives
“An alert fires from production. Without Sentinel, an engineer would spend 45–90 minutes reading logs and dashboards.  
With Sentinel, we compress chaos into clarity.”

Point to:
- Service = auth-service
- Severity = HIGH
- Environment = production

### 2) Risk + freshness routing
“Sentinel evaluates risk and context freshness.  
This alert is **high-risk** because it touches authentication and production.”

Say:
“This triggers **two gates**: one lightweight, one heavyweight.”

### 3) Gate 1 (Lightweight) — Validate Diagnosis
“Gate 1 exists because if the diagnosis is wrong, everything downstream is wasted effort.”

Callout:
- AI shows 2–3 hypotheses
- confidence + reasoning + uncertainty flags

Now emphasize:
“The human is asked a simple question:  
**Does this match anything you’ve seen before? Any context I should know?**”

Do:
- Confirm a hypothesis OR reject and inject correction

Say:
“This is fast, but it changes the AI’s downstream reasoning.”

### 4) Patch generation + sandbox mindset
“Now the AI proposes a patch and summarizes blast radius.  
We assume the AI can be wrong — so we force explicit human judgment at the decision boundary.”

### 5) Gate 2 (Heavyweight) — Approve Patch
“This is the authority boundary: AI cannot deploy.”

Point to:
- diff
- blast radius summary
- uncertainty flags
- business trade-off prompt

Say:
“The engineer must explicitly approve or reject and type a rationale.  
That keeps accountability human-owned.”

Complete:
- Approve with a one-line rationale

### 6) Wrap Run 1 (10 seconds)
“Result: AI did the heavy lifting — logs, hypotheses, diff drafting — but human judgment remained central at escalation and deployment.”

---

## Demo Run 2 — Low Risk Staging Warning (45–60 seconds)

### 1) Alert arrives
“Now we run a low-risk staging warning.”

Point to:
- Severity = LOW
- Environment = staging
- Single file touched

### 2) Routing
“Sentinel classifies this as low risk + fresh context.
No gates. No interruption. Auto-handled.”

Point to the AUTO-HANDLE panel on screen:
- Risk classifier confirmed: no auth, payment, or cross-service blast radius
- Context freshness verified: reviewed recently, low churn
- Full audit trail written — engineers can review or override at any time

Say:
“This is how we keep friction low. Humans intervene only when their input changes outcomes.
But auto-handle is never blind — every resolution is logged, justified, and reviewable.”

---

## Closing (15 seconds)
“Most AI systems try to increase autonomy.  
Codex Guardian increases leverage **without surrendering control**.

It reduces cognitive overload so senior engineers apply judgment where it matters most:
- Diagnosis validation
- Escalation decisions
- Deployment approval

**AI processes. Humans decide.**”