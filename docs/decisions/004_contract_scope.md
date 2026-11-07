# 004 — Contract Pack v0.1 的範圍與取捨

狀態：已採納
日期：2026-11-07
階段：Phase 1 — Core Contract Pack v0.1

## 背景

開發計劃要求 Phase 1 交付 11 份契約，技術欄寫明：

```text
Python dataclass / Pydantic、JSON Schema、YAML / JSON scenario format、schema versioning
```

Formal Spec 為大部分契約給了格式，但現有程式碼與資料在幾處與 Spec 不一致，Spec 自己也有兩處前後不一。這份 ADR 記錄每一處的處理方式。

**總原則：v0.1 把「現在存在的東西」正式化為必填；Spec 有但系統尚未建模的元素定義為 optional，並標明留待哪個 Phase。** 模擬行為不因契約而改變。

## 決定

### 1. 用 Pydantic v2，這是 repo 第一個執行時期相依

**契約以 Pydantic model 定義，JSON Schema 由 `model_json_schema()` 產生。** PyYAML 為了支援 YAML scenario 一併加入。

```text
Pydantic   開發計劃 Phase 1 技術欄點名；同一份 model 同時負責驗證與產生 JSON Schema
PyYAML     開發計劃 Phase 1 技術欄點名「YAML / JSON scenario format」
```

代價：README 原本寫的「沒有任何執行時期相依套件」不再成立，已改寫。兩個套件宣告在 `pyproject.toml` 的 `[project] dependencies`。

沒有另外加 `jsonschema` 套件 —— 驗證由 Pydantic 做，JSON Schema 檔只供文件與外部系統對接。兩套驗證機制並存會產生「Python 說合法、JSON Schema 說不合法」的分歧。

### 2. 必填與 optional 的劃分

| 契約 | 必填（現在存在） | optional（尚未建模） | 留待 |
|---|---|---|---|
| World Contract | world_id、world_scope、purpose、space_model、time_model、assumption_registry、evaluation_targets | entity_model、environment_state、resource_state、rule_set | Phase 2 |
| | | actor_slots | Phase 6 |
| | | failure_variables | Phase 9 |
| | | event_memory、data_provenance | — |
| Action | action_id、actor_id、action_type、target_entity_id、target_position、intent、metadata | required_resources、expected_duration、expected_effect、risk_profile、priority、confidence | Phase 3 |
| Consequence | action_id、accepted、reason、direct_effects、evaluation_impact | secondary_effects、chain_reactions | Phase 3 |
| Evaluation Result | 現有八欄 | overall_judgement、scores、failure_causes、recommended_next_tests、comparison | Phase 7 |
| Result Package | 六欄 | reproducibility | Phase 8 |

一個 optional 欄位在它所屬的 Phase 落地時改為必填，並調升 `schema_version`。

### 3. Scenario 維持扁平佈局

Spec §3.3 把 scenario 分組為 `identity` / `world_binding` / `initial_conditions` / `participants` ……。現有 scenario 是扁平的六個頂層鍵，engine 直接讀它們。

**v0.1 維持扁平佈局**，只加 `schema_version`，並把 §3.3 獨有的區塊（`assumption_registry`、`data_provenance`、`participants`、`allowed_actions`、`failure_exploration`、`output`）收為 optional 頂層鍵。

改成分組佈局會同時改動 scenario 檔、loader 與 engine 的每一處讀取，卻不帶來任何新能力。它是一次 schema 版本變更，留給真正需要分組的 Phase（多 domain 的 Phase 13–15 最可能）。

### 4. 兩種 assumption registry 並存，各自有明確位置

Spec 本身有兩種形狀：

```text
§2.3  world_contract.assumption_registry   扁平的 名稱 → 值 對照，例如 actor_policy: "..."
§11.2 Assumption Registry 契約              結構化清單：assumption_id、category、confidence、criticality
```

```text
world_contract.assumption_registry    維持 §2.3 扁平對照 —— engine 從這裡讀 actor_policy 當 system_id（ADR 002）
scenario.assumption_registry（頂層）   使用 §11.2 結構化契約
```

兩者用途不同：前者是世界的運行參數，後者是對方案可信度的稽核紀錄。

### 5. Data Provenance 一律用 §11.3

Spec §2.3 把 `world_contract.data_provenance` 畫成扁平四欄，§11.3 則是正式的結構化契約。目前沒有任何 scenario 帶 provenance，沒有既有形狀要保留，所以**兩處都用 §11.3 的專屬契約**。

### 6. `evaluation` 更名為 `evaluation_result`

開發計劃驗收第 4 條原文是「一個 result package 必須包含 evaluation_result」，Spec §8.3 的格式名稱也是 `evaluation_result`。舊鍵名 `evaluation` 更名，讀取端（engine、runner、兩個測試檔）一併修改。scenario 頂層的 `evaluation`（評估設定）是另一回事，不改名。

### 7. 契約違反一律 raise，不轉成事件

policy 交出缺 `actor_id` 的 action 時，engine **raise `ContractError`**，而不是記一筆 `ACTION_REJECTED`。

```text
ACTION_REJECTED   合法的 action 被世界規則拒絕（目標格被佔、超出射程）—— 模擬的一部分
ContractError     資料本身是壞的 —— 程式錯誤
```

這延續 `get_entity()` 故意 raise 而不回傳 None 的設計：錯的資料要當場炸掉，不要變成後面某處的靜默 no-op。

### 8. 驗證點與正規化

```text
scenario_loader.load_scenario()   validate_scenario
engine 結算 action 之前             validate_action
world_state.record_event()         validate_event（不合法的 event 不會進 event_memory）
engine.run() 回傳之前              validate_result_package
```

`validate_<x>()` 回傳 `model_dump(mode="json", exclude_unset=True)`：只回傳呼叫端給的欄位，**不會補進 optional 欄位的預設值**，所以驗證不會改變資料形狀。測試以「驗證前後相等」確認這一點。

所有 model 設 `extra="forbid"`：拼錯的鍵直接報錯，而不是被默默忽略。

### 9. 版本

```text
scenario.schema_version   "0.1"，Literal 型別 —— 其他版本的檔案直接被拒，不嘗試解讀
JSON Schema $id           skyvault/0.1/<name>.schema.json
SCHEMA_VERSION 常數        contracts/base.py；有測試確認 Scenario 的 Literal 與它一致
```

## 已知代價

**JSON Schema 會隨 docstring 改變。** Pydantic 把 model 的 docstring 寫進 schema 的 `description`，所以只改契約的說明文字也會讓 `src/skyvault/schemas/` 過期。漂移測試會抓到，修法是重跑 `python3 scripts/export_schemas.py`。

**每個 event 驗證兩次。** 一次在 `record_event()`，一次隨 result package。97 個 event 的成本可忽略；Phase 10 批量模擬時若成為瓶頸，再改為只在邊界驗證。
