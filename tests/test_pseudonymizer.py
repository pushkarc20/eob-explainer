from healthcore.privacy.pseudonymizer import Pseudonymizer


def test_same_value_gets_the_same_placeholder_and_kinds_count_separately():
    ps = Pseudonymizer()
    assert ps.register("PROVIDER", "Dr. Alicia Moreno") == "[PROVIDER_1]"
    assert ps.register("PROVIDER", "Dr. Alicia Moreno") == "[PROVIDER_1]"
    assert ps.register("PROVIDER", "Riverside Orthopedics") == "[PROVIDER_2]"
    assert ps.register("DATE", "Mar 5, 2024") == "[DATE_1]"
    assert ps.counts() == {"PROVIDER": 2, "DATE": 1}


def test_apply_replaces_every_spelling():
    ps = Pseudonymizer()
    ps.register("DATE", "Mar 5, 2024", matches=("2024-03-05",))
    text = "Seen on 2024-03-05 and again on Mar 5, 2024."
    assert ps.apply(text) == "Seen on [DATE_1] and again on [DATE_1]."


def test_apply_is_case_insensitive_and_respects_word_boundaries():
    ps = Pseudonymizer()
    ps.register("PERSON", "Ann")
    assert ps.apply("ann signed the Annual form") == "[PERSON_1] signed the Annual form"


def test_longest_spelling_wins():
    ps = Pseudonymizer()
    ps.register(
        "PROVIDER", "Riverside Orthopedics - Dr. James Whitfield", matches=("Riverside Orthopedics",)
    )
    assert ps.apply("Riverside Orthopedics - Dr. James Whitfield billed") == "[PROVIDER_1] billed"
    assert ps.apply("Riverside Orthopedics billed") == "[PROVIDER_1] billed"


def test_restore_puts_real_values_back_and_leaves_unknown_placeholders_alone():
    ps = Pseudonymizer()
    ps.register("PROVIDER", "Dr. Alicia Moreno Family Medicine")
    ps.register("DATE", "Mar 5, 2024", matches=("2024-03-05",))
    text = "Ask [PROVIDER_1] about [DATE_1] and [PROVIDER_9]."
    assert ps.restore(text) == "Ask Dr. Alicia Moreno Family Medicine about Mar 5, 2024 and [PROVIDER_9]."
    assert ps.unknown_placeholders(text) == ["[PROVIDER_9]"]


def test_round_trip_restores_the_canonical_spelling():
    ps = Pseudonymizer()
    ps.register("DATE", "Mar 5, 2024", matches=("2024-03-05",))
    assert ps.restore(ps.apply("on 2024-03-05")) == "on Mar 5, 2024"


def test_sensitive_values_include_blocked_values_and_all_spellings():
    ps = Pseudonymizer()
    ps.register("DATE", "Mar 5, 2024", matches=("2024-03-05",))
    ps.block("Patient2", "x")
    values = ps.sensitive_values()
    assert {"Mar 5, 2024", "2024-03-05", "Patient2"} <= values
    assert "x" not in values  # too short to guard without blocking ordinary text


def test_apply_with_nothing_registered_changes_nothing():
    assert Pseudonymizer().apply("plain text") == "plain text"
