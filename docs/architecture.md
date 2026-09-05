# SKYVAULT — How It Works

系統目前的架構參考。描述**現在的樣子**，隨程式碼改動而更新。

各階段當時的凍結紀錄在 [`phases/`](phases/)。

---

# 1. 系統在做什麼

一次執行就是把一份 scenario JSON 變成一包可回放、可追溯的紀錄。

```text
scenario JSON
  │
  ├─ scenario_loader 讀成 dict
  │
  ├─ engine.build_world()  建立 tick 0 的 WorldState
  │
  ├─ engine.run()  擷取 initial_world_state，進入 tick 迴圈
  │   │
  │   └─ 每個 tick，對每個存活單位：
  │        policy.decide_action()      產生 Action（意圖）
  │        world.record_event()        記錄 ACTION_SELECTED
  │        engine.resolve_action()     驗證並結算 → Consequence
  │        （若 accepted）改變 WorldState
  │        world.record_event()        記錄結果事件
  │
  ├─ evaluator.build_evaluation_summary()
  ├─ world.record_event()  記錄 SCENARIO_END
  │
  └─ result_package
       └─ 四個 exporter 各自推導出一份輸出
```

## 三個關鍵設計

**只有 Consequence 能改變世界。** Policy 產生的是 Action，那只是「想做什麼」。Action 要先通過 validation 變成 accepted 的 Consequence，engine 才會動 WorldState。這條線讓「決策」與「生效」分開，policy 換掉不會影響世界規則。

**事件是快照，不是參照。** `record_event()` 存進去的 `before_state` / `after_state` 都是 `snapshot()` 的深拷貝。事件寫入後，世界再怎麼變都不會改到它。回放能成立完全靠這一點。

**exporter 不認識這個系統。** 四個 exporter 只 import 標準函式庫，收 plain dict、回傳 plain dict。它們在型別上就不可能反過來影響模擬。

---

# 2. 依賴階層

## 核心（有上下關係，禁止向上 import）

```text
                 ① scripts/
        run_tactical_reference.py
        啟動入口 / 開發 runner
────────────────────────────────────
                 ② engine.py
        流程總管 / simulation runtime
────────────────────────────────────
  ③ scenario_loader.py   tactical_reference_policy.py   evaluator.py
       讀 scenario          臨時 actor policy          結果計算
────────────────────────────────────
     ④ world_state.py   action.py   consequence.py
        世界狀態        行動嘗試      行動後果
────────────────────────────────────
       ⑤ entity.py      event_memory.py
        世界物件          事件記憶
────────────────────────────────────
        ⑥ data/scenarios/*.json
        scenario 原料 / 初始設定
```

允許的依賴方向：

```text
① → ②
② → ③ + ④ + ⑤
③ → ④ + ⑤ + ⑥
④ → ⑤
⑤ → 不依賴上層
⑥ → 不依賴 code
```

具體意思：

```text
① scripts/
需要 ② engine.py
原因：scripts 只負責啟動流程。

② engine.py
需要 ③ scenario_loader.py / tactical_reference_policy.py / evaluator.py
需要 ④ world_state.py / action.py / consequence.py
需要 ⑤ entity.py / event_memory.py
原因：engine 要把 scenario、world、policy、action、event、evaluation 串起來。

③ scenario_loader.py
需要 ⑥ data/scenarios/*.json
原因：它讀 scenario 原料。

③ tactical_reference_policy.py
需要 ④ world_state.py / action.py
需要 ⑤ entity.py
原因：policy 要看世界與 actor 狀態，然後產生 Action。

③ evaluator.py
需要 ④ world_state.py
需要 ⑤ entity.py / event_memory.py
原因：它要看最後世界狀態與事件紀錄來算結果。

④ world_state.py
需要 ⑤ entity.py / event_memory.py
原因：WorldState 由 Entity 組成，並記錄 Event。

④ action.py
需要 ⑤ entity.py 的 Position 型別
原因：Action 需要 target_position 格式。

④ consequence.py
不應依賴上層
原因：Consequence 只是 action 結算結果的資料格式。

⑤ entity.py / event_memory.py
不應依賴上層
原因：它們是底層資料物件。

⑥ data/scenarios/*.json
不依賴 code
原因：它只是輸入資料。
```

## Exporter（在階層之外）

