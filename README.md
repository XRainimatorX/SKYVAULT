# SKYVAULT

一套 **AI-operated world / environment engine**。

SKYVAULT 創造可運行的虛擬世界與環境，讓其他 AI、系統、人類決策、裝備方案、戰術方案、治理方案可以進入其中被**測試、運行、記錄與分析**。

它回答的問題是：**如果這樣做，世界會怎麼變化？**

```text
世界
  ├─ 空間      ├─ 行動      ├─ 狀態變化
  ├─ 時間      ├─ 事件      ├─ 記錄
  ├─ 實體      ├─ 因果      └─ 結果分析
  └─ 規則
```

## 它不是什麼

```text
❌ 不是單純戰棋遊戲        遊戲只是表面形式，目標是測試決策與系統後果
❌ 不是單純軍事模擬器      軍事只是第一個應用場景，不是全部
❌ 不是 TAC ANGEL          那是戰術決策者；SKYVAULT 是戰術可被測試的世界
❌ 不是 STARTX             那做戰略推演；SKYVAULT 提供可驗證世界
❌ 不是 NEXUS              那是總入口與編排者；SKYVAULT 是被調用的世界環境
```

## 定位

SKYVAULT 是**接口型核心環境**，不是任何系統的上級：

```text
NEXUS       調度 SKYVAULT，讀取其結果
STARTX      把戰略方案交給 SKYVAULT 驗證
TAC ANGEL   在 SKYVAULT 世界內測試戰術行動
EIDEN-01    將情報轉成 SKYVAULT 的世界參數
```

它的重要性不來自統治其他系統，而來自：**很多系統需要一個共同環境來測試自己。**

---

## 目前的實作

本 repo 目前是 **tactical reference slice** —— 第一個應用場景（軍事戰術）的參考實作，用來驗證整條世界迴圈能跑通：

```text
scenario → world state → actor policy → action → validation
→ consequence → world mutation → event memory → evaluation → result package
```

各階段的實際進度與交付紀錄在 [`docs/phases/`](docs/phases/)，開發順序見 roadmap。

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
| 完整技術參考（1510 行） | [`docs/phases/phase4_tactical_slice.md`](docs/phases/phase4_tactical_slice.md) |
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
