# Making min_edge_pips Sweepable and Visible

## Summary

The `min_edge_pips` parameter is now fully integrated into the grid search and walk-forward analysis systems, allowing it to be swept as a parameter and making it visible in all relevant logs and outputs.

## Changes Made

### 1. Grid Search Worker Forwarding (Line 1215)

**File:** `tests/backtest.py`

**Before:**
```python
result = run_backtest(
    min_confidence=params.get('min_confidence'),
    broken_level_cooldown_hours=params.get('broken_level_cooldown_hours'),
    broken_level_break_pips=params.get('broken_level_break_pips', 15.0),
    # min_edge_pips NOT forwarded
    enable_confidence_filter='min_confidence' in params,
    enable_broken_level_filter='broken_level_cooldown_hours' in params,
    df=df_slice,
    enforce_bars_limit=True,
    verbose=False,
    **backtest_kwargs
)
```

**After:**
```python
result = run_backtest(
    min_confidence=params.get('min_confidence'),
    broken_level_cooldown_hours=params.get('broken_level_cooldown_hours'),
    broken_level_break_pips=params.get('broken_level_break_pips', 15.0),
    min_edge_pips=params.get('min_edge_pips', 2.0),  # ✅ NOW FORWARDED
    enable_confidence_filter='min_confidence' in params,
    enable_broken_level_filter='broken_level_cooldown_hours' in params,
    df=df_slice,
    enforce_bars_limit=True,
    verbose=False,
    **backtest_kwargs
)
```

**Effect:** Grid search workers now correctly apply the `min_edge_pips` parameter from the grid.

---

### 2. Default Walk-Forward Parameter Grid (Lines 1424-1429)

**File:** `tests/backtest.py`

**Before:**
```python
if param_grid is None:
    param_grid = {
        'min_confidence': [0.60, 0.65, 0.70],
        'broken_level_cooldown_hours': [12.0, 24.0, 48.0]
        # min_edge_pips NOT included
    }
```

**After:**
```python
if param_grid is None:
    param_grid = {
        'min_confidence': [0.60, 0.65, 0.70],
        'broken_level_cooldown_hours': [12.0, 24.0, 48.0],
        'min_edge_pips': [0.0, 2.0, 4.0]  # ✅ NOW INCLUDED
    }
```

**Effect:** When no param_grid is specified, walk-forward analysis now sweeps 3 values of min_edge_pips:
- 0.0: Filter effectively disabled
- 2.0: Default (moderate edge requirement)
- 4.0: Conservative (higher edge requirement)

**Grid Size:**
- Before: 3 × 3 = **9 combinations**
- After: 3 × 3 × 3 = **27 combinations**

---

### 3. Walk-Forward Test Backtest (Line 1555)

**File:** `tests/backtest.py`

**Before:**
```python
test_result = run_backtest(
    # ... other parameters ...
    min_confidence=test_param_dict.get('min_confidence'),
    broken_level_cooldown_hours=test_param_dict.get('broken_level_cooldown_hours'),
    broken_level_break_pips=test_param_dict.get('broken_level_break_pips', broken_level_break_pips),
    # min_edge_pips NOT passed
    enable_confidence_filter='min_confidence' in test_param_dict,
    enable_broken_level_filter='broken_level_cooldown_hours' in test_param_dict,
    df=test_df,
    enforce_bars_limit=True,
    verbose=False
)
```

**After:**
```python
test_result = run_backtest(
    # ... other parameters ...
    min_confidence=test_param_dict.get('min_confidence'),
    broken_level_cooldown_hours=test_param_dict.get('broken_level_cooldown_hours'),
    broken_level_break_pips=test_param_dict.get('broken_level_break_pips', broken_level_break_pips),
    min_edge_pips=test_param_dict.get('min_edge_pips', 2.0),  # ✅ NOW PASSED
    enable_confidence_filter='min_confidence' in test_param_dict,
    enable_broken_level_filter='broken_level_cooldown_hours' in test_param_dict,
    df=test_df,
    enforce_bars_limit=True,
    verbose=False
)
```

**Effect:** The final test backtest in each split now uses the correct `min_edge_pips` value from the best parameters.

---

