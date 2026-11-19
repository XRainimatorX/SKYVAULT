# Phase 7 — Evaluation Engine v0.7

完成報告。這份文件是 Phase 7 結束時的凍結紀錄，寫完不再更新 —— 系統目前的樣子請看 [`../architecture.md`](../architecture.md)，契約的現行規格請看 [`../spec/contracts.md`](../spec/contracts.md)。

**狀態：功能完成，沒有已記錄未修的缺陷。**

---

## 1. 這個階段做什麼

Phase 7 開始前，evaluation_result 只有八個欄位：誰活下來、幾筆 event、幾個單位被摧毀。一場以 4 / 6 單位陣亡換來的勝利，和一場兵不血刃的勝利，看起來一模一樣。

目標是 Formal Spec §8 的多軸評估與 §16 的 Metric Anti-Gaming。規格依據是 [`../plan/phase7_evaluation_engine.md`](../plan/phase7_evaluation_engine.md) 與 [`../plan/formal_spec.md`](../plan/formal_spec.md) §8、§16。

```text
Issue      #21 Phase_7_evaluation_engine（milestone #5 Phase 7 — Evaluation Engine）
開設       fixture 先 commit：balanced / tactical 兩份 profile、profile fixture
步驟 A     11 軸指標 + 第 12 份契約 evaluation_profile + profile 載入
步驟 B     防刷分、判斷、trade-off report
步驟 C     契約 0.4、engine / runner 接線、四個新輸出
```

trade-off report 原本規劃在步驟 C，實際放在 B：`evaluate_run` 回傳它，模組又小，分開反而讓 B 的測試不完整。每一步結束時都全綠（Phase 3 回顧改法 4 的事前寫法有效）。

開設時在 issue 第 6 節寫下十四項決定與 11 軸的一行定義。全部記錄於 [`../decisions/007_evaluation_engine.md`](../decisions/007_evaluation_engine.md)。

---

## 2. 這次執行發生了什麼

### event memory 一筆都不變

```text
Result          RED_survived
Events          97（型別分布與 Phase 3 相同）
event memory    去 uuid 後與 Phase 2 / 3 逐筆相同
timeline.txt    逐字相同
reference trace 的 97 筆 (time, type, actor, target, data)：不變
reference digest a55c2001… → 14f5ab21…（只因 result package 多了三個欄位）
```

### 同一場 run，兩種判斷

| | balanced | tactical |
|---|---|---|
| overall_score | 0.50 | 0.78 |
| status | **risky** | **pass** |
| confidence | 0.92（logistics_burden 沒有資料） | 1.00 |
| 刷分 | sacrifice_long_term_stability_for_short_term_success（−0.15） | 無 |

balanced 在乎穩定：RED 贏了，但全場 6 個單位摧毀了 4 個（stability_impact 0.33），被標記為焦土式勝利。tactical 不評穩定，同一場就通過了。

### RED 視角的 11 軸（與手算一致）

| 軸 | raw | score | 說明 |
|---|---|---|---|
| mission_success | 3 | 1.00 | 3 / 3 敵方摧毀 |
| tactical_value | 111 | 1.00 | 111 傷害 / 97 敵方 hp |
| strategic_value | 2 | 0.67 | 3 個保住 2 個 |
| resource_cost | 40 | 0.59 | 97 hp 損失 40（red_002 10、red_003 30） |
| time_cost | 10 | 0.00 | 打滿 10 / 10 tick |
| risk_growth | 1 | 0.67 | 1 筆風險事件（red_003 被摧毀） |
| failure_resistance | 6 | 0.60 | tick 6 首次損失 |
| recovery_ability | 0 | 0.00 | 損失 40 hp，沒有修復 |
| system_robustness | 0 | 1.00 | 26 個 action 沒有被拒 |
| logistics_burden | — | 不適用 | 世界沒有資源 |
| stability_impact | 4 | 0.33 | 6 個單位摧毀 4 個 |

---

## 3. 核心資料形狀

### evaluation_result（節錄）

```json
{
  "winner_or_result": "RED_survived",
  "event_count": 97,
  "scenario_id": "tactical_reference_001",
  "profile_id": "balanced",
  "perspective": "RED",
  "overall_judgement": { "status": "risky", "confidence": 0.9231 },
  "overall_score": 0.5045,
  "scores": { "mission_success": 1.0, "tactical_value": 1.0, "…": "…" },
  "failure_causes": [
    "red_003 destroyed at tick 6 by blue_002",
    "time_cost 0.00: ended at tick 10 of 10",
    "recovery_ability 0.00: 0 hp restored against 40 hp still lost",
    "Anti-gaming: sacrifice_long_term_stability_for_short_term_success"
  ],
  "recommended_next_tests": [
    "Exercise logistics_burden: the world holds no resources to spend",
    "Check whether sacrifice_long_term_stability_for_short_term_success was intended: …"
  ],
  "comparison": { "better_than": [], "worse_than": [] },
  "anti_gaming": {
    "gaming_detected": true,
    "flagged_behaviors": ["sacrifice_long_term_stability_for_short_term_success"],
    "penalty_total": 0.15
  }
}
```

