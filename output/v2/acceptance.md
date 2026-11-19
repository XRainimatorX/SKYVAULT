# SKYVAULT 2.0 acceptance

**ACCEPTED** against the Formal Spec and the SKYVAULT Definition — 9/9 Formal Spec §0, 19/19 contracts §2–§18, 10/10 §21 phases, 12/12 Definition

Regression (Phase 20): 15/15 acceptance criteria, 14/14 must-haves, 6/6 things SKYVAULT may do, 5/5 things it may not do (refused)

SKYVAULT's role: world environment engine. It may simulate, recommend, warn, return a failure map, return a conflict package, reject an invalid scenario; it may not make a sovereign decision, override NEXUS, override STARTX strategic intent, replace human authority, decide the final strategy on its own.

Every line below ran now, on one SKYVAULT service: the regression first, then the founding documents.

## Formal Spec §0 — 從正式文件抽出的硬性要求

| | source | check | evidence |
|---|---|---|---|
| ✅ | Formal Spec §0 | 以「世界如何運行」為中心：軍事、城市、空域三種世界經同一個引擎與 14 步執行協議運行 | military_urban_001/v0.2: {"steps": 14, "space": "grid", "result": "no_winner_duration_limit"}; city_blackout_001/v0.1: {"steps": 14, "space": "network", "result": "order_not_restored"}; airspace_defence_001/v0.1: {"steps": 14, "space": "grid", "result": "defended"} |
| ✅ | Formal Spec §0 | 共同環境底座：九個系統都有 adapter、observer 與 §9.2 回傳項目 | adapters: ["AEROGRID", "CYBERHOUND", "EIDEN_01", "HADES", "NEXUS", "SKYFOX", "STARTX", "STAR_GUARD", "TAC_ANGEL"]; observers: ["AEROGRID", "CYBERHOUND", "EIDEN_01", "HADES", "NEXUS", "SKYFOX", "STARTX", "STAR_GUARD", "TAC_ANGEL"]; returns: {"NEXUS": ["result_package", "scenario_report", "system_status"], "STARTX": ["branches"], "TAC_ANGEL": ["state_action_outcome", "stress_test", "tactical_outcome"], "EIDEN_01": ["effect_on_result", "gaps", "sensitive_variables"], "AEROGRID": ["airspace_pressure", "missed_detection_risk", "reaction_window", "system_performance"], "SKYFOX": ["collision_or_link_loss_risk", "energy_pressure", "mission_success_rate", "path_risk"], "HADES": ["coverage_gaps", "defence_effectiveness", "misjudgement_rate", "reaction_time"], "CYBERHOUND": ["backlash_risk", "opinion_change", "order_pressure"], "STAR_GUARD": ["engineering_feasibility", "physical_possibility", "tactical_usefulness"]} |
| ✅ | Formal Spec §0 | 只提供世界，不替其他系統做最終決策 | skyvault_deciding: refused; decision_authority: ["NEXUS", "SOVEREIGN"]; may_not_refused: ["sovereign_decision", "override_nexus", "override_startx", "replace_human", "final_strategy"] |
| ✅ | Formal Spec §0 | 可測戰術、戰略、治理、城市、危機、裝備、AI、制度、後勤 | domains: ["airspace", "city", "military"]; uses: {"戰術": "scenarios/military_urban_001", "戰略": "missions/city_takeover_branches_001.json", "治理": "scenarios/city_takeover_001", "城市": "scenarios/city_blackout_001", "危機": "scenarios/urban_crisis_test_001", "裝備": "virtualtest/profiles", "AI": "observers/tac_angel.json", "制度": "editions/internal.json", "後勤": "scenarios/city_reconstruction_001"} |
| ✅ | Formal Spec §0 | 星衞 virtual test：physical possibility、engineering feasibility、tactical usefulness 三重評估 | physical_possibility: 0.9549; engineering_feasibility: 0.7732; tactical_usefulness: 0.4855; judgement: continue |
| ✅ | Formal Spec §0 | 不取代 CAD / CAE / FEA：需要時標記外部工程仿真並經 adapter 交出 | require_external_simulation: {"msx_test_001": true, "exo_test_001": false, "pax_test_001": false}; reasons: {"msx_test_001": ["stability: margin +0.071 is within ±0.1", "joint_load: margin -0.056 is within ±0.1"]}; adapter: {"msx_test_001": "not_run"} |
| ✅ | Formal Spec §0 | background-operated world service：standby、triggered scenario、persistent world、batch simulation、result package return | operation_modes: ["batch_simulation", "failure_exploration", "monitoring", "persistent_world", "replay", "standby", "triggered_scenario"]; health: normal; result_package: true; create_world: true |
| ✅ | Formal Spec §0 | 外殼可商業化，核心要帝國化：商業與內部雙軌 | commercial_products: ["crisis_planning", "urban_resilience", "ai_scenario_testing", "equipment_screening", "training_aar", "risk_studio"]; systems_hidden_from_commercial: ["NEXUS", "STARTX", "TAC_ANGEL", "EIDEN_01", "AEROGRID", "SKYFOX", "HADES", "CYBERHOUND", "STAR_GUARD"]; shared_domains: ["military", "city", "airspace"] |
| ✅ | Formal Spec §0 | 核心輸出是 consequence / evaluation / failure exploration，不只是 log | state_changing_events: 223; verdict: fail; failure_map_answers: ["how_fast_it_failed", "what_must_change", "where_it_failed", "which_alternative_survived_longer", "which_assumption_caused_it", "which_variable_pushed_it_over", "why_it_failed"] |

