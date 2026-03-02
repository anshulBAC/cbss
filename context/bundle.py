# This file combines all three context sources into one bundle for the pipeline.
# It is called by main.py at the very start of the pipeline.

from context.git_history import get_git_history
from context.dependency_graph import get_dependency_graph
from context.org_context import get_org_context

def build_context_bundle(alert):
    """
    Takes the alert dictionary loaded from alert.json.
    Calls all three context functions and merges everything into one bundle.
    Returns a single dictionary containing the alert plus all context.
    """

    print("  → Fetching git history...")
    git_history = get_git_history(alert["affected_files"])

    print("  → Fetching dependency graph...")
    dependencies = get_dependency_graph(alert["service"])

    print("  → Fetching org context...")
    org_context = get_org_context()

    print("  → Context bundle assembled.")

    return {
        "alert": alert,
        "git_history": git_history,
        "dependencies": dependencies,
        "org_context": org_context
    }