### 4. Walk-Forward Stability Loop (Line 1687)

**File:** `tests/backtest.py`

**Before:**
```python
combo_test_result = run_backtest(
    # ... other parameters ...
    min_confidence=combo_params.get('min_confidence'),
    broken_level_cooldown_hours=combo_params.get('broken_level_cooldown_hours'),
    broken_level_break_pips=combo_params.get('broken_level_break_pips', broken_level_break_pips),
    # min_edge_pips NOT passed
    enable_confidence_filter='min_confidence' in combo_params,
    enable_broken_level_filter='broken_level_cooldown_hours' in combo_params,
    df=test_df,
    enforce_bars_limit=True,
    verbose=False
)
```

**After:**
```python
combo_test_result = run_backtest(
    # ... other parameters ...
    min_confidence=combo_params.get('min_confidence'),
    broken_level_cooldown_hours=combo_params.get('broken_level_cooldown_hours'),
    broken_level_break_pips=combo_params.get('broken_level_break_pips', broken_level_break_pips),
    min_edge_pips=combo_params.get('min_edge_pips', 2.0),  # ✅ NOW PASSED
    enable_confidence_filter='min_confidence' in combo_params,
    enable_broken_level_filter='broken_level_cooldown_hours' in combo_params,
    df=test_df,
    enforce_bars_limit=True,
    verbose=False
)
```

**Effect:** Parameter stability analysis now correctly tests all combinations including different `min_edge_pips` values.

---

### 5. Verbose Filter Display (Line 689)

**File:** `tests/backtest.py`

**Before:**
```python
print(f"\nFilters:")
print(f"  Min Confidence: {min_confidence if enable_confidence_filter else 'OFF'}")
if enable_broken_level_filter:
    print(f"  Broken Level Cooldown: {broken_level_cooldown_hours}h")
    print(f"  Broken Level Threshold: {broken_level_break_pips} pips")
else:
    print("  Broken Level Filter: OFF")
# min_edge_pips NOT displayed
print("=" * 70)
```

**After:**
```python
print(f"\nFilters:")
print(f"  Min Confidence: {min_confidence if enable_confidence_filter else 'OFF'}")
if enable_broken_level_filter:
    print(f"  Broken Level Cooldown: {broken_level_cooldown_hours}h")
    print(f"  Broken Level Threshold: {broken_level_break_pips} pips")
else:
    print("  Broken Level Filter: OFF")
print(f"  Min Edge (pips): {min_edge_pips if min_edge_pips > 0 else 'OFF'}")  # ✅ NOW DISPLAYED
print("=" * 70)
```

**Effect:** Verbose backtest output now shows the `min_edge_pips` setting.

**Example Output:**
```
Filters:
  Min Confidence: 0.65
  Broken Level Cooldown: 24.0h
  Broken Level Threshold: 15.0 pips
  Min Edge (pips): 2.0
======================================================================
```

**When disabled:**
```
Filters:
  Min Confidence: 0.65
  Broken Level Cooldown: 24.0h
  Broken Level Threshold: 15.0 pips
  Min Edge (pips): OFF
======================================================================
```

---

### 6. Grid Search Sample Grid (Lines 2203-2207, 2228-2229)

**File:** `tests/backtest.py`

**Before:**
```python
param_grid = {
    'min_confidence': [0.60, 0.65, 0.70, 0.75],
    'broken_level_cooldown_hours': [12.0, 24.0, 48.0]
    # min_edge_pips NOT included
}

# ...

display_cols = ['min_confidence', 'broken_level_cooldown_hours', 'total_trades',
               'win_rate', 'profit_factor', 'total_pnl_after_costs', 'max_drawdown']
```

**After:**
```python
param_grid = {
    'min_confidence': [0.60, 0.65, 0.70, 0.75],
    'broken_level_cooldown_hours': [12.0, 24.0, 48.0],
    'min_edge_pips': [0.0, 2.0, 4.0]  # ✅ NOW INCLUDED
}

# ...

display_cols = ['min_confidence', 'broken_level_cooldown_hours', 'min_edge_pips', 'total_trades',
               'win_rate', 'profit_factor', 'total_pnl_after_costs', 'max_drawdown']
```

