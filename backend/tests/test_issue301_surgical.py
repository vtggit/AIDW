import pytest

from app.bpmn.ir import IRError, build_ir


def test_issue301_surgical():
    process = {"process_key": "p", "name": None, "version": 1}
    steps = [
        {"step_key": "start", "ordinal": 0, "step_type": "start"},
        {"step_key": "end", "ordinal": 1, "step_type": "end"},
    ]

    # Valid flow_key passes through
    valid_flows = [{"flow_key": "f_ok", "source_step": "start", "target_step": "end"}]
    ir = build_ir(process, steps, valid_flows)
    assert len(ir.flows) == 1

    # Quote in flow_key must raise IRError (prevents XML/SVG attribute breakout)
    quote_flow = [{"flow_key": 'f"bad', "source_step": "start", "target_step": "end"}]
    with pytest.raises(IRError, match="Invalid flow_key"):
        build_ir(process, steps, quote_flow)

    # Leading digit must raise IRError
    digit_flow = [{"flow_key": "1f_bad", "source_step": "start", "target_step": "end"}]
    with pytest.raises(IRError, match="Invalid flow_key"):
        build_ir(process, steps, digit_flow)

    # Empty string must raise IRError
    empty_flow = [{"flow_key": "", "source_step": "start", "target_step": "end"}]
    with pytest.raises(IRError, match="Invalid flow_key"):
        build_ir(process, steps, empty_flow)
