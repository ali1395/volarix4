"""Minimal parity test with detailed debug tracing

Compares legacy vs event-driven execution bar-by-bar to diagnose timing discrepancies.
"""

import sys
import os
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.backtest import run_backtest, fetch_ohlc


def trace_legacy_execution(df, start_bar, num_bars):
    """Trace legacy backtest execution bar-by-bar

    Returns list of events: [(bar_idx, bar_time, event_type, details), ...]
    """
    # Run legacy backtest with minimal config
    result = run_backtest(
        df=df,
        bars=num_bars,
        lookback_bars=start_bar,
        verbose=False,
        use_event_loop=False
    )

    trades = result.get('trades', [])

    # Extract trade events
    events = []
    for trade in trades:
        # Find the bar index for this trade
        for i in range(len(df)):
            if df.iloc[i]['time'] == trade.entry_time:
                events.append({
                    'bar_index': i,
                    'bar_time': trade.entry_time,
                    'event': 'TRADE_ENTRY',
                    'direction': trade.direction,
                    'entry_price': trade.entry,
                    'raw_entry': trade.entry_raw,
                    'bar_open': df.iloc[i]['open'],
                    'exit_reason': trade.exit_reason,
                    'pnl': trade.pnl_after_costs
                })
                break

    return events, result


def trace_event_execution(df, start_bar, num_bars):
    """Trace event-driven backtest execution bar-by-bar

    Returns list of events with detailed tick/order/position info
    """
    # Instrument the event-driven components to capture events
    from backtest_engine import (
        OpenPriceTickGenerator,
        BacktestBroker,
        Volarix4EA,
        BacktestEngine
    )

    pip_value = 0.0001  # EURUSD

    config = {
        'symbol': 'EURUSD',
        'timeframe': 'H1',
        'bars': num_bars,
        'lookback_bars': start_bar,
        'pip_value': pip_value,
        'spread_pips': 1.0,
        'commission_per_side_per_lot': 7.0,
        'slippage_pips': 0.5,
        'lot_size': 1.0,
        'usd_per_pip_per_lot': 10.0,
        'starting_balance_usd': 10000.0,
        'min_confidence': 0.60,
        'broken_level_cooldown_hours': 48.0,
        'broken_level_break_pips': 15.0,
        'min_edge_pips': 4.0,
        'enable_confidence_filter': True,
        'enable_broken_level_filter': True,
        'enable_session_filter': True,
        'enable_trend_filter': True,
        'enable_signal_cooldown': True,
        'signal_cooldown_hours': 2.0,
        'sr_cache': None,
        'df': df,
        'max_positions': 1,
    }

    tick_generator = OpenPriceTickGenerator(df=df, pip_value=pip_value)
    broker = BacktestBroker(
        spread_pips=config['spread_pips'],
        commission_per_side_per_lot=config['commission_per_side_per_lot'],
        slippage_pips=config['slippage_pips'],
        lot_size=config['lot_size'],
        usd_per_pip_per_lot=config['usd_per_pip_per_lot'],
        pip_value=pip_value
    )
    ea = Volarix4EA(broker=broker, config=config)

    # Manually run event loop with tracing
    ea.on_init()

    events = []

    for tick in tick_generator.generate_ticks(start_index=start_bar):
        bar_idx = tick.bar_index
        bar_time = tick.timestamp
        bar_data = tick.bar_data

        # Log tick arrival
        event = {
            'bar_index': bar_idx,
            'bar_time': bar_time,
            'bar_open': bar_data['open'],
            'bar_high': bar_data['high'],
            'bar_low': bar_data['low'],
            'bar_close': bar_data['close'],
            'tick_price': tick.bid,
            'is_bar_open': tick.is_bar_open,
            'positions_before': broker.get_position_count(),
            'pending_orders_before': len(broker.state.pending_orders),
        }

        # Broker checks SL/TP
        broker.on_tick(tick)

        # EA processes tick
        ea_state_before = len(broker.state.pending_orders)
        ea.on_tick(tick)
        ea_state_after = len(broker.state.pending_orders)

        event['order_placed'] = (ea_state_after > ea_state_before)
        if event['order_placed']:
            # Get the order details
            order = broker.state.pending_orders[-1]
            event['order_entry_bar_index'] = order.entry_bar_index
            event['order_direction'] = order.direction

        # Broker executes pending orders
        if tick.is_bar_open:
            positions_opened = broker.execute_pending_orders(tick)
            event['positions_opened'] = len(positions_opened)

            if positions_opened:
                for pos in positions_opened:
                    trade = pos.trade
                    event['trade_entry_time'] = trade.entry_time
                    event['trade_direction'] = trade.direction
                    event['trade_entry_price'] = trade.entry
                    event['trade_raw_entry'] = trade.entry_raw
        else:
            event['positions_opened'] = 0

        event['positions_after'] = broker.get_position_count()
        event['pending_orders_after'] = len(broker.state.pending_orders)

        events.append(event)

    # Get closed trades
    trades = broker.state.closed_trades

    return events, trades


