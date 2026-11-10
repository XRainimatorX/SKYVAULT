# Comparative report — military_urban_001_doctrine

Scenario `military_urban_001` v0.1, profile `balanced`, seen from RED; 50 runs per variant, 150 runs in all.

## Variants

| Variant | Kind | Win rate | 95% CI | Fail | HP lost | Risk events | Score | |
|---|---|---|---|---|---|---|---|---|
| aggressive | version | 18% | 10%–31% | 12% | 201.64 | 6.36 | 0.379 | `████` |
| overwatch | version | 0% | 0%–7% | 22% | 209.8 | 6.82 | 0.357 | `·` |
| defensive | version | 10% | 4%–21% | 84% | 189.24 | 6.16 | 0.218 | `██` |

## Best per metric

- **win_rate** (higher is better): aggressive
- **failure_frequency** (lower is better): aggressive
- **mean_hp_lost** (lower is better): defensive
- **mean_risk_events** (lower is better): defensive
- **mean_score** (higher is better): aggressive

Ranking by mean score: aggressive > overwatch > defensive
