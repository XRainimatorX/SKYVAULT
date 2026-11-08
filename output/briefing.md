# SKYVAULT briefing — tactical_reference_001 v0.1

## Summary

Scenario tactical_reference_001 v0.1: 97 events over 10 ticks.

- Result: RED_survived
- Verdict: risky (confidence 0.92)
- Score: 0.50
- Profile: balanced, seen from RED

## What happened

Each tick: what was done, and who was destroyed by whom.

- Tick 1: 6 moves
- Tick 2: 6 moves
- Tick 3: 6 moves
- Tick 4: 1 miss; 5 moves
- Tick 5: 4 attacks; 2 misses
- Tick 6: 4 attacks; 1 move; Blue Commander destroyed by Red Rifleman; Red Commander destroyed by Blue Support
- Tick 7: 1 attack; 2 moves; Blue Support destroyed by Red Support
- Tick 8: 2 attacks; 1 miss
- Tick 9: 1 attack; 2 misses
- Tick 10: 2 attacks; Blue Rifleman destroyed by Red Support

## Losses

- RED lost 1 of 3: Red Commander at tick 6
- BLUE lost 3 of 3: Blue Commander at tick 6, Blue Support at tick 7, Blue Rifleman at tick 10

## Evaluation

Scenario ended because: termination_condition_met

Events recorded: 97

Destroyed entities: 4

Overall score 0.50 under profile balanced: risky (confidence 0.92)

Strongest axis: mission_success 1.00

Weakest axis: recovery_ability 0.00

- mission_success 1.00
- tactical_value 1.00
- strategic_value 0.67
- resource_cost 0.59
- time_cost 0.00
- risk_growth 0.67
- failure_resistance 0.60
- recovery_ability 0.00
- system_robustness 1.00
- stability_impact 0.33
- Failure cause: red_003 destroyed at tick 6 by blue_002
- Failure cause: time_cost 0.00: ended at tick 10 of 10
- Failure cause: recovery_ability 0.00: 0 hp restored against 40 hp still lost
- Failure cause: Anti-gaming: sacrifice_long_term_stability_for_short_term_success
- Next test: Exercise logistics_burden: the world holds no resources to spend
- Next test: Check whether sacrifice_long_term_stability_for_short_term_success was intended: prevent fast success that destroys long-term order
- Flagged: sacrifice_long_term_stability_for_short_term_success

## Trade-offs

- tactical_value 1.00 against strategic_value 0.67: both strong
- mission_success 1.00 against resource_cost 0.59: balanced
- time_cost 0.00 against risk_growth 0.67: risk_growth kept at the expense of time_cost
- mission_success 1.00 against stability_impact 0.33: mission_success bought at the expense of stability_impact

## Failure exploration

v0.1 stressed 10 times per level; a level breaks below 50% survival.

- Survives without stress: 60%
- Crushed by: communication_failure (assumption actor_policy)
- Best alternative: v0.1-support-rear
- First loss on average at tick 6.1
- sensor_failure: holds at every tested level
- communication_failure: holds up to severe, breaks at collapse
- weather_degradation: holds at every tested level
- enemy_reaction_speed: holds up to moderate, breaks at severe
- equipment_overheat: holds up to severe, breaks at collapse
- civilian_pressure: holds up to severe, breaks at collapse

| Variable | mild | moderate | severe | collapse | Breaks at | Sensitivity |
|---|---|---|---|---|---|---|
| sensor_failure | 60% | 70% | 70% | 60% | never | +0.00 |
| communication_failure | 70% | 80% | 50% | 0% | collapse | +0.60 |
| weather_degradation | 70% | 80% | 100% | 60% | never | +0.00 |
| enemy_reaction_speed | 50% | 50% | 40% | 20% | severe | +0.40 |
| equipment_overheat | 60% | 70% | 70% | 0% | collapse | +0.60 |
| civilian_pressure | 80% | 70% | 70% | 10% | collapse | +0.50 |

## Plan comparison

Batch tactical_reference_001_doctrine: 100 runs per variant, 900 runs, seen from RED.

Conflicting orders: P1 vs P2 (objective, priority, risk); P1 vs P3 (location). Highest win_rate: branch P1 (0.12). Lowest failure_frequency: branch P2+P3 (0.19). Lowest mean_hp_lost: branch P1 (65.98). Lowest mean_risk_events: branch P1 (1.73). Highest mean_score: branch P1 (0.4128). SKYVAULT does not choose between the branches; NEXUS or the user decides which orders to keep.

- Best win rate: support-rear
- Best failure frequency: support-rear
- Best mean hp lost: support-rear
- Best mean risk events: support-rear
- Best mean score: support-rear
- Conflict C1: P1 vs P2 at tick 1: both order red_002; both high priority; risk medium vs low
- Conflict C2: P1 vs P3 at tick 1: both send a unit to [1, 1]
- Decision required: yes

| Variant | Win | Fail | HP lost | Risk | Score |
|---|---|---|---|---|---|
| plan | 6% | 27% | 69.05 | 1.92 | 0.395 |
| support-rear | 17% | 17% | 61.79 | 1.61 | 0.434 |
| spread | 12% | 21% | 67.96 | 1.83 | 0.415 |
| sweep:entities[blue_002].capabilities.accuracy=0.55 | 6% | 27% | 69.05 | 1.92 | 0.395 |
| sweep:entities[blue_002].capabilities.accuracy=0.65 | 7% | 38% | 74.6 | 2.11 | 0.362 |
| sweep:entities[blue_002].capabilities.accuracy=0.75 | 3% | 41% | 79.21 | 2.22 | 0.343 |
| branch:P1 | 12% | 23% | 65.98 | 1.73 | 0.413 |
| branch:P2+P3 | 3% | 19% | 68.43 | 1.83 | 0.404 |
| branch:none | 6% | 27% | 69.05 | 1.92 | 0.395 |

## Reproducibility

- Run: run_20261108T032529810557Z_5e71d369
- Random: seed 42 (fixed)
- Runtime 0.11.0, rules rules-2438b4a50419
- Input hash: 5e71d369a6d87f35faf23d1c6f3289da60bede8b1a43de0d843402f6420fd14e
- Output hash: 63090026e13734f596339fe2129a4d17cbd43499f72c87cb0dbec5cdf9f5fd09
