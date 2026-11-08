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

- BLUE lost 3 of 3: Blue Commander at tick 6, Blue Support at tick 7, Blue Rifleman at tick 10
- RED lost 1 of 3: Red Commander at tick 6

## Evaluation

Scenario ended because: termination_condition_met

Events recorded: 97

Destroyed entities: 4

Overall score 0.50 under profile balanced: risky (confidence 0.92)

Strongest axis: mission_success 1.00

Weakest axis: recovery_ability 0.00

- failure_resistance 0.60
- mission_success 1.00
- recovery_ability 0.00
- resource_cost 0.59
- risk_growth 0.67
- stability_impact 0.33
- strategic_value 0.67
- system_robustness 1.00
- tactical_value 1.00
- time_cost 0.00
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

## Reproducibility

- Run: run_20261108T181129448172Z_5e71d369
- Random: seed 42 (fixed)
- Runtime 0.17.0, rules rules-2438b4a50419
- Input hash: 5e71d369a6d87f35faf23d1c6f3289da60bede8b1a43de0d843402f6420fd14e
- Output hash: 63090026e13734f596339fe2129a4d17cbd43499f72c87cb0dbec5cdf9f5fd09
