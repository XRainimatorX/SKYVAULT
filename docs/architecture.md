# SKYVAULT — How It Works

系統目前的架構。這份文件描述**現在的樣子**，不是歷史 —— 各階段當時的狀態記在 `docs/phases/`。

適用版本：Phase 4 完成後（Event Memory + Replay System v0.4）。

---

## 1. 一次執行的形狀

```text
scenario JSON
  → World State
    → Actor Policy        決定「想做什麼」
      → Action            意圖，尚未生效
        → Validation      世界同不同意
          → Consequence   同意後產生什麼結果
            → World State Mutation
              → Event Memory      記錄發生過的事
                → Evaluation      這場怎麼結束
                  → Result Package
                    → 四個 derived output
```

每一格只做一件事，而且**只有 Consequence 能改變世界**。Policy 只能提議，Engine 只能結算，Event Memory 只能記錄。

---

## 2. 依賴階層

### 核心（有上下關係，禁止向上 import）

```text
             ① scripts/run_tactical_reference.py
                    啟動入口
──────────────────────────────────────────────
             ② engine.py
                    流程總管
──────────────────────────────────────────────
  ③ scenario_loader.py  tactical_reference_policy.py  evaluator.py
       讀 scenario           actor policy              結果計算
──────────────────────────────────────────────
     ④ world_state.py    action.py    consequence.py
         世界狀態         行動嘗試      行動後果
──────────────────────────────────────────────
       ⑤ entity.py       event_memory.py
          世界物件           事件記憶
──────────────────────────────────────────────
        ⑥ data/scenarios/*.json
```

允許的方向：

```text
① → ②
② → ③ ④ ⑤
③ → ④ ⑤ ⑥
④ → ⑤
⑤ → 不依賴上層
⑥ → 不依賴 code
```

### Exporter（在階層之外）

```text
        timeline.py   replay.py   entity_history.py   causal_chain.py
                    只 import 標準函式庫
                    不依賴專案內任何模組
```

這四個模組**不 import 專案裡的任何東西**。它們收 plain dict、回傳 plain dict 或字串，只有 runner 會呼叫它們。

這不是巧合，是刻意的：exporter 只能是 `event_memory` 的下游，讓它們依賴 engine 或 world_state 就會產生「輸出反過來影響模擬」的可能。目前這個可能性在型別上就不存在。

### 禁止的寫法

```python
# 不要在 entity.py / world_state.py / action.py 裡這樣做
from skyvault.engine import SkyVaultTacticalReferenceEngine

# 不要在 world_state.py 裡這樣做
from skyvault.tactical_reference_policy import TacticalReferencePolicy

# 不要在任何 exporter 裡這樣做
from skyvault.world_state import WorldState
```

一句話：

```text
engine.py 可以知道 policy。
world_state.py 不可以知道 policy。
exporter 誰都不知道，只認得資料。
```

---

## 3. 各模組責任

### ⑤ 底層資料物件

**`entity.py`** — 世界裡存在的東西。

```python
Entity(entity_id, name, entity_type, faction, position, state, capabilities, tags)
```

`state` 放會變的（hp / ap / status），`capabilities` 放能力值（attack_damage / attack_range / accuracy）。`position` 可以是 `None`。

`snapshot()` 回傳深拷貝 —— 這是事件不會被後續變動污染的前提。

**`event_memory.py`** — 事件的資料形狀與 id 產生器。每個 event 有 17 個 top-level 欄位，形狀凍結（見 `docs/decisions/002_event_shape.md`）。

### ④ 世界與行動

**`world_state.py`** — 世界狀態，由 `SpaceModel`（格子與距離模型）與 `entities` 組成，並持有 `event_memory`。

主要方法：`get_entity` / `active_entities` / `active_factions` / `is_occupied` / `snapshot` / `record_event`。

**`action.py`** — Action 是**意圖**，還沒生效。含 `action_id` / `action_type` / `actor_id` / `target_entity_id` / `target_position`。

**`consequence.py`** — Action 結算後的結果資料。`accepted=False` 時帶 `reason`。**只有 accepted 的 Consequence 能改變世界。**

### ③ 中層

**`scenario_loader.py`** — 讀 scenario JSON，回傳 engine 要的 dict。

**`tactical_reference_policy.py`** — 暫時性的 actor policy。看世界與 actor 狀態，回傳一個 Action 或 `None`。

不改世界，不記錄事件。所有隨機（目標同分時的挑選、移動格同分時的挑選）都用 engine 傳進來的 seeded rng。

**`evaluator.py`** — 從最終世界狀態與事件記錄算出 evaluation summary。

### ② 流程總管

**`engine.py`** — 把上面全部串起來。持有唯一的 `random.Random(seed)`，並把它交給 policy，所以整場模擬只有一個隨機來源。

負責 move 與 attack 的 validation 與結算。

### ① 入口

**`scripts/run_tactical_reference.py`** — 載入 scenario、跑 engine、呼叫四個 exporter、寫出七個檔案。

只做 `import exporter → call exporter → write file`，不含任何模擬或格式化邏輯。

### Exporter

