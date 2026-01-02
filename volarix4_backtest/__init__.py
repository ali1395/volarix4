"""Volarix 4 Backtest - API-based backtesting engine.

This package provides a clean, OOP-based backtesting framework that:
- Gets ALL signals from the Volarix 4 HTTP API (no direct strategy imports)
- Simulates realistic broker execution with costs and partial TPs
- Produces deterministic results given fixed inputs
- Exports trades, equity curve, and performance metrics

Usage:
    python -m volarix4_backtest --symbol EURUSD --timeframe H1 --start 2023-01-01 --end 2023-12-31

Package structure:
- config: BacktestConfig and CostModel dataclasses
- data_source: BarDataSource for loading historical data
- api_client: SignalApiClient for calling /signal endpoint
- broker_sim: BrokerSimulator for trade execution simulation
- engine: BacktestEngine for backtest orchestration
- reporting: BacktestReporter for results export
- cli: Command-line interface

CRITICAL: This package MUST NOT import any volarix4.core.* modules.
All signal generation is delegated to the HTTP API.
"""

__version__ = "1.0.0"
__author__ = "Volarix Team"

from .config import BacktestConfig, CostModel
from .data_source import BarDataSource, Bar
from .api_client import SignalApiClient, SignalResponse
from .broker_sim import BrokerSimulator, Trade, ExitReason
from .engine import BacktestEngine
from .reporting import BacktestReporter

__all__ = [
    "BacktestConfig",
    "CostModel",
    "BarDataSource",
    "Bar",
    "SignalApiClient",
    "SignalResponse",
    "BrokerSimulator",
    "Trade",
    "ExitReason",
    "BacktestEngine",
    "BacktestReporter"
]
