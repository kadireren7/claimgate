"""Controlled input models for Phase 2 document generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True)
class DraftDocument:
    party_name: str
    contract_amount: Decimal
    quantity: int
    delivery_date: date
    scope: str
    deliverable: str
    currency: str = "USD"
    public_fact: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.party_name, "party_name")
        _require_text(self.scope, "scope")
        _require_text(self.deliverable, "deliverable")
        _require_text(self.currency, "currency")
        if self.public_fact is not None:
            _require_text(self.public_fact, "public_fact")
        if self.contract_amount <= 0:
            raise ValueError("contract_amount must be positive")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")

    @property
    def amount_display(self) -> str:
        return f"{self.currency.upper()} {self.contract_amount:,.2f}"

    @property
    def delivery_date_display(self) -> str:
        return self.delivery_date.isoformat()
