"""Single entry point for the deterministic analysis: parsed EOB in, facts and flags out."""
from pydantic import BaseModel, ConfigDict

from eob.flags import Flag, Thresholds, detect_flags
from eob.models import EobSummary
from eob.money import Check, MoneyView, build_money_view, check_consistency


class Analysis(BaseModel):
    model_config = ConfigDict(frozen=True)

    money: MoneyView
    checks: list[Check]
    flags: list[Flag]
    parse_warnings: list[str]


def analyze(eob: EobSummary, thresholds: Thresholds | None = None) -> Analysis:
    money = build_money_view(eob)
    return Analysis(
        money=money,
        checks=check_consistency(eob, money),
        flags=detect_flags(eob, money, thresholds or Thresholds()),
        parse_warnings=list(eob.parse_warnings),
    )
