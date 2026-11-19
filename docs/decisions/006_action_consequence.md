# 006 — Action & Consequence Engine 與 schema 0.3

狀態：已採納
日期：2026-11-08
階段：Phase 3 — Action & Consequence Engine v0.3

## 背景

開發計劃 Phase 3 要把 tactical slice 的 move / attack 擴展成一般化的 Action → Consequence 系統，列出八個框架元件（ActionAttempt、ActionValidation、ActionResolver、Consequence、DirectEffect、SecondaryEffect、ChainReaction、EvaluationImpact）與十種初期 action type，驗收五條：

```text
Action 不再直接改世界 / Action 必須先 validate / Consequence 才能 mutate world /
每次 mutation 必須生成 event / event 必須可追蹤 source_action_id
```

Phase 3 開始前，engine 的 `resolve_move` / `resolve_attack` 一邊驗證、一邊直接改 entity、一邊記 event，最後才回傳一個 Consequence。Consequence 是事後的說明，不是原因。

issue #20 第 6 節在寫程式之前列出了十三項決定。這份 ADR 記錄那十三項，以及開發中發現的四項。

**總原則照舊：文件有寫就照字面；文件沒寫，選正式化現有行為、改動最小的做法。** tactical reference 的模擬行為不變 —— 而且這次的標準比「勝負與事件數不變」更嚴：**每一筆 event 的內容都不變**。

## 決定

### 1. Action 的 target 採 Spec 巢狀形狀

Spec §6.2 是 `target: {entity_id, location, system_id}`，現行是攤平的 `target_entity_id` / `target_position`。**採用 Spec。** 程式內是 `ActionTarget` dataclass。

event 的 `target_entity_id` 不受影響（那是 ADR 002 的 event 欄位）；`ACTION_SELECTED` 的 `data.target_position` 由 `target.location` 推出，輸出檔不變。

### 2. ADR 004 的六個欄位改為必填

ADR 004 第 2 點承諾：`required_resources`、`expected_duration`、`expected_effect`、`risk_profile`、`priority`、`confidence` 在 Phase 3 改為必填。**照做。** tactical policy 填入：攻擊的 `confidence` 是 accuracy，移動是 1.0；`expected_effect` 分別是 `hp_change` / `position_change`。

只有 `required_resources` 有執行意義（第 11 點）。其餘四個是宣告：被記錄、被契約檢查，但沒有任何程式依它們做決定。

### 3. Consequence 契約採 Spec 分組，程式內保留順序

Spec §6.3 把直接效果分成 `state_changes` / `resource_changes` / `entity_changes`。但套用順序決定 event 順序，而 supply 必須先扣世界的資源、再加到單位身上。

**契約採分組；程式內 `Consequence.effects` 是有順序的 list，每個 `DirectEffect` 帶 `group`。** `to_dict()` 分組時組內保持順序。

### 4. resolver 只讀，apply_consequence 是唯一 mutation 路徑

```text
handler.validate()      只讀 → ActionValidation
handler.resolve()       只讀 → Consequence（可以抽 rng）
apply_consequence()     唯一改世界：entity effect → world.mutate_entity()
                                  resource effect → world.change_resource()
                                  chain reaction → world.record_transition()
```

`tests/actions/test_framework.py` 用 AST 走過 `handlers.py`，任何對 `.state` / `.position` 的賦值、`state.update()`、或呼叫 `record_event` / `mutate_entity` / `change_resource` 等都會失敗。這個檢查本身也反向驗證過：六種寫法各放一次都會被抓到。

### 5. 不改世界的 event 是 changes 為空的 entity effect

MISS、OBSERVE、SCAN、WAIT 有 event、沒有 mutation。**它們是 `changes: {}` 的 entity effect**：`mutate_entity()` 照樣快照前後、記 event，前後相同。這讓「一個 effect 一筆 event」沒有例外。

### 6. ENTITY_DESTROYED 是 hp 變動的 chain reaction

Spec 的 chain reaction 形狀是 `{event_id, cause, effect}`。致命一擊在 Phase 2 記成 ATTACK 與 ENTITY_DESTROYED 兩筆、前後狀態相同。

**ENTITY_DESTROYED 成為 ATTACK effect 的 chain reaction**，以 `world.record_transition()` 記錄，before / after 取自成因的 event —— 與 Phase 2 的輸出逐位元相同。`event_id` 在套用後回填；`cause` 是 `"<event_type>:<entity_id>"`。

### 7. state_changes 被契約接受，套用時 raise

Spec 有 state_changes（環境變動），但 WorldState 沒有建模 `environment_state` —— 把它放進快照會改變 WorldSnapshot 契約。**契約接受這個 list；`apply_consequence()` 遇到 state effect 直接 raise `NotImplementedError`。** 記為已知限制，留給需要環境變動的 domain。

