# codex/patch.py
#
# Calls GPT-4 with a confirmed hypothesis and context bundle to generate a patch.
# Phase 2 changes:
#   - System prompt now explicitly requests a reasoning_chain (thinking trace)
#   - Each chain step documents the observation, decision made, and trade-off considered
#   - Prompt includes a compliance_check — AI self-assesses against injected policy flags
#   - Prompt is compliance-aware: freeze windows, DBA flags, approval requirements
#     injected by Gate 0 are visible to the model before it generates the diff
#   - blast_radius remains a plain string per data contract (adapter in main.py handles shape)

import os
import json
import openai
from dotenv import load_dotenv

load_dotenv()


def _build_system_prompt():
    return """You are a senior Site Reliability Engineer generating a minimal, targeted code fix for a confirmed production incident root cause.

You MUST respond with valid JSON only. No markdown, no code fences, no extra text — raw JSON only.

Return an object matching this exact schema:
{
  "diff": "<unified diff — use actual file paths from affected_files. Must be a realistic, minimal change. Do not refactor surrounding code.>",
  "explanation": "<plain English explanation of what the fix does and why it addresses the root cause. Written for an engineer who may not know this codebase. No jargon.>",
  "blast_radius": "<plain string describing what else this change could affect — name specific services, infrastructure, and behaviours. Reference the dependency graph you were given.>",
  "confidence": <float 0.0–1.0 — your confidence this fix resolves the incident>,
  "affected_services": ["<list of service names that may be affected — can be empty>"],
  "reasoning_chain": [
    {
      "step": <integer starting at 1>,
      "observation": "<specific fact you are acting on — reference the confirmed hypothesis, a commit hash, a constraint, or a dependency>",
      "decision": "<what you decided to change and why this is the minimal correct fix>",
      "trade_off": "<known risk, downside, or assumption in this decision — be honest about what could go wrong>"
    }
  ],
  "compliance_check": {
    "flags_reviewed": ["<list each compliance flag or restriction found in injected_context — empty list if none present>"],
    "assessment": "<plain English: does this patch respect all injected compliance restrictions? Explain your reasoning for each flag reviewed.>",
    "patch_is_compliant": <true | false — your judgment. Note: this is informational for the engineer, not a gate decision.>
  }
}

Rules:
1. The diff must be a realistic unified diff format. Use the exact file paths from affected_files.
2. Keep the diff minimal — fix the specific confirmed root cause only. Do not clean up unrelated code.
3. blast_radius must name specific services and infrastructure from the context provided, not generic statements like "may affect other services".
4. reasoning_chain must have a minimum of 3 steps and a maximum of 6.
5. Each reasoning_chain step must reference a specific piece of context — hypothesis description, commit hash, org constraint, dependency name. Generic statements are not acceptable.
6. compliance_check.flags_reviewed must list every compliance restriction found in injected_context. If injected_context is empty, return an empty list.
7. If compliance_check.patch_is_compliant is false, you must explain in assessment which restriction is violated and propose an alternative approach in the explanation field.
8. Do not invent constraints not present in the context. Do not hallucinate service names not in the dependency graph.
"""


def _build_user_prompt(hypothesis, context_bundle):
    alert = context_bundle.get("alert", {})
    git = context_bundle.get("git_history", {})
    deps = context_bundle.get("dependencies", {})
    org = context_bundle.get("org_context", {})

    recent_commits = git.get("recent_commits", [])
    commit_lines = "\n".join(
        f"  [{i}] hash={c.get('hash','?')} | author={c.get('author','?')} | "
        f"{c.get('days_ago','?')}d ago | \"{c.get('message','?')}\" | "
        f"files={c.get('files_changed', [])}"
        for i, c in enumerate(recent_commits[:5])
    )

    injected = org.get("injected_context", [])
    injected_block = (
        "\n".join(f"  - {entry}" for entry in injected)
        if injected else "  (none)"
    )

    prompt = f"""=== CONFIRMED ROOT CAUSE ===
Description: {hypothesis.get('description', 'unknown')}
Reasoning:   {hypothesis.get('reasoning', 'unknown')}
Confidence:  {hypothesis.get('confidence', 'unknown')}
Uncertainty flags: {'; '.join(hypothesis.get('uncertainty_flags', [])) or 'none'}

=== INCIDENT DETAILS ===
Alert ID:       {alert.get('id', 'unknown')}
Service:        {alert.get('service', 'unknown')}
Environment:    {alert.get('environment', 'unknown')}
Severity:       {alert.get('severity', 'unknown')}
Error:          {alert.get('error', 'unknown')}
Affected files: {', '.join(alert.get('affected_files', []))}

=== RECENT CHANGES TO AFFECTED FILES ===
(Use field path git_history.recent_commits[N] when citing in reasoning_chain)
{commit_lines if commit_lines else '  (no recent commits)'}

=== SERVICE DEPENDENCIES ===
depends_on:     {', '.join(deps.get('depends_on', []))}
depended_on_by: {', '.join(deps.get('depended_on_by', []))}
shared_infra:   {', '.join(deps.get('shared_infra', []))}

=== ORG CONSTRAINTS ===
known_constraints: {'; '.join(org.get('known_constraints', []))}
team_notes:        {'; '.join(org.get('team_notes', []))}

=== INJECTED CONTEXT (compliance restrictions + prior engineer feedback) ===
{injected_block}

Generate a minimal targeted patch for the confirmed root cause.
Before writing the diff, work through your reasoning_chain step by step.
Then perform your compliance_check against every entry in the injected context above.
"""
    return prompt


