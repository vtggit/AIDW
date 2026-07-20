"""Proving test for Issue #224 — BPMN IR builder."""

import copy

import pytest

from app.bpmn.ir import FlowIR, IRError, ProcessIR, StepIR, build_ir

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid():
    """Return (process_dict, steps_list, flows_list) for a valid reference.

    Structure: start -> service -> gateway -> end1 / end2
    """
    return (
        {"process_key": "proc_1", "name": "Test Process", "version": 1},
        [
            {
                "step_key": "start_1",
                "ordinal": 0,
                "step_type": "start",
                "name": "Start",
            },
            {
                "step_key": "svc_1",
                "ordinal": 1,
                "step_type": "service",
                "name": "Service",
                "service_impl": "${myDelegate}",
            },
            {
                "step_key": "gw_1",
                "ordinal": 2,
                "step_type": "gateway",
                "name": "Gateway",
            },
            {
                "step_key": "end_1",
                "ordinal": 3,
                "step_type": "end",
                "name": "End A",
            },
            {
                "step_key": "end_2",
                "ordinal": 4,
                "step_type": "end",
                "name": "End B",
            },
        ],
        [
            {
                "flow_key": "f1",
                "source_step": "start_1",
                "target_step": "svc_1",
                "is_default": False,
            },
            {
                "flow_key": "f2",
                "source_step": "svc_1",
                "target_step": "gw_1",
                "is_default": False,
            },
            {
                "flow_key": "f3",
                "source_step": "gw_1",
                "target_step": "end_1",
                "is_default": True,
                "condition_expression": None,
            },
            {
                "flow_key": "f4",
                "source_step": "gw_1",
                "target_step": "end_2",
                "is_default": False,
                "condition_expression": "${x > 5}",
            },
        ],
    )


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_issue224_freeform():
    process, steps, flows = _valid()

    # ---- Valid reference: build and verify attributes ----------------------
    ir = build_ir(process, steps, flows)

    assert isinstance(ir, ProcessIR)
    assert ir.process_key == "proc_1"
    assert ir.name == "Test Process"
    assert ir.version == 1

    # Steps sorted by (ordinal, step_key)
    assert len(ir.steps) == 5
    assert [s.step_key for s in ir.steps] == [
        "start_1",
        "svc_1",
        "gw_1",
        "end_1",
        "end_2",
    ]

    # Step attribute round-trips (start step)
    s0 = ir.steps[0]
    assert isinstance(s0, StepIR)
    assert (
        s0.step_key,
        s0.ordinal,
        s0.step_type,
        s0.name,
        s0.service_impl,
        s0.candidate_groups,
        s0.form_key,
    ) == ("start_1", 0, "start", "Start", None, None, None)

    # Step attribute round-trips (service step)
    s1 = ir.steps[1]
    assert isinstance(s1, StepIR)
    assert (
        s1.step_key,
        s1.ordinal,
        s1.step_type,
        s1.name,
        s1.service_impl,
        s1.candidate_groups,
        s1.form_key,
    ) == ("svc_1", 1, "service", "Service", "${myDelegate}", None, None)

    # Flows sorted by (is_default descending, flow_key):
    #   f3(default=True) first, then f1, f2, f4 alphabetically
    assert len(ir.flows) == 4
    assert [f.flow_key for f in ir.flows] == ["f3", "f1", "f2", "f4"]

    # Flow attribute round-trips (default flow)
    f0 = ir.flows[0]
    assert isinstance(f0, FlowIR)
    assert (
        f0.flow_key,
        f0.source_step,
        f0.target_step,
        f0.condition_expression,
        f0.is_default,
    ) == ("f3", "gw_1", "end_1", None, True)

    # Flow attribute round-trips (conditional flow)
    f3 = ir.flows[3]
    assert isinstance(f3, FlowIR)
    assert (
        f3.flow_key,
        f3.source_step,
        f3.target_step,
        f3.condition_expression,
        f3.is_default,
    ) == ("f4", "gw_1", "end_2", "${x > 5}", False)

    # ---- Invariant violations (each broken in isolation) -------------------

    # 1. Exactly one start step — broken: zero starts
    with pytest.raises(IRError):
        build_ir(process, [s for s in steps if s["step_type"] != "start"], flows)

    # 2. At least one end step — broken: no ends
    with pytest.raises(IRError):
        build_ir(process, [s for s in steps if s["step_type"] != "end"], flows)

    # 3. Source/target must reference existing step_keys — broken: unknown target
    bad_flows = copy.deepcopy(flows)
    bad_flows[0]["target_step"] = "nonexistent"
    with pytest.raises(IRError):
        build_ir(process, steps, bad_flows)

    # 4. Gateway must have exactly one outgoing default — broken: zero defaults
    no_default_flows = copy.deepcopy(flows)
    for f in no_default_flows:
        if f["flow_key"] == "f3":
            f["is_default"] = False
    with pytest.raises(IRError):
        build_ir(process, steps, no_default_flows)

    # 5. Integer ordinal + valid step_key — broken: invalid step_key pattern
    bad_steps_5 = copy.deepcopy(steps)
    bad_steps_5[0]["step_key"] = "123bad"
    with pytest.raises(IRError):
        build_ir(process, bad_steps_5, flows)

    # 6. Unique keys — broken: duplicate step_key
    dup_steps = copy.deepcopy(steps)
    dup_steps.append(
        {
            "step_key": "start_1",
            "ordinal": 99,
            "step_type": "end",
            "name": "Dup",
        }
    )
    with pytest.raises(IRError):
        build_ir(process, dup_steps, flows)

    # 7. Service step service_impl valid — broken: null service_impl
    bad_svc = copy.deepcopy(steps)
    for s in bad_svc:
        if s["step_key"] == "svc_1":
            s["service_impl"] = None
    with pytest.raises(IRError):
        build_ir(process, bad_svc, flows)

    # ---- Input order independence ------------------------------------------
    from random import Random

    rng = Random(42)
    shuffled_steps = copy.deepcopy(steps)
    rng.shuffle(shuffled_steps)
    shuffled_flows = copy.deepcopy(flows)
    rng.shuffle(shuffled_flows)

    ir_shuffled = build_ir(process, shuffled_steps, shuffled_flows)
    assert ir == ir_shuffled
