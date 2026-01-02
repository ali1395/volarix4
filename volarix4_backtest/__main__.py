"""Entry point for running backtest as a module.

Usage:
    python -m volarix4_backtest --symbol EURUSD --timeframe H1 --start 2023-01-01
"""

from .cli import main

if __name__ == "__main__":
    exit(main())
