# City report

## city_takeover_001

- Outcome: order_restored (verdict pass)
- Governance stability score: 0.82 (start 0.52; ticks 21–30)
- Components: order 0.93, services 0.82, administration 0.62, trend 0.74

Power: no outage.

## city_blackout_001

- Outcome: order_not_restored (verdict fail)
- Governance stability score: 0.50 (start 0.52; ticks 21–30)
- Components: order 0.30, services 0.82, administration 0.28, trend 0.64

Power: cascade depth 1, at most 7 districts dark.

- Tick 4: sub_center down (incident) [event_0000000068]
- Tick 5: sub_north down (overload 13.5 > 11.0, after event_0000000068) [event_0000000093]
- Tick 5: sub_south down (overload 9.9 > 8.0, after event_0000000068) [event_0000000094]
- Tick 11: sub_center restored
- Tick 14: sub_north restored
- Tick 20: sub_south restored

## Supply delay and public order

city_takeover_001, seeds 42–44.

| delay factor | order restored | mean end order | mean score |
|---|---|---|---|
| 1 | 100% | 95.6 | 0.83 |
| 1.5 | 100% | 89.5 | 0.82 |
| 2 | 33% | 63.7 | 0.67 |
| 2.5 | 0% | 32.3 | 0.48 |
| 3 | 0% | 19.0 | 0.39 |
