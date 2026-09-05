# SKYVAULT

一個戰術模擬引擎。把一份 scenario JSON 跑成一場完整的模擬，並且讓**過程中的每一步都能被回放與追溯** —— 誰在第幾個 tick 做了什麼、造成什麼、世界因此變成什麼樣子。

目前完成到 **Phase 4（Event Memory + Replay System v0.4）**。

---

## 快速開始

```bash
git clone https://github.com/XRainimatorX/SKYVAULT.git
cd SKYVAULT
python3 scripts/run_tactical_reference.py
```

需要 Python 3.10+，沒有任何執行時期相依套件。

跑完會在 `output/` 產生七個檔案。想快速知道發生了什麼，先看 `output/timeline.txt`：

```text
Tick 6

- Red Rifleman selected ATTACK against Blue Commander
- Red Rifleman successfully attacked Blue Commander: HP 7 -> 0 (damage = 7)
- Blue Commander in the BLUE faction was destroyed by Red Rifleman
```

跑測試：

```bash
python3 -m pytest tests/ -q
```

---

## 產出什麼

| 檔案 | 這是什麼 |
|---|---|
| `event_memory.json` | **真相來源。** 這場發生過的每一件事 |
| `result_package.json` | 一次執行的完整包裝（起始狀態、終局狀態、事件、評估） |
| `final_state.json` | 終局世界狀態 |
| `timeline.txt` | 人類可讀的過程 |
| `replay_state_at_tick.json` | 每個 tick 結束時的世界 |
| `entity_history.json` | 每個單位的一生 |
| `causal_chain.json` | 哪個 action 造成哪些 event |

後面四個都是從 `event_memory.json` 推導出來的，刪掉重跑會一樣。

---

## 文件

| 你想知道 | 去哪 |
|---|---|
| 系統怎麼運作、模組怎麼分工 | [`docs/architecture.md`](docs/architecture.md) |
| 我要接手這個專案 | [`docs/handoff.md`](docs/handoff.md) |
| 某個階段做了什麼 | [`docs/phases/`](docs/phases/) |
| 為什麼這樣設計 | [`docs/decisions/`](docs/decisions/) |
| 上個階段的回顧 | [`docs/postmortems/`](docs/postmortems/) |

各階段的任務規格與驗收標準寫在 [GitHub Issues](https://github.com/XRainimatorX/SKYVAULT/issues)。

---

## Repo 結構

```text
src/skyvault/       引擎與 exporter
scripts/            執行入口
data/scenarios/     scenario 輸入
tests/              測試
output/             執行產物
docs/               文件
```

細節見 [`docs/architecture.md`](docs/architecture.md)。

---

## 進度

| Phase | 內容 | 狀態 |
|---|---|---|
| 0 | Tactical Reference Slice v0.1 | 完成 |
| 1 | Core Contract Pack | 未開始 |
| 2 | World Runtime Core | 未開始 |
| 3 | Action / Consequence 分離 | 完成（併入 Phase 0） |
| **4** | **Event Memory + Replay System** | **完成** |
| 7 | Evaluation Engine | 未開始 |
| 8 | Reproducibility | 未開始 |

Phase 4 的完成報告：[`docs/phases/phase4_event_memory.md`](docs/phases/phase4_event_memory.md)

---

## 已知限制

| 項目 | 影響 | 留待 |
|---|---|---|
| `event_id` / `action_id` 用 `uuid4()`，不受 seed 控制 | 行為可重現，但輸出檔無法跨 run 逐位元比對 | Phase 8 |
| `timeline.txt` 致命一擊顯示錯誤的傷害數字 | 4 次擊殺中 3 次顯示錯誤，其餘輸出正確 | 未定 |
| `affected_resources` / `affected_risks` 恆為空 | 資源與風險模型尚未存在 | Phase 2 / 7 |

完整清單見 [`docs/phases/phase4_event_memory.md`](docs/phases/phase4_event_memory.md)。

---

## 開發

```bash
python3 -m pytest tests/ -q --cov                # 測試與覆蓋率
ruff check .                                      # linter
black --check src/ tests/ scripts/                # 排版
mypy src/                                         # 型別
python3 -m bandit -c pyproject.toml -r src/       # 安全掃描
```

所有設定集中在 `pyproject.toml`。

送 PR 前的檢查清單見 [`docs/handoff.md`](docs/handoff.md)。
