# Formal Spec — 契約格式原文

這份是**凍結紀錄**：從上傳的《SKYVAULT Long-Term Framework & Formal Spec》抽出 16 條核心契約的定義與格式，作為各 Phase 實作契約時的依據，寫完不再更新。
實際實作的契約見 [`../spec/contracts.md`](../spec/contracts.md)；系統目前的樣子見 [`../architecture.md`](../architecture.md)。

---

## 0. 從正式文件抽出的硬性要求

| 文件定義 | 對 Spec 的要求 |
|---|---|
| SKYVAULT 是 AI-operated world / environment engine | Spec 必須以「世界如何運行」為中心，而不是以戰鬥功能為中心 |
| SKYVAULT 是共同環境底座 | 必須支援 STARTX、TAC ANGEL、NEXUS、HADES、AEROGRID、SKYFOX 等接入 |
| SKYVAULT 不是 STARTX / TAC ANGEL / NEXUS | 必須定義清楚：它只提供世界，不替其他系統做最終決策 |
| SKYVAULT 可測戰術、戰略、治理、城市、危機、裝備、AI、制度、後勤 | Spec 必須跨 domain，不能只寫軍事戰鬥 |
| SKYVAULT 支援星衞計劃 virtual test support | 必須包含 physical possibility、engineering feasibility、tactical usefulness 三重評估 |
| SKYVAULT 不取代 CAD / CAE / FEA | 必須支援外部工程仿真接入，而不是自己假裝能做完整物理仿真 |
| SKYVAULT 成熟期是 background-operated world service | 必須支援 standby、triggered scenario、persistent world、batch simulation、result package return |
| 外殼可商業化，核心要帝國化 | 必須保留商業場景與內部核心能力的雙軌架構 |
| 最終目標是讓方案在現實前接受審判 | Spec 的核心輸出應是 consequence / evaluation / failure exploration，不只是 log |

## 1. 長期總框架

```text
 1. World Contract
 2. Scenario Grammar
 3. Execution Protocol
 4. Observation Contract
 5. Action & Consequence Contract
 6. Event Memory
 7. Evaluation Logic
 8. External System Interface Contract
 9. Background Operation & World Service Contract
10. Assumption / Provenance / Version Control Contract
11. Reproducibility Contract
12. Arbitration / Branch Conflict Logic
13. Failure Exploration Spec
14. Resource & Compute Governance
15. Metric Anti-Gaming Logic
16. Authority Handoff Logic
```

前 8 項定義「世界怎麼被寫出來、怎麼運行、怎麼記錄、怎麼評估」。後 8 項定義「世界作為長期後台服務，如何可信、可重跑、可控成本、可故意失敗、可比較分支」。

---

## 2. World Contract

一個世界在 SKYVAULT 裡最低限度必須如何被描述，才可以被運行。它不是地圖檔，不是遊戲關卡，而是一份「世界存在條件」。

| 元素 | 定義 |
|---|---|
| `world_scope` | 這個世界模擬什麼範圍：城市、空域、裝備測試場、治理環境、危機場景 |
| `space_model` | 空間如何存在：格子、節點網、城市區域、道路、空域、設施 |
| `time_model` | 時間如何推進：tick、phase、event-driven、long-duration |
| `entity_model` | 世界中有哪些存在物：人、裝備、建築、資源、無人機、系統、組織 |
| `environment_state` | 天氣、地形、城市狀態、空域條件、治安、能源、通信 |
| `resource_state` | 補給、能源、維修件、醫療、燃料、時間、資金 |
| `rule_set` | 這個世界遵守哪些規則 |
| `actor_slots` | 哪些 AI / system / human decision 可以進入世界行動 |
| `event_memory` | 世界如何記錄已發生事件 |
| `evaluation_targets` | 這次世界運行要評估什麼 |
| `assumption_registry` | 這個世界基於什麼假設運行 |
| `data_provenance` | 世界資料從哪裡來、可信度如何 |
| `failure_variables` | 哪些條件可被故意惡化以測試失敗 |

