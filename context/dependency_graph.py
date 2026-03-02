def get_dependency_graph(service):
    """
    Takes a service name (e.g. "auth-service").
    Returns a dictionary showing what it depends on and what depends on it.
    """

    return {
        "service": "auth-service",
        "depends_on": ["postgres-primary", "redis-cache", "user-service"],
        "depended_on_by": ["api-gateway", "billing-service", "admin-dashboard"],
        "shared_infra": ["postgres-primary", "redis-cache"]
    }