```text
   timeline.py   replay.py   entity_history.py   causal_chain.py
              只 import 標準函式庫
              不依賴專案內任何模組
              只有 runner 會呼叫它們
```

這是刻意的。exporter 只能是資料的下游 —— 讓它們 import engine 或 world_state 就會開啟「輸出反過來影響模擬」的可能。目前這個可能性在型別上就不存在。

## 禁止向上 import

```python
# 不要在 entity.py / world_state.py / action.py 裡這樣做
from skyvault.engine import SkyVaultTacticalReferenceEngine
```

```python
# 不要在 world_state.py 裡這樣做
from skyvault.tactical_reference_policy import TacticalReferencePolicy
```

```python
# 不要在任何 exporter 裡這樣做
from skyvault.world_state import WorldState
```

核心規則：

```text
engine.py 可以知道 tactical_reference_policy.py。
world_state.py 不可以知道 tactical_reference_policy.py。
exporter 誰都不認識，只認得資料。

policy 決定 actor 想做什麼。
engine 結算 action。
world_state 儲存世界狀態。
event_memory 記錄發生過的事。
```

---

# 3. 各模組責任

## `entity.py`

定義：

```text
Position = tuple[int, int]
Entity
```

`Entity` 是世界裡存在的東西。取代了舊的 groundunit / humanbody / groundweapon 拆分。

欄位：

```python
entity_id       str
name            str
entity_type     str
faction         str | None
position        Position | None
state           dict      會變的東西：hp / ap / hunger / status / last_action
capabilities    dict      能力值：attack_damage / attack_range / accuracy
tags            list
```

方法：

```python
is_active()     state["status"] == "active"
snapshot()      回傳深拷貝的 JSON-safe dict
```

規則：

```text
Entity 只儲存自己的資料。
Entity 不可以決定行動。
Entity 不可以知道世界上有誰。
position 可以是 None —— 任何算距離的地方都要先確認。
狀態放 state，能力放 capabilities，不要混。
```

## `world_state.py`

定義：

```text
SpaceModel
WorldState
```

### `SpaceModel`

處理格子大小與距離計算。

欄位：

```python
width            int
height           int
distance_model   str    預設 "chebyshev"
```

方法：

```python
is_inside(position)     位置是否在格子內
distance(a, b)          兩點距離
```

支援三種距離模型：

```text
chebyshev        max(|dx|, |dy|)          預設，斜走與直走同價
manhattan        |dx| + |dy|
euclidean_floor  取整的直線距離
```

移動與攻擊射程都用同一個 `distance()`，所以換距離模型會同時改變兩者。

### `WorldState`

儲存目前模擬狀態。

欄位：

```python
world_id       str
scenario_id    str
tick           int
space          SpaceModel
entities       dict[str, Entity]
assumptions    dict
event_memory   list[Event]
```

方法：

```python
get_entity(entity_id)          找不到時 raise KeyError，不回傳 None
active_entities()              還活著的 entity
active_factions()              還有存活單位的陣營
is_occupied(position)          該位置有沒有活著的單位
record_event(...)              記錄一個事件
link_causal_predecessor(event) 把事件接到同 action 的前一個事件
snapshot()                     整個世界的深拷貝
```

規則：

```text
WorldState 可以儲存和改變世界資料。
WorldState 可以記錄事件。
WorldState 不可以選擇行動。
WorldState 不可以計算 threat_score。
WorldState 不可以決定攻擊目標。
```

**`get_entity()` 故意 raise 而不回傳 None** —— 錯的 id 要當場炸掉，不要變成後面某處的靜默 no-op。

**已記錄的事件不可修改。** `event_memory` 只被 append。

## `action.py`

定義：

```text
new_action_id()
Action
```

`Action` 是**意圖**，還沒生效。

欄位：

```python
action_id           str
actor_id            str
action_type         str          "move" / "attack"
target_entity_id    str | None
target_position     Position | None
intent              str
metadata            dict
```

規則：

```text
Action 只描述想做什麼。
Action 不改變世界。
Action 不判斷合不合法 —— 那是 engine 的事。
```

`new_action_id()` 用 `uuid4()`，**不受 scenario 的 random_seed 控制**。

## `consequence.py`

定義：

```text
Consequence
```

Action 結算後的結果資料。

欄位：

