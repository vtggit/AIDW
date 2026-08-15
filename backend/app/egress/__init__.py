"""Egress subsystem — outbound access to external source systems.

This package centralizes the controls that govern how the backend reaches
out to configured sources (OData services, databases, REST endpoints, file
stores).  The primary concern is **secret handling**: source credentials are
referenced by name (an environment-variable reference) and resolved at call
time, so that the secret value itself never appears in configuration, audit
records, or logs.

Exceptions
----------
``EgressError``
    Base exception for every failure raised by the egress subsystem.  Callers
    that need to catch any egress failure should catch this type.

``SecretRefInvalid``
    Raised when a secret reference does not conform to the required
    ``^[A-Z][A-Z0-9_]{2,63}$`` shape.  The message names the offending
    reference but never a resolved value.

``SecretUnavailable``
    Raised when a well-formed secret reference names an environment variable
    that is unset or empty.  The message names the variable but never a
    resolved value.
"""

__all__ = ["EgressError", "SecretRefInvalid", "SecretUnavailable"]


class EgressError(Exception):
    """Base exception for the egress subsystem."""


class SecretRefInvalid(EgressError):
    """A secret reference does not match the required pattern."""


class SecretUnavailable(EgressError):
    """A secret reference names an environment variable that is unset or empty."""
