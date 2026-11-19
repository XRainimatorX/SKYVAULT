# SKYVAULT briefing — tactical_reference_001 v0.2

## Summary

Scenario tactical_reference_001 v0.2: 91 events over 9 ticks.

- Result: BLUE_survived
- Verdict: fail (confidence 0.93)
- Score: 0.20
- Profile: balanced, seen from RED

## What happened

Each tick: what was done, and who was destroyed by whom.

- Tick 1: 6 moves
- Tick 2: 6 moves
- Tick 3: 6 moves
- Tick 4: 1 attack; 5 moves
- Tick 5: 5 attacks; 1 miss; Red Commander destroyed by Blue Support
- Tick 6: 3 attacks; 1 move; Blue Commander destroyed by Red Rifleman
- Tick 7: 1 attack; 2 misses; 1 move; Red Support destroyed by Blue Rifleman
- Tick 8: 2 attacks; 1 move
- Tick 9: 2 attacks; Red Rifleman destroyed by Blue Rifleman

## Losses

- RED lost 3 of 3: Red Commander at tick 5, Red Support at tick 7, Red Rifleman at tick 9
- BLUE lost 1 of 3: Blue Commander at tick 6

## Evaluation

Scenario ended because: termination_condition_met

Events recorded: 91

Destroyed entities: 4

Overall score 0.20 under profile balanced: fail (confidence 0.93)

Strongest axis: system_robustness 1.00

Weakest axis: crisis_resilience 0.00

- tactical_usefulness 0.61
- strategic_value 0.00
- crisis_resilience 0.00
- resource_efficiency 0.00
- risk_control 0.00
- system_robustness 1.00
- failure_resistance 0.56
- recovery_ability 0.00
- mission_success 0.00
- time_cost 0.10
- stability_impact 0.33
- commercial_demonstrability 0.67
- imperial_core_value 1.00
- resource_cost 0.00
- risk_growth 0.00
- Not judged in this world: physical_possibility, engineering_feasibility, governance_stability
- Failure cause: red_003 destroyed at tick 5 by blue_002
- Failure cause: red_002 destroyed at tick 7 by blue_001
- Failure cause: red_001 destroyed at tick 9 by blue_001
- Failure cause: mission_success 0.00: 1 of 3 opposing entities destroyed; 0 of 3 own entities still active
- Failure cause: strategic_value 0.00: 0 of 3 own entities preserved
- Failure cause: resource_cost 0.00: 97 of 97 own hp lost
- Failure cause: time_cost 0.10: ended at tick 9 of 10
- Failure cause: risk_growth 0.00: 3 risk-relevant events hit own entities (proxy until a risk model exists)
- Failure cause: recovery_ability 0.00: 0 hp restored against 97 hp still lost
- Failure cause: crisis_resilience 0.00: own strength at its lowest 0 of 97 hp (tick 9)
- Next test: Exercise logistics_burden: the world holds no resources to spend

## Trade-offs

- tactical_usefulness 0.61 against strategic_value 0.00: tactical_usefulness bought at the expense of strategic_value
- mission_success 0.00 against resource_cost 0.00: both weak
- time_cost 0.10 against risk_growth 0.00: both weak
- mission_success 0.00 against stability_impact 0.33: both weak

## Failure exploration

v0.1 stressed 2 times per level; a level breaks below 50% survival.

- Survives without stress: 50%
- Crushed by: enemy_reaction_speed (assumption combat_resolution)
- Best alternative: v0.1-support-rear
- First loss on average at tick 5.9
- sensor_failure: holds at every tested level
- communication_failure: holds up to severe, breaks at collapse
- weather_degradation: holds at every tested level
- enemy_reaction_speed: holds up to moderate, breaks at severe
- equipment_overheat: holds up to severe, breaks at collapse
- civilian_pressure: holds up to severe, breaks at collapse

| Variable | mild | moderate | severe | collapse | Breaks at | Sensitivity |
|---|---|---|---|---|---|---|
| sensor_failure | 50% | 50% | 100% | 100% | never | +0.00 |
| communication_failure | 50% | 100% | 100% | 0% | collapse | +0.50 |
| weather_degradation | 50% | 50% | 100% | 100% | never | +0.00 |
| enemy_reaction_speed | 50% | 50% | 0% | 0% | severe | +0.50 |
| equipment_overheat | 50% | 50% | 100% | 0% | collapse | +0.50 |
| civilian_pressure | 50% | 50% | 100% | 0% | collapse | +0.50 |

## Plan comparison

Batch tactical_reference_001_doctrine: 10 runs per variant, 90 runs, seen from RED.

Conflicting orders: P1 vs P2 (objective, priority, risk); P1 vs P3 (location). Highest win_rate: branch P1 (0.4). Lowest failure_frequency: branch P1 (0.1). Lowest mean_hp_lost: branch P1 (59.8). Lowest mean_risk_events: branch P1 (1.4). Highest mean_score: branch P1 (0.4495). SKYVAULT does not choose between the branches; NEXUS or the user decides which orders to keep.

- Best win rate: spread
- Best failure frequency: support-rear
- Best mean hp lost: branch:P1
- Best mean risk events: branch:P1
- Best mean score: branch:P1
- Conflict C1: P1 vs P2 at tick 1: both order red_002; both high priority; risk medium vs low
- Conflict C2: P1 vs P3 at tick 1: both send a unit to [1, 1]
- Decision required: yes

| Variant | Win | Fail | HP lost | Risk | Score |
|---|---|---|---|---|---|
| plan | 20% | 40% | 70.4 | 2.1 | 0.344 |
| support-rear | 10% | 10% | 64 | 1.6 | 0.412 |
| spread | 40% | 10% | 62.6 | 1.6 | 0.421 |
| sweep:entities[blue_002].capabilities.accuracy=0.55 | 20% | 40% | 70.4 | 2.1 | 0.344 |
| sweep:entities[blue_002].capabilities.accuracy=0.65 | 20% | 50% | 72.9 | 2.2 | 0.327 |
| sweep:entities[blue_002].capabilities.accuracy=0.75 | 10% | 50% | 78.7 | 2.3 | 0.312 |
| branch:P1 | 40% | 10% | 59.8 | 1.4 | 0.450 |
| branch:P2+P3 | 0% | 20% | 60.9 | 1.7 | 0.402 |
| branch:none | 20% | 40% | 70.4 | 2.1 | 0.344 |

## Reproducibility

- Run: run_20261119T050908076006Z_6f201ad3
- Random: seed 42 (fixed)
- Runtime 2.2.0, rules rules-f8f8b883e670
- Input hash: 6f201ad3d0592653d27cb02d13261c3dc8a9df72e66cb09e0051a47abd65be25
- Output hash: 8ad119066384116ad01b7776668b02c53232c1f7ccadae362a42f3ba448ebcaf