```python
action_id          str
accepted           bool
reason             str          被拒絕時說明原因
direct_effects     list         這個 action 造成的直接改變
evaluation_impact  dict
```

規則：

```text
只有 accepted=True 的 Consequence 能改變世界。
Consequence 只是資料，不含邏輯。
Consequence 不依賴上層任何模組。
```

被拒絕不是錯誤 —— 它會被記成 `ACTION_REJECTED` 事件，模擬照常繼續。

## `event_memory.py`

定義：

```text
new_event_id()
build_causal_links(source)
build_evaluation_relevance(source)
Event
```

`Event` 的欄位形狀已凍結，17 個 top-level 欄位：

```python
event_id              str
time                  int
event_type            str
actor_id              str | None
system_id             str | None      哪個系統做的決策
target_entity_id      str | None
source_action_id      str | None      causal_chain 靠這個分組
before_state          dict
after_state           dict
affected_entities     list
affected_locations    list
affected_resources    list            目前恆空
affected_risks        list            目前恆空
causal_links          dict            {caused_by: [], caused_events: []}
evaluation_relevance  dict            {affects_success, affects_cost, affects_risk}
data                  dict            型別專屬資料
tags                  list
```

方法：

```python
to_dict()    輸出成 JSON-safe dict
```

八種 `event_type`：

```text
ACTION_SELECTED   ACTION_REJECTED   MOVE      ATTACK
MISS              ENTITY_DESTROYED  NO_ACTION SCENARIO_END
```

規則：

```text
每個 event 都要有完整的 17 個 top-level 欄位。
空資料保留 empty list / empty dict，不要省略欄位。
不要把所有東西塞進 data。
event 寫入後不可修改。
```

為什麼是攤平而非巢狀：見 [`decisions/002_event_shape.md`](decisions/002_event_shape.md)。

`new_event_id()` 用 `uuid4()`，**不受 random_seed 控制**。

## `scenario_loader.py`

定義：

```text
load_scenario(path)
```

讀 scenario JSON，回傳 engine 要的 dict。

規則：

```text
只負責讀取與基本解析。
不建立 WorldState —— 那是 engine.build_world() 的事。
不驗證戰術合理性。
```

## `tactical_reference_policy.py`

定義：

```text
TacticalReferencePolicy
```

暫時性的 actor policy。**這不是 SKYVAULT core**，之後會被換掉。

方法：

```python
decide_action(world, actor)         回傳 Action 或 None
choose_target(world, actor)         挑攻擊目標
threat_score(world, actor, enemy)   目標的威脅評分
next_step_toward(world, actor, target)  往目標靠近一格
```

決策邏輯大致是：

```text
1. 有敵人在 attack_range 內  → 產生 attack action
2. 否則往最有威脅的敵人移動一格 → 產生 move action
3. 沒有可行動作 → 回傳 None（記為 NO_ACTION）
```

規則：

```text
policy 只提議，不執行。
policy 不改變世界。
policy 不記錄事件。
policy 用 engine 傳進來的 rng，不自己建立隨機來源。
```

隨機用在兩個地方：`choose_target()` 多個目標同分時挑一個、`next_step_toward()` 多個格子同分時挑一個。

## `engine.py`

定義：

```text
SkyVaultTacticalReferenceEngine
```

流程總管。持有整場模擬**唯一**的 `random.Random(seed)`，並交給 policy 共用。

方法：

```python
build_world(scenario)                    建立 tick 0 的 WorldState
run()                                    跑完整場，回傳 result_package
resolve_action(action)                   依 action_type 分派
resolve_move(action)                     驗證並結算移動
resolve_attack(action)                   驗證並結算攻擊
evaluate(termination_reason, event_count)  產生 evaluation summary
```

規則：

```text
engine 負責驗證與結算。
engine 不做輸出格式化。
engine 不含 replay / timeline / causal chain 邏輯。
engine 不直接改 entity —— 透過 Consequence 生效。
```

`evaluate()` 的 `event_count` 由 `run()` 明確傳入 `len(event_memory) + 1`，因為 evaluation 在 `SCENARIO_END` 寫入之前計算，必須把那個即將寫入的事件算進去。

## `evaluator.py`

定義：

```text
build_evaluation_summary(world, termination_reason, event_count)
```

從最終世界狀態與事件記錄算出結果摘要。

