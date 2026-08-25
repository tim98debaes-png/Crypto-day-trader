"""Phase 23 deterministic reliability harness for paper trading.

This harness exercises paper state and observability without exchange access.
It fails closed on malformed market data, checkpoint loss, sequence gaps,
state corruption, stale heartbeats, equity/capital invariant violations, and
unexpected recovery state.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable, Optional

from paper_engine import PaperAccount
from paper_session_observability import PaperSessionObserver


@dataclass(frozen=True)
class ReliabilityViolation:
    check: str
    detail: str


@dataclass(frozen=True)
class ReliabilityReport:
    passed: bool
    events: int
    checkpoints: int
    restarts: int
    violations: tuple[ReliabilityViolation, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "events": self.events,
            "checkpoints": self.checkpoints,
            "restarts": self.restarts,
            "violations": [asdict(v) for v in self.violations],
        }


class PaperReliabilityHarness:
    """Run bounded deterministic reliability scenarios around paper state."""

    def __init__(self, account_factory: Callable[[], PaperAccount], state_path: str,
                 stale_after_seconds: int = 900):
        self.account_factory = account_factory
        self.state_path = state_path
        self.stale_after_seconds = stale_after_seconds

    def run(
        self,
        markets: Iterable[dict[str, Any]],
        *,
        restart_after: Optional[int] = None,
        restart_points: Optional[Iterable[int]] = None,
        expected_capital: Optional[float] = None,
        active_candidate_id: Optional[str] = None,
    ) -> ReliabilityReport:
        account = self.account_factory()
        observer = PaperSessionObserver(
            stale_after_seconds=self.stale_after_seconds,
            state_path=self.state_path,
        )
        violations: list[ReliabilityViolation] = []
        events = list(markets)
        restart_set = set(restart_points or ())
        if restart_after is not None:
            restart_set.add(int(restart_after))
        restarts = 0
        previous_equity: Optional[float] = None
        expected_capital = account.capital if expected_capital is None else float(expected_capital)
        valid_events = 0

        for index, market in enumerate(events, start=1):
            if not isinstance(market, dict) or "price" not in market or "symbol" not in market:
                violations.append(ReliabilityViolation("market_schema", f"event {index} is invalid"))
                continue
            try:
                price = float(market["price"])
            except (TypeError, ValueError):
                violations.append(ReliabilityViolation("market_price", f"event {index} is not numeric"))
                continue
            if price <= 0:
                violations.append(ReliabilityViolation("market_price", f"event {index} has non-positive price"))
                continue

            valid_events += 1
            equity = account.equity(price)
            summary = {
                "equity": equity,
                "closed_trades": len([e for e in account.audit_log if e.get("event") == "CLOSE"]),
                "profit_factor": self._profit_factor(account),
                "return_pct": (equity / expected_capital - 1.0) * 100.0,
                "max_drawdown_pct": self._max_drawdown(account, expected_capital),
                "open_positions": int(account.position is not None),
                "monitor_status": "HEALTHY",
            }
            try:
                observer.heartbeat(
                    summary,
                    active_candidate_id=active_candidate_id,
                    timestamp=market.get("timestamp"),
                )
            except (TypeError, ValueError, OSError) as exc:
                violations.append(ReliabilityViolation("checkpoint_write", f"event {index}: {exc}"))

            if equity < 0:
                violations.append(ReliabilityViolation("equity_invariant", f"event {index}: negative equity"))
            if previous_equity is not None and not isinstance(equity, float):
                violations.append(ReliabilityViolation("equity_type", f"event {index}: invalid equity type"))
            previous_equity = equity

            if index in restart_set:
                expected_sequence = observer.checkpoints[-1].sequence if observer.checkpoints else 0
                expected_candidate = observer.checkpoints[-1].active_candidate_id if observer.checkpoints else active_candidate_id
                try:
                    observer = PaperSessionObserver(
                        stale_after_seconds=self.stale_after_seconds,
                        state_path=self.state_path,
                    )
                    restarts += 1
                    if not observer.checkpoints:
                        violations.append(ReliabilityViolation("restart_recovery", f"event {index}: no checkpoint restored"))
                    elif observer.checkpoints[-1].sequence != expected_sequence:
                        violations.append(ReliabilityViolation("restart_sequence", f"event {index}: expected {expected_sequence}, got {observer.checkpoints[-1].sequence}"))
                    elif observer.checkpoints[-1].active_candidate_id != expected_candidate:
                        violations.append(ReliabilityViolation("restart_candidate", f"event {index}: active candidate identity changed"))
                except Exception as exc:
                    violations.append(ReliabilityViolation("restart_recovery", str(exc)))

        try:
            expected_checkpoints = valid_events
            actual_checkpoints = len(observer.checkpoints)
            if actual_checkpoints != expected_checkpoints:
                violations.append(ReliabilityViolation("checkpoint_completeness", f"expected {expected_checkpoints}, got {actual_checkpoints}"))
            if observer.checkpoints and observer.checkpoints[-1].sequence != actual_checkpoints:
                violations.append(ReliabilityViolation("checkpoint_sequence", "final sequence does not equal checkpoint count"))
            health = observer.health(now=events[-1].get("timestamp") if events and isinstance(events[-1], dict) else None)
            if health["status"] in {"STALE", "INVALID"}:
                violations.append(ReliabilityViolation("final_health", health["status"]))
        except Exception as exc:
            violations.append(ReliabilityViolation("final_health", str(exc)))

        if abs(account.capital - expected_capital) > 1e-9:
            violations.append(ReliabilityViolation("capital_invariant", "account capital changed"))

        return ReliabilityReport(
            passed=not violations,
            events=len(events),
            checkpoints=len(observer.checkpoints),
            restarts=restarts,
            violations=tuple(violations),
        )

    @staticmethod
    def _profit_factor(account: PaperAccount) -> float:
        profits = sum(float(e.get("pnl", 0.0)) for e in account.audit_log if e.get("event") == "CLOSE" and float(e.get("pnl", 0.0)) > 0)
        losses = abs(sum(float(e.get("pnl", 0.0)) for e in account.audit_log if e.get("event") == "CLOSE" and float(e.get("pnl", 0.0)) < 0))
        return profits / losses if losses else (float("inf") if profits else 0.0)

    @staticmethod
    def _max_drawdown(account: PaperAccount, initial: float) -> float:
        curve = [initial]
        for event in account.audit_log:
            if event.get("event") == "CLOSE":
                curve.append(curve[-1] + float(event.get("pnl", 0.0)))
        peak = curve[0]
        drawdown = 0.0
        for value in curve:
            peak = max(peak, value)
            if peak > 0:
                drawdown = max(drawdown, (peak - value) / peak * 100.0)
        return drawdown
