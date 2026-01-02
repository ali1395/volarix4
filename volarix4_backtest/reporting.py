"""Results reporting and CSV export.

Provides functions to export backtest results, trades, and equity curve.
"""

from pathlib import Path
from typing import List, Dict
import pandas as pd
import logging


class BacktestReporter:
    """Generates reports and exports backtest results."""

    def __init__(self, output_dir: str = "./backtest_results", logger: logging.Logger = None):
        """Initialize reporter.

        Args:
            output_dir: Directory to save reports
            logger: Optional logger
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger or logging.getLogger(__name__)

    def save_results(
        self,
        results: dict,
        symbol: str,
        timeframe: str,
        save_trades: bool = True,
        save_equity: bool = True
    ) -> Dict[str, Path]:
        """Save backtest results to files.

        Args:
            results: Results dictionary from BacktestEngine
            symbol: Trading symbol
            timeframe: Timeframe
            save_trades: Whether to save trades CSV
            save_equity: Whether to save equity curve CSV

        Returns:
            Dictionary mapping file type to file path
        """
        saved_files = {}

        # Generate timestamp for unique filenames
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = f"{symbol}_{timeframe}_{timestamp}"

        # Save trades CSV
        if save_trades and results["trades"]:
            trades_path = self._save_trades_csv(results["trades"], prefix)
            saved_files["trades"] = trades_path
            self.logger.info(f"Saved trades to: {trades_path}")

        # Save equity curve CSV
        if save_equity and results["equity_curve"]:
            equity_path = self._save_equity_csv(results["equity_curve"], prefix)
            saved_files["equity"] = equity_path
            self.logger.info(f"Saved equity curve to: {equity_path}")

        # Save summary metrics
        summary_path = self._save_summary_txt(results, symbol, timeframe, prefix)
        saved_files["summary"] = summary_path
        self.logger.info(f"Saved summary to: {summary_path}")

        return saved_files

    def _save_trades_csv(self, trades: List, prefix: str) -> Path:
        """Save trades to CSV.

        Args:
            trades: List of Trade objects
            prefix: Filename prefix

        Returns:
            Path to saved CSV file
        """
        trades_data = [trade.to_dict() for trade in trades]
        df = pd.DataFrame(trades_data)

        # Format datetime columns
        datetime_cols = ["entry_time", "exit_time", "tp1_exit_time", "tp2_exit_time", "tp3_exit_time"]
        for col in datetime_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])

        # Sort by entry time
        df = df.sort_values("entry_time")

        # Save to CSV
        filepath = self.output_dir / f"{prefix}_trades.csv"
        df.to_csv(filepath, index=False)

        return filepath

    def _save_equity_csv(self, equity_curve: List[dict], prefix: str) -> Path:
        """Save equity curve to CSV.

        Args:
            equity_curve: List of equity curve points
            prefix: Filename prefix

        Returns:
            Path to saved CSV file
        """
        df = pd.DataFrame(equity_curve)
        df["time"] = pd.to_datetime(df["time"])
        df = df.sort_values("time")

        filepath = self.output_dir / f"{prefix}_equity.csv"
        df.to_csv(filepath, index=False)

        return filepath

    def _save_summary_txt(self, results: dict, symbol: str, timeframe: str, prefix: str) -> Path:
        """Save summary metrics to text file.

        Args:
            results: Results dictionary
            symbol: Trading symbol
            timeframe: Timeframe
            prefix: Filename prefix

        Returns:
            Path to saved text file
        """
        filepath = self.output_dir / f"{prefix}_summary.txt"

        with open(filepath, "w") as f:
            f.write("=" * 70 + "\n")
            f.write("BACKTEST RESULTS SUMMARY\n")
            f.write("=" * 70 + "\n")
            f.write(f"Symbol: {symbol}\n")
            f.write(f"Timeframe: {timeframe}\n")
            f.write(f"\n")

            f.write("SIGNAL STATISTICS\n")
            f.write("-" * 70 + "\n")
            f.write(f"Total Signals Generated: {results['total_signals']}\n")
            f.write(f"  BUY Signals: {results['buy_signals']}\n")
            f.write(f"  SELL Signals: {results['sell_signals']}\n")
            f.write(f"  HOLD Signals: {results['hold_signals']}\n")
            f.write(f"\n")

            f.write("TRADE STATISTICS\n")
            f.write("-" * 70 + "\n")
            f.write(f"Total Trades: {results['total_trades']}\n")
            f.write(f"Winning Trades: {results['winning_trades']}\n")
            f.write(f"Losing Trades: {results['losing_trades']}\n")
            f.write(f"Win Rate: {results['win_rate'] * 100:.2f}%\n")
            f.write(f"\n")

            f.write("PROFIT/LOSS\n")
            f.write("-" * 70 + "\n")
            f.write(f"Net Profit: ${results['net_profit_usd']:,.2f}\n")
            f.write(f"Gross Profit: ${results['gross_profit_usd']:,.2f}\n")
            f.write(f"Gross Loss: ${results['gross_loss_usd']:,.2f}\n")
            f.write(f"Profit Factor: {results['profit_factor']:.2f}\n")
            f.write(f"Return: {results['return_pct']:.2f}%\n")
            f.write(f"\n")

            f.write("RISK METRICS\n")
            f.write("-" * 70 + "\n")
            f.write(f"Max Drawdown: ${results['max_drawdown_usd']:,.2f} ({results['max_drawdown_pct']:.2f}%)\n")
            f.write(f"\n")

            f.write("ACCOUNT BALANCE\n")
            f.write("-" * 70 + "\n")
            f.write(f"Final Balance: ${results['final_balance']:,.2f}\n")
            f.write("=" * 70 + "\n")

        return filepath

    def print_summary(self, results: dict, symbol: str, timeframe: str):
        """Print summary to console.

        Args:
            results: Results dictionary
            symbol: Trading symbol
            timeframe: Timeframe
        """
        print("\n" + "=" * 70)
        print("BACKTEST RESULTS SUMMARY")
        print("=" * 70)
        print(f"Symbol: {symbol}")
        print(f"Timeframe: {timeframe}")
        print()

        print("SIGNAL STATISTICS")
        print("-" * 70)
        print(f"Total Signals Generated: {results['total_signals']}")
        print(f"  BUY Signals: {results['buy_signals']}")
        print(f"  SELL Signals: {results['sell_signals']}")
        print(f"  HOLD Signals: {results['hold_signals']}")
        print()

        print("TRADE STATISTICS")
        print("-" * 70)
        print(f"Total Trades: {results['total_trades']}")
        print(f"Winning Trades: {results['winning_trades']}")
        print(f"Losing Trades: {results['losing_trades']}")
        print(f"Win Rate: {results['win_rate'] * 100:.2f}%")
        print()

        print("PROFIT/LOSS")
        print("-" * 70)
        print(f"Net Profit: ${results['net_profit_usd']:,.2f}")
        print(f"Gross Profit: ${results['gross_profit_usd']:,.2f}")
        print(f"Gross Loss: ${results['gross_loss_usd']:,.2f}")
        print(f"Profit Factor: {results['profit_factor']:.2f}")
        print(f"Return: {results['return_pct']:.2f}%")
        print()

        print("RISK METRICS")
        print("-" * 70)
        print(f"Max Drawdown: ${results['max_drawdown_usd']:,.2f} ({results['max_drawdown_pct']:.2f}%)")
        print()

        print("ACCOUNT BALANCE")
        print("-" * 70)
        print(f"Final Balance: ${results['final_balance']:,.2f}")
        print("=" * 70 + "\n")
