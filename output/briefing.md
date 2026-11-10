# SKYVAULT briefing — military_urban_001 v0.2

## Summary

Scenario military_urban_001 v0.2: 528 events over 25 ticks.

- Result: no_winner_duration_limit
- Verdict: fail (confidence 1.00)
- Score: 0.29
- Profile: balanced, seen from RED

## What happened

Each tick: what was done, and who was destroyed by whom.

- Tick 1: 1 attack; 10 idle units; 1 move; 3 waits
- Tick 2: 4 attacks; 2 misses; 7 moves; 2 refused orders; Red 2nd squad Squad Leader destroyed by Blue Garrison Marksman
- Tick 3: 3 attacks; 1 idle unit; 2 misses; 2 moves; 5 refused orders; Blue Garrison Marksman destroyed by Red Support Marksman
- Tick 4: 3 attacks; 3 misses; 3 moves; 2 refused orders; 2 waits; Red 1st squad Rifleman 2 destroyed by Blue Garrison Rifleman 1
- Tick 5: 5 attacks; 1 idle unit; 3 moves; 1 refused order; 2 waits; Red Support Logistics destroyed by Blue Garrison Rifleman 1
- Tick 6: 4 attacks; 1 idle unit; 2 misses; 2 moves; 1 refused order; 1 wait; Red 2nd squad Rifleman 2 destroyed by Blue Garrison Squad Leader
- Tick 7: 2 attacks; 5 misses; 2 refused orders; 1 wait; Red 1st squad Squad Leader destroyed by Blue Garrison Rifleman 1
- Tick 8: 3 attacks; 1 idle unit; 5 misses
- Tick 9: 3 attacks; 5 misses; 1 wait; Red 1st squad Rifleman 1 destroyed by Blue Garrison Squad Leader
- Tick 10: 2 attacks; 4 misses; 2 waits; Red 1st squad Machine Gunner destroyed by Blue Garrison Rifleman 2
- Tick 11: 1 attack; 1 miss; 1 refused order; 4 waits
- Tick 12: 2 attacks; 3 misses; 1 move; 1 wait
- Tick 13: 2 attacks; 1 miss; 1 refused order; 3 waits; Red Support Marksman destroyed by Blue Garrison Rifleman 1
- Tick 14: 1 miss; 5 waits
- Tick 15: 1 miss; 5 waits
- Tick 16: 1 miss; 5 waits
- Tick 17: 1 miss; 5 waits
- Tick 18: 1 miss; 5 waits
- Tick 19: 1 refused order; 5 waits
- Tick 20: 1 attack; 1 miss; 1 move; 3 waits
- Tick 21: 1 idle unit; 5 waits
- Tick 22: 1 move; 5 waits
- Tick 23: 1 refused order; 5 waits
- Tick 24: 6 waits
- Tick 25: 6 waits

## Losses

- RED lost 8 of 10: Red 2nd squad Squad Leader at tick 2, Red 1st squad Rifleman 2 at tick 4, Red Support Logistics at tick 5, Red 2nd squad Rifleman 2 at tick 6, Red 1st squad Squad Leader at tick 7, Red 1st squad Rifleman 1 at tick 9, Red 1st squad Machine Gunner at tick 10, Red Support Marksman at tick 13
- BLUE lost 1 of 5: Blue Garrison Marksman at tick 3

## Evaluation

Scenario ended because: duration_limit_reached

Events recorded: 528

Destroyed entities: 9

Overall score 0.29 under profile balanced: fail (confidence 1.00)

Strongest axis: logistics_burden 1.00

Weakest axis: recovery_ability 0.00

