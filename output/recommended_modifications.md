# Recommended modifications — military_urban_001 v0.2

- Perspective: RED, profile `balanced`
- Runs per stressed plan: 10
- Survives without stress: 80% of runs
- Crushed by: communication_failure (attacks the assumption `actor_policy`)

## Must change before acting

1. **communication_failure** breaks the plan at collapse: Give units standing orders that still work when orders do not get through.
2. **equipment_overheat** breaks the plan at collapse: Budget for lower sustained damage, or rotate weapons to avoid overheating.
3. **enemy_reaction_speed** breaks the plan at mild: Do not assume a slow enemy: plan for an opponent that hits harder and sooner.
4. **sensor_failure** breaks the plan at collapse: Add redundant sensing, or plan engagements that do not rely on long-range accuracy.

## Where and why it fails

- red_05 lost at tick 2 to blue_03 (34 of 83 failed runs)
- red_05 lost at tick 2 to blue_05 (26 of 83 failed runs)
- red_10 lost at tick 2 to blue_05 (16 of 83 failed runs)
- red_03 lost at tick 2 to blue_04 (2 of 83 failed runs)
- red_06 lost at tick 2 to blue_04 (2 of 83 failed runs)
- failure_resistance too low in 83 of 83 failed runs
- recovery_ability too low in 83 of 83 failed runs
- resource_cost too low in 73 of 83 failed runs
- time_cost too low in 68 of 83 failed runs
- mission_success too low in 64 of 83 failed runs
- risk_growth too low in 61 of 83 failed runs
- strategic_value too low in 61 of 83 failed runs
- tactical_value too low in 29 of 83 failed runs
- stability_impact too low in 27 of 83 failed runs
- Anti-gaming: sacrifice_strategic_value_for_short_term_tactical_value in 19 of 83 failed runs
- Anti-gaming: sacrifice_long_term_stability_for_short_term_success in 14 of 83 failed runs
- system_robustness too low in 9 of 83 failed runs

## Survival conditions

- sensor_failure: holds up to severe, breaks at collapse
- communication_failure: holds up to severe, breaks at collapse
- weather_degradation: holds at every tested level
- enemy_reaction_speed: breaks already at mild
- equipment_overheat: holds up to severe, breaks at collapse
