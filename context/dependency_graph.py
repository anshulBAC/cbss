# context/dependency_graph.py
#
# Returns a dependency graph scoped to the alert's service.
# In production this would query a real service catalogue or CMDB.
# Stubs are parameterised — different services return different graphs.

# ---------------------------------------------------------------------------
# Dependency graph registry keyed by service name.
# ---------------------------------------------------------------------------

_DEPENDENCY_REGISTRY = {
    "auth-service": {
        "depends_on":     ["postgres-primary", "redis-cache", "user-service"],
        "depended_on_by": ["api-gateway", "billing-service", "admin-dashboard"],
        "shared_infra":   ["postgres-primary", "redis-cache"],
    },
    "reporting-service": {
        "depends_on":     ["postgres-replica", "redis-cache", "data-warehouse"],
        "depended_on_by": ["admin-dashboard", "finance-portal"],
        "shared_infra":   ["postgres-replica"],
    },
    "notification-service": {
        "depends_on":     ["config-service", "email-gateway"],
        "depended_on_by": [],
        "shared_infra":   [],
    },
}

_DEFAULT_GRAPH = {
    "depends_on":     [],
    "depended_on_by": [],
    "shared_infra":   [],
}


def get_dependency_graph(service):
    """
    Returns the dependency graph for the given service.

    Args:
        service (str): Service name from the alert payload.

    Returns:
        dict:
            service        (str)  — the service name
            depends_on     (list) — services this service calls
            depended_on_by (list) — services that call this service
            shared_infra   (list) — shared infrastructure components
    """
    graph = _DEPENDENCY_REGISTRY.get(service, _DEFAULT_GRAPH)

    return {
        "service":        service,
        "depends_on":     list(graph["depends_on"]),
        "depended_on_by": list(graph["depended_on_by"]),
        "shared_infra":   list(graph["shared_infra"]),
    }