```yaml
world_contract:
  world_id: "urban_crisis_test_001"
  world_scope: "city_environment"
  purpose: ["crisis_response", "system_stress_test", "governance_recovery"]
  space_model:
    type: "district_network"
    units: ["district", "road_node", "facility", "supply_point"]
  time_model:
    type: "phase_event_hybrid"
    phase_length: "6_hours"
    max_duration: "14_days"
  entity_model: {humans: true, vehicles: true, infrastructure: true, resources: true, ai_systems: true}
  environment_state: {power_grid: "unstable", public_order: "low", weather: "heavy_rain", communication: "degraded"}
  actor_slots: ["NEXUS", "STARTX", "TAC_ANGEL", "EIDEN_01", "AEROGRID", "HADES"]
  assumption_registry:
    public_order_decay_rate: "medium"
    supply_delay_model: "regional_disruption"
  data_provenance: {source_type: "mixed_input", source_quality: "medium", timestamp: "", version: ""}
  failure_variables: ["supply_delay", "communication_failure", "public_order_collapse", "weather_degradation"]
  evaluation_targets: ["stability_recovery", "resource_cost", "civilian_pressure", "system_performance", "risk_growth"]
```

## 3. Scenario Grammar

如何把一個任務、想法、方案、裝備測試、治理問題，寫成 SKYVAULT 可以運行的場景。Scenario = 世界範圍 + 初始條件 + 參與者 + 限制 + 行動權限 + 評估目標 + 終止條件 + 假設 + 失敗測試變量。

```yaml
scenario:
  identity: {scenario_id: "", scenario_type: "", domain: "", purpose: "", scenario_version: ""}
  world_binding: {world_contract_id: "", environment_profile: "", rule_profile: ""}
  initial_conditions: {entities: [], resources: {}, risks: {}, constraints: {}, uncertainty: {}}
  assumption_registry: {assumptions: [], critical_assumptions: [], assumption_confidence: {}}
  data_provenance: {sources: [], timestamps: {}, confidence: {}, modified_by: "", input_version: ""}
  participants: {human_decision_slots: [], ai_agent_slots: [], system_slots: [], equipment_profiles: []}
  allowed_actions: {action_types: [], actor_permissions: {}}
  execution_settings:
    time_mode: ""
    duration_limit: ""
    repeat_count: 1
    random_seed_policy: ""
    deterministic_mode: false
  failure_exploration:
    enabled: false
    failure_variables: []
    stress_levels: {mild: {}, moderate: {}, severe: {}, collapse: {}}
    branch_comparison: true
  evaluation: {primary_metrics: [], secondary_metrics: [], anti_gaming_metrics: [], failure_thresholds: [], comparison_targets: []}
  output: {required_logs: [], required_reports: [], replay_required: true, failure_map_required: true}
```

## 4. Execution Protocol

```text
 1. Receive Task                 接收 NEXUS / 使用者 / 外部系統提出的任務
 2. Compile Scenario             將任務轉成可運行 scenario
 3. Instantiate World            建立初始世界狀態
 4. Register Participants        把 STARTX、TAC ANGEL、HADES、AEROGRID 等接入 actor slot
 5. Generate Observations        根據每個系統視角產生可見狀態
 6. Receive Actions / Decisions  接收 actor / system 提交的行動
 7. Validate Actions             檢查行動是否合法、資源是否足夠、時間是否允許
 8. Resolve Consequences         根據 ruleset 產生直接後果與連鎖反應
 9. Mutate World State           更新世界狀態
10. Record Events                記錄每個事件、狀態變化、因果鏈
11. Evaluate Current State       評估是否達成目標、是否失敗、風險是否爆表
12. Explore Failure Branches     故意惡化指定變量，測試方案如何失敗
13. Continue / Branch / Terminate
14. Generate Result Package      輸出可讀報告與機器可讀資料
```

## 5. Observation Contract

每個進入 SKYVAULT 的系統，在某個時間點能看到什麼、看不到什麼、看到的資訊有多少延遲與不確定性。SKYVAULT 不是上帝視角沙盤，而是要測試真實決策壓力。

