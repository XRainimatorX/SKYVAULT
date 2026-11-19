# Recommended modifications — tactical_reference_001 v0.1

- Perspective: RED, profile `balanced`
- Runs per stressed plan: 2
- Survives without stress: 50% of runs
- Crushed by: enemy_reaction_speed (attacks the assumption `combat_resolution`)

## Must change before acting

1. **enemy_reaction_speed** breaks the plan at severe: Do not assume a slow enemy: plan for an opponent that hits harder and sooner.
2. **communication_failure** breaks the plan at collapse: Give units standing orders that still work when orders do not get through.
3. **equipment_overheat** breaks the plan at collapse: Budget for lower sustained damage, or rotate weapons to avoid overheating.
4. **civilian_pressure** breaks the plan at collapse: Hold forces in reserve for civilian demands, or plan with fewer effective units.
5. Consider the alternative **v0.1-support-rear**: it holds longer on baseline, communication_failure, enemy_reaction_speed, civilian_pressure.

## Where and why it fails

- red_003 lost at tick 6 to blue_002 (12 of 23 failed runs)
- red_003 lost at tick 5 to blue_003 (4 of 23 failed runs)
- red_003 lost at tick 5 to blue_002 (2 of 23 failed runs)
- red_003 lost at tick 6 to blue_001 (2 of 23 failed runs)
- red_003 lost at tick 7 to blue_001 (1 of 23 failed runs)
- mission_success too low in 23 of 23 failed runs
- time_cost too low in 23 of 23 failed runs
- recovery_ability too low in 22 of 23 failed runs
- crisis_resilience too low in 21 of 23 failed runs
- resource_cost too low in 21 of 23 failed runs
- risk_growth too low in 19 of 23 failed runs
- strategic_value too low in 19 of 23 failed runs
- tactical_usefulness too low in 4 of 23 failed runs
- stability_impact too low in 3 of 23 failed runs
- system_robustness too low in 1 of 23 failed runs

## Survival conditions

- sensor_failure: holds at every tested level
- communication_failure: holds up to severe, breaks at collapse
- weather_degradation: holds at every tested level
- enemy_reaction_speed: holds up to moderate, breaks at severe
- equipment_overheat: holds up to severe, breaks at collapse
- civilian_pressure: holds up to severe, breaks at collapse
