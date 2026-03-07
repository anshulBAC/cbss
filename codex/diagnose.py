# codex/diagnose.py
#
# Calls GPT-4 with the full context bundle to generate 2-3 root cause hypotheses.
# Phase 2 changes:
#   - System prompt now explicitly requests a reasoning_chain (thinking trace)
#   - Each chain step must reference a specific context_bundle field as evidence
#   - Prompt is aware of compliance restrictions injected by Gate 0
#   - Uncertainty handling is more structured — flags must explain *why*, not just exist
#   - context_freshness_warning logic is explicit, not left to model interpretation

import os
import json
import openai
from dotenv import load_dotenv

load_dotenv()


def _build_system_prompt():
    return """You are a senior Site Reliability Engineer diagnosing a production incident.
Your job is to generate 2-3 plausible root cause hypotheses based on the incident context provided.

You MUST respond with valid JSON only. No markdown, no code fences, no extra text — raw JSON only.

Return an object matching this exact schema:
{
  "hypotheses": [
    {
      "id": <integer starting at 1>,
      "description": "<one-sentence root cause — specific, not generic>",
      "confidence": <float 0.0–1.0>,
      "reasoning": "<2-3 sentences explaining why you believe this is the cause. Reference specific evidence from the context — commit hashes, author names, days_ago values, service names, constraint text. Do not make generic statements.>",
      "uncertainty_flags": [
        "<each flag must name a specific gap: e.g. 'No real-time connection pool metrics — cannot confirm pool saturation is currently active'. Empty list only if you have high confidence across all dimensions.>"
      ]
    }
  ],
  "context_freshness_warning": <true | false>,
  "reasoning_chain": [
    {
      "step": <integer starting at 1>,
      "observation": "<a specific fact extracted from the context — e.g. 'Commit a1b2c3d by sarah.chen 2 days ago changed POOL_TIMEOUT from 30s to 60s in src/db/connection.py'>",
      "inference": "<what this observation implies about the incident root cause>",
      "evidence": "<exact context_bundle field path this came from — e.g. 'git_history.recent_commits[0]', 'dependencies.shared_infra', 'org_context.known_constraints[1]', 'alert.error'>"
    }
  ]
}

Rules:
1. Generate exactly 2 or 3 hypotheses, ordered by confidence descending.
2. Confidence scores are individual assessments (0.0–1.0), not probabilities — they need not sum to 1.0.
3. uncertainty_flags must explain the *specific gap*, not just acknowledge uncertainty exists.
4. context_freshness_warning is true if last_reviewed_days_ago > 14 OR if recent_commits is empty.
5. reasoning_chain must have a minimum of 3 steps and a maximum of 7.
6. Every reasoning_chain step must cite a specific field path in the evidence field. Generic evidence like "the context" or "the alert" is not acceptable — be precise.
7. If injected_context contains compliance restrictions (e.g. freeze window, DBA sign-off), note them in the relevant hypothesis reasoning and uncertainty_flags where they affect your confidence.
8. The reasoning_chain should read as a transparent audit of your thinking — a junior engineer should be able to follow each step and verify it against the context you were given.
"""


def _build_user_prompt(context_bundle):
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
    injected_block = "\n".join(f"  - {entry}" for entry in injected) if injected else "  (none)"

    prompt = f"""=== INCIDENT BRIEF ===
Alert ID:       {alert.get('id', 'unknown')}
Timestamp:      {alert.get('timestamp', 'unknown')}
Service:        {alert.get('service', 'unknown')}
Environment:    {alert.get('environment', 'unknown')}
Severity:       {alert.get('severity', 'unknown')}
Error:          {alert.get('error', 'unknown')}
Affected files: {', '.join(alert.get('affected_files', []))}

=== GIT HISTORY ===
Last human review: {git.get('last_reviewed_days_ago', 'unknown')} days ago
Recent commits (use field path git_history.recent_commits[N] when citing):
{commit_lines if commit_lines else '  (no recent commits)'}

=== SERVICE DEPENDENCIES ===
depends_on:     {', '.join(deps.get('depends_on', []))}
depended_on_by: {', '.join(deps.get('depended_on_by', []))}
shared_infra:   {', '.join(deps.get('shared_infra', []))}

=== ORG CONTEXT ===
team_notes:         {'; '.join(org.get('team_notes', []))}
known_constraints:  {'; '.join(org.get('known_constraints', []))}

=== INJECTED CONTEXT (compliance restrictions + prior engineer corrections) ===
{injected_block}

Using the field paths shown above, generate 2-3 root cause hypotheses with a full reasoning_chain.
Every reasoning_chain step must cite a specific field path as evidence.
"""
    return prompt


def diagnose(context_bundle):
    """
    Call GPT-4 to diagnose a production incident.

    Args:
        context_bundle (dict): Merged context from bundle.py.

    Returns:
        dict: diagnosis_result matching the data contract in DATA_CONTRACTS.md §7.
              Keys: hypotheses, context_freshness_warning, reasoning_chain.

    Raises:
        RuntimeError: If the API call fails or the response cannot be parsed.
    """
    print("[DIAGNOSE] Sending incident context to GPT-4 for diagnosis...")

    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    try:
        response = client.chat.completions.create(
            model="gpt-4.1",
            response_format={"type": "json_object"},
            temperature=0.2,
            messages=[
                {"role": "system", "content": _build_system_prompt()},
                {"role": "user",   "content": _build_user_prompt(context_bundle)},
            ],
        )
    except openai.APITimeoutError as e:
        raise RuntimeError(f"OpenAI API timed out during diagnosis: {e}") from e
    except openai.APIError as e:
        raise RuntimeError(f"OpenAI API error during diagnosis: {e}") from e

    raw = response.choices[0].message.content

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[DIAGNOSE] ERROR: Could not parse JSON. Raw output:\n{raw}")
        raise RuntimeError(f"Failed to parse JSON from diagnosis response: {e}") from e

    # --- Validate required top-level fields ---
    for field in ("hypotheses", "context_freshness_warning", "reasoning_chain"):
        if field not in result:
            raise RuntimeError(f"Diagnosis response missing required field: '{field}'")

    # --- Validate reasoning_chain has minimum steps ---
    chain = result.get("reasoning_chain", [])
    if len(chain) < 2:
        raise RuntimeError(
            f"reasoning_chain has {len(chain)} step(s) — minimum 2 required. "
            "Check the system prompt constraints."
        )

    # --- Validate each chain step has required keys ---
    for i, step in enumerate(chain):
        for key in ("step", "observation", "inference", "evidence"):
            if key not in step:
                raise RuntimeError(
                    f"reasoning_chain[{i}] missing required key: '{key}'"
                )

    # --- Enforce context_freshness_warning based on actual data ---
    # Override model's judgment with deterministic check to ensure consistency
    git = context_bundle.get("git_history", {})
    last_reviewed = git.get("last_reviewed_days_ago", 0)
    commits = git.get("recent_commits", [])
    if last_reviewed > 14 or not commits:
        result["context_freshness_warning"] = True

    count = len(result["hypotheses"])
    chain_len = len(result["reasoning_chain"])
    print(
        f"[DIAGNOSE] {count} hypothesis{'es' if count != 1 else ''} generated. "
        f"Reasoning chain: {chain_len} steps."
    )
    return result