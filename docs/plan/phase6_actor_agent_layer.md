# Phase 6 — Actor Policy / External Agent Layer v0.6

這份是**凍結紀錄**：從上傳的《SKYVAULT 全系統開發總計劃》抽出本 Phase 的原文規格，作為開設與驗收的依據，寫完不再更新。
系統目前的樣子請看 [`../architecture.md`](../architecture.md)；所有 Phase 的順序見 [`README.md`](README.md)。

---

## 在路線中的位置

```text
執行順序    第 14 位（共 21 個 Phase）
對應 Spec   §9 External System Interface Contract、§4 Execution Protocol 步驟 4–6
```

人話：把「誰來決定行動」拆出去。SKYVAULT 不自己當戰術腦，只接收 actor 的 action。

---

## 1. 目標

把 actor 的決策從 SKYVAULT core 完全隔離出來。

SKYVAULT 不決定「做什麼」。SKYVAULT 只決定：

```text
能不能做
做了會怎樣
後果如何被記錄
結果如何評估
```

Definition 也明確區分 TAC ANGEL 是戰術決策者，而 SKYVAULT 是讓戰術可被測試的世界。

## 2. 要做的 actor types

```text
RuleBasedActor
ScriptedActor
HumanInputActor
ExternalSystemActor
LLMAssistedActor
TACAngelAdapter
STARTXBranchAdapter
HADESAdapter
AEROGRIDAdapter
SKYFOXAdapter
```

## 3. 技術

```text
policy interface
adapter pattern
async action submission
action queue
observation → action pipeline
```

## 4. 驗收標準

```text
tactical_reference_policy 可拔掉
換另一個 actor policy 後 SKYVAULT core 不用改
actor 只能透過 Action 提交意圖
world_state 不 import policy
```