**Effect:**
- Grid search now tests 3 `min_edge_pips` values
- Results table shows `min_edge_pips` column
- Grid size: 4 × 3 × 3 = **36 combinations**

**Example Output:**
```
Top 10 Parameter Combinations:
======================================================================
 min_confidence  broken_level_cooldown_hours  min_edge_pips  total_trades  win_rate  profit_factor  total_pnl_after_costs  max_drawdown
           0.70                         48.0            4.0            12      58.3           3.25                  285.5          45.2
           0.65                         24.0            2.0            18      61.1           2.85                  245.8          52.3
           0.60                         48.0            0.0            25      52.0           2.15                  198.7          68.5
```

---

### 7. Walk-Forward Sample Grid (Lines 2238-2242, 2265)

**File:** `tests/backtest.py`

**Before:**
```python
param_grid = {
    'min_confidence': [0.60, 0.65, 0.70],
    'broken_level_cooldown_hours': [12.0, 24.0, 48.0]
    # min_edge_pips NOT included
}

# ...

display_cols = ['split', 'param_min_confidence', 'param_broken_level_cooldown_hours',
               'train_profit_factor', 'test_profit_factor',
               'train_total_trades', 'test_total_trades',
               'test_total_pnl_after_costs']
```

**After:**
```python
param_grid = {
    'min_confidence': [0.60, 0.65, 0.70],
    'broken_level_cooldown_hours': [12.0, 24.0, 48.0],
    'min_edge_pips': [0.0, 2.0, 4.0]  # ✅ NOW INCLUDED
}

# ...

display_cols = ['split', 'param_min_confidence', 'param_broken_level_cooldown_hours', 'param_min_edge_pips',
               'train_profit_factor', 'test_profit_factor',
               'train_total_trades', 'test_total_trades',
               'test_total_pnl_after_costs']
```

**Effect:**
- Walk-forward analysis now sweeps 3 `min_edge_pips` values
- Results table shows `param_min_edge_pips` column
- Grid size per split: 3 × 3 × 3 = **27 combinations**

**Example Output:**
```
Detailed Walk-Forward Results:
======================================================================
 split  param_min_confidence  param_broken_level_cooldown_hours  param_min_edge_pips  train_profit_factor  test_profit_factor  train_total_trades  test_total_trades  test_total_pnl_after_costs
     1                  0.70                               48.0                  4.0                 3.50                2.85                  15                  8                       185.3
     2                  0.65                               24.0                  2.0                 3.25                2.60                  22                 12                       205.7
     3                  0.65                               48.0                  2.0                 3.10                2.45                  18                 10                       178.5
```

---

## Parameter Grid Sizes

### Before Changes:
- **Grid Search:** 4 × 3 = **12 combinations**
- **Walk-Forward (default):** 3 × 3 = **9 combinations per split**

### After Changes:
- **Grid Search:** 4 × 3 × 3 = **36 combinations** (3× larger)
- **Walk-Forward (default):** 3 × 3 × 3 = **27 combinations per split** (3× larger)

**Performance Impact:**
- Grid search takes ~3× longer
- Walk-forward takes ~3× longer per split
- But provides valuable insight into optimal edge requirements

---

## Acceptance Checks

### ✅ Grid Search

1. **Testing output shows min_edge_pips:**
   ```
   Testing parameter combinations:
   Total combinations: 36
   Parameters:
     min_confidence: [0.60, 0.65, 0.70, 0.75]
     broken_level_cooldown_hours: [12.0, 24.0, 48.0]
     min_edge_pips: [0.0, 2.0, 4.0]
   ```

2. **Results DataFrame includes min_edge_pips column:**
   ```python
   print(results_df.columns)
   # Output includes: 'min_edge_pips'
   ```

3. **Top results display shows min_edge_pips:**
   ```
   min_confidence  broken_level_cooldown_hours  min_edge_pips  total_trades  ...
   0.70            48.0                         4.0            12            ...
   ```

### ✅ Walk-Forward

1. **Best parameters include min_edge_pips:**
   ```
   Best parameters found:
     min_confidence: 0.70
     broken_level_cooldown_hours: 48.0
     min_edge_pips: 4.0
   ```

