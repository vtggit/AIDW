"""Proving test for issue #764: numeric/bool values never yield contact; plain decimal
strings are not phones; formatted phones and card ints still work."""

from app.pii.values import categories_above_floor


def test_issue764_surgical():
    # floats never yield contact
    floats = [12.3456789, 104.25, 3.1415926]
    assert "contact" not in categories_above_floor(floats)

    # same values as strings also yield no contact
    float_strings = ["12.3456789", "104.25", "3.1415926"]
    assert "contact" not in categories_above_floor(float_strings)

    # formatted phone strings still yield contact
    phones = ["+1 503 555 9931", "(503) 555-9931", "030-0074321"]
    assert "contact" in categories_above_floor(phones)

    # int card number still yields financial
    assert "financial" in categories_above_floor([4111111111111111])
