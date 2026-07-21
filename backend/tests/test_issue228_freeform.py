"""Proving test for Issue #228 — BPMN element emitters."""

import pytest

from app.bpmn.elements import (
    ServiceImplError,
    classify_service_impl,
    emit_end,
    emit_gateway,
    emit_sequence_flow,
    emit_service_task,
    emit_start,
    emit_user_task,
)


def test_issue228_freeform():  # noqa: C901 — single proving function
    # ------------------------------------------------------------------
    # classify_service_impl
    # ------------------------------------------------------------------

    # delegateExpression pattern (${...})
    assert classify_service_impl("${myDelegate}") == (
        "delegateExpression",
        "${myDelegate}",
    )
    assert classify_service_impl("${simple}") == ("delegateExpression", "${simple}")

    # Java class / dotted identifier pattern
    assert classify_service_impl("com.example.MyTask") == (
        "class",
        "com.example.MyTask",
    )
    assert classify_service_impl("_MyTask") == ("class", "_MyTask")
    assert classify_service_impl("A.B.C") == ("class", "A.B.C")

    # Raises ServiceImplError for unclassifiable values
    with pytest.raises(ServiceImplError):
        classify_service_impl("not a valid impl")

    with pytest.raises(ServiceImplError):
        classify_service_impl("")

    with pytest.raises(ServiceImplError):
        classify_service_impl("123Invalid")

    # ------------------------------------------------------------------
    # emit_start / emit_end
    # ------------------------------------------------------------------

    assert emit_start("start1") == '<bpmn:startEvent id="start1"/>'
    assert emit_end("end1") == '<bpmn:endEvent id="end1"/>'

    # ------------------------------------------------------------------
    # emit_user_task — formKey omitted (None)
    # ------------------------------------------------------------------

    result = emit_user_task("task1", "My Task", ["groupA"], None)
    assert 'id="task1"' in result
    assert 'name="My Task"' in result
    assert 'flowable:candidateGroups="groupA"' in result
    assert "formKey" not in result

    # ------------------------------------------------------------------
    # emit_user_task — formKey present
    # ------------------------------------------------------------------

    result = emit_user_task("task2", "Form Task", ["grp1", "grp2"], "myForm")
    assert 'id="task2"' in result
    assert 'flowable:candidateGroups="grp1,grp2"' in result
    assert 'flowable:formKey="myForm"' in result

    # ------------------------------------------------------------------
    # emit_service_task — delegateExpression
    # ------------------------------------------------------------------

    result = emit_service_task("svc1", "Delegate Task", "${myBean}")
    assert 'id="svc1"' in result
    assert 'name="Delegate Task"' in result
    assert 'flowable:delegateExpression="${myBean}"' in result
    assert "flowable:class" not in result

    # ------------------------------------------------------------------
    # emit_service_task — Java class name
    # ------------------------------------------------------------------

    result = emit_service_task("svc2", "Class Task", "com.example.Task")
    assert 'id="svc2"' in result
    assert 'name="Class Task"' in result
    assert 'flowable:class="com.example.Task"' in result
    assert "delegateExpression" not in result

    # ------------------------------------------------------------------
    # emit_gateway — carries its default flow id
    # ------------------------------------------------------------------

    result = emit_gateway("gw1", "Decision", "flow_yes")
    assert 'id="gw1"' in result
    assert 'name="Decision"' in result
    assert 'default="flow_yes"' in result

    # ------------------------------------------------------------------
    # emit_sequence_flow — without condition (self-closing)
    # ------------------------------------------------------------------

    result = emit_sequence_flow("flow1", "start1", "task1", None)
    assert 'id="flow1"' in result
    assert 'sourceRef="start1"' in result
    assert 'targetRef="task1"' in result
    assert "conditionExpression" not in result

    # ------------------------------------------------------------------
    # emit_sequence_flow — with condition (nested child element)
    # ------------------------------------------------------------------

    result = emit_sequence_flow("flow2", "gw1", "end1", "${approved}")
    assert 'id="flow2"' in result
    assert 'sourceRef="gw1"' in result
    assert 'targetRef="end1"' in result
    assert '<bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">' in result
    assert "${approved}" in result

    # ------------------------------------------------------------------
    # XML-special characters in a name are escaped
    # ------------------------------------------------------------------

    result = emit_user_task("task3", "A & B <C>", ["grp"], None)
    assert 'name="A &amp; B &lt;C&gt;"' in result

    # Double-quote inside an attribute value is also escaped
    result = emit_start('id"with"quotes')
    assert 'id="id&quot;with&quot;quotes"' in result
