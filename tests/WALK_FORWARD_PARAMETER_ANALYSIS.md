# Walk-Forward Parameter Performance Analysis

## Overview

The walk-forward analysis now tracks **all parameter combinations** tested during each split and provides comprehensive performance analysis across splits. This helps identify:

- **Robust parameters**: Consistently profitable across multiple splits
- **Overfitting**: Good in-sample (training) but poor out-of-sample (test)
- **Parameter stability**: How often each combo is selected as "best"
- **OOS performance**: Actual profitability when parameters are tested on unseen data

## What's New

### 1. **Full Training Grid Storage**

For each walk-forward split, the system now stores:
- Complete training grid search results (all parameter combinations tested)
- Best parameters chosen for that split
- Out-of-sample (OOS) test results for the chosen parameters

### 2. **Aggregated Parameter Performance Table**

After all splits complete, displays a sorted table showing:

| Column | Description |
|--------|-------------|
| **Params** | Parameter combination (e.g., `min_confidence=0.65, broken_level_cooldown_hours=24.0`) |
| **Selected** | How many times this combo was chosen as best during training |
| **Mean PF** | Average profit factor across all OOS tests where this combo was selected |
| **Med PF** | Median profit factor (more robust to outliers) |
| **Mean PnL** | Average PnL in pips across OOS tests |
| **% Profit** | Percentage of splits where this combo was profitable OOS |

**Sorted by:** Median OOS Profit Factor (descending), then Mean OOS PnL (descending)

### 3. **Top-3 Per Split Analysis**

For each split, shows the top 3 parameter combinations ranked by **training profit factor**, along with their OOS performance:

- **Train PF**: In-sample profit factor (what optimizer saw)
- **OOS PF**: Out-of-sample profit factor (actual unseen data)
- **OOS PnL**: Out-of-sample PnL in pips
- **Marker (*)**: Indicates which combo was selected as best

## Why This Matters

### Identifying Overfitting

**Example Output:**
```
Split 1:
  Rank   Params                              Train PF     OOS PF       OOS PnL
  ------------------------------------------------------------------------------
  1      min_confidence=0.60, cooldown=12    5.23         0.85         -45.2    *
  2      min_confidence=0.65, cooldown=24    3.10         N/A          N/A
  3      min_confidence=0.70, cooldown=48    2.85         N/A          N/A
```

**Interpretation:**
- Rank 1 had the best training PF (5.23)
- But OOS, it performed poorly (PF=0.85, -45.2 pips)
- **This is overfitting!** Parameters optimized too much to training data

### Robust Parameters

**Example Output:**
```
Parameter Performance Across All Splits:
Params                                             Selected   Mean PF    Med PF     Mean PnL     % Profit
------------------------------------------------------------------------------------------------------------
min_confidence=0.65, cooldown=24.0                 3          1.85       1.92       125.3        100.0
min_confidence=0.70, cooldown=48.0                 2          1.45       1.50       85.7         100.0
min_confidence=0.60, cooldown=12.0                 5          1.20       0.95       -15.2        40.0
```

**Interpretation:**
- First combo: Selected 3 times, median OOS PF = 1.92, **100% profitable**
- Last combo: Selected 5 times (most popular in training), but median OOS PF = 0.95, **only 40% profitable**
- **First combo is more robust** despite being selected less often

## Practical Usage

### Finding the Best Parameters

1. **Look at Parameter Performance Table**:
   - Check **Median PF** and **% Profit** columns
   - Higher median PF + higher % profit = more robust
   - Ignore combos selected only 1 time (could be luck)

2. **Check Top-3 Per Split Analysis**:
   - Look for combos that rank high in training AND perform well OOS
   - If rank #1 consistently has poor OOS, training is overfitting

3. **Cross-reference**:
   - Combos with high "Selected" count but low OOS performance → overfitting
   - Combos with moderate "Selected" count but high OOS performance → robust

### Example Decision Process

**Scenario:** 5 splits completed

**Parameter Performance Table:**
```
Params                          Selected   Mean PF   Med PF   Mean PnL   % Profit
min_confidence=0.70, cool=48    2          2.10      2.05     +150.3     100.0
min_confidence=0.65, cool=24    3          1.85      1.92     +125.3     100.0
min_confidence=0.60, cool=12    5          1.35      1.10     +20.5      60.0
```