| 系統 | 看到什麼 |
|---|---|
| STARTX | 高層趨勢、資源壓力、戰略結果、長期風險 |
| TAC ANGEL | 局部狀態、單位可見資訊、任務限制、即時壓力 |
| NEXUS | 任務進度、系統狀態、總體報告 |
| EIDEN-01 | 情報參數、可信度、來源、缺口 |
| AEROGRID | 空域目標、感測器覆蓋、攔截窗口 |
| SKYFOX | 無人機路徑、障礙、任務區域、能源狀態 |
| HADES | 來襲威脅、反應時間、防禦效果、誤判風險 |
| CYBERHOUND | 信息環境、情緒壓力、傳播路徑、認知風險 |
| 星衞裝備測試 | 裝備姿態、能耗、故障、維修壓力、任務價值 |

```yaml
observation:
  observer_id: "TAC_ANGEL"
  time: "T+03:00"
  visible_world_state: {local_area: {}, known_entities: [], known_risks: [], resources_visible: {}}
  hidden_state: {exists: true, reason: "fog_of_war"}
  uncertainty: {confidence_level: 0.72, stale_after: "10_minutes", source_quality: "medium"}
  decision_context: {mission_goal: "", constraints: [], available_actions: []}
```

## 6. Action & Consequence Contract

這是 SKYVAULT 的心臟。SKYVAULT 的真正價值是：讓世界承受 action，然後產生 consequence。

```text
Action Attempt → Validation → Resolution → Consequence → World Mutation → Event Memory
```

```yaml
action:
  action_id: ""
  actor_id: ""
  action_type: ""
  target: {entity_id: "", location: "", system_id: ""}
  intent: ""
  required_resources: {}
  expected_duration: ""
  expected_effect: ""
  risk_profile: {}
  priority: ""
  confidence: 0.0
```

```yaml
consequence:
  action_id: ""
  accepted: true
  direct_effects: {state_changes: [], resource_changes: [], entity_changes: []}
  secondary_effects: {risk_changes: [], stability_changes: [], public_order_changes: [], logistical_changes: []}
  chain_reactions:
    - {event_id: "", cause: "", effect: ""}
  evaluation_impact: {cost_delta: 0, risk_delta: 0, stability_delta: 0, tactical_value_delta: 0, strategic_value_delta: 0}
```

## 7. Event Memory

Event Memory 是 SKYVAULT 的歷史層：發生了什麼、誰導致、在什麼狀態下發生、造成什麼直接結果、後續引發什麼連鎖反應、這件事對最終評估有何影響。

```yaml
event:
  event_id: ""
  time: ""
  event_type: ""
  source: {actor_id: "", system_id: "", action_id: ""}
  affected: {entities: [], locations: [], resources: [], risks: []}
  before_state: {}
  after_state: {}
  causal_links: {caused_by: [], caused_events: []}
  tags: ["resource_loss", "stability_shift", "system_response"]
  evaluation_relevance: {affects_success: true, affects_cost: true, affects_risk: true}
```

## 8. Evaluation Logic

SKYVAULT 如何判斷一個方案是否值得、是否危險、是否可行。不是 win / lose，必須是多軸評估。

| 評估軸 | 問題 |
|---|---|
| Physical Possibility | 物理上大致可能嗎？ |
| Engineering Feasibility | 工程上值得投入嗎？ |
| Tactical Usefulness | 任務中真的有用嗎？ |
| Strategic Value | 對長期目標有價值嗎？ |
| Governance Stability | 是否改善或破壞秩序？ |
| Crisis Resilience | 面對危機是否更穩？ |
| Resource Cost | 花多少資源？ |
| Time Cost | 花多少時間？ |
| Risk Growth | 是否創造新風險？ |
| System Robustness | 系統在壓力下是否失效？ |
| Failure Resistance | 方案在故意惡化條件下能撐多久？ |
| Recovery Ability | 失敗後是否能恢復？ |
| Commercial Demonstrability | 是否能包裝成對外可展示產品？ |
| Imperial Core Value | 是否保留長期架構價值？ |

