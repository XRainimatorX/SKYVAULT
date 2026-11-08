# Phase 2 — World Runtime Core v0.2

完成報告。這份文件是 Phase 2 結束時的凍結紀錄，寫完不再更新 —— 系統目前的樣子請看 [`../architecture.md`](../architecture.md)，契約的現行規格請看 [`../spec/contracts.md`](../spec/contracts.md)。

**狀態：功能完成，沒有已記錄未修的缺陷。**

---

## 1. 這個階段做什麼

Phase 2 開始前，世界是 tactical engine 在 `build_world()` 裡臨時組出來的：只有 grid、只有 tick，World Contract 的資源與規則欄位是 optional、也沒有任何程式讀它們。event memory 號稱是真相來源，但沒有任何程式真的只靠它把世界還原出來。

目標是讓世界由 World Contract 建立，並且任一時刻的世界都能只靠 event memory 還原。規格依據是 [`../plan/phase2_world_runtime_core.md`](../plan/phase2_world_runtime_core.md) 與 [`../plan/formal_spec.md`](../plan/formal_spec.md) §2、§4。

單一工作者模式：一份 issue、依序三個步驟、各自 commit。

```text
Issue      #19 Phase_2_world_runtime_core（milestone #3 Phase 2 — World Runtime Core）
開設       fixture 先 commit：graph + event-driven、network + phase 兩份 0.2 scenario
步驟 A     space.py、clock.py
步驟 B     registry.py、resources.py、rules.py、world.py；契約升 0.2
步驟 C     sourcing.py、snapshots.py
整合       對齊凍結介面、runtime 分層測試、CI 加重建驗證
```

開設時依 Phase 1 回顧改法 3，在寫程式之前把八項規格矛盾與決定寫進 issue 第 6 節。全部記錄於 [`../decisions/005_world_runtime.md`](../decisions/005_world_runtime.md)。

---

## 2. 這次執行發生了什麼

### 模擬行為沒有改變

```text
scenario_id     tactical_reference_001
random_seed     42
Result          RED_survived
Events          97（ACTION_SELECTED 46 / MOVE 26 / ATTACK 14 / MISS 6 /
                    ENTITY_DESTROYED 4 / SCENARIO_END 1）
```

與 Phase 1 完全相同。tactical engine 改由 `create_world()` 建世界、由 `advance_time()` 推進時間，但決策、結算與事件順序一點沒動。

### 四個 exporter 的輸出也沒變

```text
entity_history   blue_003 有 21 筆紀錄       Phase 1：21
causal_chain     46 條 chain                Phase 1：46
replay           12 個 state（0–10 + final） Phase 1：12
timeline         14 句攻擊整句與 event_memory 一致
```

四個 exporter 的程式碼在 Phase 2 沒有任何改動。

### 變了的是世界快照的形狀

```text
initial / final_world_state   space 多了 "type": "grid"；多了 "resources": {}
SCENARIO_END 的 after_state    同上（它就是一份世界快照）
```

### event memory 第一次被證明是真相

```text
rebuild_world(initial_world_state, event_memory) == final_world_state     True
rebuild_world(..., at_time=N) 的 entities == replay 的第 N 個 state          N = 0..10 全部相等
從 tick 5 / tick 10 的快照起算 == 從 tick 0 起算                           at_time = 5, 6, 9, 10
```

CI 每次都從自己剛跑出來的 `result_package.json` 重建一次。

---

## 3. 核心資料形狀

### 三種世界

```json
"space_model": { "type": "grid", "width": 10, "height": 10, "distance_model": "chebyshev" }
"space_model": { "type": "graph", "nodes": ["A", "B", "C"], "edges": [["A", "B"], ["B", "C"]] }
"space_model": { "type": "network", "nodes": ["depot", "north", "city"],
                 "edges": [["depot", "north", 4], ["north", "city", 3], ["depot", "city", 10]] }
```

```json
"time_model": { "type": "tick", "max_ticks": 10 }
"time_model": { "type": "phase", "phase_length": 6, "time_unit": "hours" }
"time_model": { "type": "event_driven" }
```

### 一個 RESOURCE_CHANGED 事件

```json
{
  "event_type": "RESOURCE_CHANGED",
  "source": { "actor_id": "convoy_1", "system_id": null, "action_id": null },
  "target_entity_id": null,
  "affected": { "entities": [], "locations": [], "resources": ["fuel"], "risks": [] },
  "before_state": { "resource_id": "fuel", "amount": 100.0 },
  "after_state":  { "resource_id": "fuel", "amount": 70.0 },
  "evaluation_relevance": { "affects_success": false, "affects_cost": true, "affects_risk": false },
  "data": { "delta": -30 },
  "tags": ["resource_change", "world_state_mutation"]
}
```

`affected.resources` 從 Phase 1 起一直恆為空，這是第一個填它的事件。

---

## 4. 交付了什麼

### runtime 套件

