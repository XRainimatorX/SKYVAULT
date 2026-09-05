# SKYVAULT Tactical Reference Slice — Phase 4 完整技術文件

> 這是 Phase 4 結束時 README 的完整內容（commit `5ae69fc`，1510 行），
> 完整保留，未經刪節。
>
> 這份是**凍結紀錄**，描述 Phase 4 當時的狀態，不再更新。
> 系統目前的樣子請看 [`../architecture.md`](../architecture.md)。

---

# SKYVAULT Tactical Reference Slice v0.1

## 1. 目的

這個 repo 是一個小型可執行的 SKYVAULT 技術切片。

它用來驗證以下流程：

```text
scenario json
→ world state
→ actor policy
→ action
→ validation
→ consequence
→ world state mutation
→ event memory
→ evaluation
→ output json
```

目前這個 repo 只運行一個 tactical reference scenario。

---

## 2. 環境需求

Python 版本：

```text
Python 3.10+
```

執行主程式不需要額外套件。

測試需要：

```text
pytest
```

安裝測試套件：

```bash
pip install pytest
```

---

## 3. Repo 結構

```text
SKYVAULT/
├── README.md
├── src/
│   └── skyvault/
│       ├── __init__.py
│       ├── entity.py
│       ├── world_state.py
│       ├── action.py
│       ├── consequence.py
│       ├── event_memory.py
│       ├── scenario_loader.py
│       ├── tactical_reference_policy.py
│       ├── evaluator.py
│       ├── engine.py
│       ├── timeline.py
│       ├── replay.py
│       ├── entity_history.py
│       └── causal_chain.py
│
├── data/
│   └── scenarios/
│       └── tactical_reference_001.json
│
├── scripts/
│   └── run_tactical_reference.py
│
├── output/
│   ├── event_memory.json
│   ├── final_state.json
│   ├── result_package.json
│   ├── timeline.txt
│   ├── replay_state_at_tick.json
│   ├── entity_history.json
│   └── causal_chain.json
│
└── tests/
    ├── test_tactical_reference_slice.py
    ├── test_event_memory.py
    ├── test_timeline.py
    ├── test_replay.py
    ├── test_entity_history.py
    └── test_causal_chain.py
```

---

## 4. 執行方式

在 repo root 執行：

```bash
python scripts/run_tactical_reference.py
```

一次執行會產生全部七個 Phase 4 輸出：

```text
output/event_memory.json            engine 記錄的完整事件歷史（truth source）
output/final_state.json             scenario 結束時的世界狀態
output/result_package.json          上面兩者加上 evaluation 的整包結果
output/timeline.txt                 人類可直接閱讀的時間線
output/replay_state_at_tick.json    每個 tick 結束時的世界快照
output/entity_history.json          每個 entity 的完整生命歷史
output/causal_chain.json            action 到 event 的因果鏈
```

前三個是 Step 1 既有輸出，後四個是 Phase 4 新增。四個 Phase 4 輸出全部由
`event_memory.json` 推導而來，runner 只負責呼叫各自的 exporter 並寫檔，不含任何
轉換邏輯。

---

## 5. 測試方式

在 repo root 執行：

```bash
python -m pytest
```

測試內容包括：

```text
scenario 能載入
engine 能運行
event 能產生
event 包含 before_state 與 after_state
tactical policy 與 world state 分離
```

---

## 6. 執行流程

```text
scripts/run_tactical_reference.py
    ↓
scenario_loader.load_scenario()
    ↓
SkyVaultTacticalReferenceEngine(scenario)
    ↓
engine.build_world()
    ↓
WorldState
    ↓
TacticalReferencePolicy.decide_action()
    ↓
Action
    ↓
engine.resolve_action()
    ↓
Consequence
    ↓
WorldState mutation
    ↓
WorldState.record_event()
    ↓
engine.evaluate()
    ↓
result_package.json
event_memory.json
final_state.json
```

---

## 7. Repo 上下級金字塔與 Import 規則

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
需要 ⑤ entity.py 的 Position 型別概念
原因：Action 需要 target_position 格式。

