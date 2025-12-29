
### Scope
This contract defines the *single* canonical interpretation of “decision bar,” “execution bar,” required bar count, bar ordering, filters, and costs so that `tests/backtest.py` and the MT5→DLL→API pipeline produce the same signals and (when modeled) the same fills/PnL given the same parameters (including `lookback_bars=400`).[2][1]

### Bar data contract
- **Ordering:** Bars sent to the API must be strictly chronological (oldest → newest), and the API must treat the last row as the newest bar.[2]
- **Closed bars only:** The API must receive only fully closed bars for signal evaluation, and the last bar in the request is the **decision bar** (bar \(i\)).[2]
- **Count:** For single-timeframe operation, the request must include exactly `lookback_bars` closed bars (e.g., 400) for the exec timeframe.[2]
- **Data integrity requirement:** The MT5→DLL OHLCV struct must remain exactly 44 bytes with correct packing and timestamp type to avoid nondeterminism from corrupted data.[1]

### Decision & execution semantics
- **Decision time:** A signal is evaluated strictly at **bar \(i\) close**, using OHLCV history up to and including bar \(i\).[2]
- **Execution time:** The trade is executed at **bar \(i+1\) open** (the new-bar moment), not at the close of bar \(i\).[1]
- **Entry price source (choose one and standardize):**
  - **Option A (recommended):** API returns *signal + SL/TP distances/levels* but does **not** claim a fill price, and MT5 executes at market/new-bar open while applying SL/TP from the response.[1]
  - **Option B:** MT5 provides an explicit `execution_price` (new-bar open / current market) to the API, and the API computes SL/TP/risk checks using that explicit execution price.[2]

### Filters & statefulness
- **Filters must match exactly** between backtest and API, including session gating, confidence gating, trend validation, risk validation, broken-level cooldown filtering, and signal cooldown behavior (pass/fail reasons should be comparable).[2]
- **Signal cooldown is stateful:** The API tracks cooldown across calls (“cooldown activated… next signal allowed after …”), so parity requires the backtest to emulate the same per-symbol cooldown state machine over time.[2]
- **Cooldown duration must be parameterized and identical** (logs show runs where the effective cooldown is 4 hours, so the contract must treat it as a configuration value, not a hardcoded assumption).[2]

### Costs & rounding
- **Costs must be parameter-driven** and identical across environments, using the same configured spread/slippage/commission inputs when parity mode is enabled.[3]
- **Deterministic rounding rules:** Any rounding (prices/levels/pips) must be explicitly defined and applied identically in backtest and API before comparisons are made.[3]

