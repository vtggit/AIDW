"""BPMN Intermediate Representation (IR).

Provides frozen dataclasses for process definitions and a pure builder
function that validates all invariants before constructing an IR object.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class IRError(Exception):
    """Raised when process/step/flow data violates a BPMN invariant."""


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_STEP_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_JAVA_CLASS_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*\.)*[A-Za-z_][A-Za-z0-9_]*$")
_DELEGATE_EXPR_RE = re.compile(r"^\$\{.+\}$")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StepIR:
    """Immutable representation of a single process step."""

    step_key: str
    ordinal: int
    step_type: str
    name: str | None
    service_impl: str | None
    candidate_groups: list[str] | None
    form_key: str | None


@dataclass(frozen=True)
class FlowIR:
    """Immutable representation of a sequence flow between steps."""

    flow_key: str
    source_step: str
    target_step: str
    condition_expression: str | None
    is_default: bool


@dataclass(frozen=True)
class ProcessIR:
    """Immutable representation of an entire process definition."""

    process_key: str
    name: str | None
    version: int
    steps: tuple[StepIR, ...]
    flows: tuple[FlowIR, ...]


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_ir(
    process: dict[str, Any],
    steps: list[dict[str, Any]],
    flows: list[dict[str, Any]],
) -> ProcessIR:
    """Construct a ``ProcessIR`` from raw row dicts.

    Raises ``IRError`` if any invariant is violated.
    """

    # ---- Parse steps -------------------------------------------------------
    step_keys: set[str] = set()
    parsed_steps: list[StepIR] = []
    start_count = 0
    end_count = 0

    for row in steps:
        step_key = row["step_key"]

        # Invariant 5 — ordinal must be an integer (not bool)
        ordinal = row.get("ordinal")
        if not isinstance(ordinal, int) or isinstance(ordinal, bool):
            raise IRError(f"Step {step_key!r} has non-integer ordinal: {ordinal!r}")

        # Invariant 5 — step_key must match the allowed pattern
        if not _STEP_KEY_RE.match(step_key):
            raise IRError(f"Invalid step_key: {step_key!r}")

        # Invariant 6 — unique step_key within the process
        if step_key in step_keys:
            raise IRError(f"Duplicate step_key: {step_key!r}")
        step_keys.add(step_key)

        step_type = row["step_type"]

        # Invariants 1 & 2 — count start / end steps
        if step_type == "start":
            start_count += 1
        elif step_type == "end":
            end_count += 1

        parsed_steps.append(
            StepIR(
                step_key=step_key,
                ordinal=ordinal,
                step_type=step_type,
                name=row.get("name"),
                service_impl=row.get("service_impl"),
                candidate_groups=row.get("candidate_groups"),
                form_key=row.get("form_key"),
            )
        )

    # Invariant 1 — exactly one start step
    if start_count != 1:
        raise IRError(f"Expected exactly 1 start step, found {start_count}")

    # Invariant 2 — at least one end step
    if end_count < 1:
        raise IRError("At least one end step is required")

    # ---- Parse flows -------------------------------------------------------
    flow_keys: set[str] = set()
    parsed_flows: list[FlowIR] = []

    for row in flows:
        flow_key = row["flow_key"]

        # Invariant 6 — unique flow_key within the process
        if flow_key in flow_keys:
            raise IRError(f"Duplicate flow_key: {flow_key!r}")
        flow_keys.add(flow_key)

        source_step = row["source_step"]
        target_step = row["target_step"]

        # Invariant 3 — both endpoints must reference existing step_keys
        if source_step not in step_keys:
            raise IRError(
                f"Flow {flow_key!r} references unknown source_step: " f"{source_step!r}"
            )
        if target_step not in step_keys:
            raise IRError(
                f"Flow {flow_key!r} references unknown target_step: " f"{target_step!r}"
            )

        is_default = bool(row.get("is_default", False))

        parsed_flows.append(
            FlowIR(
                flow_key=flow_key,
                source_step=source_step,
                target_step=target_step,
                condition_expression=row.get("condition_expression"),
                is_default=is_default,
            )
        )

    # ---- Invariant 4 — gateway default flows -------------------------------
    step_type_map = {s.step_key: s.step_type for s in parsed_steps}

    outgoing_by_source: dict[str, list[FlowIR]] = {}
    for flow in parsed_flows:
        outgoing_by_source.setdefault(flow.source_step, []).append(flow)

    for sk, stype in step_type_map.items():
        if stype == "gateway":
            defaults = sum(1 for f in outgoing_by_source.get(sk, []) if f.is_default)
            if defaults != 1:
                raise IRError(
                    f"Gateway {sk!r} must have exactly one outgoing default "
                    f"flow, found {defaults}"
                )

    # ---- Invariant 7 — service step service_impl ---------------------------
    for step in parsed_steps:
        if step.step_type == "service":
            impl = step.service_impl
            if not isinstance(impl, str) or not impl:
                raise IRError(
                    f"Service step {step.step_key!r} has null/empty service_impl"
                )
            if not (_DELEGATE_EXPR_RE.match(impl) or _JAVA_CLASS_RE.match(impl)):
                raise IRError(
                    f"Service step {step.step_key!r} has invalid "
                    f"service_impl: {impl!r}"
                )

    # ---- Sort and return ---------------------------------------------------
    sorted_steps = tuple(sorted(parsed_steps, key=lambda s: (s.ordinal, s.step_key)))
    sorted_flows = tuple(
        sorted(parsed_flows, key=lambda f: (-f.is_default, f.flow_key))
    )

    return ProcessIR(
        process_key=process["process_key"],
        name=process.get("name"),
        version=process["version"],
        steps=sorted_steps,
        flows=sorted_flows,
    )
