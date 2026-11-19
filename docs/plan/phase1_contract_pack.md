# Phase 1 — Core Contract Pack v0.1

這份是**凍結紀錄**：從上傳的《SKYVAULT 全系統開發總計劃》抽出本 Phase 的原文規格，作為開設與驗收的依據，寫完不再更新。
系統目前的樣子請看 [`../architecture.md`](../architecture.md)；所有 Phase 的順序見 [`README.md`](README.md)。

---

## 在路線中的位置

```text
執行順序    第 3 位（共 21 個 Phase）
對應 Spec   §2 World Contract、§3 Scenario Grammar、§6 Action & Consequence、§7 Event Memory、§8.3 評估結果格式、§11 Assumption / Provenance / Version、§12 Reproducibility
```

人話：先定「資料格式法律」：世界怎樣寫、scenario 怎樣寫、action/event/result 要長什麼樣。

---

## 1. 目標

把 SKYVAULT 的核心資料格式正式化。

這一步不是完整引擎，而是讓所有 future code 都有統一規格。

## 2. 要做的 contract

```text
World Contract
Scenario Grammar
Entity Schema
Action Schema
Consequence Schema
Event Schema
Evaluation Result Schema
Result Package Schema
Assumption Registry Schema
Data Provenance Schema
Reproducibility Metadata Schema
```

## 3. 原文補充

Formal Spec 裡明確定義了 World Contract 必須包含 world_scope、space_model、time_model、entity_model、environment_state、resource_state、rule_set、actor_slots、event_memory、evaluation_targets、assumption_registry、data_provenance、failure_variables 等核心元素。

## 4. 技術

```text
Python dataclass / Pydantic
JSON Schema
YAML / JSON scenario format
schema versioning
basic validation tests
```

## 5. Repo 方向

```text
src/skyvault/contracts/
src/skyvault/schemas/
data/scenarios/
tests/contracts/
docs/spec/
```

## 6. 驗收標準

```text
一份 scenario 如果缺少 scenario_id，會被拒絕
一份 action 如果沒有 actor_id，會被拒絕
一個 event 必須有 before_state / after_state
一個 result package 必須包含 evaluation_result
```
