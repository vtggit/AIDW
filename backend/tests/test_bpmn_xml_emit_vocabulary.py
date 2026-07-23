"""Regression: xml_emit must speak the canonical step_type vocabulary.

The generator's step_type vocabulary is shared by app.bpmn.ir, app.bpmn.svg_emit
and the wizard: ``start`` / ``end`` / ``user`` / ``service`` / ``gateway``.

xml_emit once dispatched on ``user_task`` / ``service_task`` / ``exclusive_gateway``
instead, with a silent ``else: continue``. The result: every user task, service
task and gateway was DROPPED from the ``<bpmn:process>`` body, yet the DI section
and the sequence flows still referenced them — producing malformed BPMN with
dangling sourceRef/targetRef. The SVG preview masked it (svg_emit used the right
strings), and the Phase-3 proving test only counted DI shapes/edges (emitted for
every step regardless of type) so it never noticed.

These tests drive the FULL vocabulary through build_ir -> layout -> emit_bpmn and
assert (a) every node type actually appears as a process element and (b) no
sequence flow references a node id that isn't a real element — the check that
would have caught the drift.
"""

from xml.dom.minidom import parseString

import pytest

from app.bpmn.ir import IRError, build_ir
from app.bpmn.layout import layout
from app.bpmn.xml_emit import emit_bpmn

# Every BPMN flow-node tag emit_bpmn can produce inside <bpmn:process>.
_NODE_TAGS = (
    "bpmn:startEvent",
    "bpmn:endEvent",
    "bpmn:userTask",
    "bpmn:serviceTask",
    "bpmn:exclusiveGateway",
)


def _full_vocabulary_process():
    """A real process exercising every canonical step_type.

    start -> user task -> service task -> exclusive gateway -> {approved end,
    rejected end}. The gateway has exactly one default outgoing flow (ir
    invariant 4) and the service has a valid delegate impl (invariant 7).
    """
    process = {"process_key": "proc_vocab", "name": "Vocab", "version": 1}
    steps = [
        {"step_key": "start_1", "ordinal": 0, "step_type": "start", "name": "Start"},
        {
            "step_key": "review_1",
            "ordinal": 1,
            "step_type": "user",
            "name": "Review",
            "candidate_groups": ["managers"],
            "form_key": "review.frm",
        },
        {
            "step_key": "svc_1",
            "ordinal": 2,
            "step_type": "service",
            "name": "Do Work",
            "service_impl": "${approve}",
        },
        {"step_key": "gw_1", "ordinal": 3, "step_type": "gateway", "name": "Choose"},
        {"step_key": "end_a", "ordinal": 4, "step_type": "end", "name": "Approved"},
        {"step_key": "end_b", "ordinal": 5, "step_type": "end", "name": "Rejected"},
    ]
    flows = [
        {"flow_key": "f1", "source_step": "start_1", "target_step": "review_1"},
        {"flow_key": "f2", "source_step": "review_1", "target_step": "svc_1"},
        {"flow_key": "f3", "source_step": "svc_1", "target_step": "gw_1"},
        {
            "flow_key": "f4",
            "source_step": "gw_1",
            "target_step": "end_a",
            "is_default": True,
        },
        {
            "flow_key": "f5",
            "source_step": "gw_1",
            "target_step": "end_b",
            "condition_expression": "${rejected}",
        },
    ]
    return build_ir(process, steps, flows)


def _emit(process_ir):
    return emit_bpmn(process_ir, layout(process_ir))


def test_every_step_type_becomes_a_process_element():
    """Each canonical step_type maps to its BPMN element — none are dropped."""
    xml = _emit(_full_vocabulary_process())
    doc = parseString(xml)

    proc = doc.getElementsByTagName("bpmn:process")[0]

    def _count(tag):
        return len([n for n in proc.getElementsByTagName(tag)])

    assert _count("bpmn:startEvent") == 1
    assert _count("bpmn:userTask") == 1  # was 0 before the fix
    assert _count("bpmn:serviceTask") == 1  # was 0 before the fix
    assert _count("bpmn:exclusiveGateway") == 1  # was 0 before the fix
    assert _count("bpmn:endEvent") == 2

    # Total flow-nodes == total steps (6): the direct silent-drop guard.
    total_nodes = sum(_count(tag) for tag in _NODE_TAGS)
    assert total_nodes == 6


def test_no_sequence_flow_references_a_missing_node():
    """The dangling-ref check the proving test lacked.

    Every sourceRef/targetRef must resolve to a node element that was actually
    emitted. Under the drift, f2..f5 pointed at review_1/svc_1/gw_1 which had no
    element, so this would fail loudly.
    """
    xml = _emit(_full_vocabulary_process())
    doc = parseString(xml)
    proc = doc.getElementsByTagName("bpmn:process")[0]

    emitted_ids = {
        node.getAttribute("id")
        for tag in _NODE_TAGS
        for node in proc.getElementsByTagName(tag)
    }

    flows = proc.getElementsByTagName("bpmn:sequenceFlow")
    assert flows, "expected sequence flows to be emitted"
    for flow in flows:
        src = flow.getAttribute("sourceRef")
        tgt = flow.getAttribute("targetRef")
        assert (
            src in emitted_ids
        ), f"dangling sourceRef {src!r} in flow {flow.getAttribute('id')!r}"
        assert (
            tgt in emitted_ids
        ), f"dangling targetRef {tgt!r} in flow {flow.getAttribute('id')!r}"


def test_di_shapes_reference_only_real_process_elements():
    """BPMNShape.bpmnElement must resolve to an emitted flow-node too."""
    xml = _emit(_full_vocabulary_process())
    doc = parseString(xml)
    proc = doc.getElementsByTagName("bpmn:process")[0]

    emitted_ids = {
        node.getAttribute("id")
        for tag in _NODE_TAGS
        for node in proc.getElementsByTagName(tag)
    }

    shapes = doc.getElementsByTagName("bpmndi:BPMNShape")
    assert len(shapes) == 6
    for shape in shapes:
        ref = shape.getAttribute("bpmnElement")
        assert ref in emitted_ids, f"BPMNShape references non-existent element {ref!r}"


def test_unknown_step_type_fails_closed():
    """An unsupported step_type raises rather than silently dropping the node."""
    process = {"process_key": "proc_bad", "name": "Bad", "version": 1}
    steps = [
        {"step_key": "start_1", "ordinal": 0, "step_type": "start", "name": "Start"},
        {"step_key": "mystery", "ordinal": 1, "step_type": "timer", "name": "Wait"},
        {"step_key": "end_1", "ordinal": 2, "step_type": "end", "name": "End"},
    ]
    flows = [
        {"flow_key": "f1", "source_step": "start_1", "target_step": "mystery"},
        {"flow_key": "f2", "source_step": "mystery", "target_step": "end_1"},
    ]
    process_ir = build_ir(process, steps, flows)
    with pytest.raises(IRError):
        _emit(process_ir)
