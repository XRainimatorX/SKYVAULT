# Airspace report

## airspace_defence_001 (seed 42)

- Outcome: defended; 0 threat(s) reached an asset
- Detection gap: 21% of the airspace uncovered; mean 2.0 ticks from launch to first detection (worst 5)
- Response: 3.7 ticks from track to first shot; reaction 0.9 ticks from first chance to first shot
- False alarms: 0; shots at phantoms: 0; fratricide: 0

## HADES rules of engagement

10 runs each (seeds 42–51).

| behavior | defended | mean leaks | uncovered | detect (ticks) | reaction (ticks) |
|---|---|---|---|---|---|
| baseline | 70% | 0.4 | 21% | 2.5 | 0.9 |
| salvo 2 | 40% | 0.6 | 21% | 2.4 | 1.0 |
| first tracked | 70% | 0.3 | 21% | 2.5 | 0.9 |
| close in (engage_at 0.5) | 0% | 2.9 | 21% | 2.4 | 2.6 |
| hold fire below 0.6 | 0% | 3.5 | 21% | 2.4 | 1.1 |

## AEROGRID sensor configurations

10 runs each (seeds 42–51).

| config | defended | mean leaks | uncovered | detect (ticks) | reaction (ticks) |
|---|---|---|---|---|---|
| as built | 70% | 0.4 | 21% | 2.5 | 0.9 |
| spare radar west | 70% | 0.3 | 11% | 1.4 | 1.1 |
| spare radar east | 70% | 0.3 | 18% | 1.7 | 0.8 |
| south radar off | 40% | 1.2 | 40% | 2.4 | 1.0 |
