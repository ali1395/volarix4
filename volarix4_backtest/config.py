"""Backtest configuration settings using dataclasses."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class BacktestConfig:
    """Configuration for backtest execution.

    All signal generation is delegated to the API - this config only
    controls backtest simulation parameters (costs, risk, data range).
    """

    # Trading pair and timeframe
    symbol: str = "EURUSD"
    timeframe: str = "H1"

    # Data range
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    bars: Optional[int] = None  # If set, use last N bars instead of date range

    # API configuration
    api_url: str = "http://localhost:8000"
    api_timeout: float = 30.0
    api_max_retries: int = 3
    api_retry_delay: float = 1.0

    # API request mode
    use_optimized_mode: bool = True  # If True, send bar_time; else send full data array
    lookback_bars: int = 400  # Number of bars to send/request for signal generation

    # Backtest parity parameters (passed to API)
    min_confidence: Optional[float] = None
    broken_level_cooldown_hours: Optional[float] = None
    broken_level_break_pips: Optional[float] = None
    min_edge_pips: Optional[float] = None

    # Cost model parameters
    spread_pips: float = 1.5
    slippage_pips: float = 0.5
    commission_per_side_per_lot: float = 3.5
    usd_per_pip_per_lot: float = 10.0
    lot_size: float = 0.01

    # Risk management (backtest simulation only)
    initial_balance_usd: float = 10000.0
    risk_percent_per_trade: float = 1.0  # % of balance to risk per trade

    # Execution settings
    fill_at: str = "next_open"  # When to fill: "next_open" (default) or "signal_close"
    warmup_bars: int = 200  # Minimum bars before first signal request

    # Output settings
    output_dir: str = "./backtest_results"
    save_trades_csv: bool = True
    save_equity_curve: bool = True
    verbose: bool = False

    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.fill_at not in ["next_open", "signal_close"]:
            raise ValueError(f"fill_at must be 'next_open' or 'signal_close', got: {self.fill_at}")

        if self.warmup_bars < self.lookback_bars:
            raise ValueError(f"warmup_bars ({self.warmup_bars}) must be >= lookback_bars ({self.lookback_bars})")

        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValueError(f"start_date must be before end_date")

        if self.bars is not None and self.bars < self.warmup_bars:
            raise ValueError(f"bars ({self.bars}) must be >= warmup_bars ({self.warmup_bars})")


@dataclass
class CostModel:
    """Cost model for trade execution simulation."""

    spread_pips: float
    slippage_pips: float
    commission_per_side_per_lot: float
    usd_per_pip_per_lot: float
    lot_size: float

    def calculate_entry_cost_pips(self) -> float:
        """Calculate entry cost in pips (spread + slippage)."""
        return self.spread_pips + self.slippage_pips

    def calculate_exit_cost_pips(self) -> float:
        """Calculate exit cost in pips (slippage only, no spread on exit)."""
        return self.slippage_pips

    def calculate_commission_usd(self) -> float:
        """Calculate round-trip commission in USD."""
        return 2 * self.commission_per_side_per_lot * self.lot_size

    def calculate_total_cost_pips(self) -> float:
        """Calculate total round-trip cost in pips (spread + 2*slippage + commission)."""
        commission_pips = self.calculate_commission_usd() / self.usd_per_pip_per_lot
        return self.spread_pips + (2 * self.slippage_pips) + commission_pips

    @classmethod
    def from_config(cls, config: BacktestConfig) -> "CostModel":
        """Create CostModel from BacktestConfig."""
        return cls(
            spread_pips=config.spread_pips,
            slippage_pips=config.slippage_pips,
            commission_per_side_per_lot=config.commission_per_side_per_lot,
            usd_per_pip_per_lot=config.usd_per_pip_per_lot,
            lot_size=config.lot_size
        )
