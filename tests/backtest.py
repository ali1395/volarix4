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
        # Filter parameters
        min_confidence: Optional[float] = None,
        broken_level_cooldown_hours: Optional[float] = None,
        broken_level_break_pips: float = 15.0,
        enable_confidence_filter: bool = True,
        enable_broken_level_filter: bool = True,
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
        min_confidence: Minimum confidence threshold (None = no filter)
        broken_level_cooldown_hours: Hours to block broken levels (None = no filter)
        broken_level_break_pips: Pips beyond level to mark as broken
        enable_confidence_filter: Enable confidence filtering
        enable_broken_level_filter: Enable broken level filtering
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
            "profit_factor": 0.0,
            "total_pnl_pips": 0.0,
            "total_pnl_after_costs": 0.0,
            "max_drawdown": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "trade_frequency": 0.0,
            "signals": signals_generated,
            "filters": filter_rejections,
            "trades": []
        }

    winning_trades = [t for t in completed_trades if t.status == "win"]
    losing_trades = [t for t in completed_trades if t.status == "loss"]

    win_rate = (len(winning_trades) / total_trades) * 100

    total_pnl_pips = sum([t.pnl_pips for t in completed_trades])
    total_pnl_after_costs = sum([t.pnl_after_costs for t in completed_trades])

    gross_profit = sum([t.pnl_after_costs for t in winning_trades])
    gross_loss = abs(sum([t.pnl_after_costs for t in losing_trades]))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    avg_win = gross_profit / len(winning_trades) if winning_trades else 0.0
    avg_loss = gross_loss / len(losing_trades) if losing_trades else 0.0

    # Calculate max drawdown
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

    results = {
        "total_trades": total_trades,
        "winning_trades": len(winning_trades),
        "losing_trades": len(losing_trades),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "total_pnl_pips": total_pnl_pips,
        "total_pnl_after_costs": total_pnl_after_costs,
        "max_drawdown": max_drawdown,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "trade_frequency": (total_trades / bars) * 100,
        "signals": signals_generated,
        "filters": filter_rejections,
        "trades": completed_trades
    }

    if verbose:
        print("=" * 70)
        print("BACKTEST RESULTS")
        print("=" * 70)
        print(f"\nTrading Statistics")
        print(f"  Total Trades: {total_trades}")
        print(f"  Winning: {len(winning_trades)} ({win_rate:.1f}%)")
        print(f"  Losing: {len(losing_trades)} ({100 - win_rate:.1f}%)")
        print(f"\nProfitability")
        print(f"  Profit Factor: {profit_factor:.2f}")
        print(f"  Total P&L (before costs): {total_pnl_pips:+.1f} pips")
        print(f"  Total P&L (after costs): {total_pnl_after_costs:+.1f} pips")
        print(f"  Cost Impact: {total_pnl_pips - total_pnl_after_costs:.1f} pips")
        print(f"  Max Drawdown: {max_drawdown:.1f} pips")
        print(f"  Avg Win: +{avg_win:.1f} pips")
        print(f"  Avg Loss: -{avg_loss:.1f} pips")
        print(f"\nFilters")
        print(f"  Confidence Rejections: {filter_rejections['confidence']}")
        print(f"  Broken Level Rejections: {filter_rejections['broken_level']}")
        print("=" * 70 + "\n")

    return results


def run_grid_search(
        param_grid: Dict,
        symbol: str = "EURUSD",
        timeframe: str = "H1",
        bars: int = 500,
        lookback_bars: int = 400,
        spread_pips: float = 1.0,
        commission_per_side_per_lot: float = 7.0,
        slippage_pips: float = 0.5,
        usd_per_pip_per_lot: float = 10.0
) -> pd.DataFrame:
    """
    Run grid search over parameter combinations.

    Args:
        param_grid: Dict with parameter names as keys and list of values to test
        symbol, timeframe, bars, lookback_bars: Backtest settings
        spread_pips, commission_per_side_per_lot, slippage_pips, usd_per_pip_per_lot: Cost settings

    Returns:
        DataFrame with results sorted by profit factor
    """
    print("\n" + "=" * 70)
    print("GRID SEARCH - Parameter Optimization")
    print("=" * 70)
    print(f"\nTesting parameter combinations:")
    for param, values in param_grid.items():
        print(f"  {param}: {values}")

    # Generate all combinations
    param_names = list(param_grid.keys())
    param_values = list(param_grid.values())
    combinations = list(product(*param_values))

    total_combinations = len(combinations)
    print(f"\nTotal combinations: {total_combinations}")
    print("\nRunning backtests...\n")

    results_list = []

    for idx, combo in enumerate(combinations, 1):
        params = dict(zip(param_names, combo))

        print(f"[{idx}/{total_combinations}] Testing: {params}")

        # Run backtest
        result = run_backtest(
            symbol=symbol,
            timeframe=timeframe,
            bars=bars,
            lookback_bars=lookback_bars,
            spread_pips=spread_pips,
            commission_per_side_per_lot=commission_per_side_per_lot,
            slippage_pips=slippage_pips,
            usd_per_pip_per_lot=usd_per_pip_per_lot,
            min_confidence=params.get('min_confidence'),
            broken_level_cooldown_hours=params.get('broken_level_cooldown_hours'),
            broken_level_break_pips=params.get('broken_level_break_pips', 15.0),
            enable_confidence_filter='min_confidence' in params,
            enable_broken_level_filter='broken_level_cooldown_hours' in params,
            verbose=False
        )

        # Add parameters to results
        result.update(params)

        # Only add to results if backtest succeeded (has profit_factor key)
        if 'profit_factor' in result:
            results_list.append(result)
        else:
            print(f"  FAILED: {result.get('error', 'Unknown error')}")

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

    return df_results


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("VOLARIX 4 BACKTEST SUITE")
    print("=" * 70)

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
        min_confidence=0.65,
        broken_level_cooldown_hours=24.0,
        broken_level_break_pips=15.0,
        verbose=True
    )

    # Run grid search
    print("\n>>> Running Grid Search\n")
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
        usd_per_pip_per_lot=10.0
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

    print("\n" + "=" * 70)
    print("Backtest Suite Complete")
    print("=" * 70 + "\n")
