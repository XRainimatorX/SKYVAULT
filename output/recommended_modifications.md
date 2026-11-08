# Recommended modifications — tactical_reference_001 v0.1

- Perspective: RED, profile `balanced`
- Runs per stressed plan: 10
- Survives without stress: 60% of runs
- Crushed by: communication_failure (attacks the assumption `actor_policy`)

## Must change before acting

1. **communication_failure** breaks the plan at collapse: Give units standing orders that still work when orders do not get through.
2. **equipment_overheat** breaks the plan at collapse: Budget for lower sustained damage, or rotate weapons to avoid overheating.
3. **civilian_pressure** breaks the plan at collapse: Hold forces in reserve for civilian demands, or plan with fewer effective units.
4. **enemy_reaction_speed** breaks the plan at severe: Do not assume a slow enemy: plan for an opponent that hits harder and sooner.
5. Consider the alternative **v0.1-support-rear**: it holds longer on baseline, enemy_reaction_speed.

## Where and why it fails

- red_003 lost at tick 6 to blue_001 (23 of 112 failed runs)
- red_003 lost at tick 6 to blue_002 (21 of 112 failed runs)
- red_003 lost at tick 5 to blue_002 (20 of 112 failed runs)
- red_003 lost at tick 6 to blue_003 (11 of 112 failed runs)
- red_003 lost at tick 5 to blue_003 (11 of 112 failed runs)
- mission_success too low in 112 of 112 failed runs
- recovery_ability too low in 111 of 112 failed runs
- time_cost too low in 110 of 112 failed runs
- resource_cost too low in 90 of 112 failed runs
- risk_growth too low in 80 of 112 failed runs
- strategic_value too low in 80 of 112 failed runs
- tactical_value too low in 60 of 112 failed runs
- system_robustness too low in 9 of 112 failed runs
- stability_impact too low in 6 of 112 failed runs
- Anti-gaming: extreme_high_risk_optimization in 2 of 112 failed runs
- Anti-gaming: sacrifice_strategic_value_for_short_term_tactical_value in 2 of 112 failed runs
- Anti-gaming: maximize_score_by_inaction in 1 of 112 failed runs

## Survival conditions

- sensor_failure: holds at every tested level
- communication_failure: holds up to severe, breaks at collapse
- weather_degradation: holds at every tested level
- enemy_reaction_speed: holds up to moderate, breaks at severe
- equipment_overheat: holds up to severe, breaks at collapse
- civilian_pressure: holds up to severe, breaks at collapse
