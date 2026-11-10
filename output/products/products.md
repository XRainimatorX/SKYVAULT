# SKYVAULT Studio — products

## Crisis Planning Simulator

*When the grid fails, how far does it spread and does public order hold?*

The outage spread 1 step(s) and left at most 7 district(s) dark; governance stability went from 0.52 to 0.47 and public order was not restored.

- outcome: "order_not_restored"
- governance_score: 0.4691
- governance_score_at_start: 0.5191
- cascade_depth: 1
- most_districts_dark: 7

## Urban Resilience Simulator

*How late can supplies arrive before order breaks down?*

Order is restored in at least half the runs up to a supply delay of ×1.5; beyond it, in fewer than half.

- order_restored_rate_by_delay: {"1.0": 1.0, "1.5": 1.0, "2.0": 0.3333, "2.5": 0.0, "3.0": 0.0}
- longest_delay_order_holds: "1.5"
- runs: 15

## AI Scenario Testing Platform

*Which agent does best on this scenario — and is its score honest?*

scripted scored highest (0.345) but its score is flagged as gamed; the best honest agent is baseline.

- agents: {"baseline": {"gaming_detected": false, "result": "no_winner_duration_limit", "score": 0.329}, "rule_based": {"gaming_detected": false, "result": "BLUE_survived", "score": 0.2551}, "scripted": {"gaming_detected": true, "result": "no_winner_duration_limit", "score": 0.3455}}
- highest_score: "scripted"
- best_honest_agent: "baseline"
- flagged_for_gaming: ["scripted"]

## Equipment Concept Screening Tool

*Is this design possible, worth building, and where does it break?*

Screened before any prototype: EXO_TEST_001 continue, PAX_TEST_001 redesign, MSX_TEST_001 reject.

- EXO_TEST_001: {"engineering": 0.7732, "judgement": "continue", "physical": 0.9549, "redesign_triggers": 0}
- PAX_TEST_001: {"engineering": 0.4961, "judgement": "redesign", "physical": 0.0, "redesign_triggers": 3}
- MSX_TEST_001: {"engineering": 0.2137, "judgement": "reject", "physical": 0.0, "redesign_triggers": 5}

## Training & After-Action Review Tool

*What happened in this exercise, in order, and what did it cost?*

20 ticks, 314 recorded events; first shots at tick 5, 7 unit(s) lost — no_winner_duration_limit.

- outcome: "no_winner_duration_limit"
- ticks: 20
- events: 314
- first_contact_tick: 5
- units_lost: 7

## Risk Simulation Studio

*Which pressure breaks this plan first, and at what level?*

The plan survives 100% of runs unstressed; enemy_reaction_speed crushes it first.

- baseline_survival: 1.0
- breaking_level: {"communication_failure": "moderate", "enemy_reaction_speed": "mild", "equipment_overheat": "severe", "sensor_failure": "severe"}
- crushing_variable: "enemy_reaction_speed"
