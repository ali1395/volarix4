"""
Realistic backtest for Volarix 4 (Development Only)

NOTE: This is for development validation. Final backtesting
should be done using MT5 Expert Advisor for accurate results.

This script performs a bar-by-bar walk-forward simulation with
realistic SL/TP management and no look-ahead bias.
"""

import sys
import os

# Add parent directory to path to allow imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional
from volarix4.core.data import fetch_ohlc, connect_mt5
from volarix4.core.sr_levels import detect_sr_levels
from volarix4.core.rejection import find_rejection_candle
from volarix4.core.trade_setup import calculate_sl_tp
from volarix4.utils.helpers import calculate_pip_value


class Trade:
    """Represents a single trade with realistic SL/TP management."""

    def __init__(self, entry_time, direction, entry, sl, tp1, tp2, tp3):
        self.entry_time = entry_time
        self.direction = direction
        self.entry = entry
        self.sl = sl
        self.tp1 = tp1
        self.tp2 = tp2
        self.tp3 = tp3
        self.status = "open"
        self.exit_time = None
        self.exit_price = None
        self.pnl = 0.0
        self.pnl_pips = 0.0
        self.exit_reason = ""


def check_trade_outcome(trade: Trade, bar: pd.Series, pip_value: float) -> bool:
    """
    Check if trade hits SL or TP on current bar.
    Realistic: Checks high/low to see if SL/TP was hit during the bar.

    Returns:
        True if trade is closed
    """
    if trade.direction == "BUY":
        # Check SL hit (realistic: check if low touched SL)
        if bar['low'] <= trade.sl:
            trade.status = "loss"
            trade.exit_time = bar['time']
            trade.exit_price = trade.sl
            trade.pnl_pips = -(trade.entry - trade.sl) / pip_value
            trade.pnl = -1.0  # Full loss
            trade.exit_reason = "SL hit"
            return True

        # Check TP levels (realistic: assume partial closes at each TP)
        if bar['high'] >= trade.tp3:
            # All TPs hit
            trade.status = "win"
            trade.exit_time = bar['time']
            trade.exit_price = trade.tp3
            # Weighted profit: 40% at TP1, 40% at TP2, 20% at TP3
            r_pips = (trade.entry - trade.sl) / pip_value
            tp1_pips = (trade.tp1 - trade.entry) / pip_value
            tp2_pips = (trade.tp2 - trade.entry) / pip_value
            tp3_pips = (trade.tp3 - trade.entry) / pip_value
            trade.pnl = (0.4 * (tp1_pips / r_pips)) + (0.4 * (tp2_pips / r_pips)) + (
                        0.2 * (tp3_pips / r_pips))
            trade.pnl_pips = trade.pnl * r_pips
            trade.exit_reason = "All TPs hit"
            return True

        elif bar['high'] >= trade.tp2:
            # TP2 hit (partial exit)
            trade.status = "win"
            trade.exit_time = bar['time']
            trade.exit_price = trade.tp2
            r_pips = (trade.entry - trade.sl) / pip_value
            tp1_pips = (trade.tp1 - trade.entry) / pip_value
            tp2_pips = (trade.tp2 - trade.entry) / pip_value
            trade.pnl = (0.4 * (tp1_pips / r_pips)) + (0.4 * (tp2_pips / r_pips))
            trade.pnl_pips = trade.pnl * r_pips
            trade.exit_reason = "TP2 hit"
            return True

        elif bar['high'] >= trade.tp1:
            # TP1 hit (partial exit)
            trade.status = "win"
            trade.exit_time = bar['time']
            trade.exit_price = trade.tp1
            r_pips = (trade.entry - trade.sl) / pip_value
            tp1_pips = (trade.tp1 - trade.entry) / pip_value
            trade.pnl = 0.4 * (tp1_pips / r_pips)
            trade.pnl_pips = trade.pnl * r_pips
            trade.exit_reason = "TP1 hit"
            return True

    else:  # SELL
        # Check SL hit
        if bar['high'] >= trade.sl:
            trade.status = "loss"
            trade.exit_time = bar['time']
            trade.exit_price = trade.sl
            trade.pnl_pips = -(trade.sl - trade.entry) / pip_value
            trade.pnl = -1.0  # Full loss
            trade.exit_reason = "SL hit"
            return True

        # Check TP levels
        if bar['low'] <= trade.tp3:
            # All TPs hit
            trade.status = "win"
            trade.exit_time = bar['time']
            trade.exit_price = trade.tp3
            r_pips = (trade.sl - trade.entry) / pip_value
            tp1_pips = (trade.entry - trade.tp1) / pip_value
            tp2_pips = (trade.entry - trade.tp2) / pip_value
            tp3_pips = (trade.entry - trade.tp3) / pip_value
            trade.pnl = (0.4 * (tp1_pips / r_pips)) + (0.4 * (tp2_pips / r_pips)) + (
                        0.2 * (tp3_pips / r_pips))
            trade.pnl_pips = trade.pnl * r_pips
            trade.exit_reason = "All TPs hit"
            return True

        elif bar['low'] <= trade.tp2:
            trade.status = "win"
            trade.exit_time = bar['time']
            trade.exit_price = trade.tp2
            r_pips = (trade.sl - trade.entry) / pip_value
            tp1_pips = (trade.entry - trade.tp1) / pip_value
            tp2_pips = (trade.entry - trade.tp2) / pip_value
            trade.pnl = (0.4 * (tp1_pips / r_pips)) + (0.4 * (tp2_pips / r_pips))
            trade.pnl_pips = trade.pnl * r_pips
            trade.exit_reason = "TP2 hit"
            return True

        elif bar['low'] <= trade.tp1:
            trade.status = "win"
            trade.exit_time = bar['time']
            trade.exit_price = trade.tp1
            r_pips = (trade.sl - trade.entry) / pip_value
            tp1_pips = (trade.entry - trade.tp1) / pip_value
            trade.pnl = 0.4 * (tp1_pips / r_pips)
            trade.pnl_pips = trade.pnl * r_pips
            trade.exit_reason = "TP1 hit"
            return True

    return False


