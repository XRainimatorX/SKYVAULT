# SKYVAULT — How It Works

系統目前的架構參考。描述**現在的樣子**，隨程式碼改動而更新。

各階段當時的凍結紀錄在 [`phases/`](phases/)。

---

# 1. 系統在做什麼

一次執行就是把一份 scenario JSON 變成一包可回放、可追溯的紀錄。

```text
scenario JSON
  │
  ├─ scenario_loader 讀 JSON / YAML，通過 scenario 契約
  │
  ├─ engine.build_world()  呼叫 runtime.create_world() 建立 tick 0 的 WorldState
  │                        （space、clock、資源、規則都來自 world contract）
  │
  ├─ engine.run()  擷取 initial_world_state，進入 tick 迴圈
  │                每 5 個 tick 把世界快照存進 SnapshotStore
  │   │
  │   └─ 每個 tick，對每個存活單位：
  │        policy.decide_action()      產生 Action（意圖）
  │        validate_action()           壞 action 直接 raise
  │        world.record_event()        記錄 ACTION_SELECTED（通過 event 契約才寫入）
  │        resolver.execute()          actions/ 套件：
  │          handler.validate()          只讀；不通過 → rejected Consequence
  │          check_resources()           世界的收費（rule_set.action_costs）付得起嗎
  │          handler.resolve()           只讀；算出 Consequence（effect 清單）
  │          validate_consequence()      通過 consequence 契約
  │          apply_consequence()         唯一改世界的地方：每個 effect 一筆 event
  │        （若 rejected）記錄 ACTION_REJECTED
  │
  ├─ evaluator.build_evaluation_summary()   勝負與計數的摘要
  ├─ world.record_event()  記錄 SCENARIO_END（data = 上面的摘要）
  │
  ├─ evaluation.evaluate_run()   evaluation/ 套件：依 evaluation profile，
  │                              只從 initial / events / final 算出 11 軸判斷、
  │                              防刷分報告與 trade-off report
  │
  ├─ reproducibility 區塊       run_id、seed policy、runtime / ruleset 版本、input_hash；
  │                              通過契約後，output_hash 取自驗證過的 package
  │
  └─ result_package（通過 result package 契約才回傳）
       ├─ 四個 exporter 各自推導出一份輸出；runner 另外寫出評估的四個檔
       └─ runner 把這次 run 追加到 runs/registry.jsonl
```

Failure exploration（Phase 9）是許多次上面的 run：

```text
scripts/explore_failures.py
  ├─ failure.explore_failures()   基線 + 每個變量 × 每個壓力等級 + 分支 + 每個替代方案，
  │                               每個都跑 repeat_count 次（seed = 原 seed + i）
  │     └─ 每個惡化版本 = failure.apply_stress() 產生的子版本 scenario，交給同一個 engine
  └─ failure.analysis（純函式）    failure map、collapse sequence、survival conditions、建議
```

## 六個關鍵設計

**只有 Consequence 能改變世界。** Policy 產生的是 Action，那只是「想做什麼」。handler 只讀世界、算出 Consequence；`apply_consequence()` 是唯一把它套用到世界的地方，每個 effect 一筆帶 `source.action_id` 的 event。handler 不能改世界這件事有 AST 測試把關。這條線讓「決策」「結算」「生效」三者分開，policy 換掉不會影響世界規則。

**事件是快照，不是參照。** `record_event()` 存進去的 `before_state` / `after_state` 都是 `snapshot()` 的深拷貝。事件寫入後，世界再怎麼變都不會改到它。回放能成立完全靠這一點。

**任一時刻的世界都能只靠 event memory 還原。** `runtime.rebuild_world()` 從起始快照依序套用每個 event 的 `after_state`；重建到最後必須等於 `final_world_state`，CI 每次都驗。

**評估是紀錄的推導，不是模擬的一部分。** `evaluate_run()` 在 SCENARIO_END 之後執行，只讀 initial / event memory / final，與 exporter 一樣不 import 專案模組。換 evaluation profile 只會換判斷，不會換發生過的事 —— 有測試證明兩個 profile 的 event 完全相同。

**同一輸入得到同一個 output_hash。** event 與 action 的 id 是每個 run 自己的計數器，不再是 uuid；scenario + profile 相同、seed 相同、規則相同，result package 除了記錄執行時間的 reproducibility 區塊外逐位元相同。`scripts/verify_run.py` 只靠 result package 就能找回輸入、重跑並比對。

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
  ③ scenario_loader.py   tactical_reference_policy.py   evaluator.py   actions/
       讀 scenario          臨時 actor policy          結果計算     驗證 / 結算 / 套用
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
需要 ③ scenario_loader.py / tactical_reference_policy.py / evaluator.py / actions/
需要 ④ world_state.py / action.py
需要 ⑤ entity.py / event_memory.py
原因：engine 要把 scenario、world、policy、action、event、evaluation 串起來。

