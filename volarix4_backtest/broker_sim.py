"""Broker simulator for realistic trade execution.

Simulates fills, partial TPs, SL/TP exits with costs (spread, slippage, commission).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Literal, List
from enum import Enum


class ExitReason(Enum):
    """Reason for trade exit."""
    TP1 = "TP1"
    TP2 = "TP2"
    TP3 = "TP3"
    SL = "SL"
    MANUAL = "MANUAL"


@dataclass
class Trade:
    """Represents a single trade with partial TP tracking."""

    # Entry details
    direction: Literal["BUY", "SELL"]
    entry_time: datetime
    entry_price: float
    lot_size: float
    confidence: float
    reason: str

    # Risk parameters (from API)
    sl: float
    tp1: float
    tp2: float
    tp3: float
    tp1_percent: float  # Portion to close at TP1 (e.g., 0.5 = 50%)
    tp2_percent: float  # Portion to close at TP2 (e.g., 0.3 = 30%)
    tp3_percent: float  # Portion to close at TP3 (e.g., 0.2 = 20%)

    # Costs (in USD)
    entry_cost_usd: float = 0.0
    exit_cost_usd: float = 0.0
    commission_usd: float = 0.0

    # Position tracking
    remaining_lots: float = field(init=False)
    closed_lots: float = 0.0

    # Exit tracking
    exit_time: Optional[datetime] = None
    exit_reason: Optional[ExitReason] = None
    exit_price: Optional[float] = None

    # Partial exits
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    tp1_exit_time: Optional[datetime] = None
    tp2_exit_time: Optional[datetime] = None
    tp3_exit_time: Optional[datetime] = None

    # P&L
    gross_pnl_usd: float = 0.0
    net_pnl_usd: float = 0.0

    def __post_init__(self):
        """Initialize remaining lots."""
        self.remaining_lots = self.lot_size

    @property
    def is_closed(self) -> bool:
        """Check if trade is fully closed."""
        return self.remaining_lots <= 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for CSV export."""
        return {
            "direction": self.direction,
            "entry_time": self.entry_time,
            "entry_price": self.entry_price,
            "lot_size": self.lot_size,
            "confidence": self.confidence,
            "reason": self.reason,
            "sl": self.sl,
            "tp1": self.tp1,
            "tp2": self.tp2,
            "tp3": self.tp3,
            "tp1_percent": self.tp1_percent,
            "tp2_percent": self.tp2_percent,
            "tp3_percent": self.tp3_percent,
            "tp1_hit": self.tp1_hit,
            "tp2_hit": self.tp2_hit,
            "tp3_hit": self.tp3_hit,
            "tp1_exit_time": self.tp1_exit_time,
            "tp2_exit_time": self.tp2_exit_time,
            "tp3_exit_time": self.tp3_exit_time,
            "exit_time": self.exit_time,
            "exit_reason": self.exit_reason.value if self.exit_reason else None,
            "exit_price": self.exit_price,
            "gross_pnl_usd": self.gross_pnl_usd,
            "net_pnl_usd": self.net_pnl_usd,
            "entry_cost_usd": self.entry_cost_usd,
            "exit_cost_usd": self.exit_cost_usd,
            "commission_usd": self.commission_usd
        }


