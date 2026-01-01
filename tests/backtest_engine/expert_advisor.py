"""Expert Advisor (EA) - Strategy logic with MT5-like interface

Implements Volarix 4 trading strategy with OnInit/OnTick/OnBar callbacks,
mimicking MT5 Expert Advisor structure.

The EA:
- Runs the 9-filter pipeline on each bar
- Places orders through the broker
- Maintains strategy-specific state (broken levels, cooldowns, etc.)
- Is decoupled from position management (broker handles that)
"""

from typing import Optional, Dict, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import core strategy functions
from volarix4.core.data import is_valid_session
from volarix4.core.sr_levels import detect_sr_levels
from volarix4.core.rejection import find_rejection_candle
from volarix4.core.trade_setup import calculate_sl_tp
from volarix4.core.trend_filter import detect_trend, validate_signal_with_trend

# Import backtest utilities
from backtest import levels_sane

from .tick_generator import Tick
from .broker import BacktestBroker


@dataclass
class EAState:
    """Encapsulated EA state

    Replaces scattered state variables from original run_backtest()
    with a clean, self-contained state object.
    """
    broken_levels: Dict[float, tuple] = field(default_factory=dict)  # level -> (time, type)
    last_signal_time: Optional[datetime] = None
    filter_rejections: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    signals_generated: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    last_bar_index: int = -1  # Track bar changes for on_bar() detection


