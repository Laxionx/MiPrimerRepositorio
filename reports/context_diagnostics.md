# Context Diagnostics v1

## All Backtest Candles

Observations: 50000

### Market Regime

| Value | Count | Percentage |
|---|---:|---:|
| trend | 27445 | 54.89% |
| range | 11108 | 22.22% |
| compression | 11354 | 22.71% |
| unknown | 93 | 0.19% |

### Context Score

| Value | Count | Percentage |
|---|---:|---:|
| 0 | 93 | 0.19% |
| 50 | 11354 | 22.71% |
| 55 | 11108 | 22.22% |
| 75 | 27445 | 54.89% |

### Context Bias

| Value | Count | Percentage |
|---|---:|---:|
| long | 13865 | 27.73% |
| short | 13580 | 27.16% |
| neutral | 22555 | 45.11% |

## Accepted Trades

Observations: 414

### Market Regime

| Value | Count | Percentage |
|---|---:|---:|
| trend | 414 | 100.00% |
| range | 0 | 0.00% |
| compression | 0 | 0.00% |
| unknown | 0 | 0.00% |

### Context Score

| Value | Count | Percentage |
|---|---:|---:|
| 75 | 414 | 100.00% |

### Context Bias

| Value | Count | Percentage |
|---|---:|---:|
| long | 185 | 44.69% |
| short | 229 | 55.31% |
| neutral | 0 | 0.00% |

### Entry Score

| Value | Count | Percentage |
|---|---:|---:|
| 85 | 414 | 100.00% |

## Score Statistics

| Score | Count | Min | Max | Mean | Median | Std Dev | Most Common |
|---|---:|---:|---:|---:|---:|---:|---|
| All candles context_score | 50000 | 0.0000 | 75.0000 | 64.7403 | 75.0000 | 11.6615 | 75 (27445) |
| Accepted trades context_score | 414 | 75.0000 | 75.0000 | 75.0000 | 75.0000 | 0.0000 | 75 (414) |
| Accepted trades entry_score | 414 | 85.0000 | 85.0000 | 85.0000 | 85.0000 | 0.0000 | 85 (414) |

## Conclusions

- ContextEngine variation sufficient: yes; 4 regimes and 4 context-score values observed.
- Context score tightly clustered in accepted trades: yes; accepted-trade standard deviation 0.0000, versus 11.6615 across all candles.
- Range detected: yes (11108 candles); compression detected: yes (11354 candles).
- EntryScore saturation at 85+: yes (100.00% of accepted trades).
