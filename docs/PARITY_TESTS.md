# Backtest-API Parity Tests

## Overview

Automated tests that prevent drift between offline backtest and live API by comparing their decision outputs on identical bar windows.

**Critical:** These tests will **FAIL** if anyone changes:
- Bar indexing (forming bar inclusion)
- Session hours (London 3-11 EST, NY 8-22 EST)
- EMA periods (20/50)
- Cost model parameters or formula
- Filter order or logic
- Parameter defaults (min_confidence=0.6, min_edge=4.0, etc.)

---

## Test Structure

### **1. Test Fixtures** (`tests/fixtures/`)

JSON files containing:
- Bar window (OHLCV data)
- Parameters (costs, filters)
- Expected results (signal, entry, SL/TP, rejection reason)

**Available Fixtures:**

| Fixture | Scenario | Expected Signal | Rejection Reason |
|---------|----------|----------------|------------------|
| `trade_accepted_londonny_uptrend.json` | All filters pass | `BUY` | None |
| `rejected_session_outside_londonny.json` | Asian hours | `HOLD` | Outside London/NY session |
| `rejected_confidence_low.json` | Weak rejection (0.55 < 0.60) | `HOLD` | Confidence below threshold |
| `rejected_insufficient_edge.json` | TP1 too close to entry | `HOLD` | Insufficient edge after costs |

### **2. Test File** (`tests/test_backtest_api_parity.py`)

Main test suite with:
- `evaluate_api_logic()` - Simulates API /signal endpoint logic
- `evaluate_backtest_logic()` - Simulates backtest filter pipeline
- Parametrized tests for each fixture
- Parameter/config validation tests

---

## Running Tests

### **Install pytest** (if not already installed)

```bash
pip install pytest
```

### **Run All Parity Tests**

```bash
cd E:\prs\frx_news_root\volarix4
python -m pytest tests/test_backtest_api_parity.py -v
```

**Expected Output:**

```
tests/test_backtest_api_parity.py::test_backtest_api_parity[trade_accepted_londonny_uptrend] PASSED
tests/test_backtest_api_parity.py::test_backtest_api_parity[rejected_session_outside_londonny] PASSED
tests/test_backtest_api_parity.py::test_backtest_api_parity[rejected_confidence_low] PASSED
tests/test_backtest_api_parity.py::test_backtest_api_parity[rejected_insufficient_edge] PASSED
tests/test_backtest_api_parity.py::test_parameter_defaults_match PASSED
tests/test_backtest_api_parity.py::test_session_hours_unchanged PASSED
tests/test_backtest_api_parity.py::test_ema_periods_unchanged PASSED
tests/test_backtest_api_parity.py::test_cost_model_formula_unchanged PASSED

======================= 8 passed in 2.34s =======================
```

### **Run Specific Test**

```bash
python -m pytest tests/test_backtest_api_parity.py::test_backtest_api_parity -v
```

### **Run with Detailed Output**

```bash
python -m pytest tests/test_backtest_api_parity.py -v --tb=long
```

---

## Test Coverage

### **Core Assertions**

Each parity test asserts:

1. ✅ **Decision Bar Time** - Both use same timestamp
2. ✅ **Decision Bar Close** - Both use same close price
3. ✅ **Signal Direction** - BUY/SELL/HOLD match exactly
4. ✅ **Rejection Reason** - Identical rejection messages (if HOLD)
5. ✅ **Confidence** - Match within 0.01 tolerance
6. ✅ **Entry Price** - Match within 0.00001 tolerance
7. ✅ **SL Pips** - Match within 0.1 pip tolerance
8. ✅ **TP1 Distance** - Match within 0.1 pip tolerance
9. ✅ **Total Cost Pips** - Match within 0.1 pip tolerance
10. ✅ **Edge After Costs** - Match within 0.1 pip tolerance

### **Configuration Validation Tests**

Additional tests ensure critical parameters unchanged:

- `test_parameter_defaults_match()` - Validates API `BACKTEST_PARITY_CONFIG` defaults
- `test_session_hours_unchanged()` - Ensures London (3-11) and NY (8-22) hours unchanged
- `test_ema_periods_unchanged()` - Ensures EMA 20/50 periods unchanged
- `test_cost_model_formula_unchanged()` - Validates cost calculation formula

---

## What Tests Catch

### **Example 1: Someone Changes Session Hours**

**Before:**
```python
SESSIONS = {
    "london": (3, 11),
    "ny": (8, 22)
}
```