```text
src/skyvault/runtime/
  space.py       Space protocol；GridSpace / GraphSpace / NetworkSpace；build_space()
  clock.py       Clock protocol；TickClock / PhaseClock / EventDrivenClock；build_clock()
  registry.py    EntityRegistry —— Mapping，add() 拒絕重複，require() 找不到 raise
  resources.py   ResourceState —— 不得為負
  rules.py       RuleSet —— world_contract.rule_set 的唯讀存取
  world.py       create_world(scenario)、entity_from_record(record)
  sourcing.py    rebuild_world(start_state, event_memory, at_time) —— 純函式
  snapshots.py   SnapshotStore(interval).record(time, snapshot) / latest_at_or_before(time)
```

### WorldState 的三個新方法

```text
advance_time()                 推進 clock，world.tick = clock.now
change_resource(id, delta)     改資源 + 記 RESOURCE_CHANGED；扣到負數在記錄前就 raise
update_entity_state(id, ...)   合併 state + 記 ENTITY_STATE_CHANGED（前後完整快照）
```

### 契約 schema 0.2

```text
World Contract   entity_model / environment_state / resource_state / rule_set 改必填（可為 {}）
                 space_model.type ∈ {grid, graph, network}，各自的形狀規則
                 time_model.type ∈ {tick, phase, event_driven}；phase 必須有整數 phase_length
                 resource_state 數量 ≥ 0
Scenario         schema_version "0.2"；entity 必須在空間內
Entity / Event   position、affected.locations 可為節點 id
Event            EVENT_TYPES 加 RESOURCE_CHANGED、ENTITY_STATE_CHANGED
WorldSnapshot    resources 必填
JSON Schema      11 份重新匯出，$id 改為 skyvault/0.2/…
```

### 驗收六條

| # | 開發計劃原文 | 如何證明 |
|---|---|---|
| 1 | 可以建立一個 world | `create_world()` 由三份 scenario 建出 grid+tick、graph+event-driven、network+phase 三種世界 |
| 2 | 可以放入 entities | `EntityRegistry`；graph entity 站在節點上；重複 id、空間外位置被拒 |
| 3 | 可以推進 time | 三種 clock；phase clock 三步到 18（6 小時 × 3）；event-driven 跳到 5 再跳到 12 |
| 4 | 可以更新 state | `update_entity_state()`、`change_resource()`；資源不得為負 |
| 5 | 可以記錄 event | 兩種新事件都通過 event 契約；`affected.resources` 有值 |
| 6 | 可以從 event memory 產生 replay | `rebuild_world()` 到最後 == final_world_state；每個 tick 與 replay exporter 一致 |

---

## 5. 這一輪發現的問題

### 反向驗證抓到一個無效的分層測試

runtime 不得 import engine / policy / exporter。第一版測試只檢查 `from X import …` 的 `X`，所以 `from .. import engine` —— module 是 `None`、名字在 alias 裡 —— 完全沒被看到。把這行放進 `rules.py` 跑，測試仍然全綠。

改成同時檢查 module 與 alias 後，`from .. import engine` 與 `from ..replay import …` 兩種寫法都會紅。

**這正是 Phase 1 回顧改法 1 要防的事。** 沒有放回缺陷跑一次，這個測試會以「有分層檢查」的樣子一直存在。

### 反向驗證也找到兩段多餘的程式碼

對 `rebuild_world()` 做了三個變異：

```text
資源不套用                       → 測試紅 ✓
time <= start_tick 改成 <         → 仍綠
拿掉 SCENARIO_END 的特例          → 仍綠
```

後兩個不是測試漏了，而是變異**等價**：套用 after_state 是冪等的，重放快照已包含的事件不會改變結果；SCENARIO_END 的 after_state 沒有 `entity_id`、也不是 RESOURCE_CHANGED，通用規則本來就不會套用它。

第三個特例因此刪掉了；第二個保留但在 docstring 註明「跳過只是省時間」。**變異存活不一定代表測試不夠，也可能代表程式碼多寫了。** 兩種都要查。

### 我自己寫的 docstring 和已 commit 的 clock 不一致

步驟 B 寫 TimeModelSpec 的說明時寫成「ticks grouped into phases of phase_length ticks」，同一步的測試也照這個理解寫：推進 7 次預期 tick 7、phase 1。但步驟 A 已 commit 且有測試的 `PhaseClock` 是每次前進一整個 phase。測試紅了才發現。

以已 commit、有測試的程式碼為準，改了說明與新測試。issue 第 6 節第 3 點只寫「整數 phase_length」，沒寫 advance 的語意 —— **凍結介面寫型別，不寫行為，行為就會在不同步驟被理解成兩樣。**

### 凍結介面在整合時才被逐條比對

