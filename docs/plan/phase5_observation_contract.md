# Phase 5 — Observation Contract v0.5

這份是**凍結紀錄**：從上傳的《SKYVAULT 全系統開發總計劃》抽出本 Phase 的原文規格，作為開設與驗收的依據，寫完不再更新。
系統目前的樣子請看 [`../architecture.md`](../architecture.md)；所有 Phase 的順序見 [`README.md`](README.md)。

---

## 在路線中的位置

```text
執行順序    第 13 位（共 21 個 Phase）
對應 Spec   §5 Observation Contract
```

人話：不同系統看到不同世界。例如 TAC ANGEL 看局部戰場，STARTX 看大局，不再全部上帝視角。

---

## 1. 目標

讓不同系統看到不同的世界，不再只有上帝視角。

Formal Spec 將 Observation Contract 定義為：每個系統在某個時間點能看到什麼、看不到什麼、資訊有多少延遲與不確定性。

## 2. 要做的功能

```text
Observer Profile
Visible Entities
Hidden Entities
Fog of War
Sensor Confidence
Information Delay
Stale Data
Partial Observation
```

## 3. 對應系統

```text
TAC ANGEL 看局部戰術狀態
STARTX 看高層趨勢與資源壓力
HADES 看來襲威脅與防禦窗口
AEROGRID 看空域與感測器覆蓋
NEXUS 看任務進度與總體結果
```

## 4. 驗收標準

```text
同一個 world state
TAC ANGEL 和 STARTX 看到的 observation 不一樣
hidden state 不會暴露給不該看到的 actor
observation 有 confidence / delay / uncertainty
```
