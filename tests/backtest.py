"""
Realistic backtest for Volarix 4 with cost modeling and parameter sweep.

This script performs bar-by-bar walk-forward simulation with:
- Realistic costs (spread, commission, slippage)
- Parameter testing (min_confidence, broken_level_cooldown)
- Grid search for parameter optimization
- No look-ahead bias

NOTE: Final backtesting should be done using MT5 Expert Advisor.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from itertools import product
from concurrent.futures import ProcessPoolExecutor, as_completed
from volarix4.core.data import fetch_ohlc, connect_mt5
from volarix4.core.sr_levels import detect_sr_levels
from volarix4.core.rejection import find_rejection_candle
from volarix4.core.trade_setup import calculate_sl_tp
from volarix4.utils.helpers import calculate_pip_value


class Trade:
    """Represents a single trade with realistic SL/TP management and costs."""

    def __init__(self, entry_time, direction, entry, sl, tp1, tp2, tp3,
                 pip_value, spread_pips=0.0, slippage_pips=0.0,
                 commission_per_side_per_lot=0.0, lot_size=1.0):
        self.entry_time = entry_time
        self.direction = direction
        self.entry_raw = entry
        self.sl = sl
        self.tp1 = tp1
        self.tp2 = tp2
        self.tp3 = tp3
        self.status = "open"
        self.exit_time = None
        self.exit_price = None
        self.pnl = 0.0
        self.pnl_pips = 0.0
        self.pnl_after_costs = 0.0
        self.exit_reason = ""

        # Cost parameters
        self.pip_value = pip_value
        self.spread_pips = spread_pips
        self.slippage_pips = slippage_pips
        self.commission_per_side_per_lot = commission_per_side_per_lot
        self.lot_size = lot_size

        # Apply entry costs
        if direction == "BUY":
            # Entry: pay spread + slippage
            self.entry = entry + (spread_pips / 2 + slippage_pips) * pip_value
        else:  # SELL
            # Entry: pay spread + slippage
            self.entry = entry - (spread_pips / 2 + slippage_pips) * pip_value

        # Entry commission (1 side)
        self.entry_commission = commission_per_side_per_lot * lot_size


def apply_exit_costs(trade: Trade, exit_price: float) -> float:
    """Apply exit costs (spread, slippage) to exit price."""
    if trade.direction == "BUY":
        # Exit BUY: sell at bid (lose spread + slippage)
        return exit_price - (trade.spread_pips / 2 + trade.slippage_pips) * trade.pip_value
    else:  # SELL
        # Exit SELL: buy at ask (pay spread + slippage)
        return exit_price + (trade.spread_pips / 2 + trade.slippage_pips) * trade.pip_value


def commission_usd_to_pips(commission_usd: float, usd_per_pip_per_lot: float) -> float:
    """
    Convert USD commission to pips.

    commission_usd should already include lot sizing (i.e., USD total for this trade leg).
    """
    if usd_per_pip_per_lot == 0:
        return 0.0
    return commission_usd / usd_per_pip_per_lot



def check_trade_outcome(trade: Trade, bar: pd.Series, usd_per_pip_per_lot: float) -> bool:
    """
    Check if trade hits SL or TP on current bar.
    Applies realistic costs on exit.

    Args:
        trade: Trade instance
        bar: Current bar data
        usd_per_pip_per_lot: USD value per pip per lot for commission conversion

    Returns:
        True if trade is closed
    """
    if trade.direction == "BUY":
        # Check SL hit
        if bar['low'] <= trade.sl:
            trade.status = "loss"
            trade.exit_time = bar['time']
            exit_price_after_costs = apply_exit_costs(trade, trade.sl)
            trade.exit_price = exit_price_after_costs
            trade.pnl_pips = (exit_price_after_costs - trade.entry) / trade.pip_value
            trade.pnl = trade.pnl_pips / ((trade.entry - trade.sl) / trade.pip_value)  # In R

            # Commission: entry (1 side) + exit (1 side) = 2 sides total
            exit_commission_usd = trade.commission_per_side_per_lot * trade.lot_size
            total_commission_usd = trade.entry_commission + exit_commission_usd
            total_commission_pips = commission_usd_to_pips(total_commission_usd, usd_per_pip_per_lot)
            trade.pnl_after_costs = trade.pnl_pips - total_commission_pips
            trade.exit_reason = "SL hit"
            return True

        # Check TP levels (assume partial closes)
        r_pips = (trade.entry - trade.sl) / trade.pip_value

        if bar['high'] >= trade.tp3:
            # All TPs hit
            trade.status = "win"
            trade.exit_time = bar['time']

            # Calculate weighted PnL with costs
            tp1_exit = apply_exit_costs(trade, trade.tp1)
            tp2_exit = apply_exit_costs(trade, trade.tp2)
            tp3_exit = apply_exit_costs(trade, trade.tp3)

            tp1_pips = (tp1_exit - trade.entry) / trade.pip_value
            tp2_pips = (tp2_exit - trade.entry) / trade.pip_value
            tp3_pips = (tp3_exit - trade.entry) / trade.pip_value

            weighted_pips = 0.5 * tp1_pips + 0.3 * tp2_pips + 0.2 * tp3_pips
            trade.pnl_pips = weighted_pips
            trade.pnl = weighted_pips / r_pips

            # Commission: entry (1 side) + 3 exit sides (TP1 + TP2 + TP3) = 4 sides total
            exit_commission_usd = 3 * trade.commission_per_side_per_lot * trade.lot_size
            total_commission_usd = trade.entry_commission + exit_commission_usd
            total_commission_pips = commission_usd_to_pips(total_commission_usd, usd_per_pip_per_lot)

            trade.pnl_after_costs = trade.pnl_pips - total_commission_pips

            trade.exit_price = tp3_exit
            trade.exit_reason = "All TPs hit"
            return True

        elif bar['high'] >= trade.tp2:
            # TP2 hit
            trade.status = "win"
            trade.exit_time = bar['time']

            tp1_exit = apply_exit_costs(trade, trade.tp1)
            tp2_exit = apply_exit_costs(trade, trade.tp2)

            tp1_pips = (tp1_exit - trade.entry) / trade.pip_value
            tp2_pips = (tp2_exit - trade.entry) / trade.pip_value

            weighted_pips = 0.5 * tp1_pips + 0.3 * tp2_pips + 0.2 * 0  # TP3 not hit
            trade.pnl_pips = weighted_pips
            trade.pnl = weighted_pips / r_pips

            # Commission: entry (1 side) + 2 exit sides (TP1 + TP2) = 3 sides total
            exit_commission_usd = 2 * trade.commission_per_side_per_lot * trade.lot_size
            total_commission_usd = trade.entry_commission + exit_commission_usd
            total_commission_pips = commission_usd_to_pips(total_commission_usd, usd_per_pip_per_lot)

            trade.pnl_after_costs = trade.pnl_pips - total_commission_pips

            trade.exit_price = tp2_exit
            trade.exit_reason = "TP2 hit"
            return True

        elif bar['high'] >= trade.tp1:
            # TP1 hit
            trade.status = "win"
            trade.exit_time = bar['time']

            tp1_exit = apply_exit_costs(trade, trade.tp1)
            tp1_pips = (tp1_exit - trade.entry) / trade.pip_value

            weighted_pips = 0.5 * tp1_pips
            trade.pnl_pips = weighted_pips
            trade.pnl = weighted_pips / r_pips

            # Commission: entry (1 side) + 1 exit side (TP1) = 2 sides total
            exit_commission_usd = trade.commission_per_side_per_lot * trade.lot_size
            total_commission_usd = trade.entry_commission + exit_commission_usd
            total_commission_pips = commission_usd_to_pips(total_commission_usd, usd_per_pip_per_lot)

            trade.pnl_after_costs = trade.pnl_pips - total_commission_pips

            trade.exit_price = tp1_exit
            trade.exit_reason = "TP1 hit"
            return True

    else:  # SELL
        # Check SL hit
        if bar['high'] >= trade.sl:
            trade.status = "loss"
            trade.exit_time = bar['time']
            exit_price_after_costs = apply_exit_costs(trade, trade.sl)
            trade.exit_price = exit_price_after_costs
            trade.pnl_pips = (trade.entry - exit_price_after_costs) / trade.pip_value
            trade.pnl = trade.pnl_pips / ((trade.sl - trade.entry) / trade.pip_value)

            # Commission: entry (1 side) + exit (1 side) = 2 sides total
            exit_commission_usd = trade.commission_per_side_per_lot * trade.lot_size
            total_commission_usd = trade.entry_commission + exit_commission_usd
            total_commission_pips = commission_usd_to_pips(total_commission_usd, usd_per_pip_per_lot)

            trade.pnl_after_costs = trade.pnl_pips - total_commission_pips
            trade.exit_reason = "SL hit"
            return True

        # Check TP levels
        r_pips = (trade.sl - trade.entry) / trade.pip_value

        if bar['low'] <= trade.tp3:
            trade.status = "win"
            trade.exit_time = bar['time']

            tp1_exit = apply_exit_costs(trade, trade.tp1)
            tp2_exit = apply_exit_costs(trade, trade.tp2)
            tp3_exit = apply_exit_costs(trade, trade.tp3)

            tp1_pips = (trade.entry - tp1_exit) / trade.pip_value
            tp2_pips = (trade.entry - tp2_exit) / trade.pip_value
            tp3_pips = (trade.entry - tp3_exit) / trade.pip_value

            weighted_pips = 0.5 * tp1_pips + 0.3 * tp2_pips + 0.2 * tp3_pips
            trade.pnl_pips = weighted_pips
            trade.pnl = weighted_pips / r_pips

            # Commission: entry (1 side) + 3 exit sides (TP1 + TP2 + TP3) = 4 sides total
            exit_commission_usd = 3 * trade.commission_per_side_per_lot * trade.lot_size
            total_commission_usd = trade.entry_commission + exit_commission_usd
            total_commission_pips = commission_usd_to_pips(total_commission_usd, usd_per_pip_per_lot)

            trade.pnl_after_costs = trade.pnl_pips - total_commission_pips

            trade.exit_price = tp3_exit
            trade.exit_reason = "All TPs hit"
            return True

        elif bar['low'] <= trade.tp2:
            trade.status = "win"
            trade.exit_time = bar['time']

            tp1_exit = apply_exit_costs(trade, trade.tp1)
            tp2_exit = apply_exit_costs(trade, trade.tp2)

            tp1_pips = (trade.entry - tp1_exit) / trade.pip_value
            tp2_pips = (trade.entry - tp2_exit) / trade.pip_value

            weighted_pips = 0.5 * tp1_pips + 0.3 * tp2_pips
            trade.pnl_pips = weighted_pips
            trade.pnl = weighted_pips / r_pips

            # Commission: entry (1 side) + 2 exit sides (TP1 + TP2) = 3 sides total
            exit_commission_usd = 2 * trade.commission_per_side_per_lot * trade.lot_size
            total_commission_usd = trade.entry_commission + exit_commission_usd
            total_commission_pips = commission_usd_to_pips(total_commission_usd, usd_per_pip_per_lot)

            trade.pnl_after_costs = trade.pnl_pips - total_commission_pips

            trade.exit_price = tp2_exit
            trade.exit_reason = "TP2 hit"
            return True

        elif bar['low'] <= trade.tp1:
            trade.status = "win"
            trade.exit_time = bar['time']

            tp1_exit = apply_exit_costs(trade, trade.tp1)
            tp1_pips = (trade.entry - tp1_exit) / trade.pip_value

            weighted_pips = 0.5 * tp1_pips
            trade.pnl_pips = weighted_pips
            trade.pnl = weighted_pips / r_pips

            # Commission: entry (1 side) + 1 exit side (TP1) = 2 sides total
            exit_commission_usd = trade.commission_per_side_per_lot * trade.lot_size
            total_commission_usd = trade.entry_commission + exit_commission_usd
            total_commission_pips = commission_usd_to_pips(total_commission_usd, usd_per_pip_per_lot)

            trade.pnl_after_costs = trade.pnl_pips - total_commission_pips

            trade.exit_price = tp1_exit
            trade.exit_reason = "TP1 hit"
            return True

    return False


def run_backtest(
        symbol: str = "EURUSD",
        timeframe: str = "H1",
        bars: int = 1000,
        lookback_bars: int = 400,
        # Cost parameters
        spread_pips: float = 1.0,
        commission_per_side_per_lot: float = 7.0,
        slippage_pips: float = 0.5,
        lot_size: float = 1.0,
        usd_per_pip_per_lot: float = 10.0,
        starting_balance_usd: float = 10000.0,
        # Filter parameters
        min_confidence: Optional[float] = None,
        broken_level_cooldown_hours: Optional[float] = None,
        broken_level_break_pips: float = 15.0,
        enable_confidence_filter: bool = True,
        enable_broken_level_filter: bool = True,
        # Data
        df: Optional[pd.DataFrame] = None,
        # Display
        verbose: bool = True
) -> Dict:
    """
    Run realistic bar-by-bar backtest with costs and parameter filters.

    Args:
        symbol: Trading pair
        timeframe: Timeframe
        bars: Number of historical bars to test
        lookback_bars: Bars needed for indicator calculation
        spread_pips: Spread in pips
        commission_per_side_per_lot: Commission per side per lot in USD
        slippage_pips: Slippage in pips
        lot_size: Lot size for position sizing
        usd_per_pip_per_lot: USD value per pip per lot (for commission conversion)
        starting_balance_usd: Starting account balance in USD (for drawdown %)
        min_confidence: Minimum confidence threshold (None = no filter)
        broken_level_cooldown_hours: Hours to block broken levels (None = no filter)
        broken_level_break_pips: Pips beyond level to mark as broken
        enable_confidence_filter: Enable confidence filtering
        enable_broken_level_filter: Enable broken level filtering
        df: Pre-loaded DataFrame (if None, will fetch from MT5)
        verbose: Print detailed output

    Returns:
        Dict with backtest results
    """

    if verbose:
        print("\n" + "=" * 70)
        print("VOLARIX 4 BACKTEST - Parameter Sweep Edition")
        print("=" * 70)
        print(f"\nSymbol: {symbol}")
        print(f"Timeframe: {timeframe}")
        print(f"Test Bars: {bars}")
        print(f"Lookback: {lookback_bars}")
        print(f"\nCosts:")
        print(f"  Spread: {spread_pips} pips")
        print(f"  Commission: ${commission_per_side_per_lot} per side per lot")
        print(f"  Slippage: {slippage_pips} pips")
        print(f"  Lot Size: {lot_size}")
        print(f"  USD per pip per lot: ${usd_per_pip_per_lot}")
        print(f"\nFilters:")
        print(f"  Min Confidence: {min_confidence if enable_confidence_filter else 'OFF'}")
        if enable_broken_level_filter:
            print(f"  Broken Level Cooldown: {broken_level_cooldown_hours}h")
            print(f"  Broken Level Threshold: {broken_level_break_pips} pips")
        else:
            print("  Broken Level Filter: OFF")
        print("=" * 70)

    # Get data (either pre-loaded or fetch from MT5)
    if df is None:
        # Fetch historical data (fetch_ohlc handles MT5 connection internally)
        if verbose:
            print(f"\nFetching {bars + lookback_bars} bars for {symbol} {timeframe}...")
        try:
            df = fetch_ohlc(symbol, timeframe, bars + lookback_bars)
            if df is None or len(df) < lookback_bars:
                if verbose:
                    print(f"✗ Insufficient data (got {len(df) if df is not None else 0} bars, need {lookback_bars})")
                return {"error": f"Insufficient data (need {lookback_bars} bars)"}
        except Exception as e:
            if verbose:
                print(f"✗ Data fetch failed: {e}")
            return {"error": f"Data fetch failed: {e}"}

        if verbose:
            print(f"✓ Fetched {len(df)} bars")
            print(f"  Range: {df['time'].iloc[0]} to {df['time'].iloc[-1]}")
    else:
        # Use pre-loaded data
        if len(df) < lookback_bars:
            if verbose:
                print(f"✗ Insufficient data (got {len(df)} bars, need {lookback_bars})")
            return {"error": f"Insufficient data (need {lookback_bars} bars)"}

        if verbose:
            print(f"\n✓ Using pre-loaded data: {len(df)} bars")
            print(f"  Range: {df['time'].iloc[0]} to {df['time'].iloc[-1]}")

    # Backtest variables
    trades: List[Trade] = []
    open_trade: Optional[Trade] = None
    signals_generated = {"BUY": 0, "SELL": 0, "HOLD": 0}
    filter_rejections = {
        "confidence": 0,
        "broken_level": 0
    }

    pip_value = calculate_pip_value(symbol)

    # Broken level tracking: {level_price: (break_timestamp, level_type)}
    broken_levels: Dict[float, Tuple[datetime, str]] = {}

    # Walk forward bar by bar
    if verbose:
        print(f"\nRunning simulation...")

    for i in range(lookback_bars, len(df)):
        current_bar = df.iloc[i]
        current_time = current_bar['time']

        # Update open trade
        if open_trade:
            if check_trade_outcome(open_trade, current_bar, usd_per_pip_per_lot):
                trades.append(open_trade)
                open_trade = None

        # Generate signal only if no open trade
        if not open_trade:
            historical_data = df.iloc[:i + 1].copy()

            # Run S/R detection
            levels = detect_sr_levels(
                historical_data.tail(lookback_bars),
                min_score=60.0,
                pip_value=pip_value
            )

            if levels:
                # Mark broken levels on current bar (check ALL levels on EVERY bar)
                if enable_broken_level_filter:
                    for level_dict in levels:
                        level_price = round(level_dict['level'], 5)
                        level_type = level_dict['type']  # 'support' or 'resistance'

                        # Check if level was broken by current bar close
                        if level_type == 'support':
                            if current_bar['close'] < (level_price - broken_level_break_pips * pip_value):
                                # Support broken, mark it
                                broken_levels[level_price] = (current_time, level_type)
                        elif level_type == 'resistance':
                            if current_bar['close'] > (level_price + broken_level_break_pips * pip_value):
                                # Resistance broken, mark it
                                broken_levels[level_price] = (current_time, level_type)

                # Apply broken level filter (remove levels in cooldown)
                if enable_broken_level_filter and broken_level_cooldown_hours:
                    valid_levels = []
                    for level_dict in levels:
                        level_price = round(level_dict['level'], 5)

                        # Check if level is in cooldown
                        if level_price in broken_levels:
                            break_time, _ = broken_levels[level_price]
                            time_since_break = current_time - break_time

                            if time_since_break < timedelta(hours=broken_level_cooldown_hours):
                                # Still in cooldown
                                continue
                            else:
                                # Cooldown expired, remove
                                del broken_levels[level_price]

                        valid_levels.append(level_dict)

                    if len(valid_levels) < len(levels):
                        filter_rejections["broken_level"] += (len(levels) - len(valid_levels))

                    levels = valid_levels

                if levels:
                    # Search for rejection
                    rejection = find_rejection_candle(
                        historical_data.tail(20),
                        levels,
                        lookback=5,
                        pip_value=pip_value
                    )

                    if rejection:
                        # Apply confidence filter
                        confidence = rejection.get('confidence', 1.0)

                        if enable_confidence_filter and min_confidence is not None:
                            if confidence < min_confidence:
                                filter_rejections["confidence"] += 1
                                signals_generated["HOLD"] += 1
                                continue

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

                        # Create trade (enter on next bar open)
                        next_bar_idx = i + 1
                        if next_bar_idx < len(df):
                            entry_bar = df.iloc[next_bar_idx]
                            open_trade = Trade(
                                entry_time=entry_bar['time'],
                                direction=direction,
                                entry=entry_bar['open'],
                                sl=trade_params['sl'],
                                tp1=trade_params['tp1'],
                                tp2=trade_params['tp2'],
                                tp3=trade_params['tp3'],
                                pip_value=pip_value,
                                spread_pips=spread_pips,
                                slippage_pips=slippage_pips,
                                commission_per_side_per_lot=commission_per_side_per_lot,
                                lot_size=lot_size
                            )
                    else:
                        signals_generated["HOLD"] += 1
                else:
                    signals_generated["HOLD"] += 1
            else:
                signals_generated["HOLD"] += 1

    # Close any remaining open trade
    if open_trade:
        open_trade.status = "open_at_end"
        trades.append(open_trade)

    # Calculate statistics
    completed_trades = [t for t in trades if t.status != "open_at_end"]
    total_trades = len(completed_trades)

    if total_trades == 0:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "accuracy": 0.0,
            "profit_trades_pct": 0.0,
            "loss_trades_pct": 0.0,
            "profit_factor": 0.0,
            "recovery_factor": 0.0,
            "expected_payoff_pips": 0.0,
            "total_pnl_pips": 0.0,
            "total_pnl_after_costs": 0.0,
            "gross_profit_pips": 0.0,
            "gross_loss_pips": 0.0,
            "max_drawdown": 0.0,
            "max_drawdown_pct": 0.0,
            "largest_win_pips": 0.0,
            "largest_loss_pips": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "avg_win_pips": 0.0,
            "avg_loss_pips": 0.0,
            "max_consecutive_wins": 0,
            "max_consecutive_losses": 0,
            "max_consecutive_wins_pnl": 0.0,
            "max_consecutive_losses_pnl": 0.0,
            "trade_count_long": 0,
            "trade_count_short": 0,
            "win_rate_long": 0.0,
            "win_rate_short": 0.0,
            "trade_frequency": 0.0,
            "signals": signals_generated,
            "filters": filter_rejections,
            "trades": []
        }

    winning_trades = [t for t in completed_trades if t.status == "win"]
    losing_trades = [t for t in completed_trades if t.status == "loss"]

    # Basic counts and rates
    win_rate = (len(winning_trades) / total_trades) * 100
    accuracy = win_rate  # Same as win_rate
    profit_trades_pct = win_rate
    loss_trades_pct = 100.0 - win_rate

    # P&L metrics
    total_pnl_pips = sum([t.pnl_pips for t in completed_trades])
    total_pnl_after_costs = sum([t.pnl_after_costs for t in completed_trades])

    gross_profit_pips = sum([t.pnl_after_costs for t in winning_trades]) if winning_trades else 0.0
    gross_loss_pips = abs(sum([t.pnl_after_costs for t in losing_trades])) if losing_trades else 0.0
    profit_factor = gross_profit_pips / gross_loss_pips if gross_loss_pips > 0 else float('inf')

    expected_payoff_pips = total_pnl_after_costs / total_trades

    # Win/Loss metrics
    avg_win_pips = gross_profit_pips / len(winning_trades) if winning_trades else 0.0
    avg_loss_pips = gross_loss_pips / len(losing_trades) if losing_trades else 0.0
    avg_win = avg_win_pips  # Alias for compatibility
    avg_loss = avg_loss_pips  # Alias for compatibility

    largest_win_pips = max([t.pnl_after_costs for t in winning_trades]) if winning_trades else 0.0
    largest_loss_pips = abs(min([t.pnl_after_costs for t in losing_trades])) if losing_trades else 0.0

    # Consecutive wins/losses
    max_consecutive_wins = 0
    max_consecutive_losses = 0
    max_consecutive_wins_pnl = 0.0
    max_consecutive_losses_pnl = 0.0

    current_wins = 0
    current_losses = 0
    current_wins_pnl = 0.0
    current_losses_pnl = 0.0

    for trade in completed_trades:
        if trade.status == "win":
            current_wins += 1
            current_wins_pnl += trade.pnl_after_costs
            current_losses = 0
            current_losses_pnl = 0.0

            if current_wins > max_consecutive_wins:
                max_consecutive_wins = current_wins
                max_consecutive_wins_pnl = current_wins_pnl
        else:  # loss
            current_losses += 1
            current_losses_pnl += abs(trade.pnl_after_costs)
            current_wins = 0
            current_wins_pnl = 0.0

            if current_losses > max_consecutive_losses:
                max_consecutive_losses = current_losses
                max_consecutive_losses_pnl = current_losses_pnl

    # Long/Short breakdown
    long_trades = [t for t in completed_trades if t.direction == "BUY"]
    short_trades = [t for t in completed_trades if t.direction == "SELL"]

    trade_count_long = len(long_trades)
    trade_count_short = len(short_trades)

    long_wins = [t for t in long_trades if t.status == "win"]
    short_wins = [t for t in short_trades if t.status == "win"]

    win_rate_long = (len(long_wins) / trade_count_long * 100) if trade_count_long > 0 else 0.0
    win_rate_short = (len(short_wins) / trade_count_short * 100) if trade_count_short > 0 else 0.0

    # Calculate max drawdown in pips
    equity_curve = []
    running_pnl = 0.0
    for trade in completed_trades:
        running_pnl += trade.pnl_after_costs
        equity_curve.append(running_pnl)

    max_drawdown = 0.0
    if equity_curve:
        peak = equity_curve[0]
        for value in equity_curve:
            if value > peak:
                peak = value
            drawdown = peak - value
            if drawdown > max_drawdown:
                max_drawdown = drawdown

    # Calculate max drawdown as percentage of starting balance
    max_drawdown_usd = max_drawdown * usd_per_pip_per_lot * lot_size
    max_drawdown_pct = (max_drawdown_usd / starting_balance_usd * 100) if starting_balance_usd > 0 else 0.0

    # Recovery factor
    recovery_factor = total_pnl_after_costs / max_drawdown if max_drawdown > 0 else 0.0

    results = {
        # Trade counts
        "total_trades": total_trades,
        "winning_trades": len(winning_trades),
        "losing_trades": len(losing_trades),
        "trade_count_long": trade_count_long,
        "trade_count_short": trade_count_short,

        # Win rates
        "win_rate": win_rate,
        "accuracy": accuracy,
        "profit_trades_pct": profit_trades_pct,
        "loss_trades_pct": loss_trades_pct,
        "win_rate_long": win_rate_long,
        "win_rate_short": win_rate_short,

        # Profitability
        "profit_factor": profit_factor,
        "recovery_factor": recovery_factor,
        "expected_payoff_pips": expected_payoff_pips,

        # P&L
        "total_pnl_pips": total_pnl_pips,
        "total_pnl_after_costs": total_pnl_after_costs,
        "gross_profit_pips": gross_profit_pips,
        "gross_loss_pips": gross_loss_pips,

        # Drawdown
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": max_drawdown_pct,

        # Win/Loss stats
        "largest_win_pips": largest_win_pips,
        "largest_loss_pips": largest_loss_pips,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "avg_win_pips": avg_win_pips,
        "avg_loss_pips": avg_loss_pips,

        # Consecutive
        "max_consecutive_wins": max_consecutive_wins,
        "max_consecutive_losses": max_consecutive_losses,
        "max_consecutive_wins_pnl": max_consecutive_wins_pnl,
        "max_consecutive_losses_pnl": max_consecutive_losses_pnl,

        # Frequency
        "trade_frequency": (total_trades / bars) * 100,

        # Meta
        "signals": signals_generated,
        "filters": filter_rejections,
        "trades": completed_trades
    }

    if verbose:
        # MT5 Strategy Tester style report
        print("=" * 70)
        print("BACKTEST RESULTS - STRATEGY TESTER REPORT")
        print("=" * 70)

        print(f"\n{'Trades':<30} {total_trades:>10}")
        print(f"{'Profit trades (% of total)':<30} {len(winning_trades):>6} ({profit_trades_pct:.1f}%)")
        print(f"{'Loss trades (% of total)':<30} {len(losing_trades):>6} ({loss_trades_pct:.1f}%)")
        print(f"{'  Long trades (won %)':<30} {trade_count_long:>6} ({win_rate_long:.1f}%)")
        print(f"{'  Short trades (won %)':<30} {trade_count_short:>6} ({win_rate_short:.1f}%)")

        print(f"\n{'Gross Profit':<30} {gross_profit_pips:>10.2f} pips")
        print(f"{'Gross Loss':<30} {gross_loss_pips:>10.2f} pips")
        print(f"{'Total Net Profit':<30} {total_pnl_after_costs:>10.2f} pips")
        pf_str = f"{profit_factor:.2f}" if profit_factor != float('inf') else "Inf"
        print(f"{'Profit Factor':<30} {pf_str:>10}")
        print(f"{'Expected Payoff':<30} {expected_payoff_pips:>10.2f} pips")
        print(f"{'Recovery Factor':<30} {recovery_factor:>10.2f}")

        print(f"\n{'Absolute Drawdown':<30} {max_drawdown:>10.2f} pips")
        print(f"{'Maximal Drawdown':<30} {max_drawdown:>10.2f} pips ({max_drawdown_pct:.2f}%)")
        print(f"{'Relative Drawdown':<30} {max_drawdown_pct:>9.2f}% ({max_drawdown:.2f} pips)")

        print(f"\n{'Largest profit trade':<30} {largest_win_pips:>10.2f} pips")
        print(f"{'Largest loss trade':<30} {largest_loss_pips:>10.2f} pips")
        print(f"{'Average profit trade':<30} {avg_win_pips:>10.2f} pips")
        print(f"{'Average loss trade':<30} {avg_loss_pips:>10.2f} pips")

        print(f"\n{'Maximum consecutive wins':<30} {max_consecutive_wins:>6} ({max_consecutive_wins_pnl:+.2f} pips)")
        print(f"{'Maximum consecutive losses':<30} {max_consecutive_losses:>6} ({max_consecutive_losses_pnl:+.2f} pips)")

        # Cost breakdown
        cost_impact_pips = total_pnl_pips - total_pnl_after_costs
        print(f"\n{'--- COST ANALYSIS ---'}")
        print(f"{'P&L before costs':<30} {total_pnl_pips:>10.2f} pips")
        print(f"{'Total costs':<30} {cost_impact_pips:>10.2f} pips")
        print(f"{'P&L after costs':<30} {total_pnl_after_costs:>10.2f} pips")

        # Filter stats
        print(f"\n{'--- FILTER STATISTICS ---'}")
        print(f"{'Confidence rejections':<30} {filter_rejections['confidence']:>10}")
        print(f"{'Broken level rejections':<30} {filter_rejections['broken_level']:>10}")
        print(f"{'Signals generated (BUY/SELL)':<30} {signals_generated['BUY']}/{signals_generated['SELL']:>5}")

        print("=" * 70 + "\n")

    return results


def _run_single_backtest(args):
    """
    Worker function for parallel backtest execution.
    This function is called by each worker process.

    Args:
        args: Tuple of (params_dict, backtest_kwargs, df_slice)

    Returns:
        Dict with backtest results merged with parameters
    """
    params, backtest_kwargs, df_slice = args

    # Run backtest with these parameters
    result = run_backtest(
        min_confidence=params.get('min_confidence'),
        broken_level_cooldown_hours=params.get('broken_level_cooldown_hours'),
        broken_level_break_pips=params.get('broken_level_break_pips', 15.0),
        enable_confidence_filter='min_confidence' in params,
        enable_broken_level_filter='broken_level_cooldown_hours' in params,
        df=df_slice,
        verbose=False,
        **backtest_kwargs
    )

    # Merge parameters into result
    result.update(params)

    return result


def run_grid_search(
        param_grid: Dict,
        symbol: str = "EURUSD",
        timeframe: str = "H1",
        bars: int = 500,
        lookback_bars: int = 400,
        spread_pips: float = 1.0,
        commission_per_side_per_lot: float = 7.0,
        slippage_pips: float = 0.5,
        usd_per_pip_per_lot: float = 10.0,
        starting_balance_usd: float = 10000.0,
        df: Optional[pd.DataFrame] = None,
        n_jobs: int = -1
) -> pd.DataFrame:
    """
    Run grid search over parameter combinations using parallel processing.

    Args:
        param_grid: Dict with parameter names as keys and list of values to test
        symbol, timeframe, bars, lookback_bars: Backtest settings
        spread_pips, commission_per_side_per_lot, slippage_pips, usd_per_pip_per_lot: Cost settings
        starting_balance_usd: Starting account balance in USD (for drawdown %)
        df: Pre-loaded DataFrame (if None, will fetch from MT5)
        n_jobs: Number of parallel workers (-1 = use all CPU cores, 1 = sequential)

    Returns:
        DataFrame with results sorted by profit factor
    """
    import multiprocessing

    print("\n" + "=" * 70)
    print("GRID SEARCH - Parameter Optimization (Multi-Core)")
    print("=" * 70)
    print(f"\nTesting parameter combinations:")
    for param, values in param_grid.items():
        print(f"  {param}: {values}")

    # Generate all combinations
    param_names = list(param_grid.keys())
    param_values = list(param_grid.values())
    combinations = list(product(*param_values))

    total_combinations = len(combinations)

    # Determine number of workers
    if n_jobs == -1:
        n_workers = multiprocessing.cpu_count()
    elif n_jobs <= 0:
        n_workers = max(1, multiprocessing.cpu_count() + n_jobs)
    else:
        n_workers = min(n_jobs, total_combinations)

    print(f"\nTotal combinations: {total_combinations}")
    print(f"CPU cores available: {multiprocessing.cpu_count()}")
    print(f"Using {n_workers} parallel workers")
    print("\nRunning backtests...\n")

    # Prepare backtest kwargs (common to all backtests)
    backtest_kwargs = {
        'symbol': symbol,
        'timeframe': timeframe,
        'bars': bars,
        'lookback_bars': lookback_bars,
        'spread_pips': spread_pips,
        'commission_per_side_per_lot': commission_per_side_per_lot,
        'slippage_pips': slippage_pips,
        'usd_per_pip_per_lot': usd_per_pip_per_lot,
        'starting_balance_usd': starting_balance_usd
    }

    # Prepare arguments for each worker
    worker_args = []
    for combo in combinations:
        params = dict(zip(param_names, combo))
        worker_args.append((params, backtest_kwargs, df))

    results_list = []
    completed = 0
    failed = 0

    # Run backtests in parallel
    if n_workers == 1:
        # Sequential execution (for debugging)
        for idx, args in enumerate(worker_args, 1):
            params = args[0]
            print(f"[{idx}/{total_combinations}] Testing: {params}")
            result = _run_single_backtest(args)

            if 'profit_factor' in result:
                results_list.append(result)
                completed += 1
            else:
                print(f"  FAILED: {result.get('error', 'Unknown error')}")
                failed += 1
    else:
        # Parallel execution
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            # Submit all jobs
            future_to_params = {
                executor.submit(_run_single_backtest, args): args[0]
                for args in worker_args
            }

            # Process results as they complete
            for future in as_completed(future_to_params):
                params = future_to_params[future]
                completed += 1

                try:
                    result = future.result()

                    if 'profit_factor' in result:
                        results_list.append(result)
                        print(f"[{completed}/{total_combinations}] ✓ Completed: {params} - PF: {result['profit_factor']:.2f}, Trades: {result['total_trades']}")
                    else:
                        failed += 1
                        print(f"[{completed}/{total_combinations}] ✗ Failed: {params} - {result.get('error', 'Unknown error')}")

                except Exception as e:
                    failed += 1
                    print(f"[{completed}/{total_combinations}] ✗ Exception: {params} - {str(e)}")

    # Create DataFrame
    df_results = pd.DataFrame(results_list)

    # Sort by profit factor (descending)
    if len(df_results) > 0:
        df_results = df_results.sort_values('profit_factor', ascending=False)
    else:
        print("\nWARNING: No successful backtests to display")

    print("\n" + "=" * 70)
    print("GRID SEARCH COMPLETE")
    print("=" * 70)
    print(f"\nSummary:")
    print(f"  Total tests: {total_combinations}")
    print(f"  Successful: {len(results_list)}")
    print(f"  Failed: {failed}")
    print(f"  Success rate: {(len(results_list)/total_combinations*100):.1f}%")
    print("=" * 70)

    return df_results


def run_walk_forward(
        symbol: str = "EURUSD",
        timeframe: str = "H1",
        total_bars: int = 2000,
        lookback_bars: int = 400,
        splits: int = 5,
        train_bars: int = 300,
        test_bars: int = 100,
        param_grid: Optional[Dict] = None,
        spread_pips: float = 1.0,
        commission_per_side_per_lot: float = 7.0,
        slippage_pips: float = 0.5,
        usd_per_pip_per_lot: float = 10.0,
        starting_balance_usd: float = 10000.0,
        broken_level_break_pips: float = 15.0,
        n_jobs: int = -1
) -> pd.DataFrame:
    """
    Run walk-forward analysis: train on one segment, test on next segment.

    This prevents overfitting by ensuring test data is never used for parameter optimization.

    Args:
        symbol, timeframe: Trading pair and timeframe
        total_bars: Total bars to fetch from MT5
        lookback_bars: Bars needed for indicator calculation
        splits: Number of train/test windows
        train_bars: Size of training segment
        test_bars: Size of testing segment
        param_grid: Parameters to optimize (default: min_confidence + cooldown)
        spread_pips, commission_per_side_per_lot, slippage_pips, usd_per_pip_per_lot: Cost settings
        broken_level_break_pips: Pips beyond level to mark as broken
        n_jobs: Number of parallel workers for grid search

    Returns:
        DataFrame with one row per split containing train/test results
    """
    print("\n" + "=" * 70)
    print("WALK-FORWARD ANALYSIS")
    print("=" * 70)
    print(f"\nConfiguration:")
    print(f"  Symbol: {symbol} {timeframe}")
    print(f"  Total bars: {total_bars} (+ {lookback_bars} lookback)")
    print(f"  Splits: {splits}")
    print(f"  Train bars: {train_bars}")
    print(f"  Test bars: {test_bars}")
    print(f"  Segment size: {train_bars + test_bars} bars")
    print("=" * 70)

    # Default param grid if not provided
    if param_grid is None:
        param_grid = {
            'min_confidence': [0.60, 0.65, 0.70],
            'broken_level_cooldown_hours': [12.0, 24.0, 48.0]
        }

    # Fetch data once
    print(f"\nFetching {total_bars + lookback_bars} bars from MT5...")
    try:
        df_full = fetch_ohlc(symbol, timeframe, total_bars + lookback_bars)
        if df_full is None or len(df_full) < lookback_bars + train_bars + test_bars:
            print(f"✗ Insufficient data")
            return pd.DataFrame()
    except Exception as e:
        print(f"✗ Data fetch failed: {e}")
        return pd.DataFrame()

    print(f"✓ Fetched {len(df_full)} bars")
    print(f"  Range: {df_full['time'].iloc[0]} to {df_full['time'].iloc[-1]}")

    # Calculate split positions
    segment_size = train_bars + test_bars
    available_bars = len(df_full) - lookback_bars
    max_splits = available_bars // segment_size

    if splits > max_splits:
        print(f"\nWARNING: Requested {splits} splits but only {max_splits} possible with current data")
        splits = max_splits

    print(f"\nRunning {splits} walk-forward splits...")

    split_results = []

    for split_idx in range(splits):
        print("\n" + "-" * 70)
        print(f"SPLIT {split_idx + 1}/{splits}")
        print("-" * 70)

        # Calculate indices for this split
        split_start = lookback_bars + (split_idx * segment_size)
        train_start = split_start
        train_end = train_start + train_bars
        test_start = train_end
        test_end = test_start + test_bars

        # Extract segments
        train_df = df_full.iloc[:train_end].copy()
        test_df = df_full.iloc[:test_end].copy()

        print(f"\nTrain segment:")
        print(f"  Bars: {train_start} to {train_end} ({train_bars} bars)")
        print(f"  Time: {df_full.iloc[train_start]['time']} to {df_full.iloc[train_end-1]['time']}")

        print(f"\nTest segment:")
        print(f"  Bars: {test_start} to {test_end} ({test_bars} bars)")
        print(f"  Time: {df_full.iloc[test_start]['time']} to {df_full.iloc[test_end-1]['time']}")

        # TRAIN: Run grid search on train segment
        print(f"\n[TRAIN] Running grid search on {train_bars} bars...")

        train_results = run_grid_search(
            param_grid=param_grid,
            symbol=symbol,
            timeframe=timeframe,
            bars=train_bars,
            lookback_bars=lookback_bars,
            spread_pips=spread_pips,
            commission_per_side_per_lot=commission_per_side_per_lot,
            slippage_pips=slippage_pips,
            usd_per_pip_per_lot=usd_per_pip_per_lot,
            starting_balance_usd=starting_balance_usd,
            df=train_df,
            n_jobs=n_jobs
        )

        if len(train_results) == 0:
            print(f"\n✗ No successful backtests in training - skipping split {split_idx + 1}")
            continue

        # Select best parameters (by profit_factor, then total_pnl_after_costs)
        best_idx = train_results.sort_values(
            by=['profit_factor', 'total_pnl_after_costs'],
            ascending=[False, False]
        ).index[0]
        best_params = train_results.loc[best_idx]

        print(f"\n[TRAIN] Best parameters found:")
        for key in param_grid.keys():
            print(f"  {key}: {best_params[key]}")
        print(f"  Train PF: {best_params['profit_factor']:.2f}")
        print(f"  Train Trades: {best_params['total_trades']}")
        print(f"  Train PnL: {best_params['total_pnl_after_costs']:.1f} pips")

        # TEST: Run single backtest on test segment with best params
        print(f"\n[TEST] Testing on {test_bars} bars with best params...")

        # Extract test parameters
        test_param_dict = {key: best_params[key] for key in param_grid.keys()}

        test_result = run_backtest(
            symbol=symbol,
            timeframe=timeframe,
            bars=test_bars,
            lookback_bars=lookback_bars,
            spread_pips=spread_pips,
            commission_per_side_per_lot=commission_per_side_per_lot,
            slippage_pips=slippage_pips,
            usd_per_pip_per_lot=usd_per_pip_per_lot,
            starting_balance_usd=starting_balance_usd,
            min_confidence=test_param_dict.get('min_confidence'),
            broken_level_cooldown_hours=test_param_dict.get('broken_level_cooldown_hours'),
            broken_level_break_pips=test_param_dict.get('broken_level_break_pips', broken_level_break_pips),
            enable_confidence_filter='min_confidence' in test_param_dict,
            enable_broken_level_filter='broken_level_cooldown_hours' in test_param_dict,
            df=test_df,
            verbose=False
        )

        if 'profit_factor' not in test_result:
            print(f"\n✗ Test backtest failed: {test_result.get('error', 'Unknown error')}")
            continue

        print(f"\n[TEST] Results:")
        print(f"  Test PF: {test_result['profit_factor']:.2f}")
        print(f"  Test Trades: {test_result['total_trades']}")
        print(f"  Test PnL: {test_result['total_pnl_after_costs']:.1f} pips")
        print(f"  Test Win Rate: {test_result['win_rate']:.1f}%")

        # Store split results
        split_result = {
            'split': split_idx + 1,
            'train_start': df_full.iloc[train_start]['time'],
            'train_end': df_full.iloc[train_end - 1]['time'],
            'test_start': df_full.iloc[test_start]['time'],
            'test_end': df_full.iloc[test_end - 1]['time'],
            # Best params
            **{f'param_{k}': v for k, v in test_param_dict.items()},
            # Train metrics
            'train_profit_factor': best_params['profit_factor'],
            'train_total_trades': best_params['total_trades'],
            'train_win_rate': best_params['win_rate'],
            'train_total_pnl_after_costs': best_params['total_pnl_after_costs'],
            'train_max_drawdown': best_params['max_drawdown'],
            # Test metrics
            'test_profit_factor': test_result['profit_factor'],
            'test_total_trades': test_result['total_trades'],
            'test_win_rate': test_result['win_rate'],
            'test_total_pnl_after_costs': test_result['total_pnl_after_costs'],
            'test_max_drawdown': test_result['max_drawdown']
        }

        split_results.append(split_result)

    # Create results DataFrame
    df_results = pd.DataFrame(split_results)

    if len(df_results) == 0:
        print("\n✗ No successful splits")
        return df_results

    # Print aggregate summary
    print("\n" + "=" * 70)
    print("WALK-FORWARD SUMMARY - TEST RESULTS ONLY")
    print("=" * 70)
    print(f"\nCompleted splits: {len(df_results)}/{splits}")
    print(f"\nAggregate test metrics:")
    print(f"  Mean Profit Factor: {df_results['test_profit_factor'].mean():.2f}")
    print(f"  Median Profit Factor: {df_results['test_profit_factor'].median():.2f}")
    print(f"  Total Test Trades: {df_results['test_total_trades'].sum():.0f}")
    print(f"  Mean Win Rate: {df_results['test_win_rate'].mean():.1f}%")
    print(f"  Total PnL (after costs): {df_results['test_total_pnl_after_costs'].sum():.1f} pips")
    print(f"  Mean PnL per split: {df_results['test_total_pnl_after_costs'].mean():.1f} pips")
    print(f"  Max Drawdown (worst): {df_results['test_max_drawdown'].max():.1f} pips")
    print(f"  Profitable splits: {(df_results['test_total_pnl_after_costs'] > 0).sum()}/{len(df_results)}")
    print("=" * 70)

    return df_results


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("VOLARIX 4 BACKTEST SUITE")
    print("=" * 70)
    print("\nAvailable modes:")
    print("  1. Baseline - Single backtest with fixed parameters")
    print("  2. Grid Search - Test multiple parameter combinations")
    print("  3. Walk-Forward - Train/test splits to avoid overfitting")
    print("\nSelect mode (or edit __main__ to customize):")
    print("=" * 70)

    # Default: Run walk-forward analysis
    MODE = "walk-forward"  # Options: "baseline", "grid-search", "walk-forward"

    if MODE == "baseline":
        # Run baseline backtest
        print("\n>>> Running Baseline Backtest (with costs)\n")
        baseline = run_backtest(
            symbol="EURUSD",
            timeframe="H1",
            bars=500,
            lookback_bars=400,
            spread_pips=1.5,
            commission_per_side_per_lot=7.0,
            slippage_pips=0.5,
            usd_per_pip_per_lot=10.0,
            starting_balance_usd=10000.0,
            min_confidence=0.65,
            broken_level_cooldown_hours=24.0,
            broken_level_break_pips=15.0,
            verbose=True
        )

    elif MODE == "grid-search":
        # Run grid search (multi-core)
        print("\n>>> Running Grid Search (Parallel Processing)\n")
        param_grid = {
            'min_confidence': [0.60, 0.65, 0.70, 0.75],
            'broken_level_cooldown_hours': [12.0, 24.0, 48.0]
        }

        results_df = run_grid_search(
            param_grid=param_grid,
            symbol="EURUSD",
            timeframe="H1",
            bars=500,
            lookback_bars=400,
            spread_pips=1.5,
            commission_per_side_per_lot=7.0,
            slippage_pips=0.5,
            usd_per_pip_per_lot=10.0,
            starting_balance_usd=10000.0,
            n_jobs=-1  # -1 = use all CPU cores, 1 = sequential, N = use N cores
        )

        # Display top 10 results
        print("\nTop 10 Parameter Combinations:")
        print("=" * 70)

        if len(results_df) > 0:
            display_cols = ['min_confidence', 'broken_level_cooldown_hours', 'total_trades',
                           'win_rate', 'profit_factor', 'total_pnl_after_costs', 'max_drawdown']
            print(results_df[display_cols].head(10).to_string(index=False))
        else:
            print("No results to display - all backtests failed")

    elif MODE == "walk-forward":
        # Run walk-forward analysis
        print("\n>>> Running Walk-Forward Analysis\n")

        param_grid = {
            'min_confidence': [0.60, 0.65, 0.70],
            'broken_level_cooldown_hours': [12.0, 24.0, 48.0]
        }

        wf_results = run_walk_forward(
            symbol="EURUSD",
            timeframe="H1",
            total_bars=2000,
            lookback_bars=400,
            splits=3,
            train_bars=400,
            test_bars=200,
            param_grid=param_grid,
            spread_pips=1.5,
            commission_per_side_per_lot=7.0,
            slippage_pips=0.5,
            usd_per_pip_per_lot=10.0,
            starting_balance_usd=10000.0,
            n_jobs=-1
        )

        # Display detailed results
        if len(wf_results) > 0:
            print("\nDetailed Walk-Forward Results:")
            print("=" * 70)
            display_cols = ['split', 'param_min_confidence', 'param_broken_level_cooldown_hours',
                           'train_profit_factor', 'test_profit_factor',
                           'train_total_trades', 'test_total_trades',
                           'test_total_pnl_after_costs']
            print(wf_results[display_cols].to_string(index=False))

    print("\n" + "=" * 70)
    print("Backtest Suite Complete")
    print("=" * 70 + "\n")