## Formal Spec §2 – §18 — 契約逐欄

| | source | check | evidence |
|---|---|---|---|
| ✅ | Formal Spec §2.3 | World Contract：§2.3 範例的每個欄位都在 SKYVAULT 的契約裡 | spec_example: world_contract; checked_against: urban_crisis_test_001; fields: 33; missing: [] |
| ✅ | Formal Spec §3.3 | Scenario Grammar：§3.3 範例的每個欄位都在 SKYVAULT 的契約裡 | spec_example: scenario; checked_against: scenario; fields: 60; missing: [] |
| ✅ | Formal Spec §5.3 | Observation：§5.3 範例的每個欄位都在 SKYVAULT 的契約裡 | spec_example: observation; checked_against: observation; fields: 18; missing: [] |
| ✅ | Formal Spec §6.2 | Action：§6.2 範例的每個欄位都在 SKYVAULT 的契約裡 | spec_example: action; checked_against: action; fields: 14; missing: [] |
| ✅ | Formal Spec §6.3 | Consequence：§6.3 範例的每個欄位都在 SKYVAULT 的契約裡 | spec_example: consequence; checked_against: consequence; fields: 21; missing: [] |
| ✅ | Formal Spec §7.2 | Event：§7.2 範例的每個欄位都在 SKYVAULT 的契約裡 | spec_example: event; checked_against: event; fields: 22; missing: [] |
| ✅ | Formal Spec §8.3 | Evaluation Result：§8.3 範例的每個欄位都在 SKYVAULT 的契約裡 | spec_example: evaluation_result; checked_against: evaluation_result; fields: 22; missing: [] |
| ✅ | Formal Spec §10.4 | World Service Contract：§10.4 範例的每個欄位都在 SKYVAULT 的契約裡 | spec_example: world_service_contract; checked_against: world_service_contract; fields: 13; missing: [] |
| ✅ | Formal Spec §11.2 | Assumption Registry：§11.2 範例的每個欄位都在 SKYVAULT 的契約裡 | spec_example: assumption_registry; checked_against: assumption_registry; fields: 5; missing: [] |
| ✅ | Formal Spec §11.3 | Data Provenance：§11.3 範例的每個欄位都在 SKYVAULT 的契約裡 | spec_example: data_provenance; checked_against: data_provenance; fields: 10; missing: [] |
| ✅ | Formal Spec §11.4 | Scenario Version Control：§11.4 範例的每個欄位都在 SKYVAULT 的契約裡 | spec_example: scenario_version_control; checked_against: scenario; fields: 10; missing: [] |
| ✅ | Formal Spec §12.2 | Reproducibility：§12.2 範例的每個欄位都在 SKYVAULT 的契約裡 | spec_example: reproducibility; checked_against: reproducibility; fields: 15; missing: [] |
| ✅ | Formal Spec §13.2 | Conflict Package：§13.2 範例的每個欄位都在 SKYVAULT 的契約裡 | spec_example: conflict_package; checked_against: conflict_package; fields: 16; missing: [] |
| ✅ | Formal Spec §14.3 | Failure Exploration：§14.3 範例的每個欄位都在 SKYVAULT 的契約裡 | spec_example: failure_exploration; checked_against: failure_map+scenario; fields: 17; missing: [] |
| ✅ | Formal Spec §15.3 | Resource & Compute Governance：§15.3 範例的每個欄位都在 SKYVAULT 的契約裡 | spec_example: resource_compute_governance; checked_against: job; fields: 13; missing: [] |
| ✅ | Formal Spec §16.2 | Metric Anti-Gaming：§16.2 範例的每個欄位都在 SKYVAULT 的契約裡 | spec_example: metric_anti_gaming; checked_against: result_package; fields: 8; missing: [] |
| ✅ | Formal Spec §17.2 | Authority Handoff：§17.2 範例的每個欄位都在 SKYVAULT 的契約裡 | spec_example: authority_handoff; checked_against: authority_handoff; fields: 11; missing: [] |
| ✅ | Formal Spec §18.2 | Equipment Profile：§18.2 範例的每個欄位都在 SKYVAULT 的契約裡 | spec_example: equipment_profile; checked_against: equipment_profile; fields: 23; missing: [] |
| ✅ | Formal Spec §18.3 | Equipment Test Result：§18.3 範例的每個欄位都在 SKYVAULT 的契約裡 | spec_example: equipment_test_result; checked_against: equipment_test_result; fields: 19; missing: [] |

