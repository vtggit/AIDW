"""BPMN process layout engine.

Reads a ``ProcessIR`` (from :mod:`app.bpmn.ir`) and computes a deterministic
visual layout — one ``ShapeBox`` per step, one ``EdgeRoute`` per flow.

Algorithm summary
-----------------
1. **Longest-path rank assignment** — topological ranks are computed from the
   DAG of steps/flows so that every target has a strictly higher rank than its
   source(s).  Disconnected (in-degree-0) nodes receive rank ``0``.
2. **Lane placement** — steps sharing the same rank are distributed across
   horizontal lanes; ranks flow left-to-right.
3. **Edge routing** — each flow becomes a polyline from the right edge of its
   source shape to the left edge of its target shape, with an optional mid-point
   bend for readability.

Determinism
-----------
All internal sort keys are based on ``step_key`` / ``flow_key`` strings so that
the output is byte-identical regardless of input ordering or repeated calls.
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict

from app.bpmn.ir import FlowIR, ProcessIR, StepIR

# ---------------------------------------------------------------------------
# Public data model
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ShapeBox:
    """Axis-aligned rectangle for a single BPMN step."""

    step_key: str
    x: int
    y: int
    w: int
    h: int


@dataclasses.dataclass(frozen=True)
class EdgeRoute:
    """Polyline connecting two shapes (or the same shape for self-loops)."""

    flow_key: str
    waypoints: tuple[tuple[int, int], ...]


@dataclasses.dataclass(frozen=True)
class LayoutModel:
    """Complete visual layout for a process."""

    shapes: tuple[ShapeBox, ...]
    edges: tuple[EdgeRoute, ...]


# ---------------------------------------------------------------------------
# Constants — shape geometry
# ---------------------------------------------------------------------------

SHAPE_W = 80
SHAPE_H = 40
LANE_GAP_X = 120  # horizontal gap between ranks
LANE_GAP_Y = 60  # vertical gap between lanes at the same rank


# ---------------------------------------------------------------------------
# Core algorithm
# ---------------------------------------------------------------------------


def _compute_ranks(
    steps: tuple[StepIR, ...],
    flows: tuple[FlowIR, ...],
) -> dict[str, int]:
    """Longest-path rank assignment.

    Returns a mapping ``step_key -> rank`` where every flow target has a
    strictly higher rank than its source.  Disconnected nodes get rank 0.
    """
    step_keys = {s.step_key for s in steps}
    ranks: dict[str, int] = {k: 0 for k in step_keys}

    # Build adjacency + in-degree
    successors: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = {k: 0 for k in step_keys}

    for f in flows:
        if f.source_step in step_keys and f.target_step in step_keys:
            successors[f.source_step].append(f.target_step)
            in_degree[f.target_step] += 1

    # Kahn's algorithm with longest-path relaxation
    queue = sorted(k for k, d in in_degree.items() if d == 0)
    while queue:
        node = queue.pop(0)
        for succ in successors[node]:
            ranks[succ] = max(ranks[succ], ranks[node] + 1)
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                # Insert in sorted order to keep determinism
                queue.append(succ)
        queue.sort()

    return ranks


def _assign_positions(
    steps: tuple[StepIR, ...],
    ranks: dict[str, int],
) -> dict[str, tuple[int, int]]:
    """Map each step_key to (x, y) based on rank and lane.

    Steps at the same rank are stacked vertically with LANE_GAP_Y spacing.
    Ranks flow left-to-right with LANE_GAP_X spacing.
    """
    # Group by rank, sort keys within each rank for determinism
    rank_groups: dict[int, list[str]] = defaultdict(list)
    for s in steps:
        rank_groups[ranks[s.step_key]].append(s.step_key)

    positions: dict[str, tuple[int, int]] = {}
    for rank in sorted(rank_groups):
        keys = sorted(rank_groups[rank])  # deterministic order
        for lane_idx, key in enumerate(keys):
            x = rank * LANE_GAP_X
            y = lane_idx * LANE_GAP_Y
            positions[key] = (x, y)

    return positions


def _build_shapes(
    steps: tuple[StepIR, ...],
    positions: dict[str, tuple[int, int]],
) -> list[ShapeBox]:
    """Create one ShapeBox per step."""
    shapes: list[ShapeBox] = []
    for s in sorted(steps, key=lambda st: st.step_key):
        x, y = positions[s.step_key]
        shapes.append(
            ShapeBox(
                step_key=s.step_key,
                x=x,
                y=y,
                w=SHAPE_W,
                h=SHAPE_H,
            )
        )
    return shapes


def _build_edges(
    flows: tuple[FlowIR, ...],
    positions: dict[str, tuple[int, int]],
) -> list[EdgeRoute]:
    """Create one EdgeRoute per flow.

    The route goes from the right edge of the source shape to the left edge
    of the target shape with a mid-point bend for readability.
    """
    edges: list[EdgeRoute] = []
    for f in sorted(flows, key=lambda fl: fl.flow_key):
        sx, sy = positions[f.source_step]
        tx, ty = positions[f.target_step]

        # Source right edge -> mid-point -> target left edge
        src_right = (sx + SHAPE_W, sy + SHAPE_H // 2)
        tgt_left = (tx, ty + SHAPE_H // 2)

        if sx == tx:
            # Same rank — vertical connection with a small horizontal offset
            mid_x = max(sx, tx) + LANE_GAP_X // 4
            waypoints = (
                src_right,
                (mid_x, src_right[1]),
                (mid_x, tgt_left[1]),
                tgt_left,
            )
        else:
            # Normal left-to-right connection with a bend at the midpoint x
            mid_x = (sx + SHAPE_W + tx) // 2
            waypoints = (
                src_right,
                (mid_x, src_right[1]),
                (mid_x, tgt_left[1]),
                tgt_left,
            )

        edges.append(
            EdgeRoute(
                flow_key=f.flow_key,
                waypoints=waypoints,
            )
        )
    return edges


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def layout(process_ir: ProcessIR) -> LayoutModel:
    """Compute a deterministic visual layout for *process_ir*.

    Returns a ``LayoutModel`` containing one ``ShapeBox`` per step and one
    ``EdgeRoute`` per flow.  All coordinates are integers.  The output is
    byte-identical regardless of input ordering or repeated calls.
    """
    ranks = _compute_ranks(process_ir.steps, process_ir.flows)
    positions = _assign_positions(process_ir.steps, ranks)

    shapes = tuple(_build_shapes(process_ir.steps, positions))
    edges = tuple(_build_edges(process_ir.flows, positions))

    return LayoutModel(shapes=shapes, edges=edges)
