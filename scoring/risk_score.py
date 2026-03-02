# Rules-based classifier: determines if an alert is HIGH or LOW risk
# Checks severity, error keywords, affected files, and shared infra
# Rules-based classifier: determines if an alert is HIGH or LOW risk.
# Checks severity, environment, error keywords, service name, and shared infrastructure.

HIGH_SEVERITY_LEVELS = {"HIGH", "CRITICAL"}

HIGH_RISK_SERVICE_KEYWORDS = {"auth", "database", "db", "payment", "billing", "postgres", "redis"}

HIGH_RISK_ERROR_KEYWORDS = {
    "auth", "database", "db", "payment", "billing",
    "connection pool", "postgres", "redis", "token", "credential"
}


def score_risk(alert, dependencies):
    """
    Classify an alert as HIGH or LOW risk using a rules-based approach.

    Args:
        alert (dict): The alert payload from alert.json.
        dependencies (dict): The dependencies dict from context/dependency_graph.py,
                             containing 'shared_infra', 'depends_on', 'depended_on_by'.

    Returns:
        dict: risk_result with keys:
              - 'level' (str): "HIGH" or "LOW"
              - 'reasons' (list of str): why this score was assigned
    """
    print("[RISK SCORE] Evaluating decision risk...")

    level = "LOW"
    reasons = []

    # Rule 1: Severity
    severity = alert.get("severity", "").upper()
    if severity in HIGH_SEVERITY_LEVELS:
        reasons.append(f"Alert severity is {severity}")
        level = "HIGH"

    # Rule 2: Production environment is always HIGH risk
    environment = alert.get("environment", "").lower()
    if environment == "production":
        reasons.append("Alert fired in production environment")
        level = "HIGH"

    # Rule 3: Service name contains high-risk keywords
    service = alert.get("service", "").lower()
    for keyword in HIGH_RISK_SERVICE_KEYWORDS:
        if keyword in service:
            reasons.append(f"Service name contains high-risk keyword: '{keyword}'")
            level = "HIGH"
            break

    # Rule 4: Error message references high-risk areas
    error = alert.get("error", "").lower()
    for keyword in HIGH_RISK_ERROR_KEYWORDS:
        if keyword in error:
            reasons.append(f"Error message references high-risk area: '{keyword}'")
            level = "HIGH"
            break

    # Rule 5: Touches shared infrastructure
    shared_infra = dependencies.get("shared_infra", [])
    if shared_infra:
        reasons.append(f"Touches shared infrastructure: {', '.join(shared_infra)}")
        level = "HIGH"

    # Rule 6: Depended on by multiple downstream services (blast radius)
    depended_on_by = dependencies.get("depended_on_by", [])
    if len(depended_on_by) >= 2:
        reasons.append(
            f"Service is a dependency for {len(depended_on_by)} downstream services: "
            f"{', '.join(depended_on_by)}"
        )
        level = "HIGH"

    if not reasons:
        reasons.append("No high-risk indicators found — isolated, low-severity, non-production alert")

    print(f"[RISK SCORE] Level: {level} | Reasons: {len(reasons)}")
    return {"level": level, "reasons": reasons}