# Combines risk_score and freshness_score to decide routing:
# LOW risk + fresh context → auto-handle
# HIGH risk or stale context → send to Gate 1
