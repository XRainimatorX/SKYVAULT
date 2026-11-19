# Phase 3 — Action & Consequence Engine v0.3

這份是**凍結紀錄**：從上傳的《SKYVAULT 全系統開發總計劃》抽出本 Phase 的原文規格，作為開設與驗收的依據，寫完不再更新。
系統目前的樣子請看 [`../architecture.md`](../architecture.md)；所有 Phase 的順序見 [`README.md`](README.md)。

---

## 在路線中的位置

```text
執行順序    第 5 位（共 21 個 Phase）
對應 Spec   §6 Action & Consequence Contract
```

人話：讓 actor 做事，世界判斷能不能做，做完造成什麼後果。這是 SKYVAULT 心臟。Formal Spec 也把它定成 Action Attempt → Validation → Resolution → Consequence → World Mutation → Event Memory。

---

## 1. 目標

把目前 tactical slice 裡的 move / attack 擴展成一般化 Action → Consequence 系統。

Formal Spec 指出 SKYVAULT 的核心不是 action 本身，而是讓世界承受 action 並產生 consequence；流程是 Action Attempt → Validation → Resolution → Consequence → World Mutation → Event Memory。

## 2. 要做的 action framework

```text
ActionAttempt
ActionValidation
ActionResolver
Consequence
DirectEffect
SecondaryEffect
ChainReaction
EvaluationImpact
```

## 3. 初期 action types

```text
move
attack
observe
wait
repair
supply
deploy
withdraw
scan
communicate
```

## 4. 軍事線初期保留

```text
move
attack
observe
supply
repair
```

## 5. 驗收標準

```text
Action 不再直接改世界
Action 必須先 validate
Consequence 才能 mutate world
每次 mutation 必須生成 event
event 必須可追蹤 source_action_id
```