回傳欄位：

```python
termination_reason    str
event_count           int
active_entities       int
destroyed_entities    int
active_factions       list
winner_or_result      str
key_findings          list
failure_points        list
```

規則：

```text
evaluator 只讀，不改世界。
evaluator 不決定行動。
目前只有勝負與計數，不是多軸評估 —— 留給 Phase 7。
```

## Exporter

四個模組共同的規則：

```text
純函式：收資料、回傳資料。
不開檔、不寫檔。
module 層級不執行任何東西 —— import 不產生副作用。
不 import 專案內任何模組。
不修改 event_memory。
```

命名慣例：`build_*` 回傳結構，`render_*` 回傳文字。

### `timeline.py`

```python
build_entity_names(event_memory)             entity_id → 顯示名稱
write_event(time, entity_names, events)      一個 tick 的所有句子
render_timeline(scenario_id, event_memory)   整份 timeline 文字
```

`build_entity_names()` 先讀 `SCENARIO_END`（它一次帶著所有 entity），缺的再從各事件的快照補。

八種 event type 都有對應措辭。

### `replay.py`

```python
build_replay_state_at_tick(initial_world_state, event_memory, final_world_state)
```

輸出結構：

```text
{
  "scenario_id": ...,
  "states": {
    "0":     { "description": "initial state", "world_state": {...} },
    "1":     { "description": "after tick 1",  "world_state": {...} },
    ...
    "final": { "description": "final state",   "world_state": {...} }
  }
}
```

演算法的關鍵在 tick 邊界：

```python
# 下一個 tick 開始時，才封存上一個 tick
if previous_tick is not None and tick != previous_tick:
    states[str(previous_tick)] = snapshot()

# 迴圈結束後補最後一個 —— 因為它後面沒有下一個 tick
if previous_tick is not None:
    states[str(previous_tick)] = snapshot()
```

只封存在轉換點會漏掉最後一個 tick，因為它後面沒有轉換。

### `entity_history.py`

```python
build_record(time, event_type, role_in_event, ...)   一筆紀錄
build_entity_history(initial_world_state, event_list)
```

每個 entity 一個條目，含 `entity_id` / `name` / `faction` / `history`。

每筆 history 紀錄都有**同樣九個鍵**：

```python
time  event_type  role_in_event  event_id  source_action_id
before_state  after_state  data  tags
```

`role_in_event` 的值：

```text
initial_state   開局狀態
actor           它做的
target          它被指名為目標
affected        它被波及
final_state     ENTITY_DESTROYED / SCENARIO_END
```

`INITIAL_STATE` 與 `SCENARIO_END` 沒有來源事件，**保持同樣的九個鍵、把事件欄位留空**，而不是省略欄位 —— 讀取端因此不必分辨紀錄種類。

一個 entity 會被收錄的情況：它是 actor、它是 target、它出現在 `affected_entities`。同一個事件不會為同一個 entity 記兩次。

### `causal_chain.py`

```python
build_causal_chain(scenario_id, event_memory)
```

依 `source_action_id` 分組，每組一條 chain：

```text
{
  "source_action_id": "action_xxx",
  "events": [event_id, ...],        含 ACTION_SELECTED 本身，按 time 排序
  "event_types": [...],             排除 ACTION_SELECTED
  "summary": "Action action_xxx caused ATTACK and ENTITY_DESTROYED."
}
```

`event_types` 排除 `ACTION_SELECTED` 是為了讓 summary 讀起來是「造成攻擊與擊殺」，而不是「造成選取與攻擊與擊殺」。

`SCENARIO_END` 沒有 `source_action_id`，不納入任何 chain。

## `scripts/run_tactical_reference.py`

啟動入口。

```text
載入 scenario
跑 engine
從 result_package 取出欄位
呼叫四個 exporter
寫出七個檔案
印出摘要
```

規則：

```text
runner 只做 import exporter → call exporter → write file。
runner 不含模擬邏輯。
runner 不含格式化邏輯。
```

---

# 4. Engine 行為

## 每個 tick

```text
1. 設定 world.tick
2. 檢查 active factions
3. 取得 active entities
4. 對每個 active actor：
   4.1 policy 決定 action
   4.2 記錄 ACTION_SELECTED
   4.3 結算 action
   4.4 若 accepted，world state 改變
   4.5 記錄結果事件
5. 若只剩一個 faction，停止
6. 計算 evaluation
7. 記錄 SCENARIO_END
8. 回傳 result package
```

