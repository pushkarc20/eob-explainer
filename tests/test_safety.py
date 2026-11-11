from eob.safety import DISCLAIMER, find_banned


def test_find_banned_is_case_insensitive_and_handles_curly_apostrophes():
    found = find_banned("This looks like an Error, so don\u2019t pay it.")
    assert "error" in found
    assert "don't pay" in found


def test_ordinary_explanations_are_not_banned():
    assert find_banned("The plan paid $144.00 and you owe $36.00. Ask your insurer how this was calculated.") == []


def test_the_app_disclaimer_is_itself_clean():
    assert find_banned(DISCLAIMER) == []
    assert "insurer" in DISCLAIMER