class Volarix4EA:
    """Expert Advisor implementing Volarix 4 strategy

    MT5-like interface:
    - on_init(): Initialize EA state
    - on_tick(): Called on every tick
    - on_bar(): Called when new bar opens

    The EA is responsible for:
    - Running the 9-filter pipeline
    - Generating trading signals
    - Placing orders through the broker
    - Managing strategy-specific state
    """

    def __init__(self, broker: BacktestBroker, config: Dict):
        """Initialize EA with configuration

        Args:
            broker: BacktestBroker instance for order placement
            config: Configuration dict with strategy parameters
        """
        self.broker = broker
        self.config = config
        self.state = EAState()

        # Extract config parameters
        self.pip_value = config['pip_value']
        self.min_confidence = config.get('min_confidence', 0.60)
        self.broken_level_cooldown_hours = config.get('broken_level_cooldown_hours', 48.0)
        self.broken_level_break_pips = config.get('broken_level_break_pips', 15.0)
        self.min_edge_pips = config.get('min_edge_pips', 2.0)
        self.signal_cooldown_hours = config.get('signal_cooldown_hours', 24.0)

        # Filter enable flags
        self.enable_confidence_filter = config.get('enable_confidence_filter', True)
        self.enable_broken_level_filter = config.get('enable_broken_level_filter', True)
        self.enable_session_filter = config.get('enable_session_filter', True)
        self.enable_trend_filter = config.get('enable_trend_filter', True)
        self.enable_signal_cooldown = config.get('enable_signal_cooldown', True)

        # Data access
        self.sr_cache = config.get('sr_cache')  # Pre-computed S/R levels
        self.df = config['df']  # Full DataFrame for historical lookback
        self.lookback_bars = config.get('lookback_bars', 400)

        # Position limits
        self.max_positions = config.get('max_positions', 1)

    def on_init(self) -> bool:
        """Initialize EA

        MT5 equivalent: OnInit()

        Returns:
            True if initialization successful
        """
        return True

    def on_tick(self, tick: Tick) -> None:
        """Called on EVERY tick

        MT5 equivalent: OnTick()

        Responsibilities:
        - Detect new bar (call on_bar if needed)
        - Could implement tick-level logic here (not used in current strategy)

        Args:
            tick: Current tick data
        """
        # Detect new bar
        if tick.bar_index > self.state.last_bar_index:
            self.on_bar(tick)
            self.state.last_bar_index = tick.bar_index

    def on_bar(self, tick: Tick) -> None:
        """Called when new bar opens

        MT5 equivalent: OnBar() or custom bar detection in OnTick()

        Responsibilities:
        - Update broken levels
        - Run filter pipeline
        - Generate signals
        - Place orders through broker

        Args:
            tick: Tick at bar open (current bar i just opened, analyze previous bar i-1)
        """
        # When bar i opens (tick arrives), bar i-1 just closed
        # Analyze bar i-1 and enter on THIS bar i (matching legacy: analyze i, enter i+1)
        # But in event-driven: tick for i+1 → analyze i → enter i+1 (current)
        bar_index = tick.bar_index

        # Skip first bar (no previous bar to analyze)
        if bar_index == 0:
            return

        # Analyze PREVIOUS bar (i-1) which just closed
        signal_bar_index = bar_index - 1
        signal_bar = self.df.iloc[signal_bar_index]

        # Update broken levels
        if self.enable_broken_level_filter:
            self._update_broken_levels(signal_bar, signal_bar_index)

        # Check if we should generate signal
        if self.broker.get_position_count() >= self.max_positions:
            return

        # Run filter pipeline on the closed bar
        signal_data = self._run_filter_pipeline_for_bar(signal_bar_index)

        if signal_data is not None:
            # MT5 "Open prices only" contract:
            # - Tick arrives for bar i opening
            # - Bar i-1 just closed (we analyzed it above)
            # - Order executes on CURRENT bar i (this tick)
            # - NO 1-bar delay! Order placement = order execution
            self.broker.place_order(
                signal_data=signal_data,
                signal_bar_index=bar_index,  # Execute on CURRENT bar (immediately)
                signal_bar_time=signal_bar['time']
            )

            # Update signal cooldown
            if self.enable_signal_cooldown:
                self.state.last_signal_time = signal_bar['time']

    def _run_filter_pipeline_for_bar(self, bar_index: int) -> Optional[Dict]:
        """Run 9-stage filter pipeline for a specific bar

        This method reuses the exact filter logic from run_backtest() lines 889-1084.

        Filters:
        1. Session filter
        2. Trend detection
        3. S/R level detection
        4. Broken level filter (applied in _get_sr_levels)
        5. Rejection search
        6. Confidence filter
        7. Trend alignment
        8. Signal cooldown
        9. Min edge validation

        Args:
            bar_index: Index of bar to analyze (must be a closed bar)

        Returns:
            Dict with signal data if all filters pass, else None
        """
        current_bar = self.df.iloc[bar_index]

        # Get historical data up to current bar
        historical_data = self.df.iloc[:bar_index + 1].copy()

        # FILTER 1: Session Filter
        if self.enable_session_filter:
            if not is_valid_session(current_bar['time']):
                self.state.filter_rejections["session"] += 1
                self.state.signals_generated["HOLD"] += 1
                return None

        # FILTER 2: Trend Filter (detect but don't block yet)
        trend_info = None
        if self.enable_trend_filter:
            trend_info = detect_trend(historical_data, ema_fast=20, ema_slow=50)

        # FILTER 3: S/R Detection
        levels = self._get_sr_levels(bar_index)
        if not levels:
            self.state.filter_rejections["no_sr_levels"] += 1
            self.state.signals_generated["HOLD"] += 1
            return None

        # FILTER 4: Broken level filter (already applied in _get_sr_levels)

        # FILTER 5: Rejection Search
        rejection = find_rejection_candle(
            historical_data.tail(20),
            levels,
            lookback=5,
            pip_value=self.pip_value
        )

        if not rejection:
            self.state.signals_generated["HOLD"] += 1
            return None

        # FILTER 6: Confidence Filter
        confidence = rejection.get('confidence', 1.0)
        direction = rejection['direction']

        if self.enable_confidence_filter:
            if confidence < self.min_confidence:
                self.state.filter_rejections["confidence"] += 1
                self.state.signals_generated["HOLD"] += 1
                return None

        # FILTER 7: Trend Alignment
        if self.enable_trend_filter and trend_info is not None:
            trend_result = validate_signal_with_trend(
                signal_direction=direction,
                trend_info=trend_info
            )

            # High confidence override
            high_confidence_override = (
                confidence > 0.75 and
                rejection.get('level_score', 0) >= 80.0
            )

            if not trend_result['valid'] and not high_confidence_override:
                self.state.filter_rejections["trend_alignment"] += 1
                self.state.signals_generated["HOLD"] += 1
                return None

        # FILTER 8: Signal Cooldown
        if self.enable_signal_cooldown:
            if self.state.last_signal_time is not None:
                time_since_last = current_bar['time'] - self.state.last_signal_time
                if time_since_last < timedelta(hours=self.signal_cooldown_hours):
                    self.state.filter_rejections["signal_cooldown"] += 1
                    self.state.signals_generated["HOLD"] += 1
                    return None

        # Signal passed filters 1-8
        self.state.signals_generated[direction] += 1

        # FILTER 9: Calculate trade setup and validate min edge
        # Note: Entry price will be NEXT bar open (handled by broker)
        # For validation, use current bar close as estimate
        estimated_entry = current_bar['close']

        trade_params = calculate_sl_tp(
            entry=estimated_entry,
            level=rejection['level'],
            direction=direction,
            sl_pips_beyond=10.0,
            pip_value=self.pip_value
        )

        # Sanity check geometry
        if not levels_sane(
            entry=estimated_entry,
            sl=trade_params['sl'],
            tp1=trade_params['tp1'],
            tp2=trade_params['tp2'],
            tp3=trade_params['tp3'],
            direction=direction
        ):
            self.state.filter_rejections["invalid_geometry"] += 1
            self.state.signals_generated["HOLD"] += 1
            return None

        # Check minimum edge
        commission_pips = (
            (2 * self.broker.commission_per_side_per_lot * self.broker.lot_size) /
            self.broker.usd_per_pip_per_lot
        )
        total_cost_pips = (
            self.broker.spread_pips +
            (2 * self.broker.slippage_pips) +
            commission_pips
        )

        if direction == "BUY":
            tp1_distance_pips = (trade_params['tp1'] - estimated_entry) / self.pip_value
        else:
            tp1_distance_pips = (estimated_entry - trade_params['tp1']) / self.pip_value

        if tp1_distance_pips <= total_cost_pips + self.min_edge_pips:
            self.state.filter_rejections["insufficient_edge"] += 1
            self.state.signals_generated["HOLD"] += 1
            return None

        # All filters passed - return signal data
        return {
            'direction': direction,
            'rejection': rejection,
            'trade_params': trade_params,
            'confidence': confidence
        }

    def _get_sr_levels(self, bar_index: int) -> List[Dict]:
        """Get S/R levels for current bar

        Uses pre-computed cache if available, otherwise computes on-the-fly.
        Applies broken level filter.

        Args:
            bar_index: Current bar index

        Returns:
            List of valid S/R level dicts
        """
        # Get base levels from cache
        if self.sr_cache is not None:
            levels = self.sr_cache.get(bar_index, [])
        else:
            # Fallback: compute on-the-fly (slow)
            historical_data = self.df.iloc[:bar_index + 1]
            sr_lookback = min(200, self.lookback_bars)
            levels = detect_sr_levels(
                historical_data.tail(sr_lookback),
                min_score=60.0,
                pip_value=self.pip_value
            )

        # Apply broken level filter
        if self.enable_broken_level_filter and levels:
            levels = self._filter_broken_levels(levels, bar_index)

        return levels

    def _update_broken_levels(self, current_bar, bar_index: int) -> None:
        """Mark levels as broken if price closes beyond them

        A level is considered "broken" if price closes beyond it by
        broken_level_break_pips. Broken levels are then filtered out
        for a cooldown period.

        Args:
            current_bar: Current bar data
            bar_index: Current bar index
        """
        levels = self._get_sr_levels(bar_index)

        for level_dict in levels:
            level_price = round(level_dict['level'], 5)
            level_type = level_dict['type']

            if level_type == 'support':
                # Support broken if close below it
                if current_bar['close'] < (level_price - self.broken_level_break_pips * self.pip_value):
                    self.state.broken_levels[level_price] = (current_bar['time'], level_type)

            elif level_type == 'resistance':
                # Resistance broken if close above it
                if current_bar['close'] > (level_price + self.broken_level_break_pips * self.pip_value):
                    self.state.broken_levels[level_price] = (current_bar['time'], level_type)

    def _filter_broken_levels(self, levels: List[Dict], bar_index: int) -> List[Dict]:
        """Remove levels in cooldown period

        Levels that were recently broken are excluded from trading for
        a cooldown period (default: 48 hours).

        Args:
            levels: List of S/R level dicts
            bar_index: Current bar index

        Returns:
            Filtered list of S/R levels
        """
        current_time = self.df.iloc[bar_index]['time']
        valid_levels = []

        for level_dict in levels:
            level_price = round(level_dict['level'], 5)

            if level_price in self.state.broken_levels:
                break_time, _ = self.state.broken_levels[level_price]
                time_since_break = current_time - break_time

                if time_since_break < timedelta(hours=self.broken_level_cooldown_hours):
                    # Still in cooldown - skip this level
                    continue
                else:
                    # Cooldown expired - remove from broken list
                    del self.state.broken_levels[level_price]

            valid_levels.append(level_dict)

        return valid_levels

    def get_statistics(self) -> Dict:
        """Get EA statistics

        Returns:
            Dict with filter_rejections and signals_generated
        """
        return {
            'filter_rejections': dict(self.state.filter_rejections),
            'signals_generated': dict(self.state.signals_generated)
        }
