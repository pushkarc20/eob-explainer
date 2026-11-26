from eob.judge import (
    GLOSSARY_RULE,
    JUDGE_PROMPT_VERSION,
    JUDGE_PROMPTS,
    JUDGE_SYSTEM,
    JUDGE_SYSTEM_J1,
)


def test_j2_is_current_and_j1_is_kept_for_reproducibility():
    assert JUDGE_PROMPT_VERSION == "j2"
    assert JUDGE_PROMPTS == {"j1": JUDGE_SYSTEM_J1, "j2": JUDGE_SYSTEM}
    assert "NOT an unsupported claim" in JUDGE_SYSTEM
    assert "NOT an unsupported claim" not in JUDGE_SYSTEM_J1


def test_j2_differs_from_j1_only_by_the_glossary_rule():
    assert JUDGE_SYSTEM.replace(GLOSSARY_RULE, "") == JUDGE_SYSTEM_J1


def test_the_glossary_rule_still_requires_claims_about_this_claim_to_be_supported():
    assert "about this particular claim" in GLOSSARY_RULE
    assert JUDGE_SYSTEM.index(GLOSSARY_RULE) < JUDGE_SYSTEM.index("Respond with ONLY a JSON object")