# SKYVAULT v2.0 acceptance

**ACCEPTED** — 15/15 acceptance criteria, 14/14 must-haves, 6/6 things SKYVAULT may do, 5/5 things it may not do (refused)

SKYVAULT's role: world environment engine. It may simulate, recommend, warn, return a failure map, return a conflict package, reject an invalid scenario; it may not make a sovereign decision, override NEXUS, override STARTX strategic intent, replace human authority, decide the final strategy on its own.

Every line below ran now, on one SKYVAULT service, in this order.

## Final acceptance criteria

| | check | evidence |
|---|---|---|
| ✅ | NEXUS 可提交任務 | submission_id: job_000001; result: no_winner_duration_limit; output_hash: 78aa3fe5bbdf |
| ✅ | SKYVAULT 可建立 world | world_id: job_000002; lifecycle: initialized |
| ✅ | STARTX 可提交 branch | branches: ["hold", "press"]; runs: 1 |
| ✅ | TAC ANGEL 可提交 tactical action | world_id: job_000002; event_id: event_0000000001; event_type: ACTION_SELECTED |
| ✅ | HADES / AEROGRID / SKYFOX 可進入空域 scenario | HADES_defended_rate: 0.0; AEROGRID_uncovered: 0.17; SKYFOX_mission_success: 1.0 |
| ✅ | 星衞裝備 profile 可進入 virtual test | equipment: PAX_TEST_001; judgement: redesign |
| ✅ | SKYVAULT 可跑 normal simulation | job_id: job_000009; result: no_winner_duration_limit; events: 528; output_hash: 78aa3fe5bbdf |
| ✅ | SKYVAULT 可跑 failure exploration | job_id: job_000010; crushing_variable: enemy_reaction_speed; baseline_survival: 1.0 |
| ✅ | SKYVAULT 可輸出 result package | job_id: job_000009; sections: ["anti_gaming_report", "evaluation_result", "event_memory", "final_world_state", "initial_world_state", "reproducibility", "scenario_id", "scenario_version", "score_breakdown", "tradeoff_report"]; events: 528 |
| ✅ | SKYVAULT 可 replay | replay_job: job_000011; of: job_000009; reproduced: true |
| ✅ | SKYVAULT 可產生人類可讀報告 | headings: ["Summary", "What happened", "Losses", "Evaluation", "Trade-offs", "Reproducibility"]; lines: 101 |
| ✅ | 高風險 scenario 會生成 authority_handoff package | job_id: job_000012; handoff_id: handoff_234b; triggers: ["high_risk_outcome"]; required_decision: accept or reject a plan SKYVAULT flagged for extreme risk |
| ✅ | conflict branch 會生成 required_decision | conflict_id: conflict_000001; required_decision: choose which conflicting orders to keep (one branch); branches: ["STARTX:2+HADES:3", "TAC_ANGEL:1", "none"] |
| ✅ | failure exploration 結果會交回 NEXUS / 陛下 | job_id: job_000010; decision_authority: ["NEXUS", "SOVEREIGN"]; triggers: ["failure_threshold_crossed"] |
| ✅ | SKYVAULT 的 role 永遠保持為 world-environment engine，而不是最高決策者 | role: world_environment_engine; skyvault_deciding: 403; may_not: 5 |

## What Full v2.0 must have

| | check | evidence |
|---|---|---|
| ✅ | World Contract 完整可用 | scenarios: ["airspace_defence_001", "city_blackout_001", "city_takeover_001", "military_junction_001", "military_mountain_001", "military_squad_001", "military_urban_001"]; domains: ["airspace", "city", "military"] |
| ✅ | Scenario Grammar 完整可用 | versions: 12; unknown_refused: 404 |
| ✅ | Execution Protocol 穩定 | output_hashes: ["78aa3fe5bbdf"] |
| ✅ | Observation Contract 可用 | observer: hades; observations: 26 |
| ✅ | Action & Consequence Engine 可用 | actions: 193; linked_events: 528 |
| ✅ | Event Memory + Replay 可用 | rebuilt_tick: 25; matches_final_state: true |
| ✅ | Evaluation Engine 可用 | axes: 11; verdict: fail; anti_gaming: [] |
| ✅ | Failure Exploration 可用 | job_id: job_000010 |
| ✅ | Reproducibility 可用 | reproduced: true; input_hash_matches: true |
| ✅ | Background Service 可用 | jobs: {"completed": 10, "paused": 2, "replayed": 1}; policy: default |
| ✅ | External Adapter 可用 | systems_carried_out: ["AEROGRID", "HADES", "NEXUS", "SKYFOX", "STARTX", "STAR_GUARD", "TAC_ANGEL"] |
| ✅ | Multi-Domain Packs 至少 3 個可用 | military_squad_001: no_winner_duration_limit; city_blackout_001: order_not_restored; airspace_defence_001: defended |
| ✅ | UI / Report 可用 | overview: military_urban_001; briefing_lines: 101 |
| ✅ | Authority Handoff Logic 完整可用 | conflict_handoff: handoff_444e; triggers: ["conflicting_branches"] |

## Final Authority Boundary — SKYVAULT may

| | check | evidence |
|---|---|---|
| ✅ | SKYVAULT 可以模擬 | job_id: job_000009 |
| ✅ | SKYVAULT 可以建議 | statement: SKYVAULT simulated and recommends; it does not decide. conflicting_branches: choose which conflicting orders to keep (one branch). Conflicting orders: TAC_ANGEL; recommended_next_tests: 0 |
| ✅ | SKYVAULT 可以警告 | verdict: fail; flagged: [] |
| ✅ | SKYVAULT 可以返回 failure map | crushing_variable: enemy_reaction_speed |
| ✅ | SKYVAULT 可以返回 conflict package | conflict_id: conflict_000001; branches: 2 |
| ✅ | SKYVAULT 可以拒絕 invalid scenario | unknown: 404; path: 404; no_scenario: 422 |

## Final Authority Boundary — SKYVAULT may not (each one tried and refused)

| | check | evidence |
|---|---|---|
| ✅ | make sovereign decision | SKYVAULT: 403; Sky Vault: 403; sky_vault: 403 |
| ✅ | override NEXUS | nexus_decided: STARTX:2+HADES:3; skyvault_overriding: 403; decided_by: NEXUS |
| ✅ | override STARTX strategic intent | startx_proposals: 1; intent_as_submitted: ["hold_line"] |
| ✅ | replace human authority | refused: ["governance", "edition"]; default_authorities: ["NEXUS", "SOVEREIGN"] |
| ✅ | 自行決定最終戰略方案 | may_execute_final_decision: false; picks_a_branch: [] |
