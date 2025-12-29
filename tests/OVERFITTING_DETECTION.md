# Overfitting Detection: Degradation Metrics

## Overview

The walk-forward analysis now includes **degradation metrics** to quickly detect overfitting by comparing in-sample (training) vs out-of-sample (testing) performance consistency.

## Degradation Metrics Explained

### 1. **PF Degradation** (Profit Factor Degradation)

**Formula:** `pf_degradation = test_pf / train_pf`

**Interpretation:**
- **1.0**: Perfect consistency (test PF = train PF)
- **0.8-1.0**: Good generalization (minimal degradation)
- **0.6-0.8**: Moderate overfitting (some degradation)
- **< 0.6**: High overfitting (severe degradation)

**Example:**
```
Train PF: 3.50
Test PF:  2.80
Degradation: 2.80 / 3.50 = 0.80 (Good - 80% retained)
```

### 2. **Expected Payoff Degradation**

**Formula:** `ep_degradation = test_ep / train_ep`

**Interpretation:**
- **1.0**: Perfect consistency (test EP = train EP)
- **0.8-1.0**: Good generalization
- **0.6-0.8**: Moderate overfitting
- **< 0.6**: High overfitting

**Example:**
```
Train Expected Payoff: 5.2 pips
Test Expected Payoff:  4.1 pips
Degradation: 4.1 / 5.2 = 0.79 (Moderate - 79% retained)
```

## Per-Split Display

After each walk-forward split completes, you'll see:

```
[TEST] Results - MT5 Style Report:
  ------------------------------------------------------------
  Trades                              15
  Profit trades (% of total)          9 (60.0%)
  ...
  Profit Factor                       2.80
  Expected Payoff                     4.10 pips
  ------------------------------------------------------------

[DEGRADATION] Train → Test Performance:
  ------------------------------------------------------------
  Profit Factor                       3.50 → 2.80 (0.80x)
  Expected Payoff                     5.20 → 4.10 (0.79x)
  Status                              ✓ Good (minimal degradation)
  ------------------------------------------------------------
```

## Aggregate Summary

After all splits complete, you'll see aggregate degradation metrics:

```
OVERFITTING DETECTION (Train → Test Degradation)
----------------------------------------------------------------------
Median PF Degradation                    0.85 (test/train ratio)
Worst PF Degradation                     0.62 (split 2)
Median Expected Payoff Degradation       0.82 (test/train ratio)
Worst Expected Payoff Degradation        0.58 (split 2)

Interpretation:
  ✓ Good: Median PF degradation 0.85 ≥ 0.8 (low overfitting)
======================================================================
```

## Interpretation Guidelines

### Median Degradation

**Why Median?**
- More robust to outliers than mean
- One bad split won't skew the overall assessment
- Better represents typical performance

**Thresholds:**

| Median PF Degradation | Status | Action |
|-----------------------|--------|--------|
| ≥ 0.8 | ✓ Good | Parameters generalize well - safe to use |
| 0.6 - 0.8 | ⚠ Moderate | Some overfitting - monitor closely |
| < 0.6 | ✗ Poor | High overfitting - don't use these parameters |

### Worst Degradation

**Why Track Worst?**
- Identifies splits where strategy completely fails OOS
- Helps understand worst-case scenarios
- Reveals parameter instability

**Warning Threshold:**
- If worst degradation < 0.5 → **severe degradation** in at least one split
- Strategy may be unreliable in certain market conditions

## Real-World Examples

### Example 1: Good Generalization ✓

```
Split 1:
  Train PF: 2.85 → Test PF: 2.50 (0.88x) ✓ Good
Split 2:
  Train PF: 3.10 → Test PF: 2.65 (0.85x) ✓ Good
Split 3:
  Train PF: 2.95 → Test PF: 2.40 (0.81x) ✓ Good

Aggregate:
  Median PF Degradation: 0.85 ✓
  Worst PF Degradation: 0.81
```

**Analysis:**
- Consistent 0.81-0.88 degradation across all splits
- Median 0.85 = retains 85% of training performance
- **Decision:** Parameters are robust, safe for live trading

### Example 2: Moderate Overfitting ⚠

```
Split 1:
  Train PF: 4.20 → Test PF: 3.15 (0.75x) ⚠ Moderate
Split 2:
  Train PF: 3.80 → Test PF: 2.50 (0.66x) ⚠ Moderate
Split 3:
  Train PF: 4.50 → Test PF: 3.00 (0.67x) ⚠ Moderate

Aggregate:
  Median PF Degradation: 0.67 ⚠
  Worst PF Degradation: 0.66
```

**Analysis:**
- Degradation 0.66-0.75 (moderate overfitting)
- Retains only 67% of training performance
- **Decision:** Monitor closely, consider more conservative parameters

### Example 3: High Overfitting ✗

