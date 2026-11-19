# Phase 3 — Action & Consequence Engine v0.3

完成報告。這份文件是 Phase 3 結束時的凍結紀錄，寫完不再更新 —— 系統目前的樣子請看 [`../architecture.md`](../architecture.md)，契約的現行規格請看 [`../spec/contracts.md`](../spec/contracts.md)。

**狀態：功能完成，沒有已記錄未修的缺陷。開發中修正了 Phase 2 留下的兩個潛在缺陷（第 5 節）。**

---

## 1. 這個階段做什麼

Phase 3 開始前，engine 的 `resolve_move` / `resolve_attack` 一邊驗證、一邊直接改 entity、一邊記 event，最後才回傳一個 Consequence。Consequence 是世界已經被改完之後的說明文字，不是原因。

目標是讓 Consequence 成為世界改變的原因：Action Attempt → Validation → Resolution → Consequence → World Mutation → Event Memory（Formal Spec §6）。規格依據是 [`../plan/phase3_action_consequence_engine.md`](../plan/phase3_action_consequence_engine.md) 與 [`../plan/formal_spec.md`](../plan/formal_spec.md) §4、§6。

```text
Issue      #20 Phase_3_action_consequence_engine（milestone #4 Phase 3 — Action & Consequence Engine）
開設       fixture 先 commit：0.3 action / consequence、logistics 圖世界
步驟 A+B   資料形狀與契約 0.3 + 框架（validation / resolver / move / attack），一個 commit
步驟 C     其餘八種 handler 與資源定價
```

步驟 A 與 B 合成一個 commit：契約一改，engine 舊的 resolver 就產生不出新形狀的 Consequence，兩步之間沒有一個能全綠的中間狀態。

開設時在 issue 第 6 節寫下十三項決定，Frozen Interface 每個函式附一行行為（Phase 2 回顧改法 2）。全部記錄於 [`../decisions/006_action_consequence.md`](../decisions/006_action_consequence.md)。

---

## 2. 這次執行發生了什麼

### 模擬行為不變 —— 這次是逐筆不變

```text
Result          RED_survived
Events          97（ACTION_SELECTED 46 / MOVE 26 / ATTACK 14 / MISS 6 /
                    ENTITY_DESTROYED 4 / SCENARIO_END 1）
```

前兩個 Phase 的標準是「勝負、事件數、事件型別順序不變」。這次重寫了整條結算路徑，所以標準提高為**每一筆 event 的內容不變**：

```text
方法     把 result_package 裡的 uuid（event_… / action_…）依首次出現順序換成序號，再比對
結果     Phase 2 與 Phase 3 的正規化 result package 完全相同；timeline.txt 逐字相同
釘住     tests/fixtures/reference_trace.json —— 97 筆 (time, type, actor, target, data)
         + 整包正規化後的 SHA-256；Phase 2 程式碼與 Phase 3 程式碼算出同一個值
```

之後任何 Phase 不小心改到模擬，`test_reference_run_matches_the_committed_trace` 會紅。刻意改變時重新產生，並在完成報告記錄新舊數字。

### 四個 exporter 沒動，輸出也沒變

```text
entity_history   blue_003 21 筆      causal_chain   46 條      replay   12 個 state
```

---

## 3. 核心資料形狀

### Action（schema 0.3）

```json
{
  "action_id": "action_…",
  "actor_id": "red_002",
  "action_type": "attack",
  "target": { "entity_id": "blue_003", "location": null, "system_id": null },
  "intent": "tactical_reference_attack_selected_target",
  "required_resources": {},
  "expected_duration": "1_tick",
  "expected_effect": "hp_change",
  "risk_profile": {},
  "priority": "normal",
  "confidence": 0.55,
  "metadata": {}
}
```

### 一次致命一擊的 Consequence

```json
{
  "action_id": "action_…",
  "accepted": true,
  "reason": "Attack resolved",
  "direct_effects": {
    "state_changes": [],
    "resource_changes": [],
    "entity_changes": [
      { "entity_id": "blue_003", "event_type": "ATTACK",
        "changes": { "state": { "hp": -3, "last_damage_taken": 10, "status": "destroyed" } } }
    ]
  },
  "secondary_effects": { "risk_changes": [], "stability_changes": [],
                         "public_order_changes": [], "logistical_changes": [] },
  "chain_reactions": [
    { "event_id": "event_…", "cause": "ATTACK:blue_003", "effect": "ENTITY_DESTROYED" }
  ],
  "evaluation_impact": { "cost_delta": 0, "risk_delta": 0, "stability_delta": 0,
                         "tactical_value_delta": 10, "strategic_value_delta": 0 }
}
```

套用後產生兩筆 event：ATTACK（effect）與 ENTITY_DESTROYED（chain reaction），兩者 before / after 相同 —— 與 Phase 2 的輸出一致。

---

## 4. 交付了什麼

### actions 套件