### tradeoff_report.md（節錄）

```text
| Gain            | Score | Cost             | Score | Assessment                                            |
| tactical_value  | 1.00  | strategic_value  | 0.67  | both strong                                           |
| mission_success | 1.00  | stability_impact | 0.33  | mission_success bought at the expense of stability_impact |
```

---

## 4. 交付了什麼

### evaluation 套件（與 exporter 同級，不 import 專案模組）

```text
src/skyvault/evaluation/
  metrics.py       EvaluationContext、MetricValue、Metric、METRIC_REGISTRY（11 軸）
  anti_gaming.py   五項檢查 → 五個行為；detect_gaming()
  tradeoff.py      build_tradeoff_report()、render_tradeoff_report()
  evaluate.py      evaluate_run() —— 純函式
```

### 其他

```text
contracts/evaluation_profile.py   第 12 份契約
contracts/                        schema 0.4：evaluation_result 必填 §8.3 欄位；result package 加三欄
scenario_loader.py                load_evaluation_profile()、default_evaluation_profile()、scenario_perspective()
engine.py                         evaluation_profile 參數；SCENARIO_END 之後呼叫 evaluate_run
scripts/run_tactical_reference.py --profile；多寫四個檔；印出 Verdict
data/evaluation_profiles/         balanced.json、tactical.json
.github/workflows/ci.yml          驗證四個新檔；用 tactical profile 再跑一次
```

### 驗收六條

| # | 開發計劃原文 | 如何證明 |
|---|---|---|
| 1 | 同一 scenario 可以換不同 evaluation profile | balanced → risky 0.50；tactical → pass 0.78；兩者的 event 與 final state 完全相同 |
| 2 | 不只輸出 winner | evaluation_result 有 overall_judgement、overall_score、10 軸 scores、failure_causes、recommended_next_tests |
| 3 | 能指出 cost / risk / time / resource / failure points | score_breakdown 的 resource_cost、risk_growth、time_cost、logistics_burden 各有 raw 與說明；failure_causes 列出 red_003 在 tick 6 被 blue_002 摧毀 |
| 4 | evaluation_result 要顯示是否存在刷分行為 | `anti_gaming` 欄位（契約必填） |
| 5 | 不行動、犧牲穩定、忽略風險必須被標記 | 三種各有一場**引擎真的跑出來的** run：全員不行動（inaction 1.0）、reference（焦土）、seed 11（blue_002 剩 6 / 32 hp） |
| 6 | result package 必須包含 tradeoff_report | 契約必填；runner 寫出 tradeoff_report.md |

---

## 5. 這一輪發現的問題

### 「刷分偵測」需要一場真的刷分的 run

Phase 3 回顧改法 1：新能力要用觸發它的資料測。三種行為中，不行動與焦土都很容易：一個讓 policy 全回傳 None，一個就是 reference。

**忽略風險最難。** 第一個想法是把 red_002 的初始 hp 調低，讓它結束時瀕危 —— 結果整場戰局改變，RED 全滅（threat score 會看對手 hp）。改成掃 300 個 seed，找「勝方存活者中瀕危的比例 > 0.5」：**一場都沒有。** 把條件放寬到「至少一個瀕危」，找到 15 場，最早的是 seed 11：BLUE 勝、兩個存活者中 blue_002 剩 6 / 32 hp。

這揭露了 profile 門檻的問題：0.5 的門檻在這個 scenario 上永遠不會觸發。兩個存活者有一個瀕危，正是這項檢查要抓的事，所以門檻改為 0.3（ADR 007 第 17 點）。**如果沒有堅持用真的 run 測，這個門檻會帶著「有測試」的樣子上線，卻在任何實際情況下都沉默。**

### 寫指標時偏離了凍結的定義，對照時抓到

failure_resistance 的凍結定義是「第一次損失的 tick / 結束 tick」。寫的時候改成了「(第一次損失 − 1) / 結束 tick」，理由是「tick 6 失去單位代表只撐了 5 個 tick」。這在語意上說得通，但**不是凍結的定義**。

步驟 A commit 前依 Phase 3 回顧改法 3 逐條對照語意時發現，改回凍結版本（0.6 而不是 0.5）。這是改法 3 第一次在 commit 前、而不是整合時抓到偏離。