**Top-3 Per Split:**
```
Split 1: Rank #1 (0.60, 12) - Train PF: 4.2, OOS PF: 1.1, OOS PnL: +22.5 *
Split 2: Rank #1 (0.60, 12) - Train PF: 3.8, OOS PF: 0.9, OOS PnL: -10.2 *
Split 3: Rank #1 (0.65, 24) - Train PF: 3.5, OOS PF: 1.9, OOS PnL: +135.7 *
Split 4: Rank #1 (0.70, 48) - Train PF: 3.2, OOS PF: 2.1, OOS PnL: +165.8 *
Split 5: Rank #1 (0.65, 24) - Train PF: 3.0, OOS PF: 1.8, OOS PnL: +115.0 *
```

**Analysis:**
- **(0.60, 12)** was selected 5/5 times in training (most popular)
  - But OOS performance is inconsistent (60% profitable, median PF only 1.10)
  - Likely overfitting to training data

- **(0.65, 24)** was selected 3/5 times
  - OOS performance is excellent (100% profitable, median PF 1.92)
  - More robust choice

- **(0.70, 48)** was selected 2/5 times
  - Best OOS performance (median PF 2.05, 100% profitable)
  - **BEST CHOICE** for production despite being selected less often

**Decision:** Use `min_confidence=0.70, broken_level_cooldown_hours=48` for live trading.

## Red Flags

### 🚩 High Selection Count, Poor OOS Performance
```
Params                          Selected   Mean PF   Med PF   Mean PnL   % Profit
min_confidence=0.55, cool=6     5          1.05      0.85     -25.3      20.0
```
**Problem:** Selected 5 times but only 20% profitable OOS → **severe overfitting**

### 🚩 Huge Gap Between Train and OOS PF
```
Split 1:
  Rank   Params                              Train PF     OOS PF       OOS PnL
  1      min_confidence=0.55, cooldown=6     8.50         0.45         -125.3   *
```
**Problem:** Train PF = 8.50, OOS PF = 0.45 → **extreme overfitting**

### 🚩 Inconsistent OOS Results
```
Params                          Selected   Mean PF   Med PF   Mean PnL   % Profit
min_confidence=0.60, cool=12    4          1.50      0.95     +50.2      50.0
```
**Problem:** Mean PF (1.50) much higher than Median PF (0.95) → **outliers/inconsistency**

## Green Flags

### ✓ Consistent OOS Performance
```
Params                          Selected   Mean PF   Med PF   Mean PnL   % Profit
min_confidence=0.70, cool=48    3          1.95      1.92     +135.7     100.0
```
**Good:** Mean ≈ Median, 100% profitable, stable performance

### ✓ Moderate Selection, High OOS
```
Params                          Selected   Mean PF   Med PF   Mean PnL   % Profit
min_confidence=0.75, cool=72    2          2.35      2.30     +180.3     100.0
```
**Good:** Not overfit (selected moderately), excellent OOS performance

### ✓ Small Train-OOS Gap
```
Split 3:
  Rank   Params                              Train PF     OOS PF       OOS PnL
  1      min_confidence=0.70, cooldown=48    2.85         2.10         +165.8   *
```
**Good:** Train PF = 2.85, OOS PF = 2.10 → **generalizes well**

## Advanced Tips