`SnapshotStore.record()` 寫成 `record(snapshot)`，凍結的是 `record(time, snapshot)`；`EntityRegistry` 凍結的是 `get()` 找不到 raise，實作的是 `require()`。都是整合時拿 issue 第 6 節逐條比對才發現。前者改成凍結簽名；後者是有理由的偏離（Mapping 的 `get()` 不能 raise），記入 ADR 005 第 9 點。

### reference scenario 的格式差點被整份改寫

用 `json.dumps(indent=2)` 遷移 reference scenario 時，所有 `[0, 0]` 都被展開成多行，diff 從 6 行變成 64 行。改回文字取代，只動實際要改的兩處。fixture 本來就是 `indent=2` 格式，不受影響。

### mypy 抓到 tactical policy 的隱含假設

`Location` 擴充為 `tuple | str` 後，policy 的 `ax, ay = actor.position` 被 mypy 拒絕：字串不能拆成兩個值。policy 本來就只在 grid 上走，所以加了一行「遇到節點 id 就不移動」，行為不變。**型別擴充會把「只有一種可能」的隱含假設翻出來**，這次是好事。

---

## 6. 品質狀態

| 項目 | 結果 |
|---|---|
| pytest | 182 passed（Phase 1 為 91） |
| 全專案覆蓋率 | 97%（1218 statements，35 miss；Phase 1 為 96%） |
| `runtime/` 覆蓋率 | 9 個檔案中 8 個 100%，`clock.py` 97% |
| ruff / black | 通過 |
| mypy（`python3 -m mypy src/`） | 通過，38 個檔案 |
| bandit | 0 issues |
| 換工作目錄跑測試 | 182 passed |
| 測試讀 `output/` | 0 處 |
| exporter 程式碼變動 | 0 行 |

### 測試分布

```text
tests/runtime/test_space_and_clock.py    20   三種空間、三種 clock；GridSpace 與 Phase 4 SpaceModel 逐點對照
tests/runtime/test_world_runtime.py      21   驗收 1–5；registry、resources、rules；engine 拒絕非 grid
tests/runtime/test_event_sourcing.py     26   驗收 6；snapshot；graph 世界的資源重建；runtime 分層
tests/contracts/test_schema_0_2.py       24   0.1 被拒；四欄必填；空間、時間、位置規則；新事件型別
既有測試                                   91   2 處改動：$id 版本、World Contract 必填清單
```

### 反向驗證過的測試

```text
test_a_resource_never_goes_below_zero_and_nothing_is_recorded   ResourceState 改成夾 0 → 紅
test_resource_changes_rebuild_on_a_graph_world                  rebuild 不套用資源 → 紅
test_runtime_never_imports_the_engine_a_policy_or_an_exporter   from .. import engine → 紅
                                                                from ..replay import … → 紅
```

---

## 7. 已知限制

| 項目 | 留待 | 原因 |
|---|---|---|
| tactical engine 只跑 grid + tick | Phase 3 起 | policy 在格子間走；runtime 本身支援全部三種 |
| tactical 的 MOVE / ATTACK 不經過 `update_entity_state()` | Phase 3 | 改了會改變事件型別；結果相同，但改世界的路徑有兩條 |
| 快照只存記憶體 | 文件寫明 later | in-memory first；可由 event memory 重建 |
| `SNAPSHOT_INTERVAL = 5` 沒有文件依據 | 需要時調 | 讓 10 tick 的 run 存下 0、5、10 三份，足以測試 |
| 沒有 `phase_event_hybrid` 時間 | 需要它的 Phase | 目前沒有 Phase 用到 |
| 0.1 scenario 不自動升級 | — | 刻意：自動升級會讓人以為舊檔仍被支援 |
| `event_id` / `action_id` 仍是 uuid4 | Phase 8 | 同 Phase 1 |
| `affected.risks` 恆為空 | Phase 7 / 9 | 風險模型尚未存在 |
| 套件不可安裝，tests / scripts 靠 `sys.path` | 未定 | 同 Phase 1 |

---

## 8. 驗證

```bash
python3 -m pip install pydantic pyyaml networkx pytest pytest-cov ruff black mypy bandit types-PyYAML types-networkx
rm -f output/*.json output/timeline.txt
python3 scripts/run_tactical_reference.py           # RED_survived / 97 events
python3 -m pytest tests/ -q                          # 182 passed
cd /tmp && python3 -m pytest ~/SKYVAULT/tests -q     # 182 passed
ruff check . && black --check src/ tests/ scripts/
python3 -m mypy src/
python3 -m bandit -c pyproject.toml -r src/          # 0 issues
python3 scripts/export_schemas.py && git status src/skyvault/schemas/   # 無變動
```

---

## 9. 一句話總結

> Phase 2 讓世界由 World Contract 建立 —— grid / graph / network 三種空間、tick / phase / event-driven 三種時間、實體登記、不得為負的資源帳 —— 並第一次證明 event memory 真的是真相：只靠它就能重建任一時刻的世界，到最後與 final_world_state 完全相等；契約升到 0.2，tactical reference 的模擬行為一點沒變。