2. **Results DataFrame includes param_min_edge_pips column:**
   ```python
   print(wf_results.columns)
   # Output includes: 'param_min_edge_pips'
   ```

3. **Detailed results display shows param_min_edge_pips:**
   ```
   split  param_min_confidence  param_broken_level_cooldown_hours  param_min_edge_pips  ...
   1      0.70                  48.0                               4.0                  ...
   ```

### ✅ Verbose Output

1. **Filter section shows min_edge_pips:**
   ```
   Filters:
     Min Confidence: 0.70
     Broken Level Cooldown: 48.0h
     Broken Level Threshold: 15.0 pips
     Min Edge (pips): 4.0
   ```

2. **Shows OFF when disabled:**
   ```
   Filters:
     Min Confidence: 0.70
     Broken Level Cooldown: 48.0h
     Broken Level Threshold: 15.0 pips
     Min Edge (pips): OFF
   ```

---

## Usage Examples

### Grid Search with min_edge_pips

```python
# Example 1: Custom grid with min_edge_pips
param_grid = {
    'min_confidence': [0.65, 0.70],
    'broken_level_cooldown_hours': [24.0, 48.0],
    'min_edge_pips': [1.0, 2.0, 3.0, 4.0]  # ✅ Now sweepable
}

results = run_grid_search(
    param_grid=param_grid,
    symbol="EURUSD",
    timeframe="H1",
    bars=500
)

# Results will include min_edge_pips column
print(results[['min_edge_pips', 'profit_factor', 'total_trades']])
```

### Walk-Forward with min_edge_pips

```python
# Example 2: Walk-forward with custom min_edge_pips values
param_grid = {
    'min_confidence': [0.60, 0.65, 0.70],
    'broken_level_cooldown_hours': [12.0, 24.0, 48.0],
    'min_edge_pips': [0.0, 1.5, 3.0, 4.5]  # ✅ Custom values
}

wf_results = run_walk_forward(
    symbol="EURUSD",
    timeframe="H1",
    total_bars=2000,
    splits=5,
    train_bars=400,
    test_bars=100,
    param_grid=param_grid
)

# Results will include param_min_edge_pips column
print(wf_results[['split', 'param_min_edge_pips', 'test_profit_factor']])
```

### Analyzing min_edge_pips Impact

```python
# Example 3: Analyze edge requirement impact
results = run_grid_search(
    param_grid={
        'min_confidence': [0.70],
        'broken_level_cooldown_hours': [24.0],
        'min_edge_pips': [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]  # Focus on edge
    },
    symbol="EURUSD",
    timeframe="H1",
    bars=1000
)

# Compare trade count vs edge requirement
import matplotlib.pyplot as plt
plt.plot(results['min_edge_pips'], results['total_trades'])
plt.xlabel('Min Edge (pips)')
plt.ylabel('Total Trades')
plt.title('Trade Frequency vs Edge Requirement')
plt.show()
```

---

## Best Practices

### 1. Start with Default Range
```python
'min_edge_pips': [0.0, 2.0, 4.0]
```
- 0.0: Baseline (filter disabled)
- 2.0: Moderate edge requirement
- 4.0: Conservative edge requirement

### 2. Adjust Based on Broker Costs
```python
# High-cost broker
'min_edge_pips': [2.0, 4.0, 6.0]

# Low-cost broker
'min_edge_pips': [0.0, 1.0, 2.0]
```

### 3. Fine-Tune After Initial Sweep
```python
# Initial sweep
'min_edge_pips': [0.0, 2.0, 4.0, 6.0]

# If 2.0 performs best, fine-tune around it
'min_edge_pips': [1.0, 1.5, 2.0, 2.5, 3.0]
```

---

## Summary

✅ **Grid Search:** `min_edge_pips` now sweepable, visible in results
✅ **Walk-Forward:** `min_edge_pips` included in default grid, best params, and stability analysis
✅ **Verbose Output:** Shows `min_edge_pips` setting in filters section
✅ **Sample Grids:** Both MODE blocks include `min_edge_pips` arrays

**No behavioral changes** except now you can sweep and optimize the edge requirement parameter alongside confidence and cooldown settings.

**Result:** Complete control over minimum profit edge requirements across all backtest modes.
