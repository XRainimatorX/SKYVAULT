# Phase 6 — Actor Policy / External Agent Layer v0.6

完成報告。這份文件是 Phase 6 結束時的凍結紀錄，寫完不再更新 —— 系統目前的樣子請看 [`../architecture.md`](../architecture.md)。

**狀態：功能完成，沒有已記錄未修的缺陷。**

---

## 1. 這個階段做什麼

Phase 6 開始前，一個 policy 決定所有單位；engine 直接 import tactical reference；world policy 拿到的是可以修改的 world。

目標是開發計劃的原文：「把 actor 的決策從 SKYVAULT core 完全隔離出來。SKYVAULT 不決定做什麼。」規格依據是 [`../plan/phase6_actor_agent_layer.md`](../plan/phase6_actor_agent_layer.md) 與 Formal Spec §4 步驟 4–6、§9。

```text
Issue      #29 Phase_6_actor_agent_layer（milestone #13 Phase 6 — Actor Policy / External Agent Layer）
開設       作弊 policy 的測量、world policy 讀了什麼、複製的成本；fixture 先 commit：
           tests/fixtures/actors/（participants 兩份、scripted、LLM 回覆）、data/observers/skyfox.json
步驟 A     WorldView / EntityView、order 契約、policy 以名稱延遲註冊、engine 不 import tactical reference
步驟 B     五種基本 actor、ActionQueue、多視角
步驟 C     五個 adapter、runtime.participants、runner --participants、CI
```

十五項決定與開發中的六項記錄於 [`../decisions/015_actor_agent_layer.md`](../decisions/015_actor_agent_layer.md)。

---

## 2. 這次執行發生了什麼

### 開設時的測量

```text
作弊 policy   decide_action 把所有敵人設成 destroyed、回傳 None → 4 筆 event、RED「獲勝」、沒有任何紀錄
```

這一筆讓「唯讀世界」成為這個 Phase 的第一件事。現在同一個 policy 在第一次寫入時 raise `ReadOnlyWorldError`，世界不變。

### 模擬不變

```text
reference              RED_survived / 97、output 63090026e137…
military squad         7ea5ffe9ef0ba801…   urban    f0cd3cae5b7bfa47…   mountain   014c894cc4ae9483…
military junction      ef399a40e1a015f8…   urban + overwatch   fa32c17875f01a61…
```

六個 run 都與 Phase 5 逐位元相同（測試以常數釘住）。

### 混合的 participants

```text
participants_squad       RED 三人 TAC ANGEL adapter、機槍手 HADES adapter、BLUE 軍事 baseline
                         no_winner / 295 events；ACTION_SELECTED：baseline 41、TAC_ANGEL 40、HADES 20；17 個被拒
participants_reference   RED rule_based（只看 observation）、BLUE tactical reference（讀世界）
                         no_winner / 103 events；RED 在 tick 1 看不到任何人 → 不動，BLUE 第一 tick 就前進
```

squad 的 tick 1：TAC ANGEL 替身讓班長斜走進一個已被佔的格子，SKYVAULT 拒絕 —— actor 提議，世界決定。

### 每種 actor 跑 urban

| actor | 結果 | events |
|---|---|---|
| rule_based / tac_angel_adapter / llm_assisted（沒有 client） | RED_survived | 249 |
| startx_branch_adapter | RED_survived | 368 |
| hades_adapter | no_winner | 498 |
| aerogrid_adapter | no_winner | 589（128 個移動被拒：遠離友軍走出地圖或撞上單位） |

### 驗收四條

| # | 開發計劃原文 | 如何證明 |
|---|---|---|
| 1 | tactical_reference_policy 可拔掉 | engine.py 沒有 import 它（AST）；把模組設成不能 import，rule_based 的 run 照跑；沒有 policy 可用時明確報錯 |
| 2 | 換另一個 actor policy 後 core 不用改 | 測試裡寫的 Waiter actor 只靠 register_policy 與 participants 接入，控制 BLUE；十種內建 actor 也只靠名稱 |
| 3 | actor 只能透過 Action 提交意圖 | 作弊 policy raise、世界不變；20 種寫入方式全部被擋；observing actor 只交 order，order 通過契約 |
| 4 | world_state 不 import policy | AST：world_state.py 沒有 polic / actors / engine / tactical_reference |

---

## 3. 交付了什麼

```text
src/skyvault/actors/
  view.py          WorldView、EntityView、ReadOnlyMapping / Sequence、deep_frozen、ReadOnlyWorldError
  queue.py         ActionQueue
  participants.py  Participants、Slot
  basic.py         RuleBasedActor、ScriptedActor、HumanInputActor（QueueInput、ConsoleInput）、
                   ExternalSystemActor、LLMAssistedActor、register_client
  adapters.py      TACAngelAdapter、STARTXBranchAdapter、HADESAdapter、AEROGRIDAdapter、SKYFOXAdapter
src/skyvault/contracts/order.py         Order、OrderTarget（第 19 份契約）；ScheduledAction 改為 Order 的子類
src/skyvault/contracts/scenario.py      runtime.participants
src/skyvault/contracts/observation.py   己方單位的 state
src/skyvault/policies.py                KNOWN_POLICIES、MultiViewPolicy
src/skyvault/engine.py                  decider / decide：participant 分派、唯讀世界、order 驗證
src/skyvault/observation/observe.py     local_area.distance_model、己方單位的 state
scripts/run_tactical_reference.py       --participants
data/observers/skyfox.json、tests/fixtures/actors/（開設時 commit）
ci.yml                                  Actor layer 步驟
skyvault.__version__                    0.15.0
```

