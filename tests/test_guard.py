import pytest

from healthcore.privacy.guard import LeakError, check_outbound
from healthcore.privacy.pseudonymizer import Pseudonymizer


def test_clean_text_with_placeholders_passes(detector):
    ps = Pseudonymizer()
    ps.register("PROVIDER", "Dr. Alicia Moreno")
    check_outbound('{"provider": "[PROVIDER_1]", "billed": "150.00"}', ps, detector)


def test_a_known_value_is_blocked_and_never_echoed(detector):
    ps = Pseudonymizer()
    ps.block("Alicia Moreno")
    with pytest.raises(LeakError) as error:
        check_outbound('{"note": "seen by alicia moreno"}', ps, detector)
    message = str(error.value)
    assert "Alicia" not in message and "Moreno" not in message
    assert "Nothing was sent" in message


def test_identifier_patterns_are_blocked(detector):
    for text in ("SSN 523-45-6789", "visit on 2024-03-05", "MBI 1EG4-TE5-MK72", "call (415) 555-0123"):
        with pytest.raises(LeakError):
            check_outbound(text, Pseudonymizer(), detector)


def test_a_registered_value_that_was_not_replaced_is_blocked(detector):
    ps = Pseudonymizer()
    ps.register("DATE", "Mar 5, 2024", matches=("2024-03-05",))
    with pytest.raises(LeakError):
        check_outbound("service on Mar 5, 2024", ps, detector)
