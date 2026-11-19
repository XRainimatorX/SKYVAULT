# Phase 18 — Data / AI / Training Pipeline v1.8

完成報告。這份文件是 Phase 18 結束時的凍結紀錄，寫完不再更新 —— 系統目前的樣子請看 [`../architecture.md`](../architecture.md)。

**狀態：功能完成，沒有已記錄未修的缺陷。**

---

## 1. 這個階段做什麼

Phase 18 開始前，只有軍事 pack 能匯出 TAC ANGEL 用的 state-action-outcome，而且沒有任何東西阻止一場靠刷分拿高分的 run 被當成正例。

目標是開發計劃的原文：「讓 SKYVAULT 產生可供 TAC ANGEL / STARTX / HADES 等系統使用的訓練資料」，以及「防止 TAC ANGEL / STARTX / 其他 AI 從 SKYVAULT 資料裡學到錯誤刷分行為」。規格依據是 [`../plan/phase18_data_ai_training_pipeline.md`](../plan/phase18_data_ai_training_pipeline.md)。

```text
Issue      #27 Phase_18_data_ai_training_pipeline（milestone #11 Phase 18 — Data / AI / Training Pipeline）
開設       scratch venv 測 pyarrow；100 個 run 的 anti-gaming 分布 → 發現並修正軍事 pack 的 risk 標記；
           fixture 先 commit：data/training/sources.json
步驟 A     transitions（九個欄位）、labels（六個標籤、success_type）
步驟 B     filter（clean / risky / rejected、anti_gaming_report）、branches（STARTX）、export（JSONL / Parquet）
步驟 C     registry、RAG index、pipeline、scripts/build_training_data.py、CI
```

十八項決定、開設時的修正與開發中的四項記錄於 [`../decisions/013_training_pipeline.md`](../decisions/013_training_pipeline.md)。

---

## 2. 這次執行發生了什麼

### 模擬不變

```text
Result          RED_survived
Events          97
reference trace 不變；output_hash 63090026… 不變
```

### reference 訓練資料（sources.json：10 個來源 × 10 seed + 兩個 batch）

```text
run            100（clean 41、risky 20、rejected 39）
transition     9292（clean 3192、risky 2090、rejected 4010）
success_type   genuine_success 2、false_success 6、failure 92
branch 紀錄    15（reference batch 9 個變體 + 3 個衝突分支；doctrine batch 3 個變體）
時間           13.6 秒（batch 用 4 workers）
大小           JSONL 約 32 MB、Parquet 約 1.1 MB
```

| 標籤 | 出現的 run 數 |
|---|---|
| risk_spike | 17 |
| short_term_overfit | 14 |
| stability_damage | 8 |
| inaction_gaming | 1 |
| hidden_risk_ignored | 0 |
| strategic_misalignment | 0 |

六個 false_success：五個是 tactical reference（RED 存活但穩定性被犧牲），一個是 urban。**reference run 本身就是假成功** —— 它是 Phase 4 以來每個測試的基準，但若直接拿來當正例訓練，AI 學到的是「贏，但不顧代價」。

### 驗收六條

| # | 開發計劃原文 | 如何證明 |
|---|---|---|
| 1 | 可以從 run 產生 state-action-outcome dataset | transition 數 = ACTION_SELECTED 數；在 reference、軍事、惡化版本三種 run 上都測過 |
| 2 | TAC ANGEL 可用 dataset 做訓練或分析 | clean_training_dataset 以 JSONL 與 Parquet 匯出，讀回相同；每筆通過 Transition 模型 |
| 3 | STARTX 可用結果做 branch evaluation | branch_evaluation：兩個 batch、含衝突分支 |
| 4 | dataset 必須標記是否存在刷分 | 每筆帶六個標籤與違規清單 |
| 5 | anti-gaming violation 的 run 不可進主訓練集 | rejected ∩ clean = ∅（以 output_hash 檢查；測試與 CI） |
| 6 | 能區分「成功」和「假成功」 | success_type 三種；真實資料中 genuine 2、false 6 |

---

## 3. 交付了什麼

```text
src/skyvault/training/
  records.py       Transition 模型與 validate_transition
  transitions.py   build_transitions、scenario_metadata（純函式）
  labels.py        run_labels、BEHAVIOR_LABELS、LABELS（純函式）
  filter.py        bucket_of、split_runs、anti_gaming_report（純函式）
  branches.py      branch_evaluation（純函式）
  export.py        write_jsonl / read_jsonl、write_parquet / read_parquet
  registry.py      TrainingRegistry、dataset_id
  rag.py           build_rag_index、query、run_document（純函式）
  pipeline.py      run_sources、build_training_data
src/skyvault/domains/military/
  handlers.py      只把擊毀標為 risk（開設時修正）
  pack.py          observe、mission_outcome
  dataset.py       sensor_contacts（抽出共用）
data/training/sources.json
scripts/build_training_data.py      → output/training/、runs/training_registry.jsonl
pyproject.toml / ci.yml             pyarrow、pyarrow-stubs；CI 建 reference 訓練資料並檢查
skyvault.__version__                0.13.0
```

