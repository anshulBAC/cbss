# Calls the OpenAI API with a confirmed hypothesis and context bundle to generate a minimal targeted code patch.

import os
import json
import openai
from dotenv import load_dotenv

load_dotenv()


def _build_system_prompt():
    """Return the system prompt that instructs GPT-4 to generate a patch and return JSON only."""
    return """You are a senior Site Reliability Engineer generating a minimal, targeted code fix for a confirmed production incident root cause.

You MUST respond with valid JSON only. No markdown, no code fences, no extra text — raw JSON only.

Return an object matching this exact schema:
{
  "diff": "<the proposed code change as a unified diff, e.g. --- a/src/db/connection.py\\n+++ b/src/db/connection.py\\n@@ ... @@\\n-old line\\n+new line>",
  "explanation": "<plain English explanation of what the fix does and why it addresses the root cause, written for an engineer who may not know this codebase>",
  "blast_radius": "<description of what else this change could affect — other services, dependent systems, or behaviours that may be impacted>",
  "confidence": <float between 0.0 and 1.0 indicating how confident you are this fix resolves the incident>,
  "affected_services": ["<list of service names that may be affected by this change>"]
}

Rules:
- The diff must be a realistic unified diff format (not pseudocode). Use actual file paths from the affected_files list.
- The explanation must be written in plain English — no jargon, assume a smart but non-expert reader.
- blast_radius must mention specific services and infrastructure from the context, not generic statements.
- affected_services must be a list of strings (can be empty list if change is fully isolated).
- Keep the diff minimal — fix the specific issue, do not refactor surrounding code.
"""


def _build_user_prompt(hypothesis, context_bundle):
    """Build the user prompt from the confirmed hypothesis and context bundle."""
    alert = context_bundle.get("alert", {})
    git = context_bundle.get("git_history", {})
    deps = context_bundle.get("dependencies", {})
    org = context_bundle.get("org_context", {})

    recent_commits = git.get("recent_commits", [])
    commit_lines = "\n".join(
        f"  - [{c.get('days_ago', '?')}d ago] {c.get('author', '?')}: {c.get('message', '?')} "
        f"(files: {', '.join(c.get('files_changed', []))})"
        for c in recent_commits[:5]
    )

    prompt = f"""=== CONFIRMED ROOT CAUSE ===
Description: {hypothesis.get('description', 'unknown')}
Reasoning: {hypothesis.get('reasoning', 'unknown')}
Confidence: {hypothesis.get('confidence', 'unknown')}

=== INCIDENT DETAILS ===
Alert ID: {alert.get('id', 'unknown')}
Service: {alert.get('service', 'unknown')}
Environment: {alert.get('environment', 'unknown')}
Severity: {alert.get('severity', 'unknown')}
Error: {alert.get('error', 'unknown')}
Affected files: {', '.join(alert.get('affected_files', []))}

=== RECENT CHANGES TO AFFECTED FILES ===
{commit_lines if commit_lines else '  (no recent commits)'}

=== SERVICE DEPENDENCIES ===
This service depends on: {', '.join(deps.get('depends_on', []))}
Depended on by: {', '.join(deps.get('depended_on_by', []))}
Shared infrastructure: {', '.join(deps.get('shared_infra', []))}

=== CONSTRAINTS TO RESPECT ===
Known constraints: {'; '.join(org.get('known_constraints', []))}
Team notes: {'; '.join(org.get('team_notes', []))}
Injected context: {'; '.join(org.get('injected_context', []))}

Generate a minimal targeted patch for the confirmed root cause in the required JSON format.
"""
    return prompt


def generate_patch(hypothesis, context_bundle):
    """
    Call the OpenAI API to generate a code patch for a confirmed incident hypothesis.

    Args:
        hypothesis (dict): A single confirmed hypothesis from diagnosis_result['hypotheses'],
                           containing 'id', 'description', 'confidence', 'reasoning', 'uncertainty_flags'.
        context_bundle (dict): Merged context from alert, git history, dependencies, and org context.

    Returns:
        dict: patch_proposal with keys 'diff', 'explanation', 'blast_radius',
              'confidence', and 'affected_services'.

    Raises:
        RuntimeError: If the API call fails or the response cannot be parsed.
    """
    print("[PATCH] Sending confirmed hypothesis to GPT-4 Turbo for patch generation...")

    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(hypothesis, context_bundle)

    try:
        response = client.chat.completions.create(
            model="gpt-4.1",
            response_format={"type": "json_object"},
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
        ],
            
        )
    except openai.APITimeoutError as e:
        print(f"[PATCH] ERROR: Request timed out — {e}")
        raise RuntimeError(f"OpenAI API timed out during patch generation: {e}") from e
    except openai.APIError as e:
        print(f"[PATCH] ERROR: API error — {e}")
        raise RuntimeError(f"OpenAI API error during patch generation: {e}") from e

    raw = response.choices[0].message.content

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[PATCH] ERROR: Could not parse JSON response. Raw output:\n{raw}")
        raise RuntimeError(f"Failed to parse JSON from OpenAI patch response: {e}") from e

    required_fields = ["diff", "explanation", "blast_radius", "confidence", "affected_services"]
    for field in required_fields:
        if field not in result:
            raise RuntimeError(f"OpenAI patch response missing required field: '{field}'")

    print("[PATCH] AI generated patch proposal.")
    return result