### 1. **Focus on Median PF, Not Mean PF**
- Median is robust to outliers (one lucky split doesn't inflate the number)
- Mean can be misleading if one split had extreme performance

### 2. **Require Multiple Selections**
- Don't trust combos selected only 1 time (could be random luck)
- Look for combos selected 2-3+ times with consistent OOS performance

### 3. **Check % Profit**
- 100% profitable across splits = very robust
- <70% profitable = risky (inconsistent)

### 4. **Use Top-3 Analysis to Verify**
- If a combo ranks #1 in training but has poor OOS → overfitting
- If a combo ranks #2-3 in training but has good OOS → robust

### 5. **Consider Parameter Interpretability**
```
min_confidence=0.70 → Stricter filter, fewer but higher quality signals
min_confidence=0.60 → Looser filter, more signals but lower quality

broken_level_cooldown_hours=48 → Conservative (avoids broken levels longer)
broken_level_cooldown_hours=12 → Aggressive (re-enters broken levels sooner)
```

Choose parameters that make sense for your risk tolerance and market conditions.

## Example Full Output

```
======================================================================
PARAMETER PERFORMANCE ANALYSIS
======================================================================

Parameter Performance Across All Splits (sorted by median OOS PF, then mean OOS PnL):
------------------------------------------------------------------------------------------------------------------------
Params                                             Selected   Mean PF    Med PF     Mean PnL     % Profit
------------------------------------------------------------------------------------------------------------------------
min_confidence=0.70, broken_level_cooldown_hours=48.0    2          2.10       2.05       150.3        100.0
min_confidence=0.65, broken_level_cooldown_hours=24.0    3          1.85       1.92       125.3        100.0
min_confidence=0.70, broken_level_cooldown_hours=24.0    1          1.55       1.55       95.7         100.0
min_confidence=0.60, broken_level_cooldown_hours=48.0    1          1.35       1.35       75.2         100.0
min_confidence=0.65, broken_level_cooldown_hours=48.0    1          1.25       1.25       55.8         100.0
min_confidence=0.60, broken_level_cooldown_hours=24.0    2          1.20       1.15       35.5         50.0
min_confidence=0.60, broken_level_cooldown_hours=12.0    5          1.10       0.95       20.5         60.0
------------------------------------------------------------------------------------------------------------------------

======================================================================
TOP-3 PARAMETER COMBOS PER SPLIT (by train PF) + OOS Performance
======================================================================

Split 1:
  ------------------------------------------------------------------
  Rank   Params                              Train PF     OOS PF       OOS PnL
  ------------------------------------------------------------------
  1      min_confidence=0.60, cooldown=12    4.20         1.10         22.5         *
  2      min_confidence=0.65, cooldown=24    3.50         N/A          N/A
  3      min_confidence=0.70, cooldown=48    2.80         N/A          N/A
  ------------------------------------------------------------------
  * = Selected as best and tested OOS

Split 2:
  ------------------------------------------------------------------
  Rank   Params                              Train PF     OOS PF       OOS PnL
  ------------------------------------------------------------------
  1      min_confidence=0.60, cooldown=12    3.80         0.90         -10.2        *
  2      min_confidence=0.60, cooldown=24    3.20         N/A          N/A
  3      min_confidence=0.65, cooldown=24    2.90         N/A          N/A
  ------------------------------------------------------------------
  * = Selected as best and tested OOS

Split 3:
  ------------------------------------------------------------------
  Rank   Params                              Train PF     OOS PF       OOS PnL
  ------------------------------------------------------------------
  1      min_confidence=0.65, cooldown=24    3.50         1.90         135.7        *
  2      min_confidence=0.70, cooldown=48    3.20         N/A          N/A
  3      min_confidence=0.60, cooldown=12    2.70         N/A          N/A
  ------------------------------------------------------------------
  * = Selected as best and tested OOS

Split 4:
  ------------------------------------------------------------------
  Rank   Params                              Train PF     OOS PF       OOS PnL
  ------------------------------------------------------------------
  1      min_confidence=0.70, cooldown=48    3.20         2.10         165.8        *
  2      min_confidence=0.65, cooldown=24    2.80         N/A          N/A
  3      min_confidence=0.60, cooldown=12    2.50         N/A          N/A
  ------------------------------------------------------------------
  * = Selected as best and tested OOS

Split 5:
  ------------------------------------------------------------------
  Rank   Params                              Train PF     OOS PF       OOS PnL
  ------------------------------------------------------------------
  1      min_confidence=0.65, cooldown=24    3.00         1.80         115.0        *
  2      min_confidence=0.70, cooldown=48    2.85         N/A          N/A
  3      min_confidence=0.60, cooldown=12    2.60         N/A          N/A
  ------------------------------------------------------------------
  * = Selected as best and tested OOS

======================================================================
```

## Conclusion

This analysis helps you:
1. **Avoid overfitting**: Don't blindly trust training results
2. **Find robust parameters**: Look for consistency across splits
3. **Make informed decisions**: Use OOS performance, not just training performance
4. **Understand trade-offs**: See which parameters work in which market conditions

**Key Takeaway:** The parameter combination with the **highest median OOS profit factor and highest % profitable splits** is likely the most robust choice for live trading.
