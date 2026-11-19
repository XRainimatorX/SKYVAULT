# Phase 18 — Data / AI / Training Pipeline v1.8

這份是**凍結紀錄**：從上傳的《SKYVAULT 全系統開發總計劃》抽出本 Phase 的原文規格，作為開設與驗收的依據，寫完不再更新。
系統目前的樣子請看 [`../architecture.md`](../architecture.md)；所有 Phase 的順序見 [`README.md`](README.md)。

---

## 在路線中的位置

```text
執行順序    第 12 位（共 21 個 Phase）
對應 Spec   §20.E AI / Agent 技術、§20.F 資料與記憶技術、§16 Metric Anti-Gaming
```

人話：把模擬結果變成訓練資料，例如 state-action-outcome，給 TAC ANGEL / STARTX 用。

---

## 1. 目標

讓 SKYVAULT 產生可供 TAC ANGEL / STARTX / HADES 等系統使用的訓練資料。

Definition 中明確說 TAC ANGEL 需要 SKYVAULT 提供 state-action-outcome 記錄與不同戰術方案結果比較。

## 2. 要做的資料格式

```text
state
observation
action
consequence
reward / evaluation impact
next_state
event sequence
failure labels
scenario metadata
```

## 3. 新增功能：Anti-Gaming Training Filter

目的：防止 TAC ANGEL / STARTX / 其他 AI 從 SKYVAULT 資料裡學到錯誤刷分行為。

要做的資料標籤：

```text
inaction_gaming_label
risk_spike_label
stability_damage_label
short_term_overfit_label
hidden_risk_ignored_label
strategic_misalignment_label
```

要做的輸出：

```text
clean_training_dataset
risky_behavior_dataset
rejected_behavior_dataset
anti_gaming_report
```

## 4. 技術

```text
dataset exporter
Parquet / JSONL
MLflow later
RAG index
vector store later
training data registry
anti-gaming training filter
```

## 5. 驗收標準

```text
可以從 SKYVAULT run 產生 state-action-outcome dataset
TAC ANGEL 可用 dataset 做訓練或分析
STARTX 可用結果做 branch evaluation
state-action-outcome dataset 必須標記是否存在刷分行為
被評估為 anti-gaming violation 的 run 不可直接進入主訓練集
TAC ANGEL / STARTX 訓練資料要能區分「成功」和「假成功」
```
