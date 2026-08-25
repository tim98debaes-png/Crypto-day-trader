from prelive_safety_gate import AuthorizationStatus, PreLiveSafetyGate, SafetyLimits


def test_paper_is_allowed_and_never_live_authorized():
    decision = PreLiveSafetyGate().authorize(requested_mode="PAPER")
    assert decision.status is AuthorizationStatus.PAPER_ALLOWED
    assert decision.live_authorized is False


def test_live_defaults_to_blocked():
    decision = PreLiveSafetyGate().authorize(
        requested_mode="LIVE", environment="production", account_type="live",
        notional=100, daily_loss_pct=0,
    )
    assert decision.status is AuthorizationStatus.LIVE_BLOCKED
    assert decision.reason == "live_disabled"


def test_live_requires_every_boundary_condition():
    gate = PreLiveSafetyGate(
        {"LIVE_TRADING_ENABLED": "true"},
        SafetyLimits(max_notional=1000, max_daily_loss_pct=2),
    )
    decision = gate.authorize(
        requested_mode="LIVE", environment="production", account_type="live",
        notional=100, daily_loss_pct=0.5,
    )
    assert decision.status is AuthorizationStatus.LIVE_AUTHORIZED
    assert decision.live_authorized is True


def test_kill_switch_always_blocks():
    gate = PreLiveSafetyGate(
        {"LIVE_TRADING_ENABLED": "true"},
        SafetyLimits(max_notional=1000, max_daily_loss_pct=2),
    )
    decision = gate.authorize(
        requested_mode="LIVE", environment="production", account_type="live",
        kill_switch=True, notional=100, daily_loss_pct=0.5,
    )
    assert decision.reason == "kill_switch_active"
    assert decision.live_authorized is False


def test_ambiguous_environment_blocks():
    gate = PreLiveSafetyGate({"LIVE_TRADING_ENABLED": "true"}, SafetyLimits(1000, 2))
    decision = gate.authorize(requested_mode="LIVE", environment="paper", account_type="live", notional=100)
    assert decision.reason == "environment_not_production"


def test_notional_and_daily_loss_limits_block():
    gate = PreLiveSafetyGate({"LIVE_TRADING_ENABLED": "true"}, SafetyLimits(1000, 2))
    assert gate.authorize(requested_mode="LIVE", environment="production", account_type="live", notional=1001).reason == "notional_limit"
    assert gate.authorize(requested_mode="LIVE", environment="production", account_type="live", notional=100, daily_loss_pct=2).reason == "daily_loss_limit"


def test_invalid_mode_fails_closed():
    decision = PreLiveSafetyGate().authorize(requested_mode="SOMETHING")
    assert decision.status is AuthorizationStatus.LIVE_BLOCKED
    assert decision.live_authorized is False