def print_debug_trace(legacy_events, event_events, df, start_bar, num_bars):
    """Print detailed debug trace comparing legacy vs event-driven"""

    print("\n" + "="*120)
    print("PARITY DEBUG TRACE")
    print("="*120)
    print(f"Test window: bars {start_bar} to {start_bar + num_bars - 1}")
    print(f"Time range: {df.iloc[start_bar]['time']} to {df.iloc[start_bar + num_bars - 1]['time']}")
    print("="*120)

    # Print bar-by-bar trace for event-driven
    print("\nEVENT-DRIVEN EXECUTION TRACE:")
    print("-"*120)
    print(f"{'Bar':<4} {'Time':<20} {'OHLC':<40} {'NewBar':<8} {'Order':<10} {'Exec':<6} {'Pos':<5}")
    print("-"*120)

    for event in event_events:
        bar_idx = event['bar_index']
        bar_time = event['bar_time'].strftime('%Y-%m-%d %H:%M')
        ohlc = f"O:{event['bar_open']:.5f} H:{event['bar_high']:.5f} L:{event['bar_low']:.5f} C:{event['bar_close']:.5f}"
        new_bar = "YES" if event['is_bar_open'] else "NO"

        order_info = ""
        if event.get('order_placed'):
            order_info = f"{event.get('order_direction', '?')}@{event.get('order_entry_bar_index', '?')}"

        exec_info = ""
        if event.get('positions_opened', 0) > 0:
            exec_info = f"EXEC"

        pos_info = f"{event['positions_before']}->{event['positions_after']}"

        print(f"{bar_idx:<4} {bar_time:<20} {ohlc:<40} {new_bar:<8} {order_info:<10} {exec_info:<6} {pos_info:<5}")

    # Print legacy trade entries
    print("\n" + "-"*120)
    print("LEGACY TRADE ENTRIES:")
    print("-"*120)
    for event in legacy_events:
        print(f"Bar {event['bar_index']}: {event['bar_time']} {event['direction']} "
              f"entry={event['entry_price']:.5f} (raw={event['raw_entry']:.5f}, bar_open={event['bar_open']:.5f}) "
              f"exit={event['exit_reason']} pnl={event['pnl']:.2f}")

    # Print event-driven trade entries
    print("\nEVENT-DRIVEN TRADE ENTRIES:")
    print("-"*120)
    for event in event_events:
        if event.get('positions_opened', 0) > 0:
            print(f"Bar {event['bar_index']}: {event.get('trade_entry_time')} {event.get('trade_direction')} "
                  f"entry={event.get('trade_entry_price'):.5f} (raw={event.get('trade_raw_entry'):.5f}, bar_open={event['bar_open']:.5f})")

    print("\n" + "="*120)


