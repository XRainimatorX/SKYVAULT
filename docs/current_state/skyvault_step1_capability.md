# SKYVAULT Step 1 能力報告（Phase 0 基線）

這份是 Phase 0 交付物的**補記**（2026-11-09）：開發計劃 Phase 0 點名這個檔案，roadmap 完成後的最終核對發現它從未以這個檔名建立。
寫完不再更新。系統目前的樣子請看 [`../architecture.md`](../architecture.md)。

## Phase 0 時已完成的能力（開發計劃 Phase 0 第 2 節）

| 能力 | 當時在哪裡 |
|---|---|
| Scenario 可載入 | `scenario_loader.py`、`data/scenarios/tactical_reference_001.json` |
| World State 可建立 | `world_state.py` |
| Entity 可存在 | `entity.py` |
| Action 可產生 | `tactical_reference_policy.py`、`action.py` |
| Consequence 可結算 | `consequence.py` |
| World State 可改變 | `engine.py` |
| Event Memory 可記錄 | `event_memory.py` |
| Evaluation Result 可輸出 | `evaluator.py` |
| Result Package 可生成 | `engine.py` → `output/result_package.json` |

## 第 3 節「下一步要補」的去處

| 項目 | 在哪裡 |
|---|---|
| README | `README.md` |
| architecture decision record | `docs/decisions/001_tactical_reference_slice_done.md`（補記）、002 起每個 Phase 一份 |
| current capability report | 這份文件；Phase 0 的完整技術文件 [`../phases/phase0_tactical_slice.md`](../phases/phase0_tactical_slice.md) |
| known limitations | README「已知限制」；每個 Phase 的完成報告第 6 節 |
| testing command | README；`phase0_tactical_slice.md` 第 5 節 |
| output explanation | `phase0_tactical_slice.md` 第 10 節「Output files」 |

## 基線數字

```text
python3 scripts/run_tactical_reference.py   # RED_survived、97 events（之後每個 Phase 都不變）
```
