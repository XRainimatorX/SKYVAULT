# Phase 2 — World Runtime Core v0.2

這份是**凍結紀錄**：從上傳的《SKYVAULT 全系統開發總計劃》抽出本 Phase 的原文規格，作為開設與驗收的依據，寫完不再更新。
系統目前的樣子請看 [`../architecture.md`](../architecture.md)；所有 Phase 的順序見 [`README.md`](README.md)。

---

## 在路線中的位置

```text
執行順序    第 4 位（共 21 個 Phase）
對應 Spec   §2 World Contract、§4 Execution Protocol
```

人話：做真正的世界底盤：時間、空間、實體、資源、狀態都能存在和變化。

---

## 1. 目標

建立真正的 SKYVAULT runtime core。

這是 SKYVAULT 的心臟：

```text
World State
Time Model
Space Model
Entity Registry
Resource State
Rule Set
Event Memory
State Mutation
```

## 2. 要做的功能

```text
建立 world instance
建立 entity registry
支援 tick / phase / event-driven time
支援 grid / graph / network space
支援 entity state mutation
支援 resource mutation
支援 event sourcing
支援 snapshot
```

## 3. 技術

```text
Python core engine
dataclass / Pydantic
event sourcing
snapshot store
networkx for graph / road / node space
simple in-memory runtime first
later SQLite / PostgreSQL
```

## 4. 驗收標準

```text
可以建立一個 world
可以放入 entities
可以推進 time
可以更新 state
可以記錄 event
可以從 event memory 產生 replay
```
