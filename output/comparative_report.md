# Comparative report — tactical_reference_001_doctrine

Scenario `tactical_reference_001` v0.1, profile `balanced`, seen from RED; 100 runs per variant, 900 runs in all.

## Variants

| Variant | Kind | Win rate | 95% CI | Fail | HP lost | Risk events | Score | |
|---|---|---|---|---|---|---|---|---|
| plan | version | 6% | 3%–12% | 27% | 69.05 | 1.92 | 0.395 | `█` |
| support-rear | version | 17% | 11%–26% | 17% | 61.79 | 1.61 | 0.434 | `███` |
| spread | version | 12% | 7%–20% | 21% | 67.96 | 1.83 | 0.415 | `██` |
| sweep:entities[blue_002].capabilities.accuracy=0.55 | sweep | 6% | 3%–12% | 27% | 69.05 | 1.92 | 0.395 | `█` |
| sweep:entities[blue_002].capabilities.accuracy=0.65 | sweep | 7% | 3%–14% | 38% | 74.6 | 2.11 | 0.362 | `█` |
| sweep:entities[blue_002].capabilities.accuracy=0.75 | sweep | 3% | 1%–8% | 41% | 79.21 | 2.22 | 0.343 | `█` |
| branch:P1 | branch | 12% | 7%–20% | 23% | 65.98 | 1.73 | 0.413 | `██` |
| branch:P2+P3 | branch | 3% | 1%–8% | 19% | 68.43 | 1.83 | 0.404 | `█` |
| branch:none | branch | 6% | 3%–12% | 27% | 69.05 | 1.92 | 0.395 | `█` |

## Best per metric

- **win_rate** (higher is better): support-rear
- **failure_frequency** (lower is better): support-rear
- **mean_hp_lost** (lower is better): support-rear
- **mean_risk_events** (lower is better): support-rear
- **mean_score** (higher is better): support-rear

Ranking by mean score: support-rear > spread > branch:P1 > branch:P2+P3 > plan > sweep:entities[blue_002].capabilities.accuracy=0.55 > branch:none > sweep:entities[blue_002].capabilities.accuracy=0.65 > sweep:entities[blue_002].capabilities.accuracy=0.75

## Conflicting orders

- C1: P1 vs P2 at tick 1: both order red_002; both high priority; risk medium vs low (objective_conflict, priority_conflict, risk_conflict)
- C2: P1 vs P3 at tick 1: both send a unit to [1, 1] (location_conflict)

| Branch | Orders | Result | Δ score vs baseline |
|---|---|---|---|
| P1 | P1 | 100 runs: win 12% (95% CI 7%–20%), loss 19%, draw 69%; fail verdict 23%; mean hp lost 65.98, risk events 1.73, score 0.413 | +0.0180 |
| P2+P3 | P2, P3 | 100 runs: win 3% (95% CI 1%–8%), loss 13%, draw 84%; fail verdict 19%; mean hp lost 68.43, risk events 1.83, score 0.404 | +0.0091 |
| none | — | 100 runs: win 6% (95% CI 3%–12%), loss 25%, draw 69%; fail verdict 27%; mean hp lost 69.05, risk events 1.92, score 0.395 | +0.0000 |

Decision required: **yes**

Conflicting orders: P1 vs P2 (objective, priority, risk); P1 vs P3 (location). Highest win_rate: branch P1 (0.12). Lowest failure_frequency: branch P2+P3 (0.19). Lowest mean_hp_lost: branch P1 (65.98). Lowest mean_risk_events: branch P1 (1.73). Highest mean_score: branch P1 (0.4128). SKYVAULT does not choose between the branches; NEXUS or the user decides which orders to keep.
