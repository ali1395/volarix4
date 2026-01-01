"""Backtest broker - Position and order management

Handles position lifecycle, SL/TP checking, and order execution.
Mimics MT5 broker behavior: checks SL/TP on every tick independently
of EA callbacks.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest import Trade, apply_exit_costs, commission_usd_to_pips
from .tick_generator import Tick
from .config import ExitSemantics, TPModel, get_tp_allocations


@dataclass
class Position:
    """Represents an open trading position

    Tracks a single position through its lifecycle, including partial TP exits.

    Attributes:
        position_id: Unique identifier for this position
        trade: The Trade object containing all position details
        remaining_volume: Fraction of position still open (0.0 to 1.0)
        tp_levels_hit: List of TP levels that have been hit ([1, 2, 3])
    """
    position_id: int
    trade: Trade
    remaining_volume: float = 1.0
    tp_levels_hit: List[int] = field(default_factory=list)

    def is_fully_closed(self) -> bool:
        """Check if position is completely closed

        Returns:
            True if all TPs hit or position manually closed
        """
        return self.remaining_volume <= 0.0 or len(self.tp_levels_hit) >= 3


@dataclass
class PendingOrder:
    """Order waiting for execution (implements 1-bar entry delay)

    In MT5 and this backtest, there's a 1-bar delay between signal generation
    and order execution:
    - Signal detected on bar i (at close)
    - Order placed, pending
    - Order executes on bar i+1 (at open)

    Attributes:
        order_id: Unique identifier for this order
        direction: 'BUY' or 'SELL'
        signal_data: Dict containing rejection, trade_params, confidence, etc.
        signal_bar_time: Timestamp when signal was generated
        entry_bar_index: Bar index where entry should execute (signal_bar + 1)
    """
    order_id: int
    direction: str
    signal_data: Dict
    signal_bar_time: datetime
    entry_bar_index: int


@dataclass
class BrokerState:
    """Encapsulated broker state

    All broker state is contained in this class for:
    - Easy serialization/checkpointing
    - Thread-safe multi-backtest execution
    - Clear state ownership
    """
    open_positions: Dict[int, Position] = field(default_factory=dict)
    pending_orders: List[PendingOrder] = field(default_factory=list)
    closed_trades: List[Trade] = field(default_factory=list)
    next_position_id: int = 1
    next_order_id: int = 1


class BacktestBroker:
    """Backtest broker - manages positions and executes orders

    Core responsibilities:
    1. Check SL/TP on EVERY tick (broker-side, independent of EA)
    2. Execute pending orders when entry bar arrives
    3. Track multiple concurrent positions
    4. Calculate P&L with realistic costs

    Key difference from bar-based backtest:
    - SL/TP checked on every tick, not once per bar
    - Multiple positions supported (not just single open_trade)
    - Partial TP exits tracked per position
    """

    def __init__(self, pip_value: float, spread_pips: float,
                 slippage_pips: float, commission_per_side_per_lot: float,
                 lot_size: float, usd_per_pip_per_lot: float,
                 exit_semantics: ExitSemantics = ExitSemantics.OHLC_INTRABAR,
                 tp_model: TPModel = TPModel.FULL_CLOSE_AT_FIRST_TP):
        """Initialize broker with cost parameters and configuration

        Args:
            pip_value: Pip value for the symbol (e.g., 0.0001 for EURUSD)
            spread_pips: Spread in pips
            slippage_pips: Slippage in pips
            commission_per_side_per_lot: Commission per lot per side (USD)
            lot_size: Standard lot size for trades
            usd_per_pip_per_lot: USD value per pip per lot
            exit_semantics: How to evaluate SL/TP (OPEN_ONLY or OHLC_INTRABAR)
            tp_model: TP allocation model (FULL_CLOSE_AT_FIRST_TP or PARTIAL_TPS)
        """
        self.state = BrokerState()

        # Cost parameters
        self.pip_value = pip_value
        self.spread_pips = spread_pips
        self.slippage_pips = slippage_pips
        self.commission_per_side_per_lot = commission_per_side_per_lot
        self.lot_size = lot_size
        self.usd_per_pip_per_lot = usd_per_pip_per_lot

        # Configuration
        self.exit_semantics = exit_semantics
        self.tp_model = tp_model
        self.TP_ALLOCATIONS = get_tp_allocations(tp_model)

    def on_tick(self, tick: Tick) -> None:
        """Called on EVERY tick to check SL/TP

        This is the key broker-side mechanic: SL and TP are checked
        independently of EA callbacks, on every price update.

        Args:
            tick: Current tick data
        """
        # Check all open positions for SL/TP hits
        positions_to_close = []

        for pos_id, position in list(self.state.open_positions.items()):
            if self._check_sl_tp_on_tick(position, tick):
                # Position state changed (hit SL or TP)
                if position.is_fully_closed():
                    # Position completely closed - move to closed trades
                    positions_to_close.append(pos_id)
                    # Transfer TP tracking to Trade object for statistics
                    position.trade.tp_levels_hit = position.tp_levels_hit
                    self.state.closed_trades.append(position.trade)

        # Remove fully closed positions
        for pos_id in positions_to_close:
            del self.state.open_positions[pos_id]

    def _check_sl_tp_on_tick(self, position: Position, tick: Tick) -> bool:
        """Check if tick price hits SL or TP levels

        Behavior depends on exit_semantics configuration:

        OPEN_ONLY mode (true MT5 "Open prices only"):
        - Uses only tick.bid/ask (bar open price)
        - Called on EVERY tick (once per bar)
        - Trade cannot exit on same bar as entry (unless immediate at open)

        OHLC_INTRABAR mode (legacy hybrid):
        - Uses bar high/low for exit checks
        - Allows same-bar entry and exit
        - Matches legacy bar-based backtest behavior

        Args:
            position: Position to check
            tick: Current tick

        Returns:
            True if position state changed (SL/TP hit)
        """
        trade = position.trade

        if self.exit_semantics == ExitSemantics.OPEN_ONLY:
            # True MT5 "Open prices only" mode
            # Use only tick.bid/ask (bar open price)
            price = tick.bid if trade.direction == "BUY" else tick.ask

            if trade.direction == "BUY":
                # Check SL first (priority)
                if price <= trade.sl:
                    self._close_position_sl(position, tick, price)
                    return True

                # Check TP levels (highest to lowest)
                if price >= trade.tp3 and 3 not in position.tp_levels_hit:
                    self._close_partial_tp(position, tick, 3, trade.tp3)
                    return True
                elif price >= trade.tp2 and 2 not in position.tp_levels_hit:
                    self._close_partial_tp(position, tick, 2, trade.tp2)
                    return True
                elif price >= trade.tp1 and 1 not in position.tp_levels_hit:
                    self._close_partial_tp(position, tick, 1, trade.tp1)
                    return True

            else:  # SELL
                # Check SL first
                if price >= trade.sl:
                    self._close_position_sl(position, tick, price)
                    return True

                # Check TP levels (highest to lowest)
                if price <= trade.tp3 and 3 not in position.tp_levels_hit:
                    self._close_partial_tp(position, tick, 3, trade.tp3)
                    return True
                elif price <= trade.tp2 and 2 not in position.tp_levels_hit:
                    self._close_partial_tp(position, tick, 2, trade.tp2)
                    return True
                elif price <= trade.tp1 and 1 not in position.tp_levels_hit:
                    self._close_partial_tp(position, tick, 1, trade.tp1)
                    return True

        elif self.exit_semantics == ExitSemantics.OHLC_INTRABAR:
            # Legacy hybrid mode - check bar high/low for exits
            # This allows same-bar entry and exit
            bar_data = tick.bar_data

            if trade.direction == "BUY":
                # Check SL first (priority) - use bar LOW
                if bar_data['low'] <= trade.sl:
                    # Close at SL price (assuming hit)
                    self._close_position_sl(position, tick, trade.sl)
                    return True

                # Check TP levels using bar HIGH (highest to lowest)
                if bar_data['high'] >= trade.tp3 and 3 not in position.tp_levels_hit:
                    self._close_partial_tp(position, tick, 3, trade.tp3)
                    return True
                elif bar_data['high'] >= trade.tp2 and 2 not in position.tp_levels_hit:
                    self._close_partial_tp(position, tick, 2, trade.tp2)
                    return True
                elif bar_data['high'] >= trade.tp1 and 1 not in position.tp_levels_hit:
                    self._close_partial_tp(position, tick, 1, trade.tp1)
                    return True

            else:  # SELL
                # Check SL first - use bar HIGH
                if bar_data['high'] >= trade.sl:
                    self._close_position_sl(position, tick, trade.sl)
                    return True

                # Check TP levels using bar LOW (highest to lowest)
                if bar_data['low'] <= trade.tp3 and 3 not in position.tp_levels_hit:
                    self._close_partial_tp(position, tick, 3, trade.tp3)
                    return True
                elif bar_data['low'] <= trade.tp2 and 2 not in position.tp_levels_hit:
                    self._close_partial_tp(position, tick, 2, trade.tp2)
                    return True
                elif bar_data['low'] <= trade.tp1 and 1 not in position.tp_levels_hit:
                    self._close_partial_tp(position, tick, 1, trade.tp1)
                    return True

        return False

    def _close_position_sl(self, position: Position, tick: Tick, price: float) -> None:
        """Close position at stop loss

        Reuses existing logic from check_trade_outcome() for SL closure.

        Args:
            position: Position to close
            tick: Current tick
            price: Price at which SL was hit
        """
        trade = position.trade
        trade.status = "loss"
        trade.exit_time = tick.timestamp
        trade.exit_bar_time = tick.timestamp

        # Apply exit costs (reuse existing function)
        exit_price_after_costs = apply_exit_costs(trade, price)
        trade.exit_price = exit_price_after_costs

        # Calculate PnL in pips
        if trade.direction == "BUY":
            trade.pnl_pips = (exit_price_after_costs - trade.entry) / trade.pip_value
        else:  # SELL
            trade.pnl_pips = (trade.entry - exit_price_after_costs) / trade.pip_value

        # Calculate PnL in R multiples
        if trade.direction == "BUY":
            r_pips = (trade.entry - trade.sl) / trade.pip_value
        else:
            r_pips = (trade.sl - trade.entry) / trade.pip_value

        trade.pnl = trade.pnl_pips / r_pips if r_pips > 0 else 0

        # Calculate commission
        # SL hit = 1 exit
        exit_commission_usd = trade.commission_per_side_per_lot * trade.lot_size
        total_commission_usd = trade.entry_commission + exit_commission_usd
        total_commission_pips = commission_usd_to_pips(total_commission_usd, self.usd_per_pip_per_lot)

        trade.pnl_after_costs = trade.pnl_pips - total_commission_pips
        trade.exit_reason = "SL hit"

        # Mark position as fully closed
        position.remaining_volume = 0.0

    def _close_partial_tp(self, position: Position, tick: Tick,
                          tp_level: int, tp_price: float) -> None:
        """Close partial position at take profit level

        TP allocation (matching current backtest):
        - TP1: 50% of position
        - TP2: 30% of position
        - TP3: 20% of position

        Args:
            position: Position to partially close
            tick: Current tick
            tp_level: Which TP level hit (1, 2, or 3)
            tp_price: Price of the TP level
        """
        # Mark TP as hit
        position.tp_levels_hit.append(tp_level)
        position.remaining_volume -= self.TP_ALLOCATIONS[tp_level]

        trade = position.trade

        # Update exit info
        if position.is_fully_closed():
            # All TPs hit or position closed - calculate final PnL
            trade.status = "win"
            trade.exit_time = tick.timestamp
            trade.exit_bar_time = tick.timestamp

            # Calculate weighted PnL (reuses existing logic)
            self._calculate_weighted_pnl(position, tick)

    def _calculate_weighted_pnl(self, position: Position, tick: Tick) -> None:
        """Calculate weighted PnL for positions with multiple TP exits

        Matches existing logic from check_trade_outcome() for weighted PnL
        calculation when multiple TPs are hit.

        Args:
            position: Position to calculate PnL for
            tick: Current tick (for exit price application)
        """
        trade = position.trade
        tp_levels_hit = sorted(position.tp_levels_hit)

        # Apply exit costs to highest TP hit
        highest_tp = max(tp_levels_hit)
        if highest_tp == 1:
            exit_price_after_costs = apply_exit_costs(trade, trade.tp1)
        elif highest_tp == 2:
            exit_price_after_costs = apply_exit_costs(trade, trade.tp2)
        else:  # highest_tp == 3
            exit_price_after_costs = apply_exit_costs(trade, trade.tp3)

        trade.exit_price = exit_price_after_costs

        # Calculate R (risk in pips)
        if trade.direction == "BUY":
            r_pips = (trade.entry - trade.sl) / trade.pip_value
        else:
            r_pips = (trade.sl - trade.entry) / trade.pip_value

        # Calculate pips for each TP
        if trade.direction == "BUY":
            tp1_pips = (trade.tp1 - trade.entry) / trade.pip_value
            tp2_pips = (trade.tp2 - trade.entry) / trade.pip_value
            tp3_pips = (trade.tp3 - trade.entry) / trade.pip_value
        else:
            tp1_pips = (trade.entry - trade.tp1) / trade.pip_value
            tp2_pips = (trade.entry - trade.tp2) / trade.pip_value
            tp3_pips = (trade.entry - trade.tp3) / trade.pip_value

        # Calculate weighted PnL based on which TPs were hit
        if highest_tp == 3:
            # All 3 TPs hit
            weighted_pips = 0.5 * tp1_pips + 0.3 * tp2_pips + 0.2 * tp3_pips
            num_exits = 3
            trade.exit_reason = "All TPs hit"
        elif highest_tp == 2:
            # TP1 and TP2 hit
            weighted_pips = 0.5 * tp1_pips + 0.3 * tp2_pips
            num_exits = 2
            trade.exit_reason = "TP1 + TP2 hit"
        else:  # highest_tp == 1
            # TP1 only
            weighted_pips = 0.5 * tp1_pips
            num_exits = 1
            trade.exit_reason = "TP1 hit"

        trade.pnl_pips = weighted_pips
        trade.pnl = weighted_pips / r_pips if r_pips > 0 else 0

        # Calculate commission (entry + variable exits based on TPs hit)
        exit_commission_usd = num_exits * trade.commission_per_side_per_lot * trade.lot_size
        total_commission_usd = trade.entry_commission + exit_commission_usd
        total_commission_pips = commission_usd_to_pips(total_commission_usd, self.usd_per_pip_per_lot)

        trade.pnl_after_costs = trade.pnl_pips - total_commission_pips

    def place_order(self, signal_data: Dict, signal_bar_index: int,
                   signal_bar_time: datetime) -> int:
        """Place pending order for immediate execution

        MT5 "Open prices only" behavior:
        - Tick arrives for bar i
        - EA analyzes bar i-1 (closed), places order
        - Order executes IMMEDIATELY on bar i (current tick)
        - NO 1-bar delay!

        Args:
            signal_data: Dict containing rejection, trade_params, confidence, etc.
            signal_bar_index: Bar index to execute order on
            signal_bar_time: Timestamp when signal was generated

        Returns:
            order_id: Unique identifier for this order
        """
        order = PendingOrder(
            order_id=self.state.next_order_id,
            direction=signal_data['direction'],
            signal_data=signal_data,
            signal_bar_time=signal_bar_time,
            entry_bar_index=signal_bar_index  # Execute on specified bar (NO +1)
        )

        self.state.pending_orders.append(order)
        self.state.next_order_id += 1

        return order.order_id

    def execute_pending_orders(self, tick: Tick) -> List[Position]:
        """Execute pending orders when their entry bar arrives

        Called on bar open ticks to check if any pending orders should execute.

        Args:
            tick: Current tick (must have is_bar_open=True)

        Returns:
            List of newly opened positions
        """
        new_positions = []
        orders_to_remove = []

        for order in self.state.pending_orders:
            if tick.bar_index == order.entry_bar_index and tick.is_bar_open:
                # Execute order at bar open price (tick.bid)
                position = self._execute_order(order, tick)
                new_positions.append(position)
                orders_to_remove.append(order)

        # Remove executed orders
        for order in orders_to_remove:
            self.state.pending_orders.remove(order)

        return new_positions

    def _execute_order(self, order: PendingOrder, tick: Tick) -> Position:
        """Execute order and create position

        Reuses existing Trade class creation logic.

        Args:
            order: Pending order to execute
            tick: Tick at which to execute (bar open)

        Returns:
            Newly created Position
        """
        signal_data = order.signal_data

        # Create Trade object (reuse existing Trade class)
        trade = Trade(
            entry_time=tick.timestamp,
            direction=order.direction,
            entry=tick.bid,  # Entry at tick price (bar open)
            sl=signal_data['trade_params']['sl'],
            tp1=signal_data['trade_params']['tp1'],
            tp2=signal_data['trade_params']['tp2'],
            tp3=signal_data['trade_params']['tp3'],
            pip_value=self.pip_value,
            spread_pips=self.spread_pips,
            slippage_pips=self.slippage_pips,
            commission_per_side_per_lot=self.commission_per_side_per_lot,
            lot_size=self.lot_size
        )

        # Populate trade context (reuse existing pattern)
        rejection = signal_data['rejection']
        trade.rejection_confidence = signal_data.get('confidence')
        trade.level_price = rejection['level']
        trade.level_type = rejection.get('level_type', 'unknown')

        # Calculate SL/TP distances
        if trade.direction == "BUY":
            trade.sl_pips = (trade.entry - trade.sl) / self.pip_value
            trade.tp1_pips = (trade.tp1 - trade.entry) / self.pip_value
        else:
            trade.sl_pips = (trade.sl - trade.entry) / self.pip_value
            trade.tp1_pips = (trade.entry - trade.tp1) / self.pip_value

        # Add time metadata
        trade.hour_of_day = tick.timestamp.hour
        trade.day_of_week = tick.timestamp.weekday()

        # ATR (if available in signal_data)
        if 'atr_pips' in signal_data:
            trade.atr_pips_14 = signal_data['atr_pips']

        # Create position
        position = Position(
            position_id=self.state.next_position_id,
            trade=trade,
            remaining_volume=1.0,
            tp_levels_hit=[]
        )

        self.state.open_positions[position.position_id] = position
        self.state.next_position_id += 1

        return position

    def get_position_count(self) -> int:
        """Get count of open positions

        Returns:
            Number of currently open positions
        """
        return len(self.state.open_positions)

    def get_closed_trades(self) -> List[Trade]:
        """Get all closed trades

        Returns:
            List of all closed Trade objects (for statistics calculation)
        """
        return self.state.closed_trades
