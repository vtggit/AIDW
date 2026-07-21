"""Proving tests for the four adversarial-audit findings in the bpmn generator.

elements (2 HIGH): a ``None`` name or ``None`` candidate_groups used to crash generation
(html.escape(None) / ",".join(None)); both are optional in the real ir contract, so the attribute
is now omitted instead. Output for non-None values must be byte-identical to before.

ir (MED + LOW): the Java-class pattern rejected ``$`` (stricter than the downstream
elements.classify_service_impl, so a valid Flowable inner-class delegate could never be built);
and ``re.match`` with a ``$`` anchor let a trailing newline bypass every gate.
"""

from xml.dom.minidom import parseString

import pytest

from app.bpmn import elements as E
from app.bpmn.ir import IRError, build_ir

_NS = (
    'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
    'xmlns:flowable="http://flowable.org/bpmn" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
)


def _wellformed(fragment):
    """Every emitted fragment must still parse inside a namespace-declaring root."""
    parseString(f"<root {_NS}>{fragment}</root>")


# ── elements: the public surface must stay complete (a dropped emitter breaks xml_emit) ──


def test_elements_public_surface_intact():
    for name in (
        "ServiceImplError",
        "classify_service_impl",
        "emit_start",
        "emit_end",
        "emit_user_task",
        "emit_service_task",
        "emit_gateway",
        "emit_sequence_flow",
    ):
        assert hasattr(E, name), f"elements.{name} is missing"
        assert callable(getattr(E, name)) or isinstance(getattr(E, name), type)


# ── elements HIGH #1 + #2: None must be omitted, never crash ──


def test_user_task_none_name_and_groups_are_omitted():
    frag = E.emit_user_task("t1", None, None)
    assert "name=" not in frag
    assert "candidateGroups=" not in frag
    assert 'id="t1"' in frag
    _wellformed(frag)


def test_user_task_empty_groups_omitted():
    frag = E.emit_user_task("t1", "Review", [])
    assert "candidateGroups=" not in frag
    assert 'name="Review"' in frag
    _wellformed(frag)


def test_service_task_and_gateway_none_name_omitted():
    svc = E.emit_service_task("s1", None, "${approve}")
    assert "name=" not in svc and "delegateExpression" in svc
    _wellformed(svc)

    gw = E.emit_gateway("g1", None, "f1")
    assert "name=" not in gw and 'default="f1"' in gw
    _wellformed(gw)


def test_non_none_output_is_unchanged():
    """The byte-stability contract: values that are not None emit exactly as before."""
    frag = E.emit_user_task("t1", "Review", ["mgr", "ops"], form_key="f.frm")
    assert (
        frag == '<bpmn:userTask id="t1" name="Review" '
        'flowable:candidateGroups="mgr,ops" flowable:formKey="f.frm"/>'
    )
    assert (
        E.emit_gateway("g1", "Choose", "f1")
        == '<bpmn:exclusiveGateway id="g1" name="Choose" default="f1"/>'
    )


# ── ir: helpers to build a minimal valid process ──


def _process(steps, flows):
    return build_ir({"process_key": "p1", "name": "P", "version": 1}, steps, flows)


def _minimal(step_key="start_1", impl=None):
    steps = [
        {"step_key": step_key, "ordinal": 0, "step_type": "start", "name": "S"},
        {"step_key": "end_1", "ordinal": 2, "step_type": "end", "name": "E"},
    ]
    flows = [{"flow_key": "f1", "source_step": step_key, "target_step": "end_1"}]
    if impl is not None:
        steps.insert(
            1,
            {
                "step_key": "svc_1",
                "ordinal": 1,
                "step_type": "service",
                "name": "Do",
                "service_impl": impl,
            },
        )
        flows = [
            {"flow_key": "f1", "source_step": step_key, "target_step": "svc_1"},
            {"flow_key": "f2", "source_step": "svc_1", "target_step": "end_1"},
        ]
    return steps, flows


# ── ir MEDIUM: `$` in a Java class must be accepted (agree with elements) ──


def test_ir_accepts_java_inner_class_with_dollar():
    steps, flows = _minimal(impl="com.acme.Outer$Inner")
    ir = _process(steps, flows)
    svc = [s for s in ir.steps if s.step_type == "service"][0]
    assert svc.service_impl == "com.acme.Outer$Inner"
    # and the downstream emitter agrees, as it always did
    assert E.classify_service_impl("com.acme.Outer$Inner")[0] == "class"


def test_ir_still_accepts_delegate_and_plain_class():
    for impl in ("${approve}", "com.acme.Foo"):
        steps, flows = _minimal(impl=impl)
        assert _process(steps, flows) is not None


# ── ir LOW: a trailing newline must no longer bypass the gates ──


def test_ir_rejects_trailing_newline_step_key():
    steps, flows = _minimal(step_key="approve\n")
    with pytest.raises(IRError):
        _process(steps, flows)


def test_ir_rejects_trailing_newline_service_impl():
    steps, flows = _minimal(impl="com.acme.Foo\n")
    with pytest.raises(IRError):
        _process(steps, flows)


def test_ir_still_rejects_malformed_values():
    steps, flows = _minimal(step_key="9bad")
    with pytest.raises(IRError):
        _process(steps, flows)
    steps, flows = _minimal(impl="not a class!")
    with pytest.raises(IRError):
        _process(steps, flows)
