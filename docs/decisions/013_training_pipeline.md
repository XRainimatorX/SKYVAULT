# 013 — Data / AI / Training Pipeline 與 anti-gaming training filter

狀態：已採納
日期：2026-11-08
階段：Phase 18 — Data / AI / Training Pipeline v1.8

## 背景

開發計劃 Phase 18：讓 SKYVAULT 產生可供 TAC ANGEL / STARTX / HADES 使用的訓練資料。資料格式：state、observation、action、consequence、reward / evaluation impact、next_state、event sequence、failure labels、scenario metadata。新增 Anti-Gaming Training Filter：六個標籤（inaction_gaming、risk_spike、stability_damage、short_term_overfit、hidden_risk_ignored、strategic_misalignment）與四個輸出（clean_training_dataset、risky_behavior_dataset、rejected_behavior_dataset、anti_gaming_report）。技術：dataset exporter、Parquet / JSONL、MLflow later、RAG index、vector store later、training data registry。驗收六條見 issue #27。

開設時量了 10 個來源 × 10 seed 的 run，並因此發現 Phase 13 的一個缺陷（第 0 點）。

issue #27 第 6 節在寫程式之前列出了十八項決定。這份 ADR 記錄開設時的修正、那十八項，以及開發中的四項。**模擬行為不變**：reference trace 與 output_hash 63090026… 不變。

## 決定

### 0. 軍事 pack 只把擊毀標為 risk（修正 Phase 13）

量 anti-gaming 分布時，軍事 run 100% 被判 `extreme_high_risk_optimization`。原因：軍事 attack 把每一發（命中或未中）的 event 都標成 `affects_risk`，而 core 的 attack 只把擊毀標成 risk。risk_growth 因此膨脹，risk spike 的檢查（最糟的一個 tick 每個己方單位的風險事件數 > 0.34）每場都觸發。改成與 core 相同：命中算 success 與 cost、未中算 cost、擊毀才算 risk。模擬本身不變（evaluation_relevance 不影響任何決定）；修正後軍事 run 分到三個集合。

### 1. 新的 core 套件 training/

與 domain 無關。軍事 pack 的 build_dataset（Phase 13）保留，它有 TAC ANGEL 專用的欄位。

### 2. transition 的九個欄位

state、observation、action、consequence、reward、next_state、event_sequence、failure_labels、scenario。

### 3. observation

沒有觀測層（Phase 5）。scenario 有 domain、且 pack 提供 `observe` 時，用 pack 的感測（軍事：看得到的敵人與友軍），標 `observation_model: military_sensor`；否則是整個世界的單位摘要，標 `full_state`。

### 4. reward 不是單一數字

damage_dealt、damage_taken（到同一 actor 的下一個決定）、target_destroyed、own_destroyed，加上 episode 的 overall_score。不發明加權：怎麼合成一個 reward 是 TAC ANGEL 的訓練設計。

### 5. next_state 與 done

同一 actor 下一個 ACTION_SELECTED 上 engine 記的 snapshot；沒有下一個時用終局的 snapshot。done = 被擊毀或沒有下一個決定。

### 6. failure_labels

run 的 failure_causes（Phase 7）、actor 之後是否被擊毀、任務是否未達成。

### 7. scenario metadata 以 hash 命名

scenario_id、version、domain、profile、perspective、seed、input_hash、output_hash。不用 run_id（含時間，Phase 13 的教訓）。

### 8. 六個標籤

Phase 7 五項檢查的行為對應五個標籤；第六個 strategic_misalignment：看似成功（perspective 存活為勝方，或 verdict pass）但任務未達成。任務：有 domain 且 pack 提供 `mission_outcome` 時用它；否則 mission_success 軸 < 0.5。標籤是 run 層級，複製到每一筆 transition。

### 9. 標籤與違規

標籤 = 檢查被觸發；違規 = profile 把該行為 flagged（anti_gaming_report.flagged_behaviors），strategic_misalignment 一律是違規。在 balanced 下兩者相同，但另一個只禁止部分行為的 profile 會讓「有標籤、不違規」的 run 出現。

### 10. 三個集合

rejected：任何違規。risky：沒有違規、但 Phase 7 的判斷是 risky。clean：其餘 —— 包含 verdict fail 的真失敗。開設時量到「triggered 但未 flagged」在 balanced 下 0 次，所以 risky 不能那樣定義；用 Phase 7 自己的「risky」判斷，不另訂門檻。失敗進 clean，因為誠實的失敗是有價值的訓練資料，以 success_type 標明。

### 11. 成功與假成功

success_type：genuine_success（看似成功、無違規）、false_success（看似成功、有違規）、failure。reference run 本身就是 false_success：RED 存活，但穩定性檢查 flagged。

### 12. 主訓練集

clean_training_dataset。rejected 的 run 的 transition 永遠不在其中 —— 守護測試以 output_hash 交集檢查，CI 也檢查。

### 13. STARTX branch evaluation

batch 的每個變體一筆（metrics、Wilson 區間、相對第一個的差、ranking、在哪些指標最佳）；有 conflict package 時每個分支一筆（action_set、相對基準的差、required_decision）。

### 14. JSONL 與 Parquet

JSONL：sort_keys、一行一筆、順序固定。Parquet（pyarrow）：每個頂層欄位一欄，值存成 JSON 字串 —— 任何形狀的紀錄都能原樣讀回（測試互讀）。

### 15. training data registry

JSON Lines，同 run registry。dataset_id = 名稱 + 三個資料集內容 hash 的前 16 碼；同樣的 run 匯出兩次得到同一個 id。

### 16. RAG index first

每個 run 一份文件（scenario、結果、判斷、集合、success_type、標籤、失敗原因、key findings）；倒排索引；query 依共有的 token 數、再依文件順序排序。技術欄寫明 vector store later，所以沒有 embedding。

### 17. 大檔不進版本控制

output/training/ 約 32 MB（JSONL）；加進 .gitignore。

### 18. schema 維持 0.6

transition 的紀錄模型在 training/ 內，不是 core 契約。

### 19. pack 的兩個可選方法

training 需要 pack 的感測與任務判定，但 core 不 import pack。軍事 pack 多兩個方法 `observe`、`mission_outcome`，training 經由 `load_domain` 取得 —— 與 engine 取得 handler 的路徑相同。DomainPack protocol 不變；沒有這兩個方法的 pack 就用 full_state 與 mission_success 軸。

### 20. 感測規則抽成一個函式

`sensor_contacts(actor, units, scenario)` 從軍事 dataset 抽出，dataset 與 `observe` 共用；行為不變（軍事測試不變）。

### 21. pyarrow-stubs

mypy 需要；進 dev 相依。

### 22. runtime_version 升為 0.13.0

依 ADR 008 的慣例；UI 的 package.json 同步。

## 後果

```text
好處    任何 run 都能變成訓練資料；刷分的 run 在交出去之前就被擋在主訓練集外
        「假成功」被標出來：reference run 就是一個
        資料可重現（以 hash 命名、跨 PYTHONHASHSEED 逐位元相同）、可登記、可檢索
代價    observation 在 Phase 5 之前不是真正的觀測
        strategic_misalignment 與 hidden_risk 在目前的 100 個 run 中都沒有出現 —— 只有手造資料測過
        genuine_success 只有 2 個：防守佔優的 scenario 讓「看似成功」本來就少
```