`initial_world_state` 在**步驟 1 之前**擷取，所以 result package 同時帶著起點與終點。

## Move resolution

Action 必須包含 `target_position`。

驗證：

```text
target_position 存在
target_position 在 world 內
target_position 未被佔用
```

若通過：

```text
actor.position 改變
actor.state["last_action"] = "move"
記錄 MOVE event
Consequence accepted=True
```

若不通過：

```text
Consequence accepted=False
記錄 ACTION_REJECTED event
```

## Attack resolution

Action 必須包含 `target_entity_id`。

驗證：

```text
target 存在
actor 有 position
target 有 position
target 在 attack_range 內
```

結算：

```text
用 accuracy 做命中判定（engine 的 seeded rng）

miss  → 記錄 MISS event
hit   → target hp 扣 attack_damage
        記錄 ATTACK event
        若 hp <= 0：
            target status 改為 "destroyed"
            記錄 ENTITY_DESTROYED event
```

被摧毀的 entity **不會從 `world.entities` 移除**，只是標記。事件記憶還在引用它，所以它必須保持可用 id 定址。

---

# 5. 事件如何被記錄

這一節解釋 `record_event()` 實際做了什麼 —— 回放與追溯全部建立在這上面。

## 快照，不是參照

```python
before = target.snapshot()      # 深拷貝
# ... 改變世界 ...
after = target.snapshot()       # 另一份深拷貝
```

兩份都是獨立的資料。事件寫進 `event_memory` 之後，世界再怎麼變都不會影響它。

**如果改成淺拷貝或直接存物件參照，回放就會全部壞掉** —— 每個 tick 的「歷史狀態」都會變成最終狀態。

## before_state / after_state 記的是誰

```text
有 target 的事件（ATTACK / MISS / ENTITY_DESTROYED）
    → 記的是 target 的狀態

沒有 target 的事件（ACTION_SELECTED / MOVE）
    → 記的是 actor 的狀態

SCENARIO_END
    → after_state 帶著所有 entity
```

`entity_history.py` 需要為 actor 補上它自己的狀態，所以它會快取 `ACTION_SELECTED` 時的 actor 快照。

## 因果連結怎麼建立

`link_causal_predecessor()`：

```python
if event.source_action_id is None:
    return

for earlier in reversed(self.event_memory):
    if earlier.source_action_id != event.source_action_id:
        continue
    event.causal_links["caused_by"].append(earlier.event_id)
    earlier.causal_links["caused_events"].append(event.event_id)
    return
```

往回找**最近一個**同 `source_action_id` 的事件，雙向連起來。

所以一個 action 的事件會串成鏈：

```text
ACTION_SELECTED  ←caused_by─  ATTACK  ←caused_by─  ENTITY_DESTROYED
```

**這是記帳，不是因果推論。** 只有 engine 已經確定同屬一個 action 的事件才會被連起來，不猜測任何東西。

---

# 6. 輸出

執行一次產生七個檔案。

## Truth source

### `event_memory.json`

**唯一真相來源。** 一個 event 的完整陣列，每個含 17 個欄位。

所有其他輸出都由它推導。任何模組都不得修改它。

### `result_package.json`

一次執行的完整包裝：

```python
scenario_id          str
scenario_version     str
initial_world_state  dict     tick 0 的世界
final_world_state    dict     結束時的世界
event_memory         list     所有事件
evaluation           dict     結果摘要
```

**四個 exporter 的輸入全部來自這裡**，不從 scenario 檔取得任何東西。

### `final_state.json`

終局世界狀態。內容與 `result_package["final_world_state"]` 相同，另存一份方便直接查看。

## Derived output

| 檔案 | 回答什麼 | 由誰產生 |
|---|---|---|
| `timeline.txt` | 這場照時間順序發生了什麼 | `render_timeline()` |
| `replay_state_at_tick.json` | 第 N 個 tick 結束時世界長什麼樣 | `build_replay_state_at_tick()` |
| `entity_history.json` | 某個 entity 一生經歷了什麼 | `build_entity_history()` |
| `causal_chain.json` | 哪個 action 造成哪些 event | `build_causal_chain()` |

