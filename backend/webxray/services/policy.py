from __future__ import annotations

from webxray.config import get_settings
from webxray.security.target_policy import EgressPolicy


def egress_policy() -> EgressPolicy:
    """The deployment's destination policy, shared by the API, worker, and test runner."""
    s = get_settings()
    return EgressPolicy.from_origins(s.egress_allowed_ports, s.allowed_private_origins)
