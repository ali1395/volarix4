"""Unit tests for exit semantics configuration

Tests verify that:
1. OHLC_INTRABAR allows same-bar entry and exit (using bar high/low)
2. OPEN_ONLY prevents same-bar exit (using only bar open price)
"""

import sys
import os
import pandas as pd
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest_engine import (
    OpenPriceTickGenerator,
    BacktestBroker,
    ExitSemantics,
    TPModel,
    Tick
)


def create_test_bar_same_bar_sl_hit():
    """Create a bar that should trigger SL on same bar in OHLC mode

    Bar characteristics:
    - Open: 1.10000
    - High: 1.10050
    - Low: 1.09900 (hits SL for BUY at 1.09950)
    - Close: 1.10020

    For a BUY trade entered at open (1.10000) with SL at 1.09950:
    - OHLC_INTRABAR: Exit on same bar (low=1.09900 < SL)
    - OPEN_ONLY: No exit on same bar (open=1.10000 > SL)
    """
    return {
        'time': datetime(2025, 1, 1, 12, 0),
        'open': 1.10000,
        'high': 1.10050,
        'low': 1.09900,
        'close': 1.10020
    }


def create_test_bar_same_bar_tp_hit():
    """Create a bar that should trigger TP1 on same bar in OHLC mode

    Bar characteristics:
    - Open: 1.10000
    - High: 1.10080 (hits TP1 for BUY at 1.10070)
    - Low: 1.09980
    - Close: 1.10020

    For a BUY trade entered at open (1.10000) with TP1 at 1.10070:
    - OHLC_INTRABAR: Exit on same bar (high=1.10080 > TP1)
    - OPEN_ONLY: No exit on same bar (open=1.10000 < TP1)
    """
    return {
        'time': datetime(2025, 1, 1, 13, 0),
        'open': 1.10000,
        'high': 1.10080,
        'low': 1.09980,
        'close': 1.10020
    }


def test_ohlc_intrabar_allows_same_bar_sl_exit():
    """Test 1: OHLC_INTRABAR allows same-bar SL exit

    Scenario:
    - BUY trade enters at bar open (1.10000)
    - SL at 1.09950
    - Bar low is 1.09900 (hits SL)
    - OHLC_INTRABAR mode checks bar low
    - Trade should exit on SAME bar
    """
    print("\n" + "="*80)
    print("TEST 1: OHLC_INTRABAR allows same-bar SL exit")
    print("="*80)

    # Setup
    pip_value = 0.0001
    broker = BacktestBroker(
        pip_value=pip_value,
        spread_pips=1.0,
        commission_per_side_per_lot=7.0,
        slippage_pips=0.5,
        lot_size=1.0,
        usd_per_pip_per_lot=10.0,
        exit_semantics=ExitSemantics.OHLC_INTRABAR,
        tp_model=TPModel.FULL_CLOSE_AT_FIRST_TP
    )

    # Create test bar
    bar = create_test_bar_same_bar_sl_hit()

    # Create tick at bar open
    tick = Tick(
        timestamp=bar['time'],
        bid=bar['open'],
        ask=bar['open'] + 1.0 * pip_value,  # 1 pip spread
        bar_index=0,
        bar_data=bar,
        is_bar_open=True
    )

    # Manually create a position (simulating entry)
    # Note: In real usage, this would be done via broker.place_order() + execute_pending_orders()
    from backtest import Trade

    trade = Trade(
        entry_time=tick.timestamp,
        direction="BUY",
        entry=bar['open'],
        sl=1.09950,
        tp1=1.10070,
        tp2=1.10100,
        tp3=1.10130,
        lot_size=1.0,
        pip_value=pip_value,
        spread_pips=1.0,
        slippage_pips=0.5,
        commission_per_side_per_lot=7.0
    )

    from backtest_engine.broker import Position
    position = Position(
        position_id=1,
        trade=trade,
        remaining_volume=1.0,
        tp_levels_hit=[]
    )

    broker.state.open_positions[1] = position

    print(f"\nBar setup:")
    print(f"  Time: {bar['time']}")
    print(f"  Open: {bar['open']:.5f}")
    print(f"  High: {bar['high']:.5f}")
    print(f"  Low: {bar['low']:.5f}")
    print(f"  Close: {bar['close']:.5f}")

    print(f"\nTrade setup:")
    print(f"  Direction: BUY")
    print(f"  Entry: {trade.entry:.5f} (at bar open)")
    print(f"  SL: {trade.sl:.5f}")
    print(f"  Bar Low: {bar['low']:.5f}")
    print(f"  SL Hit? {bar['low'] <= trade.sl}")

    print(f"\nConfiguration:")
    print(f"  Exit semantics: {broker.exit_semantics.value}")
    print(f"  Expects same-bar exit: YES")

    # Process tick
    broker.on_tick(tick)

    # Verify exit
    assert len(broker.state.closed_trades) == 1, "Trade should have exited"
    assert broker.state.closed_trades[0].exit_reason == "SL hit"
    assert broker.state.closed_trades[0].exit_time == tick.timestamp, "Should exit on SAME bar"

    print(f"\nResult:")
    print(f"  Closed trades: {len(broker.state.closed_trades)}")
    print(f"  Exit reason: {broker.state.closed_trades[0].exit_reason}")
    print(f"  Exit time: {broker.state.closed_trades[0].exit_time}")
    print(f"  Entry time: {broker.state.closed_trades[0].entry_time}")
    print(f"  Same bar exit: {broker.state.closed_trades[0].exit_time == broker.state.closed_trades[0].entry_time}")

    print("\n[PASS] OHLC_INTRABAR allows same-bar SL exit")
    print("="*80)


