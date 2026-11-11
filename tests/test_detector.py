import pytest

from healthcore.privacy.detector import HARD_ENTITIES, PiiDetector, scrub_text
from healthcore.privacy.pseudonymizer import Pseudonymizer


def found_types(detector, text, entities=None):
    return {finding.entity_type for finding in detector.find(text, entities)}


def test_finds_pattern_based_identifiers(detector):
    text = "SSN 523-45-6789, email jane.doe@example.com, phone (415) 555-0123"
    assert {"US_SSN", "EMAIL_ADDRESS", "PHONE_NUMBER"} <= found_types(detector, text)


def test_finds_healthcare_identifiers(detector):
    assert "US_MBI" in found_types(detector, "MBI 1EG4-TE5-MK72")
    assert "US_NPI" in found_types(detector, "NPI 1234567893")
    assert "ID_LIKE" in found_types(detector, "claim number 22011027731")
    assert "ID_LIKE" in found_types(detector, "claim AW123412341234123412341234123413")


def test_finds_full_dates_in_common_formats(detector):
    for text in ("seen 2024-03-05", "seen 3/5/2024", "seen March 5, 2024", "seen Mar 5, 2024"):
        assert "FULL_DATE" in found_types(detector, text), text


def test_finds_a_person_name_with_the_ner_model(detector):
    # If this fails, the small spaCy model is not accurate enough and we will switch to the large one.
    assert "PERSON" in found_types(detector, "Please contact Alicia Moreno at the clinic.")


def test_ordinary_explanation_text_is_not_flagged_by_the_hard_patterns(detector):
    text = "The plan paid $150.00 and you owe $30.00 for service code 99213 on line items 1, 2."
    assert found_types(detector, text, HARD_ENTITIES) == set()


def test_scrub_text_replaces_identifiers_and_is_reversible(detector):
    ps = Pseudonymizer()
    text = "Call 415-555-0123 about the visit on 2024-03-05, MBI 1EG4-TE5-MK72."
    scrubbed, counts = scrub_text(text, detector, ps)
    for secret in ("415-555-0123", "2024-03-05", "1EG4-TE5-MK72"):
        assert secret not in scrubbed
    assert {"PHONE_NUMBER", "FULL_DATE", "US_MBI"} <= set(counts)
    assert ps.restore(scrubbed) == text


def test_scrub_text_leaves_clean_text_alone(detector):
    ps = Pseudonymizer()
    text = "Therapeutic procedure, each 15 minutes; therapeutic exercises"
    scrubbed, counts = scrub_text(text, detector, ps)
    assert scrubbed == text
    assert counts == {}


def test_missing_model_raises_a_clear_error_and_never_downloads():
    with pytest.raises(RuntimeError, match="spacy download"):
        PiiDetector(model="en_core_web_does_not_exist").find("hello")
