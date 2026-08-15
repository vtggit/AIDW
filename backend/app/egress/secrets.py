"""Secret resolution for the egress subsystem.

Source credentials are never stored in the database or in configuration.
Instead, a source connection references a secret by the *name* of an
environment variable (a "secret reference").  At call time the reference is
validated and the variable's value is read from the process environment.

Security invariants
-------------------
* The resolved secret value is returned to the caller but is **never**
  included in any exception message and is **never** written to a log.
* Exception messages name only the offending reference (the variable name),
  which is not itself a secret.
* The environment is read at call time (not import time) so that tests and
  deployments can set or unset variables without re-importing this module.
"""

import os
import re

from app.egress import SecretRefInvalid, SecretUnavailable

# A secret reference is an environment-variable name: it must start with an
# uppercase letter and be followed by 2-63 uppercase letters, digits, or
# underscores (3-64 characters total).
_SECRET_REF_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")


def resolve_secret(secret_ref: str) -> str:
    """Resolve a secret reference to the value of the named environment variable.

    Args:
        secret_ref: The name of the environment variable holding the secret.
            Must match ``^[A-Z][A-Z0-9_]{2,63}$``.

    Returns:
        The current value of the named environment variable.

    Raises:
        SecretRefInvalid: If ``secret_ref`` does not match the required
            pattern.  The message names the offending reference but never a
            resolved value.
        SecretUnavailable: If the reference is well-formed but the named
            environment variable is unset or its value is the empty string.
            The message names the variable but never a resolved value.
    """
    if not isinstance(secret_ref, str) or not _SECRET_REF_PATTERN.match(secret_ref):
        # The reference itself is not a secret, so it is safe to name.  No
        # resolved value is available at this point, so nothing sensitive can
        # leak.
        raise SecretRefInvalid(
            f"Invalid secret reference: {secret_ref!r} does not match "
            "the required pattern ^[A-Z][A-Z0-9_]{2,63}$."
        )

    value = os.environ.get(secret_ref)
    if value is None or value == "":
        # The variable name is not a secret; the (absent) value is not
        # included in the message.
        raise SecretUnavailable(f"Secret reference {secret_ref!r} is unset or empty.")

    return value
