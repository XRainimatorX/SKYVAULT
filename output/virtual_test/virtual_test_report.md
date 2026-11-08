# Virtual test report

Physics-lite screening before a prototype: is it roughly possible, is it
worth building, does it help in a mission, and where does it fail. It does
not replace CAD / CAE / FEA; it says when they are needed.

| equipment | category | physical | engineering | tactical | judgement |
|---|---|---|---|---|---|
| ERX_TEST_001 | ERX | 0.966 | 0.834 | 0.561 | continue |
| EXO_TEST_001 | EXO | 0.955 | 0.773 | 0.484 | continue |
| MSX_TEST_001 | MSX | 0.000 | 0.214 | 0.523 | reject |
| PAX_TEST_001 | PAX | 0.000 | 0.496 | 0.593 | redesign |

## ERX_TEST_001 (ERX)

**continue** — possible (physics 0.97), worth building (engineering 0.83) and useful in military_urban_001

- Impossible: none
- Warnings: none
- Engineering bottlenecks: none
- Maintenance risks: none
- Useful in: military_urban_001; weak in: none; logistics burden low
- Newly fails under: payload at severe (joint_load); heat at collapse (heat); soft_ground at collapse (ground_pressure); extended_mission at moderate (energy); nothing new fails under: supply_disruption (what already fails is listed as impossible above)
- Collapse sequence: moderate: energy; severe: joint_load; collapse: ground_pressure, heat
- Redesign triggers: none
- External simulation: not needed

## EXO_TEST_001 (EXO)

**continue** — possible (physics 0.95), worth building (engineering 0.77) and useful in military_squad_001

- Impossible: none
- Warnings: none
- Engineering bottlenecks: none
- Maintenance risks: none
- Useful in: military_squad_001; weak in: military_urban_001; logistics burden low
- Newly fails under: payload at collapse (joint_load); heat at collapse (heat); soft_ground at collapse (ground_pressure); extended_mission at moderate (energy); nothing new fails under: supply_disruption (what already fails is listed as impossible above)
- Collapse sequence: moderate: energy; severe: ground_pressure; collapse: heat, joint_load
- Redesign triggers: none
- External simulation: not needed

## MSX_TEST_001 (MSX)

**reject** — physically impossible (joint_load: its joints carry more than their rating while it moves (margin -0.06); energy: its energy store cannot power the declared endurance (margin -0.25)) and not worth engineering (score 0.21: exotic materials, more maintenance than operation (15.0 h per hour run), repairs need a factory, supply chain risk 80%)

- Impossible: joint_load: its joints carry more than their rating while it moves (margin -0.06); energy: its energy store cannot power the declared endurance (margin -0.25)
- Warnings: stability: tips over at a smaller lean than its category allows (margin +0.07); heat: it makes more heat than it can shed (margin +0.07)
- Engineering bottlenecks: exotic materials; more maintenance than operation (15.0 h per hour run); repairs need a factory; supply chain risk 80%
- Maintenance risks: 15.0 h of maintenance per hour of operation; parts are hard to replace; cannot be repaired in the field (factory)
- Useful in: military_squad_001; military_urban_001; weak in: military_mountain_001; logistics burden high
- Newly fails under: heat at collapse (heat); soft_ground at severe (ground_pressure); nothing new fails under: payload; extended_mission; supply_disruption (what already fails is listed as impossible above)
- Collapse sequence: severe: ground_pressure; collapse: heat
- Redesign triggers: base_width 3.0 → 3.5 (stability, to clear the warning); joint_load 250.0 → 264.8701 (joint_load, to make it possible); energy_capacity 600.0 → 800.0 (energy, to make it possible); cooling_capacity 320.0 → 375.0 (heat, to clear the warning); mass 18000.0 → 16989.461 (mass_limit, to make it possible)
- External simulation: required — stability: margin +0.071 is within ±0.1; joint_load: margin -0.056 is within ±0.1; heat: margin +0.067 is within ±0.1

## PAX_TEST_001 (PAX)

**redesign** — physically impossible as specified (energy: its energy store cannot power the declared endurance (margin -0.17)); within reach: energy_capacity 15.0 → 18.0001

- Impossible: energy: its energy store cannot power the declared endurance (margin -0.17)
- Warnings: joint_load: its joints carry more than their rating while it moves (margin +0.21); heat: it makes more heat than it can shed (margin -0.11)
- Engineering bottlenecks: more maintenance than operation (1.3 h per hour run)
- Maintenance risks: 1.3 h of maintenance per hour of operation; parts are hard to replace; cannot be repaired in the field (depot)
- Useful in: military_squad_001; weak in: military_junction_001; logistics burden high
- Newly fails under: payload at moderate (joint_load); heat at severe (heat); soft_ground at collapse (ground_pressure); nothing new fails under: extended_mission; supply_disruption (what already fails is listed as impossible above)
- Collapse sequence: moderate: joint_load; severe: ground_pressure, heat
- Redesign triggers: joint_load 9.0 → 9.2705 (joint_load, to clear the warning); energy_capacity 15.0 → 18.0001 (energy, to make it possible); cooling_capacity 4.0 → 5.625 (heat, to clear the warning)
- External simulation: not needed
