"""Belgian tax/compliance bookkeeping helpers.

This module is deliberately a calculation/record-keeping layer, not tax advice.
It keeps auditable transaction data, applies configurable Belgian TOB rules only
when an instrument is marked as TOB-applicable, tracks EUR values and fees, and
produces compliance-oriented exports. Tax classification of crypto income is
left as an explicit review status because the correct Belgian treatment depends
on the taxpayer's facts and legal classification.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

D = Decimal
CENT = D("0.01")


@dataclass(frozen=True)
class TaxRule:
    name: str
    rate: Decimal
    max_tax: Optional[Decimal] = None


# Belgian TOB rates are configurable because applicability depends on instrument.
TOB_RULES = {
    "0.12": TaxRule("TOB_0_12", D("0.0012")),
    "0.35": TaxRule("TOB_0_35", D("0.0035")),
    "1.32": TaxRule("TOB_1_32", D("0.0132")),
}


@dataclass
class TaxTransaction:
    timestamp: str
    venue: str
    asset: str
    side: str
    quantity: Decimal
    price_eur: Decimal
    gross_eur: Decimal
    fee_eur: Decimal
    tob_applicable: bool = False
    tob_rate: Optional[Decimal] = None
    tob_eur: Decimal = D("0")
    realized_pnl_eur: Optional[Decimal] = None
    tax_classification: str = "REVIEW_REQUIRED"
    transaction_type: str = "TRADE"
    reference: str = ""


class BelgianTaxLedger:
    """Auditable ledger for Belgian tax reporting preparation."""

    def __init__(self) -> None:
        self.transactions: list[TaxTransaction] = []

    @staticmethod
    def _money(value: Decimal | float | int) -> Decimal:
        return D(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)

    def add_trade(
        self,
        *,
        timestamp: datetime | str,
        venue: str,
        asset: str,
        side: str,
        quantity: Decimal | float,
        price_eur: Decimal | float,
        fee_eur: Decimal | float = D("0"),
        tob_applicable: bool = False,
        tob_rate: str | None = None,
        realized_pnl_eur: Decimal | float | None = None,
        reference: str = "",
    ) -> TaxTransaction:
        ts = timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp)
        qty = D(str(quantity))
        price = D(str(price_eur))
        gross = self._money(qty * price)
        fee = self._money(fee_eur)
        tob = D("0")
        rate = None
        if tob_applicable:
            if tob_rate not in TOB_RULES:
                raise ValueError("TOB rate must be one of 0.12, 0.35 or 1.32")
            rate = TOB_RULES[tob_rate].rate
            tob = self._money(gross * rate)
        tx = TaxTransaction(
            timestamp=ts, venue=venue, asset=asset, side=side.upper(),
            quantity=qty, price_eur=price, gross_eur=gross, fee_eur=fee,
            tob_applicable=tob_applicable, tob_rate=rate, tob_eur=tob,
            realized_pnl_eur=None if realized_pnl_eur is None else self._money(realized_pnl_eur),
            reference=reference,
        )
        self.transactions.append(tx)
        return tx

    def add_transfer(self, *, timestamp: datetime | str, venue: str, asset: str,
                     quantity: Decimal | float, reference: str = "") -> TaxTransaction:
        ts = timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp)
        tx = TaxTransaction(
            timestamp=ts, venue=venue, asset=asset, side="TRANSFER",
            quantity=D(str(quantity)), price_eur=D("0"), gross_eur=D("0"),
            fee_eur=D("0"), transaction_type="TRANSFER", reference=reference,
        )
        self.transactions.append(tx)
        return tx

    def realized_pnl(self) -> Decimal:
        return self._money(sum((t.realized_pnl_eur or D("0") for t in self.transactions), D("0")))

    def total_fees(self) -> Decimal:
        return self._money(sum((t.fee_eur for t in self.transactions), D("0")))

    def total_tob(self) -> Decimal:
        return self._money(sum((t.tob_eur for t in self.transactions), D("0")))

    def export_rows(self) -> list[dict]:
        rows = []
        for tx in self.transactions:
            row = asdict(tx)
            for key, value in list(row.items()):
                if isinstance(value, Decimal):
                    row[key] = str(value)
            rows.append(row)
        return rows

    def compliance_summary(self) -> dict:
        return {
            "transactions": len(self.transactions),
            "realized_pnl_eur": str(self.realized_pnl()),
            "fees_eur": str(self.total_fees()),
            "tob_eur": str(self.total_tob()),
            "tax_classification": "REVIEW_REQUIRED",
            "dac8_carf_ready": True,
            "note": "Prepared for Belgian tax review; not a determination of tax liability.",
        }


def securities_account_tax(average_value_eur: Decimal | float, reference_end: str) -> Decimal:
    """Estimate TACT for a qualifying securities account.

    Applies the official 2026 threshold/rate change: 0.15% through 31-05-2026
    and 0.30% for reference periods ending from 01-06-2026. The instrument and
    account must first be confirmed as within TACT scope.
    """
    value = D(str(average_value_eur))
    end = datetime.fromisoformat(reference_end).date()
    threshold = D("1000000")
    if value <= threshold:
        return D("0.00")
    rate = D("0.0030") if end >= datetime(2026, 6, 1).date() else D("0.0015")
    tax = (value * rate).quantize(CENT, rounding=ROUND_HALF_UP)
    cap = ((value - threshold) * D("0.10")).quantize(CENT, rounding=ROUND_HALF_UP)
    return min(tax, cap)