**After (WRONG):**
```python
SESSIONS = {
    "london": (3, 11),
    "ny": (8, 16)  # Changed to 16:00 cutoff
}
```

**Test Result:**
```
FAILED tests/test_backtest_api_parity.py::test_session_hours_unchanged
AssertionError: NY session hours changed! Expected (8, 22)
```

---

### **Example 2: Someone Changes Cost Model**

**Before:**
```python
total_cost_pips = spread_pips + (2 * slippage_pips) + commission_pips
```

**After (WRONG):**
```python
total_cost_pips = spread_pips + slippage_pips + commission_pips  # Missing 2x multiplier
```

**Test Result:**
```
FAILED tests/test_backtest_api_parity.py::test_cost_model_formula_unchanged
AssertionError: Total cost calculation changed! Expected 3.4, got 2.4
```

---

### **Example 3: Someone Changes Min Confidence Default**

**Before:**
```python
min_confidence: float = 0.60
```

**After (WRONG):**
```python
min_confidence: float = 0.65  # Increased threshold
```

**Test Result:**
```
FAILED tests/test_backtest_api_parity.py::test_backtest_api_parity[rejected_confidence_low]
AssertionError: Signal mismatch: API=HOLD, Backtest=BUY
```

(Because backtest now accepts 0.65 confidence signal that API rejects)

---

### **Example 4: Someone Changes Filter Order**

**Before:**
```python
# Confidence filter runs BEFORE trend alignment
if confidence < min_confidence:
    return HOLD
# Then trend alignment
if not trend_aligned:
    return HOLD
```

**After (WRONG):**
```python
# Trend alignment runs BEFORE confidence
if not trend_aligned:
    return HOLD
# Then confidence filter
if confidence < min_confidence:
    return HOLD
```

**Test Result:**
```
FAILED tests/test_backtest_api_parity.py::test_backtest_api_parity[trade_accepted_londonny_uptrend]
AssertionError: Rejection reason mismatch:
API: Confidence below threshold (0.55 < 0.60)
Backtest: Trend alignment failed: counter-trend
```

---

## Adding New Fixtures

### **1. Capture Real Case from Logs**

Find a case in API or MT5 logs:
```
[INFO] SESSION_CHECK: valid=True
[INFO] TREND_FILTER: trend=uptrend, allow_buy=True
[INFO] SR_DETECTION: levels_count=5
[INFO] Broken Level Filter: 2 levels filtered out
[INFO] Rejection Found: SELL at 1.08500, confidence=0.82
[INFO] Trend Filter: BYPASSED - High confidence counter-trend (0.82 >= 0.75)
[INFO] Signal cooldown: PASSED
[INFO] Min Edge Check: PASSED (TP1=22 pips > costs=3.4 + edge=4 = 7.4 pips)
[INFO] ALL FILTERS PASSED - TRADE SIGNAL GENERATED: SELL
```

### **2. Extract Bar Data**

From MT5 EA logs or API logs, extract the bar window (typically 200-400 bars).

### **3. Create Fixture JSON**

```json
{
  "description": "High confidence counter-trend SELL - bypass trend filter",
  "symbol": "EURUSD",
  "timeframe": "H1",
  "parameters": {
    "min_confidence": 0.60,
    "broken_level_cooldown_hours": 48.0,
    "broken_level_break_pips": 15.0,
    "min_edge_pips": 4.0,
    "spread_pips": 1.0,
    "slippage_pips": 0.5,
    "commission_per_side_per_lot": 7.0,
    "usd_per_pip_per_lot": 10.0,
    "lot_size": 1.0
  },
  "bars": [
    {"time": 1738310400, "open": 1.08500, "high": 1.08550, ...},
    ...
  ],
  "expected_results": {
    "decision_bar_time": 1738339200,
    "signal": "SELL",
    "confidence": 0.82,
    "entry": 1.08500,
    "rejection_reason": null,
    "filters_passed": {
      "session": true,
      "trend": true,
      "sr_detection": true,
      "broken_level": true,
      "rejection": true,
      "confidence": true,
      "trend_alignment": true,  // Bypassed due to high confidence
      "signal_cooldown": true,
      "min_edge": true
    }
  }
}
```

### **4. Add to Test**

The parametrized test will automatically pick up the new fixture:

```python
@pytest.mark.parametrize("fixture_name", [
    "trade_accepted_londonny_uptrend",
    "rejected_session_outside_londonny",
    "rejected_confidence_low",
    "rejected_insufficient_edge",
    "high_confidence_counter_trend_sell"  # NEW FIXTURE
])
def test_backtest_api_parity(fixture_name):
    ...
```

