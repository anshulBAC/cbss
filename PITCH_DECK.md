# Pitch Deck — Codex Guardian (Round 2 Demo Day)

> Format target: **3-minute presentation + 2-minute Q&A**

---

## Slide 1 — Title & Hook (0:00–0:20)
**Codex Guardian**  
AI-assisted incident response with human-in-the-loop oversight.

**Tagline:** *AI processes. Humans decide.*

### Speaker notes
- “Hi judges, we’re Team [Name]. In production incidents, speed matters—but so does control.”
- “Codex Guardian helps teams resolve incidents faster without handing deployment authority to AI.”

---

## Slide 2 — Problem Framing & Motivation (0:20–0:50)
### The problem
- Incident response is high-pressure and context-heavy.
- Engineers lose time reconstructing what happened from fragmented signals.
- Fully automated AI is risky for high-impact systems.

### Why this matters
- Slow triage increases downtime.
- Wrong fixes increase blast radius.
- Teams need both **velocity** and **accountability**.

### Speaker notes
- “Current tools force a bad tradeoff: either slow/manual or fast/risky.”
- “We designed for real ops behavior: assist aggressively, approve conservatively.”

---

## Slide 3 — Solution Design & Innovation (0:50–1:25)
### Core idea
Adaptive oversight pipeline:

`Alert → Context Bundle → Risk Score + Freshness Score → Router`

- **Low risk + fresh context** → auto-handle
- **High risk or stale context** → escalate to human gates

### Innovation
- Human gates are only triggered when they materially reduce risk.
- Explicit rejection/feedback loops improve next AI attempt.

### Speaker notes
- “The key is selective friction: minimal interruption for low-risk events, strict oversight for high-risk ones.”

---

## Slide 4 — Technical Depth (1:25–1:55)
### System modules
- `context/*`: combines git, dependency, and org context
- `scoring/*`: risk and freshness evaluation
- `router.py`: route to auto-handle or escalation
- `codex/*`: diagnosis hypotheses + patch generation
- `gates/*`: Gate 1 (diagnosis) and Gate 2 (patch approval)
- `validation/sandbox.py`: test patch safety
- `audit/logger.py`: immutable decision trail

### Robustness design
- Gate 1 reject → inject correction → re-diagnose
- Gate 2 reject → inject rationale → regenerate patch
- Sandbox fail → inject failure context → retry from diagnosis

---

## Slide 5 — Live Demo Plan (1:55–2:35)
### Scenario A: High-risk production incident
**Command:** `python main.py 0`

Expected flow:
1. High risk + production context detected
2. Escalation route selected
3. Gate 1 validates diagnosis
4. Gate 2 approves/rejects patch with rationale
5. Sandbox validation + audit log entry

### Scenario B: Low-risk staging warning
**Command:** `python main.py 2`

Expected flow:
1. Low risk + fresh context
2. Auto-handle path
3. No gate interruption

### Optional proof artifact
**Command:** `tail -n 80 audit_log.json`

---

## Slide 6 — Impact & Future Potential (2:35–2:55)
### Practical impact
- Reduces mean-time-to-clarity in incident triage
- Prevents unsafe auto-deploy behavior
- Increases governance and postmortem quality via audit trails

### Scale roadmap
- CI/CD and incident-platform integrations
- Policy tuning by service criticality
- Analytics from gate outcomes and sandbox failures

### KPI targets
- Triage time reduction
- Safe auto-handle rate
- Gate rejection quality signal
- Sandbox pre-deploy failure catch rate

---

## Slide 7 — Closing (2:55–3:00)
**“Codex Guardian gives teams the speed of AI with the accountability of human judgment.”**

**AI processes. Humans decide.**

---

# Q&A Backup (2 minutes)

## 1) What is technically novel?
Adaptive human-in-the-loop routing with structured escalation gates and feedback loops, instead of a single-pass chatbot-style assistant.

## 2) How do you ensure safety?
Three safeguards: diagnosis validation (Gate 1), explicit patch approval (Gate 2), and sandbox validation before final outcome.

## 3) What if AI is wrong repeatedly?
Engineer corrections and sandbox failures are injected as context into the next iteration, improving diagnosis and patch quality within the same run.

## 4) Why is this usable in production teams?
The architecture is modular, auditable, and policy-driven; each stage can be tuned independently to match team risk tolerance.

## 5) What would you build next?
Historical-incident-informed scoring, deeper CI/CD integration, and governance dashboards from audit-log telemetry.
