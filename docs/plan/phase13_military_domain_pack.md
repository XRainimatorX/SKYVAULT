# Phase 13 — Military / Tactical Domain Pack v1.3

這份是**凍結紀錄**：從上傳的《SKYVAULT 全系統開發總計劃》抽出本 Phase 的原文規格，作為開設與驗收的依據，寫完不再更新。
系統目前的樣子請看 [`../architecture.md`](../architecture.md)；所有 Phase 的順序見 [`README.md`](README.md)。

---

## 在路線中的位置

```text
執行順序    第 11 位（共 21 個 Phase）
對應 Spec   §21 Phase G — Multi-Domain Environment Engine（軍事線）
```

人話：把戰術軍事場景正式化：小隊、地形、火力、後勤、任務、doctrine 比較。

---

## 1. 目標

把現在 tactical reference slice 升級成正式軍事 domain pack。

## 2. 包含內容

```text
unit profile
formation profile
terrain profile
sensor profile
weapon capability profile
logistics profile
morale / readiness profile
command delay profile
mission objective profile
```

## 3. 功能

```text
小隊 / 排級 tactical scenario
城市戰 reference scenario
山地 reference scenario
交通節點 reference scenario
doctrine comparison
TAC ANGEL training dataset export
```

## 4. 注意

這不是 SKYVAULT core。這是第一個正式 domain pack。

## 5. 參考資料

《SKYVAULT 戰術戰鬥模擬器設計報告》提供本 Phase 的建模建議：intent + mission orders、suppression、overwatch、break contact、通訊降級（PACE）、fighting power triad（physical / moral / conceptual）、ammo 與 casualty handling。建議參數：SUPPRESS_THRESH = 60、PANIC_THRESH = 85、RETREAT_THRESH = 25、通訊 delay = 0–3 ticks、loss_prob = 0–0.2。

## 6. 驗收標準

```text
同一 SKYVAULT core 可跑不同 tactical scenario
TAC ANGEL policy 可替換 baseline policy
可輸出 state-action-outcome dataset
```
