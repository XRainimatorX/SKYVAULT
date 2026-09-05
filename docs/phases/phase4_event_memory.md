# Phase 4 — Event Memory + Replay System 

完成報告。這份文件是 Phase 4 結束時的凍結紀錄，寫完不再更新 —— 系統目前的樣子請看 [`../architecture.md`](../architecture.md)。

**狀態：功能完成，含一個已記錄未修的缺陷。**

---

## 1. 這個階段做什麼

Phase 4 開始前，系統能跑完一場模擬，但過程只存在 raw JSON 裡。目標是讓它可閱讀、可回放、可審計、可追蹤。

三個 section 平行開發，以 [issue #9](https://github.com/XRainimatorX/SKYVAULT/issues/9) 的 frozen event shape 作為接口契約：

```text
Section A (#5)  Event Memory 欄位補齊
Section B (#7)  Replay + Causal Chain + Runner
Section C (#8)  Timeline + Entity History
共同 (#9)       Frozen Event Shape + 共同規則
```

---

## 2. 這場 scenario 發生了什麼

### 設定

```text
scenario_id     tactical_reference_001
地圖            10 × 10 grid，chebyshev 距離（斜走與直走同價）
max_ticks       10
random_seed     42
```

六個單位，兩方對角開局：

```text
entity      name              faction  pos     hp  dmg  range  accuracy
red_001     Red Rifleman      RED     (0,0)    35   10    1     0.80
red_002     Red Support       RED     (1,0)    32   16    2     0.55
red_003     Red Commander     RED     (2,0)    30    7    1     0.70
blue_001    Blue Rifleman     BLUE    (9,9)    35   10    1     0.80
blue_002    Blue Support      BLUE    (8,9)    32   16    2     0.55
blue_003    Blue Commander    BLUE    (7,9)    30    7    1     0.70
```

雙方完全對稱。勝負只由 seed 42 的擲骰決定 —— 換 seed 7 藍方就贏。

### 97 個事件的組成

```text
ACTION_SELECTED    46      每個存活單位每 tick 一個
MOVE               26
ATTACK             14
MISS                6
ENTITY_DESTROYED    4
SCENARIO_END        1
```

### 每 tick 的事件數，看得出戰損

```text
t1:12  t2:12  t3:12  t4:12  t5:12  t6:12  t7:7  t8:6  t9:6  t10:6
                                              ↑
                                    tick 6 雙殺後單位剩下 4 個
```

前六個 tick 是雙方橫越地圖接近，每 tick 穩定 12 個事件。

### 戰鬥經過

```text
tick 6   blue_003 陣亡（red_001 擊殺）
tick 6   red_003  陣亡（blue_002 擊殺）      ← 同一 tick 互換
tick 7   blue_002 陣亡（red_002 擊殺）
tick 10  blue_001 陣亡（red_002 擊殺）
```

終局：

```text
red_001    RED   active     hp 35     ← 全程未被擊中
red_002    RED   active     hp 22     ← 四殺中拿下三殺
red_003    RED   destroyed  hp -13
blue_001   BLUE  destroyed  hp -11
blue_002   BLUE  destroyed  hp   0
blue_003   BLUE  destroyed  hp  -3
```

`RED_survived`。決定性因素是 `red_002`（傷害 16、射程 2）—— 射程 2 讓它能在對手夠不到的距離輸出。

---

## 3. Event Shape：十七個欄位

一個真實的 ATTACK 事件（tick 5，red_002 打 blue_003）：

```json
{
  "event_id": "event_98f5df28a4",
  "time": 5,
  "event_type": "ATTACK",
  "actor_id": "red_002",
  "system_id": "temporary_tactical_reference_policy",
  "target_entity_id": "blue_003",
  "source_action_id": "action_f5a9182c2b",
  "affected_entities": ["blue_003"],
  "affected_locations": [[3, 5]],
  "affected_resources": [],
  "affected_risks": [],
  "before_state": { "state": { "hp": 30, "ap": 60, "status": "active" } },
  "after_state":  { "state": { "hp": 14, "last_damage_taken": 16 } },
  "causal_links": { "caused_by": ["event_bd81986263"], "caused_events": [] },
  "evaluation_relevance": { "affects_success": true, "affects_cost": true },
  "data": {},
  "tags": []
}
```

| 欄位 | 裝什麼 | 目前狀態 |
|---|---|---|
| `event_id` | 事件唯一識別 | `uuid4()`，不受 seed 控制 |
| `time` | 第幾 tick | |
| `event_type` | 八種型別之一 | |
| `actor_id` | 誰做的 | |
| `system_id` | 哪個系統決策的 | 目前恆為 policy 名稱 |
| `target_entity_id` | 對誰 | 無目標時為 null |
| `source_action_id` | 源自哪個 action | causal_chain 靠它分組 |
| `affected_entities` | 受影響的單位 | |
| `affected_locations` | 受影響的座標 | |
| `affected_resources` | 受影響的資源 | **恆空** |
| `affected_risks` | 受影響的風險 | **恆空** |
| `before_state` / `after_state` | 前後快照 | 有 target 時記的是 target |
| `causal_links` | 因果鏈 | |
| `evaluation_relevance` | 三個評估旗標 | |
| `data` | 型別專屬資料 | ATTACK 放 hp_before / hp_after / damage |
| `tags` | 標籤 | |

`before_state` / `after_state` 存的是**深拷貝**，事件寫入後不會被後續的世界變動污染 —— 這是回放能成立的前提。

---

## 4. 四個 exporter 實際做什麼

### `replay_state_at_tick.json`

```text
states: ["0", "1", "2", ..., "10", "final"]
```

演算法的關鍵是 tick 邊界：

```python
# 下一個 tick 開始時，才封存上一個 tick
if previous_tick is not None and tick != previous_tick:
    states[str(previous_tick)] = snapshot()

# 迴圈結束後補最後一個 —— 因為它後面沒有下一個 tick
if previous_tick is not None:
    states[str(previous_tick)] = snapshot()
```

實際查詢：

```text
tick 5 的 blue_003 : hp 7,  status active
tick 6 的 blue_003 : hp -3, status destroyed
```

### `causal_chain.json`

46 條 chain，對應 46 個 `ACTION_SELECTED`。含擊殺的那條：

```json
{
  "source_action_id": "action_8a85bb69f3",
  "events": ["event_20fc9e1b61", "event_d9ef4bb297", "event_b0364c55d1"],
  "event_types": ["ATTACK", "ENTITY_DESTROYED"],
  "summary": "Action action_8a85bb69f3 caused ATTACK and ENTITY_DESTROYED."
}
```

`events` 有三個 id（含 ACTION_SELECTED 本身），`event_types` 只有兩個 —— 選取步驟被刻意排除，讓 summary 讀起來是「造成攻擊與擊殺」而非「造成選取與攻擊與擊殺」。

### `entity_history.json`

`blue_003` 共 21 筆紀錄，依角色分佈：

```text
initial_state   1     開局狀態
actor          10     它自己做的事
affected        7     它被波及
target          1     它被指名為目標
final_state     2     ENTITY_DESTROYED + SCENARIO_END
```

每筆紀錄都帶同樣九個鍵。`INITIAL_STATE` 與 `SCENARIO_END` 沒有來源事件，就把事件欄位留空而非刪掉 —— 讀取端不必分辨紀錄種類。

### `timeline.txt`

tick 6 的雙殺：

```text
Tick 6

- Red Rifleman selected ATTACK against Blue Commander
- Red Rifleman successfully attacked Blue Commander: HP 7 -> 0 (damage = 7)
- Blue Commander in the BLUE faction was destroyed by Red Rifleman

- Blue Support selected ATTACK against Red Commander
- Blue Support successfully attacked Red Commander: HP 3 -> 0 (damage = 3)
- Red Commander in the RED faction was destroyed by Blue Support
```

**上面這段有兩個數字是錯的**，見第 6 節。

---

## 5. 整合階段暴露的問題

三個 section 各自交付後才發現的事。這一節是這份報告最有價值的部分 —— 下一個階段不要重蹈。

### exporter 從未被 runner 呼叫

`replay.py` 與 `causal_chain.py` 寫成了腳本而非模組（無函式、import 即執行），runner 因此無物可呼叫，改成把整包 `result_package` 寫進那兩個檔名。**檔案存在、內容全錯。**

21 條 Done Criteria 裡有 11 條在看這兩個檔的內容，全部落空 —— 但演算法本身是對的，只是沒被接上。

### 測試測到殘留檔

四份測試都是 `open("output/xxx.json")` 後 assert，測的是磁碟現況而非函式回傳值。舊測試之所以通過，是因為手動執行過 exporter 留下了正確檔案。

一旦 runner 跑過，`replay_state_at_tick.json` 被覆寫成 `result_package`，而後者沒有 `states` 鍵 —— 同一份測試會從綠轉紅，原因與程式邏輯無關。

### `result_package` 缺 `initial_world_state`

replay 與 entity_history 只好回頭讀 scenario 檔取得 tick 0，違反 issue #9 共同規則第 1、2 條。

在 `run()` 的 tick 迴圈前擷取 `world.snapshot()` 補上後，四個 exporter 才真正只吃 result_package。

### `event_count` 差一

evaluation 在 `SCENARIO_END` 寫入**之前**計算，少算自己，`96` 對上 `len(event_memory)` 的 `97`。改由 `run()` 明確傳入 `len(...) + 1`。

### event shape 少兩欄

Formal Spec §7.2 有 17 欄，凍結的形狀只有 15，補上 `system_id` 與 `affected_risks`。

### 修正後

四個 exporter 全成純函式，runner 負責全部寫檔，測試改為呼叫函式驗回傳值。

---

## 6. 已記錄未修的缺陷

### `timeline.txt` 的致命一擊會顯示錯誤的傷害數字

`src/skyvault/timeline.py`：

```python
if hp_after <= 0:
    hp_after = 0
    damage = hp_before - hp_after     # ← 用夾過的值回推，覆寫真實傷害
```

夾住負血是為了好讀，屬合理的顯示選擇。錯的是第二行 —— 它讓 `damage` 恆等於 `hp_before`。

| tick | attacker | target | 真實傷害 | timeline 顯示 |
|---|---|---|---|---|
| 6 | red_001 | blue_003 | 10 | **7** ✗ |
| 6 | blue_002 | red_003 | 16 | **3** ✗ |
| 7 | red_002 | blue_002 | 16 | 16 ✓（hp_after 恰為 0，巧合） |
| 10 | red_002 | blue_001 | 16 | **5** ✗ |

非致命一擊不受影響。引擎、`event_memory` 與其餘三個 exporter 全部正確。

**為什麼仍要緊**：`timeline.txt` 的存在理由是讓人不必打開 JSON。一旦其中的數字可能有誤，其餘每一行也一併失去可信度。違反 issue #9 共同規則第 2 條。

**修法**：刪除 `damage = hp_before - hp_after` 一行。

**復現**：

```bash
python3 -c "
import json
ev = json.load(open('output/event_memory.json'))
for e in ev:
    if e['event_type'] == 'ATTACK' and e['data']['hp_after'] <= 0:
        d = e['data']
        print(e['time'], e['actor_id'], e['target_entity_id'],
              '真實', d['damage'], '顯示', d['hp_before'])"
```

**決策**：本階段不修，僅記錄。

### 現有測試無法偵測輸出數值錯誤

`tests/test_timeline.py` 只檢查關鍵字是否出現，不比對任何數值與 `event_memory` 的對應欄位。四個 exporter 的測試都是這個模式 —— 上面那個缺陷就是這樣通過 34 個測試的。

---

## 7. 品質狀態

| 項目 | 結果 |
|---|---|
| `event_memory.py` 測試覆蓋率 | **100%**（32 statements，0 miss） |
| 全專案覆蓋率 | 93%（544 statements，36 miss） |
| black | 通過 |
| ruff | 通過 |
| mypy | 通過 |
| bandit | 0 issues |
| pytest | 34 passed |
| 公開 API docstring | 0 缺漏（原缺 33 處） |

### 逐檔覆蓋率

```text
event_memory.py  100%    replay.py         100%    action.py      100%
entity_history.py 97%    causal_chain.py    96%    world_state.py  95%
timeline.py       91%    policy.py          91%    engine.py       90%
scenario_loader.py 86%   evaluator.py       83%
```

### 收尾時處理的三件事

**mypy 的型別窄化**。`next_step_toward()` 開頭已有 `position is None` 的防護，但 mypy 無法在可變 dataclass 屬性上跨迴圈保持窄化。把窄化後的值綁進區域變數同時解決型別與重複查找。

**ruff 的 22 個 E402**。全部來自 tests/ 與 scripts/ 的 `sys.path.insert()` 模式 —— 1 個模式、22 個位置。以 `pyproject.toml` 的 per-file-ignores 處理，根治方式（讓套件可安裝）記在設定檔註解裡。

**bandit 的 B311**。指 `random.Random(random_seed)`。模擬要的正是可重現的偽隨機，用法正確，設定檔內註明原因後跳過。

---

## 8. 已知限制

與第 6 節的缺陷不同 —— 這些是刻意的取捨，不是錯誤。

| 項目 | 留待 | 原因 |
|---|---|---|
| `event_id` / `action_id` 不受 `random_seed` 控制 | Phase 8 Reproducibility | 兩者都用 `uuid4()`。scenario 宣告 `deterministic_mode: true`，模擬**行為**確實每次相同（同樣 97 個 event、同樣型別、同樣 `RED_survived`），但 id 每次不同，所以 `output/*.json` 無法跨 run 逐位元比對 |
| event 是攤平的 17 欄，而非 Formal Spec §7.2 的巢狀 `source:` / `affected:` | Phase 1 Contract Pack | 該階段的交付物明確包含「Event Schema」。詳見 [`../decisions/002_event_shape.md`](../decisions/002_event_shape.md) |
| `affected_resources` 每個 event 都是 `[]` | Phase 2 World Runtime Core | 引擎沒有任何 action 會改動 `ap` / `hunger`，資源模型還不存在 |
| `affected_risks` 每個 event 都是 `[]` | Phase 7 / Phase 9 | 風險還不是系統裡存在的概念 |
| evaluation 只有勝負與計數，不是多軸評估 | Phase 7 Evaluation Engine | Phase 4 只需要 `SCENARIO_END` 與 result_package 有足夠欄位可用 |
| `sys.path` 手法未根除 | 未定 | 需讓套件可安裝，會改動所有人的執行方式 |

---

## 9. 驗證

```bash
rm -f output/*.json output/timeline.txt
python3 scripts/run_tactical_reference.py     # 七個輸出，97 events
python3 -m pytest tests/ -q                    # 34 passed
ruff check .                                   # All checks passed
black --check src/ tests/ scripts/
mypy src/
python3 -m bandit -c pyproject.toml -r src/    # 0 issues
cd /tmp && python3 -m pytest ~/SKYVAULT/tests  # 34 passed（非 repo-root）
```

---

## 10. 一句話總結

> Phase 4 讓 SKYVAULT 的每一步都能被回放與追溯 —— `event_memory` 成為唯一真相來源，四個 exporter 全是從 result_package 推導的純函式，七個輸出一次產生；人類可讀的 timeline 在致命一擊上會印出與真相來源不符的傷害數字，該缺陷已記錄，決定留至後續階段處理。