```
Split 1:
  Train PF: 5.20 → Test PF: 1.10 (0.21x) ✗ High degradation
Split 2:
  Train PF: 6.50 → Test PF: 0.85 (0.13x) ✗ High degradation
Split 3:
  Train PF: 4.80 → Test PF: 1.50 (0.31x) ✗ High degradation

Aggregate:
  Median PF Degradation: 0.21 ✗
  Worst PF Degradation: 0.13
  ⚠ Warning: Worst split degradation 0.13 < 0.5 (severe degradation)
```

**Analysis:**
- Severe overfitting (retains only 13-31% of training performance)
- Training PF 4.8-6.5 but test PF only 0.85-1.5
- Parameters are likely fitting noise, not signal
- **Decision:** DO NOT use these parameters - severe overfitting

### Example 4: Inconsistent Performance ⚠

```
Split 1:
  Train PF: 2.80 → Test PF: 2.50 (0.89x) ✓ Good
Split 2:
  Train PF: 4.50 → Test PF: 1.20 (0.27x) ✗ High degradation
Split 3:
  Train PF: 3.20 → Test PF: 2.70 (0.84x) ✓ Good

Aggregate:
  Median PF Degradation: 0.84 ✓
  Worst PF Degradation: 0.27 ✗
  ⚠ Warning: Worst split degradation 0.27 < 0.5 (severe degradation in split 2)
```

**Analysis:**
- Median looks good (0.84) but worst is terrible (0.27)
- Strategy works well in most conditions but fails completely in split 2
- **Decision:** Investigate split 2 market conditions, strategy may be unstable

## Common Patterns

### Pattern 1: Consistent Low Degradation (Ideal)
```
All splits: 0.80-0.90x
Median: 0.85
Worst: 0.80
```
→ **Robust parameters, strategy generalizes well**

### Pattern 2: Gradual Degradation
```
Split 1: 0.85x
Split 2: 0.70x
Split 3: 0.55x
```
→ **Market regime change or parameter decay over time**

### Pattern 3: One Outlier
```
Split 1: 0.85x
Split 2: 0.25x (outlier)
Split 3: 0.82x
```
→ **Strategy fails in specific market conditions (investigate split 2)**

### Pattern 4: High Training PF, Poor Test
```
Train PF: 6.0+
Test PF: 1.0-1.5
Degradation: 0.20x
```
→ **Classic overfitting: parameters fitted to training noise**

## Actionable Insights

### If Median Degradation ≥ 0.8
✓ **Safe to proceed**
- Parameters generalize well
- Use these parameters for live trading
- Strategy is robust

### If Median Degradation 0.6-0.8
⚠ **Proceed with caution**
- Some overfitting present
- Consider more conservative parameters
- Monitor live performance closely
- Reduce position size initially

### If Median Degradation < 0.6
✗ **Do not use**
- High overfitting
- Parameters won't work live
- Redesign parameter grid with more conservative values
- Consider adding more regularization

### If Worst Degradation < 0.5 (Even if Median is Good)
⚠ **Investigate**
- Strategy may fail in certain market conditions
- Identify what's different about the worst split
- Consider adding filters to avoid those conditions
- Reduce risk during similar market conditions

## Advanced Usage

### 1. **Compare with Parameter Performance Analysis**

Cross-reference degradation with parameter selection frequency:

```
Parameter: min_confidence=0.60, cooldown=12
  Selected: 5 times
  Median Degradation: 0.45 ✗
→ Popular in training but poor OOS → Overfitting

Parameter: min_confidence=0.70, cooldown=48
  Selected: 2 times
  Median Degradation: 0.88 ✓
→ Less popular but robust → Best choice
```

### 2. **Track Degradation Across Different Param Combos**

Add degradation as a metric in parameter performance table:
- Low degradation + high selection = robust parameters
- High degradation + high selection = overfitting to training

### 3. **Use Degradation for Early Stopping**

If you see:
```
Split 1: 0.25x degradation
Split 2: 0.30x degradation
```
→ Stop walk-forward early, parameters are clearly overfitting

## Summary

**Key Metrics:**
- **Median PF Degradation**: Overall robustness (≥0.8 = good)
- **Worst PF Degradation**: Worst-case scenario (<0.5 = warning)
- **Per-Split Degradation**: Individual split analysis

**Decision Framework:**
1. Check median degradation (≥0.8 preferred)
2. Check worst degradation (≥0.5 acceptable)
3. If both pass → parameters are robust
4. If median fails → high overfitting, don't use
5. If worst fails but median passes → investigate failure conditions

**Remember:**
- **High training PF with low test PF = overfitting**
- **Consistent degradation across splits = robust parameters**
- **Median is more reliable than mean**
- **Always check worst-case degradation**

Use these metrics alongside parameter performance analysis for the most informed decision-making!
