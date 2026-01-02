"""Year-based walk-forward testing engine.

Implements walk-forward validation where each test year is trained on N previous years.
Example: test_years=[2023, 2024, 2025], train_years_lookback=2
  - Test 2023 → Train 2021-2022
  - Test 2024 → Train 2022-2023
  - Test 2025 → Train 2023-2024
"""

from typing import List, Dict, Optional
from datetime import datetime
import logging
import pandas as pd

from .config import BacktestConfig
from .data_source import BarDataSource, Bar
from .api_client import SignalApiClient
from .broker_sim import BrokerSimulator
from .engine import BacktestEngine


class WalkForwardEngine:
    """Year-based walk-forward testing engine.

    For each test year, trains on N previous years and tests on that year.
    """

    def __init__(
        self,
        config: BacktestConfig,
        data_source: BarDataSource,
        api_client: SignalApiClient,
        broker: BrokerSimulator,
        logger: Optional[logging.Logger] = None
    ):
        """Initialize walk-forward engine.

        Args:
            config: Backtest configuration with test_years set
            data_source: Data source for loading bars
            api_client: API client for signals
            broker: Broker simulator
            logger: Optional logger
        """
        self.config = config
        self.data_source = data_source
        self.api_client = api_client
        self.broker = broker
        self.logger = logger or logging.getLogger(__name__)

        if not config.is_year_based():
            raise ValueError("WalkForwardEngine requires test_years to be set in config")

    def run(self) -> Dict:
        """Run walk-forward testing across all test years.

        Returns:
            Dictionary with results for each test year and aggregate metrics
        """
        self.logger.info("=" * 70)
        self.logger.info("YEAR-BASED WALK-FORWARD TESTING")
        self.logger.info("=" * 70)
        self.logger.info(f"Test Years: {self.config.test_years}")
        self.logger.info(f"Train Years Lookback: {self.config.train_years_lookback}")
        self.logger.info("=" * 70)

        # Load all bars
        self.logger.info("Loading all historical bars...")
        all_bars = self.data_source.load()
        self.logger.info(f"Loaded {len(all_bars)} total bars")
        self.logger.info(f"Date range: {all_bars[0].time} to {all_bars[-1].time}")

        # Convert to DataFrame for easier year filtering
        df_all = pd.DataFrame([{
            'time': bar.time,
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
            'volume': bar.volume
        } for bar in all_bars])

        # Run backtest for each test year
        results_by_year = {}

        for test_year in self.config.test_years:
            self.logger.info("\n" + "=" * 70)
            self.logger.info(f"TEST YEAR: {test_year}")
            self.logger.info("=" * 70)

            # Determine train years
            train_start_year = test_year - self.config.train_years_lookback
            train_end_year = test_year - 1

            self.logger.info(f"Training Period: {train_start_year} - {train_end_year}")
            self.logger.info(f"Testing Period: {test_year}")

            # Split data
            train_bars, test_bars = self._split_data_by_year(
                df_all,
                train_start_year,
                train_end_year,
                test_year
            )

            if not train_bars:
                self.logger.warning(f"No training data for {train_start_year}-{train_end_year}, skipping")
                continue

            if not test_bars:
                self.logger.warning(f"No test data for {test_year}, skipping")
                continue

            self.logger.info(f"Train bars: {len(train_bars)} ({train_bars[0].time} to {train_bars[-1].time})")
            self.logger.info(f"Test bars: {len(test_bars)} ({test_bars[0].time} to {test_bars[-1].time})")

            # NOTE: In a true walk-forward, you'd optimize parameters on train_bars here.
            # For now, we just test on test_bars using current config params.
            # If you want parameter optimization, add that logic here.

            # Run backtest on test period
            test_result = self._run_test_period(test_bars, test_year)

            results_by_year[test_year] = test_result

            # Print summary for this year
            self._print_year_summary(test_year, test_result)

        # Compute aggregate metrics across all years
        aggregate_results = self._compute_aggregate_results(results_by_year)

        self.logger.info("\n" + "=" * 70)
        self.logger.info("WALK-FORWARD TESTING COMPLETE")
        self.logger.info("=" * 70)

        return {
            "by_year": results_by_year,
            "aggregate": aggregate_results,
            "config": {
                "test_years": self.config.test_years,
                "train_years_lookback": self.config.train_years_lookback
            }
        }

    def _split_data_by_year(
        self,
        df: pd.DataFrame,
        train_start_year: int,
        train_end_year: int,
        test_year: int
    ) -> tuple[List[Bar], List[Bar]]:
        """Split data into train and test periods by year.

        Args:
            df: DataFrame with all bars
            train_start_year: Start year for training
            train_end_year: End year for training (inclusive)
            test_year: Year for testing

        Returns:
            Tuple of (train_bars, test_bars)
        """
        # Filter train data
        df_train = df[
            (df['time'].dt.year >= train_start_year) &
            (df['time'].dt.year <= train_end_year)
        ].copy()

        # Filter test data
        df_test = df[df['time'].dt.year == test_year].copy()

        # Convert to Bar objects
        train_bars = self._df_to_bars(df_train)
        test_bars = self._df_to_bars(df_test)

        return train_bars, test_bars

    def _df_to_bars(self, df: pd.DataFrame) -> List[Bar]:
        """Convert DataFrame to list of Bar objects."""
        bars = []
        for _, row in df.iterrows():
            bars.append(Bar(
                time=row['time'],
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=int(row['volume'])
            ))
        return bars

    def _run_test_period(self, test_bars: List[Bar], test_year: int) -> Dict:
        """Run backtest on test period.

        Args:
            test_bars: Bars for test period
            test_year: Year being tested

        Returns:
            Backtest results dictionary
        """
        # Create a temporary data source with test bars
        class InMemoryDataSource:
            def __init__(self, bars):
                self._bars = bars

            def load(self, file_path=None):
                return self._bars

        temp_data_source = InMemoryDataSource(test_bars)

        # Create engine and run
        engine = BacktestEngine(
            config=self.config,
            data_source=temp_data_source,
            api_client=self.api_client,
            broker=self.broker,
            logger=self.logger
        )

        results = engine.run()
        results['test_year'] = test_year

        return results

    def _print_year_summary(self, year: int, results: Dict):
        """Print summary for a single test year."""
        self.logger.info("\n" + "-" * 70)
        self.logger.info(f"RESULTS FOR {year}")
        self.logger.info("-" * 70)
        self.logger.info(f"Total Trades: {results['total_trades']}")
        self.logger.info(f"Win Rate: {results['win_rate'] * 100:.2f}%")
        self.logger.info(f"Net Profit: ${results['net_profit_usd']:,.2f}")
        self.logger.info(f"Profit Factor: {results['profit_factor']:.2f}")
        self.logger.info(f"Max Drawdown: {results['max_drawdown_pct']:.2f}%")
        self.logger.info(f"Return: {results['return_pct']:.2f}%")
        self.logger.info("-" * 70)

    def _compute_aggregate_results(self, results_by_year: Dict[int, Dict]) -> Dict:
        """Compute aggregate metrics across all test years.

        Args:
            results_by_year: Results dictionary keyed by year

        Returns:
            Aggregate metrics dictionary
        """
        if not results_by_year:
            return {
                "total_trades": 0,
                "total_years": 0,
                "avg_trades_per_year": 0.0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "aggregate_net_profit": 0.0,
                "aggregate_gross_profit": 0.0,
                "aggregate_gross_loss": 0.0,
                "profit_factor": 0.0,
                "aggregate_return_pct": 0.0,
                "avg_net_profit_per_year": 0.0,
                "years_tested": []
            }

        # Combine all trades
        all_trades = []
        for year_results in results_by_year.values():
            all_trades.extend(year_results['trades'])

        # Compute aggregate metrics
        total_trades = len(all_trades)
        if total_trades == 0:
            return {
                "total_trades": 0,
                "total_years": len(results_by_year),
                "avg_trades_per_year": 0,
                "aggregate_net_profit": 0,
                "aggregate_return_pct": 0
            }

        winning_trades = [t for t in all_trades if t.net_pnl_usd > 0]
        losing_trades = [t for t in all_trades if t.net_pnl_usd < 0]

        gross_profit = sum(t.net_pnl_usd for t in winning_trades)
        gross_loss = abs(sum(t.net_pnl_usd for t in losing_trades))
        net_profit = gross_profit - gross_loss

        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Calculate cumulative return
        initial_balance = self.config.initial_balance_usd
        cumulative_return_pct = (net_profit / initial_balance) * 100

        # Avg metrics per year
        avg_trades_per_year = total_trades / len(results_by_year)
        avg_net_profit_per_year = net_profit / len(results_by_year)

        return {
            "total_trades": total_trades,
            "total_years": len(results_by_year),
            "avg_trades_per_year": avg_trades_per_year,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": win_rate,
            "aggregate_net_profit": net_profit,
            "aggregate_gross_profit": gross_profit,
            "aggregate_gross_loss": gross_loss,
            "profit_factor": profit_factor,
            "aggregate_return_pct": cumulative_return_pct,
            "avg_net_profit_per_year": avg_net_profit_per_year,
            "years_tested": list(results_by_year.keys())
        }