def generate_patch(hypothesis, context_bundle):
    """
    Call GPT-4 to generate a code patch for a confirmed incident hypothesis.

    Args:
        hypothesis (dict):      A confirmed hypothesis from diagnosis_result['hypotheses'].
                                Keys: id, description, confidence, reasoning, uncertainty_flags.
        context_bundle (dict):  Merged context from bundle.py.

    Returns:
        dict: patch_proposal matching the data contract in DATA_CONTRACTS.md §9.
              Keys: diff, explanation, blast_radius, confidence, affected_services,
                    reasoning_chain, compliance_check.

    Raises:
        RuntimeError: If the API call fails or the response cannot be parsed.
    """
    print("[PATCH] Sending confirmed hypothesis to GPT-4 for patch generation...")

    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    try:
        response = client.chat.completions.create(
            model="gpt-4.1",
            response_format={"type": "json_object"},
            temperature=0.2,
            messages=[
                {"role": "system", "content": _build_system_prompt()},
                {"role": "user",   "content": _build_user_prompt(hypothesis, context_bundle)},
            ],
        )
    except openai.APITimeoutError as e:
        raise RuntimeError(f"OpenAI API timed out during patch generation: {e}") from e
    except openai.APIError as e:
        raise RuntimeError(f"OpenAI API error during patch generation: {e}") from e

    raw = response.choices[0].message.content

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[PATCH] ERROR: Could not parse JSON. Raw output:\n{raw}")
        raise RuntimeError(f"Failed to parse JSON from patch response: {e}") from e

    # --- Validate required top-level fields ---
    required_fields = [
        "diff", "explanation", "blast_radius",
        "confidence", "affected_services",
        "reasoning_chain", "compliance_check",
    ]
    for field in required_fields:
        if field not in result:
            raise RuntimeError(f"Patch response missing required field: '{field}'")

    # --- Validate reasoning_chain ---
    chain = result.get("reasoning_chain", [])
    if len(chain) < 2:
        raise RuntimeError(
            f"reasoning_chain has {len(chain)} step(s) — minimum 2 required."
        )
    for i, step in enumerate(chain):
        for key in ("step", "observation", "decision", "trade_off"):
            if key not in step:
                raise RuntimeError(
                    f"reasoning_chain[{i}] missing required key: '{key}'"
                )

    # --- Validate compliance_check ---
    cc = result.get("compliance_check", {})
    for key in ("flags_reviewed", "assessment", "patch_is_compliant"):
        if key not in cc:
            raise RuntimeError(
                f"compliance_check missing required key: '{key}'"
            )

    # --- Warn if AI flagged non-compliance ---
    if not cc.get("patch_is_compliant", True):
        print(
            f"[PATCH] ⚠️  AI compliance self-check flagged a potential violation: "
            f"{cc.get('assessment', 'see compliance_check.assessment')}"
        )

    chain_len = len(chain)
    flags_count = len(cc.get("flags_reviewed", []))
    print(
        f"[PATCH] Patch generated. "
        f"Reasoning chain: {chain_len} steps. "
        f"Compliance flags reviewed: {flags_count}. "
        f"Self-assessed compliant: {cc.get('patch_is_compliant', 'unknown')}."
    )
    return result