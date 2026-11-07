# 契約參考

SKYVAULT 11 份契約的現行規格。描述**現在的樣子**，隨程式碼改動而更新。

契約的原文出處見 [`../plan/formal_spec.md`](../plan/formal_spec.md)；v0.1 為什麼這樣劃範圍見 [`../decisions/004_contract_scope.md`](../decisions/004_contract_scope.md)。

---

## 1. 怎麼用

每份契約是 `src/skyvault/contracts/` 裡的一個 Pydantic model，配一個純函式：

```python
from skyvault.contracts import validate_scenario, ContractError

try:
    scenario = validate_scenario(data)       # 通過：回傳正規化後的 dict
except ContractError as error:
    print(error.contract)                    # "scenario"
    print(error.errors)                      # ["scenario_id: Field required", ...]
```

規則：

```text
驗證函式是純函式：不開檔、不寫檔、import 無副作用。
ContractError 一次列出全部錯誤，不是只有第一個；它是 ValueError 的子類別。
回傳值只含呼叫端給的欄位 —— 驗證不會補進 optional 欄位，不會改變資料形狀。
未知的鍵一律被拒（extra="forbid"），拼錯不會被默默忽略。
```

**契約不 import 專案內任何模組。** 任何模組都可以依賴它，它不依賴任何模組；exporter 則不 import 契約。

## 2. 在哪裡被強制

| 流程點 | 驗證 | 不合法時 |
|---|---|---|
| `scenario_loader.load_scenario()` | `validate_scenario` | raise，world 不會被建立 |
| engine 結算 action 之前 | `validate_action` | raise —— 壞 action 是 policy 的程式錯誤，不是 `ACTION_REJECTED` |
| `world_state.record_event()` | `validate_event` | raise，event 不會進 event_memory |
| `engine.run()` 回傳之前 | `validate_result_package` | raise |

## 3. 版本

```text
SCHEMA_VERSION      "0.1"（contracts/base.py）
scenario            必須帶 schema_version: "0.1"，其他版本直接被拒
JSON Schema $id     skyvault/0.1/<name>.schema.json
```

optional 欄位在它所屬的 Phase 落地時改為必填，同時調升版本。

---

## 4. 十一份契約

### 紀錄類

| 契約 | model | 必填 | optional（留待） |
|---|---|---|---|
| Entity | `EntityRecord` | entity_id、name、entity_type、faction、position | state、capabilities、tags（預設空） |
| Action | `ActionRecord` | action_id、**actor_id**、action_type | target_entity_id、target_position、intent、metadata；Spec §6.2 的 required_resources 等六欄（Phase 3） |
| Consequence | `ConsequenceRecord` | action_id、accepted、reason | direct_effects、evaluation_impact；secondary_effects、chain_reactions（Phase 3） |
| Event | `EventRecord` | 見下 | — |

`position` 是兩個整數，`[x, y]`。

### Event 的形狀

Spec §7.2 的巢狀形狀，頂層恰為 12 個鍵（[ADR 003](../decisions/003_event_nesting.md)）：

```python
event_id              str                非空
time                  int                ≥ 0
event_type            str                八種之一，見下
source                {actor_id, system_id, action_id}
target_entity_id      str | None         ADR 002 的增補欄位
affected              {entities, locations, resources, risks}
before_state          dict               必填，沒有預設值
after_state           dict               必填，沒有預設值
causal_links          {caused_by, caused_events}
evaluation_relevance  {affects_success, affects_cost, affects_risk}
data                  dict               型別專屬資料，ADR 002 的增補欄位
tags                  list[str]
```

```text
ACTION_SELECTED   ACTION_REJECTED   MOVE      ATTACK
MISS              ENTITY_DESTROYED  NO_ACTION SCENARIO_END
```

新增事件型別要改 `contracts/event.py` 的 `EVENT_TYPES` —— 沒登記的型別會在 `record_event()` 被拒。

### 場景類

| 契約 | model | 必填 | optional（留待） |
|---|---|---|---|
| World Contract | `WorldContract` | world_id、world_scope、purpose、space_model、time_model、assumption_registry、evaluation_targets | entity_model、environment_state、resource_state、rule_set（Phase 2）、actor_slots（Phase 6）、failure_variables（Phase 9）、event_memory、data_provenance |
| Scenario | `Scenario` | schema_version、**scenario_id**、scenario_version、world_contract、entities（≥ 1）、runtime、evaluation | scenario_type、domain、purpose、assumption_registry、data_provenance、participants、allowed_actions、failure_exploration、output |
| Assumption Registry | `AssumptionRegistry` | — | scenario_id、assumptions、critical_assumptions、assumption_risks、assumption_confidence |
| Data Provenance | `DataProvenance` | — | scenario_id、sources、reliability_notes、missing_data |

Scenario 的額外規則：

```text
entity_id 不得重複
space_model.type 為 "grid" 時必須有 width 與 height
distance_model 只能是 chebyshev / manhattan / euclidean_floor
```

**兩種 assumption registry 不要搞混：** `world_contract.assumption_registry` 是扁平的 名稱 → 值 對照（engine 從這裡讀 `actor_policy`）；scenario 頂層的 `assumption_registry` 是 §11.2 的結構化稽核紀錄。

### 結果類

| 契約 | model | 必填 | optional（留待） |
|---|---|---|---|
| Evaluation Result | `EvaluationResult` | termination_reason、event_count、active_entities、destroyed_entities、active_factions、winner_or_result、key_findings、failure_points | overall_judgement、scores、failure_causes、recommended_next_tests、comparison（Phase 7） |
| Result Package | `ResultPackage` | scenario_id、scenario_version、initial_world_state、final_world_state、event_memory、**evaluation_result** | reproducibility（Phase 8） |
| Reproducibility | `ReproducibilityMetadata` | Spec §12.2 全部欄位 | — |

Result Package 的額外規則：`evaluation_result.event_count` 必須等於 `len(event_memory)`。

**Reproducibility 目前沒有任何東西產生它。** event_id 與 action_id 還是 uuid4、不受 seed 控制，沒有任何 run 能誠實填出 output_hash。Phase 8 才開始填。

---

## 5. JSON Schema

```text
src/skyvault/schemas/<name>.schema.json    11 份，由契約產生，已 commit
scripts/export_schemas.py                  重新產生
```

**改了任何契約之後要重跑：**

```bash
python3 scripts/export_schemas.py
```

連只改 docstring 也要 —— Pydantic 把 docstring 寫進 schema 的 `description`。漂移測試會在已 commit 的檔與產生結果不一致時失敗。
