"""Backtest engine orchestrating API calls, trade execution, and P&L tracking.

This module coordinates:
1. Loading bars from data source
2. Calling API for signals
3. Executing trades via broker simulator
4. Tracking equity curve and metrics
"""

from typing import List, Optional
from datetime import datetime
import logging

from .config import BacktestConfig, CostModel
from .data_source import BarDataSource, Bar
from .api_client import SignalApiClient, SignalResponse
from .broker_sim import BrokerSimulator, Trade, ExitReason
from time import time


class BacktestEngine:
    """Main backtest orchestration engine.

    Implements the backtest loop:
    - For each bar after warmup
    - Call API for signal
    - If BUY/SELL and no open position, open trade
    - Update open position with current bar (check SL/TP)
    - Track equity curve
    """

    def __init__(
        self,
        config: BacktestConfig,
        data_source: BarDataSource,
        api_client: SignalApiClient,
        broker: BrokerSimulator,
        logger: Optional[logging.Logger] = None
    ):
        """Initialize backtest engine.

        Args:
            config: Backtest configuration
            data_source: Data source for bars
            api_client: API client for signals
            broker: Broker simulator
            logger: Optional logger
        """
        self.config = config
        self.data_source = data_source
        self.api_client = api_client
        self.broker = broker
        self.logger = logger or logging.getLogger(__name__)

        # State tracking
        self.bars: List[Bar] = []
        self.trades: List[Trade] = []
        self.open_trade: Optional[Trade] = None
        self.balance: float = config.initial_balance_usd
        self.equity_curve: List[dict] = []

        # Metrics
        self.total_signals = 0
        self.buy_signals = 0
        self.sell_signals = 0
        self.hold_signals = 0

    def run(self) -> dict:
        """Run the backtest.

        Returns:
            Dictionary with results including trades, equity curve, and metrics
        """
        self.logger.info("=" * 70)
        self.logger.info("Starting Backtest")
        self.logger.info("=" * 70)
        self.logger.info(f"Symbol: {self.config.symbol}")
        self.logger.info(f"Timeframe: {self.config.timeframe}")
        self.logger.info(f"Initial Balance: ${self.config.initial_balance_usd:,.2f}")
        self.logger.info(f"API URL: {self.config.api_url}")
        self.logger.info(f"Warmup Bars: {self.config.warmup_bars}")
        self.logger.info(f"Fill At: {self.config.fill_at}")
        self.logger.info("=" * 70)

        # Load bars
        self.logger.info("Loading historical bars...")
        self.bars = self.data_source.load()
        self.logger.info(f"Loaded {len(self.bars)} bars")
        self.logger.info(f"First bar: {self.bars[0].time}")
        self.logger.info(f"Last bar: {self.bars[-1].time}")

        if len(self.bars) < self.config.warmup_bars:
            raise ValueError(
                f"Insufficient bars: {len(self.bars)} < warmup_bars ({self.config.warmup_bars})"
            )

        # Run backtest loop
        self.logger.info("=" * 70)
        self.logger.info("Starting backtest loop...")
        self.logger.info("=" * 70)

        for i in range(self.config.warmup_bars, len(self.bars)):
            current_bar = self.bars[i]

            # Update open position first (if any)
            if self.open_trade:
                self._update_open_position(current_bar)

            # Request signal if no open position
            if not self.open_trade:
                signal = self._get_signal(i)
                self.total_signals += 1

                if signal.signal == "BUY":
                    self.buy_signals += 1
                    self._open_position(signal, i)
                elif signal.signal == "SELL":
                    self.sell_signals += 1
                    self._open_position(signal, i)
                else:
                    self.hold_signals += 1

            # Record equity at end of bar
            self._record_equity(current_bar.time)

            # Progress logging
            if self.config.verbose and (i - self.config.warmup_bars) % 100 == 0:
                progress = ((i - self.config.warmup_bars) / (len(self.bars) - self.config.warmup_bars)) * 100
                self.logger.info(
                    f"Progress: {progress:.1f}% "
                    f"({i - self.config.warmup_bars}/{len(self.bars) - self.config.warmup_bars} bars) "
                    f"| Trades: {len(self.trades)} | Balance: ${self.balance:,.2f}"
                )
        # Close any remaining open position at last bar
        if self.open_trade:
            self.logger.info("Closing remaining open position at end of backtest")
            last_bar = self.bars[-1]
            self.broker._close_trade(
                self.open_trade,
                last_bar.time,
                last_bar.close,
                ExitReason.MANUAL
            )
            self._finalize_trade(self.open_trade)

        # Compute final metrics
        results = self._compute_results()

        self.logger.info("=" * 70)
        self.logger.info("Backtest Complete")
        self.logger.info("=" * 70)

        return results

    def _get_signal(self, bar_index: int) -> SignalResponse:
        """Get signal from API for the given bar index.

        Args:
            bar_index: Index of the bar to get signal for

        Returns:
            SignalResponse from API
        """
        current_bar = self.bars[bar_index]

        if self.config.use_optimized_mode:
            # Optimized mode: send bar_time, API fetches bars
            signal = self.api_client.get_signal_optimized(
                symbol=self.config.symbol,
                timeframe=self.config.timeframe,
                bar_time=current_bar.time,
                lookback_bars=self.config.lookback_bars,
                min_confidence=self.config.min_confidence,
                broken_level_cooldown_hours=self.config.broken_level_cooldown_hours,
                broken_level_break_pips=self.config.broken_level_break_pips,
                min_edge_pips=self.config.min_edge_pips,
                spread_pips=self.config.spread_pips,
                slippage_pips=self.config.slippage_pips,
                commission_per_side_per_lot=self.config.commission_per_side_per_lot,
                usd_per_pip_per_lot=self.config.usd_per_pip_per_lot,
                lot_size=self.config.lot_size
            )
        else:
            # Legacy mode: send full bar data
            start_idx = max(0, bar_index - self.config.lookback_bars + 1)
            bars_for_signal = self.bars[start_idx:bar_index + 1]
            bars_dict = [bar.to_dict() for bar in bars_for_signal]

            signal = self.api_client.get_signal_legacy(
                symbol=self.config.symbol,
                timeframe=self.config.timeframe,
                bars=bars_dict,
                min_confidence=self.config.min_confidence,
                broken_level_cooldown_hours=self.config.broken_level_cooldown_hours,
                broken_level_break_pips=self.config.broken_level_break_pips,
                min_edge_pips=self.config.min_edge_pips,
                spread_pips=self.config.spread_pips,
                slippage_pips=self.config.slippage_pips,
                commission_per_side_per_lot=self.config.commission_per_side_per_lot,
                usd_per_pip_per_lot=self.config.usd_per_pip_per_lot,
                lot_size=self.config.lot_size
            )

        return signal

    def _open_position(self, signal: SignalResponse, bar_index: int):
        """Open a new position based on signal.

        Args:
            signal: SignalResponse from API
            bar_index: Index of the bar where signal was generated
        """
        # Determine entry bar and price based on fill_at config
        if self.config.fill_at == "next_open":
            # Fill at next bar open (no peeking)
            if bar_index + 1 >= len(self.bars):
                # No next bar available, skip
                return
            entry_bar = self.bars[bar_index + 1]
            entry_price = entry_bar.open
        else:  # "signal_close"
            # Fill at signal bar close (used for testing, can peek)
            entry_bar = self.bars[bar_index]
            entry_price = entry_bar.close

        # Calculate position size based on risk
        # Risk per trade = balance * risk_percent / 100
        # Lot size already provided in config, but could calculate dynamically here
        lot_size = self.config.lot_size

        # Open trade via broker
        trade = self.broker.open_trade(
            direction=signal.signal,
            entry_time=entry_bar.time,
            entry_price=entry_price,
            lot_size=lot_size,
            sl=signal.sl,
            tp1=signal.tp1,
            tp2=signal.tp2,
            tp3=signal.tp3,
            tp1_percent=signal.tp1_percent,
            tp2_percent=signal.tp2_percent,
            tp3_percent=signal.tp3_percent,
            confidence=signal.confidence,
            reason=signal.reason
        )

        self.open_trade = trade

        if self.config.verbose:
            self.logger.info(
                f"[{entry_bar.time}] Opened {signal.signal} @ {entry_price:.5f} "
                f"(SL: {signal.sl:.5f}, TP1: {signal.tp1:.5f}) - {signal.reason}"
            )

    def _update_open_position(self, current_bar: Bar):
        """Update open position with current bar data.

        Args:
            current_bar: Current bar to check for SL/TP hits
        """
        if not self.open_trade or self.open_trade.is_closed:
            return

        # Update trade with current bar
        trade_updated = self.broker.update_trade(
            self.open_trade,
            current_bar.time,
            current_bar.high,
            current_bar.low,
            current_bar.close
        )

        # If trade was closed or partially closed
        if trade_updated and self.config.verbose:
            if self.open_trade.is_closed:
                self.logger.info(
                    f"[{current_bar.time}] Closed {self.open_trade.direction} "
                    f"@ {self.open_trade.exit_price:.5f} "
                    f"({self.open_trade.exit_reason.value}) - "
                    f"P&L: ${self.open_trade.net_pnl_usd:.2f}"
                )
            else:
                # Partial TP hit
                tp_hit = []
                if self.open_trade.tp1_hit:
                    tp_hit.append("TP1")
                if self.open_trade.tp2_hit:
                    tp_hit.append("TP2")
                if self.open_trade.tp3_hit:
                    tp_hit.append("TP3")
                self.logger.info(
                    f"[{current_bar.time}] Partial TP hit: {', '.join(tp_hit)} - "
                    f"Remaining: {self.open_trade.remaining_lots:.2f} lots"
                )

        # If trade fully closed, finalize it
        if self.open_trade.is_closed:
            self._finalize_trade(self.open_trade)
            self.open_trade = None

    def _finalize_trade(self, trade: Trade):
        """Finalize a closed trade and update balance.

        Args:
            trade: Closed trade to finalize
        """
        # Update balance
        self.balance += trade.net_pnl_usd

        # Add to trade history
        self.trades.append(trade)

    def _record_equity(self, time: datetime):
        """Record equity at current point in time.

        Args:
            time: Current timestamp
        """
        # Calculate total equity (balance + unrealized P&L)
        unrealized_pnl = 0.0
        if self.open_trade and not self.open_trade.is_closed:
            unrealized_pnl = self.open_trade.net_pnl_usd

        total_equity = self.balance + unrealized_pnl

        self.equity_curve.append({
            "time": time,
            "balance": self.balance,
            "unrealized_pnl": unrealized_pnl,
            "equity": total_equity
        })

    def _compute_results(self) -> dict:
        """Compute backtest results and metrics.

        Returns:
            Dictionary with all results
        """
        if not self.trades:
            return {
                "trades": [],
                "equity_curve": self.equity_curve,
                "total_trades": 0,
                "total_signals": self.total_signals,
                "buy_signals": self.buy_signals,
                "sell_signals": self.sell_signals,
                "hold_signals": self.hold_signals,
                "winning_trades": 0,
                "losing_trades": 0,
                "net_profit_usd": 0.0,
                "gross_profit_usd": 0.0,
                "gross_loss_usd": 0.0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "max_drawdown_usd": 0.0,
                "max_drawdown_pct": 0.0,
                "final_balance": self.balance,
                "return_pct": 0.0
            }

        # Calculate metrics
        total_trades = len(self.trades)
        winning_trades = [t for t in self.trades if t.net_pnl_usd > 0]
        losing_trades = [t for t in self.trades if t.net_pnl_usd < 0]

        gross_profit = sum(t.net_pnl_usd for t in winning_trades)
        gross_loss = abs(sum(t.net_pnl_usd for t in losing_trades))
        net_profit = gross_profit - gross_loss

        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Calculate max drawdown
        peak = self.config.initial_balance_usd
        max_dd = 0.0
        max_dd_pct = 0.0

        for point in self.equity_curve:
            equity = point["equity"]
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd
                max_dd_pct = (dd / peak) * 100 if peak > 0 else 0.0

        return {
            "trades": self.trades,
            "equity_curve": self.equity_curve,
            "total_trades": total_trades,
            "total_signals": self.total_signals,
            "buy_signals": self.buy_signals,
            "sell_signals": self.sell_signals,
            "hold_signals": self.hold_signals,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "net_profit_usd": net_profit,
            "gross_profit_usd": gross_profit,
            "gross_loss_usd": gross_loss,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown_usd": max_dd,
            "max_drawdown_pct": max_dd_pct,
            "final_balance": self.balance,
            "return_pct": ((self.balance - self.config.initial_balance_usd) / self.config.initial_balance_usd) * 100
        }
