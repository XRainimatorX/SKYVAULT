# Airspace report

## airspace_defence_001 (seed 42)

- Outcome: defended; 0 threat(s) reached an asset
- Detection gap: 21% of the airspace uncovered; mean 2.0 ticks from launch to first detection (worst 5)
- Response: 3.7 ticks from track to first shot; reaction 0.9 ticks from first chance to first shot
- False alarms: 0; shots at phantoms: 0; fratricide: 0

## HADES rules of engagement

5 runs each (seeds 42–46).

| behavior | defended | mean leaks | uncovered | detect (ticks) | reaction (ticks) |
|---|---|---|---|---|---|
| baseline | 100% | 0.0 | 21% | 2.5 | 0.9 |
| salvo 2 | 60% | 0.4 | 21% | 2.1 | 1.0 |
| first tracked | 100% | 0.0 | 21% | 2.5 | 0.9 |
| close in (engage_at 0.5) | 0% | 3.2 | 21% | 2.3 | 2.8 |
| hold fire below 0.6 | 0% | 3.6 | 21% | 2.3 | 1.1 |

## AEROGRID sensor configurations

5 runs each (seeds 42–46).

| config | defended | mean leaks | uncovered | detect (ticks) | reaction (ticks) |
|---|---|---|---|---|---|
| as built | 100% | 0.0 | 21% | 2.5 | 0.9 |
| spare radar west | 100% | 0.0 | 11% | 1.5 | 1.1 |
| spare radar east | 100% | 0.0 | 18% | 1.7 | 0.7 |
| south radar off | 60% | 0.8 | 40% | 2.1 | 1.1 |