### 8. secondary_effects 只是描述

risk / stability / public_order / logistical 四類，對應的模型（Phase 7、9）還不存在。**它們是描述性紀錄，不改世界。** supply 寫一筆 `logistical_changes`，其他 handler 都留空。

### 9. evaluation_impact 是五個數值

Spec 的五個 delta 預設 0。舊的隨意鍵對應為：`time_cost: 1` → `cost_delta: 1`（move）；`damage_done` → `tactical_value_delta`（attack 命中）。這些數字沒有出現在任何輸出檔，Phase 7 才會拿來打分。

### 10. 十種 action type 的語意；軍事線五種

Spec 只列名稱。每種的語意寫在 issue #20 第 6 節與 `docs/architecture.md` 的 handler 表格。所有距離上限都是 entity 的 capability，預設 1。

`MILITARY_ACTION_TYPES = ("move", "attack", "observe", "supply", "repair")`。tactical engine 只登記這五種；其他 type 回傳 `"Unsupported action type: ..."` —— 與 Phase 2 對未知 type 的處理相同。

### 11. 資源由世界定價；時間只是宣告

Spec §4 第 7 步：「檢查資源是否足夠、時間是否允許」。

```text
資源   world_contract.rule_set.action_costs[action_type] 有定義就用它，
       否則用 action.required_resources —— 價格是世界定的，不是 actor 說了算
       不足 → 拒絕，世界與 event memory 不變
       足夠 → 在 handler 的 effect 之前扣除，每個資源一筆 RESOURCE_CHANGED
時間   expected_duration 不強制；所有 action 都在一步內完成
```

supply 運送的就是它被收的費：世界的存量減少多少，目標的 state 就增加多少。

### 12. move 加上距離上限

Phase 2 的 move 只檢查界內與未被佔據，等於能瞬移到任何空格。**加上 `distance ≤ move_range`（預設 1）。** reference 用 chebyshev，policy 只走八個鄰格，距離都是 1，不受影響 —— reference trace 證明了這一點。

### 13. schema_version 升為 0.3

action 與 consequence 契約不相容，`schema_version` 升為 `"0.3"`，0.2 被拒。scenario 檔只需改版本號：action 與 consequence 不寫在 scenario 裡。

### 14. `apply_consequence()` 多一個 optional 的 system_id（偏離凍結介面）

凍結的簽名是 `apply_consequence(world, consequence, action)`。但每筆 event 的 `source.system_id` 必須是 policy 的名字（Phase 2 的輸出就是這樣），而 consequence 與 action 都不帶它。

**加一個預設為 None 的 `system_id` 參數。** 凍結的三參數呼叫照樣成立；`ActionResolver` 傳入 `context.system_id`。

### 15. withdraw 要求同陣營；supply 要求目標活著（凍結語意之外的兩條）

凍結語意中，withdraw 只寫「活著」、supply 沒寫目標狀態。寫 handler 時補上：

```text
withdraw   目標必須與 actor 同陣營 —— 否則等於能把敵人「撤出戰場」
supply     目標必須活著 —— 補給一個被摧毀的單位沒有意義
```

兩條都只讓更多 action 被拒絕，不影響 reference（policy 不用這兩種）。

### 16. 範圍拒絕訊息的距離顯示整數

graph 的 networkx 距離是 float，訊息會出現 `distance=2.0`。**整數值顯示為整數。** grid 的距離本來就是 int，tactical 的拒絕訊息逐字不變。

### 17. rebuild_world 從起始 tick（含）開始重放（修正 ADR 005 第 7 點）

ADR 005 第 7 點寫「只套用 start_state 的 tick **之後**的事件」，前提是快照已包含它那個 tick 的事件。但初始快照是在任何 tick 0 事件**之前**擷取的；Phase 3 的 action 測試在 tick 0 行動，重建就漏掉了它們。

**改為從起始 tick（含）開始重放。** 套用 after_state 是冪等的（Phase 2 反向驗證時發現的等價變異），所以重放快照已包含的事件不會改變結果。ADR 005 是凍結文件不修改，以本點為準。

## 後果

```text
好處    Consequence 是世界改變的原因：它在生效前存在、可以被檢查、可以被拒絕
        Phase 9（插入惡化）與 Phase 12（比較兩個 consequence）有了可以插手的位置
        改世界只有一條路，而且有 AST 測試守著
        reference 的每一筆 event 與 Phase 2 相同，由 tests/fixtures/reference_trace.json 釘住
代價    action 契約多了五個目前沒人讀的宣告欄位
        每個 accepted action 多一次 consequence 契約驗證
```
