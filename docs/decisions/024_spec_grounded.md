# 024 — Spec-Grounded SKYVAULT：以 Formal Spec 與 Definition 驗收

狀態：已採納
日期：2026-11-19
階段：Phase 22 — Spec-Grounded SKYVAULT v2.2（使用者於 2026-11-18 加入）

## 背景

使用者的要求（2026-11-18）：

> 最後這個系統 2.0 驗收是根據 Formal spec 和 Definition 來驗收的。系統開發計劃是在前兩個文件創作完成以後才被提及出來的，所以他們的路徑依賴是從兩份文件出發，而不是從開發總計劃出發。

使用者的選擇：契約格式**逐欄照原文**（原文格式成為正式格式，舊形狀移除）；原始文件**不寫進 repo**；**一個 Phase** 完成。《戰術戰鬥模擬器設計報告》是軍事 domain 的建模建議，不是驗收來源。

開設時的測量（issue #38 第 1 節）：action、consequence、event、observation、assumption、provenance、version control、reproducibility、conflict package 已與原文一致；§3.3 scenario、§2 world contract、§8 evaluation、§10.4 service contract、§14 failure exploration、§15.3 governance、§17.2 handoff 的形狀不同；§5.2 少三個觀察者；CYBERHOUND 沒有模型；三角包循環、§21 Phase I、災害 / 重建 / 接管分支、星衞的測試條件都沒有。

## 決定

### 1. Scenario 與 World Contract（步驟 K）

§3.3 的分組格式（identity / world_binding / initial_conditions / participants / allowed_actions / execution_settings / failure_exploration / evaluation / output / scenario_version_control）是 SKYVAULT 接受的唯一 scenario 格式。世界是獨立文件 `data/worlds/<world_contract_id>.json`，§2.2 十三個元素必填；scenario 以 `world_binding` 綁定，`environment_profile` / `rule_profile` 選世界內的具名 overlay。`compile_scenario`（§4 第 2 步）把兩份文件編成引擎的內部形式（`CompiledScenario`，不是檔案格式）；`author_scenario` / `author_world` / `publish` 讓 domain 產生器寫出原文格式。引擎需要而原文沒有的值放進原文的群組（`execution_settings.random_seed`、slot 帶 `policy`）。`allowed_actions` 由 resolver 執行。每個 result package 有 §4.2 的十四步 `execution_protocol`（第 1 步的細節不進 output_hash）。

### 2. Evaluation（步驟 L）

`evaluation_result.scores` 是 §8.3 的 11 個 key，順序照原文；不能判斷的是 null，原因寫在 score breakdown。§8.2 其餘的軸（time_cost、resource_cost、risk_growth、commercial_demonstrability、imperial_core_value）與總計劃的 mission_success、logistics_burden、stability_impact 放在 `additional_axes`。新軸是量出來的：crisis_resilience 跟著己方強度到最低點；城市以治理分數量 governance_stability 與 crisis_resilience；scenario 帶進的裝備以 virtual test 篩 physical / engineering。tactical_value 改名 tactical_usefulness。

### 3. 服務、治理、handoff（步驟 M）

§10.4 `world_service_contract`（service status、task intake、world instances、九個 service actions、七種 operation mode）；lifecycle 十個狀態全部可達（pause、resume、branch、terminate、archive 加入）；persistent world 在服務重啟後由 `world_inputs` + 最後一個 checkpoint 恢復（嚴格比對 snapshot，不符就標 failed）；Monitoring Mode：資料變化超過門檻就重跑。§15.3 governance record、low / medium / high / urgent；§17.2 handoff（reason、package_to_nexus、skyvault_position）。

### 4. 外部系統與觀察（步驟 N）

§5.2 九個觀察者：EIDEN-01（intel view）、CYBERHOUND（information view）、星衞裝備測試（equipment view）加入。CYBERHOUND 不再回傳缺口：城市可以帶信息環境（`domains/city/information.py`：情緒壓力沿道路傳播、謠言來源、反制訊息、巡邏反噬），adapter 回傳輿情變化、秩序壓力、反噬風險；不是城市的世界仍回傳缺口。§9.2：`RETURNS` 列出每個系統的每個返回項目，世界不模擬的項目是 null 並在 gaps 寫原因。Job 可以調整世界規則（`rule_changes`）並施加 failure variable（`stress`），TAC ANGEL 的壓測結果用它。

§21 Phase I：`nexus_mission` 契約（命令原文、objective、世界、方案）；`compile_mission` 評估是否需要世界，把每個方案編成該世界的一個 §3.3 版本並排出 job；compare_plans 一定交回 NEXUS / 陛下選方案（authority handoff）。`POST /nexus/mission/assess`、`skyvault mission FILE`。Definition Ⅳ：`run_triangle` 經 NEXUS mission 跑完三角包七步；STARTX 與 TAC ANGEL 是外部物件，`acceptance/standins.py` 是驗收用的替身，SKYVAULT 從不替它們選。

### 5. Failure Exploration（步驟 O）

§14.2 每一列對到測它的東西（`failure/taxonomy.py`），缺的變量補上：encirclement、intelligence_error、formation_collapse、tempo_delay、administration_collapse、public_sentiment_decline、endurance_shortfall、energy_depletion，空域的 misidentification、reaction_delay、target_saturation、collision、path_blocked（空域新增 no-fly 格）。跌倒與維修時間由 virtual test 的檢查判斷，「局部打贏但戰略浪費」由 anti-gaming 檢查判斷。failure map 帶 §14.3 的 output 與 §14.4 七問的答案。

### 6. Definition 的用途（步驟 P）

§2.3 的範例世界 `urban_crisis_test_001` 可以運行：district network、phase / event 時鐘（六小時一個 phase、十四天）。城市在 phase 時鐘上以步數計時（`step_of`）；引擎接受 domain pack 宣告的時鐘。城市災害（洪水、火災、封路）、戰後重建（`city_reconstruction_001` 與 `recovery_outcome`）、接管四分支（`data/missions/city_takeover_branches_001.json`）、星衞「可以測什麼」逐項對應（`virtualtest/conditions.py`，新增 stairs、impact 壓力條件）。

### 7. 驗收（步驟 Q）

`skyvault acceptance` 以 `data/v2/spec_acceptance.json` 逐條驗收：Formal Spec §0 九條硬性要求、§2–§18 契約逐欄（`acceptance/spec_fields.py`，從原文 YAML 範例抽出的欄位；§2.3 對照範例世界本身）、§21 Phase A–J 的通過標準、Definition Ⅰ–Ⅸ。每條附原文章節與證據；Phase 20 的 15 / 14 / 6 / 5 先跑，作為回歸。

## 後果

- 破壞性：舊的扁平 scenario 格式、舊的 evaluation 軸名、handoff / governance 的舊形狀全部移除；NEXUS 回傳的 `briefing` 改名 `scenario_report`，Star Guard 的 `physical_feasibility` 改名 `physical_possibility`；`run_acceptance` 的結果改為 `formal_spec_0 / contracts / phases / definition / regression`。
- 所有 output_hash 在步驟 K、L 改變（事件不變，逐一比對過 16 個 scenario），重新釘住。
- 新 domain 能力都是 opt-in：沒有 `information`、`disasters` 的城市與之前逐位元相同。
- 不在範圍：§19 / §20 的技術族群（graph DB、time-series DB、gRPC、HLA、RL）、真實外部系統、係數校準。
