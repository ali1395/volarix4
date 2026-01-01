# Volarix 4 Test Suite

## Overview

This directory contains the test suite for Volarix 4, including:
- **Parity tests** - Ensure backtest and API produce identical results
- **Fixtures** - Recorded bar windows with expected results
- **Backtest script** - Offline backtesting with cost modeling

---

## Directory Structure

```
tests/
├── test_backtest_api_parity.py   # Main parity test suite
├── backtest.py                   # Backtest runner
├── requirements.txt              # Test dependencies
├── fixtures/                     # Test fixtures (JSON)
│   ├── trade_accepted_londonny_uptrend.json
│   ├── rejected_session_outside_londonny.json
│   ├── rejected_confidence_low.json
│   └── rejected_insufficient_edge.json
└── README.md                     # This file
```

---

## Running Tests

### **Install Dependencies**

```bash
pip install -r tests/requirements.txt
```

### **Run All Parity Tests**

```bash
python -m pytest tests/test_backtest_api_parity.py -v
```

### **Run Specific Test**

```bash
python -m pytest tests/test_backtest_api_parity.py::test_backtest_api_parity -v
```

### **Run Backtest**

```bash
python tests/backtest.py
```

---

## Test Coverage

### **Parity Tests** (`test_backtest_api_parity.py`)

Automated tests that compare backtest and API results on identical bar windows:

✅ **Core Assertions:**
- Decision bar time and close match
- Signal direction (BUY/SELL/HOLD) matches
- Rejection reasons match (if HOLD)
- Entry, SL, TP prices match
- Cost calculations match
- Confidence scores match

✅ **Configuration Validation:**
- Parameter defaults match API config
- Session hours unchanged (London 3-11, NY 8-22)
- EMA periods unchanged (20/50)
- Cost model formula unchanged

**Test Fixtures:**

| Fixture | Expected Signal | Test Case |
|---------|----------------|-----------|
| `trade_accepted_londonny_uptrend.json` | BUY | All filters pass |
| `rejected_session_outside_londonny.json` | HOLD | Asian hours rejection |
| `rejected_confidence_low.json` | HOLD | Confidence < 0.60 |
| `rejected_insufficient_edge.json` | HOLD | TP1 too close after costs |

---

## What Tests Prevent

These tests will **FAIL** if anyone changes:

❌ Bar indexing (e.g., including forming bar)
❌ Session hours (London/NY times)
❌ EMA periods (20/50 for trend filter)
❌ Cost model parameters or formula
❌ Filter order or logic
❌ Parameter defaults (min_confidence, min_edge, etc.)

---

## CI Integration

Tests run automatically on:
- Push to main/master/develop branches
- Pull requests to main/master/develop
- Changes to Python files or test fixtures

See `.github/workflows/parity_tests.yml` for CI configuration.

---

## Adding New Tests

### **1. Capture Real Case from Logs**

Find interesting case in API or MT5 logs (e.g., high confidence counter-trend bypass)

### **2. Create Fixture**

Create new JSON file in `fixtures/`:

```json
{
  "description": "Your test case description",
  "symbol": "EURUSD",
  "timeframe": "H1",
  "parameters": { ... },
  "bars": [ ... ],
  "expected_results": { ... }
}
```

### **3. Add to Test**

Update parametrized test in `test_backtest_api_parity.py`:

```python
@pytest.mark.parametrize("fixture_name", [
    ...,
    "your_new_fixture_name"  # Add here
])
```

### **4. Run Tests**

```bash
python -m pytest tests/test_backtest_api_parity.py -v
```

---

## Documentation

📄 **`docs/PARITY_TESTS.md`** - Detailed test documentation
📄 **`docs/BACKTEST_PARITY.md`** - Backtest-API parity implementation
📄 **`docs/PARITY_CONTRACT_IMPLEMENTATION.md`** - MT5 closed bars implementation

---

## Questions?

See:
- `docs/PARITY_TESTS.md` for detailed test documentation
- `docs/BACKTEST_PARITY.md` for backtest implementation details
- `tests/test_backtest_api_parity.py` for test code

---

**Status:** ✅ **COMPLETE**
**Coverage:** 4 fixtures, 8 test cases
**CI:** GitHub Actions workflow configured
