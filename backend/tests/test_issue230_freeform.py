"""Proving test for Issue #230 — BPMN layout engine.

Validates that ``app.bpmn.layout`` produces correct, deterministic layouts
for linear processes and exclusive-gateway fan-outs.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from app.bpmn.layout import EdgeRoute, LayoutModel, ShapeBox, layout

# ---------------------------------------------------------------------------
# Minimal IR types used only by this test
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Step:
    step_key: str
    ordinal: int
    kind: str
    label: str


@dataclass(frozen=True)
class _Flow:
    flow_key: str
    source_step_key: str
    target_step_key: str
    is_default: bool


@dataclass(frozen=True)
class _ProcessIR:
    steps: tuple[_Step, ...]
    flows: tuple[_Flow, ...]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_no_overlap(shapes: tuple[ShapeBox, ...]) -> None:
    """Assert no two ShapeBoxes overlap."""
    for i, a in enumerate(shapes):
        for b in shapes[i + 1 :]:
            assert not (
                a.x < b.x + b.w
                and a.x + a.w > b.x
                and a.y < b.y + b.h
                and a.y + a.h > b.y
            ), f"Overlap between {a.id} ({a.x},{a.y}) and {b.id} ({b.x},{b.y})"


def _assert_waypoints_in_viewbox(
    edges: tuple[EdgeRoute, ...], viewbox: tuple[int, int, int, int]
) -> None:
    """Assert every waypoint lies within the viewbox bounds."""
    vb_min_x, vb_min_y, vb_w, vb_h = viewbox
    for edge in edges:
        for wx, wy in edge.waypoints:
            assert (
                vb_min_x <= wx <= vb_min_x + vb_w
            ), f"Waypoint x={wx} outside viewbox [{vb_min_x}, {vb_min_x+vb_w}] on edge {edge.id}"
            assert (
                vb_min_y <= wy <= vb_min_y + vb_h
            ), f"Waypoint y={wy} outside viewbox [{vb_min_y}, {vb_min_y+vb_h}] on edge {edge.id}"


def _assert_x_increases_along_flows(
    shapes: tuple[ShapeBox, ...], flows: tuple[_Flow, ...]
) -> None:
    """Assert a shape's x strictly increases along each forward sequence."""
    shape_by_id = {s.id: s for s in shapes}
    for flow in flows:
        src = shape_by_id[flow.source_step_key]
        tgt = shape_by_id[flow.target_step_key]
        assert (
            src.x + src.w < tgt.x
        ), f"x does not increase along {flow.flow_key}: {src.id} east={src.x+src.w} >= {tgt.id} west={tgt.x}"


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_issue230_freeform() -> None:
    # ---- Linear process: start -> task1 -> end -----------------------------
    linear_steps = (
        _Step("start", 0, "start_event", "Start"),
        _Step("task1", 1, "task", "Task 1"),
        _Step("end", 2, "end_event", "End"),
    )
    linear_flows = (
        _Flow("f1", "start", "task1", True),
        _Flow("f2", "task1", "end", True),
    )
    linear_ir = _ProcessIR(linear_steps, linear_flows)

    lm_linear: LayoutModel = layout(linear_ir)

    # Every step has exactly one ShapeBox
    assert len(lm_linear.shapes) == 3
    shape_ids = {s.id for s in lm_linear.shapes}
    assert shape_ids == {"start", "task1", "end"}

    # Every sequence has exactly one EdgeRoute
    assert len(lm_linear.edges) == 2
    edge_ids = {e.id for e in lm_linear.edges}
    assert edge_ids == {"f1", "f2"}

    # No two ShapeBoxes overlap
    _assert_no_overlap(lm_linear.shapes)

    # Every waypoint lies within the viewbox bounds
    _assert_waypoints_in_viewbox(lm_linear.edges, lm_linear.viewbox)

    # A shape's x strictly increases along each forward sequence
    _assert_x_increases_along_flows(lm_linear.shapes, linear_flows)

    # Deterministic: computing twice gives equal LayoutModel
    assert layout(linear_ir) == lm_linear

    # ---- Gateway process with two branches ---------------------------------
    gw_steps = (
        _Step("start", 0, "start_event", "Start"),
        _Step("gw", 1, "exclusive_gateway", "Gateway"),
        _Step("branch_a", 2, "task", "Branch A"),
        _Step("branch_b", 3, "task", "Branch B"),
        _Step("end", 4, "end_event", "End"),
    )
    gw_flows = (
        _Flow("f_start_gw", "start", "gw", True),
        _Flow("f_gw_a", "gw", "branch_a", True),  # default branch
        _Flow("f_gw_b", "gw", "branch_b", False),  # non-default branch
        _Flow("f_a_end", "branch_a", "end", True),
        _Flow("f_b_end", "branch_b", "end", True),
    )
    gw_ir = _ProcessIR(gw_steps, gw_flows)

    lm_gw: LayoutModel = layout(gw_ir)

    # Every step has exactly one ShapeBox
    assert len(lm_gw.shapes) == 5
    shape_ids_gw = {s.id for s in lm_gw.shapes}
    assert shape_ids_gw == {"start", "gw", "branch_a", "branch_b", "end"}

    # Every sequence has exactly one EdgeRoute
    assert len(lm_gw.edges) == 5
    edge_ids_gw = {e.id for e in lm_gw.edges}
    assert edge_ids_gw == {"f_start_gw", "f_gw_a", "f_gw_b", "f_a_end", "f_b_end"}

    # No two ShapeBoxes overlap
    _assert_no_overlap(lm_gw.shapes)

    # Every waypoint lies within the viewbox bounds
    _assert_waypoints_in_viewbox(lm_gw.edges, lm_gw.viewbox)

    # A shape's x strictly increases along each forward sequence
    _assert_x_increases_along_flows(lm_gw.shapes, gw_flows)

    # Deterministic: computing twice gives equal LayoutModel
    assert layout(gw_ir) == lm_gw

    # ---- Determinism from shuffled inputs ----------------------------------
    rng = random.Random(42)  # seeded for reproducibility of the test itself

    # Shuffle linear process
    shuffled_linear_steps = tuple(rng.sample(list(linear_steps), len(linear_steps)))
    shuffled_linear_flows = tuple(rng.sample(list(linear_flows), len(linear_flows)))
    lm_shuffled_linear = layout(
        _ProcessIR(shuffled_linear_steps, shuffled_linear_flows)
    )
    assert lm_shuffled_linear == lm_linear

    # Shuffle gateway process
    shuffled_gw_steps = tuple(rng.sample(list(gw_steps), len(gw_steps)))
    shuffled_gw_flows = tuple(rng.sample(list(gw_flows), len(gw_flows)))
    lm_shuffled_gw = layout(_ProcessIR(shuffled_gw_steps, shuffled_gw_flows))
    assert lm_shuffled_gw == lm_gw
