# Monte Carlo Trade Order Reshuffle Analysis

## Overview

The Monte Carlo (MC) simulation shuffles the order of trades and measures how much performance depends on **sequence luck**. This reveals whether your results are robust or just happened to occur in a favorable order.

## What It Does

For each split's test trades:
1. **Extract** all trade PnLs in chronological order
2. **Shuffle** the order 1,000 times (Monte Carlo simulations)
3. **Recalculate** equity curve and max drawdown for each shuffle
4. **Measure** distribution of outcomes

## Key Metrics

### Per-Split Display

After each split completes, you'll see:

```
[MONTE CARLO] Trade Order Reshuffle (N=1000 simulations):
  ------------------------------------------------------------
  Observed Max DD                     45.2 pips
  MC Median Max DD                    52.3 pips
  MC 95th Percentile DD               78.5 pips
  MC Maximum DD                       95.7 pips
  P(final PnL < 0)                    15.2%
  P(DD > observed)                    68.5%
  Interpretation                      ✓ Lucky sequence (obs < median)
  ------------------------------------------------------------
```

### Aggregate Summary

After all splits complete:

```
======================================================================
MONTE CARLO ANALYSIS - Sequence Risk (Trade Order Reshuffle)
======================================================================

Drawdown Statistics (averaged across splits):
Observed Avg Max DD                      47.8 pips
MC Median Max DD                         55.3 pips
MC 95th Percentile DD                    82.1 pips
MC Maximum DD (worst split)              112.4 pips

Sequence Risk:
Avg P(final PnL < 0)                     12.5%
Avg P(DD > observed)                     65.3%

Interpretation:
  ✓ Lucky: Observed DD 0.86x median (got favorable trade order)
  ✓ Low Risk: 12.5% probability of loss with random order
======================================================================
```

## Metric Explanations

### 1. **Observed Max DD**
- The actual max drawdown from your chronological trade order
- What you saw in the backtest

### 2. **MC Median Max DD**
- Median max drawdown across 1,000 shuffled scenarios
- **More realistic** estimate of typical drawdown
- Not biased by lucky/unlucky sequence

### 3. **MC 95th Percentile DD**
- 95% of shuffled scenarios had DD below this value
- **Worst-case planning**: 5% chance of exceeding this DD
- Use for risk management

### 4. **MC Maximum DD**
- Worst possible drawdown across all 1,000 shuffles
- **Absolute worst case** for this set of trades
- Useful for stress testing

### 5. **P(final PnL < 0)**
- Probability of ending with a loss if trades were reshuffled
- **Strategy fragility**: higher = more dependent on sequence
- <20% = robust, 20-40% = moderate risk, >40% = fragile

### 6. **P(DD > observed)**
- Probability of worse drawdown than observed
- **Sequence luck**: higher = you got lucky with order
- >70% = lucky, 30-70% = typical, <30% = unlucky

## Interpretation Guide

### Scenario 1: Lucky Sequence ✓

```
Observed Max DD:     45.2 pips
MC Median Max DD:    65.8 pips
P(DD > observed):    78.5%
```

**Analysis:**
- Observed DD (45.2) is much less than median (65.8)
- 78.5% of shuffled scenarios had worse DD
- **You got lucky** with trade order

**Implication:**
- Don't expect this low DD in live trading
- Use MC Median DD (65.8) for risk planning
- Strategy is fine, just don't rely on favorable sequence

### Scenario 2: Unlucky Sequence ⚠

```
Observed Max DD:     85.3 pips
MC Median Max DD:    52.1 pips
P(DD > observed):    12.3%
```

**Analysis:**
- Observed DD (85.3) is much worse than median (52.1)
- Only 12.3% of shuffled scenarios had worse DD
- **You got unlucky** with trade order

**Implication:**
- Live trading will likely be better than backtest
- Observed DD is pessimistic
- Strategy is actually more robust than it appears

### Scenario 3: Typical Sequence ~

```
Observed Max DD:     58.7 pips
MC Median Max DD:    55.3 pips
P(DD > observed):    47.2%
```

**Analysis:**
- Observed DD (58.7) close to median (55.3)
- ~50% of shuffled scenarios had worse DD
- **Typical sequence** - not particularly lucky or unlucky

**Implication:**
- Observed DD is representative
- Can use observed DD for risk planning
- No sequence bias

### Scenario 4: Fragile Strategy ✗

```
P(final PnL < 0):    45.8%
MC Median Max DD:    125.3 pips
MC 95th Percentile:  198.7 pips
```

**Analysis:**
- 45.8% chance of loss with reshuffled order
- High variation in possible outcomes
- Performance heavily depends on sequence

**Implication:**
- **Don't use this strategy**
- Results are sequence-dependent, not skill-based
- Strategy lacks robustness

### Scenario 5: Robust Strategy ✓

```
P(final PnL < 0):    5.2%
MC Median Max DD:    42.3 pips
MC 95th Percentile:  58.7 pips
```

**Analysis:**
- Only 5.2% chance of loss with reshuffled order
- Low variation in outcomes
- Consistent regardless of sequence

**Implication:**
- **Robust strategy**
- Performance is skill-based, not luck-based
- Safe for live trading

## Practical Decision Making

### Risk Planning

Use **MC 95th Percentile DD** for risk management:

```
MC 95th Percentile DD: 82.1 pips
```

**Action:**
- Plan for DD of ~82 pips (not the lucky 45 pips observed)
- Size positions assuming 82-pip drawdown
- Set stop-loss levels accordingly

### Position Sizing

