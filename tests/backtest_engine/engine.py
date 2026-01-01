"""Backtest Engine - Main event loop orchestrator

Connects tick generator, broker, and EA into a cohesive event-driven backtest.
Mimics MT5 Strategy Tester architecture with time-ordered tick stream.

Event sequence per tick:
1. Broker checks SL/TP on all positions
2. EA processes tick (detects new bar, runs filters)
3. Broker executes pending orders (on bar open)
"""

from typing import Dict, Optional
import pandas as pd
from datetime import datetime

from .tick_generator import TickGenerator
from .broker import BacktestBroker
from .expert_advisor import Volarix4EA


class BacktestEngine:
    """Event-driven backtest engine

    Orchestrates the main event loop, coordinating:
    - Tick stream generation
    - Broker position management
    - EA strategy logic
    - Statistics calculation

    Designed to produce identical results to the legacy bar-based backtest
    when using "Open prices only" tick mode.
    """

    def __init__(
        self,
        tick_generator: TickGenerator,
        broker: BacktestBroker,
        ea: Volarix4EA,
        config: Dict
    ):
        """Initialize backtest engine

        Args:
            tick_generator: Tick stream generator
            broker: BacktestBroker instance
            ea: Volarix4EA instance
            config: Configuration dict (for metadata in results)
        """
        self.tick_generator = tick_generator
        self.broker = broker
        self.ea = ea
        self.config = config

    def run(self, start_index: int = 0, verbose: bool = False) -> Dict:
        """Run event-driven backtest

        Main event loop that processes ticks chronologically and orchestrates
        broker and EA interactions.

        Args:
            start_index: Bar index to start from (for lookback handling)
            verbose: If True, print progress information

        Returns:
            Dict with backtest results (same format as legacy run_backtest)
        """
        # Initialize EA
        if not self.ea.on_init():
            raise RuntimeError("EA initialization failed")

        if verbose:
            print(f"\n{'='*60}")
            print(f"Starting event-driven backtest")
            print(f"Tick mode: {self.tick_generator.get_tick_mode_name()}")
            print(f"Start index: {start_index}")
            print(f"Total bars: {len(self.tick_generator.df)}")
            print(f"{'='*60}\n")

        # Main event loop
        tick_count = 0
        bar_count = 0
        last_bar_index = -1

        for tick in self.tick_generator.generate_ticks(start_index=start_index):
            tick_count += 1

            # Track bar progression
            if tick.bar_index > last_bar_index:
                bar_count += 1
                last_bar_index = tick.bar_index

                if verbose and bar_count % 100 == 0:
                    positions = self.broker.get_position_count()
                    trades = len(self.broker.state.closed_trades)
                    print(f"Processed {bar_count} bars, {tick_count} ticks | "
                          f"Open: {positions} | Closed: {trades}")

            # Event sequence per tick:
            # 1. Broker checks SL/TP on all positions
            self.broker.on_tick(tick)

            # 2. EA processes tick (detects new bar, runs filters)
            self.ea.on_tick(tick)

            # 3. Broker executes pending orders (on bar open only)
            if tick.is_bar_open:
                self.broker.execute_pending_orders(tick)

        if verbose:
            print(f"\n{'='*60}")
            print(f"Backtest complete")
            print(f"Total ticks processed: {tick_count}")
            print(f"Total bars processed: {bar_count}")
            print(f"{'='*60}\n")

        # Calculate and return statistics
        return self._calculate_statistics()

    def _calculate_statistics(self) -> Dict:
        """Calculate backtest statistics

        Reuses the same statistics calculation logic as the legacy backtest
        to ensure identical output format.

        Returns:
            Dict with comprehensive backtest results
        """
        trades = self.broker.state.closed_trades
        ea_stats = self.ea.get_statistics()

        # Basic metrics
        total_trades = len(trades)

        if total_trades == 0:
            return self._empty_results(ea_stats)

        # Trade outcomes
        winning_trades = [t for t in trades if t.pnl_after_costs > 0]
        losing_trades = [t for t in trades if t.pnl_after_costs < 0]
        breakeven_trades = [t for t in trades if t.pnl_after_costs == 0]

        wins = len(winning_trades)
        losses = len(losing_trades)

        # PnL metrics
        total_pnl_before_costs = sum(t.pnl for t in trades)  # pnl is before costs
        total_pnl_after_costs = sum(t.pnl_after_costs for t in trades)
        total_costs = total_pnl_before_costs - total_pnl_after_costs

        # Win/loss statistics
        win_rate = wins / total_trades if total_trades > 0 else 0.0

        avg_win = (sum(t.pnl_after_costs for t in winning_trades) / wins) if wins > 0 else 0.0
        avg_loss = (sum(t.pnl_after_costs for t in losing_trades) / losses) if losses > 0 else 0.0

        # Risk metrics
        profit_factor = (
            sum(t.pnl_after_costs for t in winning_trades) /
            abs(sum(t.pnl_after_costs for t in losing_trades))
            if losses > 0 and sum(t.pnl_after_costs for t in losing_trades) != 0
            else float('inf') if wins > 0 else 0.0
        )

        expectancy = total_pnl_after_costs / total_trades if total_trades > 0 else 0.0

        # Equity curve analysis
        equity_curve = self._calculate_equity_curve(trades)
        max_drawdown = self._calculate_max_drawdown(equity_curve)

        # TP analysis
        tp1_hits = sum(1 for t in trades if 1 in t.tp_levels_hit)
        tp2_hits = sum(1 for t in trades if 2 in t.tp_levels_hit)
        tp3_hits = sum(1 for t in trades if 3 in t.tp_levels_hit)
        sl_hits = sum(1 for t in trades if t.exit_reason == 'sl')

        # Direction breakdown
        buy_trades = [t for t in trades if t.direction == 'BUY']
        sell_trades = [t for t in trades if t.direction == 'SELL']

        buy_wins = sum(1 for t in buy_trades if t.pnl_after_costs > 0)
        sell_wins = sum(1 for t in sell_trades if t.pnl_after_costs > 0)

        # Assemble results
        results = {
            # Summary metrics
            'total_trades': total_trades,
            'wins': wins,
            'losses': losses,
            'breakeven': len(breakeven_trades),
            'win_rate': win_rate,

            # PnL metrics
            'total_pnl_before_costs': total_pnl_before_costs,
            'total_pnl_after_costs': total_pnl_after_costs,
            'total_costs': total_costs,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'expectancy': expectancy,
            'profit_factor': profit_factor,

            # Risk metrics
            'max_drawdown': max_drawdown,
            'max_drawdown_pct': (max_drawdown / 10000) * 100 if max_drawdown != 0 else 0.0,

            # TP/SL breakdown
            'tp1_hits': tp1_hits,
            'tp2_hits': tp2_hits,
            'tp3_hits': tp3_hits,
            'sl_hits': sl_hits,
            'tp1_rate': tp1_hits / total_trades if total_trades > 0 else 0.0,
            'tp2_rate': tp2_hits / total_trades if total_trades > 0 else 0.0,
            'tp3_rate': tp3_hits / total_trades if total_trades > 0 else 0.0,
            'sl_rate': sl_hits / total_trades if total_trades > 0 else 0.0,

            # Direction breakdown
            'buy_trades': len(buy_trades),
            'sell_trades': len(sell_trades),
            'buy_win_rate': buy_wins / len(buy_trades) if buy_trades else 0.0,
            'sell_win_rate': sell_wins / len(sell_trades) if sell_trades else 0.0,
            'buy_pnl': sum(t.pnl_after_costs for t in buy_trades),
            'sell_pnl': sum(t.pnl_after_costs for t in sell_trades),

            # EA filter statistics
            'filter_rejections': ea_stats['filter_rejections'],
            'signals_generated': ea_stats['signals_generated'],

            # Raw data
            'trades': trades,
            'equity_curve': equity_curve,

            # Metadata
            'config': self.config,
            'tick_mode': self.tick_generator.get_tick_mode_name(),
            'backtest_type': 'event_driven',
        }

        return results

    def _empty_results(self, ea_stats: Dict) -> Dict:
        """Return empty results structure when no trades executed

        Args:
            ea_stats: EA statistics dict

        Returns:
            Dict with zero/empty values
        """
        return {
            'total_trades': 0,
            'wins': 0,
            'losses': 0,
            'breakeven': 0,
            'win_rate': 0.0,
            'total_pnl_before_costs': 0.0,
            'total_pnl_after_costs': 0.0,
            'total_costs': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'expectancy': 0.0,
            'profit_factor': 0.0,
            'max_drawdown': 0.0,
            'max_drawdown_pct': 0.0,
            'tp1_hits': 0,
            'tp2_hits': 0,
            'tp3_hits': 0,
            'sl_hits': 0,
            'tp1_rate': 0.0,
            'tp2_rate': 0.0,
            'tp3_rate': 0.0,
            'sl_rate': 0.0,
            'buy_trades': 0,
            'sell_trades': 0,
            'buy_win_rate': 0.0,
            'sell_win_rate': 0.0,
            'buy_pnl': 0.0,
            'sell_pnl': 0.0,
            'filter_rejections': ea_stats['filter_rejections'],
            'signals_generated': ea_stats['signals_generated'],
            'trades': [],
            'equity_curve': [],
            'config': self.config,
            'tick_mode': self.tick_generator.get_tick_mode_name(),
            'backtest_type': 'event_driven',
        }

    def _calculate_equity_curve(self, trades: list) -> list:
        """Calculate cumulative equity curve

        Args:
            trades: List of closed Trade objects

        Returns:
            List of (datetime, equity) tuples
        """
        equity_curve = []
        cumulative_pnl = 0.0

        for trade in trades:
            cumulative_pnl += trade.pnl_after_costs
            equity_curve.append((trade.exit_time, cumulative_pnl))

        return equity_curve

    def _calculate_max_drawdown(self, equity_curve: list) -> float:
        """Calculate maximum drawdown from equity curve

        Args:
            equity_curve: List of (datetime, equity) tuples

        Returns:
            Maximum drawdown in USD
        """
        if not equity_curve:
            return 0.0

        max_drawdown = 0.0
        peak_equity = equity_curve[0][1]

        for _, equity in equity_curve:
            # Update peak
            if equity > peak_equity:
                peak_equity = equity

            # Calculate drawdown from peak
            drawdown = peak_equity - equity

            # Update max drawdown
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        return max_drawdown
