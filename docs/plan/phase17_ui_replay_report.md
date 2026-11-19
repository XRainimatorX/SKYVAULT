# Phase 17 — UI / Replay / Report System v1.7

這份是**凍結紀錄**：從上傳的《SKYVAULT 全系統開發總計劃》抽出本 Phase 的原文規格，作為開設與驗收的依據，寫完不再更新。
系統目前的樣子請看 [`../architecture.md`](../architecture.md)；所有 Phase 的順序見 [`README.md`](README.md)。

---

## 在路線中的位置

```text
執行順序    第 10 位（共 21 個 Phase）
對應 Spec   §20.J 可視化與商業展示技術
```

人話：做人類能看的介面：時間線、地圖、replay、failure map、報告匯出。

---

## 1. 目標

讓非技術使用者能看懂 SKYVAULT 結果。

## 2. 功能

```text
event timeline
map view
replay view
scenario comparison dashboard
failure map view
causal chain view
result package viewer
PDF / DOCX export
```

## 3. 技術

```text
React / Next.js
FastAPI backend
WebSocket replay
Plotly / ECharts
map visualisation
report generator
```

## 4. 驗收標準

```text
不用打開 JSON 也能看懂 simulation process
可以看到 tick-by-tick timeline
可以看到 failure map
可以匯出 briefing report
```