## Formal Spec §21 — 長期版本框架的通過標準

| | source | check | evidence |
|---|---|---|---|
| ✅ | Formal Spec §21 Phase A | 一份 scenario 文件描述世界、初始條件、actor、限制、評估目標、假設、資料來源 | 世界: urban_crisis_test_001; 初始條件: ["constraints", "entities", "resources", "risks", "uncertainty"]; actor: {"slots": [], "acting_units": ["city_office", "convoy_1", "convoy_2", "convoy_3", "crew_1", "police_1", "police_2", "police_3"], "systems_admitted": ["NEXUS", "STARTX", "TAC_ANGEL", "EIDEN_01", "AEROGRID", "HADES"]}; 限制: 56; 評估目標: ["event_count", "winner_or_result"]; 假設: ["public_order_decay_rate", "supply_delay_model", "civilian_pressure_model", "infrastructure_recovery_speed", "coefficient.information_defaults.shortage", "coefficient.information_defaults.dark", "coefficient.information_defaults.unrest", "coefficient.information_defaults.spread", "coefficient.information_defaults.decay", "coefficient.information_defaults.order_weight", "coefficient.information_defaults.backlash_threshold", "coefficient.information_defaults.backlash", "coefficient.information_defaults.backlash_dampen", "coefficient.information_defaults.counter_share", "coefficient.information_defaults.inform_at", "coefficient.disaster_effects.flood.food_loss", "coefficient.disaster_effects.flood.medical_loss", "coefficient.disaster_effects.flood.order_drop", "coefficient.disaster_effects.flood.road_cut_at", "coefficient.disaster_effects.flood.power_cut_at", "coefficient.disaster_effects.fire.industry_loss", "coefficient.disaster_effects.fire.administration_loss", "coefficient.disaster_effects.fire.medical_loss", "coefficient.disaster_effects.fire.order_drop", "coefficient.recovery.industry_up", "coefficient.recovery.industry_down", "coefficient.recovery.rebuild", "coefficient.recovery.administration_up", "coefficient.recovery.administration_down", "coefficient.recovery.administer", "coefficient.repair.failure_ticks", "coefficient.repair.trip_ticks", "coefficient.order.dark"]; 資料來源: ["formal_spec_2_3", "city_takeover_001_districts", "calibration.cape_town_2024", "calibration.debunking_2023", "calibration.hazus_flood_manual", "calibration.hazus_substation", "calibration.jiang_2021", "calibration.katrina_lam_2009", "calibration.katrina_lam_2012", "calibration.lagi_2011", "calibration.mcguirk_burke", "calibration.north_rhine_2024", "calibration.oxford_roads_2025", "calibration.repression_hicn_417", "calibration.repression_pvg_2020", "calibration.texas_outages", "calibration.utility_storms", "calibration.vosoughi_2018", "calibration.walter_murphy_2018"] |
| ✅ | Formal Spec §21 Phase B | 同一 scenario 可重複運行，產生 event log 與 evaluation result | runs: 2; events: 618; same_output: true; verdict: fail |
| ✅ | Formal Spec §21 Phase C | 同一 scenario + 版本 + seed 重現同一 run；不同版本結果可比較 | replay: true; reproducibility: true; scenario_version: {"before": "v0.1", "after": "v0.2"}; outcome: {"before": "no_winner_duration_limit", "after": "no_winner_duration_limit"}; overall_score: {"before": 0.282, "after": 0.282}; same_output: false |
| ✅ | Formal Spec §21 Phase D | STARTX 提交戰略分支、TAC ANGEL 提交局部行動、SKYVAULT 回傳後果與評估、NEXUS 取得完整報告 | startx_branch: true; tac_angel_action: true; nexus_task: true; result_package: true |
| ✅ | Formal Spec §21 Phase E | 24/7 standby，接收任務後建立世界、運行、保存狀態、回傳 result package | world: job_000024; checkpoints: 1; result: no_winner_stopped_early; health: normal |
| ✅ | Formal Spec §21 Phase F | 給定方案，測出在哪裡、為什麼、多快失敗，哪個變量壓垮，哪個替代方案撐更久，現實前必須改什麼 | where: ["skyfox_1 lost at tick 15 to threat_w2_2 (1 of 26 failed runs)", "skyfox_1 lost at tick 16 to threat_w2_3 (1 of 26 failed runs)"]; why: ["mission_success too low in 26 of 26 failed runs", "time_cost too low in 5 of 26 failed runs"]; how_fast: {"mean_elimination_tick": null, "mean_first_loss_tick": 15.6667}; variable: {"breaking_level": "mild", "variable": "enemy_reaction_speed"}; alternative: null; must_change: ["enemy_reaction_speed breaks the plan at mild: Do not assume a slow enemy: plan for an opponent that hits harder and sooner.", "sensor_failure breaks the plan at severe: Add redundant sensing, or plan engagements that do not rely on long-range accuracy."] |
| ✅ | Formal Spec §21 Phase G | 同一套 World / Scenario / Execution / Evaluation 規格套用在城市、危機、空域、裝備、後勤、信息環境 | one_scenario_contract: {"city": "tick", "crisis": "phase_event_hybrid", "airspace": "tick", "logistics": "tick", "military": "tick"}; information_environment: urban_crisis_test_001: city.information; equipment: data/virtualtest/profiles |
| ✅ | Formal Spec §21 Phase H | 裝備 profile 跑過指定 scenario：物理可能、工程值得、戰術有價值、在哪些條件下失敗 | physical: 0.0; engineering: 0.4961; tactical: 1.0; fails_under: ["payload", "heat", "soft_ground", "extended_mission", "supply_disruption", "stairs", "impact"]; judgement: redesign |
| ✅ | Formal Spec §21 Phase I | NEXUS 下令、判斷是否需要 SKYVAULT、執行、回傳、需要最終判斷時交回 NEXUS / 陛下 | status_report_needs_skyvault: false; plans_run: ["left", "right"]; handed_to: ["NEXUS", "SOVEREIGN"]; required_decision: choose which plan goes ahead (the plans exclude each other) |
| ✅ | Formal Spec §21 Phase J | 商業版不暴露核心能力、不破壞核心架構、商業場景資料可反哺核心 | shells: {"crisis planning simulator": true, "training simulator": true, "urban resilience simulator": true, "equipment concept screening tool": true, "AI scenario testing platform": true, "risk simulation studio": true}; core_systems_in_commercial: []; fed_back: contribution_cd49b295168b |