```text
src/skyvault/actions/
  validation.py   ActionValidation；action_cost()（rule_set 定價優先）；check_resources()
  handlers.py     十種 handler，validate() 與 resolve() 都只讀；CORE_HANDLERS；
                  MILITARY_ACTION_TYPES；handlers_for()
  resolver.py     ActionContext；ActionResolver.execute()；apply_consequence()
```

### 資料物件

```text
action.py        ActionTarget；Action = ActionAttempt，帶 Spec §6.2 全部欄位；to_dict()
consequence.py   DirectEffect、ChainReaction、SecondaryEffects、EvaluationImpact、Consequence；
                 Consequence.rejected()；to_dict() 依 §6.3 分組
world_state.py   mutate_entity()（唯一改 entity 的方法）、record_transition()（chain reaction 用）
```

### engine 變薄了

`resolve_action` / `resolve_move` / `resolve_attack` 移除，engine.py 從 486 行降到 233 行。engine 只管時間、輪到誰、何時結束；action 交給 `self.resolver = ActionResolver(軍事線五種, ActionContext(self.rng, actor_policy))`。

### 驗收五條

| # | 開發計劃原文 | 如何證明 |
|---|---|---|
| 1 | Action 不再直接改世界 | 十種 handler 各驗 resolve 前後世界快照相等；AST 檢查 handlers.py（檢查本身反向驗證六種寫法） |
| 2 | Action 必須先 validate | 七種拒絕情境（缺目標、界外、被佔、太遠、未登記…）世界與 event memory 都不變 |
| 3 | Consequence 才能 mutate world | 套用 rejected 或別的 action 的 consequence 都 raise；state effect raise |
| 4 | 每次 mutation 必須生成 event | reference 中每個 accepted consequence：event 數 = effect 數 + chain reaction 數 |
| 5 | event 必須可追蹤 source_action_id | reference 中除 NO_ACTION / SCENARIO_END 外，每筆 event 的 action_id 都對應一筆 ACTION_SELECTED，actor 也一致 |

### 十種 action type

logistics 圖世界上，每種都有接受與拒絕的測試（共 61 個）。一串九個 action（observe → scan → wait → repair → supply → communicate → deploy → withdraw → move）產生 11 筆 event（repair 與 supply 各多一筆收費），**只靠這 11 筆 event 重建的世界與實際世界相等**。

---

## 5. 這一輪發現的問題

### Phase 2 的 Event.to_dict() 會把節點 id 拆成字元

`Event.to_dict()` 對每個 `affected_locations` 呼叫 `list(location)`。grid 的 `(3, 5)` 變成 `[3, 5]` 沒問題；graph 的 `"depot"` 變成 `["d", "e", "p", "o", "t"]`，再被 event 契約拒絕。

Phase 2 有一個「RESOURCE_CHANGED 帶節點位置」的測試，但它驗證的是**手寫的 dict**，從來沒有一筆真的 Event 帶著節點位置走過 `to_dict()`。graph 上的第一個 move 就撞上了。

已修，並補了 `test_a_recorded_event_keeps_node_id_locations_whole`（反向驗證：拿掉修正 → 2 個測試紅）。**教訓：測資料形狀的測試，要用產生資料的那段程式碼產生資料，不能手寫。**

### Phase 2 的 rebuild_world 漏掉 tick 0 的事件

`rebuild_world` 只重放起始快照的 tick **之後**的事件，前提是「快照已包含它那個 tick 的事件」。SnapshotStore 的快照確實如此，但**初始快照是在 tick 0 任何事件之前擷取的**。reference 的事件從 tick 1 開始，所以 Phase 2 沒發現；logistics 測試在 tick 0 行動，重建就少了全部事件。

Phase 2 反向驗證時，「`<=` 改成 `<`」是一個存活的變異，當時判定為等價變異並在 docstring 寫「跳過只是省時間」。**它不是等價的 —— 只是 Phase 2 的測試資料剛好沒有 tick 0 的事件。** 現在改成 `<`（含起始 tick），補了 tick 0 的重建測試（反向驗證：改回 `<=` → 2 個測試紅）。ADR 006 第 17 點。

**教訓：判定「等價變異」之前，要問測試資料有沒有涵蓋讓兩者不同的情況。** Phase 2 回顧寫「變異存活時先判斷是否等價：等價就簡化程式碼」—— 這條需要補一句：判斷等價要找反例，不是看現有測試。

### git stash 讓測試跑在舊的 bytecode 上

為了證明 Phase 2 程式碼與 Phase 3 程式碼的 reference digest 相同，用 `git stash` 切回 Phase 2、跑一次、`stash pop`。之後 70 個測試失敗：`schema_version: Input should be '0.2'`。

原因：`scenario.py` 的兩個版本只差 `"0.2"` ↔ `"0.3"`，**檔案大小相同**，而且在同一秒內被改寫。Python 用 (mtime, size) 判斷 `.pyc` 是否過期，兩者都一樣，就沿用了 stash 期間編譯的舊 bytecode。清掉 `__pycache__` 後全綠。

