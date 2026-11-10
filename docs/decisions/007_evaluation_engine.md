# 007 — Evaluation Engine 與 schema 0.4

狀態：已採納
日期：2026-11-08
階段：Phase 7 — Evaluation Engine v0.7

## 背景

開發計劃 Phase 7 要把 evaluation 從「誰活下來」升級成多軸評估，並加上 Metric Anti-Gaming Logic，驗收六條：

```text
同一 scenario 可以換不同 evaluation profile / 不只輸出 winner /
能指出 cost、risk、time、resource、failure points / evaluation_result 要顯示是否刷分 /
靠不行動、犧牲穩定、忽略風險拿高分必須被標記 / result package 必須包含 tradeoff_report
```

issue #21 第 6 節在寫程式之前列出了十四項決定。這份 ADR 記錄那十四項，以及開發中做的六項。

**總原則照舊：文件有寫就照字面；文件沒寫，選正式化現有行為、改動最小的做法。** 這次刻意改變輸出（result package 變大、多四個檔），但 **event memory 一筆都不變**。

## 決定

### 1. registry 實作開發計劃的 11 軸，不實作 Spec 獨有的六軸

開發計劃列 Tactical Value、Strategic Value、Resource Cost、Time Cost、Risk Growth、Failure Resistance、Recovery Ability、System Robustness、Logistics Burden、Stability Impact、Mission Success。Spec §8.3 的 scores 是另一組鍵，其中 physical_possibility、engineering_feasibility、governance_stability、crisis_resilience、commercial_demonstrability、imperial_core_value 在一場模擬裡沒有任何資料來源。

**registry 實作開發計劃的 11 軸，名稱轉成 snake_case。** Spec 獨有的六軸列為已知限制：給它們一個常數分數比不給更糟 —— 那是假裝評估過。

### 2. 分數 ∈ [0, 1]，越高越好

Spec 只寫 `0`。**每個 score 都在 [0, 1]，越高越好；成本類反轉**：resource_cost 1.0 表示沒有損失。這讓加權平均有意義，也讓「最強 / 最弱軸」可以直接比較。原始值、單位、說明放在 score_breakdown，分數背後的數字不會消失。

### 3. 評估「誰的」方案由 perspective 決定

Spec 沒說評估的是哪一方的方案。tactical reference 有兩個陣營，同一場 run 對 RED 是勝利、對 BLUE 是全滅。

**profile.perspective 指定陣營；未指定時用 scenario.evaluation.perspective，再沒有就用 scenario 第一個有陣營的 entity。** reference 的第一個 entity 是 red_001，所以預設評 RED。

### 4. 沒有資料的軸不計分，但降低信心

reference 世界沒有資源，logistics_burden 無從判斷。給它 1.0（沒花資源）會灌高分數，給 0 會冤枉它。**`applicable = False`：不計入加權，`confidence` = 可計算軸的權重 / 全部權重。** reference 在 balanced 下 confidence 0.92（12 / 13）。recommended_next_tests 會列出「去測這一軸」。

### 5. risk_growth 與 stability_impact 是代理指標

沒有風險模型、沒有穩定模型（Phase 9 起）。**risk_growth 用以己方為目標的 affects_risk 事件，stability_impact 用全場被摧毀的比例**，說明文字裡標明「proxy」。

### 6. overall_judgement 的規則

Spec 只列四種狀態。依序判斷：

```text
fail             overall < fail 門檻，或 mission_success = 0，或 scenario failure_threshold 觸發
risky            偵測到禁止的刷分行為，或 risk_growth < 0.5
pass             overall ≥ pass 門檻
needs_more_test  其餘
```

fail 優先：一個失敗的方案不需要再被說「有風險」。risky 在 pass 之前：刷出來的高分不能算通過。

### 7. 五項 penalty 對應五個行為

開發計劃列五項 penalty，Spec §16 列三個 forbidden behavior。一對一對應，補兩個行為名：

```text
inaction_penalty        maximize_score_by_inaction
stability_penalty       sacrifice_long_term_stability_for_short_term_success
risk_spike_penalty      extreme_high_risk_optimization                              （新增）
hidden_risk_penalty     ignore_hidden_risk_to_improve_visible_score
long_term_cost_penalty  sacrifice_strategic_value_for_short_term_tactical_value     （新增）
```

**觸發一定被報告；只有行為列在 profile 的 forbidden 清單時才扣分並算作刷分。** tactical profile 不在乎穩定，焦土式的勝利就可以成立 —— 但若加入 stability 檢查而不禁止它，trade-off report 會寫「觸發但此 profile 允許」。

### 8. 第 12 份契約：evaluation_profile

Spec §16 的 metric_anti_gaming 欄位（primary_metric、secondary_metrics、anti_gaming_metrics、forbidden_optimization_behaviors、tradeoff_report_required）保留原名，加上 profile_id、perspective、weights、thresholds。thresholds 的鍵是 `pass` 與 `fail`；`pass` 是 Python 關鍵字，model 用 alias，`check()` 因此改為依 alias 輸出（目前只有這一個 alias，其他契約不受影響）。

