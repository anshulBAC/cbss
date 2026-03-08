# Codex Guardian — Demo Script & Video Prompts

> **Total target runtime:** 4–6 minutes
> **Setup:** Run `./demo_record.sh` — it handles server start, browser open, and QuickTime recording automatically.

---

## One-Line Pitch (say this first, on camera)

> "We're not replacing engineers. We're giving them a command center that compresses a production incident into a decision in under 3 minutes — with every AI reasoning step on screen and every approval on record."

---

## Pre-Demo Checklist

```bash
# Terminal A — start recording script (handles everything):
./demo_record.sh

# That script will:
#   1. Kill any old server, start python3 server.py
#   2. Open http://localhost:8080 in your browser
#   3. Launch QuickTime screen recording
#   4. Print the exact commands to run
```

**Browser layout:** fullscreen the dashboard tab. Keep Terminal B visible on a split — 60% browser / 40% terminal works well.

---

## SCENE 1 — Dashboard Overview (~45 sec)

**What to do:** Slowly pan the dashboard. No commands yet.

**Narration:**

> "This is the Codex Guardian command center. Every incident that flows through our pipeline lands here in real time."

👉 Point to **KPI strip** (top cards)
> "At a glance — total incidents, auto-resolved without human touch, escalated for review, and patch success rate. All 100% on sandbox validation."

👉 Point to **Pipeline diagram**
> "This is the live pipeline. Right now it's showing the last completed run — DEPLOYED. When a new run starts, each stage lights up as the pipeline moves through it."

👉 Point to **Latest Incident card**
> "Every run produces a full incident record — the AI hypothesis, the reasoning chain, what the engineer confirmed at each gate. Fully auditable."

👉 Point to **Compliance panel**
> "This is new — a compliance evaluation panel. Every run checks policy rules automatically. POL-001 through POL-005. You can see which ones triggered and exactly why."

---

## SCENE 2 — Auto-Handle Run (LOW risk) (~45 sec)

**Terminal command:**
```bash
python3 backtest.py 2
```
*(alert-003 — notification-service, LOW severity, staging)*

**Narration (while it runs):**

> "Low risk alert from staging. Watch the pipeline badge in the dashboard — ALERT, CONTEXT, RISK SCORE, FRESHNESS, ROUTER... and straight to DEPLOY."

👉 Watch the **pipeline stage badge** cycle amber through each stage live

> "No gates. No interruption. The risk classifier confirmed bounded blast radius, context is fresh. The system resolves it automatically — but critically, it's not silent."

👉 Point to **Audit Log** row that appears
> "Every auto-resolution is logged here. Route taken, timestamp, approver. Engineers can review or challenge any of these at any time."

**Key line:**
> "This is how you keep friction low — humans intervene only when their input changes the outcome."

---

## SCENE 3 — HIGH Risk Escalation (manual run) (~2.5 min)

**Terminal command:**
```bash
python3 main.py 0
```
*(alert-001 — auth-service, HIGH severity, production)*

**Narration as pipeline starts:**
> "HIGH risk, production, auth-service. This one triggers both gates — because mistakes here can cascade."

👉 Watch dashboard badge: **ALERT → CONTEXT → RISK SCORE → FRESHNESS → ROUTER**
> "The router sees high risk — escalate path. Gate 1 fires."

---

### Gate 1 — Validate Diagnosis

*Terminal shows 2–3 AI hypotheses with confidence scores*

**Narration:**
> "Gate 1 is lightweight — under 30 seconds. The AI surfaces its top hypotheses. You see confidence scores, the full reasoning chain, and uncertainty flags — what it knows it doesn't know."

👉 Dashboard badge shows: **● LIVE: GATE 1 — AWAITING INPUT**

**What to type:**
```
Enter your handle: @yourname
# Read hypothesis 1 aloud briefly, then:
Enter choice: 1
```

**Narration:**
> "I'm confirming hypothesis 1. That decision gets injected into everything downstream — the AI now patches for the right problem."

---

### Gate 2 — Approve Patch

*Terminal shows unified diff, blast radius, reasoning*

**Narration:**
> "Gate 2 is the authority boundary. The AI cannot deploy. It can only propose."

👉 Dashboard badge shows: **● LIVE: GATE 2 — AWAITING INPUT**