```yaml
evaluation_result:
  scenario_id: ""
  overall_judgement: {status: "pass / fail / risky / needs_more_test", confidence: 0.0}
  scores:
    physical_possibility: 0
    engineering_feasibility: 0
    tactical_usefulness: 0
    strategic_value: 0
    governance_stability: 0
    crisis_resilience: 0
    resource_efficiency: 0
    risk_control: 0
    system_robustness: 0
    failure_resistance: 0
    recovery_ability: 0
  key_findings: [""]
  failure_causes: [""]
  recommended_next_tests: [""]
  comparison: {better_than: [], worse_than: []}
```

## 9. External System Interface Contract

SKYVAULT 不是其他系統的上級，而是其他系統可共同使用的模擬環境提供者。

| 系統 | 提交給 SKYVAULT | SKYVAULT 返回 |
|---|---|---|
| NEXUS | 任務、調度要求、報告格式 | result package、scenario report、system status |
| STARTX | 戰略分支、資源限制、長期目標、比較要求 | 分支後果、風險曲線、資源壓力、方案評分 |
| TAC ANGEL | 局部行動方案、戰術規則、行動偏好 | state-action-outcome、戰術成敗、壓測結果 |
| EIDEN-01 | 情報資料、可信度、世界參數 | 情報轉 scenario 的缺口、敏感變量、結果影響 |
| AEROGRID | 空域配置、防空系統 profile、感測器覆蓋 | 空域壓力、反應窗口、漏檢風險、系統表現 |
| SKYFOX | 無人機 actor profile、任務路徑、能源限制 | 任務成功率、路徑風險、能源壓力、碰撞 / 失聯風險 |
| HADES | 防禦流程、威脅模型、反應規則 | 防禦有效性、誤判率、反應時間、覆蓋缺口 |
| CYBERHOUND | 信息環境參數、傳播模型、認知壓力 | 輿情變化、秩序壓力、反噬風險 |
| 星衞計劃 | EXO / PAX / MSX / ERX / 載具 profile | physical possibility、engineering feasibility、tactical usefulness |

## 10. Background Operation & World Service Contract

成熟期 SKYVAULT 不是前台 app，而是 background-operated / background-running world-environment service：24/7 standby、接收任務、建立 world instance、運行 scenario、維持 persistent world、批量跑分支、保存狀態、輸出 result package、回傳 NEXUS。

```text
Operation Modes      Standby / Triggered Scenario / Persistent World / Batch Simulation /
                     Monitoring / Replay / Failure Exploration
World Lifecycle      created → initialized → running → paused → branched →
                     completed / failed → archived → replayed → deleted
```

```yaml
world_service_contract:
  service_status: {mode: "standby / running / batch / persistent / failure_exploration", health: "normal / degraded / failed"}
  task_intake: {source_system: "", task_type: "", priority: "", required_result_package: ""}
  world_instance: {world_id: "", scenario_id: "", lifecycle_state: "created"}
  service_actions: [receive_task, create_world_instance, run_scenario, pause_world, resume_world,
                    branch_world, terminate_world, archive_world, export_result_package]
```

## 11. Assumption / Provenance / Version Control Contract

確保結果不是黑箱：這個 scenario 假設了什麼？資料從哪裡來？這是第幾版？這次結果為什麼和上次不同？

```yaml
assumption_registry:
  scenario_id: ""
  assumptions:
    - assumption_id: ""
      description: ""
      category: "enemy_behavior / public_order / equipment_failure / supply / weather / system_performance"
      value: ""
      confidence: 0.0
      criticality: "low / medium / high"
  critical_assumptions: [""]
  assumption_risks: [""]
```

```yaml
data_provenance:
  scenario_id: ""
  sources:
    - source_id: ""
      source_type: "EIDEN_01 / STARTX / manual_input / external_data / historical_record"
      timestamp: ""
      confidence: 0.0
      version: ""
      modified_by: ""
  reliability_notes: [""]
  missing_data: [""]
```

```yaml
scenario_version_control:
  scenario_id: ""
  version: "v1.0"
  parent_version: ""
  changed_from_previous: {assumptions_changed: [], data_changed: [], rules_changed: [], metrics_changed: [], failure_variables_changed: []}
  change_reason: ""
```

## 12. Reproducibility Contract

同一個 scenario 必須能重跑，讓結果可以被復查、比較、重播、歸檔。