---

## 4. 這一輪發現的問題

### 唯讀世界第一版讓軍事 run 慢了三倍

通用的 `__getattr__` 代理每次讀取都產生新的包裝、每次讀一格地形都把整張地形表轉成 tuple。urban 一場 104 → 360 ms，比開設時否決的「複製」（約慢一倍）還糟。四輪修正後約慢 18%（ADR 015 第 16 點）。其中最不直覺的一步：cProfile 顯示兩個版本總時間幾乎相同，但實際時間差 45% —— 差距在 `__getattr__` 內部被丟出又接住的 AttributeError，profiler 不計。

### 開設時寫了一個能執行的佔位

SKYFOX 的替身第一版是 `drone.get("hp") if False else None` 加 `raise NotImplementedError` —— 因為 observation 沒有己方單位的 energy。Phase 18 回顧改法 3 說「不寫能執行的佔位」；這次寫的是會 raise 的佔位，但本該先停下來補上缺的資料。修正：己方單位帶 state（ADR 015 第 19 點）。

### HADES 的機槍手整場不動

第一版替身只攔截「最近的己方單位是自己」的威脅，而 squad 的機槍手在後排；軍事 domain 又沒有 observe，monitor 就變成不行動。是讀 participants run 的逐單位統計時看到的（20 個 NO_ACTION）。

### 測試的寫入方式

用 `x.__setitem__(...)` 測唯讀 mapping 時，Python 內建的 mappingproxy 丟 AttributeError、自己的類別丟 ReadOnlyWorldError，兩者不一致；改用 `operator.setitem`（真正的項目指定）。

---

## 5. 品質狀態

| 項目 | 結果 |
|---|---|
| pytest | 881 passed（Phase 5 為 793） |
| Python 3.10 venv | 881 passed |
| 全專案覆蓋率 | 99% |
| `actors/` 覆蓋率 | 98–100% |
| ruff / black / mypy / bandit | 通過（mypy 109 個檔案） |
| 測試讀 `output/` | 0 處 |
| exporter 程式碼變動 | 0 行 |

### 測試分布

```text
tests/actors/test_actors.py   88   作弊 policy；20 種寫入；每個讀取對照活的世界；單位 view 唯一；frozen 的相等；
                                   六個 run 的 output_hash 釘住；拔掉 tactical reference；每個已知名稱都能建；
                                   外部 actor 經 participants 接入；分層（world_state、actors、engine）；
                                   order 契約；壞 order；規則的順序 / 記憶 / 距離模型；scripted fixture 的判決；
                                   佇列（跨執行緒、逾時、重複、async）；console；外部系統（同步、async、逾時不等待、
                                   失敗、名稱）；LLM（fixture 的五種回覆）；五個 adapter 的每種回答與替身門檻；
                                   participants（分派、重疊、未知單位、system_id、契約）；兩個 fixture；多視角；
                                   六種 actor 跑完 urban
既有測試                      793   一個 Phase 5 測試改用新 API（engine.observers），兩個加上 state / distance_model
```

### 反向驗證過的測試（19 個變異全部紅）

```text
唯讀 mapping 允許寫入 / view 的 setattr 寫到世界 / engine 給 policy 原本的 world   → 紅
engine import tactical reference / 延遲 import 拿掉                              → 紅
participants 不檢查重疊 / system_id 不用 participant_id / NO_ACTION 用預設 id      → 紅
engine 不驗證 order / 佇列接受重複 / 外部系統逾時時等它結束                        → 紅
LLM 接受不認識的目標 / STARTX 拿到 local view / HADES 沒有 wait / SKYFOX 不看 energy → 紅
ids 開放 event / close_on_known 不看記憶 / deep_frozen 不轉 tuple / state 包裝不更新 → 紅
```

---

## 6. 已知限制

| 項目 | 留待 | 原因 |
|---|---|---|
| world policy 慢約 18%（軍事） | 有需要時 | 唯讀代理的成本；reference 幾乎不變 |
| rules / environment 的 list 對 policy 是 tuple | — | 凍結一次的副作用 |
| state 裡巢狀的 dict / list 是唯讀包裝，但 view 不阻止讀到的 snapshot 被改 | — | snapshot 本來就是複本 |
| adapter 的替身很簡單 | 真系統接入時 | 真正的 TAC ANGEL 等以 callable 接入 |
| HTTP 等傳輸 | Phase 12 | 這個 Phase 只定義 actor 怎麼接入 |
| 沒有真正的 LLM 呼叫 | — | 技術欄沒有點名 SDK；client 由使用者注入 |
| 外部系統的同步 client 逾時後執行緒仍在跑 | — | Python 無法終止執行緒；結果被丟棄 |

---

## 7. 驗證

```bash
python3 scripts/run_tactical_reference.py    # RED_survived / 97；output 63090026e137
python3 scripts/run_tactical_reference.py --scenario data/scenarios/military_squad_001/v0.1.json \
    --participants tests/fixtures/actors/participants_squad.json   # TAC_ANGEL、HADES、military_baseline
python3 -m pytest tests/ -q                  # 881 passed
```

---

## 8. 一句話總結

> Phase 6 讓 SKYVAULT 只當世界：開設時一個 policy 能不留痕跡地抹掉所有敵人，現在它在第一次寫入時就被擋下；而同一場 run 裡，TAC ANGEL、HADES 與 baseline 可以各自指揮自己的單位，每個決定都記著是誰做的。