---

## CI Integration

### **GitHub Actions** (`.github/workflows/tests.yml`)

```yaml
name: Parity Tests

on:
  push:
    branches: [ main, master, develop ]
  pull_request:
    branches: [ main, master, develop ]

jobs:
  test:
    runs-on: windows-latest  # Or ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install pytest pandas numpy MetaTrader5

    - name: Run parity tests
      run: |
        python -m pytest tests/test_backtest_api_parity.py -v --tb=short

    - name: Fail on test failure
      if: failure()
      run: exit 1
```

### **GitLab CI** (`.gitlab-ci.yml`)

```yaml
test:parity:
  stage: test
  script:
    - pip install pytest pandas numpy MetaTrader5
    - python -m pytest tests/test_backtest_api_parity.py -v --tb=short
  only:
    - main
    - develop
    - merge_requests
```

### **Local Pre-Commit Hook** (`.git/hooks/pre-commit`)

```bash
#!/bin/bash
echo "Running parity tests before commit..."
python -m pytest tests/test_backtest_api_parity.py -v --tb=short

if [ $? -ne 0 ]; then
    echo "❌ Parity tests failed! Commit rejected."
    echo "Fix the issues or update tests if intentional change."
    exit 1
fi

echo "✅ Parity tests passed!"
exit 0
```

Make executable:
```bash
chmod +x .git/hooks/pre-commit
```

---

## Troubleshooting

### **Test Fails After Intentional Change**

If you intentionally changed a parameter (e.g., increased min_confidence from 0.60 to 0.65):

1. **Update fixture expectations:**
   - Edit `tests/fixtures/*.json`
   - Update `expected_results` to match new behavior

2. **Update validation tests:**
   - Edit `test_parameter_defaults_match()` if defaults changed
   - Edit other validation tests if needed

3. **Document the change:**
   - Update `docs/BACKTEST_PARITY.md`
   - Update `docs/PARITY_TESTS.md`

4. **Re-run tests:**
   ```bash
   python -m pytest tests/test_backtest_api_parity.py -v
   ```

### **Test Fails with "No module named pytest"**

Install pytest:
```bash
pip install pytest
```

### **Test Fails with "Fixture not found"**

Ensure fixtures exist:
```bash
ls tests/fixtures/
```

Expected files:
- `trade_accepted_londonny_uptrend.json`
- `rejected_session_outside_londonny.json`
- `rejected_confidence_low.json`
- `rejected_insufficient_edge.json`

### **Test Fails with "ModuleNotFoundError"**

Ensure all dependencies installed:
```bash
pip install pandas numpy MetaTrader5
```

---

## Best Practices

### **1. Run Tests Before Committing**

```bash
python -m pytest tests/test_backtest_api_parity.py -v
```

### **2. Update Fixtures When Changing Logic**

If you intentionally change filter logic:
- Update fixtures to reflect new expected behavior
- Document the change in commit message

### **3. Add New Fixtures for Edge Cases**

When you find a new edge case in production:
- Capture the bar window and parameters
- Create a new fixture
- Add to parametrized test

### **4. Keep Fixtures Minimal**

Use smallest bar window that reproduces the case (usually 9-200 bars)

### **5. Document Expected Behavior**

Add clear `notes` section in fixtures explaining:
- Why this case exists
- What filters should pass/fail
- Expected signal and reason

---

## Files

| File | Purpose |
|------|---------|
| `tests/test_backtest_api_parity.py` | Main test suite |
| `tests/fixtures/*.json` | Test fixtures (bar windows + expected results) |
| `docs/PARITY_TESTS.md` | This documentation |
| `.github/workflows/tests.yml` | CI configuration (if using GitHub Actions) |
| `.git/hooks/pre-commit` | Local pre-commit hook (optional) |

---

## Summary

✅ **Parity tests ensure backtest and API produce identical results**

✅ **Tests catch unintentional changes to:**
- Bar indexing and timing
- Session hours and filters
- Cost model and formulas
- Parameter defaults
- Filter order and logic

✅ **Easy to add new test cases from production logs**

✅ **CI integration prevents drift in production**

✅ **Local pre-commit hooks catch issues before push**

---

**Implementation Date:** 2025-12-29
**Status:** ✅ **COMPLETE**
**Impact:** 🟢 **CRITICAL** - Prevents costly drift between backtest and live trading