def test_open_only_prevents_same_bar_sl_exit():
    """Test 2: OPEN_ONLY prevents same-bar SL exit

    Scenario:
    - BUY trade enters at bar open (1.10000)
    - SL at 1.09950
    - Bar low is 1.09900 (hits SL intrabar)
    - But bar open is 1.10000 (above SL)
    - OPEN_ONLY mode only checks bar open
    - Trade should NOT exit on same bar
    """
    print("\n" + "="*80)
    print("TEST 2: OPEN_ONLY prevents same-bar SL exit")
    print("="*80)

    # Setup
    pip_value = 0.0001
    broker = BacktestBroker(
        pip_value=pip_value,
        spread_pips=1.0,
        commission_per_side_per_lot=7.0,
        slippage_pips=0.5,
        lot_size=1.0,
        usd_per_pip_per_lot=10.0,
        exit_semantics=ExitSemantics.OPEN_ONLY,
        tp_model=TPModel.FULL_CLOSE_AT_FIRST_TP
    )

    # Create test bar
    bar = create_test_bar_same_bar_sl_hit()

    # Create tick at bar open
    tick = Tick(
        timestamp=bar['time'],
        bid=bar['open'],
        ask=bar['open'] + 1.0 * pip_value,  # 1 pip spread
        bar_index=0,
        bar_data=bar,
        is_bar_open=True
    )

    # Manually create a position
    from backtest import Trade

    trade = Trade(
        entry_time=tick.timestamp,
        direction="BUY",
        entry=bar['open'],
        sl=1.09950,
        tp1=1.10070,
        tp2=1.10100,
        tp3=1.10130,
        lot_size=1.0,
        pip_value=pip_value,
        spread_pips=1.0,
        slippage_pips=0.5,
        commission_per_side_per_lot=7.0
    )

    from backtest_engine.broker import Position
    position = Position(
        position_id=1,
        trade=trade,
        remaining_volume=1.0,
        tp_levels_hit=[]
    )

    broker.state.open_positions[1] = position

    print(f"\nBar setup:")
    print(f"  Time: {bar['time']}")
    print(f"  Open: {bar['open']:.5f}")
    print(f"  High: {bar['high']:.5f}")
    print(f"  Low: {bar['low']:.5f} (would hit SL intrabar)")
    print(f"  Close: {bar['close']:.5f}")

    print(f"\nTrade setup:")
    print(f"  Direction: BUY")
    print(f"  Entry: {trade.entry:.5f} (at bar open)")
    print(f"  SL: {trade.sl:.5f}")
    print(f"  Bar Open: {bar['open']:.5f} (above SL)")
    print(f"  Bar Low: {bar['low']:.5f} (below SL)")
    print(f"  SL Hit at open? {bar['open'] <= trade.sl}")

    print(f"\nConfiguration:")
    print(f"  Exit semantics: {broker.exit_semantics.value}")
    print(f"  Expects same-bar exit: NO (only checks bar open)")

    # Process tick
    broker.on_tick(tick)

    # Verify NO exit
    assert len(broker.state.closed_trades) == 0, "Trade should NOT exit (open price doesn't hit SL)"
    assert len(broker.state.open_positions) == 1, "Position should still be open"

    print(f"\nResult:")
    print(f"  Closed trades: {len(broker.state.closed_trades)}")
    print(f"  Open positions: {len(broker.state.open_positions)}")
    print(f"  Trade still open: YES")

    print("\n[PASS] OPEN_ONLY prevents same-bar SL exit (only checks bar open price)")
    print("="*80)


