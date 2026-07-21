import pytest

from app.bpmn.ids import IdCollisionError, assert_unique, element_id, slug


def test_issue226_freeform():
    # Representative keys map to expected ids (sanitization & leading underscore)
    assert slug("review step!") == "review_step_"
    assert slug("1st") == "_1st"
    assert slug("normal_key") == "normal_key"

    # element_id composes the prefix correctly
    assert element_id("task", "review step!") == "task_review_step_"
    assert element_id("gateway", "1st") == "gateway__1st"

    # Two distinct source keys which sanitize to the same id raise IdCollisionError
    colliding_pairs = [
        ("review step!", element_id("task", "review step!")),
        ("review_step_", element_id("task", "review_step_")),
    ]
    with pytest.raises(IdCollisionError):
        assert_unique(colliding_pairs)

    # An already-distinct set passes without error
    distinct_pairs = [
        ("a", element_id("x", "a")),
        ("b", element_id("x", "b")),
    ]
    assert_unique(distinct_pairs)
