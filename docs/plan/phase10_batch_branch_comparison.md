# Phase 10 — Batch Simulation + Branch Comparison v1.0

這份是**凍結紀錄**：從上傳的《SKYVAULT 全系統開發總計劃》抽出本 Phase 的原文規格，作為開設與驗收的依據，寫完不再更新。
系統目前的樣子請看 [`../architecture.md`](../architecture.md)；所有 Phase 的順序見 [`README.md`](README.md)。

---

## 在路線中的位置

```text
執行順序    第 9 位（共 21 個 Phase）
對應 Spec   §13 Arbitration / Branch Conflict Logic
```

人話：一次跑很多方案，比誰成本低、風險小、撐得久。

---

## 1. 目標

讓 SKYVAULT 可以比較多方案，而不是只跑一次。

## 2. 要做的功能

```text
batch runner
scenario variants
branch comparison
Monte Carlo
parameter sweep
run aggregation
comparative report
```

## 3. 新增功能：Arbitration / Branch Conflict Logic

目的：當不同 actor / system 提出互相衝突的行動時，SKYVAULT 不替它們裁決誰對，而是把衝突拆成不同 branch 來跑。

要做的功能：

```text
conflict detection
incompatible action marking
conflict_type classification
separate branch simulation
branch result comparison
conflict_package output
```

conflict_type 包括：

```text
resource_conflict
timing_conflict
objective_conflict
risk_conflict
location_conflict
priority_conflict
```

## 4. 用途

```text
doctrine comparison
戰術方案比較
戰略分支比較
城市接管方案比較
裝備 profile 比較
HADES 配置比較
互相衝突 action 的分支比較
```

## 5. 技術

```text
job runner
parallel execution
pandas / polars
statistics
visual comparison
conflict detection
branch result aggregation
```

## 6. 輸出

```text
batch_result.json
branch_comparison.json
conflict_package.json
comparative_report.md
```

## 7. 驗收標準

```text
同一 scenario 可跑 100 次
不同 branch 可並排比較
輸出 win rate / cost / risk / failure frequency
如果兩個 action 互相衝突，SKYVAULT 不直接選一個
SKYVAULT 必須分支跑不同選項
每個 branch 都要有 result summary
最後輸出 conflict_package 給 NEXUS / 使用者判斷
```