def test_ohlc_intrabar_allows_same_bar_tp_exit():
    """Test 3: OHLC_INTRABAR allows same-bar TP exit

    Scenario:
    - BUY trade enters at bar open (1.10000)
    - TP1 at 1.10070
    - Bar high is 1.10080 (hits TP1)
    - OHLC_INTRABAR mode checks bar high
    - Trade should exit on SAME bar
    """
    print("\n" + "="*80)
    print("TEST 3: OHLC_INTRABAR allows same-bar TP exit")
    print("="*80)

    # Setup
    pip_value = 0.0001
    broker = BacktestBroker(
        pip_value=pip_value,
        spread_pips=1.0,
        commission_per_side_per_lot=7.0,
        slippage_pips=0.5,
        lot_size=1.0,
        usd_per_pip_per_lot=10.0,
        exit_semantics=ExitSemantics.OHLC_INTRABAR,
        tp_model=TPModel.FULL_CLOSE_AT_FIRST_TP
    )

    # Create test bar
    bar = create_test_bar_same_bar_tp_hit()

    # Create tick at bar open
    tick = Tick(
        timestamp=bar['time'],
        bid=bar['open'],
        ask=bar['open'] + 1.0 * pip_value,
        bar_index=0,
        bar_data=bar,
        is_bar_open=True
    )

    # Manually create a position
    from backtest import Trade

    trade = Trade(
        entry_time=tick.timestamp,
        direction="BUY",
        entry=bar['open'],
        sl=1.09950,
        tp1=1.10070,
        tp2=1.10100,
        tp3=1.10130,
        lot_size=1.0,
        pip_value=pip_value,
        spread_pips=1.0,
        slippage_pips=0.5,
        commission_per_side_per_lot=7.0
    )

    from backtest_engine.broker import Position
    position = Position(
        position_id=1,
        trade=trade,
        remaining_volume=1.0,
        tp_levels_hit=[]
    )

    broker.state.open_positions[1] = position

    print(f"\nBar setup:")
    print(f"  Time: {bar['time']}")
    print(f"  Open: {bar['open']:.5f}")
    print(f"  High: {bar['high']:.5f}")
    print(f"  Low: {bar['low']:.5f}")
    print(f"  Close: {bar['close']:.5f}")

    print(f"\nTrade setup:")
    print(f"  Direction: BUY")
    print(f"  Entry: {trade.entry:.5f} (at bar open)")
    print(f"  TP1: {trade.tp1:.5f}")
    print(f"  Bar High: {bar['high']:.5f}")
    print(f"  TP1 Hit? {bar['high'] >= trade.tp1}")

    print(f"\nConfiguration:")
    print(f"  Exit semantics: {broker.exit_semantics.value}")
    print(f"  TP model: {broker.tp_model.value}")
    print(f"  Expects same-bar exit: YES")

    # Process tick
    broker.on_tick(tick)

    # Verify exit
    assert len(broker.state.closed_trades) == 1, "Trade should have exited at TP1"
    assert 1 in broker.state.closed_trades[0].tp_levels_hit
    assert broker.state.closed_trades[0].exit_time == tick.timestamp, "Should exit on SAME bar"

    print(f"\nResult:")
    print(f"  Closed trades: {len(broker.state.closed_trades)}")
    print(f"  TP levels hit: {broker.state.closed_trades[0].tp_levels_hit}")
    print(f"  Exit time: {broker.state.closed_trades[0].exit_time}")
    print(f"  Entry time: {broker.state.closed_trades[0].entry_time}")
    print(f"  Same bar exit: {broker.state.closed_trades[0].exit_time == broker.state.closed_trades[0].entry_time}")

    print("\n[PASS] OHLC_INTRABAR allows same-bar TP exit")
    print("="*80)