### 反向驗證的變異插在 docstring 裡

驗證「evaluation/ 不 import 專案模組」時，用 `sed '1a ...'` 在第 1 行後插入 `from ..contracts import …`。測試全綠。原因：metrics.py 的第 1 行是多行 docstring 的開頭，插入的那行**在 docstring 裡**，根本不是 import。

改成插在 `from typing import Any` 之後，測試正確變紅。**反向驗證的變異本身也要確認有被執行到** —— 一個沒生效的變異會讓人以為測試抓不到。

### 「約三成」其實是 5%

ADR 草稿寫「result package 大了約三成」。量了才知道是 131 KB → 138 KB，約 5%。數字在寫進凍結文件前都要量。

### pass 是 Python 關鍵字

Spec §16 沒有 thresholds，但 profile 需要 `pass` / `fail` 兩個門檻。`pass` 不能當欄位名，Pydantic 用 alias。`check()` 原本用欄位名輸出，驗證後 `pass` 會變成 `passing`，違反「驗證不改變資料形狀」。改為依 alias 輸出；目前全專案只有這一個 alias。

---

## 6. 品質狀態

| 項目 | 結果 |
|---|---|
| pytest | 353 passed（Phase 3 為 289） |
| 全專案覆蓋率 | 98%（2050 statements，43 miss） |
| `evaluation/` 覆蓋率 | 95–100% |
| ruff / black | 通過 |
| mypy | 通過，48 個檔案 |
| bandit | 0 issues |
| 換工作目錄跑測試 | 353 passed |
| 測試讀 `output/` | 0 處 |
| exporter 程式碼變動 | 0 行 |
| event memory 與 Phase 3 比對 | 逐筆相同 |

### 測試分布

```text
tests/evaluation/test_metrics.py            28   11 軸手算對照；不適用的軸；profile 契約
tests/evaluation/test_evaluate.py           25   驗收六條；四種判斷；五項檢查；純函式；分層
tests/evaluation/test_engine_evaluation.py   6   預設 profile；perspective；壞 profile 先失敗；換 profile 不改事件
tests/contracts/                            +7   evaluation_result 必填；分數範圍；三份輸出必填；0.3 被拒
既有測試                                    289   改動：SCENARIO_END 與 evaluation_result 的關係、schema 數量
```

### 反向驗證過的測試

```text
test_doing_nothing_scores_high_on_cost_axes_and_is_flagged      inaction 永遠回報 0 → 紅
test_a_triggered_check_the_profile_allows_costs_nothing         忽略 forbidden 清單 → 紅
test_a_win_that_hides_a_critically_damaged_survivor_is_flagged  hidden_risk 永不觸發 → 紅
test_evaluation_imports_nothing_from_the_project                metrics.py 加 from ..contracts import → 紅
                                                                （第一次變異插在 docstring 裡，無效，重做）
```

---

## 7. 已知限制

| 項目 | 留待 | 原因 |
|---|---|---|
| Spec §8.3 獨有的六軸不評 | 需要它們的 domain | 模擬中沒有資料來源 |
| risk_growth、stability_impact 是代理指標 | Phase 9 起 | 沒有風險與穩定模型 |
| comparison 恆為空 | Phase 10 / 12 | 單一 run 沒有比較對象 |
| consequence 的 evaluation_impact 不進評估 | 未定 | consequence 不在 result package |
| profile 的門檻是經驗值 | 有更多 scenario 時調整 | 只有一個 reference scenario 可以校準 |
| perspective 預設取第一個 entity 的陣營 | — | scenario 可用 evaluation.perspective 明確指定 |

---

## 8. 驗證

```bash
rm -f output/*.json output/*.txt output/*.md
python3 scripts/run_tactical_reference.py                       # Verdict: risky (score 0.50, profile balanced)
python3 scripts/run_tactical_reference.py --profile data/evaluation_profiles/tactical.json   # pass 0.78
python3 -m pytest tests/ -q                                      # 353 passed
cd /tmp && python3 -m pytest ~/SKYVAULT/tests -q                 # 353 passed
ruff check . && black --check src/ tests/ scripts/
python3 -m mypy src/
python3 -m bandit -c pyproject.toml -r src/
python3 scripts/export_schemas.py && git status src/skyvault/schemas/   # 無變動
```

---

## 9. 一句話總結

> Phase 7 讓 evaluation_result 從「誰活下來」變成由 profile 決定權重的 11 軸判斷 —— 同一場勝利在 balanced 下因焦土被判 risky、在 tactical 下通過；三種刷分行為各由一場引擎真的跑出來的 run 證明會被標記；評估只讀紀錄、與 exporter 同級，所以 event memory 一筆都沒變。
