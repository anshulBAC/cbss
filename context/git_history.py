# context/git_history.py
#
# Returns realistic commit history scoped to the alert's affected files and service.
# In production this would call the real git API or GitHub/GitLab.
# Stubs are parameterised — different alerts return different histories.

from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Commit templates keyed by file path fragment.
# Each entry is a list of plausible commits for that file.
# ---------------------------------------------------------------------------

_COMMIT_TEMPLATES = {
    "connection.py": [
        {
            "hash": "a1b2c3d",
            "author": "sarah.chen",
            "message": "fix: increase connection pool timeout from 30s to 60s",
            "days_ago": 2,
        },
        {
            "hash": "e4f5g6h",
            "author": "james.okafor",
            "message": "refactor: move session cleanup logic to background worker",
            "days_ago": 5,
        },
        {
            "hash": "i7j8k9l",
            "author": "priya.nair",
            "message": "chore: update db connection pool config comments",
            "days_ago": 8,
        },
    ],
    "session.py": [
        {
            "hash": "m1n2o3p",
            "author": "james.okafor",
            "message": "fix: handle session expiry edge case on concurrent logins",
            "days_ago": 3,
        },
        {
            "hash": "q4r5s6t",
            "author": "sarah.chen",
            "message": "feat: add session invalidation on password reset",
            "days_ago": 10,
        },
    ],
    "generator.py": [
        {
            "hash": "u7v8w9x",
            "author": "priya.nair",
            "message": "perf: batch report rows to reduce memory overhead",
            "days_ago": 4,
        },
        {
            "hash": "y1z2a3b",
            "author": "tom.west",
            "message": "fix: timeout guard on monthly report aggregation query",
            "days_ago": 9,
        },
    ],
    "cache_layer.py": [
        {
            "hash": "c4d5e6f",
            "author": "tom.west",
            "message": "chore: bump cache TTL from 5m to 15m for reporting queries",
            "days_ago": 1,
        },
        {
            "hash": "g7h8i9j",
            "author": "priya.nair",
            "message": "fix: invalidate stale cache entries on schema migration",
            "days_ago": 6,
        },
    ],
    "flags.py": [
        {
            "hash": "k1l2m3n",
            "author": "dev.ops",
            "message": "chore: deprecate legacy feature flag USE_OLD_NOTIFY_TRANSPORT",
            "days_ago": 14,
        },
    ],
}

# ---------------------------------------------------------------------------
# Review recency by service — how many days ago a human last reviewed the code.
# ---------------------------------------------------------------------------

_LAST_REVIEWED_BY_SERVICE = {
    "auth-service":          3,
    "reporting-service":    18,
    "notification-service":  7,
}

_DEFAULT_LAST_REVIEWED = 10


def get_git_history(affected_files, service=None):
    """
    Returns commit history scoped to the alert's affected files.

    Args:
        affected_files (list[str]): File paths from the alert payload.
        service (str | None):       Service name — used to look up review recency.

    Returns:
        dict:
            recent_commits        (list) — commits touching the affected files
            last_reviewed_days_ago (int) — days since a human last reviewed this code
    """
    matched_commits = []
    seen_hashes = set()

    for file_path in affected_files:
        # Match on the filename fragment (basename without directory prefix)
        file_name = file_path.split("/")[-1]
        for fragment, commits in _COMMIT_TEMPLATES.items():
            if fragment in file_name:
                for commit in commits:
                    if commit["hash"] not in seen_hashes:
                        # Attach the actual file path so callers see real paths
                        matched_commits.append({
                            **commit,
                            "files_changed": [file_path],
                        })
                        seen_hashes.add(commit["hash"])

    # Sort by recency (most recent first)
    matched_commits.sort(key=lambda c: c["days_ago"])

    last_reviewed = _LAST_REVIEWED_BY_SERVICE.get(
        service, _DEFAULT_LAST_REVIEWED
    )

    return {
        "recent_commits": matched_commits,
        "last_reviewed_days_ago": last_reviewed,
    }