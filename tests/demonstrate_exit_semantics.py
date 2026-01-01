"""Demonstration: Why legacy exits same-bar but OPEN_ONLY doesn't

This script shows bar-by-bar execution for Trade 1 from the parity test,
demonstrating the fundamental difference between OHLC_INTRABAR and OPEN_ONLY
exit semantics.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.backtest import run_backtest, fetch_ohlc


def demonstrate_trade_1_execution():
    """Demonstrate Trade 1 execution with both exit semantics

    Trade 1 characteristics (from parity test):
    - Entry bar: 468 @ 2025-12-27 17:00
    - Direction: BUY
    - Entry price: ~1.04170
    - SL: ~1.04120
    - Bar 468 has low that hits SL on same bar
    """
    print("\n" + "="*100)
    print("DEMONSTRATION: SAME-BAR EXIT BEHAVIOR")
    print("="*100)
    print("\nThis demonstrates why legacy backtest exits trades on the same bar as entry,")
    print("while MT5 'Open prices only' mode does not.")
    print("\nKey concept: Exit semantics determine WHEN to check SL/TP:")
    print("  - OHLC_INTRABAR: Check bar high/low (can exit same bar)")
    print("  - OPEN_ONLY: Check only bar open price (cannot exit same bar)")
    print("="*100)

    # Fetch data
    df = fetch_ohlc('EURUSD', 'H1', 500)

    # Run legacy backtest (OHLC_INTRABAR semantics)
    print("\n" + "-"*100)
    print("MODE 1: OHLC_INTRABAR (Legacy Backtest)")
    print("-"*100)
    print("Exit logic: Check if bar HIGH >= TP or bar LOW <= SL")
    print("Result: Trade can enter and exit on SAME bar")
    print("-"*100)

    legacy_result = run_backtest(
        df=df,
        bars=100,
        lookback_bars=400,
        verbose=False,
        use_event_loop=True,
        exit_semantics="ohlc_intrabar",
        tp_model="full_close_first_tp"
    )

    if legacy_result['total_trades'] > 0:
        trade1 = legacy_result['trades'][0]

        # Find entry bar
        entry_bar_idx = None
        for i in range(len(df)):
            if df.iloc[i]['time'] == trade1.entry_time:
                entry_bar_idx = i
                break

        if entry_bar_idx is not None:
            entry_bar = df.iloc[entry_bar_idx]

            print(f"\nTrade 1 Entry:")
            print(f"  Bar index: {entry_bar_idx}")
            print(f"  Time: {entry_bar['time']}")
            print(f"  Direction: {trade1.direction}")
            print(f"  Entry: {trade1.entry:.5f} (at bar open + costs)")
            print(f"  SL: {trade1.sl:.5f}")
            print(f"  TP1: {trade1.tp1:.5f}")

            print(f"\nEntry Bar OHLC:")
            print(f"  Open:  {entry_bar['open']:.5f}")
            print(f"  High:  {entry_bar['high']:.5f}")
            print(f"  Low:   {entry_bar['low']:.5f}")
            print(f"  Close: {entry_bar['close']:.5f}")

            print(f"\nExit Check (OHLC_INTRABAR):")
            if trade1.direction == "BUY":
                print(f"  Checking: Does bar LOW ({entry_bar['low']:.5f}) <= SL ({trade1.sl:.5f})?")
                if entry_bar['low'] <= trade1.sl:
                    print(f"  Result: YES - SL hit on SAME bar!")
                else:
                    print(f"  Checking: Does bar HIGH ({entry_bar['high']:.5f}) >= TP1 ({trade1.tp1:.5f})?")
                    if entry_bar['high'] >= trade1.tp1:
                        print(f"  Result: YES - TP1 hit on SAME bar!")

            print(f"\nTrade 1 Exit:")
            print(f"  Exit time: {trade1.exit_time}")
            print(f"  Exit reason: {trade1.exit_reason}")
            print(f"  Same bar exit: {trade1.exit_time == trade1.entry_time}")

    # Run OPEN_ONLY backtest
    print("\n" + "-"*100)
    print("MODE 2: OPEN_ONLY (MT5 'Open prices only')")
    print("-"*100)
    print("Exit logic: Check if bar OPEN >= TP or bar OPEN <= SL")
    print("Result: Trade CANNOT exit on same bar (unless immediate at open)")
    print("-"*100)

    open_only_result = run_backtest(
        df=df,
        bars=100,
        lookback_bars=400,
        verbose=False,
        use_event_loop=True,
        exit_semantics="open_only",
        tp_model="full_close_first_tp"
    )

    if open_only_result['total_trades'] > 0:
        trade1 = open_only_result['trades'][0]

        # Find entry bar
        entry_bar_idx = None
        for i in range(len(df)):
            if df.iloc[i]['time'] == trade1.entry_time:
                entry_bar_idx = i
                break

        if entry_bar_idx is not None:
            entry_bar = df.iloc[entry_bar_idx]
            exit_bar_idx = entry_bar_idx

            # Find exit bar
            if trade1.exit_time != trade1.entry_time:
                for i in range(entry_bar_idx + 1, len(df)):
                    if df.iloc[i]['time'] == trade1.exit_time:
                        exit_bar_idx = i
                        break

            print(f"\nTrade 1 Entry:")
            print(f"  Bar index: {entry_bar_idx}")
            print(f"  Time: {entry_bar['time']}")
            print(f"  Direction: {trade1.direction}")
            print(f"  Entry: {trade1.entry:.5f} (at bar open + costs)")
            print(f"  SL: {trade1.sl:.5f}")
            print(f"  TP1: {trade1.tp1:.5f}")

            print(f"\nEntry Bar OHLC:")
            print(f"  Open:  {entry_bar['open']:.5f}")
            print(f"  High:  {entry_bar['high']:.5f}")
            print(f"  Low:   {entry_bar['low']:.5f}")
            print(f"  Close: {entry_bar['close']:.5f}")

            print(f"\nExit Check on Entry Bar (OPEN_ONLY):")
            if trade1.direction == "BUY":
                print(f"  Checking: Does bar OPEN ({entry_bar['open']:.5f}) <= SL ({trade1.sl:.5f})?")
                if entry_bar['open'] <= trade1.sl:
                    print(f"  Result: YES - Immediate SL hit at open!")
                else:
                    print(f"  Result: NO - Bar open above SL")
                    print(f"  Note: Bar LOW ({entry_bar['low']:.5f}) would hit SL, but we only check OPEN")
                    print(f"  Trade stays OPEN until next bar")

            if exit_bar_idx != entry_bar_idx:
                exit_bar = df.iloc[exit_bar_idx]
                print(f"\nNext Bar (Exit Bar):")
                print(f"  Bar index: {exit_bar_idx}")
                print(f"  Time: {exit_bar['time']}")
                print(f"  Open:  {exit_bar['open']:.5f}")
                print(f"  High:  {exit_bar['high']:.5f}")
                print(f"  Low:   {exit_bar['low']:.5f}")
                print(f"  Close: {exit_bar['close']:.5f}")

                print(f"\n Exit Check on Next Bar:")
                if trade1.direction == "BUY":
                    if exit_bar['open'] <= trade1.sl:
                        print(f"  Checking: Does bar OPEN ({exit_bar['open']:.5f}) <= SL ({trade1.sl:.5f})?")
                        print(f"  Result: YES - SL hit at open of next bar")
                    elif exit_bar['open'] >= trade1.tp1:
                        print(f"  Checking: Does bar OPEN ({exit_bar['open']:.5f}) >= TP1 ({trade1.tp1:.5f})?")
                        print(f"  Result: YES - TP1 hit at open of next bar")

            print(f"\nTrade 1 Exit:")
            print(f"  Exit time: {trade1.exit_time}")
            print(f"  Exit reason: {trade1.exit_reason}")
            print(f"  Same bar exit: {trade1.exit_time == trade1.entry_time}")

    # Summary
    print("\n" + "="*100)
    print("SUMMARY")
    print("="*100)
    print("\nOHLC_INTRABAR (Legacy):")
    print(f"  Total trades: {legacy_result['total_trades']}")
    if legacy_result['total_trades'] > 0:
        same_bar_exits = sum(1 for t in legacy_result['trades'] if t.exit_time == t.entry_time)
        print(f"  Same-bar exits: {same_bar_exits}/{legacy_result['total_trades']}")

    print("\nOPEN_ONLY (MT5 'Open prices only'):")
    print(f"  Total trades: {open_only_result['total_trades']}")
    if open_only_result['total_trades'] > 0:
        same_bar_exits = sum(1 for t in open_only_result['trades'] if t.exit_time == t.entry_time)
        print(f"  Same-bar exits: {same_bar_exits}/{open_only_result['total_trades']}")

    print("\nKey Insight:")
    print("  OHLC_INTRABAR is MORE OPTIMISTIC - assumes you can catch intrabar moves")
    print("  OPEN_ONLY is MORE CONSERVATIVE - only 1 tick per bar, no intrabar granularity")
    print("\nNeither is 'wrong' - they model different execution assumptions:")
    print("  - Legacy backtest: Hybrid model (bar-based but checks OHLC)")
    print("  - MT5 'Open prices only': True tick-by-tick with 1 tick per bar")
    print("="*100)


if __name__ == '__main__':
    demonstrate_trade_1_execution()
