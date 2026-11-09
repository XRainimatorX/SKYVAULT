# 001 — Tactical Reference Slice v0.1 定為第一個技術基線

狀態：已採納（補記）
日期：2026-11-09（補記；基線本身在 Phase 0 時已存在）
階段：Phase 0 — Baseline

## 背景

開發計劃 Phase 0 的交付物點名這份 ADR 與 `docs/current_state/skyvault_step1_capability.md`。
roadmap 完成後的最終核對發現：這兩個檔名從未建立，ADR 編號從 002 開始。
內容本身已在 [`../phases/phase0_tactical_slice.md`](../phases/phase0_tactical_slice.md)（Phase 0 的完整技術文件）與 README。
這份 ADR 補上計劃點名的紀錄，不改任何程式或行為。

## 決定

把 Tactical Reference Slice v0.1 —— `scenario json → world state → actor policy → action → validation →
consequence → world state mutation → event memory → evaluation → output json` —— 定為 SKYVAULT 的第一個技術基線。

之後每個 Phase 都以這條基線的 reference run 作為不變量：`tactical_reference_001` 的結果 RED_survived、
97 個 event（Phase 8 起另釘 output_hash `63090026e137`）。刻意改變模擬的 Phase 必須在完成報告記錄舊 → 新數字。

## 後果

```text
好處    每個 Phase 都有一條可重跑、可比對的基線；20 個 Phase 之後 reference 的結果仍與基線相同
代價    基線只有一個 grid + tick 的 tactical scenario；其他 domain 由 Phase 13–16 加入
```