這不是程式碼的問題，但它讓全綠的程式碼看起來壞了。**用 stash 切換版本後，先清 `__pycache__` 再跑。** 已寫進 handoff 地雷區。

### 凍結語意之外多加了兩條規則

寫 handler 時，withdraw 補了「同陣營」、supply 補了「目標活著」。都是讓更多 action 被拒、不影響 reference，但它們不在凍結語意裡。這次是在整合時對照第 6 節才發現的，**不是在寫的當下** —— Phase 2 回顧改法 3（每步 commit 前對照）只做到簽名，沒做到語意。已記入 ADR 006 第 15 點。

### range 訊息在 graph 上出現 `2.0`

networkx 的距離是 float，`distance=2.0, range=1`。改成整數值顯示為整數；grid 距離本來就是 int，tactical 訊息逐字不變。

---

## 6. 品質狀態

| 項目 | 結果 |
|---|---|
| pytest | 289 passed（Phase 2 為 182） |
| 全專案覆蓋率 | 98%（1597 statements，36 miss；Phase 2 為 97%） |
| `actions/` 覆蓋率 | validation 100%、handlers 98%、resolver 96% |
| ruff / black | 通過 |
| mypy（`python3 -m mypy src/`） | 通過，42 個檔案 |
| bandit | 0 issues |
| 換工作目錄跑測試 | 289 passed |
| 測試讀 `output/` | 0 處 |
| exporter 程式碼變動 | 0 行 |
| reference 正規化後與 Phase 2 比對 | 完全相同 |

### 測試分布

```text
tests/actions/test_framework.py      41   驗收五條；reference trace；AST 守護；資源與定價；分層
tests/actions/test_action_types.py   61   十種 action 的接受與拒絕；一天的 action 由 event 重建
tests/runtime/                         +2   節點位置不被拆字元；tick 0 事件被重放
tests/contracts/                       +3   consequence 契約；0.2 被拒
既有測試                             182   改動：fixture 改名（graph / network）、consequence 測試改新形狀
```

### 反向驗證過的測試

```text
test_handlers_never_change_the_world_or_record_events      handler 裡寫 target.state[...] = → 紅
test_the_handler_check_catches_each_kind_of_mutation        六種寫法各自 → 紅（檢查本身的驗證）
test_every_event_an_action_caused_carries_its_action_id    chain reaction 丟掉 action_id → 紅
test_a_refused_action_changes_nothing_and_records_nothing  resolver 跳過 validate → 紅（6 個）
test_repair_stops_at_max_hp                                拿掉 max_hp 上限 → 紅
test_a_recorded_event_keeps_node_id_locations_whole        拿掉節點位置修正 → 紅
test_events_at_the_starting_tick_are_replayed              rebuild 改回 <= → 紅
```

---

## 7. 已知限制

| 項目 | 留待 | 原因 |
|---|---|---|
| `expected_duration` 不強制 | 需要排程的 Phase | 所有 action 在一步內完成 |
| state_changes 套用時 raise | 需要環境變動的 domain | WorldState 沒有建模 environment_state |
| secondary_effects / evaluation_impact 只記錄 | Phase 7 / 9 | 風險、穩定、評分模型尚不存在 |
| tactical policy 只產生 move / attack | domain pack（Phase 13） | observe / supply / repair 已登記但沒人用 |
| observe / scan 是上帝視角 | Phase 5 | 沒有視角、延遲、不確定性 |
| 每個 accepted action 驗證一次 consequence 契約 | Phase 10 | 成本可忽略；批量模擬若成為瓶頸再改 |
| `event_id` / `action_id` 仍是 uuid4 | Phase 8 | 同前 |

---

## 8. 驗證

```bash
rm -f output/*.json output/timeline.txt
python3 scripts/run_tactical_reference.py           # RED_survived / 97 events
python3 -m pytest tests/ -q                          # 289 passed
cd /tmp && python3 -m pytest ~/SKYVAULT/tests -q     # 289 passed
ruff check . && black --check src/ tests/ scripts/
python3 -m mypy src/
python3 -m bandit -c pyproject.toml -r src/          # 0 issues
python3 scripts/export_schemas.py && git status src/skyvault/schemas/   # 無變動
python3 tests/reference_trace.py | head -2           # digest a55c2001…
```

---

## 9. 一句話總結

> Phase 3 讓 Consequence 成為世界改變的原因而不是事後的說明 —— handler 只讀、`apply_consequence()` 是唯一會改世界的地方、每個改動一筆帶 action id 的 event，十種 action type 走同一條路；tactical reference 的 97 筆 event 與 Phase 2 逐筆相同，並由一份 reference trace 釘住，順帶修掉了 Phase 2 兩個只在圖世界與 tick 0 才會出現的潛在缺陷。
