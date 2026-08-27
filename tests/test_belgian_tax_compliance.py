from decimal import Decimal

from belgian_tax_compliance import BelgianTaxLedger, securities_account_tax


def test_crypto_trade_is_auditable_and_tax_classification_requires_review():
    ledger = BelgianTaxLedger()
    tx = ledger.add_trade(
        timestamp="2026-08-27T12:00:00+00:00",
        venue="Bitvavo",
        asset="BTC",
        side="buy",
        quantity=0.01,
        price_eur=100000,
        fee_eur=1.50,
        reference="T-1",
    )
    assert tx.gross_eur == Decimal("1000.00")
    assert tx.tob_eur == Decimal("0")
    assert tx.tax_classification == "REVIEW_REQUIRED"
    assert ledger.compliance_summary()["dac8_carf_ready"] is True


def test_tob_is_only_applied_when_explicitly_marked():
    ledger = BelgianTaxLedger()
    tx = ledger.add_trade(
        timestamp="2026-08-27T12:00:00+00:00",
        venue="Broker",
        asset="ETF",
        side="buy",
        quantity=10,
        price_eur=100,
        tob_applicable=True,
        tob_rate="0.35",
    )
    assert tx.tob_eur == Decimal("3.50")


def test_securities_account_tax_2026_rate_and_threshold():
    assert securities_account_tax(1_000_000, "2026-08-31") == Decimal("0.00")
    assert securities_account_tax(1_010_000, "2026-08-31") == Decimal("30.00")


def test_transfer_is_preserved_without_being_treated_as_a_trade():
    ledger = BelgianTaxLedger()
    tx = ledger.add_transfer(
        timestamp="2026-08-27T12:00:00+00:00",
        venue="Bitvavo",
        asset="BTC",
        quantity=0.5,
        reference="wallet-transfer",
    )
    assert tx.transaction_type == "TRANSFER"
    assert ledger.compliance_summary()["transactions"] == 1
