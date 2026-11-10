# 015 — Actor Policy / External Agent Layer：唯讀世界、participant 與 adapter

狀態：已採納
日期：2026-11-08
階段：Phase 6 — Actor Policy / External Agent Layer v0.6

## 背景

開發計劃 Phase 6：把 actor 的決策從 SKYVAULT core 完全隔離。SKYVAULT 只決定能不能做、做了會怎樣、後果如何記錄、結果如何評估。要做的 actor 類型：RuleBasedActor、ScriptedActor、HumanInputActor、ExternalSystemActor、LLMAssistedActor、TACAngelAdapter、STARTXBranchAdapter、HADESAdapter、AEROGRIDAdapter、SKYFOXAdapter。技術：policy interface、adapter pattern、async action submission、action queue、observation → action pipeline。驗收四條見 issue #29。

開設時的測量決定了這個 Phase 的重心：**一個 world policy 可以在 decide_action 裡把所有敵人設成 destroyed、回傳 None** —— run 只有 4 筆 event、RED「獲勝」，沒有任何 event 記錄敵人怎麼死的。「actor 只能透過 Action 提交意圖」在 Phase 5 之前只是約定。

issue #29 第 6 節在寫程式之前列出了十五項決定。這份 ADR 記錄那十五項與開發中的六項。**模擬行為不變**：reference trace、output_hash 63090026…，以及五個軍事 run（四個 reference scenario 與 overwatch 變體）的 output_hash 都與 Phase 5 相同（測試以常數釘住）。

## 決定

### 1. 新的 core 套件 actors/

view、queue、participants、basic、adapters；不 import engine（測試逐檔檢查）。

### 2. world policy 拿到唯讀的世界

engine 給 world policy 的是 `WorldView(world)` 與單位的 `EntityView`，不是 world 本身。只開放開設時量到的讀取：tick、space、ids（只有 action）、entities、active_entities、get_entity、is_occupied、active_factions、environment、resources（amount、snapshot）、rules（require、索引）、assumptions、snapshot（複本）。單位的 state / capabilities 是唯讀的 mapping，巢狀的 dict 與 list 也一樣。任何寫入、任何沒開放的屬性都 raise `ReadOnlyWorldError` —— 這是壞 policy 的程式錯誤，raise 出 run，不記成 ACTION_REJECTED（與 ADR 004 第 7 點的壞 action 相同）。開設時的作弊 policy 在第一次寫入就被擋下，世界沒有改變（測試）。

### 3. 預設 policy 以名稱取得

policies.py 的 `KNOWN_POLICIES` 把名稱對到模組（tactical_reference → skyvault.tactical_reference_policy；十種 actor 類型 → skyvault.actors），第一次用到時才 import。engine 用 `build_policy("tactical_reference")`，不再 import 它。

### 4. 「拔掉」的意思

tactical_reference_policy 不能被 import 時，用其他 policy 的 run 照跑；沒有任何 policy 可用時 `KeyError` 列出已註冊的名稱（測試把模組設成不能 import）。

### 5. order 契約

`{action_type, target, intent, required_resources, expected_effect, risk_profile, priority, confidence, metadata}` —— 第 19 份 core 契約。scheduled action（Phase 10）改為 order 加上 tick、actor_id、system_id。engine 在把 observing actor 的 order 轉成 Action 之前驗證；壞 order raise。

### 6. 五種基本 actor（都是 observation → order）

```text
RuleBasedActor       依序套用具名規則：attack_in_range、close_on_visible、close_on_known、hold
ScriptedActor        (tick, entity_id) → order；建構時每個 order 通過契約，重複的鍵被拒
HumanInputActor      InputSource：QueueInput（ActionQueue）、ConsoleInput（stdin 的 JSON，空行 = 不行動）
ExternalSystemActor  client 同步或 coroutine；逾時（預設 1 秒）或失敗 → 不行動並計數（timeouts、errors）
LLMAssistedActor     prompt = observation + 可用 action；回覆中第一個 JSON；非法 action、不認識的目標、
                     解析失敗或沒有 client → 退回 RuleBasedActor 並計數（fallbacks）
```

### 7. ActionQueue

(tick, entity_id) 為鍵；`await submit` 與 `submit_nowait`；`take(tick, entity_id, timeout)` 以 `threading.Condition` 等待；同一個鍵第二次提交 → ValueError。

### 8. 多視角

