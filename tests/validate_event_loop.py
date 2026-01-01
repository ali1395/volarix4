"""Validation test for event-driven backtest engine

Runs identical backtests using both legacy bar-based and event-driven
architectures, then compares results to ensure parity.

Expected: Both modes should produce IDENTICAL results when using
"open_prices" tick mode.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.backtest import run_backtest


def compare_results(legacy_results, event_results):
    """Compare two backtest results dicts for parity

    Args:
        legacy_results: Results from legacy bar-based backtest
        event_results: Results from event-driven backtest

    Returns:
        (passed: bool, differences: list)
    """
    differences = []

    # Key metrics to compare
    metrics = [
        'total_trades',
        'wins',
        'losses',
        'win_rate',
        'total_pnl_before_costs',
        'total_pnl_after_costs',
        'total_costs',
        'avg_win',
        'avg_loss',
        'expectancy',
        'profit_factor',
        'max_drawdown',
        'tp1_hits',
        'tp2_hits',
        'tp3_hits',
        'sl_hits',
        'buy_trades',
        'sell_trades',
    ]

    for metric in metrics:
        legacy_val = legacy_results.get(metric, 0)
        event_val = event_results.get(metric, 0)

        # For floats, use approximate comparison
        if isinstance(legacy_val, float):
            tolerance = 0.01 if metric != 'profit_factor' else 0.001
            if abs(legacy_val - event_val) > tolerance:
                differences.append(
                    f"{metric}: legacy={legacy_val:.4f}, event={event_val:.4f}, "
                    f"diff={abs(legacy_val - event_val):.4f}"
                )
        else:
            # For ints, exact comparison
            if legacy_val != event_val:
                differences.append(
                    f"{metric}: legacy={legacy_val}, event={event_val}"
                )

    # Trade-by-trade comparison
    legacy_trades = legacy_results.get('trades', [])
    event_trades = event_results.get('trades', [])

    if len(legacy_trades) != len(event_trades):
        differences.append(
            f"Trade count mismatch: legacy={len(legacy_trades)}, "
            f"event={len(event_trades)}"
        )
    else:
        # Compare each trade
        for i, (lt, et) in enumerate(zip(legacy_trades, event_trades)):
            if lt.direction != et.direction:
                differences.append(
                    f"Trade {i}: direction mismatch (legacy={lt.direction}, "
                    f"event={et.direction})"
                )

            if lt.entry_time != et.entry_time:
                differences.append(
                    f"Trade {i}: entry_time mismatch (legacy={lt.entry_time}, "
                    f"event={et.entry_time})"
                )

            if abs(lt.pnl_after_costs - et.pnl_after_costs) > 0.01:
                differences.append(
                    f"Trade {i}: PnL mismatch (legacy={lt.pnl_after_costs:.2f}, "
                    f"event={et.pnl_after_costs:.2f})"
                )

    passed = len(differences) == 0
    return passed, differences


def run_validation(bars=500, verbose=False):
    """Run validation test

    Args:
        bars: Number of bars to test
        verbose: Print detailed output

    Returns:
        True if validation passed
    """
    print("\n" + "="*70)
    print("EVENT-DRIVEN BACKTEST VALIDATION")
    print("="*70)
    print(f"\nTesting with {bars} bars...\n")

    # Test parameters (using defaults for simplicity)
    test_config = {
        'symbol': 'EURUSD',
        'timeframe': 'H1',
        'bars': bars,
        'lookback_bars': 400,
        'verbose': verbose
    }

    # Run legacy backtest
    print("Running LEGACY bar-based backtest...")
    legacy_results = run_backtest(**test_config, use_event_loop=False)

    if 'error' in legacy_results:
        print(f"[FAIL] Legacy backtest failed: {legacy_results['error']}")
        return False

    print(f"[OK] Legacy backtest complete")
    print(f"  Trades: {legacy_results['total_trades']}")
    print(f"  Win Rate: {legacy_results['win_rate']:.2%}")
    print(f"  PnL: ${legacy_results['total_pnl_after_costs']:.2f}\n")

    # Run event-driven backtest
    print("Running EVENT-DRIVEN backtest (open_prices mode)...")
    event_results = run_backtest(
        **test_config,
        use_event_loop=True,
        tick_mode='open_prices'
    )

    if 'error' in event_results:
        print(f"[FAIL] Event-driven backtest failed: {event_results['error']}")
        return False

    print(f"[OK] Event-driven backtest complete")
    print(f"  Trades: {event_results['total_trades']}")
    print(f"  Win Rate: {event_results['win_rate']:.2%}")
    print(f"  PnL: ${event_results['total_pnl_after_costs']:.2f}\n")

    # Compare results
    print("Comparing results...")
    passed, differences = compare_results(legacy_results, event_results)

    if passed:
        print("[OK] VALIDATION PASSED - Results match exactly!")
        print("="*70)
        return True
    else:
        print("[FAIL] VALIDATION FAILED - Differences found:")
        for diff in differences:
            print(f"  - {diff}")
        print("="*70)
        return False


if __name__ == '__main__':
    # Run validation with different bar counts
    test_cases = [
        ('Quick test', 100, False),
        ('Medium test', 500, False),
        ('Full test', 1000, False),
    ]

    all_passed = True

    for name, bars, verbose in test_cases:
        print(f"\n{'='*70}")
        print(f"TEST: {name} ({bars} bars)")
        print(f"{'='*70}")

        try:
            passed = run_validation(bars=bars, verbose=verbose)
            if not passed:
                all_passed = False
                print(f"\n[FAIL] {name} FAILED\n")
            else:
                print(f"\n[OK] {name} PASSED\n")
        except Exception as e:
            print(f"\n[ERROR] {name} ERROR: {e}\n")
            import traceback
            traceback.print_exc()
            all_passed = False

    # Summary
    print("\n" + "="*70)
    print("VALIDATION SUMMARY")
    print("="*70)
    if all_passed:
        print("[OK] ALL TESTS PASSED - Event-driven backtest is production-ready!")
    else:
        print("[FAIL] SOME TESTS FAILED - Review differences above")
    print("="*70)
