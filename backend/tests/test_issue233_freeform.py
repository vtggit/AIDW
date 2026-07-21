"""Proving test for Issue #233 — layout reads the real ProcessIR contract.

Covers:
- Standard process with start, user_task, service task, exclusive gateway,
  default/conditional flows, and two end nodes.
- ShapeBox count == step count; EdgeRoute count == flow count.
- All coordinates are ints; no duplicate (x, y).
- Byte-identical output on repeated calls and shuffled inputs.
- Disconnected-node resilience (in-degree-0 step other than start).
"""

from __future__ import annotations

import itertools

from app.bpmn.ir import FlowIR, ProcessIR, StepIR, build_ir
from app.bpmn.layout import EdgeRoute, LayoutModel, ShapeBox, layout

# ---------------------------------------------------------------------------
# Helper — canonical process definition used by multiple assertions
# ---------------------------------------------------------------------------


def _make_canonical_process() -> dict:
    """Return the raw dicts that ``build_ir`` expects for a standard process.

    Structure::

        start -> user_task -> service_task -> gateway
                                              ├── (default) -> end_a
                                              └── (condition) -> end_b
    """
    return {
        "process_key": "proc_canonical",
        "name": "Canonical Process",
        "version": 1,
    }


def _make_canonical_steps() -> list[dict]:
    return [
        {"step_key": "start", "ordinal": 0, "step_type": "start", "name": "Start"},
        {
            "step_key": "user_task",
            "ordinal": 1,
            "step_type": "user_task",
            "name": "Review Request",
        },
        {
            "step_key": "service_task",
            "ordinal": 2,
            "step_type": "service",
            "name": "Validate Data",
            "service_impl": "${validate(data)}",
        },
        {
            "step_key": "gateway",
            "ordinal": 3,
            "step_type": "gateway",
            "name": "Decision Gateway",
        },
        {"step_key": "end_a", "ordinal": 4, "step_type": "end", "name": "End A"},
        {"step_key": "end_b", "ordinal": 5, "step_type": "end", "name": "End B"},
    ]


def _make_canonical_flows() -> list[dict]:
    return [
        {
            "flow_key": "f1",
            "source_step": "start",
            "target_step": "user_task",
            "condition_expression": None,
            "is_default": False,
        },
        {
            "flow_key": "f2",
            "source_step": "user_task",
            "target_step": "service_task",
            "condition_expression": None,
            "is_default": False,
        },
        {
            "flow_key": "f3",
            "source_step": "service_task",
            "target_step": "gateway",
            "condition_expression": None,
            "is_default": False,
        },
        # Default outgoing from gateway -> end_a
        {
            "flow_key": "f4",
            "source_step": "gateway",
            "target_step": "end_a",
            "condition_expression": None,
            "is_default": True,
        },
        # Conditional outgoing from gateway -> end_b
        {
            "flow_key": "f5",
            "source_step": "gateway",
            "target_step": "end_b",
            "condition_expression": "${approved == false}",
            "is_default": False,
        },
    ]


def _build_canonical_ir() -> ProcessIR:
    """Build the canonical ProcessIR via ``build_ir``."""
    return build_ir(
        process=_make_canonical_process(),
        steps=_make_canonical_steps(),
        flows=_make_canonical_flows(),
    )


# ---------------------------------------------------------------------------
# Main test — all assertions in one function (gate node id)
# ---------------------------------------------------------------------------


def test_issue233_freeform() -> None:
    """Full acceptance-criteria proof for Issue #233."""

    # ---- 1. Build canonical ProcessIR via build_ir ----
    process_ir = _build_canonical_ir()

    # Verify we got real StepIR / FlowIR objects (not mocks)
    assert all(isinstance(s, StepIR) for s in process_ir.steps)
    assert all(isinstance(f, FlowIR) for f in process_ir.flows)

    # ---- 2. Call layout() and check basic counts ----
    result: LayoutModel = layout(process_ir)

    assert isinstance(result, LayoutModel)
    assert len(result.shapes) == len(process_ir.steps), "exactly one ShapeBox per step"
    assert len(result.edges) == len(process_ir.flows), "exactly one EdgeRoute per flow"

    # ---- 3. Every ShapeBox coordinate is int ----
    for shape in result.shapes:
        assert isinstance(shape, ShapeBox)
        assert isinstance(shape.x, int), f"x must be int, got {type(shape.x)}"
        assert isinstance(shape.y, int), f"y must be int, got {type(shape.y)}"
        assert isinstance(shape.w, int), f"w must be int, got {type(shape.w)}"
        assert isinstance(shape.h, int), f"h must be int, got {type(shape.h)}"

    # ---- 4. Every EdgeRoute waypoint is (int, int) ----
    for edge in result.edges:
        assert isinstance(edge, EdgeRoute)
        for wp in edge.waypoints:
            assert len(wp) == 2, f"waypoint must be pair, got {wp}"
            assert isinstance(wp[0], int), f"waypoint x must be int, got {type(wp[0])}"
            assert isinstance(wp[1], int), f"waypoint y must be int, got {type(wp[1])}"

    # ---- 5. No two shapes share the same (x, y) ----
    positions = {(s.x, s.y): s.step_key for s in result.shapes}
    assert len(positions) == len(result.shapes), "duplicate shape position detected"

    # ---- 6. Byte-identical on repeated calls ----
    result2: LayoutModel = layout(process_ir)
    assert result == result2, "layout() must be deterministic across calls"

    # ---- 7. Byte-identical when input collections are shuffled ----
    for _ in range(5):
        permuted_steps = tuple(sorted(process_ir.steps, key=lambda s: s.step_key))
        import random

        random.shuffle(list(permuted_steps))
        permuted_flows = tuple(sorted(process_ir.flows, key=lambda f: f.flow_key))
        random.shuffle(list(permuted_flows))

        shuffled_ir = ProcessIR(
            process_key=process_ir.process_key,
            name=process_ir.name,
            version=process_ir.version,
            steps=tuple(permuted_steps),
            flows=tuple(permuted_flows),
        )
        shuffled_result: LayoutModel = layout(shuffled_ir)
        assert (
            result == shuffled_result
        ), "layout() must be deterministic regardless of input ordering"

    # ---- 8. Disconnected-node resilience ----
    # Build a process with an extra step that has NO incoming flow
    disconnected_steps = _make_canonical_steps() + [
        {
            "step_key": "orphan",
            "ordinal": 99,
            "step_type": "service",
            "name": "Orphan Service",
            "service_impl": "${orphan_task()}",
        },
    ]

    disconnected_ir = build_ir(
        process=_make_canonical_process(),
        steps=disconnected_steps,
        flows=_make_canonical_flows(),  # no flow touches 'orphan'
    )

    # Must NOT raise — every step gets a ShapeBox
    disc_result: LayoutModel = layout(disconnected_ir)
    assert len(disc_result.shapes) == len(
        disconnected_ir.steps
    ), "every step must get a ShapeBox, including disconnected ones"

    # Verify the orphan shape exists and has int coords
    orphan_shapes = [s for s in disc_result.shapes if s.step_key == "orphan"]
    assert len(orphan_shapes) == 1, "orphan step must have exactly one ShapeBox"
    orphan_shape = orphan_shapes[0]
    assert isinstance(orphan_shape.x, int)
    assert isinstance(orphan_shape.y, int)

    # No duplicate positions in the disconnected layout either
    disc_positions = {(s.x, s.y): s.step_key for s in disc_result.shapes}
    assert len(disc_positions) == len(
        disc_result.shapes
    ), "no duplicate positions with disconnected nodes"
