"""Unit tests for the risk manager."""
from risk.risk_manager import RiskLimits, RiskManager


def _rm(**kw):
    return RiskManager(RiskLimits(**kw))


def test_target_qty_respects_per_asset_cap():
    rm = _rm(max_position_pct=0.15)
    # 100k equity, 15% cap = 15k / $100 = 150 shares
    assert rm.target_qty(equity=100_000, price=100) == 150


def test_target_qty_zero_on_bad_inputs():
    rm = _rm()
    assert rm.target_qty(0, 100) == 0
    assert rm.target_qty(100_000, 0) == 0


def test_check_order_blocks_oversized_position():
    rm = _rm(max_position_pct=0.15, max_gross_exposure=1.0)
    ok, reason = rm.check_order(
        "AAPL", qty=1000, price=100, equity=100_000,
        current_positions={}, current_gross=0,
    )
    assert not ok and "per-asset" in reason


def test_check_order_allows_within_limits():
    rm = _rm(max_position_pct=0.15, max_gross_exposure=1.0)
    ok, reason = rm.check_order(
        "AAPL", qty=100, price=100, equity=100_000,
        current_positions={}, current_gross=0,
    )
    assert ok and reason == "ok"


def test_check_order_blocks_when_max_positions_reached():
    rm = _rm(max_position_pct=0.5, max_positions=2)
    positions = {"AAPL": 10, "MSFT": 5}
    ok, reason = rm.check_order(
        "GOOG", qty=1, price=100, equity=100_000,
        current_positions=positions, current_gross=0,
    )
    assert not ok and "max positions" in reason


def test_check_order_blocks_gross_exposure():
    rm = _rm(max_position_pct=1.0, max_gross_exposure=1.0)
    ok, reason = rm.check_order(
        "AAPL", qty=100, price=100, equity=100_000,
        current_positions={}, current_gross=95_000,
    )
    assert not ok and "gross exposure" in reason


def test_stop_loss_and_take_profit():
    rm = _rm(stop_loss_pct=0.05, take_profit_pct=0.10)
    # long position down 6% -> stop
    hit, reason = rm.should_exit(entry_price=100, current_price=94, side=1)
    assert hit and reason == "stop_loss"
    # long position up 11% -> take profit
    hit, reason = rm.should_exit(entry_price=100, current_price=111, side=1)
    assert hit and reason == "take_profit"
    # short position: price falling is a profit
    hit, reason = rm.should_exit(entry_price=100, current_price=88, side=-1)
    assert hit and reason == "take_profit"
