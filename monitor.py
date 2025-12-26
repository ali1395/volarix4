"""Performance monitoring for Volarix 4"""

import time
from functools import wraps
from typing import Dict, List, Any
from collections import defaultdict
from datetime import datetime, timedelta


class PerformanceMonitor:
    """Track API performance metrics in real-time."""

    def __init__(self):
        self.requests: List[Dict[str, Any]] = []
        self.signal_counts = defaultdict(int)
        self.symbol_counts = defaultdict(int)
        self.start_time = datetime.now()

    def record_request(self, duration: float, signal: str, success: bool,
                       symbol: str, confidence: float = 0.0):
        """
        Record API request metrics.

        Args:
            duration: Request duration in seconds
            signal: Signal type (BUY/SELL/HOLD)
            success: Whether request succeeded
            symbol: Trading symbol
            confidence: Signal confidence (0-1)
        """
        self.requests.append({
            'timestamp': datetime.now(),
            'duration': duration,
            'signal': signal,
            'success': success,
            'symbol': symbol,
            'confidence': confidence
        })
        self.signal_counts[signal] += 1
        self.symbol_counts[symbol] += 1

    def get_stats(self, last_n_minutes: int = None) -> Dict[str, Any]:
        """
        Get performance statistics.

        Args:
            last_n_minutes: Only include requests from last N minutes

        Returns:
            Dict with performance metrics
        """
        requests = self.requests

        if last_n_minutes:
            cutoff = datetime.now() - timedelta(minutes=last_n_minutes)
            requests = [r for r in self.requests if r['timestamp'] >= cutoff]

        if not requests:
            return {
                'total_requests': 0,
                'uptime_seconds': (datetime.now() - self.start_time).total_seconds()
            }

        total = len(requests)
        successful = len([r for r in requests if r['success']])
        durations = [r['duration'] for r in requests]

        # Calculate signal distribution
        signal_dist = defaultdict(int)
        for r in requests:
            signal_dist[r['signal']] += 1

        # Calculate average confidence by signal type
        avg_confidence = {}
        for signal in ['BUY', 'SELL']:
            signal_requests = [r for r in requests if r['signal'] == signal]
            if signal_requests:
                avg_conf = sum([r['confidence'] for r in signal_requests]) / len(signal_requests)
                avg_confidence[signal] = avg_conf

        return {
            'total_requests': total,
            'success_rate': (successful / total) * 100 if total > 0 else 0,
            'avg_response_time_ms': (sum(durations) / len(durations)) * 1000,
            'min_response_time_ms': min(durations) * 1000,
            'max_response_time_ms': max(durations) * 1000,
            'signals': dict(signal_dist),
            'avg_confidence': avg_confidence,
            'top_symbols': dict(sorted(
                self.symbol_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]),
            'uptime_seconds': (datetime.now() - self.start_time).total_seconds(),
            'requests_per_minute': total / ((datetime.now() - self.start_time).total_seconds() / 60) if (
                                                                                                                 datetime.now() - self.start_time).total_seconds() > 0 else 0
        }

    def print_stats(self, last_n_minutes: int = None):
        """
        Print formatted statistics.

        Args:
            last_n_minutes: Only show stats from last N minutes
        """
        stats = self.get_stats(last_n_minutes)

        timeframe = f"Last {last_n_minutes} minutes" if last_n_minutes else "All time"

        print("\n" + "=" * 60)
        print(f"API PERFORMANCE STATS - {timeframe}")
        print("=" * 60)

        uptime_hours = stats['uptime_seconds'] / 3600
        print(f"\n⏱ Uptime: {uptime_hours:.1f} hours")

        if stats['total_requests'] > 0:
            print(f"\n📊 Request Statistics")
            print(f"{'─' * 60}")
            print(f"  Total Requests: {stats['total_requests']}")
            print(f"  Success Rate: {stats['success_rate']:.1f}%")
            print(f"  Requests/Minute: {stats['requests_per_minute']:.2f}")

            print(f"\n⚡ Response Times")
            print(f"{'─' * 60}")
            print(f"  Average: {stats['avg_response_time_ms']:.1f}ms")
            print(f"  Min/Max: {stats['min_response_time_ms']:.1f}ms / {stats['max_response_time_ms']:.1f}ms")

            print(f"\n📈 Signal Distribution")
            print(f"{'─' * 60}")
            for signal, count in stats['signals'].items():
                pct = (count / stats['total_requests']) * 100
                conf_str = ""
                if signal in stats.get('avg_confidence', {}):
                    conf_str = f" (avg conf: {stats['avg_confidence'][signal]:.2f})"
                print(f"  {signal:4s}: {count:4d} ({pct:5.1f}%){conf_str}")

            if stats.get('top_symbols'):
                print(f"\n🔝 Top Symbols")
                print(f"{'─' * 60}")
                for symbol, count in stats['top_symbols'].items():
                    print(f"  {symbol}: {count}")

        else:
            print("\n  No requests recorded yet")

        print("\n" + "=" * 60 + "\n")

    def reset(self):
        """Reset all statistics."""
        self.requests.clear()
        self.signal_counts.clear()
        self.symbol_counts.clear()
        self.start_time = datetime.now()

    def get_recent_requests(self, n: int = 10) -> List[Dict[str, Any]]:
        """
        Get N most recent requests.

        Args:
            n: Number of recent requests to return

        Returns:
            List of recent request dicts
        """
        return self.requests[-n:]


# Global monitor instance
monitor = PerformanceMonitor()


def timed(func):
    """
    Decorator to time function execution and return result with duration.

    Usage:
        @timed
        def my_function():
            ...

        result, duration = my_function()
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start
        return result, duration

    return wrapper


# Test code
if __name__ == "__main__":
    print("Testing monitor.py module...\n")

    # Simulate API requests
    print("1. Simulating API requests...")

    for i in range(20):
        duration = 0.1 + (i % 5) * 0.05  # Varying durations
        signal = ['BUY', 'SELL', 'HOLD'][i % 3]
        success = True
        symbol = ['EURUSD', 'GBPUSD', 'USDJPY'][i % 3]
        confidence = 0.75 if signal != 'HOLD' else 0.0

        monitor.record_request(duration, signal, success, symbol, confidence)

        # Simulate one failure
        if i == 10:
            monitor.record_request(0.5, 'HOLD', False, 'INVALID', 0.0)

    print(f"  Recorded {len(monitor.requests)} requests")

    # Print statistics
    monitor.print_stats()

    # Test timed decorator
    print("\n2. Testing timed decorator...")

    @timed
    def slow_function():
        time.sleep(0.1)
        return "result"

    result, duration = slow_function()
    print(f"  Function returned: {result}")
    print(f"  Duration: {duration * 1000:.1f}ms")

    # Show recent requests
    print("\n3. Recent requests:")
    recent = monitor.get_recent_requests(5)
    for req in recent:
        print(f"  {req['timestamp'].strftime('%H:%M:%S')} | "
              f"{req['signal']:4s} | {req['symbol']:6s} | "
              f"{req['duration'] * 1000:.1f}ms")

    print("\n✓ Monitor testing complete")
