# 002 — Phase 4 的 event shape

狀態：已採納
日期：2026-09-04
階段：Phase 4 — Event Memory + Replay System v0.4

## 背景

Formal Spec §7.2 定義了 event 的正典格式，其中 `source` 與 `affected` 是巢狀結構：

```yaml
event:
  source:
    actor_id: ""
    system_id: ""
    action_id: ""
  affected:
    entities: []
    locations: []
    resources: []
    risks: []
```

Phase 4 開工時，三個 Section 為了平行開發先凍結了一份共用的 event shape。那份凍結形狀是攤平的，而且**只有 15 個欄位** —— 漏掉了 `source.system_id` 與 `affected.risks`。

三個 Section 各自照那份凍結形狀做到完成，但成品與 Spec §7.2 對不上。

## 決定

**補上缺的兩個欄位，但不改成巢狀結構。**

實際輸出的 17 個頂層欄位，依 Spec 的語意分組排列：

```
event_id · time · event_type
actor_id · system_id · target_entity_id · source_action_id
affected_entities · affected_locations · affected_resources · affected_risks
before_state · after_state
causal_links · evaluation_relevance · data · tags
```

`target_entity_id` 與 `data` 是 Spec 沒有的增補欄位，純加法，不影響對照。

## 理由

補欄位是必要的：`system_id` 在總計劃的 Phase 4 功能清單裡明確寫著「source actor / system / action」，不是可選項。`affected.risks` 則是 Spec §7.2 明列的。

不改巢狀結構有三個理由：

1. 開發順序上，**Phase 1 Contract Pack 排在 Phase 4 之後**，而 Phase 1 的交付物清單裡明確有「Event Schema」。正式 schema 化是那一階段的工作。
2. Phase 4 開工前的共同基準已經寫明：Phase 4 期間不要邊做邊改 event shape，否則三組會互相衝突。
3. 巢狀化會同時打斷四個 exporter 與六個測試檔，而補完這兩欄之後，攤平形式與 Spec §7.2 承載的**資訊完全等價** —— 差別只在欄位擺放位置。

## 為什麼有兩個欄位恆為空

`affected_resources` 與 `affected_risks` 目前在每個 event 上都是 `[]`。

這不是漏做，是誠實回報：

- **資源**：scenario 的 entity state 雖然有 `ap` 和 `hunger`，但引擎沒有任何 action 會改動它們。資源模型要到 Phase 2 World Runtime Core 才建立。
- **風險**：風險在系統裡還不是一個存在的概念。它要到 Phase 7 Evaluation Engine 與 Phase 9 Failure Exploration 才有意義。

欄位保留空結構而不是省略，是因為共同基準要求每個 event 都有完整 shape，讓下游的 timeline / replay / entity_history / causal_chain 可以用同一種方式讀每一個 event。等模型建立後填值即可，屆時不需要再改 event 結構。

## `system_id` 的取值

值來自 scenario 自己的 `world_contract.assumption_registry.actor_policy`，目前是 `temporary_tactical_reference_policy`。

`SCENARIO_END` 不是任何 actor 系統產生的，帶引擎自己的識別 `skyvault_tactical_reference_engine`。

這樣 `system_id` 回答的正是 Spec 要問的問題：這個行動是哪個系統下的。Phase 6 把 actor 換成 TAC ANGEL adapter 之後，這個欄位會自動變成該系統的識別，不必再動 event 結構。

## 交接給 Phase 1

Phase 1 Contract Pack 正式定義 Event Schema 時，需要決定是否把 `source` 與 `affected` 收回巢狀。如果收，受影響的是：

```
src/skyvault/timeline.py
src/skyvault/replay.py
src/skyvault/entity_history.py
src/skyvault/causal_chain.py
tests/test_event_memory.py 及四個 exporter 的測試
```

一併處理即可，不需要分批。