| 模組 | 函式 | 回傳 | 產生 |
|---|---|---|---|
| `timeline.py` | `render_timeline()` | `str` | `timeline.txt` |
| `replay.py` | `build_replay_state_at_tick()` | `dict` | `replay_state_at_tick.json` |
| `entity_history.py` | `build_entity_history()` | `dict` | `entity_history.json` |
| `causal_chain.py` | `build_causal_chain()` | `dict` | `causal_chain.json` |

命名慣例：`build_*` 回傳結構，`render_*` 回傳文字。**四個都不寫檔** —— 寫檔是 runner 的事。

---

## 4. Engine 行為

### 每個 tick

```text
1. 設定 world.tick
2. 檢查 active factions
3. 取得 active entities
4. 對每個 active actor：
   4.1 policy 決定 action
   4.2 記錄 ACTION_SELECTED
   4.3 結算 action
   4.4 若 accepted，改變 world state
   4.5 記錄結果事件
5. 只剩一個 faction 就停止
6. 計算 evaluation
7. 記錄 SCENARIO_END
8. 回傳 result package
```

`initial_world_state` 在**進入迴圈之前**擷取，所以 result package 同時帶著起點與終點。

### Move

必須有 `target_position`。驗證：存在、在世界內、未被佔用。

```text
通過  →  actor.position 改變、last_action = "move"、記錄 MOVE
失敗  →  Consequence accepted=False、記錄 ACTION_REJECTED
```

### Attack

必須有 `target_entity_id`。驗證：target 存在、雙方都有 position、target 在 `attack_range` 內。

```text
用 accuracy 做命中判定（seeded rng）
miss  →  記錄 MISS
hit   →  target hp 扣 attack_damage、記錄 ATTACK
hp <= 0  →  status 改為 destroyed、記錄 ENTITY_DESTROYED
```

---

## 5. 輸出

執行一次產生七個檔案。

### Truth source

**`event_memory.json`** — 唯一真相來源。所有其他輸出都由它推導，任何 exporter 都不得修改它。

**`result_package.json`** — 一次執行的完整包裝：

```text
scenario_id  scenario_version  initial_world_state
final_world_state  event_memory  evaluation
```

**`final_state.json`** — 終局世界狀態（也在 result_package 裡，另外寫一份方便直接看）。

### Derived output

| 檔案 | 回答什麼問題 |
|---|---|
| `timeline.txt` | 這場照時間順序發生了什麼？ |
| `replay_state_at_tick.json` | 第 N 個 tick 結束時世界長什麼樣？ |
| `entity_history.json` | 某個 entity 一生經歷了什麼？ |
| `causal_chain.json` | 哪個 action 造成哪些 event？ |

四個都是純推導 —— 刪掉重跑會得到相同內容（除了 uuid）。

---

## 6. 分離規則

```text
policy      決定 actor 想做什麼          不改世界、不記錄
engine      結算 action、驅動 tick        不做格式化
world_state 儲存世界狀態                  不知道 policy 存在
event_memory 記錄發生過的事               只被寫入，不被修改
exporter    把事件轉成別的形狀            不依賴任何專案模組
runner      啟動與寫檔                    不含業務邏輯
```

違反其中任何一條，通常會在整合階段才爆出來 —— Phase 4 就是這樣。詳見 `docs/phases/phase4_event_memory.md` 第 5 節。

---

## 7. 決定論

scenario 宣告 `random_seed`，engine 建立唯一的 `random.Random(seed)` 並交給 policy 共用。

隨機只用在三個地方：

```text
engine.py     命中判定
policy.py     多個目標同分時挑一個
policy.py     多個移動格同分時挑一個
```

同一個 seed 每次跑出完全相同的行為。**但 `event_id` 與 `action_id` 用 `uuid4()`，不受 seed 控制** —— 所以輸出檔無法跨 run 逐位元比對。這是已知限制，留待 Phase 8。

---

## 8. Debug checklist

| 症狀 | 先看哪裡 |
|---|---|
| 事件數不對 | `event_memory.json` 的長度 vs `evaluation.event_count` |
| 某個 tick 狀態不對 | `replay_state_at_tick.json` 的該 tick |
| 某個 entity 行為奇怪 | `entity_history.json` 的該 entity |
| 不知道某個結果從哪來 | `causal_chain.json` 找 `source_action_id` |
| 想快速看懂整場 | `timeline.txt` |
| 結果每次不同 | 檢查 `random_seed` 是否被改動 |
| 輸出檔內容是錯的 | 確認 runner 有呼叫 exporter，而不是寫入別的東西 |

`timeline.txt` 目前有一個已知缺陷：致命一擊會顯示錯誤的傷害數字。詳見 `docs/phases/phase4_event_memory.md` 第 6 節。

---

## 9. 環境

```text
Python 3.10+     （程式碼用到 X | None 聯集語法）
開發環境          3.11
無執行時期相依套件  只用標準函式庫
```

開發工具（`pyproject.toml` 有完整設定）：

```bash
python3 -m pytest tests/ -q                     # 測試
python3 -m pytest tests/ -q --cov               # 覆蓋率
ruff check .                                    # linter
black --check src/ tests/ scripts/              # 排版
mypy src/                                       # 型別
python3 -m bandit -c pyproject.toml -r src/     # 安全掃描
```