④ consequence.py
不應依賴上層
原因：Consequence 只是 action 結算結果資料格式。

⑤ entity.py / event_memory.py
不應依賴上層
原因：它們是底層資料物件。

⑥ data/scenarios/*.json
不依賴 code
原因：它只是輸入資料。
```

禁止向上 import。

錯誤例子：

```python
# 不要在 entity.py / world_state.py / action.py 裡這樣做
from skyvault.engine import SkyVaultTacticalReferenceEngine
```

```python
# 不要在 world_state.py 裡這樣做
from skyvault.tactical_reference_policy import TacticalReferencePolicy
```

核心規則：

```text
engine.py 可以知道 tactical_reference_policy.py。
world_state.py 不可以知道 tactical_reference_policy.py。

policy 決定 actor 想做什麼。
engine 結算 action。
world_state 儲存世界狀態。
event_memory 記錄發生過的事。
```

---

## 8. 各檔案責任

### `entity.py`

定義 `Entity`。

`Entity` 是世界內存在的物件。

欄位：

```python
entity_id: str
name: str
entity_type: str
faction: str | None
position: tuple[int, int] | None
state: dict
capabilities: dict
tags: list[str]
```

重要方法：

```python
is_active()
snapshot()
```

規則：

```text
不要在這裡放移動邏輯。
不要在這裡放攻擊邏輯。
不要在這裡放目標選擇邏輯。
```

---

### `world_state.py`

定義：

```text
SpaceModel
WorldState
```

`SpaceModel` 處理 grid 大小與距離計算。

重要方法：

```python
is_inside(position)
distance(a, b)
```

`WorldState` 儲存目前模擬狀態。

欄位：

```python
world_id
scenario_id
tick
space
entities
assumptions
event_memory
```

重要方法：

```python
get_entity(entity_id)
active_entities()
active_factions()
is_occupied(position)
record_event(...)
snapshot()
```

規則：

```text
WorldState 可以儲存和改變世界資料。
WorldState 可以記錄事件。
WorldState 不可以選擇行動。
WorldState 不可以計算 threat_score。
WorldState 不可以決定攻擊目標。
```

---

### `action.py`

定義 `Action`。

`Action` 表示 actor 嘗試做某件事。

欄位：

```python
action_id: str
actor_id: str
action_type: str
target_entity_id: str | None
target_position: tuple[int, int] | None
intent: str
metadata: dict
```

v0.1 支援的 action type：

```text
move
attack
```

規則：

```text
Action 不會自己改變 world state。
Action 只是一次嘗試。
```

---

### `consequence.py`

定義 `Consequence`。

`Consequence` 表示 action 被結算後的結果。

欄位：

```python
action_id: str
accepted: bool
reason: str
direct_effects: list[dict]
evaluation_impact: dict
```

例子：

```python
Consequence(
    action_id="action_x",
    accepted=True,
    reason="Attack resolved",
    direct_effects=[
        {
            "type": "hp_change",
            "entity_id": "blue_001",
            "from": 35,
            "to": 25
        }
    ],
    evaluation_impact={"damage_done": 10}
)
```

規則：

```text
Action = 嘗試做什麼。
Consequence = 結算後發生什麼。
Event = 被記錄下來的事實。
```

---

### `event_memory.py`

定義 `Event`。

`Event` 是世界內已發生並被記錄的事實。

欄位：

```python
event_id: str
time: int
event_type: str
actor_id: str | None
target_entity_id: str | None
source_action_id: str | None
before_state: dict
after_state: dict
data: dict
tags: list[str]
```

目前 event types：

```text
ACTION_SELECTED
ACTION_REJECTED
MOVE
ATTACK
MISS
ENTITY_DESTROYED
SCENARIO_END
NO_ACTION
```

規則：

```text
每個會改變狀態的 event 必須包含 before_state 和 after_state。
event 用於 debug、replay、後續 evaluation。
```

---

### `scenario_loader.py`

載入 scenario JSON。

必要 top-level keys：

```python
REQUIRED_KEYS = {
    "scenario_id",
    "scenario_version",
    "world_contract",
    "entities",
    "runtime",
    "evaluation",
}
```

函式：

```python
load_scenario(path)
```

規則：

```text
這個檔案只負責載入與基本驗證。
不要在這裡建立 entities。
不要在這裡執行 simulation。
```

---

### `tactical_reference_policy.py`

定義 `TacticalReferencePolicy`。

這個檔案負責替 actor 選擇 action。

這裡允許存在：

```text
choose_target
threat_score
target_score
next_step_toward
temporary tactical decision logic
```

重要方法：

```python
decide_action(world, actor)
choose_target(world, actor, enemies)
threat_score(actor, enemy)
next_step_toward(world, actor, target)
```

規則：

```text
這個檔案可以讀 WorldState。
這個檔案可以建立 Action。
這個檔案不可以改變 WorldState。
這個檔案不可以直接扣 HP。
這個檔案不可以記錄 event。
```

這個檔案只是 v0.1 的臨時支援。

它不是 SKYVAULT core。

---

### `engine.py`

定義：

```python
SkyVaultTacticalReferenceEngine
```

主要責任：

```text
從 scenario 建立 world
執行 tick loop
向 policy 要 action
記錄 ACTION_SELECTED
驗證 action
結算 move
結算 attack
記錄 world events
計算 evaluation
回傳 result package
```

重要方法：

```python
build_world(scenario)
run()
resolve_action(action)
resolve_move(action)
resolve_attack(action)
evaluate(termination_reason)
```

規則：

```text
engine.py 可以 import tactical_reference_policy.py。
engine.py 負責控制 simulation flow。
engine.py 可以把 core objects 串起來。
```

---

### `evaluator.py`

若使用此檔案，應放置結果計算邏輯。

v0.1 可以先把簡單 evaluation 放在 `engine.py` 內。

未來方向：

```text
當 evaluation 變大時，將 engine.py 內的 evaluation logic 移到 evaluator.py。
```

Evaluation 應計算：

```text
event_count
active_entities
destroyed_entities
active_factions
winner_or_result
key_findings
failure_points
```

---

### `timeline.py`

This file is dedicated for human reading.

It has converted the json file "event_memory.json" into human readable sentences for tracing purposes.

Example sentences include:

```text
Tick 1

- Red Rifleman selected MOVE
- Red Rifleman moved from (0, 0) to (0, 1).

Tick 5

- Red Rifleman selected ATTACK against Blue Commander
- Red Rifleman attacked Blue Commander but missed.

Tick 6

- Red Rifleman selected ATTACK against Blue Commander
- Red Rifleman successfully attacked Blue Commander: HP 7 -> 0 (damage = 7)
- Blue Commander in the BLUE faction was destroyed by Red Rifleman
```

---

### `entity_history.py`

The purpose for this file is to record actions from each entity.

This is done by extracting data from the event_memory.json and separating into events for each entities.

It includes events where an entity is an actor, the target, or affected.

Example data includes:

```text
{
        "time": 4,
        "event_type": "MISS",
        "role_in_event": "actor",
        "event_id": "event_76dc7b39b0",
        "source_action_id": "action_b5dd8940b5",
        "before_state": {
          "entity_id": "blue_002",
          "name": "Blue Support",
          "entity_type": "tactical_actor",
          "faction": "BLUE",
          "position": [
            5,
            6
          ],
          "state": {
            "hp": 32,
            "ap": 50,
            "hunger": 50,
            "status": "active",
            "last_action": "move"
          },
          "capabilities": {
            "attack_damage": 16,
            "attack_range": 2,
            "accuracy": 0.55
          },
          "tags": [
            "SUPPORT"
          ]
        },
        "after_state": {
          "entity_id": "blue_002",
          "name": "Blue Support",
          "entity_type": "tactical_actor",
          "faction": "BLUE",
          "position": [
            5,
            6
          ],
          "state": {
            "hp": 32,
            "ap": 50,
            "hunger": 50,
            "status": "active",
            "last_action": "move"
          },
          "capabilities": {
            "attack_damage": 16,
            "attack_range": 2,
            "accuracy": 0.55
          },
          "tags": [
            "SUPPORT"
          ]
        },
        "data": {
          "accuracy": 0.55,
          "distance": 2
        },
        "tags": [
          "attack",
          "miss"
        ]
      }
```

and

```text
{
        "time": 4,
        "event_type": "MISS",
        "role_in_event": "target",
        "event_id": "event_76dc7b39b0",
        "source_action_id": "action_b5dd8940b5",
        "before_state": {
          "entity_id": "red_003",
          "name": "Red Commander",
          "entity_type": "tactical_actor",
          "faction": "RED",
          "position": [
            4,
            4
          ],
          "state": {
            "hp": 30,
            "ap": 60,
            "hunger": 60,
            "status": "active",
            "last_action": "move"
          },
          "capabilities": {
            "attack_damage": 7,
            "attack_range": 1,
            "accuracy": 0.7
          },
          "tags": [
            "COMMAND"
          ]
        },
        "after_state": {
          "entity_id": "red_003",
          "name": "Red Commander",
          "entity_type": "tactical_actor",
          "faction": "RED",
          "position": [
            4,
            4
          ],
          "state": {
            "hp": 30,
            "ap": 60,
            "hunger": 60,
            "status": "active",
            "last_action": "move"
          },
          "capabilities": {
            "attack_damage": 7,
            "attack_range": 1,
            "accuracy": 0.7
          },
          "tags": [
            "COMMAND"
          ]
        },
        "data": {
          "accuracy": 0.55,
          "distance": 2
        },
        "tags": [
          "attack",
          "miss"
        ]
      }
```
These two sets of data perfectly demonstrates how the same event (with the same event_id) could be recorded twice.

This is due to one of the entity being actor while the other being target.

Therefore, every perspective of the events has been recorded into separate entities as their historical records.

---

### `replay.py`

負責從 event_memory 重建每個 tick 結束時的世界狀態。

作法是拿 scenario 的初始 entity 清單當起點，依序讀過每個 event 的
`after_state`，更新該 entity 的最新已知狀態；每當 tick 改變，就把當下所有
entity 的狀態拍一張快照存進 `states`。

對外只暴露一個函式：

```python
build_replay_state_at_tick(scenario, event_memory, final_world_state) -> dict
```

它不開檔、不寫檔，資料由呼叫端傳入、結果由呼叫端決定怎麼存。所以 import 這個
模組不會產生任何副作用。

不做 timeline 排版、不做 causal chain 分組、不修改 world state。

---

### `causal_chain.py`

負責回答「哪一個 action 造成了哪些後果」。

作法是把 event_memory 依 `source_action_id` 分組，同一組內依 `time` 排序，
串成一條鏈。`ACTION_SELECTED` 的 event_id 會保留在 `events` 裡，但不列進
`event_types`，因為它是決定本身而不是後果。

對外只暴露一個函式：

```python
build_causal_chain(scenario_id, event_memory) -> dict
```

同樣不開檔、不寫檔、import 無副作用。

沒有 action 來源的 event（`NO_ACTION` 的 `source_action_id` 是 `None`、
`SCENARIO_END` 也沒有）不會被歸進任何一條鏈；`SCENARIO_END` 另外放在
`scenario_end` 欄位。

---

### `scripts/run_tactical_reference.py`

開發用 runner。

責任：

```text
設定 repo root
設定 src path
載入 scenario
建立 engine
執行 engine
寫出 output json files
印出 terminal summary
```

規則：

```text
路徑處理應放在這裡。
core files 不應 hardcode repo-root paths。
```

---

### `data/scenarios/tactical_reference_001.json`

輸入 scenario。

這個檔案取代舊 prototype 裡 hardcoded team / unit setup。

包含：

```text
scenario_id
scenario_version
world_contract
entities
runtime
evaluation
```

規則：

```text
JSON 只儲存資料。
不要在 JSON 內放行為邏輯。
不要在 JSON 內放必須執行的 Python function 名稱。
```

---

### `tests/test_tactical_reference_slice.py`

測試檔案。

應測試：

```text
scenario loading
engine running
event creation
before_state / after_state existence
policy separation
```

---

### `tests/test_timeline.py`

Testing the `timeline.py` file.

The following tests had been included:

```text
String output
Title and Scenario ID inclusion
Tick inclusion
Human-readable events output
Textfile existence
```

---

### `tests/test_entity_history.py`

Testing the `entity_history.py` file/

The following tests had been included:

```text
Basic structure for output
Non-emptiness of output
Existence of records for factions
Basic structure of entities
Existence of records for INITIAL_STATE
Existence of records for all states (initial, before, after, final)
```

---

## 9. Scenario JSON 格式

最小合法結構：

```json
{
  "scenario_id": "tactical_reference_001",
  "scenario_version": "v0.1",
  "world_contract": {},
  "entities": [],
  "runtime": {},
  "evaluation": {}
}
```

---

### `world_contract`

例子：

```json
{
  "world_id": "tactical_reference_world_001",
  "world_scope": "tactical_reference_environment",
  "purpose": [
    "state_change_test",
    "action_consequence_test",
    "event_memory_test",
    "evaluation_result_test"
  ],
  "space_model": {
    "type": "grid",
    "width": 10,
    "height": 10,
    "distance_model": "chebyshev"
  },
  "time_model": {
    "type": "tick",
    "max_ticks": 10
  },
  "assumption_registry": {
    "movement_model": "one_step_grid",
    "combat_resolution": "accuracy_damage",
    "actor_policy": "temporary_tactical_reference_policy",
    "distance_model": "chebyshev"
  },
  "evaluation_targets": [
    "world_state_changed",
    "event_memory_created",
    "result_package_created"
  ]
}
```

---

### `entities`

entity 例子：

```json
{
  "entity_id": "red_001",
  "name": "Red Rifleman",
  "entity_type": "tactical_actor",
  "faction": "RED",
  "position": [0, 0],
  "state": {
    "hp": 35,
    "ap": 50,
    "hunger": 50,
    "status": "active"
  },
  "capabilities": {
    "attack_damage": 10,
    "attack_range": 1,
    "accuracy": 0.8
  },
  "tags": ["ASSAULT"]
}
```

欄位意思：

```text
entity_id      唯一 ID
name           顯示名稱
entity_type    entity 類型
faction        RED / BLUE / 其他 faction
position       [x, y]
state          目前狀態數值
capabilities   entity 可做什麼
tags           role / category labels
```

重要：

```text
state.hp 是資料。
capabilities.attack_damage 是資料。
tags 是標籤。
行為邏輯不放在這裡。
```

---

### `runtime`

例子：

```json
{
  "max_ticks": 10,
  "random_seed": 42,
  "deterministic_mode": true
}
```

欄位意思：

```text
max_ticks            最大 simulation ticks
random_seed          deterministic random choices 的 seed
deterministic_mode   是否要求可重跑
```

---

### `evaluation`

例子：

```json
{
  "primary_metrics": [
    "event_count",
    "active_entities",
    "destroyed_entities",
    "winner_or_result"
  ],
  "failure_thresholds": [
    "all_entities_destroyed"
  ]
}
```

---

## 10. Output files

### `output/event_memory.json`

完整 event list，Phase 4 的 truth source。其餘四個 Phase 4 輸出全部由它推導。

每個 event 都有同樣的 17 個欄位，即使某個欄位當下沒有資料也保留空結構：

```json
{
  "event_id": "event_xxxxx",
  "time": 1,
  "event_type": "MOVE",
  "actor_id": "red_001",
  "system_id": "temporary_tactical_reference_policy",
  "target_entity_id": null,
  "source_action_id": "action_xxxxx",
  "affected_entities": ["red_001"],
  "affected_locations": [[0, 0], [1, 1]],
  "affected_resources": [],
  "affected_risks": [],
  "before_state": {},
  "after_state": {},
  "causal_links": {
    "caused_by": ["event_yyyyy"],
    "caused_events": []
  },
  "evaluation_relevance": {
    "affects_success": false,
    "affects_cost": true,
    "affects_risk": false
  },
  "data": {
    "from": [0, 0],
    "to": [1, 1]
  },
  "tags": ["movement", "world_state_mutation"]
}
```

幾個欄位的意義：

```text
system_id             這個行動是哪個系統下的。目前是 scenario 宣告的 actor_policy；
                      SCENARIO_END 帶引擎自己的識別。
affected_*            這個 event 影響到誰、哪裡、哪些資源與風險。
causal_links          同一個 action 解算出來的 event 互相串起來。
evaluation_relevance  這件事是否影響成敗、成本、風險。
```

`affected_resources` 與 `affected_risks` 目前恆為空 —— 引擎沒有任何 action 會改動
`ap` / `hunger`，風險也還不是系統裡存在的概念。欄位保留但不填值，理由見
`docs/decisions/002_event_shape.md`。

用途：

```text
用來逐步 debug simulation 行為，也是 timeline / replay / entity_history /
causal_chain 四個輸出的唯一資料來源。
```

---

### `output/final_state.json`

最終 world state。

預期包含：

```text
world_id
scenario_id
tick
space
entities
assumptions
```

用途：

```text
檢查最終 HP、position、status、faction survival。
```

---

### `output/result_package.json`

主要輸出報告。

預期包含：

```text
scenario_id
scenario_version
final_world_state
event_memory
evaluation
```

evaluation 預期包含：

```text
termination_reason
event_count
active_entities
destroyed_entities
active_factions
winner_or_result
key_findings
failure_points
```

---

### `output/timeline.txt`

把 event_memory 翻成一份從頭讀到尾就看得懂的戰況記錄，不需要打開任何 JSON。

格式：

```text
SKYVAULT Tactical Reference Timeline
Scenario: tactical_reference_001

Tick 1

- Red Rifleman selected MOVE
- Red Rifleman moved from (0, 0) to (0, 1).

Tick 7

- Red Support selected ATTACK against Blue Rifleman
- Red Support successfully attacked Blue Rifleman: HP 5 -> 0 (damage = 5)
- Blue Rifleman in the BLUE faction was destroyed by Red Support

Scenario Ended: termination_condition_met
- Result: RED_survived
```

八種 event type 全部支援：`ACTION_SELECTED` / `ACTION_REJECTED` / `MOVE` /
`ATTACK` / `MISS` / `ENTITY_DESTROYED` / `NO_ACTION` / `SCENARIO_END`。

---

### `output/replay_state_at_tick.json`

每個 tick 結束時，世界長什麼樣。用來回答「第 5 回合的時候戰場是什麼狀態」。

```text
scenario_id
states
  "0"       初始狀態
  "1".."N"  每個 tick 結束後的世界
  "final"   scenario 結束時的世界
```

每個 state 底下有 `description` 與 `world_state`，`world_state` 是 entity_id
對應到該 entity 當下的完整快照。

---

### `output/entity_history.json`

以 entity 為主軸重新整理事件，回答「這個單位一路上發生過什麼」。

每個 entity 包含：

```text
entity_id
name
faction
history
```

`history` 裡每一筆 record 形狀一致，都含九個欄位：

```text
time
event_type
role_in_event
event_id
source_action_id
before_state
after_state
data
tags
```

`role_in_event` 可能是 `initial_state` / `actor` / `target` / `affected` /
`final_state`。一個 entity 會被記錄三種情況：它是 actor、它是 target、以及它
出現在該 event 的 `affected_entities` 裡。

---

### `output/causal_chain.json`

把同一個 action 產生的事件串成一條鏈，回答「哪個決定造成了哪些後果」。

```text
scenario_id
chains
  source_action_id
  events         該 action 產生的 event_id，依 time 排序
  event_types    去掉 ACTION_SELECTED 後的後果類型
  summary        一句話描述這條鏈
scenario_end
```

分組只依據 `source_action_id`。沒有 action 來源的事件（`NO_ACTION`、
`SCENARIO_END`）不會被硬塞進任何一條鏈。

---

## 10.1 Phase 4 已知限制

以下項目在 Phase 4 刻意不做，留給後續階段。記在這裡是為了讓接手的人不用重新考古。

| 項目 | 延到哪一階段 | 為什麼 |
|---|---|---|
| `event_id` / `action_id` 不受 `random_seed` 控制 | Phase 8 Reproducibility | 兩者都用 `uuid4()`。scenario 宣告 `deterministic_mode: true`，模擬**行為**確實每次相同（同樣 97 個 event、同樣型別、同樣 `RED_survived`），但 id 每次不同，所以 `output/*.json` 無法跨 run 逐位元比對 |
| event 是攤平的 17 欄，而非 Formal Spec §7.2 的巢狀 `source:` / `affected:` | Phase 1 Contract Pack | 該階段的交付物明確包含「Event Schema」。詳見 `docs/decisions/002_event_shape.md` |
| `affected_resources` 每個 event 都是 `[]` | Phase 2 World Runtime Core | 引擎沒有任何 action 會改動 `ap` / `hunger`，資源模型還不存在 |
| `affected_risks` 每個 event 都是 `[]` | Phase 7 / Phase 9 | 風險還不是系統裡存在的概念 |
| evaluation 只有勝負與計數，不是多軸評估 | Phase 7 Evaluation Engine | Phase 4 只需要 `SCENARIO_END` 與 result_package 有足夠欄位可用 |

---

## 11. Engine 行為

每個 tick：

```text
1. 設定 world.tick
2. 檢查 active factions
3. 取得 active entities
4. 對每個 active actor：
   4.1 policy 決定 action
   4.2 engine 記錄 ACTION_SELECTED
   4.3 engine 結算 action
   4.4 如果 action 成功，world state 改變
   4.5 event memory 記錄結果
5. 如果只剩一個 faction，停止
6. 計算 evaluation
7. 記錄 SCENARIO_END
8. 回傳 result package
```

---

## 12. Move resolution

Move action 必須包含：

```python
target_position
```

Validation：

```text
target_position 存在
target_position 在 world 內
target_position 未被佔用
```

若 valid：

```text
actor.position 改變
actor.state["last_action"] = "move"
記錄 MOVE event
Consequence accepted=True
```

若 invalid：

```text
Consequence accepted=False
記錄 ACTION_REJECTED event
```

---

## 13. Attack resolution

Attack action 必須包含：

```python
target_entity_id
```

Validation：

```text
target 存在
actor 有 position
target 有 position
target 在 attack_range 內
```

Resolution：

```text
用 accuracy 做 random hit check
如果 miss：
    記錄 MISS event
如果 hit：
    target hp 扣 attack_damage
    記錄 ATTACK event
如果 hp <= 0：
    target status 變成 destroyed
    記錄 ENTITY_DESTROYED event
```

---

## 14. 分離規則

### 正確

```text
tactical_reference_policy.py 選擇 Action
engine.py 結算 Action
world_state.py 儲存與記錄 state
event_memory.py 定義 Event
```

### 錯誤

```text
world_state.py 選 target
entity.py 直接套用 attack damage
action.py 改 HP
tactical_reference_policy.py 記錄 event
scenario_loader.py 執行 simulation
```

---

## 15. 快速 debug checklist

如果 import fail：

```text
確認從 repo root 執行。
確認 scripts/run_tactical_reference.py 有把 /src 加入 sys.path。
確認檔名與 import 名稱一致。
```

如果 scenario 載入失敗：

```text
確認 tactical_reference_001.json 存在。
確認 required top-level keys 存在。
確認 JSON syntax 正確。
```

如果沒有 events：

```text
確認 entities status 是 active。
確認 factions 不同。
確認 positions 合法。
確認 policy 有回傳 actions。
```

如果沒有 attack：

```text
確認 attack_range。
確認 distance_model。
確認 actors 可以移近。
確認 map 沒有被 occupied positions 卡死。
```

如果 tests fail：

```text
從 repo root 執行 python -m pytest。
除非 test 明確執行 engine，否則 output files 不應被當成測試前提。
```

---

## 16. 一句技術總結

這個 repo 會載入 tactical scenario JSON，建立 WorldState，用臨時 tactical policy 產生 Actions，把 Actions 結算成 Consequences，改變 world state，記錄 Events，計算結果，最後輸出 JSON。