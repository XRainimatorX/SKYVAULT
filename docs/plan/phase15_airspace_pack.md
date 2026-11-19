# Phase 15 — Airspace / HADES / SKYFOX / AEROGRID Domain Pack v1.5

這份是**凍結紀錄**：從上傳的《SKYVAULT 全系統開發總計劃》抽出本 Phase 的原文規格，作為開設與驗收的依據，寫完不再更新。
系統目前的樣子請看 [`../architecture.md`](../architecture.md)；所有 Phase 的順序見 [`README.md`](README.md)。

---

## 在路線中的位置

```text
執行順序    第 18 位（共 21 個 Phase）
對應 Spec   §21 Phase G — Multi-Domain Environment Engine（空域線）
```

人話：做空域、無人機、反無人機、防空配置測試。

---

## 1. 目標

支援低空空域、防空配置、無人機行動、HADES 反無人機測試。

Definition 裡寫明 AEROGRID、SKYFOX、HADES 都可用 SKYVAULT 的城市 / 空域環境測試防空、無人機、反無人機流程。

## 2. 包含內容

```text
airspace grid / volume
sensor coverage
drone actor
threat actor
interception window
detection probability
reaction delay
false positive / false negative
coverage gap
```

## 3. 技術

```text
trajectory model
sensor model
event simulation
probabilistic detection
2D first, 3D later
```

## 4. 驗收標準

```text
HADES 可提交 defense behavior
SKYFOX 可作為 drone actor
AEROGRID 可提交 airspace config
SKYVAULT 可輸出 detection gap / response time / failure points
```
