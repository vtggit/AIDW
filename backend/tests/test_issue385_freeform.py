"""Proving test for Issue #385 — load-sequence BPMN projection."""

from xml.dom.minidom import parseString

import pytest


def _count_elements(doc, tag_name):
    """Return the number of elements matching *tag_name* in an XML document.

    Handles namespace prefixes by splitting on ':' and checking localName/prefix.
    """
    if ":" in tag_name:
        prefix, local = tag_name.split(":", 1)
        return len(
            [
                e
                for e in doc.getElementsByTagName("*")
                if e.prefix == prefix and e.localName == local
            ]
        )
    return len(doc.getElementsByTagName(tag_name))


def test_issue385_freeform(client, admin_headers):
    """Projecting a load sequence as BPMN returns the server-generated diagram."""

    # ---- Fixture chain: create prerequisite rows (every create asserts 201) ----

    # Create pipeline
    resp = client.post("/api/pipelines", json={"name": "p1"}, headers=admin_headers)
    assert resp.status_code == 201, f"pipeline create failed: {resp.text}"
    pipeline_id = resp.json()["id"]

    # Create load sequence
    resp = client.post(
        "/api/load-sequences", json={"name": "seq1"}, headers=admin_headers
    )
    assert resp.status_code == 201, f"load-sequence create failed: {resp.text}"
    seq_id = resp.json()["id"]

    # Create sequence step 1
    resp = client.post(
        "/api/sequence-steps",
        json={
            "name": "s1",
            "sequence_id": seq_id,
            "pipeline_id": pipeline_id,
            "order_index": 0,
            "label": "step 1",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, f"sequence-step 1 create failed: {resp.text}"

    # Create sequence step 2
    resp = client.post(
        "/api/sequence-steps",
        json={
            "name": "s2",
            "sequence_id": seq_id,
            "pipeline_id": pipeline_id,
            "order_index": 1,
            "label": "step 2",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, f"sequence-step 2 create failed: {resp.text}"

    # ---- GET the BPMN projection ----

    resp = client.get(f"/api/load-sequences/{seq_id}/bpmn", headers=admin_headers)
    assert resp.status_code == 200, f"bpmn get failed: {resp.text}"
    body = resp.json()

    # ---- Assert process_key ----
    assert body["process_key"] == f"load_sequence_{seq_id}"

    # ---- Parse and assert BPMN XML structure via xml.dom.minidom ----
    bpmn_doc = parseString(body["bpmn_xml"])
    assert bpmn_doc.documentElement.localName == "definitions"

    assert _count_elements(bpmn_doc, "bpmn:startEvent") == 1
    assert _count_elements(bpmn_doc, "bpmn:endEvent") == 1
    assert _count_elements(bpmn_doc, "bpmn:serviceTask") == 2
    assert _count_elements(bpmn_doc, "bpmn:sequenceFlow") == 3
    assert _count_elements(bpmn_doc, "bpmndi:BPMNShape") == 4
    assert _count_elements(bpmn_doc, "bpmndi:BPMNEdge") == 3

    # ---- Parse and assert SVG structure ----
    svg_doc = parseString(body["svg"])
    assert svg_doc.documentElement.localName == "svg"

    # ---- 404 for unknown sequence id ----
    resp = client.get(
        "/api/load-sequences/nonexistent-sequence-id/bpmn", headers=admin_headers
    )
    assert resp.status_code == 404

    # ---- 401 without Authorization header ----
    resp = client.get(f"/api/load-sequences/{seq_id}/bpmn")
    assert resp.status_code == 401