def diagnose_timing_offset():
    """Diagnose the 1-hour timing offset"""

    print("\n" + "="*120)
    print("DIAGNOSING TIMING OFFSET")
    print("="*120)

    # Fetch data
    df = fetch_ohlc('EURUSD', 'H1', 500)

    print(f"\nData fetched: {len(df)} bars")
    print(f"First bar: {df.iloc[0]['time']}")
    print(f"Last bar: {df.iloc[-1]['time']}")

    # Check timestamp alignment
    print("\nChecking timestamp alignment to hour boundaries:")
    for i in range(min(10, len(df))):
        bar_time = df.iloc[i]['time']
        if isinstance(bar_time, pd.Timestamp):
            bar_time = bar_time.to_pydatetime()

        # Check if timestamp is on hour boundary
        on_hour = (bar_time.minute == 0 and bar_time.second == 0)
        unix_time = bar_time.timestamp()
        on_3600 = (unix_time % 3600 == 0)

        print(f"  Bar {i}: {bar_time} | On hour: {on_hour} | Unix % 3600: {unix_time % 3600:.0f}")

    # Run full test to find first trade
    legacy_result = run_backtest(
        df=df,
        bars=100,
        lookback_bars=400,
        verbose=False,
        use_event_loop=False
    )

    if not legacy_result.get('trades'):
        print("\nNo trades found in legacy backtest!")
        return

    first_trade = legacy_result['trades'][0]
    print(f"\nFirst legacy trade: {first_trade.entry_time} {first_trade.direction}")

    # Find bar index
    first_trade_bar_idx = None
    for i in range(len(df)):
        if df.iloc[i]['time'] == first_trade.entry_time:
            first_trade_bar_idx = i
            break

    if first_trade_bar_idx is None:
        print("Could not find trade bar in dataframe!")
        return

    print(f"First trade bar index: {first_trade_bar_idx}")

    # Create narrow test window around first trade
    # Start 10 bars before, run for 20 bars
    test_start = max(400, first_trade_bar_idx - 10)
    test_bars = 20

    print(f"\nTest window: bars {test_start} to {test_start + test_bars - 1}")
    print(f"Time range: {df.iloc[test_start]['time']} to {df.iloc[test_start + test_bars - 1]['time']}")

    # Trace both executions
    print("\nTracing legacy execution...")
    legacy_events, legacy_result = trace_legacy_execution(df, test_start, test_bars)

    print("Tracing event-driven execution...")
    event_events, event_trades = trace_event_execution(df, test_start, test_bars)

    # Print debug trace
    print_debug_trace(legacy_events, event_events, df, test_start, test_bars)

    # Diagnosis
    print("\n" + "="*120)
    print("DIAGNOSIS")
    print("="*120)

    if len(legacy_events) > 0 and len([e for e in event_events if e.get('positions_opened', 0) > 0]) > 0:
        legacy_bar = legacy_events[0]['bar_index']
        event_bars = [e['bar_index'] for e in event_events if e.get('positions_opened', 0) > 0]

        if event_bars:
            event_bar = event_bars[0]
            offset = event_bar - legacy_bar

            print(f"\nFirst trade timing:")
            print(f"  Legacy entry: bar {legacy_bar} @ {legacy_events[0]['bar_time']}")
            print(f"  Event entry:  bar {event_bar} @ {df.iloc[event_bar]['time']}")
            print(f"  Offset: {offset} bar(s) = {offset} hour(s)")

            # Check if order was placed correctly
            order_events = [e for e in event_events if e.get('order_placed')]
            if order_events:
                order_event = order_events[0]
                print(f"\n  Order placement:")
                print(f"    Placed at bar: {order_event['bar_index']}")
                print(f"    Entry bar index: {order_event.get('order_entry_bar_index')}")
                print(f"    Expected execution: bar {order_event.get('order_entry_bar_index')}")
                print(f"    Actual execution: bar {event_bar}")

    print("\n" + "="*120)


if __name__ == '__main__':
    diagnose_timing_offset()
