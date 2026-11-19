# Phase 12 — External System Interface v1.2

這份是**凍結紀錄**：從上傳的《SKYVAULT 全系統開發總計劃》抽出本 Phase 的原文規格，作為開設與驗收的依據，寫完不再更新。
系統目前的樣子請看 [`../architecture.md`](../architecture.md)；所有 Phase 的順序見 [`README.md`](README.md)。

---

## 在路線中的位置

```text
執行順序    第 16 位（共 21 個 Phase）
對應 Spec   §9 External System Interface Contract、§13 Arbitration、§17 Authority Handoff Logic
```

人話：讓 NEXUS、STARTX、TAC ANGEL、HADES、AEROGRID、SKYFOX 等系統正式接入。

---

## 1. 目標

讓 NEXUS、STARTX、TAC ANGEL、EIDEN-01、AEROGRID、SKYFOX、HADES、CYBERHOUND、星衞計劃都可以接入 SKYVAULT。

Definition 裡明確說 SKYVAULT 是共同環境底座，這些系統可向 SKYVAULT 提供資料、作為 actor / domain module 運行、讀取結果並回傳 NEXUS。

## 2. 要做的 adapters

```text
NEXUSAdapter
STARTXAdapter
TACAngelAdapter
EIDENAdapter
AEROGRIDAdapter
SKYFOXAdapter
HADESAdapter
CYBERHOUNDAdapter
StarGuardEquipmentAdapter
```

## 3. API

```text
POST /scenario/submit
POST /world/create
POST /action/submit
GET /run/{run_id}
GET /run/{run_id}/events
GET /run/{run_id}/result
POST /failure_exploration/run
POST /branch_compare/run
```

## 4. 新增功能 A：Conflict Package Return

目的：當 STARTX、TAC ANGEL、HADES、AEROGRID 等系統提交互相衝突的 action，SKYVAULT 要把 conflict package 回傳給 NEXUS，而不是自己裁決。

要做的接口：

```text
POST /action/submit
POST /branch_conflict/resolve
GET /conflict/{conflict_id}
GET /conflict/{conflict_id}/branches
GET /conflict/{conflict_id}/package
```

## 5. 新增功能 B：Authority Handoff Logic

目的：SKYVAULT 可以 simulate、recommend、alert、reject invalid scenario、return failure map，但不能做最終戰略決策。

要做的功能：

```text
handoff_required 判斷
authority_handoff package
high_risk_outcome trigger
strategic_tradeoff trigger
conflicting_branches trigger
failure_threshold_crossed trigger
```

authority_handoff package 包含：

```text
result_summary
branch_comparison
failure_map
required_decision
skyvault_position
may_recommend: true
may_execute_final_decision: false
```

## 6. 驗收標準

```text
外部系統可提交 action
SKYVAULT 可回傳 state-action-outcome
NEXUS 可調用完整 result package
TAC ANGEL 可在 SKYVAULT 世界中測 tactical action
STARTX 可提交 branch
外部系統可以提交互相衝突的 action
SKYVAULT 可以標記 conflict
SKYVAULT 可以分支模擬
SKYVAULT 可以回傳 conflict_package
高風險結果必須觸發 handoff
衝突分支必須觸發 handoff
failure threshold crossed 必須觸發 handoff
SKYVAULT 不可自行選擇最終方案
最終決策交回 NEXUS / 陛下 / 指定權威
```
