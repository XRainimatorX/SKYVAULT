# Phase 4 — Event Memory + Replay System v0.4

這份是**凍結紀錄**：從上傳的《SKYVAULT 全系統開發總計劃》抽出本 Phase 的原文規格，作為開設與驗收的依據，寫完不再更新。
系統目前的樣子請看 [`../architecture.md`](../architecture.md)；所有 Phase 的順序見 [`README.md`](README.md)。

---

## 在路線中的位置

```text
執行順序    第 2 位（共 21 個 Phase）
對應 Spec   §7 Event Memory
```

人話：把「發生過什麼」完整記下來，讓人能復盤，不只是看最後誰贏。

---

## 1. 目標

讓 SKYVAULT 從「跑完一次」變成「可復盤、可審計、可回放」。

Definition 中明確說 SKYVAULT 要讓其他 AI、系統、人類決策、裝備方案、戰術方案進入世界後被測試、運行、記錄與分析；所以 Event Memory 是核心，不是附屬品。

## 2. 要做的功能

```text
event_id
time
event_type
source actor / system / action
affected entities / resources / locations
before_state
after_state
causal_links
evaluation_relevance
tags
```

## 3. 技術

```text
JSON event log
event sourcing
snapshot every N ticks
replay engine
timeline export
human readable event timeline
```

## 4. 輸出

```text
event_memory.json
timeline.txt
replay_state_at_tick.json
causal_chain.json
```

## 5. 驗收標準

```text
可以看第幾 tick 發生什麼
可以看某 entity 的完整歷史
可以回放到某一 tick 的 world state
可以看 action → consequence → event 的因果鏈
```