③ scenario_loader.py
需要 ⑥ data/scenarios/*.json
原因：它讀 scenario 原料。

③ tactical_reference_policy.py
需要 ④ world_state.py / action.py
需要 ⑤ entity.py
原因：policy 要看世界與 actor 狀態，然後產生 Action。

③ actions/
需要 ④ world_state.py / action.py / consequence.py
需要 ⑤ event_memory.py
原因：它驗證 action、算出 Consequence、經 world_state 套用並記錄 event。

③ evaluator.py
需要 ④ world_state.py
需要 ⑤ entity.py / event_memory.py
原因：它要看最後世界狀態與事件紀錄來算結果。

④ world_state.py
需要 ⑤ entity.py / event_memory.py
原因：WorldState 由 Entity 組成，並記錄 Event。

④ action.py
需要 ⑤ entity.py 的 Location 型別
原因：ActionTarget.location 是格子或節點 id。

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

## Contracts（在階層最底層）

```text
   src/skyvault/contracts/
              13 份契約：Pydantic model + validate_<x>()
              不 import 專案內任何模組
              ② ③ ④ 都可以依賴它；exporter 不依賴它
```

契約是全系統的資料法律，所以它必須在最底層：誰都可以拿它來驗證，它不認識任何人。若契約 import 了 engine 或 world_state，就會出現循環依賴，而且「格式的定義」會開始依賴「格式的使用者」。細節見 [`spec/contracts.md`](spec/contracts.md)。

## Runtime（在核心與 contracts 之間）

```text
   src/skyvault/runtime/
              space / clock / registry / resources / rules / snapshots / sourcing / world
              只依賴 contracts 與 ⑤ 的底層資料物件（entity、event_memory）
              ④ world_state.py 用它的 space、clock、registry、resources、rules
              不 import engine、policy、exporter（測試逐檔檢查）
```

世界由哪些積木組成（空間、時間、實體登記、資源、規則），與 tactical engine 怎麼用它們無關。runtime 不認識 tactics，所以同一套積木能建 grid、graph、network 任一種世界。

唯一例外是 `runtime/world.py` 的 `create_world()`：它要回傳 `WorldState`，所以 import ④。它因此**不從 `runtime/__init__.py` 匯出**，否則 world_state ↔ runtime 會循環 import。`sourcing.py` 與 `snapshots.py` 更嚴格：只 import 標準函式庫，跟 exporter 一樣。

## Actions（在 ③，與 policy 同層但互不依賴）

```text
   src/skyvault/actions/
              validation / handlers / resolver
              依賴 ④ world_state、action、consequence，⑤ event_memory 與 contracts
              不 import engine、policy、exporter（測試逐檔檢查）
```

policy 決定「想做什麼」，actions 決定「世界接不接受、接受了會怎樣」。兩者在同一層但互不認識：policy 換掉，世界規則不變；規則改了，policy 不用知道。

## Failure（在 engine 之上，與 verification 同層）

```text
   src/skyvault/failure/
              variables   scenario 轉換；只依賴 reproducibility（compare_scenarios）
              analysis    純函式，不 import 專案模組
              explore     建 engine 跑每個惡化版本 —— 在 engine 之上
```

惡化是 scenario 層的事：每個變量把 scenario 改成一個新版本，再交給完全沒改過的 engine。engine 唯一的配合是 `rule_set.faults`（通訊失效的 fault injection），沒有 faults 時它什麼都不做。

## Reproducibility 與 verification

```text
   src/skyvault/reproducibility/
              hashing / versioning / registry
              只依賴 contracts（SCHEMA_VERSION）與 skyvault.__version__；不 import engine
   src/skyvault/verification.py
              在 engine 之上（與 scripts 同層）：建 engine 重跑一個 package
```

engine 用 reproducibility 產生 hash 與版本；verification 用 engine 重跑。兩者若放在同一個模組會循環依賴，所以重跑放在 engine 之上。

## Evaluation（在階層之外，與 exporter 同級）

```text
   src/skyvault/evaluation/
              metrics / anti_gaming / tradeoff / evaluate
              只 import 標準函式庫，收 plain dict、回傳 plain dict
              engine 呼叫它；它不認識 engine
```

評估只能看見 event memory 記下的東西。若讓它 import world_state 或 engine，它就可能用到「引擎知道但沒記錄」的資訊，評估結果就不再能只靠 result package 重現。

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
Location = Position | str     grid 上是格子，graph / network 上是節點 id
Entity
```

`Entity` 是世界裡存在的東西。取代了舊的 groundunit / humanbody / groundweapon 拆分。

欄位：

```python
entity_id       str
name            str
entity_type     str
faction         str | None
position        Location | None
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

## `runtime/`

Phase 2 建立。世界的積木，每一塊都可以單獨使用。

### `space.py`

```python
class Space(Protocol):
    is_inside(position) -> bool
    distance(a, b) -> float
    neighbors(position) -> list
    describe() -> dict             寫進 snapshot 的 space，帶 type
build_space(space_model) -> Space
```

| 型別 | 位置 | distance | 由誰算 |
|---|---|---|---|
| `GridSpace` | `(x, y)` | chebyshev / manhattan / euclidean_floor | 自己算，與 Phase 4 的 SpaceModel 逐點相同 |
| `GraphSpace` | 節點 id | 最少跳數 | networkx 最短路 |
| `NetworkSpace` | 節點 id | 加權最短路 | networkx 最短路（edge 第三項為權重） |

不連通的兩點距離為 `inf`。tactical engine 的移動與攻擊射程都用同一個 `distance()`，所以換距離模型會同時改變兩者。

### `clock.py`

```python
TickClock              每次 advance +1
PhaseClock             每次 advance +phase_length；.phase = now // phase_length
EventDrivenClock       schedule(at, payload)；advance() 跳到下一個排程時間；due() 取出到期的
build_clock(time_model) -> Clock
```

`world.tick` 一律等於 `clock.now`，名稱保留 tick 是因為所有 event 與 snapshot 都用這個鍵記時間。

### `registry.py`、`resources.py`、`rules.py`

```text
EntityRegistry   Mapping[str, Entity]；add() 拒絕重複 id；require() 找不到 raise KeyError；
                 active() 只列活著的；被摧毀者保留
ResourceState    名稱 → 數量；change(id, delta) -> (before, after)；不得為負（raise，不夾住）
RuleSet          world_contract.rule_set 的唯讀存取；require() 缺參數 raise KeyError
```

`EntityRegistry.get()` 是 Mapping 原生的、找不到回傳 None；要 raise 用 `require()`（[ADR 005](decisions/005_world_runtime.md) 第 9 點）。

### `ids.py`

```python
IdSequence(prefix).next()      f"{prefix}_{n:010d}"，n 從 1 開始
RunIds().event() / .action()   一個 run 的兩個序列
```

計數器屬於 world，不屬於程序：兩個並存的 world 各自從 1 開始。十位數字維持 Phase 1 的 id 形狀（十個 hex 字元）。

### `world.py`

```python
create_world(scenario) -> WorldState     由 world contract 建出任一種世界
entity_from_record(record) -> Entity     JSON list 轉 tuple；節點 id 保持字串
```

### `sourcing.py`、`snapshots.py`

```python
rebuild_world(start_state, event_memory, at_time=None) -> dict     純函式
SnapshotStore(interval).record(time, snapshot) / latest_at_or_before(time)
```

`rebuild_world` 只套用 `start_state` 的 tick 之後的事件：

```text
after_state 有 entity_id     取代該 entity
RESOURCE_CHANGED             after_state {resource_id, amount} 設定存量
其他（SCENARIO_END）          不套用
```

從 SnapshotStore 的快照起算，與從 tick 0 起算，結果相同 —— 快照只是捷徑，event memory 才是真相。

## `world_state.py`

定義：

```text
WorldState
```

### `WorldState`

儲存目前模擬狀態。

欄位：

```python
world_id       str
scenario_id    str
tick           int               永遠等於 clock.now
space          Space             GridSpace / GraphSpace / NetworkSpace
entities       EntityRegistry
assumptions    dict
event_memory   list[Event]
resources      ResourceState
rules          RuleSet
clock          Clock
ids            RunIds            event / action id 的計數器（Phase 8）
```

方法：

```python
get_entity(entity_id)          找不到時 raise KeyError，不回傳 None
active_entities()              還活著的 entity
active_factions()              還有存活單位的陣營
is_occupied(position)          該位置有沒有活著的單位
advance_time()                 推進 clock 一次，回傳新的 tick
mutate_entity(id, changes, event_type, ...)   改 position / state 並記一筆 event（前後完整快照）
record_transition(event_type, before, after, ...)  記一筆不改世界的 event（chain reaction 用）
change_resource(id, delta)     改資源並記一筆 RESOURCE_CHANGED（affected.resources 有值）
update_entity_state(id, ...)   不屬於任何 action 的 state 變動；記 ENTITY_STATE_CHANGED
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

**`record_event()` 在寫入前先通過 event 契約。** 不合法的 event raise `ContractError`，永遠不會進 event_memory。

**已記錄的事件不可修改。** `event_memory` 只被 append。

**改變世界要經過會記錄 event 的方法。** 資源扣到負數時在記錄之前就 raise，event_memory 不會出現一筆沒發生的變動。

## `action.py`

定義：

```text
location_to_json(location)       格子轉 list，節點 id 保持字串
ActionTarget
Action（= ActionAttempt）
```

`Action` 是**意圖**，還沒生效。Formal Spec §6.2 的完整形狀（schema 0.3）。

欄位：

```python
action_id            str
actor_id             str
action_type          str            十種之一，見 actions/handlers.py
target               ActionTarget   {entity_id, location, system_id}，皆可為 None
intent               str
required_resources   dict[str, float]   actor 預期花費；rule_set 有定價時以定價為準
expected_duration    str            宣告，不強制
expected_effect      str            宣告
risk_profile         dict           宣告
priority             str            宣告
confidence           float          0–1；tactical 攻擊用 accuracy
metadata             dict
```

`to_dict()` 產生契約形狀。

規則：

```text
Action 只描述想做什麼。
Action 不改變世界。
Action 不判斷合不合法 —— 那是 actions/ 的事。
```

action id 由 `world.ids.action()` 產生（`action_0000000001` 起），policy 從 world 取，所以同一輸入的 id 每次相同。

## `consequence.py`

定義：

```text
DirectEffect     一個改變 + 記錄它的 event（group：entity / resource / state）
ChainReaction    某個 effect 引發的後續 event（與成因同一組 before / after）
SecondaryEffects risk / stability / public_order / logistical —— 只是描述
EvaluationImpact 五個數值 delta —— Phase 7 才拿來打分
Consequence
```

Consequence 是**計畫，不是紀錄**：handler 讀世界算出它，`apply_consequence()` 執行它。

```python
action_id          str
accepted           bool
reason             str                被拒絕時說明原因
effects            list[DirectEffect] 有順序：套用順序 = event 順序
secondary_effects  SecondaryEffects
chain_reactions    list[ChainReaction]
evaluation_impact  EvaluationImpact
```

`to_dict()` 依 Spec §6.3 分組成 `direct_effects{state_changes, resource_changes, entity_changes}`，組內保持順序。`Consequence.rejected(action_id, reason)` 是全空的拒絕。

規則：

```text
只有 accepted=True 的 Consequence 能被套用；套用 rejected 的會 raise。
entity effect 的 changes 只能有 position 與 state；可以是 {}（記錄但不改，例如 MISS）。
state effect（環境）目前一律 raise —— WorldState 沒有建模環境。
```

被拒絕不是錯誤 —— engine 把它記成 `ACTION_REJECTED` 事件，模擬照常繼續。

## `actions/`

Phase 3 建立。Action Attempt → Validation → Resolution → Consequence → World Mutation → Event Memory。

### `validation.py`

```python
ActionValidation(valid, reason)；.ok() / .reject(reason)
action_cost(world, action)      rule_set.action_costs[type] 有定義就用它，否則 action.required_resources
check_resources(world, cost)    任一不足 → reject "Insufficient <id>: have X, need Y"
```

### `handlers.py`

每種 action 一個 handler，`validate()` 與 `resolve()` 都**只讀**世界。

| type | 需要 | 改變 | event |
|---|---|---|---|
| move | target.location 界內、未佔、距離 ≤ move_range(1) | position、last_action | MOVE |
| attack | target.entity_id、距離 ≤ attack_range(1) | miss：無；hit：hp、last_damage_taken、可能 destroyed | MISS / ATTACK + chain ENTITY_DESTROYED |
| observe | target.entity_id、距離 ≤ observe_range(1) | 無 | OBSERVE（帶目標 state 副本） |
| scan | actor 有位置 | 無 | SCAN（data.detected） |
| wait | — | 無 | WAIT |
| repair | repair_amount > 0、目標活著有 hp 未滿、距離 ≤ repair_range(1) | hp（上限 max_hp） | REPAIR |
| supply | 收費不為空、目標活著、距離 ≤ supply_range(1) | 世界扣、目標 state 加 | RESOURCE_CHANGED… + SUPPLY |
| deploy | 同陣營 reserve 單位、地點界內未佔、距離 ≤ deploy_range(1) | position、status active | DEPLOY |
| withdraw | 同陣營、活著 | position None、status withdrawn | WITHDRAW |
| communicate | 目標活著；有 comm_range 時距離 ≤ 它 | last_message、last_message_from | COMMUNICATE |

`CORE_HANDLERS` 有十種；`MILITARY_ACTION_TYPES = ("move", "attack", "observe", "supply", "repair")`；`handlers_for(types)` 取子集。

### `resolver.py`

```python
ActionContext(rng, system_id)
ActionResolver(handlers, context).execute(world, action) -> Consequence
apply_consequence(world, consequence, action, system_id=None) -> list[Event]
```

`execute()` 的順序：未登記 → rejected；actor 不活躍 → rejected；通訊失效（`rule_set.faults.drop_actions`，用 `ActionContext.fault_rng`）→ rejected；`validate` → 資源檢查 → `resolve` → 把收費插在最前面（每個資源一個 resource effect）→ `validate_consequence` → `apply_consequence`。任何一步拒絕，世界與 event memory 都不變。

`apply_consequence()` 依序套用 effect（entity → `world.mutate_entity()`，resource → `world.change_resource()`），每個 chain reaction 緊接在它的成因之後用 `world.record_transition()` 記錄，並回填 `event_id`。

## `event_memory.py`

定義：

```text
build_causal_links(source)
build_evaluation_relevance(source)
Event
```

`Event` dataclass 的屬性是攤平的，方便 engine 傳參數：

```python
event_id, time, event_type
actor_id, system_id, target_entity_id, source_action_id
before_state, after_state
affected_entities, affected_locations, affected_resources, affected_risks
causal_links, evaluation_relevance, data, tags
```

**`to_dict()` 輸出 Spec §7.2 的巢狀形狀**，那才是 event_memory 儲存、event 契約檢查的形狀（[ADR 003](decisions/003_event_nesting.md)）：

```python
event_id              str
time                  int
event_type            str
source                {actor_id, system_id, action_id}     action_id 是 causal_chain 分組的依據
target_entity_id      str | None
affected              {entities, locations, resources, risks}   resources / risks 目前恆空
before_state          dict
after_state           dict
causal_links          {caused_by: [], caused_events: []}
evaluation_relevance  {affects_success, affects_cost, affects_risk}
data                  dict            型別專屬資料
tags                  list
```

方法：

```python
to_dict()    輸出巢狀、JSON-safe 的 dict；每個可變容器都複製一份
```

八種 `event_type`：

```text
ACTION_SELECTED   ACTION_REJECTED   MOVE      ATTACK
MISS              ENTITY_DESTROYED  NO_ACTION SCENARIO_END
```

規則：

```text
每個 event 都要有完整的 12 個頂層鍵與巢狀結構。
空資料保留 empty list / empty dict，不要省略欄位。
新事件型別要先登記到 contracts/event.py 的 EVENT_TYPES，否則 record_event() 會拒絕。
不要把所有東西塞進 data。
event 寫入後不可修改。
```

屬性攤平、輸出巢狀的理由見 [`decisions/003_event_nesting.md`](decisions/003_event_nesting.md)；Phase 4 的攤平決定見 [`decisions/002_event_shape.md`](decisions/002_event_shape.md)。

event id 由 `WorldState.record_event()` 呼叫 `self.ids.event()` 產生（`event_0000000001` 起），每個 world 各自計數。

## `scenario_loader.py`

定義：

```text
load_scenario(path)
load_evaluation_profile(path)
default_evaluation_profile(scenario)    balanced.json，perspective 依 scenario 決定
scenario_perspective(scenario)          evaluation.perspective，否則第一個有陣營的 entity
```

讀 scenario 與 evaluation profile 檔（`.json`、`.yaml`、`.yml`，依副檔名決定），各自通過契約後回傳 dict。

規則：

```text
只負責讀取與契約驗證。
缺 scenario_id、帶未知的鍵、schema_version 不是 0.6、entity 不在空間內、version_control.version 與 scenario_version 不符 → raise ContractError。
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
__init__(scenario, evaluation_profile=None)  None → balanced；profile 在 run 之前就通過契約
build_world(scenario)                    呼叫 create_world；只接受 grid + tick，其他 raise ValueError
run()                                    跑完整場，回傳 result_package
evaluate(termination_reason, event_count)  產生 evaluation summary
self.resolver                            ActionResolver(軍事線五種, ActionContext(self.rng, actor_policy))
```

規則：

```text
engine 負責流程：時間、輪到誰、何時結束。
engine 不驗證、不結算 action —— 交給 self.resolver。
engine 不做輸出格式化。
engine 不含 replay / timeline / causal chain 邏輯。
engine 不直接改 entity。
```

Phase 3 前的 `resolve_move` / `resolve_attack` 已移除；它們一邊驗證、一邊改 entity、一邊記 event，最後才回傳 Consequence。

**tactical engine 刻意維持 grid + tick 專用。** 它的 policy 在格子間一步一步走，給它 graph 或 phase clock 會在 `build_world()` 直接 raise，而不是跑出沒意義的結果。runtime 本身支援全部三種空間與時間。

`self.snapshots` 是 `SnapshotStore(SNAPSHOT_INTERVAL=5)`，記 tick 0 與每個 tick 結束時（只保留落在間隔上的），所以這個 scenario 會存下 tick 0、5、10。

**engine 在兩個地方驗證：** policy 交出的 action 在被記錄與結算之前通過 action 契約；`run()` 回傳之前整包通過 result package 契約。壞 action 是 policy 的程式錯誤，raise `ContractError`，不會被記成 `ACTION_REJECTED`（[ADR 004](decisions/004_contract_scope.md) 第 7 點）。

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
它只產生 SCENARIO_END 的摘要；多軸判斷在 evaluation/。
```

## `reproducibility/`

Phase 8 建立。Formal Spec §11（版本控制）與 §12（Reproducibility）。

```python
canonical_json(value)                  sort_keys、緊湊、ensure_ascii False
content_hash(value)                    canonical JSON 的 SHA-256
input_hash(scenario, profile)          scenario 與 profile 一起
output_hash(package)                   去掉 reproducibility 的 content_hash
RUNTIME_VERSION                        = skyvault.__version__（每個 Phase 調升 minor）
ruleset_version(scenario, action_types)  "rules-" + hash(rule_set, action types, SCHEMA_VERSION)[:12]
seed_policy(runtime)                   (policy, seed, replayable)
compare_scenarios(old, new)            Spec §11 五類差異，每項 "<path>: <old> -> <new>"
compare_runs(a, b)                     same_input / same_output / same_rules + 結果、事件數、判斷、分數的前後值
RunRegistry(path)                      JSON Lines；record / all / get / by_input
```

scenario 的版本放在 `data/scenarios/<scenario_id>/<version>.json`，檔內 `version_control` 記錄 parent 與變更；`compare_scenarios(parent, child)` 的結果應與 child 的 `changed_from_previous` 相同（測試檢查 v0.1 → v0.2）。

## `failure/`

Phase 9 建立。Formal Spec §14。

### `variables.py`

```python
STRESS_LEVELS = ("mild", "moderate", "severe", "collapse")
FailureVariable(name, description, assumption, magnitudes, applies, apply)
FAILURE_VARIABLES      八個
apply_stress(scenario, {variable: level}, perspective) -> 子版本 scenario
```

| 變量 | 作用（mild / moderate / severe / collapse） | 攻擊的假設 |
|---|---|---|
| supply_delay | 世界資源 × 0.9 / 0.75 / 0.5 / 0.25 | resource_model |
| sensor_failure | 己方 accuracy × 0.9 / 0.75 / 0.6 / 0.4 | combat_resolution |
| communication_failure | 己方 action 失效率 0.1 / 0.25 / 0.5 / 0.8 | actor_policy |
| weather_degradation | 全體 accuracy × 0.9 / 0.75 / 0.6 / 0.4 | combat_resolution |
| enemy_reaction_speed | 敵方 accuracy + 0.05 / 0.1 / 0.2 / 0.35（上限 1） | combat_resolution |
| equipment_overheat | 己方 attack_damage × 0.9 / 0.75 / 0.5 / 0.25（取整） | combat_resolution |
| civilian_pressure | 己方起始 hp × 0.9 / 0.75 / 0.6 / 0.4（取整，至少 1） | force_availability |
| resource_shortage | 世界資源 × 0.75 / 0.5 / 0.25 / 0 | resource_model |

沒有對應目標的變量（沒有資源的世界裡的資源變量）`applies()` 回傳 `(False, 原因)`，exploration 只報告不跑。惡化後的 scenario_version 是 `<原版>+<變量>:<等級>`，version_control 指回原版，changed_from_previous 由 `compare_scenarios` 算出。

### `explore.py`

```python
explore_failures(scenario, profile, config=None, scenarios_dir=None) -> dict
```

config 預設是 scenario 的 `failure_exploration`。回傳每個 run 的摘要（seed、verdict、分數、己方損失序列、output_hash）：基線、每個適用變量 × 每個等級、分支（兩個最敏感的變量在 moderate 一起施加）、每個替代方案的同樣掃描。

### `analysis.py`

```python
build_failure_map(exploration)            → failure map（第 13 份契約）
build_collapse_sequence(exploration)      → 壓垮變量在崩潰等級的第一個失敗 run 的損失序列
build_survival_conditions(failure_map)    → 每個變量撐到哪一級
render_recommended_modifications(map, conditions) → Markdown
```

```text
存活           verdict 不是 fail
存活率         非 fail 的比例
breaking_level 第一個存活率 < survival_threshold 的等級
sensitivity    基線存活率 − 最差等級的存活率（可為負：壓力反而有利）
crushing       sensitivity 最大者；同分取較早崩潰者，再同分取名稱
替代方案       依各變量的崩潰等級與基線存活率比較：holds_longer / breaks_sooner / mixed / same
```

## `verification.py`

```python
locate_inputs(package)                              → (scenario, profile)，只靠 package 找
verify_reproducibility(package, scenario, profile)  → {reproduced, replay_available, input_hash_matches,
                                                       expected / recorded / actual_output_hash}
```

`expected_output_hash` 從 package 本身重算，所以 package 被改過、即使 reproducibility 區塊沒動，也不會被判為重現成功。stochastic 的 run 不重跑。

## `evaluation/`

Phase 7 建立。Formal Spec §8（多軸評估）與 §16（Metric Anti-Gaming）。

### `metrics.py`

```python
EvaluationContext.build(initial_world_state, event_memory, final_world_state, perspective, max_ticks)
MetricValue(raw, score, applicable, explanation)
Metric(name, description, unit, compute)
METRIC_REGISTRY      11 軸
```

每個 score ∈ [0, 1]，越高越好；成本類反轉。沒有資料可判斷時 `applicable = False`，不計入加權並降低 confidence。F = perspective 陣營，E = 其他有陣營的 entity：

| 軸 | 定義 |
|---|---|
| mission_success | F 全滅 → 0；E 全滅 → 1；否則 E 被摧毀的比例 |
| tactical_value | F 造成的傷害 / E 初始 hp（上限 1） |
| strategic_value | F 存活 / F 總數 |
| resource_cost | 1 − F 損失 hp / F 初始 hp |
| time_cost | 1 − 結束 tick / max_ticks |
| risk_growth | 1 − 以 F 為目標的 affects_risk 事件 / F 總數（代理指標） |
| failure_resistance | F 第一次損失的 tick / 結束 tick；沒有損失 → 1 |
| recovery_ability | REPAIR 恢復的 hp / 曾損失的 hp；沒有損失 → 不適用 |
| system_robustness | 1 − F 被拒的 action / F 選擇的 action |
| logistics_burden | 1 − F 花掉的世界資源 / 初始世界資源；沒有資源 → 不適用 |
| stability_impact | 1 − 全場被摧毀 / 全場 entity（代理指標） |

### `anti_gaming.py`

```python
detect_gaming(context, scores, profile) -> dict
```

| 檢查 | 觸發條件 | 行為 |
|---|---|---|
| inaction_penalty | F 的回合中 NO_ACTION 或 wait 的比例 > 門檻 | maximize_score_by_inaction |
| stability_penalty | mission_success ≥ 0.8 且 stability_impact < 門檻 | sacrifice_long_term_stability_for_short_term_success |
| risk_spike_penalty | 單一 tick 內以 F 為目標的風險事件 / F 總數 > 門檻 | extreme_high_risk_optimization |
| hidden_risk_penalty | mission_success ≥ 0.8 且 F 存活者中 hp ≤ 25% 的比例 > 門檻 | ignore_hidden_risk_to_improve_visible_score |
| long_term_cost_penalty | tactical_value ≥ 0.8 且 strategic_value < 門檻 | sacrifice_strategic_value_for_short_term_tactical_value |

觸發一定被報告；只有行為列在 profile 的 `forbidden_optimization_behaviors` 時才扣分並算作刷分。

### `evaluate.py`、`tradeoff.py`

```python
evaluate_run(initial, events, final, summary, profile, max_ticks, failure_thresholds=None)
    -> {evaluation_result, score_breakdown, anti_gaming_report, tradeoff_report}
build_tradeoff_report(score_breakdown, anti_gaming_report, judgement, profile) -> dict
render_tradeoff_report(report) -> str       Markdown
```

overall_score = 適用且有權重的軸的加權平均 − 防刷分扣分。判斷依序：

```text
fail             overall < fail 門檻，或 mission_success = 0，或 scenario failure_threshold 觸發
risky            偵測到禁止的刷分行為，或 risk_growth < 0.5
pass             overall ≥ pass 門檻
needs_more_test  其餘
```

`evaluate_run` 是純函式：不改輸入，同輸入同輸出。

## `contracts/`

定義：

```text
13 份契約（開發計劃的 11 份 + evaluation_profile + failure_map），各一個 Pydantic model + validate_<x>()
ContractError
SCHEMA_VERSION = "0.6"
build_json_schemas()
```

規則：

```text
驗證函式是純函式，回傳正規化後的 dict，不改變資料形狀。
ContractError 一次列出全部錯誤，格式 "<欄位路徑>: <訊息>"。
所有 model 設 extra="forbid"：未知的鍵直接被拒。
不 import 專案內任何模組。
```

完整欄位與每個 optional 欄位留待哪個 Phase，見 [`spec/contracts.md`](spec/contracts.md)。

**改了契約要重跑 `scripts/export_schemas.py`** —— 連只改 docstring 也要，因為 Pydantic 把它寫進 JSON Schema 的 `description`。

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
載入 scenario（--scenario，預設 tactical_reference_001/v0.1.json）與 profile（--profile）
跑 engine
從 result_package 取出欄位
呼叫四個 exporter 與 render_tradeoff_report
寫出十一個檔案
把 run 追加到 run registry（--registry，預設 runs/registry.jsonl，已 gitignore）
印出摘要、判斷、run_id 與 output_hash 前 12 碼
```

`scripts/verify_run.py <result_package.json>`：從 package 找回 scenario 與 profile，重跑，比對 output_hash；重現成功 exit 0，否則 exit 1。

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
   4.3 resolver.execute()：驗證 → 結算 → 套用（套用時記錄結果事件）
   4.4 若 rejected，記錄 ACTION_REJECTED
5. 若只剩一個 faction，停止
6. 計算 evaluation
7. 記錄 SCENARIO_END
8. 回傳 result package
```

`initial_world_state` 在**步驟 1 之前**擷取，所以 result package 同時帶著起點與終點。

## Action resolution

每種 action 的驗證與後果見第 3 節 `actions/handlers.py` 的表格。tactical engine 只登記軍事線五種，tactical policy 只產生 move 與 attack。

attack 的命中判定從 `ActionContext.rng` 抽 —— 那就是 engine 的 `self.rng`，所以同一個 seed 得到同樣的命中與失誤。致命一擊記成兩筆 event：ATTACK（hp 歸零、status destroyed），以及它的 chain reaction ENTITY_DESTROYED，兩者的 before / after 相同。

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

執行一次產生十一個檔案；`scripts/explore_failures.py` 另外寫四個。

## Truth source

### `event_memory.json`

**唯一真相來源。** 一個 event 的完整陣列，每個都是 12 個頂層鍵的巢狀形狀。

所有其他輸出都由它推導。任何模組都不得修改它。

### `result_package.json`

一次執行的完整包裝：

```python
scenario_id          str
scenario_version     str
initial_world_state  dict     tick 0 的世界（含 space.type 與 resources）
final_world_state    dict     結束時的世界
event_memory         list     所有事件
evaluation_result    dict     摘要 + Spec §8.3 的多軸判斷（Phase 1 前叫 evaluation）
score_breakdown      dict     11 軸的 score、raw、unit、weight、applicable、explanation
anti_gaming_report   dict     Spec §16 欄位 + 每項檢查的結果
tradeoff_report      dict     四組對立軸、最強 / 最弱軸、防刷分摘要
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

四個都是純推導 —— 刪掉重跑會得到相同內容。

## Failure output（`scripts/explore_failures.py`）

| 檔案 | 回答什麼 |
|---|---|
| `failure_map.json` | 在哪裡失敗、為什麼、多快、哪個變量壓垮、哪個假設、哪個替代方案撐更久（第 13 份契約） |
| `collapse_sequence.json` | 壓垮變量在崩潰等級的一個失敗 run：己方單位依序在哪個 tick 被誰摧毀 |
| `survival_conditions.json` | 每個變量撐到哪一級、在哪一級崩潰；不適用的變量與原因 |
| `recommended_modifications.md` | 現實行動前必須改什麼 |

## Evaluation output

| 檔案 | 回答什麼 | 內容來源 |
|---|---|---|
| `evaluation_result.json` | 這個方案值不值得、危不危險 | `result_package["evaluation_result"]` |
| `score_breakdown.json` | 每一軸為什麼是這個分數 | `result_package["score_breakdown"]` |
| `anti_gaming_report.json` | 高分是不是刷出來的 | `result_package["anti_gaming_report"]` |
| `tradeoff_report.md` | 得到什麼、付出什麼 | `render_tradeoff_report(result_package["tradeoff_report"])` |

`python3 scripts/run_tactical_reference.py --profile <path>` 用別的 profile 評同一個 scenario；不給就用 `data/evaluation_profiles/balanced.json`。

---

# 7. 決定論

scenario 宣告 `random_seed`，engine 建立**唯一**的 `random.Random(seed)` 並交給 policy 共用。

隨機只用在三個地方：

```text
AttackHandler.resolve()          命中判定（ActionContext.rng 就是 engine.rng）
policy.choose_target()           多個目標同分時挑一個
policy.next_step_toward()        多個移動格同分時挑一個
```

同一個 seed 每次跑出完全相同的行為 —— 同樣的事件數、同樣的型別順序、同樣的勝負。

Phase 8 起 `event_id` 與 `action_id` 是每個 run 的計數器（`runtime/ids.py`），所以連 id 也相同：兩次 run 的 result package 除了 reproducibility 區塊外逐位元相同，output_hash 相同。

`runtime.random_seed_policy` 為 `stochastic` 時，engine 刻意用不帶 seed 的 `Random()`，reproducibility 記錄 `random_seed: null`、`deterministic_replay_available: false`。

實測：seed 42 → `RED_survived`；seed 7 → `BLUE_survived`。雙方單位完全對稱，勝負純由擲骰決定。

---

# 8. 不變量

改動程式碼時，這些必須一直成立。破壞其中任何一條都不會立刻報錯，但會在整合或回放時爆出來。

```text
1. event_memory 只被 append，永不修改已寫入的事件
2. before_state / after_state 是深拷貝
3. 每個 event 是 12 個頂層鍵的巢狀形狀，空值保留為 [] 或 {}
4. 只有 accepted 的 Consequence 能改變世界
5. 被摧毀的 entity 保留在 world.entities，只改 status
6. 整場模擬只有一個 random.Random 實例
7. exporter 不 import 專案內任何模組
8. exporter 不寫檔
9. evaluation_result.event_count == len(event_memory)（result package 契約強制）
10. result_package 的欄位足以產生全部四個 derived output
11. contracts 不 import 專案內任何模組；exporter 不 import contracts
12. 驗證函式不改變資料形狀：驗證前後的 dict 相等
13. rebuild_world(initial_world_state, event_memory) == final_world_state
14. 資源存量永不為負；變動一律記成 RESOURCE_CHANGED
15. runtime 不 import engine、policy、exporter
16. handler 只讀世界；action 的改變只經過 apply_consequence()
17. action 造成的每筆 event 的 source.action_id 都是該 action；NO_ACTION 與 SCENARIO_END 為 null
18. reference run 與 tests/fixtures/reference_trace.json 一致（除非 Phase 刻意改變模擬，並重新產生）
19. evaluation/ 不 import 專案模組；evaluate_run 不改輸入、同輸入同輸出
20. 換 evaluation profile 不改變 event memory 與 final_world_state
21. 同一 scenario + profile + seed + 規則 → 同一個 output_hash
22. output_hash = 驗證過的 result package 去掉 reproducibility 後的 canonical JSON 的 SHA-256
23. hashing / versioning / registry 不 import engine
24. 沒有 rule_set.faults 時，fault_rng 一次都不會被抽；有 faults 時也不擾動主 rng
25. failure/analysis 不 import 專案模組；variables 不 import engine
```

---

# 9. Debug checklist

| 症狀 | 先看哪裡 |
|---|---|
| 事件數不對 | `len(event_memory)` vs `evaluation_result.event_count` |
| `ContractError` | `error.contract` 指出哪份契約，`error.errors` 列出每個欄位路徑 |
| JSON Schema 測試失敗 | 契約改過（連 docstring 也算）但沒重跑 `scripts/export_schemas.py` |
| 某個 tick 狀態不對 | `replay_state_at_tick.json` 的該 tick；或 `rebuild_world(..., at_time=N)` |
| 重建結果 ≠ final_world_state | 有人改了世界卻沒記 event，或 event 的 after_state 不是完整快照 |
| tactical engine 拒絕 scenario | 它只跑 grid + tick；其他空間與時間要用 `create_world()` 直接建 |
| action 被拒但不知道為什麼 | `ACTION_REJECTED` 的 `data.reason`；或直接 `resolver.execute()` 看回傳的 `reason` |
| `reference_trace` 測試失敗 | 模擬行為變了。刻意的就重新產生並在完成報告記錄新舊數字；不是刻意的就是 bug |
| 改了 handler 後 AST 測試失敗 | handler 改了世界或記了 event。把改變寫成 DirectEffect 交給 apply_consequence |
| 某個 entity 行為奇怪 | `entity_history.json` 的該 entity |
| 不知道某個結果從哪來 | `causal_chain.json` 找 `source_action_id` |
| 想快速看懂整場 | `timeline.txt` |
| 想知道為什麼被判 risky / fail | `evaluation_result.json` 的 `failure_causes`，再看 `anti_gaming_report.json` 的 `checks` |
| 某一軸分數看不懂 | `score_breakdown.json` 的 `raw`、`explanation`；`applicable: false` 表示沒有資料 |
| 換 profile 後 event 也變了 | 不該發生 —— 評估不能改模擬；檢查有沒有人在 evaluation/ 裡 import 了專案模組 |
| verify_run 說沒有重現 | 看 `input_hash_matches`：false 是輸入變了（scenario 或 profile 被改）；true 但 hash 不同是程式行為變了，或 package 被改過 |
| failure map 說某變量「壓力反而有利」 | sensitivity 為負是真的結果：例如壞天氣讓雙方都打不中，守方反而活下來 |
| exploration 太慢 | 每次 run 約 20 ms；runs = repeat × [(1 + 變量 × 等級 + 分支) + 替代方案數 × (1 + 變量 × 等級)]，reference 是 760。用 `--repeats` 調小 |
| 兩次 run 的 output_hash 不同 | 有隨機來源沒走 engine.rng，或有東西用了時間 / uuid；`tests/reproducibility/test_determinism.py` 會抓 |
| 結果每次不同 | 檢查 `random_seed`；檢查有沒有人另外建了 `Random()` |
| 輸出檔內容是錯的 | 確認 runner 有呼叫 exporter，而不是寫入別的東西 |
| 回放的歷史狀態都是最終狀態 | 檢查 `snapshot()` 是否被改成淺拷貝 |
| 攻擊打不到 | 檢查 `distance_model`，移動與射程共用同一個 |
| import 時產生檔案 | 某個模組在 module 層級做 I/O |

Phase 4 記錄的 `timeline.txt` 致命一擊傷害數字缺陷已在 Phase 1 修正，見 [`phases/phase1_contract_pack.md`](phases/phase1_contract_pack.md)。

---

# 10. 環境與工具

```text
Python 3.10+     程式碼用到 X | None 聯集語法（PEP 604）
開發環境          3.11
執行時期相依       pydantic>=2、PyYAML（ADR 004）、networkx>=3（ADR 005），宣告在 pyproject.toml
```

```bash
python3 scripts/run_tactical_reference.py       # 跑一次
python3 -m pytest tests/ -q                     # 測試
python3 -m pytest tests/ -q --cov               # 覆蓋率
ruff check .                                    # linter
black --check src/ tests/ scripts/              # 排版
python3 -m mypy src/                            # 型別（要用能 import pydantic 的直譯器）
python3 scripts/export_schemas.py               # 改契約後重新產生 JSON Schema
python3 scripts/verify_run.py output/result_package.json   # 重跑並比對 output_hash
python3 scripts/explore_failures.py [--repeats N]         # 故意惡化，寫出四個 failure 輸出
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
| [`decisions/002_event_shape.md`](decisions/002_event_shape.md) | Phase 4 為什麼 event 是攤平的 |
| [`decisions/003_event_nesting.md`](decisions/003_event_nesting.md) | Phase 1 為什麼收回巢狀 |
| [`decisions/004_contract_scope.md`](decisions/004_contract_scope.md) | 契約 v0.1 的範圍與取捨 |
| [`spec/contracts.md`](spec/contracts.md) | 12 份契約的現行規格 |
| [`plan/`](plan/) | 每個 Phase 的原文規格與開發順序 |
| [`phases/phase1_contract_pack.md`](phases/phase1_contract_pack.md) | Phase 1 完成報告 |
| [`decisions/005_world_runtime.md`](decisions/005_world_runtime.md) | schema 0.2 與 runtime 的設計決定 |
| [`phases/phase2_world_runtime_core.md`](phases/phase2_world_runtime_core.md) | Phase 2 完成報告 |
| [`decisions/006_action_consequence.md`](decisions/006_action_consequence.md) | schema 0.3 與 action framework 的設計決定 |
| [`phases/phase3_action_consequence_engine.md`](phases/phase3_action_consequence_engine.md) | Phase 3 完成報告 |
| [`decisions/007_evaluation_engine.md`](decisions/007_evaluation_engine.md) | schema 0.4 與 evaluation engine 的設計決定 |
| [`decisions/008_reproducibility.md`](decisions/008_reproducibility.md) | schema 0.5、決定性 id、hash 與版本的設計決定 |
| [`decisions/009_failure_exploration.md`](decisions/009_failure_exploration.md) | schema 0.6 與 failure exploration 的設計決定 |
| [`phases/phase9_failure_exploration.md`](phases/phase9_failure_exploration.md) | Phase 9 完成報告 |
| [`phases/phase8_reproducibility.md`](phases/phase8_reproducibility.md) | Phase 8 完成報告 |
| [`phases/phase7_evaluation_engine.md`](phases/phase7_evaluation_engine.md) | Phase 7 完成報告 |
| [`postmortems/phase1.md`](postmortems/phase1.md)、[`phase2.md`](postmortems/phase2.md)、[`phase3.md`](postmortems/phase3.md)、[`phase7.md`](postmortems/phase7.md)、[`phase8.md`](postmortems/phase8.md)、[`phase9.md`](postmortems/phase9.md) | 各 Phase 回顧 |
