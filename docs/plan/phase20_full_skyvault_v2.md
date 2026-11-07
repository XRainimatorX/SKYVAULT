# Phase 20 — Full SKYVAULT v2.0

這份是**凍結紀錄**：從上傳的《SKYVAULT 全系統開發總計劃》抽出本 Phase 的原文規格，作為開設與驗收的依據，寫完不再更新。
系統目前的樣子請看 [`../architecture.md`](../architecture.md)；所有 Phase 的順序見 [`README.md`](README.md)。

---

## 在路線中的位置

```text
執行順序    第 21 位（共 21 個 Phase）
對應 Spec   §22 最終總規格、§17 Authority Handoff Logic
```

人話：所有核心、接口、多 domain、失敗探索、報告、後台服務全部整合成完整系統。

---

## 1. 目標

達成完整 SKYVAULT baseline。

## 2. Full v2.0 必須具備

```text
World Contract 完整可用
Scenario Grammar 完整可用
Execution Protocol 穩定
Observation Contract 可用
Action & Consequence Engine 可用
Event Memory + Replay 可用
Evaluation Engine 可用
Failure Exploration 可用
Reproducibility 可用
Background Service 可用
External Adapter 可用
Multi-Domain Packs 至少 3 個可用
UI / Report 可用
Authority Handoff Logic 完整可用
```

## 3. 新增必備能力：Final Authority Boundary

```text
SKYVAULT 可以模擬
SKYVAULT 可以建議
SKYVAULT 可以警告
SKYVAULT 可以返回 failure map
SKYVAULT 可以返回 conflict package
SKYVAULT 可以拒絕 invalid scenario
```

但 SKYVAULT 不可以：

```text
make sovereign decision
override NEXUS
override STARTX strategic intent
replace human authority
自行決定最終戰略方案
```

## 4. 最終驗收標準

```text
NEXUS 可提交任務
SKYVAULT 可建立 world
STARTX 可提交 branch
TAC ANGEL 可提交 tactical action
HADES / AEROGRID / SKYFOX 可進入空域 scenario
星衞裝備 profile 可進入 virtual test
SKYVAULT 可跑 normal simulation
SKYVAULT 可跑 failure exploration
SKYVAULT 可輸出 result package
SKYVAULT 可 replay
SKYVAULT 可產生人類可讀報告
高風險 scenario 會生成 authority_handoff package
conflict branch 會生成 required_decision
failure exploration 結果會交回 NEXUS / 陛下
SKYVAULT 的 role 永遠保持為 world-environment engine，而不是最高決策者
```
