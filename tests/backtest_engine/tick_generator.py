"""Tick generation strategies for event-driven backtest

Converts OHLC bar data into time-ordered tick streams, mimicking different
MT5 Strategy Tester modeling modes:
- Open prices only: 1 tick per bar (simplest, fastest)
- OHLC: 4 ticks per bar (O→H→L→C)
- 1-minute OHLC: M1 bars synthesized (most realistic)
- Real ticks: Actual tick data replay
"""

from abc import ABC, abstractmethod
from typing import Iterator, Optional
from datetime import datetime
from dataclasses import dataclass
import pandas as pd


@dataclass
class Tick:
    """Single tick data structure

    Represents a price update event in the backtest simulation.

    Attributes:
        timestamp: Exact time of this tick
        bid: Bid price at this tick
        ask: Ask price at this tick
        bar_index: Index of the bar this tick belongs to (0-based)
        bar_data: Full OHLCV data of the parent bar (pd.Series)
        is_bar_open: True if this is the first tick of a new bar
    """
    timestamp: datetime
    bid: float
    ask: float
    bar_index: int
    bar_data: pd.Series
    is_bar_open: bool = False

    def __repr__(self) -> str:
        bar_open_marker = " [BAR_OPEN]" if self.is_bar_open else ""
        return (f"Tick(time={self.timestamp}, bid={self.bid:.5f}, "
                f"ask={self.ask:.5f}, bar={self.bar_index}{bar_open_marker})")


class TickGenerator(ABC):
    """Abstract base class for tick generation strategies

    Subclasses implement different MT5 modeling modes by generating
    different numbers and types of ticks from OHLC bar data.
    """

    def __init__(self, df: pd.DataFrame, pip_value: float):
        """Initialize tick generator

        Args:
            df: DataFrame with OHLC data (columns: time, open, high, low, close)
            pip_value: Pip value for the symbol (e.g., 0.0001 for EURUSD)
        """
        self.df = df
        self.pip_value = pip_value
        self.current_bar_index = 0

    @abstractmethod
    def generate_ticks(self, start_index: int = 0) -> Iterator[Tick]:
        """Generate tick stream from bar data

        Args:
            start_index: Bar index to start from (for lookback handling)

        Yields:
            Tick objects in chronological order
        """
        pass

    @abstractmethod
    def get_tick_mode_name(self) -> str:
        """Return descriptive name of this tick mode

        Returns:
            Human-readable tick mode name (e.g., "Open prices only")
        """
        pass


class OpenPriceTickGenerator(TickGenerator):
    """Generate one tick per bar at open price

    MT5 equivalent: "Open prices only" modeling mode

    This is the simplest and fastest tick mode. It generates exactly one
    tick per bar, placed at the bar's open price and open time. This mode:
    - Has zero intra-bar granularity
    - Assumes all SL/TP are hit exactly at open price if within range
    - Produces identical results to traditional bar-based backtests
    - Runs at maximum speed (minimal tick overhead)

    Use this mode for:
    - Initial validation (should match legacy backtest exactly)
    - Fast parameter optimization
    - Strategies that only need bar-open execution
    """

    def get_tick_mode_name(self) -> str:
        return "Open prices only"

    def generate_ticks(self, start_index: int = 0) -> Iterator[Tick]:
        """Generate one tick per bar at open price

        Args:
            start_index: Bar index to start from

        Yields:
            One Tick per bar, at bar open time and open price

        Example:
            Bar: time=2024-01-01 09:00, O=1.0850, H=1.0860, L=1.0840, C=1.0855
            Tick: time=2024-01-01 09:00, bid=1.0850, ask=1.0850, is_bar_open=True
        """
        for i in range(start_index, len(self.df)):
            bar = self.df.iloc[i]

            # Single tick at bar open price
            # Note: For simplicity, we use open price for both bid and ask
            # In a more sophisticated model, bid/ask could be derived from spread
            tick = Tick(
                timestamp=bar['time'],
                bid=bar['open'],
                ask=bar['open'],
                bar_index=i,
                bar_data=bar,
                is_bar_open=True  # Every tick opens a new bar in this mode
            )

            yield tick


class OHLCTickGenerator(TickGenerator):
    """Generate 4 ticks per bar (Open → High → Low → Close)

    MT5 equivalent: "Every tick based on real ticks" (simplified)

    NOT YET IMPLEMENTED - Placeholder for future enhancement.

    This mode generates 4 ticks per bar:
    1. Open tick (bar open time)
    2. High tick (intra-bar, time estimated)
    3. Low tick (intra-bar, time estimated)
    4. Close tick (bar close time)

    Provides better intra-bar execution modeling than open prices only,
    but still makes assumptions about when high/low occurred within the bar.
    """

    def get_tick_mode_name(self) -> str:
        return "OHLC (4 ticks per bar)"

    def generate_ticks(self, start_index: int = 0) -> Iterator[Tick]:
        raise NotImplementedError(
            "OHLCTickGenerator not yet implemented. "
            "Use OpenPriceTickGenerator for initial version."
        )


class MinuteOHLCTickGenerator(TickGenerator):
    """Generate ticks from 1-minute OHLC bars

    MT5 equivalent: "1 minute OHLC" modeling mode

    NOT YET IMPLEMENTED - Placeholder for future enhancement.

    This mode synthesizes ticks from M1 (1-minute) bar data, providing
    much higher granularity than H1 bars. Requires M1 data to be available.

    Most realistic option short of actual tick data replay.
    """

    def get_tick_mode_name(self) -> str:
        return "1-minute OHLC"

    def generate_ticks(self, start_index: int = 0) -> Iterator[Tick]:
        raise NotImplementedError(
            "MinuteOHLCTickGenerator not yet implemented. "
            "Requires M1 data integration."
        )


class RealTickGenerator(TickGenerator):
    """Replay actual tick data from historical records

    MT5 equivalent: "Every tick" (real ticks) modeling mode

    NOT YET IMPLEMENTED - Placeholder for future enhancement.

    This mode replays actual historical tick data, providing the most
    realistic backtesting possible. Requires tick data files (CSV, database, etc.)
    """

    def get_tick_mode_name(self) -> str:
        return "Real ticks"

    def generate_ticks(self, start_index: int = 0) -> Iterator[Tick]:
        raise NotImplementedError(
            "RealTickGenerator not yet implemented. "
            "Requires tick data source integration."
        )
