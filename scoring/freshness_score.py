# Scores how stale the AI's context is for this incident
# Based on: days since last human review + churn rate of affected files
# Scores how stale the AI's context is for this incident.
# Based on: days since last human review + commit churn rate of affected files.

STALE_REVIEW_THRESHOLD_DAYS = 14   # More than this → context is likely stale
HIGH_CHURN_COMMIT_COUNT = 5         # 5+ recent commits = HIGH churn
MEDIUM_CHURN_COMMIT_COUNT = 2       # 2–4 recent commits = MEDIUM churn


def score_freshness(git_history):
    """
    Score how fresh the AI's context is for the affected files.

    Args:
        git_history (dict): The git_history dict from context/git_history.py, containing:
                            - 'last_reviewed_days_ago' (int)
                            - 'recent_commits' (list of commit dicts)

    Returns:
        dict: freshness_result with keys:
              - 'score' (str): "FRESH" or "STALE"
              - 'last_reviewed_days_ago' (int)
              - 'churn_rate' (str): "HIGH", "MEDIUM", or "LOW"
    """
    print("[FRESHNESS SCORE] Evaluating context freshness...")

    last_reviewed = git_history.get("last_reviewed_days_ago", 0)
    recent_commits = git_history.get("recent_commits", [])
    commit_count = len(recent_commits)

    # Determine churn rate from commit volume
    if commit_count >= HIGH_CHURN_COMMIT_COUNT:
        churn_rate = "HIGH"
    elif commit_count >= MEDIUM_CHURN_COMMIT_COUNT:
        churn_rate = "MEDIUM"
    else:
        churn_rate = "LOW"

    # STALE if: reviewed too long ago, OR high churn without a recent review
    stale_by_age = last_reviewed > STALE_REVIEW_THRESHOLD_DAYS
    stale_by_churn = churn_rate == "HIGH" and last_reviewed > 7

    if stale_by_age or stale_by_churn:
        score = "STALE"
        if stale_by_age:
            print(
                f"[FRESHNESS SCORE] STALE — last reviewed {last_reviewed} days ago "
                f"(threshold: {STALE_REVIEW_THRESHOLD_DAYS} days)"
            )
        else:
            print(
                f"[FRESHNESS SCORE] STALE — high churn ({commit_count} commits) "
                f"with no recent review ({last_reviewed} days ago)"
            )
    else:
        score = "FRESH"
        print(
            f"[FRESHNESS SCORE] FRESH — last reviewed {last_reviewed} days ago, "
            f"churn rate: {churn_rate}"
        )

    return {
        "score": score,
        "last_reviewed_days_ago": last_reviewed,
        "churn_rate": churn_rate,
    }