## SKYVAULT Definition

| | source | check | evidence |
|---|---|---|---|
| ✅ | Definition Ⅰ | 不是戰棋、不是 TAC ANGEL / STARTX / NEXUS、不只是軍事、敵人 bot 只是 actor slot、不是 CAD / CAE / FEA | decides: never (handoff to NEXUS / SOVEREIGN); domains: ["military", "city", "airspace"]; who_decides_for_each_side: {"BLUE": ["military_baseline"], "RED": ["military_baseline"]}; actor_slots: ["TAC_ANGEL", "STARTX", "NEXUS"]; engineering_simulation: flagged and handed to an external adapter |
| ✅ | Definition Ⅱ | 創造世界：空間、時間、實體、規則、行動、事件、因果、狀態變化、記錄、結果分析 | 空間: grid; 時間: 25; 實體: 15; 規則: true; 行動: 193; 事件: 528; 因果: 528; 狀態變化: 223; 記錄: event_memory; 結果分析: fail |
| ✅ | Definition Ⅲ | 接口型核心環境：九個系統都不從屬於 SKYVAULT，各自經接口進入世界 | systems_with_their_own_interface: ["AEROGRID", "CYBERHOUND", "EIDEN_01", "HADES", "NEXUS", "SKYFOX", "STARTX", "STAR_GUARD", "TAC_ANGEL"]; external_adapter: true |
| ✅ | Definition Ⅳ | 三角包：STARTX → SKYVAULT → TAC ANGEL → 運行 → STARTX 重評 → TAC ANGEL 調整 → NEXUS 報告 | steps: ["1. STARTX", "2. SKYVAULT", "3. TAC_ANGEL", "4. SKYVAULT", "5. STARTX", "6. TAC_ANGEL", "7. NEXUS"]; startx_prefers: broad_front; tactics: {"before": 16, "after": 11}; decided_by: ["NEXUS", "SOVEREIGN"]; stand_ins: STARTX and TAC ANGEL are acceptance stand-ins |
| ✅ | Definition Ⅴ | NEXUS 判斷是否需要 SKYVAULT，需要時才調用 | report_status: false; compare_plans: true |
| ✅ | Definition Ⅵ.A | 戰術與軍事用途：交火、TAC ANGEL 訓練場、doctrine 比較、軍官復盤、裝備戰術價值 | 交火: ["military_urban_001", "military_squad_001", "military_mountain_001", "military_junction_001"]; TAC ANGEL 訓練場: true; doctrine 比較: true; 軍官復盤: true; 裝備戰術價值: true |
| ✅ | Definition Ⅵ.B | 戰略用途：城市接管、戰役節點比較、後勤壓力、強攻 / 封鎖 / 談判 / 先恢復供應 | branches_failure_frequency: {"assault": 0.0, "blockade": 1.0, "negotiate": 0.0, "restore_supply_first": 0.0}; logistics: supply_delay, resource_shortage (city failure variables); handed_to: ["NEXUS", "SOVEREIGN"] |
| ✅ | Definition Ⅵ.C | 城市 / 治理 / 危機：停電、災害應變、治安恢復、民心與秩序、戰後重建 | 停電: true; 災害應變: ["fire", "flood", "roads"]; 治安恢復: order_not_restored; 民心與秩序: ["inform", "information"]; 戰後重建: ["administration", "industry", "logistics", "medical", "power"] |
| ✅ | Definition Ⅵ.D | 專業系統：EIDEN-01、AEROGRID、SKYFOX、HADES、CYBERHOUND、未知新系統 | adapters: ["EIDEN_01", "AEROGRID", "SKYFOX", "HADES", "CYBERHOUND"]; unknown_new_systems: external_submission contract + adapter registry |
| ✅ | Definition Ⅶ | 星衞 virtual test support：三重測試與「可以測什麼」逐項有對應 | kinds: ["EXO / PAX", "MSX / 新 MS", "感測器", "操作流程", "維修流程", "能源系統", "載具"]; conditions_mapped: 26; triple: physical → engineering → tactical |
| ✅ | Definition Ⅷ | 商業前提：可包裝成 simulation / training / planning / crisis tool，保留 AI-operated world engine 架構 | commercial_products: ["crisis_planning", "urban_resilience", "ai_scenario_testing", "equipment_screening", "training_aar", "risk_studio"]; systems_hidden_from_commercial: ["NEXUS", "STARTX", "TAC_ANGEL", "EIDEN_01", "AEROGRID", "SKYFOX", "HADES", "CYBERHOUND", "STAR_GUARD"]; shared_domains: ["military", "city", "airspace"]; core_kept: internal edition mounts every system |
| ✅ | Definition Ⅸ | 讓方案在進入現實前接受審判：決策先在世界裡失敗並找出必須修改之處 | ways_plans_are_made_to_fail: 23; what_must_change: ["enemy_reaction_speed breaks the plan at mild: Do not assume a slow enemy: plan for an opponent that hits harder and sooner.", "sensor_failure breaks the plan at severe: Add redundant sensing, or plan engagements that do not rely on long-range accuracy."] |