```yaml
reproducibility:
  run_id: ""
  scenario_id: ""
  scenario_version: ""
  random_seed_policy: "fixed / controlled_random / stochastic"
  random_seed: ""
  runtime_version: ""
  ruleset_version: ""
  input_hash: ""
  output_hash: ""
  deterministic_replay_available: true
  run_metadata: {started_at: "", ended_at: "", compute_profile: "", operator_system: ""}
```

## 13. Arbitration / Branch Conflict Logic

SKYVAULT 不裁決誰對；SKYVAULT 展示每條路會怎樣死、怎樣活：detect conflict → mark incompatible actions → simulate separate branches → return conflict package to NEXUS。

```yaml
conflict_package:
  conflict_id: ""
  scenario_id: ""
  conflicting_actions:
    - {actor_id: "", action_id: "", intent: "", conflict_with: []}
  conflict_type: [resource_conflict, timing_conflict, objective_conflict, risk_conflict]
  branch_runs:
    - {branch_id: "", action_set: [], result_summary: "", evaluation_delta: {}}
  recommendation_to_nexus: {required_decision: true, decision_reason: ""}
```

## 14. Failure Exploration Spec

故意讓方案、scenario、系統、裝備與治理流程失敗，以找出現實行動前必須修正的弱點。

| 類別 | 要故意讓它怎樣失敗 |
|---|---|
| 戰術方案 | 被包圍、補給斷、情報錯、隊形崩 |
| 城市接管 | 治安反彈、糧食不足、行政癱瘓、民心下滑 |
| 裝備方案 | 過熱、續航不足、跌倒、維修時間過長 |
| HADES / AEROGRID | 漏檢、誤判、反應太慢、目標太多 |
| SKYFOX | 失聯、撞機、能源耗盡、路徑阻塞 |
| STARTX 方案 | 長期資源壓力爆炸、戰略節奏延誤 |
| TAC ANGEL 行動 | 局部打贏但戰略上浪費成本 |

```yaml
failure_exploration:
  scenario_id: ""
  objective: "find_weakness"
  failure_variables: [supply_delay, sensor_failure, weather_degradation, enemy_reaction_speed, equipment_overheat, civilian_pressure]
  stress_levels: {mild: {}, moderate: {}, severe: {}, collapse: {}}
  run_policy: {repeat_count: 100, random_seed_policy: "controlled_random", branch_comparison: true}
  output: {failure_points: [], collapse_sequence: [], survival_conditions: [], recommended_modifications: []}
```

Failure Map 輸出：在哪裡死、為什麼死、多快死、哪個假設害死、哪個變量壓垮、哪個替代方案活得更久、現實行動前必須改什麼。

## 15. Resource & Compute Governance

SKYVAULT 是 background-operated world service，不能無限制 24/7 燒算力。這一章只負責 SKYVAULT 自身的運行資源管理，不是權限層。

```yaml
resource_compute_governance:
  scenario_id: ""
  compute_budget: {max_runtime: "", max_parallel_runs: 0, max_batch_count: 0, estimated_cost: ""}
  priority: {level: "low / medium / high / urgent", reason: ""}
  auto_stop_conditions: [budget_exceeded, infinite_loop_detected, no_new_state_change, failure_threshold_reached]
  queue_policy: {allow_defer: true, allow_partial_result: true}
```

## 16. Metric Anti-Gaming Logic

如果 Evaluation Logic 設錯，系統會學會「刷分」：只看損耗低，AI 可能永遠不行動；只看速度快，AI 可能犧牲穩定度；只看成功率，AI 可能走高風險極端方案。

```yaml
metric_anti_gaming:
  scenario_id: ""
  primary_metric: ""
  secondary_metrics: []
  anti_gaming_metrics:
    - {metric: "inaction_penalty", reason: "prevent doing nothing to preserve resources"}
    - {metric: "stability_penalty", reason: "prevent fast success that destroys long-term order"}
    - {metric: "risk_spike_penalty", reason: "prevent extreme high-risk optimization"}
  forbidden_optimization_behaviors:
    - maximize_score_by_inaction
    - sacrifice_long_term_stability_for_short_term_success
    - ignore_hidden_risk_to_improve_visible_score
  tradeoff_report_required: true
```

