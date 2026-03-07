# Combines risk_score and freshness_score to decide routing:
# LOW risk + fresh context → auto-handle
# HIGH risk or stale context → send to Gate 1
# Combines risk_score and freshness_score to decide routing:
# LOW risk + FRESH context → auto-handle (no human gates triggered)
# HIGH risk OR STALE context → escalate to Gate 1 → Gate 2


from rich.console import Console
_console = Console()


def route(risk_result, freshness_result):
    """
    Decide whether to auto-handle the incident or escalate to human gates.

    Args:
        risk_result (dict): Output from scoring/risk_score.py.
                            Keys: 'level' ("HIGH" or "LOW"), 'reasons' (list of str).
        freshness_result (dict): Output from scoring/freshness_score.py.
                                 Keys: 'score' ("FRESH" or "STALE"),
                                       'last_reviewed_days_ago' (int),
                                       'churn_rate' (str).

    Returns:
        dict: route_decision with keys:
              - 'route' (str): "auto-handle" or "escalate"
              - 'risk_level' (str): "HIGH" or "LOW"
              - 'freshness' (str): "FRESH" or "STALE"
              - 'explanation' (str): human-readable routing rationale
    """
    _console.print("[bold][ROUTER][/bold] Determining routing decision...")

    risk_level = risk_result.get("level", "LOW")
    freshness = freshness_result.get("score", "FRESH")

    if risk_level == "LOW" and freshness == "FRESH":
        route_decision = "auto-handle"
        explanation = (
            "Risk is LOW and context is FRESH — AI can resolve this incident "
            "automatically without human intervention."
        )
    else:
        route_decision = "escalate"
        escalation_reasons = []
        if risk_level == "HIGH":
            risk_reasons = risk_result.get("reasons", [])
            summary = risk_reasons[0] if risk_reasons else "high risk indicators present"
            escalation_reasons.append(f"risk is HIGH ({summary})")
        if freshness == "STALE":
            days = freshness_result.get("last_reviewed_days_ago", "?")
            escalation_reasons.append(
                f"context is STALE (last reviewed {days} days ago)"
            )
        explanation = (
            "Escalating to human gates because: "
            + " and ".join(escalation_reasons)
            + ". Gate 1 (diagnosis validation) and Gate 2 (patch approval) required."
        )

    route_color = "green" if route_decision == "auto-handle" else "yellow"
    _console.print(f"[ROUTER] Route: [{route_color}][bold]{route_decision.upper()}[/bold][/{route_color}]")
    _console.print(f"[ROUTER] [dim]{explanation}[/dim]")

    return {
        "route": route_decision,
        "risk_level": risk_level,
        "freshness": freshness,
        "explanation": explanation,
    }