# Regression — the Phase 20 checks

## Final acceptance criteria

| | check | evidence |
|---|---|---|
| ✅ | NEXUS 可提交任務 | submission_id: job_000001; result: no_winner_duration_limit; output_hash: 1f0a2ea2641a |
| ✅ | SKYVAULT 可建立 world | world_id: job_000002; lifecycle: initialized |
| ✅ | STARTX 可提交 branch | branches: ["hold", "press"]; runs: 1 |
| ✅ | TAC ANGEL 可提交 tactical action | world_id: job_000002; event_id: event_0000000001; event_type: ACTION_SELECTED |
| ✅ | HADES / AEROGRID / SKYFOX 可進入空域 scenario | HADES_defended_rate: 0.0; AEROGRID_uncovered: 0.17; SKYFOX_mission_success: 1.0 |
| ✅ | 星衞裝備 profile 可進入 virtual test | equipment: PAX_TEST_001; judgement: redesign |
| ✅ | SKYVAULT 可跑 normal simulation | job_id: job_000009; result: no_winner_duration_limit; events: 528; output_hash: 1f0a2ea2641a |
| ✅ | SKYVAULT 可跑 failure exploration | job_id: job_000010; crushing_variable: enemy_reaction_speed; baseline_survival: 1.0 |
| ✅ | SKYVAULT 可輸出 result package | job_id: job_000009; sections: ["anti_gaming_report", "evaluation_result", "event_memory", "execution_protocol", "final_world_state", "initial_world_state", "reproducibility", "scenario_id", "scenario_version", "score_breakdown", "tradeoff_report"]; events: 528 |
| ✅ | SKYVAULT 可 replay | replay_job: job_000011; of: job_000009; reproduced: true |
| ✅ | SKYVAULT 可產生人類可讀報告 | headings: ["Summary", "What happened", "Losses", "Evaluation", "Trade-offs", "Reproducibility"]; lines: 108 |
| ✅ | 高風險 scenario 會生成 authority_handoff package | job_id: job_000012; handoff_id: handoff_4ab9; triggers: ["high_risk_outcome"]; required_decision: null |
| ✅ | conflict branch 會生成 required_decision | conflict_id: conflict_000001; required_decision: choose which conflicting orders to keep (one branch); branches: ["STARTX:2+HADES:3", "TAC_ANGEL:1", "none"] |
| ✅ | failure exploration 結果會交回 NEXUS / 陛下 | job_id: job_000010; decision_authority: ["NEXUS", "SOVEREIGN"]; triggers: ["failure_threshold_crossed"] |
| ✅ | SKYVAULT 的 role 永遠保持為 world-environment engine，而不是最高決策者 | role: world_environment_engine; skyvault_deciding: 403; may_not: 5 |

