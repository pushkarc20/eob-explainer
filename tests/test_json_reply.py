from healthcore.llm.json_reply import extract_json_object


def test_plain_fenced_and_surrounded_json_are_all_found():
    assert extract_json_object('{"a": 1}') == '{"a": 1}'
    assert extract_json_object('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert extract_json_object('Sure! Here it is: {"a": 1} Hope that helps.') == '{"a": 1}'


def test_text_without_an_object_returns_none():
    assert extract_json_object("no json here") is None
    assert extract_json_object("} backwards {") is None
