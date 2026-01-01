"""Event-driven backtest engine for Volarix 4

This module provides an MT5-like tick-based event loop for backtesting,
replacing the traditional bar-based iteration with a more realistic
event-driven architecture.

Key Components:
- TickGenerator: Converts OHLC bars to tick streams (various modes)
- BacktestBroker: Manages positions, checks SL/TP on every tick
- Volarix4EA: Expert Advisor with OnInit/OnTick/OnBar callbacks
- BacktestEngine: Main event loop orchestrator
"""

from .tick_generator import TickGenerator, OpenPriceTickGenerator, Tick
from .broker import BacktestBroker, Position, PendingOrder
from .expert_advisor import Volarix4EA
from .engine import BacktestEngine
from .config import ExitSemantics, TPModel, LEGACY_PARITY_CONFIG, MT5_REALISTIC_CONFIG

__all__ = [
    'TickGenerator',
    'OpenPriceTickGenerator',
    'Tick',
    'BacktestBroker',
    'Position',
    'PendingOrder',
    'Volarix4EA',
    'BacktestEngine',
    'ExitSemantics',
    'TPModel',
    'LEGACY_PARITY_CONFIG',
    'MT5_REALISTIC_CONFIG'
]
