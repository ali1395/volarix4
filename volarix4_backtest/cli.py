"""Command-line interface for running backtests."""

import argparse
from datetime import datetime
from pathlib import Path
import logging

from .config import BacktestConfig
from .data_source import BarDataSource
from .api_client import SignalApiClient
from .broker_sim import BrokerSimulator
from .engine import BacktestEngine
from .walk_forward import WalkForwardEngine
from .reporting import BacktestReporter


def parse_args():
    """Parse command-line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Volarix 4 Backtest - API-based backtesting engine",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Config file (NEW - preferred method)
    parser.add_argument("--config", type=str, help="Path to JSON config file (overrides all other args)")

    # Trading pair and timeframe
    parser.add_argument("--symbol", type=str, default="EURUSD", help="Trading symbol")
    parser.add_argument("--timeframe", type=str, default="H1", help="Timeframe (H1, M15, D1, etc.)")

    # Data source
    parser.add_argument("--source", type=str, default="mt5", choices=["csv", "parquet", "mt5"],
                        help="Data source type")
    parser.add_argument("--file", type=str, help="Path to CSV/Parquet file (required for csv/parquet source)")
    parser.add_argument("--start", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--bars", type=int, help="Number of most recent bars to load (alternative to date range)")

    # API configuration
    parser.add_argument("--api-url", type=str, default="http://localhost:8000", help="API base URL")
    parser.add_argument("--api-timeout", type=float, default=30.0, help="API request timeout (seconds)")
    parser.add_argument("--api-max-retries", type=int, default=3, help="Max API request retries")
    parser.add_argument("--use-legacy-mode", action="store_true",
                        help="Use legacy mode (send full bar data) instead of optimized mode (bar_time)")
    parser.add_argument("--lookback-bars", type=int, default=400,
                        help="Number of lookback bars for signal generation")

    # Backtest parity parameters
    parser.add_argument("--min-confidence", type=float, help="Minimum confidence threshold")
    parser.add_argument("--broken-level-cooldown-hours", type=float,
                        help="Broken level cooldown period (hours)")
    parser.add_argument("--broken-level-break-pips", type=float,
                        help="Broken level break threshold (pips)")
    parser.add_argument("--min-edge-pips", type=float, help="Minimum edge after costs (pips)")

    # Cost model
    parser.add_argument("--spread-pips", type=float, default=1.5, help="Spread cost (pips)")
    parser.add_argument("--slippage-pips", type=float, default=0.5, help="Slippage per execution (pips)")
    parser.add_argument("--commission", type=float, default=3.5,
                        help="Commission per side per lot (USD)")
    parser.add_argument("--usd-per-pip", type=float, default=10.0, help="USD value per pip per lot")
    parser.add_argument("--lot-size", type=float, default=0.01, help="Position size (lots)")

    # Risk management
    parser.add_argument("--initial-balance", type=float, default=10000.0,
                        help="Initial account balance (USD)")
    parser.add_argument("--risk-percent", type=float, default=1.0,
                        help="Risk per trade (% of balance)")

    # Execution settings
    parser.add_argument("--fill-at", type=str, default="next_open", choices=["next_open", "signal_close"],
                        help="When to fill entries: next_open (no peeking) or signal_close")
    parser.add_argument("--warmup-bars", type=int, default=200,
                        help="Minimum bars before first signal request")

    # Output settings
    parser.add_argument("--output-dir", type=str, default="./backtest_results",
                        help="Output directory for results")
    parser.add_argument("--no-save-trades", action="store_true", help="Don't save trades CSV")
    parser.add_argument("--no-save-equity", action="store_true", help="Don't save equity curve CSV")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    return parser.parse_args()


def setup_logging(verbose: bool = False):
    """Setup logging configuration.

    Args:
        verbose: Enable verbose (DEBUG) logging
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )


def main():
    """Main CLI entry point."""
    args = parse_args()

    # Load config from JSON file if provided
    if args.config:
        logger_temp = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO)
        logger_temp.info(f"Loading config from: {args.config}")

        try:
            config = BacktestConfig.from_json(args.config)
        except Exception as e:
            logger_temp.error(f"Failed to load config file: {e}")
            return 1

        # Setup logging based on config
        setup_logging(config.verbose)
        logger = logging.getLogger(__name__)
        logger.info("Config loaded successfully from JSON file")

    else:
        # Legacy CLI args mode
        # Setup logging
        setup_logging(args.verbose)
        logger = logging.getLogger(__name__)

        # Parse dates if provided
        start_date = None
        end_date = None
        if args.start:
            start_date = datetime.strptime(args.start, "%Y-%m-%d")
        if args.end:
            end_date = datetime.strptime(args.end, "%Y-%m-%d")

        # Validate inputs
        if args.source in ["csv", "parquet"] and not args.file:
            logger.error(f"--file is required when using --source={args.source}")
            return 1

        # Create config from CLI args
        config = BacktestConfig(
        symbol=args.symbol,
        timeframe=args.timeframe,
        start_date=start_date,
        end_date=end_date,
        bars=args.bars,
        api_url=args.api_url,
        api_timeout=args.api_timeout,
        api_max_retries=args.api_max_retries,
        use_optimized_mode=not args.use_legacy_mode,
        lookback_bars=args.lookback_bars,
        min_confidence=args.min_confidence,
        broken_level_cooldown_hours=args.broken_level_cooldown_hours,
        broken_level_break_pips=args.broken_level_break_pips,
        min_edge_pips=args.min_edge_pips,
        spread_pips=args.spread_pips,
        slippage_pips=args.slippage_pips,
        commission_per_side_per_lot=args.commission,
        usd_per_pip_per_lot=args.usd_per_pip,
        lot_size=args.lot_size,
        initial_balance_usd=args.initial_balance,
        risk_percent_per_trade=args.risk_percent,
        fill_at=args.fill_at,
        warmup_bars=args.warmup_bars,
        output_dir=args.output_dir,
        save_trades_csv=not args.no_save_trades,
        save_equity_curve=not args.no_save_equity,
        verbose=args.verbose
    )

    # Determine data source settings
    if args.config:
        # Use config settings
        source = "mt5"  # Default for config mode
        file_path = None
        start_date = config.start_date
        end_date = config.end_date
        bars = config.bars
    else:
        # Use CLI args
        source = args.source
        file_path = args.file
        start_date = start_date  # Already parsed above
        end_date = end_date  # Already parsed above
        bars = args.bars

    # Create data source
    data_source = BarDataSource(
        source=source,
        symbol=config.symbol,
        timeframe=config.timeframe,
        start_date=start_date,
        end_date=end_date,
        bars=bars
    )

    # For year-based testing, don't load yet (will be loaded in walk-forward engine)
    if not config.is_year_based():
        # Load data for single-period backtest
        logger.info("Loading data...")
        try:
            data_source.load(file_path=file_path)
        except Exception as e:
            logger.error(f"Failed to load data: {e}")
            return 1

    # Create API client
    api_client = SignalApiClient(
        base_url=config.api_url,
        timeout=config.api_timeout,
        max_retries=config.api_max_retries,
        logger=logger
    )

    # Create broker simulator
    # Calculate pip value based on symbol (simple heuristic)
    pip_value = 0.0001 if "JPY" not in config.symbol else 0.01

    broker = BrokerSimulator(
        spread_pips=config.spread_pips,
        slippage_pips=config.slippage_pips,
        commission_per_side_per_lot=config.commission_per_side_per_lot,
        usd_per_pip_per_lot=config.usd_per_pip_per_lot,
        pip_value=pip_value
    )

    # Determine which engine to use
    if config.is_year_based():
        # Year-based walk-forward testing
        logger.info("Using Year-Based Walk-Forward Engine")
        engine = WalkForwardEngine(
            config=config,
            data_source=data_source,
            api_client=api_client,
            broker=broker,
            logger=logger
        )
    else:
        # Single-period backtest
        logger.info("Using Single-Period Backtest Engine")
        engine = BacktestEngine(
            config=config,
            data_source=data_source,
            api_client=api_client,
            broker=broker,
            logger=logger
        )

    # Run backtest
    try:
        results = engine.run()
    except Exception as e:
        logger.error(f"Backtest failed: {e}", exc_info=True)
        return 1

    # Create reporter and save results
    reporter = BacktestReporter(output_dir=config.output_dir, logger=logger)

    # Save and print results
    if config.is_year_based():
        # Walk-forward results - print aggregate summary
        _print_walk_forward_summary(results, config, logger)

        # Save aggregate results
        # TODO: Implement walk-forward specific reporting
        logger.info(f"Walk-forward results saved to: {config.output_dir}")
    else:
        # Single-period results
        saved_files = reporter.save_results(
            results=results,
            symbol=config.symbol,
            timeframe=config.timeframe,
            save_trades=config.save_trades_csv,
            save_equity=config.save_equity_curve
        )

        # Print summary
        reporter.print_summary(results, config.symbol, config.timeframe)

    # Print API client stats
    api_stats = api_client.get_stats()
    logger.info("=" * 70)
    logger.info("API CLIENT STATISTICS")
    logger.info("=" * 70)
    logger.info(f"Total Requests: {api_stats['total_requests']}")
    logger.info(f"Failed Requests: {api_stats['failed_requests']}")
    logger.info(f"Total Retries: {api_stats['total_retry_count']}")
    logger.info(f"Success Rate: {api_stats['success_rate'] * 100:.2f}%")
    logger.info("=" * 70)

    logger.info("\nBacktest complete!")
    return 0


def _print_walk_forward_summary(results: dict, config: BacktestConfig, logger: logging.Logger):
    """Print walk-forward testing summary."""
    print("\n" + "=" * 70)
    print("WALK-FORWARD TESTING SUMMARY")
    print("=" * 70)
    print(f"Symbol: {config.symbol}")
    print(f"Timeframe: {config.timeframe}")
    print(f"Test Years: {config.test_years}")
    print(f"Train Years Lookback: {config.train_years_lookback}")
    print()

    # Print results by year
    print("RESULTS BY YEAR")
    print("-" * 70)
    for year, year_results in results["by_year"].items():
        print(f"{year}:")
        print(f"  Trades: {year_results['total_trades']}")
        print(f"  Win Rate: {year_results['win_rate'] * 100:.2f}%")
        print(f"  Net Profit: ${year_results['net_profit_usd']:,.2f}")
        print(f"  Return: {year_results['return_pct']:.2f}%")
    print()

    # Print aggregate metrics
    agg = results["aggregate"]
    print("AGGREGATE METRICS (All Years)")
    print("-" * 70)
    print(f"Total Years Tested: {agg['total_years']}")
    print(f"Total Trades: {agg['total_trades']}")
    print(f"Avg Trades/Year: {agg['avg_trades_per_year']:.1f}")
    print(f"Winning Trades: {agg['winning_trades']}")
    print(f"Losing Trades: {agg['losing_trades']}")
    print(f"Win Rate: {agg['win_rate'] * 100:.2f}%")
    print(f"Profit Factor: {agg['profit_factor']:.2f}")
    print()
    print(f"Aggregate Net Profit: ${agg['aggregate_net_profit']:,.2f}")
    print(f"Avg Net Profit/Year: ${agg['avg_net_profit_per_year']:,.2f}")
    print(f"Aggregate Return: {agg['aggregate_return_pct']:.2f}%")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    exit(main())
