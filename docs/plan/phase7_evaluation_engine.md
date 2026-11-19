# Phase 7 — Evaluation Engine v0.7

這份是**凍結紀錄**：從上傳的《SKYVAULT 全系統開發總計劃》抽出本 Phase 的原文規格，作為開設與驗收的依據，寫完不再更新。
系統目前的樣子請看 [`../architecture.md`](../architecture.md)；所有 Phase 的順序見 [`README.md`](README.md)。

---

## 在路線中的位置

```text
執行順序    第 6 位（共 21 個 Phase）
對應 Spec   §8 Evaluation Logic、§16 Metric Anti-Gaming Logic
```

人話：不只判斷勝負，而是評估成本、風險、時間、後勤、戰術價值、戰略價值。Spec 明確要求 Evaluation 不是 win/lose，而是多軸評估。

---

## 1. 目標

從簡單 winner / destroyed 結果，升級成 multi-axis evaluation。

Formal Spec 明確要求 Evaluation 不是 win / lose，而是多軸評估：physical possibility、engineering feasibility、tactical usefulness、strategic value、governance stability、crisis resilience、resource cost、risk growth、failure resistance、recovery ability 等。

## 2. 要做的評估軸

```text
Tactical Value
Strategic Value
Resource Cost
Time Cost
Risk Growth
Failure Resistance
Recovery Ability
System Robustness
Logistics Burden
Stability Impact
Mission Success
```

## 3. 新增功能：Metric Anti-Gaming Logic

目的：防止 actor / AI 為了刷高分而做出不合理行為。

例如：

```text
為了降低損耗而永遠不行動
為了提高速度而犧牲長期穩定
為了表面成功率而忽略隱藏風險
為了短期 tactical value 而破壞 strategic value
```

要做的功能：

```text
inaction_penalty
stability_penalty
risk_spike_penalty
hidden_risk_penalty
long_term_cost_penalty
forbidden_optimization_behaviors
tradeoff_report_required
```

## 4. 技術

```text
metric registry
scoring functions
scenario-specific evaluation profile
anti-gaming metrics
trade-off report
```

## 5. 輸出

```text
evaluation_result.json
score_breakdown.json
tradeoff_report.md
anti_gaming_report.json
```

## 6. 驗收標準

```text
同一 scenario 可以換不同 evaluation profile
不只輸出 winner
能指出 cost / risk / time / resource / failure points
evaluation_result 不只顯示高分，也要顯示是否存在刷分行為
如果 actor 靠不行動、犧牲穩定、忽略風險來拿高分，系統必須標記
result package 必須包含 tradeoff_report
```