### 9. 評估在 SCENARIO_END 之後，只讀紀錄

評估若在 engine 內部、用 WorldState 計算，就可能用到「引擎知道但沒記錄」的資訊。**`evaluate_run()` 是 initial / events / final 的純函式，evaluation/ 套件與 exporter 一樣不 import 專案模組。**

SCENARIO_END 的 data 維持原本的勝負摘要 —— 這讓 **event memory 一筆都不變**。package 的 evaluation_result 是那份摘要加上多軸判斷；key_findings 在原本三條後面追加三條。

### 10. scenario 的 primary_metrics 維持原意

reference scenario 的 primary_metrics 是 `event_count`、`winner_or_result` 等摘要欄位名，不是 registry 指標。**它們維持「摘要要報告什麼」的意思；計分由 profile 決定。** 把兩者混在一起，就得讓 `event_count` 有一個分數。

### 11. comparison 為空

單一 run 沒有比較對象。better_than / worse_than 是空 list，留給 Phase 10（批量）與 Phase 12（仲裁）。

### 12. 四個新輸出；result package 三個新欄位

```text
evaluation_result.json       result_package["evaluation_result"]
score_breakdown.json         result_package["score_breakdown"]
anti_gaming_report.json      result_package["anti_gaming_report"]
tradeoff_report.md           render_tradeoff_report(result_package["tradeoff_report"])
```

驗收第 6 條「result package 必須包含 tradeoff_report」由契約強制：三個欄位都是必填。

### 13. 支援兩種 failure_threshold

`all_entities_destroyed`、`perspective_eliminated` 會被檢查；其他名稱不猜測其意思，寫進 recommended_next_tests：「尚未評估」。

### 14. schema_version 升為 0.4

ADR 004 承諾 evaluation_result 的 §8.3 欄位在 Phase 7 改為必填；加上 result package 三個新欄位，契約不相容，升為 `"0.4"`。scenario.evaluation 新增 optional 的 perspective。scenario 檔只需改版本號。

### 15. profile 的載入放在 scenario_loader，不在 contracts（偏離凍結介面的分組）

凍結介面把 `load_evaluation_profile` 與 `default_evaluation_profile` 列在「contracts」底下。但契約的規則是純函式、不開檔。**兩者放在 `scenario_loader.py`，與 `load_scenario` 並列**；`validate_evaluation_profile` 仍在 contracts。簽名不變。

### 16. 三項檢查要求「看得見的成功」

凍結的對應表只寫了行為名，沒寫觸發條件的細節。stability、hidden_risk、long_term_cost 三項的本意都是「高分背後藏著代價」，所以都要求對應的成功指標 ≥ 0.8：

```text
stability_penalty        mission_success ≥ 0.8
hidden_risk_penalty      mission_success ≥ 0.8
long_term_cost_penalty   tactical_value ≥ 0.8
```

輸掉的一方不會被說成「為了勝利犧牲穩定」。

### 17. hidden_risk 的門檻從 0.5 改為 0.3

fixture commit 時三份 profile 的 hidden_risk 門檻是 0.5（存活者中瀕危的比例 > 0.5 才觸發）。寫測試時在 300 個 seed 裡找不到任何一場勝方存活者過半瀕危的 run；最接近的是 seed 11：BLUE 勝、兩個存活者中 blue_002 只剩 6 / 32 hp（0.5）。

兩個存活者有一個瀕危，正是這項檢查要抓的情況。**門檻改為 0.3**，balanced profile 原樣就能標記 seed 11。

### 18. recovery_ability 用「曾經損失的 hp」當分母

凍結定義是「REPAIR 恢復的 hp / F 損失的 hp」。hp_lost() 算的是結束時的淨損失（已扣掉修復），所以分母用淨損失 + 已恢復 = 曾經損失的總量，比例才不會超過 1。

### 19. 最弱軸同分時依名稱排序

同分的軸在「最強」依名稱排序，「最弱」原本因為反轉而變成反向。統一為同分依名稱，讓報告可預測。

### 20. consequence 的 evaluation_impact 不進評估

Phase 3 的每個 Consequence 都有五個數值 delta，但 consequence 不在 result package 裡；評估只讀紀錄，所以用不到它們。要用的話得先把 consequence 寫進 event memory 或 result package —— 那是另一個 Phase 的決定。記為已知限制。

## 後果

```text
好處    一場 run 可以用不同 profile 重新評估，不必重跑
        刷分行為被看見：reference 在 balanced 下因為焦土式勝利被判 risky
        每個分數都能追溯到 event memory 裡的數字
代價    result package 大了約 5%（131 KB → 138 KB）
        11 軸中有兩個是代理指標，分數只代表目前能從紀錄中看到的東西
```
