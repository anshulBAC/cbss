# This file returns fake organisational context about the team and current constraints.
# In production, some of this would come from a ticketing system or internal wiki.

def get_org_context():
    """
    Takes no inputs.
    Returns a dictionary with team notes, known constraints, and any manually injected context.
    """

    return {
        "team_notes": [
            "Auth team is currently mid-sprint — avoid non-critical deployments where possible",
            "Connection pool issues have occurred twice in the last quarter during peak traffic",
            "On-call engineer for auth-service this week is james.okafor"
        ],
        "known_constraints": [
            "Connection pool max size is capped at 20 by infrastructure policy",
            "Any changes to auth-service require sign-off from the security team",
            "Production deployments are blocked on Fridays after 3pm"
        ],
        "last_updated": "2025-03-02T09:00:00Z",

        # ---------------------------------------------------------------
        # INJECTED CONTEXT — Edit this list manually before running a demo
        # Add any time-sensitive notes here, for example:
        #   "Team standup flagged a potential DB issue this morning"
        #   "Release freeze is in effect until Thursday"
        # Leave it empty if there's nothing to add.
        # ---------------------------------------------------------------
        "injected_context": []
    }