"""BPMN 2.0 XML element emitters for Flowable process definitions.

Pure functions that produce well-formed BPMN 2.0 fragment strings using the
``bpmn:`` and ``flowable:`` namespace prefixes.  All injected values are
XML-escaped; attribute values use double quotes.
"""

from __future__ import annotations

import re
from html import escape as _xml_escape


class ServiceImplError(Exception):
    """Raised when a service implementation value cannot be classified."""


_DELEGATE_RE = re.compile(r"^\$\{.+\}$")
_JAVA_CLASS_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*(\.[A-Za-z_][A-Za-z0-9_$]*)*$")


def classify_service_impl(value: str) -> tuple[str, str]:
    """Classify a service implementation value.

    Returns ``("delegateExpression", value)`` for ``${...}`` expressions,
    ``("class", value)`` for dotted Java identifiers, or raises
    :class:`ServiceImplError`.
    """
    if _DELEGATE_RE.match(value):
        return ("delegateExpression", value)
    if _JAVA_CLASS_RE.match(value):
        return ("class", value)
    raise ServiceImplError(f"Cannot classify service implementation: {value!r}")


# ---------------------------------------------------------------------------
# Emitter helpers
# ---------------------------------------------------------------------------


def _attr(name: str, value: str) -> str:
    """Return a double-quoted XML attribute with the value escaped."""
    return f'{name}="{_xml_escape(value)}"'


# ---------------------------------------------------------------------------
# Element emitters — each returns one BPMN 2.0 fragment string
# ---------------------------------------------------------------------------


def emit_start(id: str) -> str:
    """Emit a ``<bpmn:startEvent>`` element."""
    return f"<bpmn:startEvent {_attr('id', id)}/>"


def emit_end(id: str) -> str:
    """Emit a ``<bpmn:endEvent>`` element."""
    return f"<bpmn:endEvent {_attr('id', id)}/>"


def emit_user_task(
    id: str,
    name: str | None,
    candidate_groups: list[str] | None,
    form_key: str | None = None,
) -> str:
    """Emit a ``<bpmn:userTask>`` element.

    ``name``, ``flowable:candidateGroups`` and ``flowable:formKey`` are all OPTIONAL — the real
    ``app.bpmn.ir`` contract declares them ``| None`` and no invariant fills them — so each is
    omitted entirely rather than emitted empty (or crashing) when absent.
    """
    attrs = [_attr("id", id)]
    if name is not None:
        attrs.append(_attr("name", name))
    if candidate_groups:
        attrs.append(_attr("flowable:candidateGroups", ",".join(candidate_groups)))
    if form_key is not None:
        attrs.append(_attr("flowable:formKey", form_key))
    return f"<bpmn:userTask {' '.join(attrs)}/>"


def emit_service_task(
    id: str,
    name: str | None,
    service_impl: str,
) -> str:
    """Emit a ``<bpmn:serviceTask>`` element.

    The implementation type (delegateExpression vs class) is determined by
    :func:`classify_service_impl`.
    """
    impl_type, impl_value = classify_service_impl(service_impl)
    if impl_type == "delegateExpression":
        impl_attr = _attr("flowable:delegateExpression", impl_value)
    else:
        impl_attr = _attr("flowable:class", impl_value)

    attrs = [_attr("id", id)]
    if name is not None:
        attrs.append(_attr("name", name))
    attrs.append(impl_attr)
    return f"<bpmn:serviceTask {' '.join(attrs)}/>"


def emit_gateway(
    id: str,
    name: str | None,
    default_flow_id: str,
) -> str:
    """Emit a ``<bpmn:exclusiveGateway>`` element with its *default* flow."""
    attrs = [_attr("id", id)]
    if name is not None:
        attrs.append(_attr("name", name))
    attrs.append(_attr("default", default_flow_id))
    return f"<bpmn:exclusiveGateway {' '.join(attrs)}/>"


def emit_sequence_flow(
    id: str,
    source_ref: str,
    target_ref: str,
    condition: str | None = None,
) -> str:
    """Emit a ``<bpmn:sequenceFlow>`` element.

    When *condition* is not ``None``, a nested
    ``<bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">`` child
    holding the XML-escaped condition is included.
    """
    attrs = [
        _attr("id", id),
        _attr("sourceRef", source_ref),
        _attr("targetRef", target_ref),
    ]

    if condition is not None:
        escaped_condition = _xml_escape(condition)
        inner = (
            f'<bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">'
            f"{escaped_condition}</bpmn:conditionExpression>"
        )
        return f"<bpmn:sequenceFlow {' '.join(attrs)}>{inner}</bpmn:sequenceFlow>"

    return f"<bpmn:sequenceFlow {' '.join(attrs)}/>"
