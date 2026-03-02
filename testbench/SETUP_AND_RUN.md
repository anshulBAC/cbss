# Codex Guardian — Testbench Setup & Run Guide

All tests run without an OpenAI API key. External API calls are intercepted using Python's `unittest.mock`.

---

## Prerequisites

- Python 3.8 or higher
- `pip`

Check your Python version:
```bash
python --version
```

---

## Step 1 — Clone or navigate to the repo

```bash
cd /path/to/cbss
```

Confirm you are at the project root (you should see `main.py` and the `testbench/` folder):
```bash
ls
# main.py  requirements.txt  testbench/  context/  scoring/  codex/  gates/  ...
```

---

## Step 2 — Create a virtual environment

```bash
python -m venv venv
```

Activate it:

**macOS / Linux:**
```bash
source venv/bin/activate
```

**Windows:**
```bash
venv\Scripts\activate
```

Your prompt should now show `(venv)`.

---

## Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

This installs `openai` and `python-dotenv`. Both are needed for imports even though the tests mock the actual API calls.

---

## Step 4 — Set up the `.env` file (optional for tests)

The tests mock all OpenAI calls, so no real API key is needed to run the test suite.

However, if you plan to also run the live pipeline (`python main.py`), set up your key:
```bash
cp .env.example .env
```
Then open `.env` and fill in:
```
OPENAI_API_KEY=sk-...
```

---

## Step 5 — Run all tests

From the project root:
```bash
python testbench/run_all_tests.py
```

**Expected output:**
```
test_baseline_low_risk (test_scoring.TestRiskScore) ... ok
test_high_severity_triggers_high_risk (test_scoring.TestRiskScore) ... ok
...
----------------------------------------------------------------------
Ran 85 tests in 0.XXXs

OK
✓ All 85 tests passed.
```

Exit code `0` = all tests passed. Exit code `1` = failures present.

---

## Step 6 — Run individual test files

You can run any single test file directly from the project root:

```bash
# Scoring tests (risk, freshness, router)
python -m unittest testbench.test_scoring -v

# Context module tests (git history, dependency graph, org context, bundle)
python -m unittest testbench.test_context -v

# Gate UI tests (CLI input simulation)
python -m unittest testbench.test_gates -v

# Sandbox and audit logger tests
python -m unittest testbench.test_sandbox_audit -v

# Integration tests (mocked OpenAI + full flow)
python -m unittest testbench.test_integration -v
```

---

## Step 7 — Run a specific test class or method

```bash
# A single test class:
python -m unittest testbench.test_scoring.TestRiskScore -v

# A single test method:
python -m unittest testbench.test_scoring.TestRiskScore.test_production_environment_triggers_high_risk -v
```

---

## What each test file covers

| File | Module(s) tested | API key needed |
|------|-----------------|----------------|
| `test_scoring.py` | `scoring/risk_score.py`, `scoring/freshness_score.py`, `scoring/router.py` | No |
| `test_context.py` | `context/git_history.py`, `context/dependency_graph.py`, `context/org_context.py`, `context/bundle.py` | No |
| `test_gates.py` | `gates/gate1_ui.py`, `gates/gate2_ui.py` | No |
| `test_sandbox_audit.py` | `validation/sandbox.py`, `audit/logger.py` | No |
| `test_integration.py` | Full routing chain, `codex/diagnose.py`, `codex/patch.py`, gate flows, `main._adapt_patch_for_gate2` | No (mocked) |

---

## Running the live pipeline (requires API key)

Once your `.env` is configured:

```bash
# Alert 0 — HIGH risk, auth-service, production (triggers Gate 1 + Gate 2)
python main.py

# Alert 2 — LOW risk, notification-service, staging (auto-handled, no gates)
python main.py 2

# Alert 1 — MEDIUM risk, reporting-service, production (triggers gates)
python main.py 1
```

During a gate prompt, you will be asked to:
- **Gate 1:** Enter your handle, then type a hypothesis number (e.g. `1`) to confirm, or `r` to reject and provide a correction.
- **Gate 2:** Enter your handle, then type `approve` (with a one-line rationale) or `reject` (with a reason).

After each run, the full audit entry is appended to `audit_log.json` in the project root.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'openai'`**
→ Run `pip install -r requirements.txt` and confirm your virtual environment is active.

**`ModuleNotFoundError: No module named 'testbench'`**
→ Make sure you are running commands from the **project root** (where `main.py` lives), not from inside the `testbench/` folder.

**`ImportError` when running a test file directly**
→ Use `python -m unittest testbench.test_scoring -v` (with the module path), not `python testbench/test_scoring.py` directly.

**Tests fail with `StopIteration`**
→ A test's mocked `input()` call ran out of expected values. Check the `side_effect` list in that test for missing inputs.

**`audit_log.json` growing during tests**
→ It shouldn't — all audit logger tests mock `builtins.open`. If it does grow, a test is calling `log_decision` without a mock. Check for missing `patch` decorators in `test_integration.py`.
