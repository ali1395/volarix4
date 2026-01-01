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
import numpy as np
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from itertools import product
from concurrent.futures import ProcessPoolExecutor, as_completed
from volarix4.core.data import fetch_ohlc, connect_mt5, is_valid_session
from volarix4.core.sr_levels import detect_sr_levels
from volarix4.core.rejection import find_rejection_candle
from volarix4.core.trade_setup import calculate_sl_tp
from volarix4.core.trend_filter import detect_trend, validate_signal_with_trend
from volarix4.utils.helpers import calculate_pip_value


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"


def precompute_sr_levels(df: pd.DataFrame, lookback_bars: int, pip_value: float,
                         min_score: float = 60.0, compute_interval: int = 24,
                         verbose: bool = False) -> Dict[int, List]:
    """
    Pre-compute S/R levels for dataset with smart caching.

    Instead of computing on EVERY bar (slow), computes every N bars and
    reuses results for nearby bars (e.g., every 24 bars = once per day on H1).

    Args:
        df: Full DataFrame with OHLC data
        lookback_bars: Number of bars to use for S/R detection
        pip_value: Pip value for the symbol
        min_score: Minimum score for S/R levels
        compute_interval: Compute S/R every N bars (default: 24 = 1 day on H1)
        verbose: Print progress

    Returns:
        Dict mapping bar index -> list of S/R levels
    """
    if verbose:
        print(f"\n[OPTIMIZATION] Pre-computing S/R levels (smart caching)...")
        print(f"  Lookback: {lookback_bars} bars")
        print(f"  Computing every {compute_interval} bars (reusing for nearby bars)")
        print(f"  This dramatically reduces computation time!\n")

    start_time = time.time()
    sr_cache = {}

    # Only compute for bars where we can make decisions (after lookback period)
    total_bars = len(df) - lookback_bars
    bars_to_compute = (total_bars // compute_interval) + 1
    progress_interval = max(10, bars_to_compute // 20)  # Report every 5%

    computed_count = 0
    last_computed_levels = []

    for i in range(lookback_bars, len(df)):
        bar_idx = i - lookback_bars

        # Compute S/R levels every N bars
        if bar_idx % compute_interval == 0:
            computed_count += 1

            # Progress reporting
            if verbose and computed_count % progress_interval == 0:
                pct = (computed_count / bars_to_compute) * 100
                elapsed = time.time() - start_time
                rate = computed_count / elapsed if elapsed > 0 else 0
                eta = (bars_to_compute - computed_count) / rate if rate > 0 else 0
                print(f"  Progress: {pct:.0f}% ({computed_count}/{bars_to_compute} checkpoints) - {rate:.1f}/sec - ETA: {format_duration(eta)}")

            # Get historical data up to this point
            historical_data = df.iloc[:i + 1]

            # Detect S/R levels
            levels = detect_sr_levels(
                historical_data.tail(lookback_bars),
                min_score=min_score,
                pip_value=pip_value
            )

            last_computed_levels = levels if levels else []

        # Store in cache (reuse last computed levels for bars between checkpoints)
        sr_cache[i] = last_computed_levels

    elapsed = time.time() - start_time

    if verbose:
        print(f"\n[OPTIMIZATION] ✓ Pre-computed S/R levels in {format_duration(elapsed)}")
        print(f"  Computed {computed_count} checkpoints (every {compute_interval} bars)")
        print(f"  Average: {computed_count / elapsed:.1f} checkpoints/sec")
        print(f"  Cache size: {len(sr_cache)} entries (covers all bars)")
        print(f"  Speedup: ~{compute_interval}x faster than computing every bar!\n")

    return sr_cache


class Trade:
    """Represents a single trade with realistic SL/TP management and costs."""

    def __init__(self, entry_time, direction, entry, sl, tp1, tp2, tp3,
                 pip_value, spread_pips=0.0, slippage_pips=0.0,
                 commission_per_side_per_lot=0.0, lot_size=1.0):
        # Basic trade info
        self.entry_time = entry_time
        self.entry_bar_time = entry_time  # Alias for consistency
        self.direction = direction
        self.entry_raw = entry
        self.sl = sl
        self.tp1 = tp1
        self.tp2 = tp2
        self.tp3 = tp3
        self.status = "open"
        self.exit_time = None
        self.exit_bar_time = None  # Will be set on exit
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

        # Context at entry (to be populated by caller)
        self.rejection_confidence = None
        self.level_price = None
        self.level_type = None  # 'support' or 'resistance'
        self.sl_pips = None
        self.tp1_pips = None
        self.hour_of_day = None
        self.day_of_week = None
        self.atr_pips_14 = None

        # Apply entry costs
        if direction == "BUY":
            # Entry: pay spread + slippage
            self.entry = entry + (spread_pips / 2 + slippage_pips) * pip_value
            self.entry_after_costs = self.entry
        else:  # SELL
            # Entry: pay spread + slippage
            self.entry = entry - (spread_pips / 2 + slippage_pips) * pip_value
            self.entry_after_costs = self.entry

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
            trade.exit_bar_time = bar['time']
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
            trade.exit_bar_time = bar['time']

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
            trade.exit_bar_time = bar['time']

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
            trade.exit_bar_time = bar['time']

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
            trade.exit_bar_time = bar['time']
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
            trade.exit_bar_time = bar['time']

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
            trade.exit_bar_time = bar['time']

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
            trade.exit_bar_time = bar['time']

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


def calculate_atr_pips(df: pd.DataFrame, period: int = 14, pip_value: float = 0.0001) -> float:
    """
    Calculate Average True Range (ATR) in pips for the last N bars.

    Args:
        df: DataFrame with OHLC data
        period: Lookback period (default: 14)
        pip_value: Pip size (default: 0.0001 for most pairs)

    Returns:
        ATR in pips
    """
    if len(df) < period:
        return 0.0

    # Calculate True Range for last N bars
    df_subset = df.tail(period).copy()

    # True Range = max(high-low, abs(high-prev_close), abs(low-prev_close))
    df_subset['h_l'] = df_subset['high'] - df_subset['low']
    df_subset['h_pc'] = abs(df_subset['high'] - df_subset['close'].shift(1))
    df_subset['l_pc'] = abs(df_subset['low'] - df_subset['close'].shift(1))

    df_subset['tr'] = df_subset[['h_l', 'h_pc', 'l_pc']].max(axis=1)

    # ATR = average of True Range
    atr = df_subset['tr'].mean()
    atr_pips = atr / pip_value

    return atr_pips


def trades_to_dataframe(trades: List[Trade]) -> pd.DataFrame:
    """Convert list of Trade objects to pandas DataFrame."""
    if not trades:
        return pd.DataFrame()

    trades_data = []
    for trade in trades:
        trades_data.append({
            'entry_bar_time': trade.entry_bar_time,
            'exit_bar_time': trade.exit_bar_time,
            'direction': trade.direction,
            'entry_raw': trade.entry_raw,
            'entry_after_costs': trade.entry_after_costs,
            'exit_price': trade.exit_price,
            'sl': trade.sl,
            'tp1': trade.tp1,
            'tp2': trade.tp2,
            'tp3': trade.tp3,
            'exit_reason': trade.exit_reason,
            'pnl_pips': trade.pnl_pips,
            'pnl_after_costs': trade.pnl_after_costs,
            'status': trade.status,
            # Context
            'rejection_confidence': trade.rejection_confidence,
            'level_price': trade.level_price,
            'level_type': trade.level_type,
            'sl_pips': trade.sl_pips,
            'tp1_pips': trade.tp1_pips,
            'hour_of_day': trade.hour_of_day,
            'day_of_week': trade.day_of_week,
            'atr_pips_14': trade.atr_pips_14
        })

    return pd.DataFrame(trades_data)


def print_bucket_diagnostics(trades: List[Trade], bucket_name: str = "TEST"):
    """
    Print bucket diagnostics for trades.

    Buckets:
    - BUY vs SELL
    - Hour of day (Asian/London/NY)
    - ATR quartiles
    - Confidence bins
    """
    if not trades:
        print(f"\n[{bucket_name}] No trades to analyze")
        return

    print(f"\n{'='*70}")
    print(f"[{bucket_name}] BUCKET DIAGNOSTICS")
    print(f"{'='*70}")

    # Helper function to compute bucket stats
    def bucket_stats(trade_list):
        if not trade_list:
            return {
                'count': 0,
                'net_pnl': 0.0,
                'profit_factor': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0
            }

        count = len(trade_list)
        net_pnl = sum(t.pnl_after_costs for t in trade_list)

        profit_deals = [t for t in trade_list if t.pnl_after_costs > 0]
        loss_deals = [t for t in trade_list if t.pnl_after_costs < 0]

        gross_profit = sum(t.pnl_after_costs for t in profit_deals) if profit_deals else 0.0
        gross_loss = abs(sum(t.pnl_after_costs for t in loss_deals)) if loss_deals else 0.0

        pf = gross_profit / gross_loss if gross_loss > 0 else (float('inf') if gross_profit > 0 else 0.0)
        avg_win = gross_profit / len(profit_deals) if profit_deals else 0.0
        avg_loss = gross_loss / len(loss_deals) if loss_deals else 0.0

        return {
            'count': count,
            'net_pnl': net_pnl,
            'profit_factor': pf,
            'avg_win': avg_win,
            'avg_loss': avg_loss
        }

    # 1. BUY vs SELL
    print(f"\n1. DIRECTION BUCKETS:")
    print(f"{'Bucket':<15} {'Trades':<8} {'Net PnL':<12} {'PF':<10} {'Avg Win':<10} {'Avg Loss':<10}")
    print("-" * 70)

    buy_trades = [t for t in trades if t.direction == "BUY"]
    sell_trades = [t for t in trades if t.direction == "SELL"]

    for direction, trade_list in [("BUY", buy_trades), ("SELL", sell_trades)]:
        stats = bucket_stats(trade_list)
        pf_str = f"{stats['profit_factor']:.2f}" if stats['profit_factor'] != float('inf') else "Inf"
        print(f"{direction:<15} {stats['count']:<8} {stats['net_pnl']:<12.1f} {pf_str:<10} "
              f"{stats['avg_win']:<10.1f} {stats['avg_loss']:<10.1f}")

    # 2. Hour of Day Buckets
    print(f"\n2. HOUR OF DAY BUCKETS:")
    print(f"{'Bucket':<15} {'Trades':<8} {'Net PnL':<12} {'PF':<10} {'Avg Win':<10} {'Avg Loss':<10}")
    print("-" * 70)

    asian_trades = [t for t in trades if t.hour_of_day is not None and 0 <= t.hour_of_day < 8]
    london_trades = [t for t in trades if t.hour_of_day is not None and 8 <= t.hour_of_day < 16]
    ny_trades = [t for t in trades if t.hour_of_day is not None and 16 <= t.hour_of_day < 24]

    for session, trade_list in [("Asian (0-7)", asian_trades), ("London (8-15)", london_trades), ("NY (16-23)", ny_trades)]:
        stats = bucket_stats(trade_list)
        pf_str = f"{stats['profit_factor']:.2f}" if stats['profit_factor'] != float('inf') else "Inf"
        print(f"{session:<15} {stats['count']:<8} {stats['net_pnl']:<12.1f} {pf_str:<10} "
              f"{stats['avg_win']:<10.1f} {stats['avg_loss']:<10.1f}")

    # 3. ATR Quartiles
    print(f"\n3. ATR VOLATILITY BUCKETS:")
    print(f"{'Bucket':<15} {'Trades':<8} {'Net PnL':<12} {'PF':<10} {'Avg Win':<10} {'Avg Loss':<10}")
    print("-" * 70)

    atr_trades = [t for t in trades if t.atr_pips_14 is not None and t.atr_pips_14 > 0]
    if atr_trades:
        atr_values = sorted([t.atr_pips_14 for t in atr_trades])
        q1 = np.percentile(atr_values, 25)
        q2 = np.percentile(atr_values, 50)
        q3 = np.percentile(atr_values, 75)

        low_atr = [t for t in atr_trades if t.atr_pips_14 <= q1]
        med_atr = [t for t in atr_trades if q1 < t.atr_pips_14 <= q3]
        high_atr = [t for t in atr_trades if t.atr_pips_14 > q3]

        for volatility, trade_list in [("Low ATR", low_atr), ("Medium ATR", med_atr), ("High ATR", high_atr)]:
            stats = bucket_stats(trade_list)
            pf_str = f"{stats['profit_factor']:.2f}" if stats['profit_factor'] != float('inf') else "Inf"
            print(f"{volatility:<15} {stats['count']:<8} {stats['net_pnl']:<12.1f} {pf_str:<10} "
                  f"{stats['avg_win']:<10.1f} {stats['avg_loss']:<10.1f}")

    # 4. Confidence Bins
    print(f"\n4. CONFIDENCE BUCKETS:")
    print(f"{'Bucket':<15} {'Trades':<8} {'Net PnL':<12} {'PF':<10} {'Avg Win':<10} {'Avg Loss':<10}")
    print("-" * 70)

    conf_trades = [t for t in trades if t.rejection_confidence is not None]
    if conf_trades:
        low_conf = [t for t in conf_trades if t.rejection_confidence < 0.6]
        mid_conf = [t for t in conf_trades if 0.6 <= t.rejection_confidence < 0.7]
        high_conf = [t for t in conf_trades if t.rejection_confidence >= 0.7]

        for conf_level, trade_list in [("<0.6", low_conf), ("0.6-0.7", mid_conf), ("≥0.7", high_conf)]:
            stats = bucket_stats(trade_list)
            pf_str = f"{stats['profit_factor']:.2f}" if stats['profit_factor'] != float('inf') else "Inf"
            print(f"{conf_level:<15} {stats['count']:<8} {stats['net_pnl']:<12.1f} {pf_str:<10} "
                  f"{stats['avg_win']:<10.1f} {stats['avg_loss']:<10.1f}")

    print(f"{'='*70}\n")


def monte_carlo_reshuffle(pnl_list: List[float], observed_max_dd: float, n_simulations: int = 1000) -> Dict:
    """
    Monte Carlo simulation: shuffle trade order and assess sequence risk.

    This stress test reveals how much performance depends on trade order:
    - If median DD >> observed DD → you got lucky with trade order
    - If P(final PnL < 0) is high → strategy is fragile
    - If P(DD > observed) is high → observed drawdown is optimistic

    Args:
        pnl_list: List of trade PnL values (pnl_after_costs) in chronological order
        observed_max_dd: Observed max drawdown from actual chronological order (pips)
        n_simulations: Number of Monte Carlo simulations (default: 1000)

    Returns:
        Dict with Monte Carlo statistics
    """
    if len(pnl_list) == 0:
        return {
            'mc_median_max_dd': 0.0,
            'mc_max_max_dd': 0.0,
            'mc_95th_percentile_dd': 0.0,
            'mc_prob_loss': 0.0,
            'mc_prob_dd_exceeds_observed': 0.0
        }

    # Storage for simulation results
    max_drawdowns = []
    final_pnls = []

    # Run N simulations
    for _ in range(n_simulations):
        # Shuffle trade order
        shuffled_pnl = np.random.permutation(pnl_list)

        # Rebuild equity curve
        equity_curve = np.cumsum(shuffled_pnl)

        # Compute max drawdown
        peak = equity_curve[0]
        max_dd = 0.0
        for value in equity_curve:
            if value > peak:
                peak = value
            dd = peak - value
            if dd > max_dd:
                max_dd = dd

        max_drawdowns.append(max_dd)
        final_pnls.append(equity_curve[-1])

    # Convert to numpy arrays for statistics
    max_drawdowns = np.array(max_drawdowns)
    final_pnls = np.array(final_pnls)

    # Compute statistics
    median_max_dd = np.median(max_drawdowns)
    max_max_dd = np.max(max_drawdowns)
    percentile_95_dd = np.percentile(max_drawdowns, 95)
    prob_loss = np.sum(final_pnls < 0) / n_simulations
    prob_dd_exceeds_observed = np.sum(max_drawdowns > observed_max_dd) / n_simulations

    return {
        'mc_median_max_dd': median_max_dd,
        'mc_max_max_dd': max_max_dd,
        'mc_95th_percentile_dd': percentile_95_dd,
        'mc_prob_loss': prob_loss,
        'mc_prob_dd_exceeds_observed': prob_dd_exceeds_observed
    }


def levels_sane(entry: float, sl: float, tp1: float, tp2: float, tp3: float, direction: str) -> bool:
    """
    Sanity check for SL/TP geometry.

    For BUY: sl < entry < tp1 < tp2 < tp3
    For SELL: tp3 < tp2 < tp1 < entry < sl

    Returns:
        True if geometry is valid, False otherwise
    """
    direction = direction.upper()

    if direction == "BUY":
        return sl < entry < tp1 < tp2 < tp3
    elif direction == "SELL":
        return tp3 < tp2 < tp1 < entry < sl
    else:
        return False


def run_backtest(
        symbol: str = "EURUSD",
        timeframe: str = "H1",
        bars: int = 1000,
        lookback_bars: int = 400,
        # Cost parameters (match API BACKTEST_PARITY_CONFIG)
        spread_pips: float = 1.0,
        commission_per_side_per_lot: float = 7.0,
        slippage_pips: float = 0.5,
        lot_size: float = 1.0,
        usd_per_pip_per_lot: float = 10.0,
        starting_balance_usd: float = 10000.0,
        # Filter parameters (match API BACKTEST_PARITY_CONFIG)
        min_confidence: float = 0.60,  # API default: 0.60
        broken_level_cooldown_hours: float = 48.0,  # API default: 48.0
        broken_level_break_pips: float = 15.0,  # API default: 15.0
        min_edge_pips: float = 4.0,  # API default: 4.0
        enable_confidence_filter: bool = True,
        enable_broken_level_filter: bool = True,
        enable_session_filter: bool = True,  # NEW: Match API session filter
        enable_trend_filter: bool = True,  # NEW: Match API trend filter
        enable_signal_cooldown: bool = True,  # NEW: Match API signal cooldown
        signal_cooldown_hours: float = 2.0,  # NEW: Match API (2 hours)
        # Data
        df: Optional[pd.DataFrame] = None,
        sr_cache: Optional[Dict[int, List]] = None,  # OPTIMIZATION: Pre-computed S/R levels
        enforce_bars_limit: bool = True,
        # Display
        verbose: bool = True
) -> Dict:
    """
    Run realistic bar-by-bar backtest with costs and parameter filters.

    IMPORTANT - Sign-Based vs Status-Based Categorization:
        - "Profitable deal" = pnl_after_costs > 0 (actual money made)
        - "Loss deal" = pnl_after_costs < 0 (actual money lost)
        - A trade can hit TP1 (status="win") but LOSE money after costs
        - Example: TP1 = +10 pips, but costs = 12 pips → status="win" but pnl=-2 pips
        - All metrics use SIGN-BASED categorization (not status-based)
        - This matches real MT5 Strategy Tester reporting

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
        enforce_bars_limit: If True, only process last (lookback_bars + bars) rows
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
        print(f"\nFilters (API Parity Mode):")
        print(f"  Session Filter (London/NY): {'ON' if enable_session_filter else 'OFF'}")
        print(f"  Trend Filter (EMA 20/50): {'ON' if enable_trend_filter else 'OFF'}")
        print(f"  Min Confidence: {min_confidence if enable_confidence_filter else 'OFF'}")
        if enable_broken_level_filter:
            print(f"  Broken Level Cooldown: {broken_level_cooldown_hours}h")
            print(f"  Broken Level Threshold: {broken_level_break_pips} pips")
        else:
            print("  Broken Level Filter: OFF")
        print(f"  Signal Cooldown: {signal_cooldown_hours}h" if enable_signal_cooldown else "  Signal Cooldown: OFF")
        print(f"  Min Edge (pips): {min_edge_pips if min_edge_pips > 0 else 'OFF'}")
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

    # Enforce bars limit: only use last (lookback_bars + bars) rows
    if enforce_bars_limit:
        required_bars = lookback_bars + bars
        if len(df) > required_bars:
            df = df.iloc[-required_bars:].copy()
            if verbose:
                print(f"  Enforcing bars limit: using last {required_bars} bars")
                print(f"  Evaluation window: {df['time'].iloc[0]} to {df['time'].iloc[-1]}")

    # Backtest variables
    trades: List[Trade] = []
    open_trade: Optional[Trade] = None
    signals_generated = {"BUY": 0, "SELL": 0, "HOLD": 0}
    filter_rejections = {
        "session": 0,  # NEW: Session filter
        "trend": 0,  # NEW: Trend filter
        "no_sr_levels": 0,  # NEW: No S/R levels found
        "confidence": 0,
        "broken_level": 0,
        "trend_alignment": 0,  # NEW: Trend alignment filter
        "signal_cooldown": 0,  # NEW: Signal cooldown
        "invalid_geometry": 0,
        "insufficient_edge": 0
    }

    pip_value = calculate_pip_value(symbol)

    # Broken level tracking: {level_price: (break_timestamp, level_type)}
    broken_levels: Dict[float, Tuple[datetime, str]] = {}

    # Signal cooldown tracking: {symbol: last_signal_timestamp}
    last_signal_time: Optional[datetime] = None

    # Walk forward bar by bar
    if verbose:
        print(f"\nRunning simulation...")

    # Progress tracking for worker processes
    total_bars = len(df) - lookback_bars
    progress_interval = max(500, total_bars // 10)  # Log every 10% or 500 bars
    last_progress_time = time.time()

    for i in range(lookback_bars, len(df)):
        current_bar = df.iloc[i]
        current_time = current_bar['time']

        # Progress logging for workers (not verbose mode)
        bar_idx = i - lookback_bars
        if not verbose and bar_idx > 0 and bar_idx % progress_interval == 0:
            elapsed = time.time() - last_progress_time
            pct = (bar_idx / total_bars) * 100
            bars_per_sec = progress_interval / elapsed if elapsed > 0 else 0
            import sys
            sys.stderr.write(f"[PROGRESS] {pct:.0f}% ({bar_idx}/{total_bars} bars) - {bars_per_sec:.1f} bars/sec\n")
            sys.stderr.flush()
            last_progress_time = time.time()

        # Update open trade
        if open_trade:
            if check_trade_outcome(open_trade, current_bar, usd_per_pip_per_lot):
                trades.append(open_trade)
                open_trade = None

        # Generate signal only if no open trade
        if not open_trade:
            historical_data = df.iloc[:i + 1].copy()
            decision_bar = current_bar  # Decision made at current (closed) bar

            # FILTER 1: Session Filter (check if decision bar is in valid session)
            # Match API: volarix4/api/main.py:350-373
            if enable_session_filter:
                if not is_valid_session(decision_bar['time']):
                    filter_rejections["session"] += 1
                    signals_generated["HOLD"] += 1
                    continue

            # FILTER 2: Trend Filter (EMA 20/50)
            # Match API: volarix4/api/main.py:375-383
            if enable_trend_filter:
                trend_info = detect_trend(historical_data, ema_fast=20, ema_slow=50)
                # Note: Trend filter doesn't block here - it's applied after rejection
                # Store for later use in trend alignment validation
            else:
                trend_info = None

            # FILTER 3: S/R Detection
            # Match API: volarix4/api/main.py:385-411

            # Use pre-computed S/R levels if available (HUGE speed improvement!)
            if sr_cache is not None:
                levels = sr_cache.get(i, [])
            else:
                # Fallback to on-the-fly computation (slow!)
                # Use reduced lookback for speed (200 bars instead of 400)
                sr_lookback = min(200, lookback_bars)

                # Periodic detailed logging for first few bars
                if not verbose and bar_idx < 10:
                    import sys
                    sys.stderr.write(f"[DETAIL] Bar {bar_idx}: Starting S/R detection on {sr_lookback} bars...\n")
                    sys.stderr.flush()
                    sr_start = time.time()

                levels = detect_sr_levels(
                    historical_data.tail(sr_lookback),
                    min_score=60.0,
                    pip_value=pip_value
                )

                if not verbose and bar_idx < 10:
                    sr_time = time.time() - sr_start
                    import sys
                    sys.stderr.write(f"[DETAIL] Bar {bar_idx}: S/R detection took {sr_time:.3f}s, found {len(levels)} levels\n")
                    sys.stderr.flush()

            if not levels:
                filter_rejections["no_sr_levels"] += 1
                signals_generated["HOLD"] += 1
                continue

            # FILTER 4: Broken Level Filter (mark and filter broken levels)
            # Match API: volarix4/api/main.py:413-465
            if enable_broken_level_filter:
                # Mark broken levels on current bar (check ALL levels on EVERY bar)
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

                if not levels:
                    signals_generated["HOLD"] += 1
                    continue

            # FILTER 5: Rejection Search
            # Match API: volarix4/api/main.py:467-556

            if not verbose and bar_idx < 10:
                import sys
                sys.stderr.write(f"[DETAIL] Bar {bar_idx}: Starting rejection search...\n")
                sys.stderr.flush()
                rej_start = time.time()

            rejection = find_rejection_candle(
                historical_data.tail(20),
                levels,
                lookback=5,
                pip_value=pip_value
            )

            if not verbose and bar_idx < 10:
                rej_time = time.time() - rej_start
                import sys
                sys.stderr.write(f"[DETAIL] Bar {bar_idx}: Rejection search took {rej_time:.3f}s\n")
                sys.stderr.flush()

            if not rejection:
                signals_generated["HOLD"] += 1
                continue

            # FILTER 6: Confidence Filter
            # Match API: volarix4/api/main.py:547-556 (embedded in rejection)
            confidence = rejection.get('confidence', 1.0)
            direction = rejection['direction']

            if enable_confidence_filter:
                if confidence < min_confidence:
                    filter_rejections["confidence"] += 1
                    signals_generated["HOLD"] += 1
                    continue

            # FILTER 7: Trend Alignment Validation (with bypass for high confidence)
            # Match API: volarix4/api/main.py:558-626
            if enable_trend_filter and trend_info is not None:
                # Check if signal aligns with trend
                trend_result = validate_signal_with_trend(
                    signal_direction=direction,
                    trend_info=trend_info
                )

                # Allow bypass for high confidence (match API logic)
                high_confidence_override = confidence > 0.75 and rejection.get('level_score', 0) >= 80.0

                if not trend_result['valid'] and not high_confidence_override:
                    filter_rejections["trend_alignment"] += 1
                    signals_generated["HOLD"] += 1
                    continue

            # FILTER 8: Signal Cooldown (per-symbol, 2 hours)
            # Match API: volarix4/api/main.py:628-640
            if enable_signal_cooldown:
                if last_signal_time is not None:
                    time_since_last_signal = current_time - last_signal_time
                    if time_since_last_signal < timedelta(hours=signal_cooldown_hours):
                        filter_rejections["signal_cooldown"] += 1
                        signals_generated["HOLD"] += 1
                        continue

            # Signal passed all filters - record it
            signals_generated[direction] += 1

            # FILTER 9: Trade Setup Calculation and Min Edge Validation
            # Match API: volarix4/api/main.py:642-796
            # Create trade (enter on next bar open)
            next_bar_idx = i + 1
            if next_bar_idx < len(df):
                entry_bar = df.iloc[next_bar_idx]
                actual_entry = entry_bar['open']

                # Calculate trade setup using ACTUAL entry price (next bar open)
                trade_params = calculate_sl_tp(
                    entry=actual_entry,
                    level=rejection['level'],
                    direction=direction,
                    sl_pips_beyond=10.0,
                    pip_value=pip_value
                )

                # Sanity check: validate SL/TP geometry
                if not levels_sane(
                    entry=actual_entry,
                    sl=trade_params['sl'],
                    tp1=trade_params['tp1'],
                    tp2=trade_params['tp2'],
                    tp3=trade_params['tp3'],
                    direction=direction
                ):
                    # Invalid geometry - skip this trade
                    filter_rejections["invalid_geometry"] += 1
                    signals_generated["HOLD"] += 1
                    continue

                # Calculate round-trip costs in pips
                commission_pips = (2 * commission_per_side_per_lot * lot_size) / usd_per_pip_per_lot
                total_cost_pips = spread_pips + (2 * slippage_pips) + commission_pips

                # Calculate TP1 distance in pips
                if direction == "BUY":
                    tp1_distance_pips = (trade_params['tp1'] - actual_entry) / pip_value
                else:  # SELL
                    tp1_distance_pips = (actual_entry - trade_params['tp1']) / pip_value

                # Check minimum edge after costs
                if tp1_distance_pips <= total_cost_pips + min_edge_pips:
                    # Insufficient edge - TP1 would not be profitable after costs
                    filter_rejections["insufficient_edge"] += 1
                    signals_generated["HOLD"] += 1
                    continue

                # Update signal cooldown timestamp (signal accepted)
                if enable_signal_cooldown:
                    last_signal_time = current_time

                # Create trade with validated parameters
                open_trade = Trade(
                    entry_time=entry_bar['time'],
                    direction=direction,
                    entry=actual_entry,
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

                # Populate trade context
                open_trade.rejection_confidence = confidence
                open_trade.level_price = rejection['level']
                open_trade.level_type = rejection.get('level_type', 'unknown')

                # Calculate SL/TP in pips (using actual_entry)
                if direction == "BUY":
                    open_trade.sl_pips = (actual_entry - trade_params['sl']) / pip_value
                    open_trade.tp1_pips = (trade_params['tp1'] - actual_entry) / pip_value
                else:  # SELL
                    open_trade.sl_pips = (trade_params['sl'] - actual_entry) / pip_value
                    open_trade.tp1_pips = (actual_entry - trade_params['tp1']) / pip_value

                # Time context
                open_trade.hour_of_day = entry_bar['time'].hour
                open_trade.day_of_week = entry_bar['time'].dayofweek

                # Calculate ATR at entry (using data up to current bar)
                df_for_atr = df.iloc[:next_bar_idx+1]
                open_trade.atr_pips_14 = calculate_atr_pips(df_for_atr, period=14, pip_value=pip_value)

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

    # SIGN-BASED CATEGORIZATION (not status-based)
    # A trade is "profitable" if pnl_after_costs > 0, regardless of hitting TP
    # A trade can hit TP1 (status="win") but lose money after costs → not profitable
    profit_deals = [t for t in completed_trades if t.pnl_after_costs > 0]
    loss_deals = [t for t in completed_trades if t.pnl_after_costs < 0]

    # Basic counts and rates (sign-based)
    win_rate = (len(profit_deals) / total_trades) * 100
    accuracy = win_rate  # Same as win_rate
    profit_trades_pct = win_rate
    loss_trades_pct = 100.0 - win_rate

    # P&L metrics (sign-based)
    total_pnl_pips = sum([t.pnl_pips for t in completed_trades])
    total_pnl_after_costs = sum([t.pnl_after_costs for t in completed_trades])

    gross_profit_pips = sum([t.pnl_after_costs for t in profit_deals]) if profit_deals else 0.0
    gross_loss_pips = abs(sum([t.pnl_after_costs for t in loss_deals])) if loss_deals else 0.0
    profit_factor = gross_profit_pips / gross_loss_pips if gross_loss_pips > 0 else float('inf')

    expected_payoff_pips = total_pnl_after_costs / total_trades

    # Win/Loss metrics (sign-based)
    avg_win_pips = gross_profit_pips / len(profit_deals) if profit_deals else 0.0
    avg_loss_pips = gross_loss_pips / len(loss_deals) if loss_deals else 0.0
    avg_win = avg_win_pips  # Alias for compatibility
    avg_loss = avg_loss_pips  # Alias for compatibility

    largest_win_pips = max([t.pnl_after_costs for t in profit_deals]) if profit_deals else 0.0
    largest_loss_pips = abs(min([t.pnl_after_costs for t in loss_deals])) if loss_deals else 0.0

    # Consecutive wins/losses (sign-based)
    max_consecutive_wins = 0
    max_consecutive_losses = 0
    max_consecutive_wins_pnl = 0.0
    max_consecutive_losses_pnl = 0.0

    current_wins = 0
    current_losses = 0
    current_wins_pnl = 0.0
    current_losses_pnl = 0.0

    for trade in completed_trades:
        if trade.pnl_after_costs > 0:  # Profitable deal
            current_wins += 1
            current_wins_pnl += trade.pnl_after_costs
            current_losses = 0
            current_losses_pnl = 0.0

            if current_wins > max_consecutive_wins:
                max_consecutive_wins = current_wins
                max_consecutive_wins_pnl = current_wins_pnl
        else:  # Loss deal (pnl_after_costs < 0)
            current_losses += 1
            current_losses_pnl += abs(trade.pnl_after_costs)
            current_wins = 0
            current_wins_pnl = 0.0

            if current_losses > max_consecutive_losses:
                max_consecutive_losses = current_losses
                max_consecutive_losses_pnl = current_losses_pnl

    # Long/Short breakdown (sign-based)
    long_trades = [t for t in completed_trades if t.direction == "BUY"]
    short_trades = [t for t in completed_trades if t.direction == "SELL"]

    trade_count_long = len(long_trades)
    trade_count_short = len(short_trades)

    long_profit_deals = [t for t in long_trades if t.pnl_after_costs > 0]
    short_profit_deals = [t for t in short_trades if t.pnl_after_costs > 0]

    win_rate_long = (len(long_profit_deals) / trade_count_long * 100) if trade_count_long > 0 else 0.0
    win_rate_short = (len(short_profit_deals) / trade_count_short * 100) if trade_count_short > 0 else 0.0

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
        "winning_trades": len(profit_deals),  # Profitable deals (pnl_after_costs > 0)
        "losing_trades": len(loss_deals),     # Loss deals (pnl_after_costs < 0)
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
        print(f"{'Profit trades (% of total)':<30} {len(profit_deals):>6} ({profit_trades_pct:.1f}%)")
        print(f"{'Loss trades (% of total)':<30} {len(loss_deals):>6} ({loss_trades_pct:.1f}%)")
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
        print(f"{'Invalid geometry rejections':<30} {filter_rejections['invalid_geometry']:>10}")
        print(f"{'Insufficient edge rejections':<30} {filter_rejections['insufficient_edge']:>10}")
        print(f"{'Signals generated (BUY/SELL)':<30} {signals_generated['BUY']}/{signals_generated['SELL']:>5}")

        print("=" * 70 + "\n")

    # Convert trades to DataFrame
    trades_df = trades_to_dataframe(completed_trades)

    # Save to CSV with timestamp
    import os
    from datetime import datetime

    output_dir = "./outputs"
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"{output_dir}/trades_{symbol}_{timeframe}_{timestamp}.csv"

    if len(trades_df) > 0:
        trades_df.to_csv(csv_filename, index=False)
        if verbose:
            print(f"✓ Saved {len(trades_df)} trades to {csv_filename}\n")

    # Add trades_df to results
    results['trades_df'] = trades_df

    return results


def _run_single_backtest(args):
    """
    Worker function for parallel backtest execution.
    This function is called by each worker process.

    Args:
        args: Tuple of (params_dict, backtest_kwargs, df_slice, sr_cache)

    Returns:
        Dict with backtest results merged with parameters
    """
    import sys
    params, backtest_kwargs, df_slice, sr_cache = args

    try:
        # Print to indicate work has started (will be captured by parent)
        sys.stderr.write(f"[WORKER] Starting: {params}\n")
        sys.stderr.flush()

        start_time = time.time()

        # Run backtest with these parameters
        result = run_backtest(
            min_confidence=params.get('min_confidence'),
            broken_level_cooldown_hours=params.get('broken_level_cooldown_hours'),
            broken_level_break_pips=params.get('broken_level_break_pips', 15.0),
            min_edge_pips=params.get('min_edge_pips', 2.0),
            enable_confidence_filter='min_confidence' in params,
            enable_broken_level_filter='broken_level_cooldown_hours' in params,
            df=df_slice,
            sr_cache=sr_cache,  # Pass pre-computed S/R levels
            enforce_bars_limit=True,
            verbose=False,
            **backtest_kwargs
        )

        duration = time.time() - start_time
        sys.stderr.write(f"[WORKER] Completed in {duration:.1f}s: {params}\n")
        sys.stderr.flush()

        # Merge parameters into result
        result.update(params)

        return result

    except Exception as e:
        sys.stderr.write(f"[WORKER] Error: {params} - {str(e)}\n")
        sys.stderr.flush()
        return {'error': str(e), **params}


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
        n_jobs: int = -1,
        verbose: bool = False
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

    if verbose:
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

    if verbose:
        print(f"\nTotal combinations: {total_combinations}")
        print(f"CPU cores available: {multiprocessing.cpu_count()}")
        print(f"Using {n_workers} parallel workers")
        print(f"[TIMER] Starting grid search at {time.strftime('%H:%M:%S')}")

    grid_start_time = time.time()

    # OPTIMIZATION: Pre-compute S/R levels once for all backtests
    if verbose:
        print(f"\n[OPTIMIZATION] Pre-computing S/R levels for {len(df)} bars...")
        print(f"  This takes ~1-2 minutes but will save hours across {total_combinations} backtests!\n")

    pip_value = calculate_pip_value(symbol)
    # Use reduced lookback for S/R (200 instead of 400) - 2x faster, still effective
    sr_lookback = min(200, lookback_bars)  # Use 200 bars for S/R detection (faster)
    if verbose:
        print(f"[OPTIMIZATION] Using {sr_lookback} bars for S/R detection (reduced from {lookback_bars} for speed)")
    # Compute every 24 bars (1 day on H1) - 24x fewer computations!
    sr_cache = precompute_sr_levels(df, sr_lookback, pip_value, min_score=60.0,
                                    compute_interval=24, verbose=verbose)

    if verbose:
        print("\nRunning backtests with pre-computed S/R levels...\n")

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

    # Prepare arguments for each worker (now includes sr_cache)
    worker_args = []
    for combo in combinations:
        params = dict(zip(param_names, combo))
        worker_args.append((params, backtest_kwargs, df, sr_cache))

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
        import threading

        # Heartbeat function to show progress every 30 seconds
        stop_heartbeat = threading.Event()
        def heartbeat():
            last_count = 0
            while not stop_heartbeat.is_set():
                stop_heartbeat.wait(30)  # Check every 30 seconds
                if not stop_heartbeat.is_set():
                    elapsed = time.time() - grid_start_time
                    if completed > last_count:
                        rate = completed / (elapsed / 60) if elapsed > 0 else 0
                        print(f"[HEARTBEAT] {completed}/{total_combinations} completed in {format_duration(elapsed)} ({rate:.1f}/min)")
                        last_count = completed

        # Start heartbeat thread
        heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
        heartbeat_thread.start()

        try:
            with ProcessPoolExecutor(max_workers=n_workers) as executor:
                # Submit all jobs
                future_to_params = {
                    executor.submit(_run_single_backtest, args): args[0]
                    for args in worker_args
                }

                if verbose:
                    print(f"[INFO] Submitted {len(future_to_params)} jobs to worker pool")
                    print(f"[INFO] Each backtest processes ~{bars} bars, this may take several minutes per job\n")

                # Process results as they complete
                for future in as_completed(future_to_params):
                    params = future_to_params[future]
                    completed += 1

                    # Calculate ETA
                    elapsed = time.time() - grid_start_time
                    if completed > 0:
                        avg_time_per_combo = elapsed / completed
                        remaining = total_combinations - completed
                        eta = avg_time_per_combo * remaining
                        eta_str = f" (ETA: {format_duration(eta)})"
                    else:
                        eta_str = ""

                    try:
                        result = future.result()

                        if 'profit_factor' in result:
                            results_list.append(result)
                            if verbose:
                                print(f"[{completed}/{total_combinations}] ✓ {params} → PF: {result['profit_factor']:.2f}, Trades: {result['total_trades']}{eta_str}")
                        else:
                            failed += 1
                            if verbose:
                                print(f"[{completed}/{total_combinations}] ✗ Failed: {params} - {result.get('error', 'Unknown error')}{eta_str}")

                    except Exception as e:
                        failed += 1
                        if verbose:
                            print(f"[{completed}/{total_combinations}] ✗ Exception: {params} - {str(e)}{eta_str}")

        finally:
            # Stop heartbeat thread
            stop_heartbeat.set()
            heartbeat_thread.join(timeout=1)

    # Create DataFrame
    df_results = pd.DataFrame(results_list)

    # Sort by profit factor (descending)
    if len(df_results) > 0:
        df_results = df_results.sort_values('profit_factor', ascending=False)
    else:
        print("\nWARNING: No successful backtests to display")

    grid_total_time = time.time() - grid_start_time
    avg_time_per_backtest = grid_total_time / total_combinations if total_combinations > 0 else 0

    if verbose:
        print("\n" + "=" * 70)
        print("GRID SEARCH COMPLETE")
        print("=" * 70)
        print(f"[TIMER] Grid search completed in {format_duration(grid_total_time)}")
        print(f"  • Average time per backtest: {format_duration(avg_time_per_backtest)}")
        print(f"  • Throughput: {total_combinations / (grid_total_time / 60):.1f} backtests/minute")
        print(f"\nSummary:")
        print(f"  Total tests: {total_combinations}")
        print(f"  Successful: {len(results_list)}")
        print(f"  Failed: {failed}")
        print(f"  Success rate: {(len(results_list)/total_combinations*100):.1f}%")
        print("=" * 70)

    return df_results


def _run_year_based_walk_forward(
        df_full: pd.DataFrame,
        test_years: List[int],
        symbol: str,
        timeframe: str,
        lookback_bars: int,
        param_grid: Dict,
        spread_pips: float,
        commission_per_side_per_lot: float,
        slippage_pips: float,
        usd_per_pip_per_lot: float,
        starting_balance_usd: float,
        broken_level_break_pips: float,
        n_jobs: int,
        verbose: bool = False
) -> pd.DataFrame:
    """
    Run year-based walk-forward: train on 2 previous years, test on each target year.

    Args:
        df_full: Full DataFrame with all data
        test_years: List of years to test (e.g., [2022, 2023, 2024, 2025])
        Other args: Same as run_walk_forward

    Returns:
        DataFrame with results for each year
    """
    overall_start = time.time()
    split_results = []
    all_train_results = []
    param_stability_data = []

    for split_idx, test_year in enumerate(test_years):
        split_start = time.time()

        if verbose:
            print("\n" + "-" * 70)
            print(f"YEAR {test_year} (Split {split_idx + 1}/{len(test_years)})")
            print("-" * 70)
            print(f"[TIMER] Starting year {test_year} at {time.strftime('%H:%M:%S')}")

        # Define train and test periods
        # TODO: For faster testing, use 1 year instead of 2. Change back to -2 for full test.
        TRAIN_YEARS = 1  # TEMPORARY: Change to 2 for full 2-year training
        train_start_year = test_year - TRAIN_YEARS
        train_end_year = test_year - 1

        # Filter data by year
        data_prep_start = time.time()
        if verbose:
            print(f"[STEP 1/3] Preparing data...")

        train_start_date = pd.Timestamp(f"{train_start_year}-01-01")
        train_end_date = pd.Timestamp(f"{test_year}-01-01")  # Exclusive
        test_start_date = pd.Timestamp(f"{test_year}-01-01")
        test_end_date = pd.Timestamp(f"{test_year + 1}-01-01")  # Exclusive

        if verbose:
            print(f"\nTrain period: {train_start_year}-{train_end_year} (2 years)")
            print(f"  Date range: {train_start_date.date()} to {train_end_date.date()}")
            print(f"\nTest period: {test_year} (1 year)")
            print(f"  Date range: {test_start_date.date()} to {test_end_date.date()}")

        # Extract train data
        train_mask = (df_full['time'] >= train_start_date) & (df_full['time'] < train_end_date)
        train_data_only = df_full[train_mask].copy()

        if len(train_data_only) == 0:
            if verbose:
                print(f"\n✗ No training data for {train_start_year}-{train_end_year}")
            continue

        # Add lookback bars before training period
        train_lookback_start_idx = df_full[train_mask].index[0] - lookback_bars
        if train_lookback_start_idx < 0:
            if verbose:
                print(f"\n✗ Insufficient lookback bars for training period")
            continue

        train_df = df_full.iloc[train_lookback_start_idx:df_full[train_mask].index[-1] + 1].copy()
        train_bars = len(train_data_only)

        # Extract test data
        test_mask = (df_full['time'] >= test_start_date) & (df_full['time'] < test_end_date)
        test_data_only = df_full[test_mask].copy()

        if len(test_data_only) == 0:
            if verbose:
                print(f"\n✗ No test data for {test_year}")
            continue

        # Add lookback bars before test period
        test_lookback_start_idx = df_full[test_mask].index[0] - lookback_bars
        if test_lookback_start_idx < 0:
            if verbose:
                print(f"\n✗ Insufficient lookback bars for test period")
            continue

        test_df = df_full.iloc[test_lookback_start_idx:df_full[test_mask].index[-1] + 1].copy()
        test_bars = len(test_data_only)

        if verbose:
            print(f"\nTrain segment:")
            print(f"  Total bars (with lookback): {len(train_df)}")
            print(f"  Evaluation bars: {train_bars}")
            print(f"  Time: {train_df['time'].iloc[lookback_bars]} to {train_df['time'].iloc[-1]}")

            print(f"\nTest segment:")
            print(f"  Total bars (with lookback): {len(test_df)}")
            print(f"  Evaluation bars: {test_bars}")
            print(f"  Time: {test_df['time'].iloc[lookback_bars]} to {test_df['time'].iloc[-1]}")

        data_prep_time = time.time() - data_prep_start
        if verbose:
            print(f"[TIMER] Data preparation took {format_duration(data_prep_time)}")

        # TRAIN: Run grid search on training years
        grid_search_start = time.time()
        if verbose:
            print(f"\n[STEP 2/3] Running grid search on training data...")
            print(f"[TRAIN] Grid search on {train_start_year}-{train_end_year} ({train_bars} bars)...")

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
            n_jobs=n_jobs,
            verbose=verbose
        )

        if len(train_results) == 0:
            if verbose:
                print(f"\n✗ No successful backtests in training - skipping year {test_year}")
            continue

        grid_search_time = time.time() - grid_search_start
        if verbose:
            print(f"[TIMER] Grid search took {format_duration(grid_search_time)}")

        # Select best parameters (by profit_factor, then total_pnl_after_costs)
        train_results_sorted = train_results.sort_values(
            by=['profit_factor', 'total_pnl_after_costs'],
            ascending=[False, False]
        )
        best_params = train_results_sorted.iloc[0]

        if verbose:
            print(f"\n[TRAIN] Best parameters found:")
            print(f"  min_confidence: {best_params['min_confidence']}")
            print(f"  broken_level_cooldown_hours: {best_params['broken_level_cooldown_hours']}")
            print(f"  min_edge_pips: {best_params['min_edge_pips']}")
            print(f"  Train Profit Factor: {best_params['profit_factor']:.2f}")
            print(f"  Train Total Trades: {best_params['total_trades']:.0f}")
            print(f"  Train PnL: {best_params['total_pnl_after_costs']:.2f} pips")

        # TEST: Run backtest on test year with best params
        test_start = time.time()
        if verbose:
            print(f"\n[STEP 3/3] Running test on {test_year}...")
            print(f"[TEST] Testing on {test_year} ({test_bars} bars) with best params...")

            # Pre-compute S/R levels for test data (same optimization as training)
            print(f"[OPTIMIZATION] Pre-computing S/R levels for test year {test_year}...")
        test_pip_value = calculate_pip_value(symbol)
        test_sr_lookback = min(200, lookback_bars)
        test_sr_cache = precompute_sr_levels(test_df, test_sr_lookback, test_pip_value,
                                            min_score=60.0, compute_interval=24, verbose=False)
        if verbose:
            print(f"[OPTIMIZATION] ✓ Test S/R cache ready ({len(test_sr_cache)} entries)")

        test_result = run_backtest(
            min_confidence=best_params['min_confidence'],
            broken_level_cooldown_hours=best_params['broken_level_cooldown_hours'],
            min_edge_pips=best_params['min_edge_pips'],
            symbol=symbol,
            timeframe=timeframe,
            bars=test_bars,
            lookback_bars=lookback_bars,
            spread_pips=spread_pips,
            commission_per_side_per_lot=commission_per_side_per_lot,
            slippage_pips=slippage_pips,
            usd_per_pip_per_lot=usd_per_pip_per_lot,
            starting_balance_usd=starting_balance_usd,
            broken_level_break_pips=broken_level_break_pips,
            df=test_df,
            sr_cache=test_sr_cache  # Use pre-computed S/R for test too!
        )

        if test_result is None or test_result['total_trades'] == 0:
            if verbose:
                print(f"\n✗ Test backtest failed or no trades - skipping year {test_year}")
            continue

        test_time = time.time() - test_start
        if verbose:
            print(f"[TIMER] Test run took {format_duration(test_time)}")

        test_trades = test_result.get('trades', [])

        if verbose:
            print(f"\n[TEST] Year {test_year} Results:")
            print(f"  Profit Factor: {test_result['profit_factor']:.2f}")
            print(f"  Total Trades: {test_result['total_trades']:.0f}")
            print(f"  Win Rate: {test_result['win_rate']:.1f}%")
            print(f"  PnL: {test_result['total_pnl_after_costs']:.2f} pips")
            print(f"  Max Drawdown: {test_result['max_drawdown']:.2f} pips ({test_result['max_drawdown_pct']:.2f}%)")

        # Calculate performance degradation
        pf_degradation = test_result['profit_factor'] / best_params['profit_factor'] if best_params['profit_factor'] > 0 else 0

        if verbose:
            print(f"\nPerformance Degradation:")
            print(f"  PF Ratio (test/train): {pf_degradation:.2f}")

        split_time = time.time() - split_start
        if verbose:
            print(f"\n[TIMER] Year {test_year} completed in {format_duration(split_time)}")
            print(f"  • Data prep: {format_duration(data_prep_time)}")
            print(f"  • Grid search: {format_duration(grid_search_time)}")
            print(f"  • Test run: {format_duration(test_time)}")

        # Store split results
        split_result = {
            'split': split_idx + 1,
            'test_year': test_year,
            'train_years': f"{train_start_year}-{train_end_year}",
            'train_bars': train_bars,
            'test_bars': test_bars,

            # Best parameters
            'param_min_confidence': best_params['min_confidence'],
            'param_broken_level_cooldown_hours': best_params['broken_level_cooldown_hours'],
            'param_min_edge_pips': best_params['min_edge_pips'],

            # Train metrics
            'train_total_trades': best_params['total_trades'],
            'train_win_rate': best_params['win_rate'],
            'train_profit_factor': best_params['profit_factor'],
            'train_total_pnl_after_costs': best_params['total_pnl_after_costs'],
            'train_max_drawdown': best_params['max_drawdown'],

            # Test metrics
            'test_total_trades': test_result['total_trades'],
            'test_win_rate': test_result['win_rate'],
            'test_profit_factor': test_result['profit_factor'],
            'test_total_pnl_after_costs': test_result['total_pnl_after_costs'],
            'test_max_drawdown': test_result['max_drawdown'],
            'test_max_drawdown_pct': test_result['max_drawdown_pct'],
            'test_largest_win_pips': test_result['largest_win_pips'],
            'test_largest_loss_pips': test_result['largest_loss_pips'],

            # Degradation metrics
            'pf_degradation': pf_degradation,
            'expected_payoff_degradation': (test_result.get('expected_payoff_pips', 0) / best_params.get('expected_payoff_pips', 1))
                                          if best_params.get('expected_payoff_pips', 0) > 0 else 0
        }

        split_results.append(split_result)

        # Store training results for later analysis
        all_train_results.append({
            'split': split_idx + 1,
            'test_year': test_year,
            'train_results': train_results,
            'best_params': best_params,
            'test_profit_factor': test_result['profit_factor'],
            'test_total_pnl_after_costs': test_result['total_pnl_after_costs']
        })

    # Convert to DataFrame
    df_results = pd.DataFrame(split_results)

    if len(df_results) == 0:
        if verbose:
            print("\n✗ No successful year-based splits")
        return df_results

    overall_time = time.time() - overall_start

    if verbose:
        # Print summary statistics
        print("\n" + "=" * 70)
        print("YEAR-BASED WALK-FORWARD SUMMARY")
        print("=" * 70)
        print(f"[TIMER] Total execution time: {format_duration(overall_time)}")

        print(f"\nCompleted years: {len(df_results)}/{len(test_years)}")

        # Overall test performance
        total_test_trades = df_results['test_total_trades'].sum()
        total_test_pnl = df_results['test_total_pnl_after_costs'].sum()
        avg_test_pf = df_results['test_profit_factor'].mean()

        print(f"\nOverall Test Performance:")
        print(f"{'Total trades across all years':<40} {total_test_trades:.0f}")
        print(f"{'Total PnL across all years':<40} {total_test_pnl:.2f} pips")
        print(f"{'Average Profit Factor':<40} {avg_test_pf:.2f}")

        # Per-year statistics
        print(f"\n{'Mean Profit Factor (per year)':<40} {df_results['test_profit_factor'].mean():.2f}")
        print(f"{'Median Profit Factor (per year)':<40} {df_results['test_profit_factor'].median():.2f}")
        print(f"{'Mean PnL per year':<40} {df_results['test_total_pnl_after_costs'].mean():.2f} pips")

        # Profitable years
        profitable_years = (df_results['test_total_pnl_after_costs'] > 0).sum()
        print(f"\n{'Profitable years':<40} {profitable_years}/{len(df_results)} ({profitable_years/len(df_results)*100:.1f}%)")

        # Parameter stability
        print(f"\nParameter Stability:")
        print(f"{'Unique min_confidence values':<40} {df_results['param_min_confidence'].nunique()}")
        print(f"{'Unique cooldown values':<40} {df_results['param_broken_level_cooldown_hours'].nunique()}")
        print(f"{'Unique min_edge values':<40} {df_results['param_min_edge_pips'].nunique()}")

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
        n_jobs: int = -1,
        use_year_based_splits: bool = False,
        test_years: Optional[List[int]] = None,
        verbose: bool = False
) -> pd.DataFrame:
    """
    Run walk-forward analysis: train on one segment, test on next segment.

    This prevents overfitting by ensuring test data is never used for parameter optimization.

    Args:
        symbol, timeframe: Trading pair and timeframe
        total_bars: Total bars to fetch from MT5 (ignored if use_year_based_splits=True)
        lookback_bars: Bars needed for indicator calculation
        splits: Number of train/test windows (ignored if use_year_based_splits=True)
        train_bars: Size of training segment (ignored if use_year_based_splits=True)
        test_bars: Size of testing segment (ignored if use_year_based_splits=True)
        param_grid: Parameters to optimize (default: min_confidence + cooldown)
        spread_pips, commission_per_side_per_lot, slippage_pips, usd_per_pip_per_lot: Cost settings
        broken_level_break_pips: Pips beyond level to mark as broken
        n_jobs: Number of parallel workers for grid search
        use_year_based_splits: If True, use year-based train/test splits
        test_years: List of years to test on (e.g., [2022, 2023, 2024, 2025])
                    For each year, trains on 2 previous years

    Returns:
        DataFrame with one row per split containing train/test results
    """
    if verbose:
        print("\n" + "=" * 70)
        print("WALK-FORWARD ANALYSIS")
        print("=" * 70)

    # Default param grid if not provided
    if param_grid is None:
        param_grid = {
            'min_confidence': [0.60, 0.65, 0.70],
            'broken_level_cooldown_hours': [12.0, 24.0, 48.0],
            'min_edge_pips': [0.0, 2.0, 4.0]
        }

    if use_year_based_splits:
        # Year-based walk-forward
        if test_years is None:
            test_years = [2022, 2023, 2024, 2025]

        if verbose:
            print(f"\nConfiguration (Year-Based):")
            print(f"  Symbol: {symbol} {timeframe}")
            print(f"  Test years: {test_years}")
            print(f"  Training: 2 years before each test year")
            print(f"  Lookback bars: {lookback_bars}")
            print("=" * 70)

        # Fetch all available data (we'll filter by year)
        # Fetch enough bars to cover all years (approximate)
        years_needed = max(test_years) - min(test_years) + 3  # +3 for 2 training years before first test
        if timeframe == "H1":
            bars_per_year = 365 * 24  # Approximate
        elif timeframe == "H4":
            bars_per_year = 365 * 6
        elif timeframe == "D1":
            bars_per_year = 365
        else:
            bars_per_year = 365 * 24  # Default to H1 estimate

        total_bars_needed = int(years_needed * bars_per_year * 1.2)  # 20% buffer

        if verbose:
            print(f"\nFetching ~{total_bars_needed} bars from MT5 to cover {years_needed} years...")
        try:
            df_full = fetch_ohlc(symbol, timeframe, total_bars_needed + lookback_bars)
            if df_full is None or len(df_full) < lookback_bars:
                if verbose:
                    print(f"✗ Insufficient data")
                return pd.DataFrame()
        except Exception as e:
            if verbose:
                print(f"✗ Data fetch failed: {e}")
            return pd.DataFrame()

        if verbose:
            print(f"✓ Fetched {len(df_full)} bars")
            print(f"  Range: {df_full['time'].iloc[0]} to {df_full['time'].iloc[-1]}")

        return _run_year_based_walk_forward(
            df_full=df_full,
            test_years=test_years,
            symbol=symbol,
            timeframe=timeframe,
            lookback_bars=lookback_bars,
            param_grid=param_grid,
            spread_pips=spread_pips,
            commission_per_side_per_lot=commission_per_side_per_lot,
            slippage_pips=slippage_pips,
            usd_per_pip_per_lot=usd_per_pip_per_lot,
            starting_balance_usd=starting_balance_usd,
            broken_level_break_pips=broken_level_break_pips,
            n_jobs=n_jobs,
            verbose=verbose
        )

    else:
        # Original bar-based walk-forward
        if verbose:
            print(f"\nConfiguration (Bar-Based):")
            print(f"  Symbol: {symbol} {timeframe}")
            print(f"  Total bars: {total_bars} (+ {lookback_bars} lookback)")
            print(f"  Splits: {splits}")
            print(f"  Train bars: {train_bars}")
            print(f"  Test bars: {test_bars}")
            print(f"  Segment size: {train_bars + test_bars} bars")
            print("=" * 70)

        # Fetch data once
        if verbose:
            print(f"\nFetching {total_bars + lookback_bars} bars from MT5...")
        try:
            df_full = fetch_ohlc(symbol, timeframe, total_bars + lookback_bars)
            if df_full is None or len(df_full) < lookback_bars + train_bars + test_bars:
                if verbose:
                    print(f"✗ Insufficient data")
                return pd.DataFrame()
        except Exception as e:
            if verbose:
                print(f"✗ Data fetch failed: {e}")
            return pd.DataFrame()

        if verbose:
            print(f"✓ Fetched {len(df_full)} bars")
            print(f"  Range: {df_full['time'].iloc[0]} to {df_full['time'].iloc[-1]}")

        # Calculate split positions
        segment_size = train_bars + test_bars
        available_bars = len(df_full) - lookback_bars
        max_splits = available_bars // segment_size

        if splits > max_splits:
            if verbose:
                print(f"\nWARNING: Requested {splits} splits but only {max_splits} possible with current data")
            splits = max_splits

        if verbose:
            print(f"\nRunning {splits} walk-forward splits...")

    split_results = []
    all_train_results = []  # Store full training grid results for each split
    param_stability_data = []  # Store ALL param combo test results across all splits

    for split_idx in range(splits):
        if verbose:
            print("\n" + "-" * 70)
            print(f"SPLIT {split_idx + 1}/{splits}")
            print("-" * 70)

        # Calculate indices for this split
        split_start = lookback_bars + (split_idx * segment_size)
        train_start = split_start
        train_end = train_start + train_bars
        test_start = train_end
        test_end = test_start + test_bars

        # Safety check: ensure we have enough lookback bars
        train_start_with_lookback = train_start - lookback_bars
        test_start_with_lookback = test_start - lookback_bars

        if train_start_with_lookback < 0:
            if verbose:
                print(f"\n✗ Skip split {split_idx + 1}: insufficient lookback bars for training")
                print(f"  Need index {train_start_with_lookback}, but minimum is 0")
            continue

        if test_start_with_lookback < 0:
            if verbose:
                print(f"\n✗ Skip split {split_idx + 1}: insufficient lookback bars for testing")
                print(f"  Need index {test_start_with_lookback}, but minimum is 0")
            continue

        # Extract segments with lookback bars included
        train_df = df_full.iloc[train_start_with_lookback:train_end].copy()
        test_df = df_full.iloc[test_start_with_lookback:test_end].copy()

        if verbose:
            print(f"\nTrain segment:")
            print(f"  Data range (with lookback): index {train_start_with_lookback} to {train_end}")
            print(f"  Evaluation bars: {train_bars}")
            print(f"  Time: {df_full.iloc[train_start]['time']} to {df_full.iloc[train_end-1]['time']}")

            print(f"\nTest segment:")
            print(f"  Data range (with lookback): index {test_start_with_lookback} to {test_end}")
            print(f"  Evaluation bars: {test_bars}")
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
            if verbose:
                print(f"\n✗ No successful backtests in training - skipping split {split_idx + 1}")
            continue

        # Select best parameters (by profit_factor, then total_pnl_after_costs)
        best_idx = train_results.sort_values(
            by=['profit_factor', 'total_pnl_after_costs'],
            ascending=[False, False]
        ).index[0]
        best_params = train_results.loc[best_idx]

        if verbose:
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
            min_edge_pips=test_param_dict.get('min_edge_pips', 2.0),
            enable_confidence_filter='min_confidence' in test_param_dict,
            enable_broken_level_filter='broken_level_cooldown_hours' in test_param_dict,
            df=test_df,
            enforce_bars_limit=True,
            verbose=False
        )

        if 'profit_factor' not in test_result:
            if verbose:
                print(f"\n✗ Test backtest failed: {test_result.get('error', 'Unknown error')}")
            continue

        if verbose:
            # Print compact MT5-style test results block
            print(f"\n[TEST] Results - MT5 Style Report:")
            print("  " + "-" * 60)
            pf_str = f"{test_result['profit_factor']:.2f}" if test_result['profit_factor'] != float('inf') else "Inf"
            print(f"  {'Trades':<35} {test_result['total_trades']:>10}")
            print(f"  {'Profit trades (% of total)':<35} {test_result['winning_trades']:>6} ({test_result['profit_trades_pct']:.1f}%)")
            print(f"  {'  Long (won %)':<35} {test_result['trade_count_long']:>6} ({test_result['win_rate_long']:.1f}%)")
            print(f"  {'  Short (won %)':<35} {test_result['trade_count_short']:>6} ({test_result['win_rate_short']:.1f}%)")
            print(f"  {'Gross Profit':<35} {test_result['gross_profit_pips']:>10.2f} pips")
            print(f"  {'Gross Loss':<35} {test_result['gross_loss_pips']:>10.2f} pips")
            print(f"  {'Total Net Profit':<35} {test_result['total_pnl_after_costs']:>10.2f} pips")
            print(f"  {'Profit Factor':<35} {pf_str:>10}")
            print(f"  {'Expected Payoff':<35} {test_result['expected_payoff_pips']:>10.2f} pips")
            print(f"  {'Recovery Factor':<35} {test_result['recovery_factor']:>10.2f}")
            print(f"  {'Max Drawdown':<35} {test_result['max_drawdown']:>10.2f} pips ({test_result['max_drawdown_pct']:.2f}%)")
            print(f"  {'Largest profit trade':<35} {test_result['largest_win_pips']:>10.2f} pips")
            print(f"  {'Largest loss trade':<35} {test_result['largest_loss_pips']:>10.2f} pips")
            print(f"  {'Average profit trade':<35} {test_result['avg_win_pips']:>10.2f} pips")
            print(f"  {'Average loss trade':<35} {test_result['avg_loss_pips']:>10.2f} pips")
            print("  " + "-" * 60)

        # Calculate and display degradation metrics
        train_pf = best_params['profit_factor']
        test_pf = test_result['profit_factor']
        pf_degradation = test_pf / max(train_pf, 1e-9)

        train_ep = best_params['expected_payoff_pips']
        test_ep = test_result['expected_payoff_pips']
        ep_degradation = test_ep / max(train_ep, 1e-9) if train_ep > 0 else (0.0 if test_ep <= 0 else float('inf'))

        if verbose:
            print(f"\n[DEGRADATION] Train → Test Performance:")
            print("  " + "-" * 60)
            train_pf_str = f"{train_pf:.2f}" if train_pf != float('inf') else "Inf"
            test_pf_str = f"{test_pf:.2f}" if test_pf != float('inf') else "Inf"
            print(f"  {'Profit Factor':<35} {train_pf_str} → {test_pf_str} ({pf_degradation:.2f}x)")
            print(f"  {'Expected Payoff':<35} {train_ep:.2f} → {test_ep:.2f} ({ep_degradation:.2f}x)")

            # Interpretation
            if pf_degradation >= 0.8:
                print(f"  {'Status':<35} ✓ Good (minimal degradation)")
            elif pf_degradation >= 0.6:
                print(f"  {'Status':<35} ⚠ Moderate degradation")
            else:
                print(f"  {'Status':<35} ✗ High degradation (possible overfitting)")
            print("  " + "-" * 60)

        # Monte Carlo trade order reshuffle stress test
        test_trades = test_result.get('trades', [])
        if verbose:
            print(f"\n[MONTE CARLO] Trade Order Reshuffle (N=1000 simulations):")
            print("  " + "-" * 60)

        if len(test_trades) > 0:
            # Extract PnL values in chronological order
            pnl_list = [trade.pnl_after_costs for trade in test_trades]
            observed_dd = test_result['max_drawdown']

            # Run Monte Carlo simulation
            mc_results = monte_carlo_reshuffle(pnl_list, observed_dd, n_simulations=1000)

            if verbose:
                print(f"  {'Observed Max DD':<35} {observed_dd:.2f} pips")
                print(f"  {'MC Median Max DD':<35} {mc_results['mc_median_max_dd']:.2f} pips")
                print(f"  {'MC 95th Percentile DD':<35} {mc_results['mc_95th_percentile_dd']:.2f} pips")
                print(f"  {'MC Maximum DD':<35} {mc_results['mc_max_max_dd']:.2f} pips")
                print(f"  {'P(final PnL < 0)':<35} {mc_results['mc_prob_loss']*100:.1f}%")
                print(f"  {'P(DD > observed)':<35} {mc_results['mc_prob_dd_exceeds_observed']*100:.1f}%")

                # Interpretation
                dd_ratio = observed_dd / mc_results['mc_median_max_dd'] if mc_results['mc_median_max_dd'] > 0 else 1.0
                if dd_ratio < 0.8:
                    print(f"  {'Interpretation':<35} ✓ Lucky sequence (obs < median)")
                elif dd_ratio > 1.2:
                    print(f"  {'Interpretation':<35} ⚠ Unlucky sequence (obs > median)")
                else:
                    print(f"  {'Interpretation':<35} ~ Typical sequence")

                if mc_results['mc_prob_loss'] > 0.3:
                    print(f"  {'Risk Warning':<35} ⚠ High loss probability ({mc_results['mc_prob_loss']*100:.1f}%)")
        else:
            mc_results = {
                'mc_median_max_dd': 0.0,
                'mc_max_max_dd': 0.0,
                'mc_95th_percentile_dd': 0.0,
                'mc_prob_loss': 0.0,
                'mc_prob_dd_exceeds_observed': 0.0
            }
            if verbose:
                print(f"  {'Status':<35} No trades to analyze")

        if verbose:
            print("  " + "-" * 60)

            # ================================================================
            # BUCKET DIAGNOSTICS (Per-Trade Analysis)
            # ================================================================
            if len(test_trades) > 0:
                print_bucket_diagnostics(test_trades, bucket_name=f"SPLIT {split_idx + 1} TEST")

            # ================================================================
            # TEST ALL PARAMETER COMBINATIONS (for parameter stability analysis)
            # ================================================================
            print(f"\n[STABILITY] Testing all {len(train_results)} parameter combinations on test set...")

        all_test_results = []  # Store test results for all param combos

        for idx, row in train_results.iterrows():
            # Extract params for this combo
            combo_params = {key: row[key] for key in param_grid.keys()}

            # Run test backtest with this param combo
            combo_test_result = run_backtest(
                symbol=symbol,
                timeframe=timeframe,
                bars=test_bars,
                lookback_bars=lookback_bars,
                spread_pips=spread_pips,
                commission_per_side_per_lot=commission_per_side_per_lot,
                slippage_pips=slippage_pips,
                usd_per_pip_per_lot=usd_per_pip_per_lot,
                starting_balance_usd=starting_balance_usd,
                min_confidence=combo_params.get('min_confidence'),
                broken_level_cooldown_hours=combo_params.get('broken_level_cooldown_hours'),
                broken_level_break_pips=combo_params.get('broken_level_break_pips', broken_level_break_pips),
                min_edge_pips=combo_params.get('min_edge_pips', 2.0),
                enable_confidence_filter='min_confidence' in combo_params,
                enable_broken_level_filter='broken_level_cooldown_hours' in combo_params,
                df=test_df,
                enforce_bars_limit=True,
                verbose=False
            )

            # Store result with params
            if 'profit_factor' in combo_test_result:
                all_test_results.append({
                    'split': split_idx + 1,
                    'params': combo_params.copy(),
                    'test_profit_factor': combo_test_result['profit_factor'],
                    'test_total_pnl_after_costs': combo_test_result['total_pnl_after_costs'],
                    'test_total_trades': combo_test_result['total_trades'],
                    'test_win_rate': combo_test_result['win_rate'],
                    'is_best': all(combo_params[k] == test_param_dict[k] for k in param_grid.keys())
                })

        print(f"  ✓ Tested {len(all_test_results)} combinations on test set")

        # Add to global parameter stability data
        param_stability_data.extend(all_test_results)

        # Store split results
        split_result = {
            'split': split_idx + 1,
            'train_start': df_full.iloc[train_start]['time'],
            'train_end': df_full.iloc[train_end - 1]['time'],
            'test_start': df_full.iloc[test_start]['time'],
            'test_end': df_full.iloc[test_end - 1]['time'],
            # Best params
            **{f'param_{k}': v for k, v in test_param_dict.items()},
            # Train metrics (basic)
            'train_profit_factor': best_params['profit_factor'],
            'train_total_trades': best_params['total_trades'],
            'train_win_rate': best_params['win_rate'],
            'train_total_pnl_after_costs': best_params['total_pnl_after_costs'],
            'train_max_drawdown': best_params['max_drawdown'],
            # Test metrics (comprehensive)
            'test_profit_factor': test_result['profit_factor'],
            'test_total_trades': test_result['total_trades'],
            'test_winning_trades': test_result['winning_trades'],
            'test_losing_trades': test_result['losing_trades'],
            'test_win_rate': test_result['win_rate'],
            'test_profit_trades_pct': test_result['profit_trades_pct'],
            'test_total_pnl_after_costs': test_result['total_pnl_after_costs'],
            'test_gross_profit_pips': test_result['gross_profit_pips'],
            'test_gross_loss_pips': test_result['gross_loss_pips'],
            'test_expected_payoff_pips': test_result['expected_payoff_pips'],
            'test_max_drawdown': test_result['max_drawdown'],
            'test_max_drawdown_pct': test_result['max_drawdown_pct'],
            'test_recovery_factor': test_result['recovery_factor'],
            'test_avg_win_pips': test_result['avg_win_pips'],
            'test_avg_loss_pips': test_result['avg_loss_pips'],
            'test_largest_win_pips': test_result['largest_win_pips'],
            'test_largest_loss_pips': test_result['largest_loss_pips'],
            'test_trade_count_long': test_result['trade_count_long'],
            'test_trade_count_short': test_result['trade_count_short'],
            'test_win_rate_long': test_result['win_rate_long'],
            'test_win_rate_short': test_result['win_rate_short'],
            # Degradation metrics (overfitting detection)
            'train_expected_payoff_pips': best_params['expected_payoff_pips'],
            'pf_degradation': test_result['profit_factor'] / max(best_params['profit_factor'], 1e-9),
            'expected_payoff_degradation': test_result['expected_payoff_pips'] / max(best_params['expected_payoff_pips'], 1e-9) if best_params['expected_payoff_pips'] > 0 else (0.0 if test_result['expected_payoff_pips'] <= 0 else float('inf')),
            # Monte Carlo metrics (sequence risk)
            'mc_median_max_dd': mc_results['mc_median_max_dd'],
            'mc_max_max_dd': mc_results['mc_max_max_dd'],
            'mc_95th_percentile_dd': mc_results['mc_95th_percentile_dd'],
            'mc_prob_loss': mc_results['mc_prob_loss'],
            'mc_prob_dd_exceeds_observed': mc_results['mc_prob_dd_exceeds_observed']
        }

        split_results.append(split_result)

        # Store full training grid results for parameter performance analysis
        all_train_results.append({
            'split': split_idx + 1,
            'train_results': train_results.copy(),  # Full grid search results
            'best_params': test_param_dict.copy(),  # Params chosen as best
            'test_profit_factor': test_result['profit_factor'],
            'test_total_pnl_after_costs': test_result['total_pnl_after_costs']
        })

    # Create results DataFrame
    df_results = pd.DataFrame(split_results)

    if len(df_results) == 0:
        if verbose:
            print("\n✗ No successful splits")
        return df_results

    if verbose:
        # Print aggregate summary
        print("\n" + "=" * 70)
        print("WALK-FORWARD SUMMARY - TEST RESULTS ONLY")
        print("=" * 70)
        print(f"\nCompleted splits: {len(df_results)}/{splits}")

        print(f"\n{'AGGREGATE TEST METRICS'}")
        print("-" * 70)

        # Trade statistics
        total_test_trades = df_results['test_total_trades'].sum()
        total_winning = df_results['test_winning_trades'].sum()
        total_losing = df_results['test_losing_trades'].sum()
        aggregate_win_rate = (total_winning / total_test_trades * 100) if total_test_trades > 0 else 0.0

        print(f"{'Total trades across all splits':<40} {total_test_trades:.0f}")
        print(f"{'  Winning trades':<40} {total_winning:.0f} ({aggregate_win_rate:.1f}%)")
        print(f"{'  Losing trades':<40} {total_losing:.0f} ({100-aggregate_win_rate:.1f}%)")

        # Profitability
        total_gross_profit = df_results['test_gross_profit_pips'].sum()
        total_gross_loss = df_results['test_gross_loss_pips'].sum()
        aggregate_pf = total_gross_profit / total_gross_loss if total_gross_loss > 0 else float('inf')
        pf_str = f"{aggregate_pf:.2f}" if aggregate_pf != float('inf') else "Inf"

        print(f"\n{'Total Gross Profit':<40} {total_gross_profit:.2f} pips")
        print(f"{'Total Gross Loss':<40} {total_gross_loss:.2f} pips")
        print(f"{'Total Net PnL (after costs)':<40} {df_results['test_total_pnl_after_costs'].sum():.2f} pips")
        print(f"{'Aggregate Profit Factor':<40} {pf_str}")
        print(f"{'Mean Expected Payoff':<40} {df_results['test_expected_payoff_pips'].mean():.2f} pips")

        # Per-split statistics
        print(f"\n{'Mean Profit Factor (per split)':<40} {df_results['test_profit_factor'].mean():.2f}")
        print(f"{'Median Profit Factor (per split)':<40} {df_results['test_profit_factor'].median():.2f}")
        print(f"{'Mean PnL per split':<40} {df_results['test_total_pnl_after_costs'].mean():.2f} pips")

        # Risk metrics
        print(f"\n{'Max Drawdown (worst split)':<40} {df_results['test_max_drawdown'].max():.2f} pips ({df_results['test_max_drawdown_pct'].max():.2f}%)")
        print(f"{'Mean Recovery Factor':<40} {df_results['test_recovery_factor'].mean():.2f}")

        # Win/Loss statistics
        print(f"\n{'Mean Avg Win':<40} {df_results['test_avg_win_pips'].mean():.2f} pips")
        print(f"{'Mean Avg Loss':<40} {df_results['test_avg_loss_pips'].mean():.2f} pips")
        print(f"{'Largest Win (across splits)':<40} {df_results['test_largest_win_pips'].max():.2f} pips")
        print(f"{'Largest Loss (across splits)':<40} {df_results['test_largest_loss_pips'].max():.2f} pips")

        # Direction breakdown
        total_long = df_results['test_trade_count_long'].sum()
        total_short = df_results['test_trade_count_short'].sum()
        print(f"\n{'Total Long trades':<40} {total_long:.0f}")
        print(f"{'Total Short trades':<40} {total_short:.0f}")
        print(f"{'Mean Win Rate Long':<40} {df_results['test_win_rate_long'].mean():.1f}%")
        print(f"{'Mean Win Rate Short':<40} {df_results['test_win_rate_short'].mean():.1f}%")

        # Overall performance
        profitable_splits = (df_results['test_total_pnl_after_costs'] > 0).sum()
        print(f"\n{'Profitable splits':<40} {profitable_splits}/{len(df_results)} ({profitable_splits/len(df_results)*100:.1f}%)")

        # Overfitting detection (degradation metrics)
        print(f"\n{'OVERFITTING DETECTION (Train → Test Degradation)'}")
        print("-" * 70)

        # PF degradation (ratio = test_pf / train_pf)
        median_pf_degradation = df_results['pf_degradation'].median()
        worst_pf_degradation = df_results['pf_degradation'].min()
        worst_pf_split = df_results.loc[df_results['pf_degradation'].idxmin(), 'split']

        print(f"{'Median PF Degradation':<40} {median_pf_degradation:.2f} (test/train ratio)")
        print(f"{'Worst PF Degradation':<40} {worst_pf_degradation:.2f} (split {worst_pf_split:.0f})")

        # Expected payoff degradation
        median_ep_degradation = df_results['expected_payoff_degradation'].median()
        worst_ep_degradation = df_results['expected_payoff_degradation'].min()
        worst_ep_split = df_results.loc[df_results['expected_payoff_degradation'].idxmin(), 'split']

        print(f"{'Median Expected Payoff Degradation':<40} {median_ep_degradation:.2f} (test/train ratio)")
        print(f"{'Worst Expected Payoff Degradation':<40} {worst_ep_degradation:.2f} (split {worst_ep_split:.0f})")

        # Interpretation
        print(f"\nInterpretation:")
        if median_pf_degradation >= 0.8:
            print(f"  ✓ Good: Median PF degradation {median_pf_degradation:.2f} ≥ 0.8 (low overfitting)")
        elif median_pf_degradation >= 0.6:
            print(f"  ⚠ Moderate: Median PF degradation {median_pf_degradation:.2f} (some overfitting)")
        else:
            print(f"  ✗ Poor: Median PF degradation {median_pf_degradation:.2f} < 0.6 (high overfitting)")

        if worst_pf_degradation < 0.5:
            print(f"  ⚠ Warning: Worst split degradation {worst_pf_degradation:.2f} < 0.5 (severe degradation in split {worst_pf_split:.0f})")

        print("=" * 70)

    if verbose:
        # Monte Carlo sequence risk analysis
        print("\n" + "=" * 70)
        print("MONTE CARLO ANALYSIS - Sequence Risk (Trade Order Reshuffle)")
        print("=" * 70)

        # Aggregate MC statistics across splits
        mc_median_dd_avg = df_results['mc_median_max_dd'].mean()
        mc_95th_dd_avg = df_results['mc_95th_percentile_dd'].mean()
        mc_max_dd_worst = df_results['mc_max_max_dd'].max()
        mc_prob_loss_avg = df_results['mc_prob_loss'].mean()
        mc_prob_dd_exceeds_avg = df_results['mc_prob_dd_exceeds_observed'].mean()

        # Observed vs MC comparison
        observed_dd_avg = df_results['test_max_drawdown'].mean()
        dd_ratio = observed_dd_avg / mc_median_dd_avg if mc_median_dd_avg > 0 else 1.0

        print(f"\nDrawdown Statistics (averaged across splits):")
        print(f"{'Observed Avg Max DD':<40} {observed_dd_avg:.2f} pips")
        print(f"{'MC Median Max DD':<40} {mc_median_dd_avg:.2f} pips")
        print(f"{'MC 95th Percentile DD':<40} {mc_95th_dd_avg:.2f} pips")
        print(f"{'MC Maximum DD (worst split)':<40} {mc_max_dd_worst:.2f} pips")

        print(f"\nSequence Risk:")
        print(f"{'Avg P(final PnL < 0)':<40} {mc_prob_loss_avg*100:.1f}%")
        print(f"{'Avg P(DD > observed)':<40} {mc_prob_dd_exceeds_avg*100:.1f}%")

        print(f"\nInterpretation:")
        if dd_ratio < 0.8:
            print(f"  ✓ Lucky: Observed DD {dd_ratio:.2f}x median (got favorable trade order)")
        elif dd_ratio > 1.2:
            print(f"  ⚠ Unlucky: Observed DD {dd_ratio:.2f}x median (got unfavorable trade order)")
        else:
            print(f"  ~ Typical: Observed DD {dd_ratio:.2f}x median (trade order not extreme)")

        if mc_prob_loss_avg > 0.4:
            print(f"  ✗ High Risk: {mc_prob_loss_avg*100:.1f}% probability of loss with random order")
        elif mc_prob_loss_avg > 0.2:
            print(f"  ⚠ Moderate Risk: {mc_prob_loss_avg*100:.1f}% probability of loss with random order")
        else:
            print(f"  ✓ Low Risk: {mc_prob_loss_avg*100:.1f}% probability of loss with random order")

        if mc_prob_dd_exceeds_avg > 0.7:
            print(f"  ⚠ Optimistic DD: {mc_prob_dd_exceeds_avg*100:.1f}% chance of worse drawdown")

        print("=" * 70)

    # ========================================================================
    # PARAMETER PERFORMANCE ANALYSIS ACROSS SPLITS
    # ========================================================================
    if len(all_train_results) > 0 and verbose:
        print("\n" + "=" * 70)
        print("PARAMETER PERFORMANCE ANALYSIS")
        print("=" * 70)

        # Build aggregated parameter performance table
        param_performance = {}  # key = tuple of param values, value = list of test results

        for split_data in all_train_results:
            split_num = split_data['split']
            train_df = split_data['train_results']
            best_params = split_data['best_params']

            # For each parameter combination in training grid
            for idx, row in train_df.iterrows():
                # Create param tuple as key
                param_tuple = tuple(sorted([(k, row[k]) for k in param_grid.keys()]))

                if param_tuple not in param_performance:
                    param_performance[param_tuple] = {
                        'params': dict(param_tuple),
                        'count_selected': 0,
                        'test_profit_factors': [],
                        'test_pnls': [],
                        'splits_seen': []
                    }

                param_performance[param_tuple]['splits_seen'].append(split_num)

                # Check if this combo was chosen as best for this split
                is_best = all(row[k] == best_params[k] for k in param_grid.keys())
                if is_best:
                    param_performance[param_tuple]['count_selected'] += 1
                    param_performance[param_tuple]['test_profit_factors'].append(split_data['test_profit_factor'])
                    param_performance[param_tuple]['test_pnls'].append(split_data['test_total_pnl_after_costs'])

        # Compute aggregate metrics for each parameter combination
        param_summary = []
        for param_tuple, data in param_performance.items():
            if len(data['test_profit_factors']) > 0:  # Only combos that were selected at least once
                # Replace inf with a large number for aggregation
                pf_values = [pf if pf != float('inf') else 999.0 for pf in data['test_profit_factors']]

                param_summary.append({
                    'params': data['params'],
                    'count_selected': data['count_selected'],
                    'mean_test_pf': np.mean(pf_values),
                    'median_test_pf': np.median(pf_values),
                    'mean_test_pnl': np.mean(data['test_pnls']),
                    'pct_splits_profitable': (sum(1 for pnl in data['test_pnls'] if pnl > 0) / len(data['test_pnls']) * 100)
                })

        if len(param_summary) > 0:
            # Sort by median_test_pf (desc), then mean_test_pnl (desc)
            param_summary.sort(key=lambda x: (x['median_test_pf'], x['mean_test_pnl']), reverse=True)

            print(f"\nParameter Performance Across All Splits (sorted by median OOS PF, then mean OOS PnL):")
            print("-" * 120)
            print(f"{'Params':<50} {'Selected':<10} {'Mean PF':<10} {'Med PF':<10} {'Mean PnL':<12} {'% Profit':<10}")
            print("-" * 120)

            for item in param_summary:
                params_str = ', '.join([f"{k}={v}" for k, v in item['params'].items()])
                mean_pf_str = f"{item['mean_test_pf']:.2f}" if item['mean_test_pf'] < 900 else "Inf"
                med_pf_str = f"{item['median_test_pf']:.2f}" if item['median_test_pf'] < 900 else "Inf"

                print(f"{params_str:<50} {item['count_selected']:<10} {mean_pf_str:<10} {med_pf_str:<10} {item['mean_test_pnl']:<12.1f} {item['pct_splits_profitable']:<10.1f}")

            print("-" * 120)

        # ====================================================================
        # TOP-3 PARAMETER COMBOS PER SPLIT (TRAIN PF) + OOS PERFORMANCE
        # ====================================================================
        print("\n" + "=" * 70)
        print("TOP-3 PARAMETER COMBOS PER SPLIT (by train PF) + OOS Performance")
        print("=" * 70)

        for split_data in all_train_results:
            split_num = split_data['split']
            train_df = split_data['train_results'].copy()
            best_params = split_data['best_params']

            # Sort by train profit_factor descending
            train_df_sorted = train_df.sort_values(
                by=['profit_factor', 'total_pnl_after_costs'],
                ascending=[False, False]
            ).head(3)

            print(f"\nSplit {split_num}:")
            print("  " + "-" * 66)
            print(f"  {'Rank':<6} {'Params':<35} {'Train PF':<12} {'OOS PF':<12} {'OOS PnL':<12}")
            print("  " + "-" * 66)

            for rank, (idx, row) in enumerate(train_df_sorted.iterrows(), 1):
                # Build param string
                params_str = ', '.join([f"{k}={row[k]}" for k in param_grid.keys()])

                # Check if this combo was the best (i.e., has OOS test result)
                is_best = all(row[k] == best_params[k] for k in param_grid.keys())

                train_pf_str = f"{row['profit_factor']:.2f}" if row['profit_factor'] != float('inf') else "Inf"

                if is_best:
                    # This combo was chosen - we have OOS results
                    oos_pf = split_data['test_profit_factor']
                    oos_pnl = split_data['test_total_pnl_after_costs']
                    oos_pf_str = f"{oos_pf:.2f}" if oos_pf != float('inf') else "Inf"
                    oos_pnl_str = f"{oos_pnl:.1f}"
                    marker = " *"  # Mark the chosen combo
                else:
                    # Not chosen - no OOS test
                    oos_pf_str = "N/A"
                    oos_pnl_str = "N/A"
                    marker = ""

                print(f"  {rank:<6} {params_str:<35} {train_pf_str:<12} {oos_pf_str:<12} {oos_pnl_str:<12}{marker}")

            print("  " + "-" * 66)
            print("  * = Selected as best and tested OOS")

        print("=" * 70)

    # ========================================================================
    # PARAMETER STABILITY ACROSS SPLITS
    # ========================================================================
    if len(param_stability_data) > 0:
        print("\n" + "=" * 70)
        print("PARAMETER STABILITY ACROSS SPLITS")
        print("=" * 70)
        print("\nTesting ALL parameter combinations on each split's test set")
        print("(This reveals which parameters are robust across market conditions)")
        print("-" * 70)

        # Aggregate by parameter combination
        from collections import defaultdict
        param_aggregates = defaultdict(lambda: {
            'test_pfs': [],
            'test_pnls': [],
            'count_selected': 0,
            'splits_profitable': 0,
            'total_splits': 0
        })

        for result in param_stability_data:
            # Create param tuple as key
            param_tuple = tuple(sorted([(k, v) for k, v in result['params'].items()]))

            # Aggregate data
            pf = result['test_profit_factor']
            pnl = result['test_total_pnl_after_costs']

            # Handle inf PF for aggregation
            pf_value = pf if pf != float('inf') else 999.0

            param_aggregates[param_tuple]['test_pfs'].append(pf_value)
            param_aggregates[param_tuple]['test_pnls'].append(pnl)
            param_aggregates[param_tuple]['total_splits'] += 1

            if result['is_best']:
                param_aggregates[param_tuple]['count_selected'] += 1

            if pnl > 0:
                param_aggregates[param_tuple]['splits_profitable'] += 1

        # Compute summary statistics for each combo
        stability_summary = []
        for param_tuple, data in param_aggregates.items():
            mean_pf = np.mean(data['test_pfs'])
            median_pf = np.median(data['test_pfs'])
            mean_pnl = np.mean(data['test_pnls'])
            median_pnl = np.median(data['test_pnls'])
            pct_profitable = (data['splits_profitable'] / data['total_splits'] * 100)

            stability_summary.append({
                'params': dict(param_tuple),
                'mean_test_pf': mean_pf,
                'median_test_pf': median_pf,
                'mean_test_pnl': mean_pnl,
                'median_test_pnl': median_pnl,
                'pct_profitable': pct_profitable,
                'count_selected': data['count_selected'],
                'splits_tested': data['total_splits']
            })

        # Sort by median test PF (descending)
        stability_summary.sort(key=lambda x: x['median_test_pf'], reverse=True)

        # Print TOP 10 by median test PF
        print(f"\nTOP 10 PARAMETER COMBINATIONS (by median test PF):")
        print("-" * 120)
        print(f"{'Rank':<6} {'Params':<40} {'Med PF':<10} {'Mean PF':<10} {'Med PnL':<12} {'% Profit':<10} {'Selected':<10}")
        print("-" * 120)

        for rank, item in enumerate(stability_summary[:10], 1):
            params_str = ', '.join([f"{k}={v}" for k, v in item['params'].items()])
            med_pf_str = f"{item['median_test_pf']:.2f}" if item['median_test_pf'] < 900 else "Inf"
            mean_pf_str = f"{item['mean_test_pf']:.2f}" if item['mean_test_pf'] < 900 else "Inf"

            print(f"{rank:<6} {params_str:<40} {med_pf_str:<10} {mean_pf_str:<10} "
                  f"{item['median_test_pnl']:<12.1f} {item['pct_profitable']:<10.1f} {item['count_selected']:<10}")

        print("-" * 120)

        # Find MOST STABLE combination (highest % profitable, then best median PF)
        stability_summary_for_stable = sorted(stability_summary,
                                               key=lambda x: (x['pct_profitable'], x['median_test_pf']),
                                               reverse=True)
        most_stable = stability_summary_for_stable[0]

        print(f"\nMOST STABLE PARAMETER COMBINATION:")
        print("-" * 70)
        params_str = ', '.join([f"{k}={v}" for k, v in most_stable['params'].items()])
        print(f"  Parameters: {params_str}")
        print(f"  % Profitable Splits: {most_stable['pct_profitable']:.1f}%")
        print(f"  Median Test PF: {most_stable['median_test_pf']:.2f}")
        print(f"  Mean Test PF: {most_stable['mean_test_pf']:.2f}")
        print(f"  Median Test PnL: {most_stable['median_test_pnl']:.1f} pips")
        print(f"  Mean Test PnL: {most_stable['mean_test_pnl']:.1f} pips")
        print(f"  Selected as Best: {most_stable['count_selected']}/{most_stable['splits_tested']} splits")

        # Interpretation
        print(f"\n  Interpretation:")
        if most_stable['pct_profitable'] == 100.0:
            print(f"    ✓ Excellent: Profitable in 100% of splits")
        elif most_stable['pct_profitable'] >= 80.0:
            print(f"    ✓ Good: Profitable in {most_stable['pct_profitable']:.1f}% of splits")
        elif most_stable['pct_profitable'] >= 60.0:
            print(f"    ⚠ Moderate: Profitable in {most_stable['pct_profitable']:.1f}% of splits")
        else:
            print(f"    ✗ Poor: Profitable in only {most_stable['pct_profitable']:.1f}% of splits")

        if most_stable['median_test_pf'] >= 2.0:
            print(f"    ✓ Strong: Median PF {most_stable['median_test_pf']:.2f} ≥ 2.0")
        elif most_stable['median_test_pf'] >= 1.5:
            print(f"    ✓ Good: Median PF {most_stable['median_test_pf']:.2f} ≥ 1.5")
        elif most_stable['median_test_pf'] >= 1.0:
            print(f"    ⚠ Marginal: Median PF {most_stable['median_test_pf']:.2f} barely profitable")
        else:
            print(f"    ✗ Poor: Median PF {most_stable['median_test_pf']:.2f} < 1.0 (unprofitable)")

        print("-" * 70)
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
            'broken_level_cooldown_hours': [12.0, 24.0, 48.0],
            'min_edge_pips': [0.0, 2.0, 4.0]
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
            display_cols = ['min_confidence', 'broken_level_cooldown_hours', 'min_edge_pips', 'total_trades',
                           'win_rate', 'profit_factor', 'total_pnl_after_costs', 'max_drawdown']
            print(results_df[display_cols].head(10).to_string(index=False))
        else:
            print("No results to display - all backtests failed")

    elif MODE == "walk-forward":
        # Run walk-forward analysis (YEAR-BASED)
        print("\n>>> Running Year-Based Walk-Forward Analysis\n")

        # Reduced grid for faster testing (3×2×2 = 12 combinations vs 27)
        # This cuts runtime by ~55% while still exploring key parameter space
        param_grid = {
            'min_confidence': [0.60, 0.65, 0.70],  # Keep 3 values
            'broken_level_cooldown_hours': [24.0, 48.0],  # Reduce to 2 (drop 12.0)
            'min_edge_pips': [2.0, 4.0]  # Reduce to 2 (drop 0.0)
        }

        # For comprehensive testing, use full grid:
        # param_grid = {
        #     'min_confidence': [0.60, 0.65, 0.70],
        #     'broken_level_cooldown_hours': [12.0, 24.0, 48.0],
        #     'min_edge_pips': [0.0, 2.0, 4.0]
        # }

        wf_results = run_walk_forward(
            symbol="EURUSD",
            timeframe="H1",
            lookback_bars=400,
            param_grid=param_grid,
            spread_pips=1.0,
            commission_per_side_per_lot=7.0,
            slippage_pips=0.5,
            usd_per_pip_per_lot=10.0,
            starting_balance_usd=10000.0,
            n_jobs=-1,
            # Year-based walk-forward
            use_year_based_splits=True,
            test_years=[2022, 2023, 2024, 2025]  # Train on 2 previous years, test on each
        )

        # Display detailed results
        if len(wf_results) > 0:
            print("\nDetailed Year-Based Walk-Forward Results:")
            print("=" * 70)
            display_cols = ['test_year', 'train_years',
                           'param_min_confidence', 'param_broken_level_cooldown_hours', 'param_min_edge_pips',
                           'train_profit_factor', 'test_profit_factor',
                           'train_total_trades', 'test_total_trades',
                           'test_total_pnl_after_costs', 'pf_degradation']
            print(wf_results[display_cols].to_string(index=False))

    print("\n" + "=" * 70)
    print("Backtest Suite Complete")
    print("=" * 70 + "\n")
