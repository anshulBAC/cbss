def get_git_history(affected_files):
    """
    Takes a list of affected file names.
    Returns a dictionary with recent fake commits and how long ago the code was last reviewed.
    """

    return {
        "recent_commits": [
            {
                "hash": "a1b2c3d",
                "author": "sarah.chen",
                "message": "fix: increase connection pool timeout from 30s to 60s",
                "files_changed": ["src/db/connection.py"],
                "days_ago": 2
            },
            {
                "hash": "e4f5g6h",
                "author": "james.okafor",
                "message": "refactor: move session cleanup logic to background worker",
                "files_changed": ["src/auth/session.py", "src/db/connection.py"],
                "days_ago": 5
            },
            {
                "hash": "i7j8k9l",
                "author": "priya.nair",
                "message": "chore: update db connection pool config comments",
                "files_changed": ["src/db/connection.py"],
                "days_ago": 8
            }
        ],
        "last_reviewed_days_ago": 3
    }