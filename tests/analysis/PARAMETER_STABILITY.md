# Parameter Stability Across Splits

## Overview

The **Parameter Stability Analysis** tests ALL parameter combinations on EVERY split's test set, revealing which parameters are truly robust across different market conditions—not just which ones happen to perform well during training.

## Key Difference from Other Analyses

### 1. **Parameter Performance Analysis** (Existing)
- Only tests the **best** parameter combo on each split's test set
- Shows which combos were selected most often
- Limited to combos that won during training

### 2. **Parameter Stability Analysis** (NEW)
- Tests **ALL** parameter combos on each split's test set
- Shows which combos perform consistently well **regardless** of training selection
- Reveals hidden gems that train poorly but test well

## What It Does

For each split:
1. **Training**: Run grid search on training segment (as usual)
2. **Testing (NEW)**: Test ALL parameter combinations on test segment
   - Not just the best one from training
   - Get test PF and PnL for every combo

Then aggregate across all splits:
- **Mean/Median Test PF**: Average performance across splits
- **Mean/Median Test PnL**: Average profit across splits
- **% Splits Profitable**: How often combo is profitable
- **Count Selected**: How often combo won during training

## Output Format

### Per-Split Progress

```
[STABILITY] Testing all 9 parameter combinations on test set...
  ✓ Tested 9 combinations on test set
```

### Top 10 by Median Test PF

```
======================================================================
PARAMETER STABILITY ACROSS SPLITS
======================================================================

Testing ALL parameter combinations on each split's test set
(This reveals which parameters are robust across market conditions)
----------------------------------------------------------------------

TOP 10 PARAMETER COMBINATIONS (by median test PF):
------------------------------------------------------------------------------------------------------------------------
Rank   Params                                   Med PF     Mean PF    Med PnL      % Profit   Selected
------------------------------------------------------------------------------------------------------------------------
1      min_confidence=0.70, cooldown=48.0       2.15       2.08       145.3        100.0      2
2      min_confidence=0.65, cooldown=24.0       1.92       1.85       125.7        100.0      3
3      min_confidence=0.70, cooldown=24.0       1.75       1.68       98.5         80.0       1
4      min_confidence=0.65, cooldown=48.0       1.55       1.48       75.2         80.0       0
5      min_confidence=0.60, cooldown=48.0       1.35       1.28       52.3         60.0       0
6      min_confidence=0.60, cooldown=24.0       1.15       1.10       28.7         60.0       2
7      min_confidence=0.60, cooldown=12.0       0.95       0.88       -15.3        40.0       5
8      min_confidence=0.65, cooldown=12.0       0.85       0.78       -32.8        20.0       0
9      min_confidence=0.70, cooldown=12.0       0.75       0.68       -48.5        20.0       0
------------------------------------------------------------------------------------------------------------------------
```

### Most Stable Combination

```
MOST STABLE PARAMETER COMBINATION:
----------------------------------------------------------------------
  Parameters: min_confidence=0.70, broken_level_cooldown_hours=48.0
  % Profitable Splits: 100.0%
  Median Test PF: 2.15
  Mean Test PF: 2.08
  Median Test PnL: 145.3 pips
  Mean Test PnL: 142.7 pips
  Selected as Best: 2/5 splits

  Interpretation:
    ✓ Excellent: Profitable in 100% of splits
    ✓ Strong: Median PF 2.15 ≥ 2.0
----------------------------------------------------------------------
```

## Key Metrics Explained

### 1. **Median Test PF**
- **Median** profit factor across all splits for this combo
- More robust than mean (not affected by outliers)
- **Primary ranking metric**

### 2. **Mean Test PF**
- **Average** profit factor across splits
- Can be skewed by one exceptional split
- Use median instead for ranking

### 3. **Median Test PnL**
- **Median** net profit across splits
- Secondary ranking metric (after median PF)

