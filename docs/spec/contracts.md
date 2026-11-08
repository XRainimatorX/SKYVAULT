# 契約參考

SKYVAULT 12 份契約的現行規格（開發計劃 Phase 1 的 11 份，加上 Phase 7 的 evaluation profile）。描述**現在的樣子**，隨程式碼改動而更新。

契約的原文出處見 [`../plan/formal_spec.md`](../plan/formal_spec.md)；v0.1 為什麼這樣劃範圍見 [`../decisions/004_contract_scope.md`](../decisions/004_contract_scope.md)；0.2 的變更見 [`../decisions/005_world_runtime.md`](../decisions/005_world_runtime.md)；0.3 的變更見 [`../decisions/006_action_consequence.md`](../decisions/006_action_consequence.md)；0.4 的變更見 [`../decisions/007_evaluation_engine.md`](../decisions/007_evaluation_engine.md)。

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
| `ActionResolver.execute()` 套用之前 | `validate_consequence` | raise —— handler 產生了壞 consequence，世界不會被改 |
| `world_state.record_event()` | `validate_event` | raise，event 不會進 event_memory |
| `engine.run()` 回傳之前 | `validate_result_package` | raise |

## 3. 版本

```text
SCHEMA_VERSION      "0.4"（contracts/base.py）
scenario            必須帶 schema_version: "0.4"，其他版本（含 0.1–0.3）直接被拒
JSON Schema $id     skyvault/0.4/<name>.schema.json
```

optional 欄位在它所屬的 Phase 落地時改為必填，同時調升版本。

| 版本 | Phase | 變更 |
|---|---|---|
| 0.1 | 1 | 初版 11 份契約 |
| 0.2 | 2 | World Contract 四欄必填；space / time 型別封閉；位置可為節點 id；snapshot 加 resources；兩種新事件型別 |
| 0.3 | 3 | Action 採 Spec §6.2 全形狀（巢狀 target、六欄必填）；Consequence 採 §6.3 分組（四部分必填）；八種新事件型別 |
| 0.4 | 7 | Evaluation Result 的 §8.3 欄位必填並加 profile_id / perspective / overall_score / anti_gaming；Result Package 加三份評估輸出；新增 evaluation_profile 契約；scenario.evaluation 加 optional perspective |

0.1 → 0.2 的遷移：`schema_version` 改 `"0.2"`，`world_contract` 補上 `entity_model`、`environment_state`、`resource_state`、`rule_set`（沒有就寫 `{}`）。

0.2 → 0.3 的遷移：scenario 只改 `schema_version: "0.3"`。action 與 consequence 不寫在 scenario 檔裡；直接產生它們的程式（policy、測試）要改成下面的新形狀。

0.3 → 0.4 的遷移：scenario 只改 `schema_version: "0.4"`（可選擇加 `evaluation.perspective`）。手寫的 result package 要補上完整的 evaluation_result 與三份評估輸出 —— 最簡單的做法是用 `evaluate_run()` 產生。

---

## 4. 十一份契約

### 紀錄類

| 契約 | model | 必填 | optional（留待） |
|---|---|---|---|
| Entity | `EntityRecord` | entity_id、name、entity_type、faction、position | state、capabilities、tags（預設空） |
| Action | `ActionRecord` | action_id、**actor_id**、action_type、target、intent、required_resources、expected_duration、expected_effect、risk_profile、priority、confidence | metadata（預設 `{}`） |
| Consequence | `ConsequenceRecord` | action_id、accepted、reason、direct_effects、secondary_effects、chain_reactions、evaluation_impact | — |
| Event | `EventRecord` | 見下 | — |

`position` 是 `[x, y]` 兩個整數（grid），或非空字串的節點 id（graph / network）。

### Action 的形狀

```python
action_id            str                非空
actor_id             str                非空（驗收 2）
action_type          str                非空；十種見 architecture.md 的 actions/handlers.py
target               {entity_id, location, system_id}   三者皆可為 null；location 與 position 同型
intent               str
required_resources   {資源 id: 數量 ≥ 0}
expected_duration    str                宣告，不強制
expected_effect      str
risk_profile         dict
priority             str
confidence           float              0–1
metadata             dict               optional
```

### Consequence 的形狀

```python
action_id          str
accepted           bool
reason             str
direct_effects     {state_changes:    list[dict]                         環境；套用時一律 raise（尚未建模）
                    resource_changes: list[{resource_id, delta, event_type}]
                    entity_changes:   list[{entity_id, event_type, changes}]}   changes 只含 position / state，可為 {}
secondary_effects  {risk_changes, stability_changes, public_order_changes, logistical_changes}   皆為描述性 list
chain_reactions    list[{event_id, cause, effect}]   event_id 套用前為 null；cause 為 "<event_type>:<id>"
evaluation_impact  {cost_delta, risk_delta, stability_delta, tactical_value_delta, strategic_value_delta}
```

rejected 的 consequence 各部分皆為空。consequence 不寫進 result package；它在 `ActionResolver.execute()` 裡、套用之前通過契約。

### Event 的形狀

Spec §7.2 的巢狀形狀，頂層恰為 12 個鍵（[ADR 003](../decisions/003_event_nesting.md)）：

