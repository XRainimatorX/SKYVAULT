# Comparative report — airspace_defence_001_south_radar

Scenario `airspace_defence_001` v0.1, profile `balanced`, seen from DEFENCE; 10 runs per variant, 20 runs in all.

## Variants

| Variant | Kind | Win rate | 95% CI | Fail | HP lost | Risk events | Score | |
|---|---|---|---|---|---|---|---|---|
| sweep:entities[radar_south].state.online=True | sweep | 70% | 40%–89% | 30% | 0 | 0 | 0.797 | `██████████████` |
| sweep:entities[radar_south].state.online=False | sweep | 40% | 17%–69% | 60% | 0 | 0 | 0.693 | `████████` |

## Best per metric

- **win_rate** (higher is better): sweep:entities[radar_south].state.online=True
- **failure_frequency** (lower is better): sweep:entities[radar_south].state.online=True
- **mean_hp_lost** (lower is better): sweep:entities[radar_south].state.online=True
- **mean_risk_events** (lower is better): sweep:entities[radar_south].state.online=True
- **mean_score** (higher is better): sweep:entities[radar_south].state.online=True

Ranking by mean score: sweep:entities[radar_south].state.online=True > sweep:entities[radar_south].state.online=False
