# City report

## city_takeover_001

- Outcome: order_restored (verdict pass)
- Governance stability score: 0.82 (start 0.52; ticks 21–30)
- Components: order 0.93, services 0.82, administration 0.62, trend 0.74

Power: no outage.

## city_blackout_001

- Outcome: order_not_restored (verdict fail)
- Governance stability score: 0.47 (start 0.52; ticks 21–30)
- Components: order 0.25, services 0.82, administration 0.21, trend 0.62

Power: cascade depth 1, at most 7 districts dark.

- Tick 4: sub_center down (incident) [event_0000000068]
- Tick 5: sub_north down (overload 13.5 > 11.0, after event_0000000068) [event_0000000093]
- Tick 5: sub_south down (overload 9.9 > 8.0, after event_0000000068) [event_0000000094]
- Tick 10: sub_center restored
- Tick 13: sub_north restored
- Tick 19: sub_south restored

## Supply delay and public order

city_takeover_001, seeds 42–51.

| delay factor | order restored | mean end order | mean score |
|---|---|---|---|
| 1 | 100% | 96.1 | 0.83 |
| 1.5 | 100% | 90.3 | 0.82 |
| 2 | 60% | 65.1 | 0.68 |
| 2.5 | 0% | 35.5 | 0.49 |
| 3 | 0% | 21.3 | 0.40 |
