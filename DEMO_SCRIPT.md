# Round 2 Demo Day Kit — Codex Guardian

## 0) What to optimize for (judging alignment)
Use this framing sentence early and often:

> **Codex Guardian helps teams resolve incidents faster without giving up human control at high-risk decision points.**

How this maps to judging:
- **Problem framing:** incident response is noisy, high-pressure, and expensive when mistakes happen.
- **Innovation:** AI assistance + explicit human gates (not full automation).
- **Technical depth:** risk/freshness scoring, routing, iterative diagnosis/patch loops, sandbox validation, audit logging.
- **Demo effectiveness:** show two paths (escalation and auto-handle) in one flow.
- **Impact:** faster triage, safer deployments, better accountability trail.

---

## 1) 3-minute presentation script (talk track)

### Slide 1 — Hook & Problem (0:00–0:30)
“Hi judges, we’re Team [Your Team], and this is **Codex Guardian**.

In incidents, engineers lose time stitching logs, context, and possible fixes under pressure. Most AI tools either generate noisy suggestions or push toward over-automation. Both increase risk in production.

So we asked: **How do we speed up incident response while keeping accountability human-owned?**”

### Slide 2 — Solution in one line (0:30–0:55)
“Codex Guardian is an AI-assisted incident response pipeline where:
**AI processes, humans decide.**

The system ingests alert context, scores risk and freshness, then routes incidents:
- low-risk + fresh context → auto-handle
- high-risk or stale context → escalate through human gates.”

### Slide 3 — Architecture & Technical Depth (0:55–1:35)
“Technically, our pipeline is:
**Alert → Context Bundle → Risk Score → Freshness Score → Router**.

If escalated:
- **Gate 1:** engineer validates AI diagnosis hypotheses.
- **Patch generation:** AI creates a minimal diff with blast-radius reasoning.
- **Gate 2:** engineer explicitly approves or rejects with rationale.
- **Sandbox validation:** patch is tested before outcome is finalized.
- **Audit logger:** every decision is recorded for traceability.

A key design choice is iterative feedback loops:
- Gate 1 rejection injects correction and re-diagnoses.
- Gate 2 rejection injects feedback and regenerates patch.
- Sandbox failures loop back with failure context.

This gives us speed without blind trust.”

### Slide 4 — Demo walkthrough (1:35–2:35)
“Quickly, we’ll show two live scenarios:

1) **High-risk production auth alert**
- routes to escalation
- Gate 1 validates diagnosis
- Gate 2 approves patch
- sandbox validates
- audit trail is written

2) **Low-risk staging notification alert**
- routes to auto-handle
- no gate friction

This demonstrates adaptive oversight: humans are only interrupted when their judgment materially changes risk.”

### Slide 5 — Impact & Close (2:35–3:00)
“Codex Guardian reduces cognitive overload and mean-time-to-clarity during incidents, while improving safety and accountability in production decisions.

Our next steps are stronger risk calibration with historical incident data, CI/CD integration, and richer governance analytics from audit logs.

**AI processes. Humans decide.** Thank you.”

---

## 2) Demo operator runbook (what to click/type)

### Pre-demo checklist (30–60s before presenting)
- Terminal 1 ready in repo root.
- `.env` configured with `OPENAI_API_KEY`.
- Font size increased.
- `input/alert.json` open in editor tab (quick visual reference).
- Optional backup: pre-recorded terminal output clip.

### Live commands

#### Scenario A: High-risk escalation path
```bash
python main.py 0
```
Narrate while running:
- “Notice severity HIGH in production on auth-service.”
- “Risk/freshness routing escalates.”
- “Gate 1 shows ranked hypotheses with uncertainty.”
- “Gate 2 requires explicit approve/reject rationale.”
- “Sandbox validates before finalizing.”
- “Audit log captures all decisions.”

#### Scenario B: Low-risk auto-handle path
```bash
python main.py 2
```
Narrate:
- “LOW + staging + fresh context.”
- “Auto-handle selected, no human interruption.”

#### Optional: show audit artifact
```bash
tail -n 80 audit_log.json
```
Narrate:
- “Structured records support postmortems, governance, and compliance.”

---

## 3) Slide ideas (5-slide structure)

1. **Problem & stakes**
   - Incident-response pain: time, ambiguity, blast radius risk.
2. **Solution thesis**
   - “AI processes. Humans decide.”
   - Routing logic graphic.
3. **System architecture**
   - Module diagram from repo: context, scoring, router, gates, sandbox, audit.
4. **Live demo outcomes**
   - Side-by-side table: high-risk escalated vs low-risk auto-handled.
5. **Impact + roadmap**
   - Current value, measurable KPIs, future improvements.

---

## 4) 2-minute Q&A prep (rapid-fire answers)

### Q: What is your core innovation?
“Our core innovation is **adaptive human oversight**. We don’t apply one level of friction to every incident. We route low-risk alerts automatically, while high-risk/uncertain cases require explicit human validation and approval with feedback loops.”

### Q: How is this better than a chatbot for ops?
“A chatbot gives suggestions. Codex Guardian is a **decision pipeline** with routing, gates, sandbox checks, and auditability. It operationalizes reliability and accountability instead of only generating text.”

### Q: What if AI is wrong?
“We assume it can be wrong. That’s why Gate 1 validates diagnosis, Gate 2 validates patch intent, and sandbox testing validates executable safety. Rejections and failures are fed back to improve subsequent attempts.”

### Q: How do you scale this in real teams?
“We can integrate with incident tooling and CI/CD, calibrate risk models per service criticality, and use audit logs to tune policies over time. The architecture is modular, so each stage can be improved independently.”

### Q: What metrics would you track in production?
- Mean time to triage / clarity
- % incidents auto-handled safely
- Gate rejection rates (quality signal)
- Sandbox failure rate before deployment
- Incident recurrence rate after accepted patches

---

## 5) Delivery tips for finals
- Keep one speaker for architecture + one for demo narration.
- Use a timer: hard-stop scripted section at 2:50.
- In demo, narrate decisions, not code lines.
- If a live step fails, switch to backup output immediately and continue the story.
- End with one sentence the judges remember:
  - “We built for the real world: fast AI assistance, with human accountability where risk is highest.”