def test_open_only_prevents_same_bar_tp_exit():
    """Test 4: OPEN_ONLY prevents same-bar TP exit

    Scenario:
    - BUY trade enters at bar open (1.10000)
    - TP1 at 1.10070
    - Bar high is 1.10080 (hits TP1 intrabar)
    - But bar open is 1.10000 (below TP1)
    - OPEN_ONLY mode only checks bar open
    - Trade should NOT exit on same bar
    """
    print("\n" + "="*80)
    print("TEST 4: OPEN_ONLY prevents same-bar TP exit")
    print("="*80)

    # Setup
    pip_value = 0.0001
    broker = BacktestBroker(
        pip_value=pip_value,
        spread_pips=1.0,
        commission_per_side_per_lot=7.0,
        slippage_pips=0.5,
        lot_size=1.0,
        usd_per_pip_per_lot=10.0,
        exit_semantics=ExitSemantics.OPEN_ONLY,
        tp_model=TPModel.FULL_CLOSE_AT_FIRST_TP
    )

    # Create test bar
    bar = create_test_bar_same_bar_tp_hit()

    # Create tick at bar open
    tick = Tick(
        timestamp=bar['time'],
        bid=bar['open'],
        ask=bar['open'] + 1.0 * pip_value,
        bar_index=0,
        bar_data=bar,
        is_bar_open=True
    )

    # Manually create a position
    from backtest import Trade

    trade = Trade(
        entry_time=tick.timestamp,
        direction="BUY",
        entry=bar['open'],
        sl=1.09950,
        tp1=1.10070,
        tp2=1.10100,
        tp3=1.10130,
        lot_size=1.0,
        pip_value=pip_value,
        spread_pips=1.0,
        slippage_pips=0.5,
        commission_per_side_per_lot=7.0
    )

    from backtest_engine.broker import Position
    position = Position(
        position_id=1,
        trade=trade,
        remaining_volume=1.0,
        tp_levels_hit=[]
    )

    broker.state.open_positions[1] = position

    print(f"\nBar setup:")
    print(f"  Time: {bar['time']}")
    print(f"  Open: {bar['open']:.5f}")
    print(f"  High: {bar['high']:.5f} (would hit TP1 intrabar)")
    print(f"  Low: {bar['low']:.5f}")
    print(f"  Close: {bar['close']:.5f}")

    print(f"\nTrade setup:")
    print(f"  Direction: BUY")
    print(f"  Entry: {trade.entry:.5f} (at bar open)")
    print(f"  TP1: {trade.tp1:.5f}")
    print(f"  Bar Open: {bar['open']:.5f} (below TP1)")
    print(f"  Bar High: {bar['high']:.5f} (above TP1)")
    print(f"  TP1 Hit at open? {bar['open'] >= trade.tp1}")

    print(f"\nConfiguration:")
    print(f"  Exit semantics: {broker.exit_semantics.value}")
    print(f"  Expects same-bar exit: NO (only checks bar open)")

    # Process tick
    broker.on_tick(tick)

    # Verify NO exit
    assert len(broker.state.closed_trades) == 0, "Trade should NOT exit (open price doesn't hit TP1)"
    assert len(broker.state.open_positions) == 1, "Position should still be open"

    print(f"\nResult:")
    print(f"  Closed trades: {len(broker.state.closed_trades)}")
    print(f"  Open positions: {len(broker.state.open_positions)}")
    print(f"  Trade still open: YES")

    print("\n[PASS] OPEN_ONLY prevents same-bar TP exit (only checks bar open price)")
    print("="*80)


if __name__ == '__main__':
    print("\n" + "="*80)
    print("EXIT SEMANTICS UNIT TESTS")
    print("="*80)
    print("\nThese tests verify that:")
    print("1. OHLC_INTRABAR allows same-bar entry and exit (using bar high/low)")
    print("2. OPEN_ONLY prevents same-bar exit (using only bar open price)")
    print("\nThis is NOT a bug - it's a fundamental semantic difference:")
    print("- Legacy backtest uses OHLC_INTRABAR (optimistic)")
    print("- MT5 'Open prices only' uses OPEN_ONLY (conservative)")
    print("="*80)

    try:
        test_ohlc_intrabar_allows_same_bar_sl_exit()
        test_open_only_prevents_same_bar_sl_exit()
        test_ohlc_intrabar_allows_same_bar_tp_exit()
        test_open_only_prevents_same_bar_tp_exit()

        print("\n" + "="*80)
        print("ALL TESTS PASSED")
        print("="*80)

    except AssertionError as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
