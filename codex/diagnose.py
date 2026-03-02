# Calls the OpenAI API with the full context bundle to generate 2-3 root cause hypotheses for a production incident.

import os
import json
import openai
from dotenv import load_dotenv

load_dotenv()


def _build_system_prompt():
    """Return the system prompt that instructs GPT-4 to act as an SRE and return JSON only."""
    return """You are a senior Site Reliability Engineer analysing a production incident.
Your job is to generate 2-3 plausible root cause hypotheses based on the incident context provided.

You MUST respond with valid JSON only. No markdown, no code fences, no extra text — raw JSON only.

Return an object matching this exact schema:
{
  "hypotheses": [
    {
      "id": <integer starting at 1>,
      "description": "<one-sentence root cause description>",
      "confidence": <float between 0.0 and 1.0>,
      "reasoning": "<2-3 sentences explaining why you think this is the cause, referencing specific context clues>",
      "uncertainty_flags": ["<reason this hypothesis might be wrong, e.g. 'limited git context', 'no metrics data'>"]
    }
  ],
  "context_freshness_warning": <true if the context appears stale or incomplete, false otherwise>
}

Rules:
- Generate exactly 2 or 3 hypotheses, ordered by confidence descending.
- Confidence scores must sum to no more than 2.0 across all hypotheses (they are not probabilities, they are individual confidence levels).
- uncertainty_flags must be a list of strings (can be empty list if no flags).
- context_freshness_warning is true if last_reviewed_days_ago is more than 14, or if recent commit data is missing.
"""


def _build_user_prompt(context_bundle):
    """Summarise the context bundle into a readable incident brief for the model."""
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

    prompt = f"""=== INCIDENT BRIEF ===
Alert ID: {alert.get('id', 'unknown')}
Timestamp: {alert.get('timestamp', 'unknown')}
Service: {alert.get('service', 'unknown')}
Environment: {alert.get('environment', 'unknown')}
Severity: {alert.get('severity', 'unknown')}
Error: {alert.get('error', 'unknown')}
Affected files: {', '.join(alert.get('affected_files', []))}

=== GIT HISTORY ===
Last human review: {git.get('last_reviewed_days_ago', 'unknown')} days ago
Recent commits:
{commit_lines if commit_lines else '  (no recent commits)'}

=== SERVICE DEPENDENCIES ===
This service depends on: {', '.join(deps.get('depends_on', []))}
Depended on by: {', '.join(deps.get('depended_on_by', []))}
Shared infrastructure: {', '.join(deps.get('shared_infra', []))}

=== ORG CONTEXT ===
Team notes: {'; '.join(org.get('team_notes', []))}
Known constraints: {'; '.join(org.get('known_constraints', []))}
Injected context: {'; '.join(org.get('injected_context', []))}

Based on this context, generate 2-3 root cause hypotheses in the required JSON format.
"""
    return prompt


def diagnose(context_bundle):
    """
    Call the OpenAI API to diagnose a production incident.

    Args:
        context_bundle (dict): Merged context from alert, git history, dependencies, and org context.

    Returns:
        dict: diagnosis_result with keys 'hypotheses' (list) and 'context_freshness_warning' (bool).

    Raises:
        RuntimeError: If the API call fails or the response cannot be parsed.
    """
    print("[DIAGNOSE] Sending incident context to GPT-4 Turbo for diagnosis...")

    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(context_bundle)

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
        print(f"[DIAGNOSE] ERROR: Request timed out — {e}")
        raise RuntimeError(f"OpenAI API timed out during diagnosis: {e}") from e
    except openai.APIError as e:
        print(f"[DIAGNOSE] ERROR: API error — {e}")
        raise RuntimeError(f"OpenAI API error during diagnosis: {e}") from e

    raw = response.choices[0].message.content

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[DIAGNOSE] ERROR: Could not parse JSON response. Raw output:\n{raw}")
        raise RuntimeError(f"Failed to parse JSON from OpenAI diagnosis response: {e}") from e

    try:
        _ = result["hypotheses"]
        _ = result["context_freshness_warning"]
    except KeyError as e:
        raise RuntimeError(f"OpenAI diagnosis response missing required field: {e}") from e

    count = len(result["hypotheses"])
    print(f"[DIAGNOSE] AI generated {count} hypothesis{'es' if count != 1 else ''}.")
    return result