- mission_success 0.20
- tactical_value 0.43
- strategic_value 0.20
- resource_cost 0.11
- time_cost 0.00
- risk_growth 0.20
- failure_resistance 0.08
- recovery_ability 0.00
- system_robustness 0.81
- logistics_burden 1.00
- stability_impact 0.40
- Failure cause: red_05 destroyed at tick 2 by blue_05
- Failure cause: red_03 destroyed at tick 4 by blue_02
- Failure cause: red_10 destroyed at tick 5 by blue_02
- Failure cause: red_07 destroyed at tick 6 by blue_01
- Failure cause: red_01 destroyed at tick 7 by blue_02
- Failure cause: red_02 destroyed at tick 9 by blue_01
- Failure cause: red_04 destroyed at tick 10 by blue_03
- Failure cause: red_09 destroyed at tick 13 by blue_02
- Failure cause: mission_success 0.20: 1 of 5 opposing entities destroyed; 2 of 10 own entities still active
- Failure cause: strategic_value 0.20: 2 of 10 own entities preserved
- Failure cause: resource_cost 0.11: 254 of 286 own hp lost
- Failure cause: time_cost 0.00: ended at tick 25 of 25
- Failure cause: risk_growth 0.20: 8 risk-relevant events hit own entities (proxy until a risk model exists)
- Failure cause: failure_resistance 0.08: first own loss at tick 2 of 25
- Failure cause: recovery_ability 0.00: 0 hp restored against 254 hp still lost

## Trade-offs

- tactical_value 0.43 against strategic_value 0.20: balanced
- mission_success 0.20 against resource_cost 0.11: both weak
- time_cost 0.00 against risk_growth 0.20: both weak
- mission_success 0.20 against stability_impact 0.40: balanced

## Failure exploration

v0.2 stressed 10 times per level; a level breaks below 50% survival.

- Survives without stress: 80%
- Crushed by: communication_failure (assumption actor_policy)
- Best alternative: None
- First loss on average at tick 2.0
- sensor_failure: holds up to severe, breaks at collapse
- communication_failure: holds up to severe, breaks at collapse
- weather_degradation: holds at every tested level
- enemy_reaction_speed: breaks already at mild
- equipment_overheat: holds up to severe, breaks at collapse

| Variable | mild | moderate | severe | collapse | Breaks at | Sensitivity |
|---|---|---|---|---|---|---|
| sensor_failure | 80% | 70% | 70% | 40% | collapse | +0.40 |
| communication_failure | 70% | 80% | 80% | 10% | collapse | +0.70 |
| weather_degradation | 80% | 100% | 90% | 100% | never | +0.00 |
| enemy_reaction_speed | 40% | 40% | 50% | 30% | mild | +0.50 |
| equipment_overheat | 80% | 80% | 50% | 20% | collapse | +0.60 |

## Plan comparison

Batch military_urban_001_doctrine: 50 runs per variant, 150 runs, seen from RED.

Conflicting orders: P1 vs P2 (objective, priority, risk); P1 vs P3 (location). Highest win_rate: branch P1 (0.12). Lowest failure_frequency: branch P2+P3 (0.19). Lowest mean_hp_lost: branch P1 (65.98). Lowest mean_risk_events: branch P1 (1.73). Highest mean_score: branch P1 (0.4128). SKYVAULT does not choose between the branches; NEXUS or the user decides which orders to keep.

- Best win rate: aggressive
- Best failure frequency: aggressive
- Best mean hp lost: defensive
- Best mean risk events: defensive
- Best mean score: aggressive
- Conflict C1: P1 vs P2 at tick 1: both order red_002; both high priority; risk medium vs low
- Conflict C2: P1 vs P3 at tick 1: both send a unit to [1, 1]
- Decision required: yes

| Variant | Win | Fail | HP lost | Risk | Score |
|---|---|---|---|---|---|
| aggressive | 18% | 12% | 201.64 | 6.36 | 0.379 |
| overwatch | 0% | 22% | 209.8 | 6.82 | 0.357 |
| defensive | 10% | 84% | 189.24 | 6.16 | 0.218 |

## Reproducibility

- Run: run_20261110T052243750831Z_089b5d39
- Random: seed 42 (fixed)
- Runtime 2.1.0, rules rules-4e2bb5389c00
- Input hash: 089b5d39939a0c98e8e5f2c0322f9879f2dac6d7f32744c2309ca795c4244969
- Output hash: 78aa3fe5bbdfc1b2828e2756c40fecf72982a7c8b208b97c441626afcb1c6c57
