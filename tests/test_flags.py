from datetime import date
from decimal import Decimal

from eob.engine import analyze
from eob.flags import Thresholds
from eob.models import AmountSet, EobLine, EobSummary

FORBIDDEN = [
    "error", "wrong", "mistake", "incorrect", "overcharg", "fraud", "illegal",
    "refund", "don't pay", "do not pay", "should not pay",
]


def make_eob(**kwargs) -> EobSummary:
    return EobSummary(eob_id="t1", **kwargs)


def line(sequence: int, code: str | None = "99213", day: date = date(2024, 3, 1), **amounts) -> EobLine:
    return EobLine(sequence=sequence, service_code=code, service_date=day, amounts=AmountSet(**amounts))


def codes(eob: EobSummary) -> list[str]:
    return [flag.code for flag in analyze(eob).flags]


def test_charge_reversal_recharge_nets_to_one_and_is_not_a_duplicate():
    eob = make_eob(lines=[
        line(1, submitted=Decimal("68.8")),
        line(2, submitted=Decimal("-68.8")),
        line(3, submitted=Decimal("68.8")),
    ])
    assert codes(eob) == ["claim_has_reversals"]


def test_two_identical_charges_are_flagged_as_a_question():
    eob = make_eob(lines=[line(1, submitted=Decimal(100)), line(2, submitted=Decimal(100))])
    flags = analyze(eob).flags
    assert [flag.code for flag in flags] == ["possible_duplicate_line"]
    assert flags[0].severity == "question"
    assert flags[0].line_sequences == [1, 2]
    assert "2 times" in flags[0].detail
    assert "$100.00" in flags[0].detail


def test_three_identical_charges_report_three():
    eob = make_eob(lines=[line(number, submitted=Decimal(100)) for number in (1, 2, 3)])
    flags = analyze(eob).flags
    assert "3 times" in flags[0].detail


def test_same_service_on_different_days_is_not_flagged():
    eob = make_eob(lines=[
        line(1, submitted=Decimal(100)),
        line(2, day=date(2024, 3, 2), submitted=Decimal(100)),
    ])
    assert codes(eob) == []


def test_lines_without_a_service_code_are_ignored():
    eob = make_eob(lines=[line(1, code=None, submitted=Decimal(100)), line(2, code=None, submitted=Decimal(100))])
    assert codes(eob) == []


def test_a_single_line_is_never_a_duplicate():
    assert codes(make_eob(lines=[line(1, submitted=Decimal(100))])) == []


def test_noncovered_amount_is_flagged_with_its_line():
    eob = make_eob(
        totals=AmountSet(noncovered=Decimal("224.11")),
        lines=[line(4, submitted=Decimal("751.2"), noncovered=Decimal("224.11"))],
    )
    flags = analyze(eob).flags
    assert [flag.code for flag in flags] == ["noncovered_amount"]
    assert "$224.11" in flags[0].detail
    assert flags[0].line_sequences == [4]


def test_high_share_mostly_explained_by_deductible_is_info():
    eob = make_eob(totals=AmountSet(eligible=Decimal(100), deductible=Decimal(100), member_liability=Decimal(100)))
    flags = analyze(eob).flags
    assert [(flag.code, flag.severity) for flag in flags] == [("high_patient_share", "info")]
    assert "100%" in flags[0].detail
    assert "$100.00 deductible" in flags[0].detail


def test_high_share_without_itemization_is_a_question():
    eob = make_eob(totals=AmountSet(eligible=Decimal(100), member_liability=Decimal(80)))
    flags = analyze(eob).flags
    assert [(flag.code, flag.severity) for flag in flags] == [("high_patient_share", "question")]


def test_small_balances_are_not_flagged_even_at_a_high_share():
    eob = make_eob(totals=AmountSet(eligible=Decimal(20), member_liability=Decimal(15)))
    assert codes(eob) == []


def test_low_share_is_not_flagged():
    eob = make_eob(totals=AmountSet(eligible=Decimal(1000), member_liability=Decimal(100)))
    assert codes(eob) == []


def test_thresholds_can_be_overridden():
    eob = make_eob(totals=AmountSet(eligible=Decimal(100), member_liability=Decimal(80)))
    assert analyze(eob, Thresholds(share_threshold=Decimal("0.9"))).flags == []


def test_unitemized_amount_is_flagged():
    eob = make_eob(totals=AmountSet(eligible=Decimal(500), member_liability=Decimal(100), deductible=Decimal(40)))
    flags = analyze(eob).flags
    assert [flag.code for flag in flags] == ["unitemized_patient_amount"]
    assert "$60.00" in flags[0].detail


def test_fully_itemized_responsibility_is_not_flagged():
    eob = make_eob(totals=AmountSet(
        eligible=Decimal(500), member_liability=Decimal(100), deductible=Decimal(40), copay=Decimal(60)
    ))
    assert codes(eob) == []


def test_computed_responsibility_is_never_called_unitemized():
    assert codes(make_eob(totals=AmountSet(deductible=Decimal(40)))) == []


def test_reversal_lines_get_an_info_flag():
    flags = analyze(make_eob(lines=[line(1, submitted=Decimal(-10))])).flags
    assert [(flag.code, flag.severity) for flag in flags] == [("claim_has_reversals", "info")]


def kitchen_sink() -> EobSummary:
    return make_eob(
        lines=[
            line(1, submitted=Decimal(100)),
            line(2, submitted=Decimal(100)),
            line(3, code="97110", submitted=Decimal(-10)),
        ],
        totals=AmountSet(
            eligible=Decimal(200),
            benefit=Decimal(50),
            member_liability=Decimal(150),
            deductible=Decimal(20),
            noncovered=Decimal(30),
        ),
    )


def test_flags_are_ordered_questions_first_then_info():
    flags = analyze(kitchen_sink()).flags
    assert [flag.code for flag in flags] == [
        "high_patient_share",
        "noncovered_amount",
        "possible_duplicate_line",
        "unitemized_patient_amount",
        "claim_has_reversals",
    ]


def test_wording_is_safe_and_always_says_who_to_ask():
    analysis = analyze(kitchen_sink())
    texts = [f"{flag.title} {flag.detail} {flag.ask}" for flag in analysis.flags]
    texts += [check.message for check in analysis.checks]
    for text in texts:
        lowered = text.lower()
        for word in FORBIDDEN:
            assert word not in lowered, f"'{word}' found in: {text}"
    for flag in analysis.flags:
        ask = flag.ask.lower()
        assert "insurer" in ask or "provider" in ask
