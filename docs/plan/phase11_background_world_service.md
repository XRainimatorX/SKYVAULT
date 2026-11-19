# Phase 11 — Background World Service v1.1

這份是**凍結紀錄**：從上傳的《SKYVAULT 全系統開發總計劃》抽出本 Phase 的原文規格，作為開設與驗收的依據，寫完不再更新。
系統目前的樣子請看 [`../architecture.md`](../architecture.md)；所有 Phase 的順序見 [`README.md`](README.md)。

---

## 在路線中的位置

```text
執行順序    第 15 位（共 21 個 Phase）
對應 Spec   §10 Background Operation & World Service Contract、§15 Resource & Compute Governance
```

人話：把 SKYVAULT 從手動 script 變成後台服務，可 standby、跑任務、保存狀態、回傳結果。

---

## 1. 目標

把 SKYVAULT 從 script 變成後台服務。

Formal Spec 要求成熟期 SKYVAULT 是 background-operated / background-running world-environment service，支援 standby、triggered scenario、persistent world、batch simulation、monitoring、replay、failure exploration mode。

## 2. 要做的模式

```text
Standby Mode
Triggered Scenario Mode
Persistent World Mode
Batch Simulation Mode
Monitoring Mode
Replay Mode
Failure Exploration Mode
```

## 3. 新增功能：Resource & Compute Governance

目的：SKYVAULT 成熟期是 background world service，不能無限制燒算力、無限跑 scenario、無限開 branch。

要做的功能：

```text
run priority
compute budget
max scenario duration
max parallel runs
max batch count
estimated cost
auto-stop condition
queue policy
persistent world resource cap
partial result export
```

auto-stop conditions 包括：

```text
budget_exceeded
infinite_loop_detected
no_new_state_change
failure_threshold_reached
max_runtime_exceeded
resource_cap_reached
```

## 4. 技術

```text
FastAPI
Celery / RQ / Dramatiq
Redis
PostgreSQL
Docker
worker system
job queue
scheduler
health monitoring
resource limiter
checkpointing
```

## 5. 驗收標準

```text
API 可以提交 scenario run
worker 可以背景執行
可查詢 run status
可下載 result package
可重播歷史 run
可限制 compute budget
每個 run 必須有 resource_compute_governance metadata
background worker 不可無限制運行
batch simulation 必須受 max_batch_count 控制
persistent world 必須有 resource cap
如果 run 被中止，要能輸出 partial result
```