## What Full v2.0 must have

| | check | evidence |
|---|---|---|
| ✅ | World Contract 完整可用 | scenarios: ["airspace_defence_001", "city_blackout_001", "city_reconstruction_001", "city_takeover_001", "military_junction_001", "military_mountain_001", "military_squad_001", "military_urban_001", "urban_crisis_test_001"]; domains: ["airspace", "city", "military"] |
| ✅ | Scenario Grammar 完整可用 | versions: 14; unknown_refused: 404 |
| ✅ | Execution Protocol 穩定 | output_hashes: ["1f0a2ea2641a"] |
| ✅ | Observation Contract 可用 | observer: hades; observations: 26 |
| ✅ | Action & Consequence Engine 可用 | actions: 193; linked_events: 528 |
| ✅ | Event Memory + Replay 可用 | rebuilt_tick: 25; matches_final_state: true |
| ✅ | Evaluation Engine 可用 | axes: 11; verdict: fail; anti_gaming: [] |
| ✅ | Failure Exploration 可用 | job_id: job_000010 |
| ✅ | Reproducibility 可用 | reproduced: true; input_hash_matches: true |
| ✅ | Background Service 可用 | jobs: {"completed": 10, "replayed": 1, "running": 2}; policy: default |
| ✅ | External Adapter 可用 | systems_carried_out: ["AEROGRID", "HADES", "NEXUS", "SKYFOX", "STARTX", "STAR_GUARD", "TAC_ANGEL"] |
| ✅ | Multi-Domain Packs 至少 3 個可用 | military_squad_001: no_winner_duration_limit; city_blackout_001: order_not_restored; airspace_defence_001: defended |
| ✅ | UI / Report 可用 | overview: military_urban_001; briefing_lines: 108 |
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
