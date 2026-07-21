"""Deterministic integer-coordinate layout engine for BPMN process IR.

Produces a ``LayoutModel`` (shapes + edges + viewbox) from a validated
process object whose ``steps`` and ``flows`` tuples describe the graph.

Algorithm summary
-----------------
1. Sort steps by ``(ordinal, step_key)``; sort each step's outgoing flows
   by ``(is_default first, then flow_key)`` so output is independent of
   input order.
2. Assign every step a **rank** equal to the longest forward path length
   from the single start step (start at rank 0).
3. Place shapes left-to-right by rank; keep the main path on a center row
   and fan gateway branch targets onto adjacent rows.
4. Size each shape by kind (event 36×36, task 100×80, gateway 50×50).
5. Route every sequence with straight or right-angled integer waypoints
   from the source shape's east edge to the target shape's west edge.
6. Compute a viewbox enclosing all shapes and waypoints with a small margin.

Every coordinate is an ``int``.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Public data types (frozen for immutability / hashability)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ShapeBox:
    """A positioned shape in the layout."""

    id: str
    x: int
    y: int
    w: int
    h: int
    label: str
    kind: str


@dataclass(frozen=True)
class EdgeRoute:
    """A routed edge between two shapes."""

    id: str
    waypoints: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class LayoutModel:
    """Complete layout model with shapes, edges, and viewbox.

    Attributes
    ----------
    shapes : tuple of ShapeBox
        One shape per step in the process IR.
    edges : tuple of EdgeRoute
        One edge per sequence flow in the process IR.
    viewbox : (min_x, min_y, width, height)
        Integer rectangle enclosing every shape and waypoint with margin.
    """

    shapes: tuple[ShapeBox, ...]
    edges: tuple[EdgeRoute, ...]
    viewbox: tuple[int, int, int, int]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Shape dimensions ``(width, height)`` keyed by step kind.
SHAPE_DIMS: dict[str, tuple[int, int]] = {
    "start_event": (36, 36),
    "end_event": (36, 36),
    "task": (100, 80),
    "exclusive_gateway": (50, 50),
}

#: Horizontal spacing between rank columns.
_RANK_SPACING: int = 140

#: Vertical spacing between lanes (rows).
_LANE_SPACING: int = 120

#: Margin added around the bounding box for the viewbox.
_MARGIN: int = 20


# ---------------------------------------------------------------------------
# Core layout function
# ---------------------------------------------------------------------------


def layout(process_ir) -> LayoutModel:
    """Compute a deterministic integer-coordinate layout for a process IR.

    Parameters
    ----------
    process_ir : object
        Must expose ``steps`` (tuple) and ``flows`` (tuple).  Each step
        carries ``step_key``, ``ordinal``, ``kind``, and ``label``.  Each
        flow carries ``flow_key``, ``source_step_key``, ``target_step_key``,
        and ``is_default`` (bool).

    Returns
    -------
    LayoutModel
    """
    # 1. Deterministic ordering ------------------------------------------------
    sorted_steps = sorted(process_ir.steps, key=lambda s: (s.ordinal, s.step_key))
    step_map: dict[str, object] = {s.step_key: s for s in sorted_steps}

    # Adjacency structures
    outgoing: dict[str, list[object]] = {}  # step_key -> [flows]
    incoming: dict[str, list[object]] = {}  # step_key -> [flows]

    for flow in process_ir.flows:
        src = flow.source_step_key
        tgt = flow.target_step_key
        outgoing.setdefault(src, []).append(flow)
        incoming.setdefault(tgt, []).append(flow)

    # Sort outgoing flows: is_default=True first, then by flow_key
    for src in outgoing:
        outgoing[src].sort(key=lambda f: (not f.is_default, f.flow_key))

    # Identify the single start step
    start_step = next(s for s in sorted_steps if s.kind == "start_event")

    # 2. Rank assignment via longest forward path from start -------------------
    in_degree: dict[str, int] = {
        s.step_key: len(incoming.get(s.step_key, [])) for s in sorted_steps
    }
    ranks: dict[str, int] = {}

    if in_degree[start_step.step_key] == 0:
        ranks[start_step.step_key] = 0

    queue: list[str] = [start_step.step_key] if start_step.step_key in ranks else []
    topo_order: list[str] = []

    while queue:
        # Deterministic tie-breaking when multiple nodes are ready
        queue.sort(key=lambda k: (ranks.get(k, 0), step_map[k].ordinal, k))
        current = queue.pop(0)
        topo_order.append(current)

        for flow in outgoing.get(current, []):
            tgt = flow.target_step_key
            new_rank = ranks[current] + 1
            if tgt not in ranks or new_rank > ranks[tgt]:
                ranks[tgt] = new_rank
            in_degree[tgt] -= 1
            if in_degree[tgt] == 0:
                queue.append(tgt)

    # 3. Lane (row) assignment -------------------------------------------------
    lanes: dict[str, int] = {}
    next_lane_id: list[int] = [1]  # mutable counter for branch lanes

    for step_key in topo_order:
        if step_key == start_step.step_key:
            lanes[step_key] = 0
            continue

        inc_flows = sorted(
            incoming.get(step_key, []),
            key=lambda f: (not f.is_default, f.flow_key),
        )

        # A node is a branch target when it receives a non-default flow from
        # a source that has multiple outgoing flows (i.e. an exclusive gateway).
        is_branch_target = False
        for flow in inc_flows:
            src_outgoing = outgoing.get(flow.source_step_key, [])
            if len(src_outgoing) > 1 and not flow.is_default:
                is_branch_target = True
                break

        if is_branch_target:
            lanes[step_key] = next_lane_id[0]
            next_lane_id[0] += 1
        else:
            # Inherit lane from the first (default) incoming source.
            src_key = inc_flows[0].source_step_key
            lanes[step_key] = lanes[src_key]

    # 4. Place shapes on grid by rank and lane ---------------------------------
    shape_map: dict[str, ShapeBox] = {}
    for step in sorted_steps:
        w, h = SHAPE_DIMS.get(step.kind, (100, 80))
        x = ranks[step.step_key] * _RANK_SPACING + (_RANK_SPACING - w) // 2
        y = lanes[step.step_key] * _LANE_SPACING + (_LANE_SPACING - h) // 2
        shape_map[step.step_key] = ShapeBox(
            id=step.step_key,
            x=x,
            y=y,
            w=w,
            h=h,
            label=step.label,
            kind=step.kind,
        )

    # 5. Route edges -----------------------------------------------------------
    edge_routes: list[EdgeRoute] = []
    for step_key in topo_order:
        for flow in outgoing.get(step_key, []):
            src_box = shape_map[flow.source_step_key]
            tgt_box = shape_map[flow.target_step_key]

            src_east_x = src_box.x + src_box.w
            src_mid_y = src_box.y + src_box.h // 2
            tgt_west_x = tgt_box.x
            tgt_mid_y = tgt_box.y + tgt_box.h // 2

            if src_mid_y == tgt_mid_y:
                # Straight horizontal line (same lane)
                waypoints: tuple[tuple[int, int], ...] = (
                    (src_east_x, src_mid_y),
                    (tgt_west_x, tgt_mid_y),
                )
            else:
                # Right-angled path via midpoint x
                mid_x = (src_east_x + tgt_west_x) // 2
                waypoints = (
                    (src_east_x, src_mid_y),
                    (mid_x, src_mid_y),
                    (mid_x, tgt_mid_y),
                    (tgt_west_x, tgt_mid_y),
                )

            edge_routes.append(EdgeRoute(id=flow.flow_key, waypoints=waypoints))

    # 6. Compute viewbox -------------------------------------------------------
    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")

    for shape in shape_map.values():
        min_x = min(min_x, shape.x)
        min_y = min(min_y, shape.y)
        max_x = max(max_x, shape.x + shape.w)
        max_y = max(max_y, shape.y + shape.h)

    for edge in edge_routes:
        for wx, wy in edge.waypoints:
            min_x = min(min_x, wx)
            min_y = min(min_y, wy)
            max_x = max(max_x, wx)
            max_y = max(max_y, wy)

    viewbox: tuple[int, int, int, int] = (
        int(min_x - _MARGIN),
        int(min_y - _MARGIN),
        int(max_x - min_x + 2 * _MARGIN),
        int(max_y - min_y + 2 * _MARGIN),
    )

    # Build final shapes tuple in deterministic order (sorted by ordinal, key)
    shapes = tuple(shape_map[s.step_key] for s in sorted_steps)

    return LayoutModel(shapes=shapes, edges=tuple(edge_routes), viewbox=viewbox)
