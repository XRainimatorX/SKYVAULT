# 003 — Event 收回 Spec §7.2 的巢狀形狀

狀態：已採納（取代 [002](002_event_shape.md) 中「維持攤平」的決定）
日期：2026-11-07
階段：Phase 1 — Core Contract Pack v0.1

## 背景

[ADR 002](002_event_shape.md) 在 Phase 4 把 event 維持為攤平的 17 個頂層欄位，理由是三個 section 平行開發期間不能改形狀，並明確把是否收回巢狀的決定交給 Phase 1：

```text
Phase 1 Contract Pack 正式定義 Event Schema 時，需要決定是否把 source 與 affected 收回巢狀。
```

Phase 1 的規格依據是開發總計劃與 Formal Spec。Formal Spec §7.2 的正典格式是巢狀的：

```yaml
event:
  source: {actor_id: "", system_id: "", action_id: ""}
  affected: {entities: [], locations: [], resources: [], risks: []}
```

## 決定

**event_memory 儲存的 event 改為 Spec §7.2 的巢狀形狀。**

```text
舊（攤平，17 欄）              新（巢狀，12 個頂層鍵）
actor_id                  →    source.actor_id
system_id                 →    source.system_id
source_action_id          →    source.action_id
affected_entities         →    affected.entities
affected_locations        →    affected.locations
affected_resources        →    affected.resources
affected_risks            →    affected.risks
其餘 10 欄                     不變
```

`target_entity_id` 與 `data` 是 ADR 002 已記錄的增補欄位，Spec 沒有但純屬加法，繼續保留在頂層。

**`Event` dataclass 的內部屬性維持攤平**，只有 `to_dict()` 輸出巢狀。engine 與 `world_state.record_event()` 的呼叫端完全不用改。

## 理由

1. **契約現在由機器強制。** Phase 1 之前形狀只寫在 issue 裡，Phase 4 就因此凍結出一份與 Spec 不符的 15 欄形狀。契約進了程式碼之後，程式碼裡的形狀就是正式形狀，它必須與 Spec 一致，否則 Phase 12 對外交付的 JSON Schema 會與文件矛盾。

2. **ADR 002 不改巢狀的三個理由都已不成立。** 平行開發已結束；「Phase 4 期間不要改 event shape」的約束只限 Phase 4；改動範圍正是 ADR 002 預先列出的那幾個檔案。

3. **內部屬性不動，影響面最小。** 巢狀化只發生在序列化的邊界。實際被改到的讀取端只有三處：`timeline.py` 一處、`entity_history.py` 三處、`causal_chain.py` 一處；`replay.py` 只讀 `time` 與 `after_state`，完全不受影響。

## 影響

```text
src/skyvault/event_memory.py     to_dict() 輸出巢狀
src/skyvault/timeline.py         讀 source.actor_id
src/skyvault/entity_history.py   讀 source.actor_id、source.action_id、affected.entities
src/skyvault/causal_chain.py     讀 source.action_id
tests/test_event_memory.py       改驗巢狀形狀
tests/test_causal_chain.py       改讀 source.action_id
```

四個 exporter 的**輸出格式不變**。`entity_history.json` 的紀錄與 `causal_chain.json` 的 chain 仍然叫 `source_action_id` —— 那是它們自己的輸出欄位名，不是 event 的欄位。

**模擬行為不變**：`RED_survived` / 97 events / 事件型別順序相同。

## 對外部讀取者

任何直接讀 `output/event_memory.json` 的程式都要改用巢狀鍵。Repo 內沒有這樣的讀取者（測試一律呼叫函式），但外部腳本若有，會在讀 `event["actor_id"]` 時得到 `KeyError`。