ObservingPolicy 可以宣告 `observer_profiles`（tuple）；engine 產生每一個 observation，呼叫 `decide_from_observations({observer_id: observation})`。單一視角的路徑不變。

### 9. adapter pattern

```text
TACAngelAdapter      TAC_ANGEL              {maneuver: engage | advance | hold, target, waypoint}
STARTXBranchAdapter  STARTX + TAC_ANGEL     {stance: press | hold | withdraw}；STARTX 只拿到 aggregate
HADESAdapter         HADES + TAC_ANGEL      {response: intercept | monitor, threat}
AEROGRIDAdapter      AEROGRID + TAC_ANGEL   {reposition: true | false}
SKYFOXAdapter        SKYFOX                 {waypoint: [x, y] | null}
```

每個 adapter 接受 `system`（原生輸入 → 原生回答）；沒有時用內建替身。回答的欄位不在 adapter 認識的範圍內 → ValueError（系統與 SKYVAULT 之間的約定被破壞）。

### 10. participants

scenario `runtime.participants`（只新增）：`[{participant_id, policy {name, params}, controls {factions, entity_ids}}]`。一個單位被兩個 participant 控制、或點名了不存在的單位 → 建構 engine 時 raise。沒有被控制的單位用預設 policy。契約另外檢查 participant_id 不重複、controls 不是空的。

### 11. system_id

participant 的 policy 有 system_id 用它，否則 participant_id；記在 ACTION_SELECTED、結果 event 與 NO_ACTION 上。

### 12. 隨機

所有 participant 共用 engine 唯一的 rng。

### 13. 軍事 baseline 的感測

維持每個單位自己看；observer profile 不加 sensing 欄位（Phase 5 回顧第 7 節：改動最小）。

### 14. world_state

不 import policies、actors、engine、tactical_reference_policy（AST 測試）。

### 15. 模擬不變

reference trace 與五個軍事 run 的 output_hash 不變。

## 開發中的決定

### 16. 唯讀世界的實作：一個 view、明確的屬性

第一版用通用的 `__getattr__` 代理：urban 一場從 104 ms 變成 360 ms，比被否決的「複製」還慢。逐步改成：lazy 的唯讀序列（不轉換整張地形表）、rules 與 environment 在 view 建立時凍結一次（一場 run 中它們不變）、一場 run 一個 WorldView、每個單位一個 EntityView、所有讀取都是明確的 property / method —— `__getattr__` 只在被拒時執行（它的內部 AttributeError 是真實成本，cProfile 看不到）。最後約慢 18%（urban 109 → 129 ms）。

### 17. rules 與 environment 的 list 被看成 tuple

凍結一次的副作用：rule_set 與 environment 裡的 list 在 policy 眼中是 tuple。五個軍事 run 的結果不變，代表現有 policy 不依賴它；新的 policy 不要用 `== [...]` 比較它們。

### 18. order 的 target 只寫需要的

`OrderTarget` 三欄都是可省略的（預設 null）；ActionTargetRecord 維持三欄必填。scheduled action 因此也接受只寫一欄的 target（放寬，相容）。

### 19. 己方單位帶 state（Phase 5 的 observation 只新增）

SKYFOX 需要自己的 energy；observation 的己方單位只有 hp 與 capabilities。己方的 KnownEntity 多一個 state（敵方永遠 null，契約檢查）。local_area 多 distance_model，讓 actor 用 world 的距離判斷自己的射程。

### 20. HADES 替身

第一版只攔截「最近的己方單位是自己」的威脅，squad 的機槍手在後排、整場不動。改成：先攔截對自己的威脅，否則攔截對陣營最快的威脅；monitor 在沒有 observe 時用 wait。

### 21. runtime_version 升為 0.15.0

依 ADR 008 的慣例；UI 的 package.json 同步。

## 後果

```text
好處    「actor 只能透過 Action 提交意圖」由結構保證：world policy 改不了世界，其他 actor 從不拿到世界
        每個單位可以由不同的系統決定（TAC ANGEL、HADES、baseline 同場），event 記著是誰
        外部系統、人、LLM 都有接入的方式，而且它們的失誤（逾時、壞回覆）不會拖垮整場 run
代價    world policy 慢約 18%（軍事）；參考 run 幾乎不變
        rules / environment 的 list 對 policy 是 tuple
        adapter 的替身很簡單 —— 真正的系統以 callable 接入；傳輸協定是 Phase 12
```