```python
event_id              str                非空
time                  int                ≥ 0
event_type            str                十八種之一，見下
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
RESOURCE_CHANGED  ENTITY_STATE_CHANGED                         （0.2 新增）
OBSERVE   WAIT    REPAIR    SUPPLY                              （0.3 新增）
DEPLOY    WITHDRAW  SCAN    COMMUNICATE                         （0.3 新增）
```

`affected.locations` 的元素與 position 同型：`[x, y]` 或節點 id。

| 事件 | before_state / after_state | 其他 |
|---|---|---|
| `RESOURCE_CHANGED` | `{resource_id, amount}` | `affected.resources` 列出資源；`data.delta`；`affects_cost` 為 true |
| `ENTITY_STATE_CHANGED` | entity 完整快照 | `affected.entities`；`data.changes` |

新增事件型別要改 `contracts/event.py` 的 `EVENT_TYPES` —— 沒登記的型別會在 `record_event()` 被拒。

### 場景類

| 契約 | model | 必填 | optional（留待） |
|---|---|---|---|
| World Contract | `WorldContract` | world_id、world_scope、purpose、space_model、time_model、assumption_registry、evaluation_targets、entity_model、environment_state、resource_state、rule_set | actor_slots（Phase 6）、failure_variables（Phase 9）、event_memory、data_provenance |
| Scenario | `Scenario` | schema_version、**scenario_id**、scenario_version、world_contract、entities（≥ 1）、runtime、evaluation | scenario_type、domain、purpose、assumption_registry、data_provenance、participants、allowed_actions、failure_exploration、output |
| Assumption Registry | `AssumptionRegistry` | — | scenario_id、assumptions、critical_assumptions、assumption_risks、assumption_confidence |
| Data Provenance | `DataProvenance` | — | scenario_id、sources、reliability_notes、missing_data |

Scenario 的額外規則：

```text
entity_id 不得重複
每個 entity 的 position 必須在空間內：grid 是界內的 [x, y]，graph / network 是已知節點
```

World Contract 的形狀規則：

| 欄位 | 規則 |
|---|---|
| `space_model.type` | `grid` / `graph` / `network` 之一 |
| grid | 必須有 `width`、`height`（> 0）；`distance_model` 為 chebyshev / manhattan / euclidean_floor |
| graph | 必須有 `nodes`（不重複）與 `edges`，每條 `[a, b]`，端點必須是已知節點 |
| network | 同 graph，但每條 edge 是 `[a, b, weight]`，weight > 0 |
| `time_model.type` | `tick` / `phase` / `event_driven` 之一 |
| phase | 必須有整數 `phase_length`（> 0）；`time_unit` optional |
| `resource_state` | 名稱 → 數量，數量 ≥ 0 |
| `entity_model`、`environment_state`、`rule_set` | dict，可為 `{}` |

**兩種 assumption registry 不要搞混：** `world_contract.assumption_registry` 是扁平的 名稱 → 值 對照（engine 從這裡讀 `actor_policy`）；scenario 頂層的 `assumption_registry` 是 §11.2 的結構化稽核紀錄。

### 結果類

| 契約 | model | 必填 | optional（留待） |
|---|---|---|---|
| Evaluation Result | `EvaluationResult` | 摘要八欄（termination_reason … failure_points）＋ scenario_id、profile_id、perspective、overall_judgement、overall_score、scores、failure_causes、recommended_next_tests、comparison、anti_gaming | — |
| Result Package | `ResultPackage` | scenario_id、scenario_version、initial_world_state、final_world_state、event_memory、**evaluation_result**、score_breakdown、anti_gaming_report、**tradeoff_report** | reproducibility（Phase 8） |
| Evaluation Profile | `EvaluationProfile` | profile_id、perspective（可為 null）、primary_metric、secondary_metrics、weights、thresholds、anti_gaming_metrics、forbidden_optimization_behaviors、tradeoff_report_required | description |
| Reproducibility | `ReproducibilityMetadata` | Spec §12.2 全部欄位 | — |

Result Package 的額外規則：`evaluation_result.event_count` 必須等於 `len(event_memory)`。

Evaluation Result 的形狀細節：

```python
overall_judgement   {status: pass / fail / risky / needs_more_test, confidence: 0–1}
overall_score       0–1
scores              {軸名: 0–1}               只列有資料的軸
comparison          {better_than, worse_than}  單一 run 為空
anti_gaming         {gaming_detected, flagged_behaviors, penalty_total}
```

Evaluation Profile 的規則：

```text
weights、primary_metric、secondary_metrics 的名稱必須是 11 軸之一；至少一個權重 > 0
thresholds 用鍵 pass 與 fail，0 ≤ fail ≤ pass ≤ 1
anti_gaming_metrics 每項 {metric, reason, threshold, penalty}；metric 是五項檢查之一
forbidden_optimization_behaviors 只能是五項檢查對應的行為名
perspective 為 null 時由 scenario 決定（evaluation.perspective，否則第一個有陣營的 entity）
```

`data/evaluation_profiles/` 有 balanced 與 tactical 兩份。

`initial_world_state` / `final_world_state`（`WorldSnapshot`）的必填欄位：world_id、scenario_id、tick、space、entities、resources。`space` 由 `Space.describe()` 寫入，帶 `type`；`resources` 是名稱 → 數量，數量 ≥ 0。

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