### 4. **% Profit**
- Percentage of splits where this combo was profitable (PnL > 0)
- **Critical for stability**: 100% = always profitable
- <60% = unreliable

### 5. **Selected**
- How many times this combo won during training
- **Disconnect reveals overfitting**:
  - High selection, low test performance = overfitting
  - Low selection, high test performance = undervalued

### 6. **Most Stable**
- Combo with **highest % profitable**, then **best median PF**
- Prioritizes consistency over peak performance
- Best choice for live trading

## Interpretation Examples

### Example 1: Hidden Gem Discovered

```
Rank 1:
  Params: min_confidence=0.70, cooldown=48.0
  Med PF: 2.15
  % Profit: 100.0%
  Selected: 2/5 splits (only 40%)
```

**Analysis:**
- Only selected 2/5 times during training (not the favorite)
- But performs best on test sets (median PF 2.15)
- 100% profitable across all splits
- **Hidden gem!** Training undervalued it

**Implication:**
- Don't just use the most-selected combo
- This combo is more robust than training suggested
- **Best choice** for live trading

### Example 2: Overfitting Exposed

```
Rank 7:
  Params: min_confidence=0.60, cooldown=12.0
  Med PF: 0.95
  % Profit: 40.0%
  Selected: 5/5 splits (100%)
```

**Analysis:**
- Selected 5/5 times during training (training favorite)
- But performs poorly on test sets (median PF 0.95 < 1.0)
- Only profitable in 40% of splits
- **Severe overfitting!**

**Implication:**
- Training loved it, but it doesn't generalize
- Unprofitable in reality (PF < 1.0)
- **Don't use** despite high selection rate

### Example 3: Stable Workhorse

```
Rank 2:
  Params: min_confidence=0.65, cooldown=24.0
  Med PF: 1.92
  % Profit: 100.0%
  Selected: 3/5 splits (60%)
```

**Analysis:**
- Selected 3/5 times (moderately popular)
- Excellent test performance (median PF 1.92)
- 100% profitable across splits
- **Consistent performer**

**Implication:**
- Training correctly identified it as good
- Test confirms it's robust
- **Safe choice** for live trading

### Example 4: Mediocre Consistency

```
Rank 5:
  Params: min_confidence=0.60, cooldown=48.0
  Med PF: 1.35
  % Profit: 60.0%
  Selected: 0/5 splits (0%)
```

**Analysis:**
- Never selected during training
- Marginal test performance (median PF 1.35)
- Only profitable in 60% of splits
- **Not reliable enough**

**Implication:**
- Training correctly avoided it
- Inconsistent performance (40% loss rate)
- Look for better options

## Decision Framework

### ✓ Excellent Choice
```
% Profitable: 100%
Median Test PF: ≥ 1.5
Selected: Doesn't matter (stability proves robustness)
```
→ **Use for live trading**

### ✓ Good Choice
```
% Profitable: ≥ 80%
Median Test PF: ≥ 1.5
```
→ **Safe for live trading**

### ⚠ Risky Choice
```
% Profitable: 60-80%
Median Test PF: 1.0-1.5
```
→ **Use with caution, reduce position size**

### ✗ Poor Choice
```
% Profitable: < 60%
OR
Median Test PF: < 1.0
```
→ **Don't use - unreliable**

## Most Stable vs Top 10

### Most Stable Combo
- Prioritizes **consistency** (% profitable)
- Secondary: Best median PF among consistent combos
- **Best for risk-averse traders**
- Example: 100% profitable, PF 1.8

### Top 10 Rank #1
- Prioritizes **performance** (median PF)
- May sacrifice consistency
- **Best for performance-focused traders**
- Example: 80% profitable, PF 2.3

**Recommendation:**
- Use **Most Stable** if you prioritize avoiding losses
- Use **Top 10 Rank #1** if you can tolerate occasional losses for higher returns
- Often they're the same combo (ideal scenario)

## Integration with Other Analyses

