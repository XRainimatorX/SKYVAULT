# Phase 8 — Reproducibility + Version Control v0.8

這份是**凍結紀錄**：從上傳的《SKYVAULT 全系統開發總計劃》抽出本 Phase 的原文規格，作為開設與驗收的依據，寫完不再更新。
系統目前的樣子請看 [`../architecture.md`](../architecture.md)；所有 Phase 的順序見 [`README.md`](README.md)。

---

## 在路線中的位置

```text
執行順序    第 7 位（共 21 個 Phase）
對應 Spec   §11 Assumption / Provenance / Version Control、§12 Reproducibility Contract
```

人話：讓同一個 scenario 可以重跑、對照、查原因。否則結果不可審計。

---

## 1. 目標

讓 SKYVAULT 的每一次 run 可重跑、可比較、可追蹤。

Formal Spec 明確要求 Reproducibility Contract，包括 random_seed_policy、runtime_version、ruleset_version、input_hash、output_hash、deterministic_replay_available 等。

## 2. 要做的功能

```text
scenario_version
ruleset_version
runtime_version
random_seed
input_hash
output_hash
run_id
run_metadata
deterministic replay
```

## 3. 技術

```text
hashlib
metadata registry
versioned scenario folder
run registry
snapshot store
```

## 4. 驗收標準

```text
同一 scenario + 同一 seed + 同一 ruleset 會得到同一結果
不同版本 scenario 可比較差異
result package 能追蹤來源
```