def run_backtest(
        symbol: str = "EURUSD",
        timeframe: str = "H1",
        bars: int = 1000,
        lookback_bars: int = 50
):
    """
    Run realistic bar-by-bar backtest.

    This simulates the API being called on each bar with proper
    SL/TP management and no look-ahead bias.

    Args:
        symbol: Trading pair
        timeframe: Timeframe
        bars: Number of historical bars to test
        lookback_bars: Bars needed for indicator calculation
    """

    print("\n" + "=" * 70)
    print("VOLARIX 4 BACKTEST - Development Validation")
    print("=" * 70)
    print(f"\nSymbol: {symbol}")
    print(f"Timeframe: {timeframe}")
    print(f"Test Bars: {bars}")
    print(f"Lookback: {lookback_bars}")
    print("\n⚠ NOTE: This is for development only.")
    print("  Final backtesting should use MT5 Expert Advisor.\n")
    print("=" * 70)

    # Connect to MT5
    print("\nConnecting to MT5...")
    if not connect_mt5():
        print("✗ Failed to connect to MT5")
        print("  Make sure MT5 is running and credentials are configured")
        return

    print("✓ Connected to MT5")

    # Fetch historical data
    print(f"\nFetching {bars + lookback_bars} bars of historical data...")
    try:
        df = fetch_ohlc(symbol, timeframe, bars + lookback_bars)
    except Exception as e:
        print(f"✗ Failed to fetch data: {e}")
        return

    if df is None or len(df) < lookback_bars:
        print("✗ Insufficient data fetched")
        return

    print(f"✓ Fetched {len(df)} bars")
    print(f"  Date Range: {df['time'].iloc[0]} to {df['time'].iloc[-1]}")

    # Backtest variables
    trades: List[Trade] = []
    open_trade: Optional[Trade] = None
    signals_generated = {"BUY": 0, "SELL": 0, "HOLD": 0}

    pip_value = calculate_pip_value(symbol)

    # Walk forward bar by bar
    print(f"\nRunning bar-by-bar simulation...")
    print("  (This may take a minute...)\n")

    for i in range(lookback_bars, len(df)):
        current_bar = df.iloc[i]

        # Update open trade if exists
        if open_trade:
            if check_trade_outcome(open_trade, current_bar, pip_value):
                trades.append(open_trade)
                open_trade = None

        # Generate signal only if no open trade (one trade at a time)
        if not open_trade:
            # Get historical data up to current bar (no look-ahead bias)
            historical_data = df.iloc[:i + 1].copy()

            # Run S/R detection
            levels = detect_sr_levels(
                historical_data.tail(lookback_bars),
                min_score=60.0,
                pip_value=pip_value
            )

            if levels:
                # Search for rejection
                rejection = find_rejection_candle(
                    historical_data.tail(20),
                    levels,
                    lookback=5,
                    pip_value=pip_value
                )

                if rejection:
                    direction = rejection['direction']
                    signals_generated[direction] += 1

                    # Calculate trade setup
                    trade_params = calculate_sl_tp(
                        entry=rejection['entry'],
                        level=rejection['level'],
                        direction=direction,
                        sl_pips_beyond=10.0,
                        pip_value=pip_value
                    )

                    # Create trade (enters on next bar open - realistic)
                    next_bar_idx = i + 1
                    if next_bar_idx < len(df):
                        entry_bar = df.iloc[next_bar_idx]
                        open_trade = Trade(
                            entry_time=entry_bar['time'],
                            direction=direction,
                            entry=entry_bar['open'],  # Enter at next bar open
                            sl=trade_params['sl'],
                            tp1=trade_params['tp1'],
                            tp2=trade_params['tp2'],
                            tp3=trade_params['tp3']
                        )
                else:
                    signals_generated["HOLD"] += 1
            else:
                signals_generated["HOLD"] += 1

    # Close any remaining open trade
    if open_trade:
        open_trade.status = "open_at_end"
        trades.append(open_trade)

    # Calculate statistics
    print("=" * 70)
    print("BACKTEST RESULTS")
    print("=" * 70)

    total_trades = len([t for t in trades if t.status != "open_at_end"])
    winning_trades = len([t for t in trades if t.status == "win"])
    losing_trades = len([t for t in trades if t.status == "loss"])

    if total_trades > 0:
        win_rate = (winning_trades / total_trades) * 100

        total_pnl = sum([t.pnl for t in trades if t.status != "open_at_end"])
        total_pnl_pips = sum([t.pnl_pips for t in trades if t.status != "open_at_end"])

        gross_profit = sum([t.pnl for t in trades if t.status == "win"])
        gross_loss = abs(sum([t.pnl for t in trades if t.status == "loss"]))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        print(f"\n📊 Trading Statistics")
        print(f"{'─' * 70}")
        print(f"  Total Trades: {total_trades}")
        print(f"  Winning: {winning_trades} ({win_rate:.1f}%)")
        print(f"  Losing: {losing_trades} ({100 - win_rate:.1f}%)")

        print(f"\n💰 Profitability")
        print(f"{'─' * 70}")
        print(f"  Profit Factor: {profit_factor:.2f}")
        print(f"  Total P&L: {total_pnl:+.2f}R ({total_pnl_pips:+.1f} pips)")

        if winning_trades > 0:
            avg_win = gross_profit / winning_trades
            print(f"  Avg Win: +{avg_win:.2f}R")

        if losing_trades > 0:
            avg_loss = gross_loss / losing_trades
            print(f"  Avg Loss: -{avg_loss:.2f}R")

        print(f"\n📈 Signal Distribution")
        print(f"{'─' * 70}")
        total_signals = sum(signals_generated.values())
        for signal, count in signals_generated.items():
            pct = (count / total_signals * 100) if total_signals > 0 else 0
            print(f"  {signal:4s}: {count:4d} ({pct:5.1f}%)")

        trade_frequency = (total_trades / bars) * 100
        print(f"\n  Trade Frequency: {trade_frequency:.2f}% of bars")

        # Show recent trades
        print(f"\n📝 Recent Trades (Last 10)")
        print(f"{'─' * 70}")
        for trade in trades[-10:]:
            if trade.status != "open_at_end":
                status_symbol = "✓" if trade.status == "win" else "✗"
                pnl_str = f"{trade.pnl:+.2f}R"
                pips_str = f"({trade.pnl_pips:+.1f}p)"
                print(f"  {status_symbol} {trade.entry_time} | {trade.direction:4s} | "
                      f"{trade.exit_reason:12s} | {pnl_str:8s} {pips_str:10s}")

    else:
        print("\n⚠ No trades executed during backtest period")
        print(f"\nSignal Distribution:")
        for signal, count in signals_generated.items():
            print(f"  {signal}: {count}")
        print("\nPossible reasons:")
        print("  - No valid S/R levels detected")
        print("  - No rejection patterns found")
        print("  - Outside trading sessions")

    print("\n" + "=" * 70)
    print("Backtest Complete")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    # Run backtest with default parameters
    run_backtest(symbol="EURUSD", timeframe="H1", bars=500, lookback_bars=50)