### 1. Cross-Reference with Parameter Performance

**Parameter Performance** (only best combos tested):
```
min_confidence=0.60, cooldown=12
  Selected: 5 times
  Median OOS PF: 0.95
```

**Parameter Stability** (all combos tested):
```
min_confidence=0.60, cooldown=12
  Rank: 7/9
  Median Test PF: 0.95
  % Profit: 40%
  Selected: 5/5
```

**Combined Insight:**
- Training loved it (selected 5/5)
- Testing hates it (rank 7/9, only 40% profitable)
- **Clear overfitting** - don't use!

### 2. Cross-Reference with Degradation

**Degradation Analysis:**
```
Median PF Degradation: 0.45 (severe)
```

**Parameter Stability:**
```
Most selected combo (0.60, 12):
  Training PF: ~4.0
  Test PF: 0.95
  → Severe degradation confirmed
```

**Combined Insight:**
- Degradation shows overfitting is happening
- Stability shows which combo is overfitting
- Avoid that combo!

### 3. Cross-Reference with Monte Carlo

**Monte Carlo:**
```
P(final PnL < 0): 38%
MC Median DD: 95 pips
```

**Parameter Stability:**
```
Best combo (0.70, 48):
  % Profit: 100%
  Median PF: 2.15
```

**Combined Insight:**
- MC shows current best combo has 38% loss risk
- Stability shows (0.70, 48) has 0% loss rate (100% profitable)
- **Switch to (0.70, 48)** for better robustness!

## Real-World Example

### Training Results

```
Split 1: Best = (0.60, 12) | Train PF: 4.2
Split 2: Best = (0.60, 12) | Train PF: 3.8
Split 3: Best = (0.65, 24) | Train PF: 3.5
Split 4: Best = (0.70, 48) | Train PF: 3.2
Split 5: Best = (0.60, 12) | Train PF: 4.0
```

**Training says:** Use (0.60, 12) - selected 3/5 times

### Parameter Stability Results

```
Rank 1: (0.70, 48) | Med PF: 2.15 | % Profit: 100% | Selected: 1/5
Rank 2: (0.65, 24) | Med PF: 1.92 | % Profit: 100% | Selected: 1/5
Rank 7: (0.60, 12) | Med PF: 0.95 | % Profit: 40%  | Selected: 3/5
```

**Testing says:** Use (0.70, 48) - best test performance!

### Decision

**Without Stability Analysis:**
- Would use (0.60, 12) because training selected it most
- Would lose money (median PF 0.95 < 1.0)

**With Stability Analysis:**
- Use (0.70, 48) despite low selection rate
- Expect median PF 2.15 and 100% profitability
- **Correct decision!**

## Computational Cost

**Warning:** This analysis is computationally expensive.

Example:
- 9 parameter combinations
- 5 splits
- Total test backtests: 9 × 5 = **45 backtests**

**Mitigation:**
- Runs in parallel if you have multiple cores
- Each split's stability test runs sequentially but quickly
- Worth the cost for robust parameter selection

## Summary

**Parameter Stability Analysis reveals:**
1. **Hidden gems**: Combos that test well but train poorly
2. **Overfitting traps**: Combos that train well but test poorly
3. **True stability**: Which combos are consistently profitable

**Key Metrics:**
- **Top 10**: Best performers (by median test PF)
- **Most Stable**: Most consistent (by % profitable, then median PF)

**Decision Framework:**
- Require: **% Profitable ≥ 80%** and **Median PF ≥ 1.5**
- Prefer: **Most Stable** combo for live trading
- Avoid: High selection but poor test performance (overfitting)

**Integration:**
- Use with **Degradation** to detect overfitting
- Use with **Parameter Performance** to confirm selection bias
- Use with **Monte Carlo** to assess sequence risk

This analysis is the **final arbiter** of which parameters to use for live trading, overriding training preferences when they conflict with test reality!