四個都是純推導 —— 刪掉重跑會得到相同內容（除了 uuid）。

---

# 7. 決定論

scenario 宣告 `random_seed`，engine 建立**唯一**的 `random.Random(seed)` 並交給 policy 共用。

隨機只用在三個地方：

```text
engine.resolve_attack()          命中判定
policy.choose_target()           多個目標同分時挑一個
policy.next_step_toward()        多個移動格同分時挑一個
```

同一個 seed 每次跑出完全相同的行為 —— 同樣的事件數、同樣的型別順序、同樣的勝負。

**但 `event_id` 與 `action_id` 用 `uuid4()`，不受 seed 控制**，`causal_links` 裡也存 id，所以 `output/*.json` 無法跨 run 逐位元比對。這是已知限制，留待 Phase 8。

實測：seed 42 → `RED_survived`；seed 7 → `BLUE_survived`。雙方單位完全對稱，勝負純由擲骰決定。

---

# 8. 不變量

改動程式碼時，這些必須一直成立。破壞其中任何一條都不會立刻報錯，但會在整合或回放時爆出來。

```text
1. event_memory 只被 append，永不修改已寫入的事件
2. before_state / after_state 是深拷貝
3. 每個 event 有完整 17 個 top-level 欄位，空值保留為 [] 或 {}
4. 只有 accepted 的 Consequence 能改變世界
5. 被摧毀的 entity 保留在 world.entities，只改 status
6. 整場模擬只有一個 random.Random 實例
7. exporter 不 import 專案內任何模組
8. exporter 不寫檔
9. evaluation.event_count == len(event_memory)
10. result_package 的欄位足以產生全部四個 derived output
```

---

# 9. Debug checklist

| 症狀 | 先看哪裡 |
|---|---|
| 事件數不對 | `len(event_memory)` vs `evaluation.event_count` |
| 某個 tick 狀態不對 | `replay_state_at_tick.json` 的該 tick |
| 某個 entity 行為奇怪 | `entity_history.json` 的該 entity |
| 不知道某個結果從哪來 | `causal_chain.json` 找 `source_action_id` |
| 想快速看懂整場 | `timeline.txt` |
| 結果每次不同 | 檢查 `random_seed`；檢查有沒有人另外建了 `Random()` |
| 輸出檔內容是錯的 | 確認 runner 有呼叫 exporter，而不是寫入別的東西 |
| 回放的歷史狀態都是最終狀態 | 檢查 `snapshot()` 是否被改成淺拷貝 |
| 攻擊打不到 | 檢查 `distance_model`，移動與射程共用同一個 |
| import 時產生檔案 | 某個模組在 module 層級做 I/O |

`timeline.txt` 目前有一個已知缺陷：致命一擊會顯示錯誤的傷害數字。詳見 [`phases/phase4_event_memory.md`](phases/phase4_event_memory.md) 第 6 節。

---

# 10. 環境與工具

```text
Python 3.10+     程式碼用到 X | None 聯集語法（PEP 604）
開發環境          3.11
執行時期相依       無，只用標準函式庫
```

```bash
python3 scripts/run_tactical_reference.py       # 跑一次
python3 -m pytest tests/ -q                     # 測試
python3 -m pytest tests/ -q --cov               # 覆蓋率
ruff check .                                    # linter
black --check src/ tests/ scripts/              # 排版
mypy src/                                       # 型別
python3 -m bandit -c pyproject.toml -r src/     # 安全掃描
```

所有工具設定集中在 `pyproject.toml`。

---

# 11. 相關文件

| 文件 | 內容 |
|---|---|
| [`handoff.md`](handoff.md) | 接手指南、地雷區、送 PR 前的檢查 |
| [`phases/phase4_tactical_slice.md`](phases/phase4_tactical_slice.md) | Phase 4 結束時的完整技術文件（1510 行凍結紀錄） |
| [`phases/phase4_event_memory.md`](phases/phase4_event_memory.md) | Phase 4 完成報告 |
| [`phases/phase0_tactical_slice.md`](phases/phase0_tactical_slice.md) | Phase 0 凍結紀錄 |
| [`postmortems/phase4.md`](postmortems/phase4.md) | Phase 4 回顧 |
| [`decisions/002_event_shape.md`](decisions/002_event_shape.md) | 為什麼 event 是攤平的 |