---

## 4. 這一輪發現的問題

### Phase 13 的軍事 pack 讓每一場都像在刷分

開設時量分布，軍事 run 100% 被判 `extreme_high_risk_optimization`。軍事 attack 把每一發的 event 都標成影響風險，core 只標擊毀。修正後軍事 run 分到三個集合（ADR 013 第 0 點）。**這是開設前先量的直接收穫**：如果先寫 filter 再看資料，會得到一個「所有軍事資料都是刷分」的訓練集，而 filter 本身完全正確。

### 「triggered 但未 flagged」不存在

規劃時打算用它定義 risky；量了才知道 balanced profile 禁止全部五種行為，兩者恆等。改用 Phase 7 自己的 risky 判斷。

### 我在 Phase 13 收尾後停了下來

不是被阻塞：三個允許停下的條件都沒發生。使用者問「為什麼停了」才繼續。之後的規則寫進計畫：每個 Phase 的最後一步是開設下一個 Phase（見回顧）。

### 一個佔位寫進了程式

transition 的 episode_score 第一版是一行 `x if False else 0.0` 的佔位，在第一次執行前看到並改正。

### 變異腳本的輸出被多行的 pattern 打亂

修正後每個變異一行、pattern 對不上明確標示「NO MATCH」。這輪有一個 NO MATCH（black 重排了 read_parquet），用實際的程式碼重跑後被抓到。

---

## 5. 品質狀態

| 項目 | 結果 |
|---|---|
| pytest | 718 passed（Phase 13 為 687） |
| Python 3.10 venv | 718 passed |
| 全專案覆蓋率 | 99% |
| `training/` 覆蓋率 | 97–100% |
| ruff / black / mypy / bandit | 通過（mypy 96 個檔案） |
| 測試讀 `output/` | 0 處 |
| exporter 程式碼變動 | 0 行 |

### 測試分布

```text
tests/training/test_training.py   31   三種 run 的 transition、snapshot 接續、reward、event_sequence、被拒的命令、
                                       observation 兩種、metadata；五個檢查標籤 × 三態、strategic misalignment
                                       （分數路徑與 domain 路徑）、success_type 四例；集合規則、守護測試、報告；
                                       兩種 batch 的 branch 紀錄；JSONL / Parquet 互讀；registry；RAG；
                                       管線端到端；跨 hash seed；純函式不跑模擬
既有測試                          687   未改
```

### 反向驗證過的測試

```text
違規改用 triggered 而非 flagged                → 紅
strategic misalignment 不看任務 / 不走 domain  → 紅
false / genuine success 對調                    → 紅
risky 規則拿掉                                  → 紅
rejected 的 transition 放進 clean                → 紅
next_state 用自己 / done 不看最後一個決定        → 紅
damage_taken 不把負 hp 夾到 0                    → 紅
observation 永遠 full_state                     → 紅
event_sequence 漏掉 ACTION_SELECTED             → 紅
Parquet 讀回時保留缺欄位的 None                  → 紅（第一次 NO MATCH，以實際程式碼重跑）
RAG 同分不依文件順序 / registry 取最舊的一筆     → 紅
```

---

## 6. 已知限制

| 項目 | 留待 | 原因 |
|---|---|---|
| observation 不是真正的觀測 | Phase 5 | 軍事用 pack 的感測，其他是 full_state |
| hidden_risk 與 strategic_misalignment 在真實資料中未出現 | 更多 scenario | 只有手造資料測過 |
| genuine_success 只有 2 個 | 調整 scenario 時 | 防守佔優讓看似成功本來就少 |
| reward 沒有合成單一數字 | TAC ANGEL | 加權是訓練設計，不是模擬的事實 |
| MLflow、vector store | later | 技術欄寫明 |
| 訓練資料不進版本控制 | — | 約 32 MB；由 sources.json 重產 |

---

## 7. 驗證

```bash
python3 scripts/run_tactical_reference.py           # RED_survived / 97；output 63090026e137
python3 scripts/build_training_data.py --workers 4  # 100 run：41 / 20 / 39；genuine 2、false 6
python3 -m pytest tests/ -q                          # 718 passed
```

---

## 8. 一句話總結

> Phase 18 讓 SKYVAULT 的每一場模擬都能變成訓練資料，並在交出去之前先問「這是真的成功嗎」：100 場 run 中 39 場因為刷分被擋在主訓練集外，6 場「贏了」被標為假成功 —— 其中包括每個測試都在用的 reference run 本身。
