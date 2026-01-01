# Analysis Methodologies

This directory contains documentation for advanced analysis methodologies used to validate and optimize the Volarix 4 trading strategy.

## Overview

These documents describe **analytical techniques** for evaluating strategy robustness, parameter sensitivity, and potential overfitting. They are **methodologies** (how to analyze), not implementation guides.

## Files

### Parameter Validation & Optimization

**[PARAMETER_STABILITY.md](PARAMETER_STABILITY.md)**
- **Purpose:** Test if parameters are stable across different market conditions
- **Method:** Grid search with multiple parameter combinations
- **Output:** Performance metrics per parameter set, sensitivity analysis
- **When to use:** Before deploying strategy with new parameters

**[WALK_FORWARD_PARAMETER_ANALYSIS.md](WALK_FORWARD_PARAMETER_ANALYSIS.md)**
- **Purpose:** Validate parameter robustness using walk-forward testing
- **Method:** Train on in-sample period, validate on out-of-sample period, roll forward
- **Output:** In-sample vs out-of-sample performance comparison
- **When to use:** To detect parameter overfitting and ensure generalization

### Overfitting Detection

**[OVERFITTING_DETECTION.md](OVERFITTING_DETECTION.md)**
- **Purpose:** Identify if strategy is overfit to historical data
- **Method:** Compare in-sample vs out-of-sample performance, check parameter sensitivity
- **Output:** Overfitting risk score, recommended parameter adjustments
- **When to use:** After parameter optimization, before live deployment

**[MONTE_CARLO_ANALYSIS.md](MONTE_CARLO_ANALYSIS.md)**
- **Purpose:** Assess strategy robustness using randomized trade sequence simulations
- **Method:** Shuffle trade outcomes, generate distribution of equity curves
- **Output:** Confidence intervals for drawdown, profit factor, win rate
- **When to use:** To understand worst-case scenarios and risk of ruin

---

## When to Use These Methodologies

### Before Live Trading
- ✅ Run overfitting detection to validate strategy isn't curve-fit
- ✅ Run Monte Carlo to understand risk distribution
- ✅ Run walk-forward analysis to confirm parameter stability

### After Parameter Changes
- ✅ Run parameter stability analysis to test new settings
- ✅ Re-run overfitting detection
- ✅ Update Monte Carlo simulations with new backtest results

### Regular Validation (Monthly/Quarterly)
- ✅ Walk-forward analysis on recent data
- ✅ Parameter stability check (has optimal region shifted?)
- ✅ Monte Carlo update with latest trade results

---

## Implementation Status

| Methodology | Implemented | Location | Notes |
|-------------|-------------|----------|-------|
| Parameter Stability | ⚠️ Methodology only | PARAMETER_STABILITY.md | Implementation guide provided |
| Walk-Forward Analysis | ⚠️ Methodology only | WALK_FORWARD_PARAMETER_ANALYSIS.md | Implementation guide provided |
| Overfitting Detection | ⚠️ Methodology only | OVERFITTING_DETECTION.md | Implementation guide provided |
| Monte Carlo | ⚠️ Methodology only | MONTE_CARLO_ANALYSIS.md | Implementation guide provided |

**Note:** These are **documentation of methodologies**, not implemented code. To use them:
1. Read the methodology document
2. Implement the analysis using the backtest framework (`tests/backtest.py`)
3. Follow the steps outlined in each document

---

## Quick Start

### Example: Run Parameter Stability Analysis

1. **Read methodology:** `tests/analysis/PARAMETER_STABILITY.md`

2. **Modify backtest.py** to sweep parameters:
```python
# Example parameter grid
min_confidence_values = [0.55, 0.60, 0.65, 0.70]
min_edge_values = [3.0, 4.0, 5.0, 6.0]

for conf in min_confidence_values:
    for edge in min_edge_values:
        # Run backtest with these parameters
        results = run_backtest(min_confidence=conf, min_edge_pips=edge)
        # Store results
        ...
```

3. **Analyze results** per methodology document instructions

4. **Document findings** and update parameters if needed

---

## Relationship to Main Tests

| Directory | Purpose | Type |
|-----------|---------|------|
| `tests/` | Automated test suite, parity tests, backtest runner | **Executable code** |
| `tests/analysis/` | Analysis methodologies, validation techniques | **Documentation** |
| `tests/fixtures/` | Test data for parity tests | **Data files** |

**Key Difference:**
- `tests/` contains **runnable code** (pytest tests, backtest scripts)
- `tests/analysis/` contains **methodologies** (guides for analysis)

---

## Contributing

When adding new analysis methodologies:
1. Create a new `.md` file in `tests/analysis/`
2. Follow the structure: Purpose, Method, Output, When to use
3. Provide implementation examples
4. Update this README with the new methodology

---

## References

- **Main Backtest:** `tests/backtest.py`
- **Parity Tests:** `tests/test_backtest_api_parity.py`
- **Strategy Docs:** `docs/03-STRATEGY-LOGIC.md`
- **Parameter Docs:** `docs/04-API-REFERENCE.md`
