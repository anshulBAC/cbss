# Codex Guardian — Enterprise Dashboard Design

**Date**: 2026-03-08
**Status**: Approved
**Scope**: Redesign of `dashboard/index.html` — single-page enterprise SaaS command center

---

## Design System

### Colors
| Token | Value | Usage |
|-------|-------|-------|
| `--bg` | `#03060F` | Page background |
| `--surface` | `#070D1A` | Sidebar, overlays |
| `--card` | `#0A1628` | Primary cards |
| `--card-2` | `#0D1E38` | Nested card surfaces |
| `--amber` | `#F59E0B` | Alerts, human decisions, active states |
| `--cyan` | `#06B6D4` | System states, AI outputs, info |
| `--green` | `#10B981` | Success, auto-resolved, pass |
| `--red` | `#F43F5E` | Danger, rejection, failure |

### Typography
- **Display**: `Bebas Neue` (Google Fonts) — KPI numbers, section titles
- **Data/Body**: `IBM Plex Mono` (Google Fonts) — all data, labels, table content

---

## Layout

```
┌─────────────────────────────────────────────────────────┐
│  APP BAR: Logo · Org · System Status · LIVE · Clock · User│
├──────┬──────────────────────────────────────────────────┤
│ SIDE │  § Overview — KPI Strip (5 metric cards)         │
│  BAR │  § Pipeline — Diagram + Metrics sidebar          │
│      │  § Incidents — Latest incident (expandable)      │
│ 56px │  § Compliance — Policy evaluation panel (NEW)    │
│      │  § Audit Log — Rich table w/ compliance badges   │
└──────┴──────────────────────────────────────────────────┘
```

---

## New Components

### Compliance Panel
Surfaces `compliance_reasoning` from the latest audit entry. Each policy rule
rendered as an expandable row: TRIGGERED (amber) or CLEAR (green). Injected
restrictions shown as highlighted callouts. Previously invisible in the UI.

### Expandable Incident Card
Three collapsible sections added to the Latest Incident card:
1. **Diagnosis Reasoning Chain** — numbered steps from `diagnosis_reasoning_chain`
2. **Patch Reasoning Chain** — numbered steps from `patch_reasoning_chain`
3. **Gate Clarifications** — Q&A pairs from `gate1_clarifications` + `gate2_clarifications`

### Enhanced Audit Table
New columns: `2nd Approver`, `Compliance` (pill showing flag count).
Click any row to expand a detail drawer with hypothesis + full compliance flags.

---

## Technical Constraints
- Zero build step — pure HTML/CSS/JS (same as current `server.py` architecture)
- Google Fonts via `@import` in `<style>`
- Vanilla JS only — no frameworks
- Serves from `dashboard/index.html` via `python server.py`
