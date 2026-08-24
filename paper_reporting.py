"""Reporting helpers for the simulation-only paper portfolio.

The reporting layer is deliberately read-only: it never changes portfolio state
and never places orders. It turns the persisted paper portfolio into stable,
JSON/CSV-friendly report structures for the dashboard and exports.
"""

from datetime import datetime, timezone
from math import isfinite


def _json_number(value):
    """Return a JSON-safe numeric value."""
    if isinstance(value, float) and not isfinite(value):
        return None
    return value


def build_report(portfolio, marks=None):
    """Build a read-only report snapshot from a PaperPortfolio."""
    summary = portfolio.summary(marks or {})
    events = portfolio.audit_log()

    open_positions = []
    for symbol, account in portfolio.accounts.items():
        position = account.position
        if position is None:
            continue
        open_positions.append(
            {
                "symbol": symbol,
                "direction": position.direction,
                "entry_price": position.entry_price,
                "quantity": position.quantity,
                "stop_price": position.stop_price,
                "target_price": position.target_price,
                "entry_fee": position.entry_fee,
                "opened_at": position.opened_at,
            }
        )

    closed_trades = [
        dict(event)
        for event in events
        if event.get("event") == "CLOSE"
    ]

    safe_summary = {
        key: _json_number(value)
        for key, value in summary.items()
    }

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "simulation_only": True,
        "summary": safe_summary,
        "open_positions": open_positions,
        "closed_trades": closed_trades,
        "equity_history": [float(value) for value in portfolio.equity_history],
    }


def closed_trade_rows(report):
    """Return stable, flat rows suitable for CSV export."""
    rows = []
    for event in report.get("closed_trades", []):
        rows.append(
            {
                "timestamp": event.get("timestamp", ""),
                "symbol": event.get("symbol", ""),
                "direction": event.get("direction", ""),
                "exit_price": event.get("price", 0.0),
                "quantity": event.get("quantity", 0.0),
                "gross_pnl": event.get("gross_pnl", 0.0),
                "entry_fee": event.get("entry_fee", 0.0),
                "exit_fee": event.get("exit_fee", 0.0),
                "pnl": event.get("pnl", 0.0),
                "reason": event.get("reason", ""),
            }
        )
    return rows


def summary_rows(report):
    """Return key performance metrics as label/value rows."""
    summary = report.get("summary", {})
    keys = [
        ("Equity", "equity"),
        ("Return %", "return_pct"),
        ("Peak equity", "peak_equity"),
        ("Current drawdown %", "current_drawdown_pct"),
        ("Maximum drawdown %", "max_drawdown_pct"),
        ("Closed trades", "closed_trades"),
        ("Wins", "wins"),
        ("Losses", "losses"),
        ("Win rate %", "win_rate_pct"),
        ("Profit factor", "profit_factor"),
        ("Expectancy", "expectancy"),
        ("Best trade", "best_trade"),
        ("Worst trade", "worst_trade"),
        ("Gross profit", "gross_profit"),
        ("Gross loss", "gross_loss"),
        ("Total fees", "total_fees"),
        ("Payoff ratio", "payoff_ratio"),
        ("LONG trades", "long_trades"),
        ("SHORT trades", "short_trades"),
    ]
    return [
        {"metric": label, "value": summary.get(key, 0.0)}
        for label, key in keys
    ]
