"""
World service = SKYVAULT as a background service (development plan Phase 11).

Important:
Jobs come in through an API, wait in a queue, run on workers and leave
their results in a store; every run is held to a Resource & Compute
Governance policy and stopped on its own when it runs away. Nothing here
is imported by the engine: the engine only knows a governor's methods.
"""
