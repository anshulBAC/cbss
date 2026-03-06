# context/bundle.py
#
# Combines all three context sources into one bundle for the pipeline.
# Called by main.py at the very start of the pipeline.

from context.git_history import get_git_history
from context.dependency_graph import get_dependency_graph
from context.org_context import get_org_context


def build_context_bundle(alert):
    """
    Takes the alert dictionary loaded from alert.json.
    Calls all three context functions and merges everything into one bundle.
    Returns a single dictionary containing the alert plus all context.

    Args:
        alert (dict): Alert payload from input/alert.json.

    Returns:
        dict: context bundle with keys alert, git_history, dependencies, org_context.
    """
    print("  → Fetching git history...")
    git_history = get_git_history(
        affected_files=alert.get("affected_files", []),
        service=alert.get("service"),
    )

    print("  → Fetching dependency graph...")
    dependencies = get_dependency_graph(alert.get("service", ""))

    print("  → Fetching org context...")
    org_context = get_org_context()

    print("  → Context bundle assembled.")

    return {
        "alert":        alert,
        "git_history":  git_history,
        "dependencies": dependencies,
        "org_context":  org_context,
    }