## 17. Authority Handoff Logic

成熟期 SKYVAULT 可以自主運行，但不能擁有最終決策權。可以 simulate、recommend、alert、reject invalid scenario、return conflict package、return failure map；不應該 make sovereign decision、override NEXUS、override STARTX strategic intent、replace human authority。

```yaml
authority_handoff:
  scenario_id: ""
  handoff_required: true
  reason: [conflicting_branches, high_risk_outcome, strategic_tradeoff, failure_threshold_crossed]
  package_to_nexus: {result_summary: "", branch_comparison: [], failure_map: [], required_decision: ""}
  skyvault_position: {may_recommend: true, may_execute_final_decision: false}
```

## 18. 星衞計劃 Virtual Test Support Spec

在 EXO / PAX / MSX / ERX / 新 MS / 載具做實體原型前，先做三重篩查：Physical Possibility → Engineering Feasibility → Tactical Usefulness。

```yaml
equipment_profile:
  equipment_id: "MSX_TEST_001"
  category: "MSX"
  physical_parameters: {mass: "", height: "", center_of_gravity: "", joint_load: "", power_requirement: "", heat_output: "", endurance: ""}
  engineering_parameters: {material_complexity: "", maintenance_time: "", part_replacement_difficulty: "", supply_chain_risk: "", repair_environment_required: ""}
  operational_parameters: {operator_fatigue: "", terrain_accessibility: "", transport_requirement: "", deployment_time: "", mission_role: ""}
  test_targets: [movement_viability, energy_burden, maintenance_pressure, mission_value]
```

```yaml
equipment_test_result:
  equipment_id: ""
  physical_possibility: {score: 0, warnings: [], impossible_flags: []}
  engineering_feasibility: {score: 0, bottlenecks: [], maintenance_risks: []}
  tactical_usefulness: {score: 0, useful_contexts: [], weak_contexts: [], logistics_burden: ""}
  failure_exploration: {failure_points: [], collapse_sequence: [], redesign_triggers: []}
  final_judgement: {status: "continue / redesign / reject / require_external_simulation", reason: ""}
```

---

## 19. 必要技術族群（摘要）

```text
A 世界描述        JSON Schema / YAML Schema、Pydantic / dataclass、DSL、versioned schema、ontology
B 模擬運行        Discrete Event Simulation、Agent-Based Modeling、Monte Carlo、State Machine、
                  Causal Graph、Experiment Runner、Replay Engine（長期可參考 HLA）
C 城市地理        GIS data model、network graph、city model、path / flow simulation、
                  spatial indexing（參考 CityGML、OpenDRIVE / OpenSCENARIO）
D 外部工程仿真    FMI / FMU、surrogate model、physics-lite rule model、co-simulation adapter、
                  constraint solver —— SKYVAULT 不取代 CAD / CAE / FEA
E AI / Agent      rule-based agent、planning agent、RL、multi-agent simulation、
                  LLM-assisted scenario builder、RAG、uncertainty model、evaluation agent
                  AI 在 SKYVAULT 裡不是本體
F 資料與記憶      event sourcing、snapshot store、time-series DB、graph DB、object storage、
                  metadata registry、data provenance
G 接口整合        REST / GraphQL、gRPC、message bus、WebSocket、API versioning、adapter pattern
H 後台服務        job queue、scheduler、worker system、checkpointing、health monitoring、
                  failure recovery、resource limiter
I 失敗探索        fault injection、stress testing、sensitivity analysis、branch search、
                  collapse sequence detection、failure map generator
J 可視化          dashboard、replay timeline、map view、causal chain view、failure map view、
                  comparison report、export PDF / DOCX、scenario studio
```

## 20. 一句話收束（原文）

> 我要定義一個世界如何被寫出來、如何被啟動、如何讓 AI / 系統 / 裝備進入、如何承受行動後果、如何記住因果、如何評估方案是否值得進入現實、如何作為後台世界服務長期待命、如何讓方案在虛擬世界裡先失敗一千次以找出正確道路。
