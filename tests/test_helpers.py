from datetime import date
from decimal import Decimal

from healthcore.fhir.helpers import (
    all_codes,
    load_resource,
    parse_fhir_date,
    reference_display,
    to_decimal,
)


def test_to_decimal_handles_common_inputs():
    assert to_decimal("258.91") == Decimal("258.91")
    assert to_decimal(5) == Decimal(5)
    assert to_decimal(0.1) == Decimal("0.1")
    assert to_decimal(None) is None
    assert to_decimal(True) is None
    assert to_decimal("not a number") is None
    assert to_decimal("NaN") is None


def test_parse_fhir_date():
    assert parse_fhir_date("2019-07-02") == date(2019, 7, 2)
    assert parse_fhir_date("2019-07-02T10:00:00+00:00") == date(2019, 7, 2)
    assert parse_fhir_date("2019") is None
    assert parse_fhir_date("2019-13-45") is None
    assert parse_fhir_date(None) is None


def test_load_resource_keeps_money_exact(tmp_path):
    path = tmp_path / "x.json"
    path.write_text('{"amount": 0.1}')
    value = load_resource(path)["amount"]
    assert isinstance(value, Decimal)
    assert value == Decimal("0.1")


def test_all_codes_and_reference_display():
    concept = {"coding": [{"code": "a"}, {"system": "s"}, {"code": "b"}]}
    assert all_codes(concept) == ["a", "b"]
    assert all_codes(None) == []
    assert reference_display({"reference": "Organization/1", "display": "Acme"}) == "Acme"
    assert reference_display({"reference": "Organization/1"}) is None
