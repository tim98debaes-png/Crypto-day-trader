"""Connect validated strategy signals to the paper execution loop."""

from paper_execution import PaperExecutionLoop
from signal_engine import generate_signal


class PaperStrategyRunner:
    def __init__(self, execution_loop: PaperExecutionLoop):
        self.execution_loop = execution_loop

    def process(self, market: dict, candidate: dict, indicators: dict) -> dict:
        signal = generate_signal(candidate, indicators)
        if signal.action == "WAIT":
            self.execution_loop._record_equity(float(market["price"]))
            return {"action": "WAIT", "reason": signal.reason}

        execution_market = dict(market)
        execution_market["direction"] = signal.direction
        execution_market["stop_distance"] = signal.stop_distance
        execution_market["rr"] = signal.rr
        return self.execution_loop.on_market(execution_market, candidate=candidate)