class BrokerSimulator:
    """Simulates realistic broker execution with costs and partial TPs."""

    def __init__(
        self,
        spread_pips: float,
        slippage_pips: float,
        commission_per_side_per_lot: float,
        usd_per_pip_per_lot: float,
        pip_value: float = 0.0001
    ):
        """Initialize broker simulator.

        Args:
            spread_pips: Spread cost in pips
            slippage_pips: Slippage per execution in pips
            commission_per_side_per_lot: Commission per side per lot in USD
            usd_per_pip_per_lot: USD value per pip per lot
            pip_value: Pip value for the symbol (default 0.0001 for EURUSD)
        """
        self.spread_pips = spread_pips
        self.slippage_pips = slippage_pips
        self.commission_per_side_per_lot = commission_per_side_per_lot
        self.usd_per_pip_per_lot = usd_per_pip_per_lot
        self.pip_value = pip_value

    def open_trade(
        self,
        direction: Literal["BUY", "SELL"],
        entry_time: datetime,
        entry_price: float,
        lot_size: float,
        sl: float,
        tp1: float,
        tp2: float,
        tp3: float,
        tp1_percent: float,
        tp2_percent: float,
        tp3_percent: float,
        confidence: float,
        reason: str
    ) -> Trade:
        """Open a new trade with cost simulation.

        Args:
            direction: "BUY" or "SELL"
            entry_time: Entry timestamp
            entry_price: Intended entry price (before costs)
            lot_size: Position size in lots
            sl: Stop loss price
            tp1, tp2, tp3: Take profit levels
            tp1_percent, tp2_percent, tp3_percent: Portion to close at each TP
            confidence: Signal confidence
            reason: Signal reason

        Returns:
            Trade object with costs applied
        """
        # Calculate entry costs
        entry_cost_pips = self.spread_pips + self.slippage_pips
        entry_cost_usd = entry_cost_pips * lot_size * self.usd_per_pip_per_lot

        # Calculate commission (entry side only)
        commission_entry = self.commission_per_side_per_lot * lot_size

        # Apply slippage to entry price
        if direction == "BUY":
            actual_entry = entry_price + (self.slippage_pips * self.pip_value)
        else:  # SELL
            actual_entry = entry_price - (self.slippage_pips * self.pip_value)

        trade = Trade(
            direction=direction,
            entry_time=entry_time,
            entry_price=actual_entry,
            lot_size=lot_size,
            confidence=confidence,
            reason=reason,
            sl=sl,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            tp1_percent=tp1_percent,
            tp2_percent=tp2_percent,
            tp3_percent=tp3_percent,
            entry_cost_usd=entry_cost_usd,
            commission_usd=commission_entry  # Will add exit commission on close
        )

        return trade

    def update_trade(
        self,
        trade: Trade,
        current_time: datetime,
        current_high: float,
        current_low: float,
        current_close: float
    ) -> bool:
        """Update trade state based on current bar.

        Checks for SL/TP hits and updates P&L. Processes in order: SL first, then TP3, TP2, TP1.

        Args:
            trade: Trade to update
            current_time: Current bar timestamp
            current_high: Current bar high
            current_low: Current bar low
            current_close: Current bar close

        Returns:
            True if trade was closed (fully or partially), False otherwise
        """
        if trade.is_closed:
            return False

        trade_updated = False

        if trade.direction == "BUY":
            # Check SL first (high priority)
            if current_low <= trade.sl:
                self._close_trade(trade, current_time, trade.sl, ExitReason.SL)
                return True

            # Check TPs (from furthest to nearest)
            if not trade.tp3_hit and current_high >= trade.tp3:
                self._partial_close(trade, current_time, trade.tp3, ExitReason.TP3)
                trade_updated = True

            if not trade.tp2_hit and current_high >= trade.tp2:
                self._partial_close(trade, current_time, trade.tp2, ExitReason.TP2)
                trade_updated = True

            if not trade.tp1_hit and current_high >= trade.tp1:
                self._partial_close(trade, current_time, trade.tp1, ExitReason.TP1)
                trade_updated = True

        else:  # SELL
            # Check SL first (high priority)
            if current_high >= trade.sl:
                self._close_trade(trade, current_time, trade.sl, ExitReason.SL)
                return True

            # Check TPs (from furthest to nearest)
            if not trade.tp3_hit and current_low <= trade.tp3:
                self._partial_close(trade, current_time, trade.tp3, ExitReason.TP3)
                trade_updated = True

            if not trade.tp2_hit and current_low <= trade.tp2:
                self._partial_close(trade, current_time, trade.tp2, ExitReason.TP2)
                trade_updated = True

            if not trade.tp1_hit and current_low <= trade.tp1:
                self._partial_close(trade, current_time, trade.tp1, ExitReason.TP1)
                trade_updated = True

        return trade_updated

    def _partial_close(
        self,
        trade: Trade,
        exit_time: datetime,
        exit_price: float,
        exit_reason: ExitReason
    ):
        """Close partial position at TP level.

        Args:
            trade: Trade to partially close
            exit_time: Exit timestamp
            exit_price: Exit price (before slippage)
            exit_reason: Which TP was hit
        """
        # Determine lots to close
        if exit_reason == ExitReason.TP1:
            lots_to_close = trade.lot_size * trade.tp1_percent
            trade.tp1_hit = True
            trade.tp1_exit_time = exit_time
        elif exit_reason == ExitReason.TP2:
            lots_to_close = trade.lot_size * trade.tp2_percent
            trade.tp2_hit = True
            trade.tp2_exit_time = exit_time
        elif exit_reason == ExitReason.TP3:
            lots_to_close = trade.lot_size * trade.tp3_percent
            trade.tp3_hit = True
            trade.tp3_exit_time = exit_time
        else:
            return  # Unknown TP

        # Don't close more than remaining
        lots_to_close = min(lots_to_close, trade.remaining_lots)

        if lots_to_close <= 0:
            return

        # Apply slippage to exit price
        if trade.direction == "BUY":
            actual_exit = exit_price - (self.slippage_pips * self.pip_value)
        else:  # SELL
            actual_exit = exit_price + (self.slippage_pips * self.pip_value)

        # Calculate P&L for this partial close
        if trade.direction == "BUY":
            pips = (actual_exit - trade.entry_price) / self.pip_value
        else:  # SELL
            pips = (trade.entry_price - actual_exit) / self.pip_value

        gross_pnl = pips * lots_to_close * self.usd_per_pip_per_lot

        # Calculate exit costs for this portion
        exit_cost_usd = self.slippage_pips * lots_to_close * self.usd_per_pip_per_lot
        commission_exit = self.commission_per_side_per_lot * lots_to_close

        net_pnl = gross_pnl - exit_cost_usd - commission_exit

        # Update trade
        trade.remaining_lots -= lots_to_close
        trade.closed_lots += lots_to_close
        trade.gross_pnl_usd += gross_pnl
        trade.exit_cost_usd += exit_cost_usd
        trade.commission_usd += commission_exit
        trade.net_pnl_usd += net_pnl

        # If fully closed, mark as closed
        if trade.remaining_lots <= 0.0:
            trade.exit_time = exit_time
            trade.exit_reason = exit_reason
            trade.exit_price = actual_exit
            trade.remaining_lots = 0.0

    def _close_trade(
        self,
        trade: Trade,
        exit_time: datetime,
        exit_price: float,
        exit_reason: ExitReason
    ):
        """Close entire remaining position (usually SL).

        Args:
            trade: Trade to close
            exit_time: Exit timestamp
            exit_price: Exit price (before slippage)
            exit_reason: Exit reason (usually SL)
        """
        if trade.remaining_lots <= 0:
            return

        # Apply slippage to exit price
        if trade.direction == "BUY":
            actual_exit = exit_price - (self.slippage_pips * self.pip_value)
        else:  # SELL
            actual_exit = exit_price + (self.slippage_pips * self.pip_value)

        # Calculate P&L for remaining position
        if trade.direction == "BUY":
            pips = (actual_exit - trade.entry_price) / self.pip_value
        else:  # SELL
            pips = (trade.entry_price - actual_exit) / self.pip_value

        gross_pnl = pips * trade.remaining_lots * self.usd_per_pip_per_lot

        # Calculate exit costs
        exit_cost_usd = self.slippage_pips * trade.remaining_lots * self.usd_per_pip_per_lot
        commission_exit = self.commission_per_side_per_lot * trade.remaining_lots

        net_pnl = gross_pnl - exit_cost_usd - commission_exit

        # Update trade
        trade.closed_lots += trade.remaining_lots
        trade.remaining_lots = 0.0
        trade.gross_pnl_usd += gross_pnl
        trade.exit_cost_usd += exit_cost_usd
        trade.commission_usd += commission_exit
        trade.net_pnl_usd += net_pnl
        trade.exit_time = exit_time
        trade.exit_reason = exit_reason
        trade.exit_price = actual_exit