**What to type:**
```
Enter your handle: @yourname
Type 'approve' or 'reject': approve
1-line rationale: Connection pool fix is scoped to src/db — blast radius confirmed minimal
```

**Narration:**
> "Explicit approval. Explicit rationale. That engineer owns this deployment on record."

---

### Sandbox + Deploy

*Terminal runs sandbox validation*

👉 Dashboard badge: **● LIVE: SANDBOX ⟳** → **● LIVE: DEPLOYING ⟳** → clears back to **● DEPLOYED**

**Narration:**
> "Sandbox passes. Deployed. Watch the dashboard update."

---

### Dashboard Walkthrough (after run)

👉 New row appears in **Audit Log**
> "Full run record — alert ID, route, risk, approver, sandbox result, compliance flags."

👉 Click the row to **expand detail drawer**
> "Click any row — you get the complete audit trail for that incident."

👉 **Latest Incident card** updates
> "Latest incident updated. Full journey from ALERT through to DEPLOYED."

👉 Click **Diagnosis Reasoning Chain** expander
> "Here's the AI's full reasoning — observation, inference, evidence — for every step it took to reach that hypothesis. Not a black box."

👉 Click **Patch Reasoning Chain**
> "Same for the patch — what it considered, the trade-offs it weighed."

👉 Point to **Compliance panel**
> "POL-001 triggered — auth-service patch required a second approver. That restriction was injected into the AI's context automatically before it generated the patch."

**Key line:**
> "Every AI decision is traceable. Every human decision is attributed. That's the audit trail a real ops team needs."

---

## SCENE 4 — Backtest (all alerts, live stage cycling) (~45 sec)

**Terminal command:**
```bash
python3 backtest.py
```
*(runs all 4 alerts sequentially, auto-approves all gates)*

**Narration:**
> "This is the backtest runner — it auto-approves all gates and runs the full pipeline for every alert. Watch the dashboard stage badge cycle through each run live."

👉 Keep an eye on the **pipeline diagram** — stages light up amber as each step fires, arrows illuminate as they complete

> "Four alerts processed. Mix of auto-handle and escalation paths. All results appended to the audit log in real time."

👉 Point to growing **Audit Log** table
> "Every run. Every decision. Append-only. Reviewable."

---

## SCENE 5 — Close (~20 sec)

**Narration:**
> "Most AI systems optimize for autonomy. Codex Guardian optimizes for leverage."
>
> "Senior engineers spend time on diagnosis validation, escalation decisions, and deployment approval — not reading 400 lines of logs."
>
> "AI processes. Humans decide."

---

## Q&A — Pocket Answers

| Question | Answer |
|----------|--------|
| **Why is auto-handle safe?** | Risk classifier confirms no auth/payment blast radius. Context freshness verified. Sandbox still runs. Nothing is silent — it's all in the audit log. |
| **Who's accountable for a deploy?** | The approver on record. Gate 2 requires `approve` + rationale — typed, attributed, logged. The AI proposes. A human owns it. |
| **How does Gate 1 prevent wasted work?** | Wrong diagnosis → wrong patch. Gate 1 lets the engineer inject a correction before any patch is generated. That context feeds back into GPT-4.1's next pass. |
| **Can this scale to a real SOC?** | Yes. Scoring and routing are policy-configurable. Audit log is append-only JSON — ships directly to a SIEM. Dashboard can point to any audit_log.json. |
| **What if the AI is wrong at Gate 2?** | Engineer rejects, types feedback. That's injected and GPT-4.1 regenerates. If sandbox fails, it loops back to re-diagnosis automatically. |

---

## Exact Commands Reference

```bash
# Start everything (server + browser + recording):
./demo_record.sh

# Scene 2 — auto-handle:
python3 backtest.py 2

# Scene 3 — manual HIGH risk run:
python3 main.py 0
#   Gate 1 handle:  @yourname
#   Gate 1 choice:  1
#   Gate 2 handle:  @yourname
#   Gate 2 approve: approve
#   Gate 2 reason:  Connection pool fix scoped to src/db — blast radius confirmed minimal

# Scene 4 — full backtest:
python3 backtest.py

# Stop recording — go back to demo_record.sh terminal, press ENTER
```