```
Account Size: $10,000
Max Acceptable DD: 10% = $1,000
MC 95th Percentile DD: 82.1 pips
USD per pip at 1.0 lot: $10

Safe Position Size:
  $1,000 / (82.1 pips × $10) = 1.22 lots maximum
```

### Strategy Approval Checklist

**✓ Safe to proceed if:**
- P(final PnL < 0) < 20%
- MC Median DD is acceptable for your risk tolerance
- Observed DD vs MC Median DD ratio is 0.8-1.2 (typical sequence)

**⚠ Proceed with caution if:**
- P(final PnL < 0) = 20-40%
- Large gap between observed and MC Median DD
- MC 95th Percentile DD exceeds your risk limits

**✗ Do not use if:**
- P(final PnL < 0) > 40%
- MC 95th Percentile DD is unacceptable
- High variation in MC results (fragile strategy)

## Advanced Usage

### Cross-Reference with Degradation Metrics

Combine MC analysis with degradation metrics for full picture:

```
[DEGRADATION]
  Train PF: 3.50 → Test PF: 2.80 (0.80x)
  Status: ✓ Good

[MONTE CARLO]
  P(final PnL < 0): 8.5%
  P(DD > observed): 52.3%
  Interpretation: ~ Typical sequence
```

**Combined Analysis:**
- ✓ Good train-test consistency (0.80x degradation)
- ✓ Low loss probability (8.5%)
- ✓ Typical sequence (not lucky)
- **Decision:** Strong strategy, safe to use

### Identify Sequence-Dependent Parameters

Compare MC metrics across different parameter combinations:

```
Params A (min_conf=0.60, cool=12):
  P(final PnL < 0): 42.5% ✗
  → Fragile, sequence-dependent

Params B (min_conf=0.70, cool=48):
  P(final PnL < 0): 8.2% ✓
  → Robust, not sequence-dependent
```

**Decision:** Use Params B (more robust to trade order)

## Real-World Examples

### Example 1: False Confidence

**Backtest Results:**
```
Test PnL: +185.3 pips
Max DD: 28.5 pips
Profit Factor: 3.2
```

**Looks great!** But then Monte Carlo reveals:

```
MC Median Max DD: 75.8 pips
P(final PnL < 0): 38.5%
P(DD > observed): 89.2%
```

**Reality Check:**
- You got extremely lucky (89.2% had worse DD)
- 38.5% chance of loss with different order
- Expect DD of ~76 pips, not 28 pips
- **Strategy is fragile** despite good backtest

### Example 2: Hidden Robustness

**Backtest Results:**
```
Test PnL: +52.3 pips
Max DD: 95.7 pips
Profit Factor: 1.4
```

**Looks mediocre.** But Monte Carlo reveals:

```
MC Median Max DD: 58.3 pips
P(final PnL < 0): 6.8%
P(DD > observed): 8.5%
```

**Reality Check:**
- You got unlucky (only 8.5% had worse DD)
- 93.2% chance of profit with different order
- Typical DD is ~58 pips, not 95 pips
- **Strategy is robust** despite poor backtest

### Example 3: Perfect Scenario

**Backtest Results:**
```
Test PnL: +125.8 pips
Max DD: 45.2 pips
Profit Factor: 2.5
```

**Monte Carlo:**
```
MC Median Max DD: 48.7 pips
P(final PnL < 0): 4.2%
P(DD > observed): 48.5%
```

**Combined:**
```
PF Degradation: 0.85x (good)
MC P(loss): 4.2% (excellent)
Sequence: Typical (48.5%)
```

**Decision:**
- ✓ Good degradation (not overfitting)
- ✓ Low loss risk (robust)
- ✓ Typical sequence (not lucky)
- **USE THIS STRATEGY** for live trading

## Common Pitfalls

### Pitfall 1: Ignoring MC Results

**Mistake:**
```
Observed DD: 25 pips (great!)
MC Median DD: 80 pips (ignored)
→ Trades live with 25-pip risk assumption
→ Gets hit with 80-pip drawdown
→ Account blown
```

**Solution:** Always use MC Median or 95th percentile for risk planning

### Pitfall 2: Misinterpreting Luck

**Mistake:**
```
P(DD > observed): 85%
User thinks: "85% confidence level" ✓
Reality: "You got lucky, 85% had worse DD" ⚠
```

**Solution:** High P(DD > observed) = you got LUCKY, not confident

### Pitfall 3: Accepting Fragility

**Mistake:**
```
P(final PnL < 0): 45%
User thinks: "Still 55% chance of profit" ✓
Reality: "Strategy is gambling, not skill" ✗
```

**Solution:** Reject strategies with >30% loss probability

## Summary

**Monte Carlo Analysis Reveals:**
1. **Sequence Luck**: Did you get favorable trade order?
2. **Strategy Fragility**: Is performance sequence-dependent?
3. **Realistic Risk**: What's the typical/worst-case DD?

**Key Takeaways:**
- Use **MC Median DD** for realistic planning (not observed DD)
- Use **MC 95th Percentile DD** for worst-case scenario
- Require **P(final PnL < 0) < 20%** for robust strategy
- Check **P(DD > observed)** to detect sequence bias

**Decision Framework:**
| Metric | Good | Moderate | Poor |
|--------|------|----------|------|
| P(loss) | <20% | 20-40% | >40% |
| P(DD>obs) | 30-70% | <30% or >70% | N/A |
| MC Med/Obs | 0.8-1.2 | 0.6-0.8 or 1.2-1.5 | <0.6 or >1.5 |

Use Monte Carlo analysis alongside degradation metrics and parameter performance analysis for comprehensive strategy evaluation!
