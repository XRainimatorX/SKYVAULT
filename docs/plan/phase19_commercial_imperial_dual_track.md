# Phase 19 — Commercial / Imperial Dual Track v1.9

這份是**凍結紀錄**：從上傳的《SKYVAULT 全系統開發總計劃》抽出本 Phase 的原文規格，作為開設與驗收的依據，寫完不再更新。
系統目前的樣子請看 [`../architecture.md`](../architecture.md)；所有 Phase 的順序見 [`README.md`](README.md)。

---

## 在路線中的位置

```text
執行順序    第 20 位（共 21 個 Phase）
對應 Spec   §21 Phase J — Commercial / Imperial Dual Track
```

人話：做對外可賣的乾淨商業版，同時保留內部完整核心能力。

---

## 1. 目標

建立對外商業版與內部核心版的分離。

Definition 明確要求：外殼可商業化，核心要帝國化；短期可以包裝成 simulation / training /planning / crisis tool，但不能封死未來 NEXUS / STARTX / TAC ANGEL 接口。

## 2. 商業版可包裝為

```text
Crisis Planning Simulator
Urban Resilience Simulator
AI Scenario Testing Platform
Equipment Concept Screening Tool
Training & After-Action Review Tool
Risk Simulation Studio
```

## 3. 內部版保留

```text
multi-domain world engine
failure exploration
NEXUS / STARTX / TAC ANGEL adapter
Star Guard equipment testing
full event memory
scenario grammar
```

## 4. 驗收標準

```text
商業版能展示價值
內部 core 不被破壞
商業場景產生的技術可反哺核心
```
