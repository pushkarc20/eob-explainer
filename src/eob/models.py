"""Typed, minimal view of an ExplanationOfBenefit.

DESIGN RULE (privacy by schema): this model is an allow-list. Anything not declared
here is dropped by the parser and can never reach the rules engine, the UI, or a
cloud model. Deliberately NOT parsed: patient name/ID/address/birth date, member IDs,
provider IDs (NPI), diagnoses, and free-text notes.
"""
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AmountSet(BaseModel):
    """Dollar amounts for one line or for a whole claim.

    A missing amount is None, never 0: 'not reported' and '$0' are different facts.
    Field names mirror the FHIR adjudication category codes seen in real examples.
    The parser records what is reported; it does not interpret it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    submitted: Decimal | None = None  # billed by the provider
    eligible: Decimal | None = None  # allowed amount
    benefit: Decimal | None = None
    deductible: Decimal | None = None
    copay: Decimal | None = None
    noncovered: Decimal | None = None
    member_liability: Decimal | None = None
    paid_to_provider: Decimal | None = None
    paid_by_patient: Decimal | None = None
    other: dict[str, Decimal] = Field(default_factory=dict)  # categories not recognized yet

    def is_empty(self) -> bool:
        names = [name for name in type(self).model_fields if name != "other"]
        return not self.other and all(getattr(self, name) is None for name in names)


class EobLine(BaseModel):
    """One billed service line."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: int
    service_code: str | None = None  # e.g. a CPT/HCPCS code
    service_code_system: str | None = None
    service_display: str | None = None
    service_date: date | None = None
    quantity: Decimal | None = None
    amounts: AmountSet = Field(default_factory=AmountSet)
    statuses: dict[str, str] = Field(default_factory=dict)  # e.g. benefitpaymentstatus -> other


class EobSummary(BaseModel):
    """What the explainer is allowed to know about one claim."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    eob_id: str
    claim_id: str | None = None  # identifying: kept local, handled by the privacy layer later
    claim_type: str | None = None
    claim_subtype: str | None = None
    status: str | None = None
    outcome: str | None = None
    use: str | None = None
    billable_start: date | None = None
    billable_end: date | None = None
    insurer_display: str | None = None
    provider_display: str | None = None
    header_amounts: AmountSet = Field(default_factory=AmountSet)
    header_statuses: dict[str, str] = Field(default_factory=dict)  # e.g. billingnetworkstatus
    totals: AmountSet = Field(default_factory=AmountSet)
    payment_amount: Decimal | None = None
    payment_adjustment: Decimal | None = None
    lines: list[EobLine] = Field(default_factory=list)
    parse_warnings: list[str] = Field(default_factory=list)  # never contains personal data
