# Phase 10 — Batch Simulation + Branch Comparison v1.0

完成報告。這份文件是 Phase 10 結束時的凍結紀錄，寫完不再更新 —— 系統目前的樣子請看 [`../architecture.md`](../architecture.md)，契約的現行規格請看 [`../spec/contracts.md`](../spec/contracts.md)。

**狀態：功能完成，沒有已記錄未修的缺陷。**

---

## 1. 這個階段做什麼

Phase 10 開始前，SKYVAULT 一次跑一個方案；failure exploration 能跑很多次，但只針對一個方案的惡化。不同的部署、不同的參數、不同系統給的命令，沒辦法放在同一張表上比較；兩個系統的命令互相衝突時，也沒有任何機制。

目標是 Formal Spec §13 的一句話：「SKYVAULT 不裁決誰對；SKYVAULT 展示每條路會怎樣死、怎樣活。」規格依據是 [`../plan/phase10_batch_branch_comparison.md`](../plan/phase10_batch_branch_comparison.md) 與 [`../plan/formal_spec.md`](../plan/formal_spec.md) §13。

```text
Issue      #24 Phase_10_batch_branch_comparison（milestone #8 Phase 10 — Batch Simulation + Branch Comparison）
開設       測量 run 時間與 pandas 版本；fixture 先 commit：data/batches/tactical_reference_001.json
步驟 A     child_version、variants.py、runtime.scheduled_actions（engine 與契約）
步驟 B     runner.py（平行）、aggregate.py（pandas）、三份契約
步驟 C     conflicts.py、conflict package、scripts/run_batch.py、comparative_report.md
```

十五項決定與開發、整合中的九項記錄於 [`../decisions/010_batch_branch_comparison.md`](../decisions/010_batch_branch_comparison.md)。

---

## 2. 這次執行發生了什麼

### 沒有排程時，模擬不變

```text
Result          RED_survived
Events          97
reference trace 不變；output_hash 63090026… 不變
```

### reference batch：9 個變體 × 100 次

設定：`data/batches/tactical_reference_001.json`，balanced profile，RED 視角，seed 42–141，4 workers，共 900 次 run，約 4.6 秒（循序 16.4 秒）。

| 變體 | 勝率 | 95% CI | fail | hp 損失 | 風險事件 | 分數 |
|---|---|---|---|---|---|---|
| plan（v0.1） | 6% | 3–12% | 27% | 69.05 | 1.92 | 0.395 |
| **support-rear** | **17%** | 11–26% | **17%** | **61.79** | **1.61** | **0.434** |
| spread | 12% | 7–20% | 21% | 67.96 | 1.83 | 0.415 |
| blue_002 accuracy = 0.55 | 6% | 3–12% | 27% | 69.05 | 1.92 | 0.395 |
| blue_002 accuracy = 0.65 | 7% | 3–14% | 38% | 74.6 | 2.11 | 0.362 |
| blue_002 accuracy = 0.75 | 3% | 1–8% | 41% | 79.21 | 2.22 | 0.343 |
| branch P1 | 12% | 7–20% | 23% | 65.98 | 1.73 | 0.413 |
| branch P2+P3 | 3% | 1–8% | 19% | 68.43 | 1.83 | 0.404 |
| branch none（基準） | 6% | 3–12% | 27% | 69.05 | 1.92 | 0.395 |

support-rear 在五個指標上全部最佳 —— 與 Phase 9 的結論（它撐得更久）一致，這次是從 100 次 run 的統計得出。

### 三道命令的衝突

```text
P1  TAC_ANGEL  red_002 移到 [1, 1]   high    medium   推進支援組
P2  HADES      red_002 移到 [0, 1]   high    low      撤回支援組
P3  TAC_ANGEL  red_001 移到 [1, 1]   normal  medium   推進步槍兵

C1  P1 vs P2   objective + priority + risk     同一個 actor、同為 high、風險不同
C2  P1 vs P3   location                        都要去 [1, 1]

分支   {P1}、{P2, P3}，加上沒有任何命令的基準
```

conflict package 的 decision_reason：

```text
Highest win_rate: branch P1 (0.12). Lowest failure_frequency: branch P2+P3 (0.19).
Lowest mean_hp_lost: branch P1 (65.98). Lowest mean_risk_events: branch P1 (1.73).
Highest mean_score: branch P1 (0.4128).
SKYVAULT does not choose between the branches; NEXUS or the user decides which orders to keep.
```

**這正是不裁決的理由。** P1 勝率較高，P2+P3 被判 fail 的比例較低 —— 兩個分支都比完全不下命令好，但好在不同的地方。哪一個更重要，取決於指揮官要什麼，SKYVAULT 不知道。

### 驗收七條

| # | 開發計劃原文 | 如何證明 |
|---|---|---|
| 1 | 同一 scenario 可跑 100 次 | plan 100 次、100 個 run 紀錄、100 個不同的 output_hash |
| 2 | 不同 branch 可並排比較 | branch_comparison：9 個變體同一張表、各指標最佳、相對第一個的差、better_than / worse_than |
| 3 | 輸出 win rate / cost / risk / failure frequency | 每個變體的 win_rate（含 Wilson 區間）、mean_hp_lost、mean_risk_events、failure_frequency |
| 4 | 兩個 action 衝突時不直接選一個 | required_decision true；decision_reason 只陳述取捨 |
| 5 | 必須分支跑不同選項 | {P1}、{P2, P3}、基準，各 100 次 |
| 6 | 每個 branch 都要有 result summary | 每個 branch_run 的 result_summary 與相對基準的 evaluation_delta |
| 7 | 輸出 conflict_package 給 NEXUS / 使用者 | conflict_package.json 通過 ConflictPackage 契約 |

---

## 3. 交付了什麼

```text
src/skyvault/batch/
  variants.py      Variant、set_parameter()、build_variants()、branch_variant()
  runner.py        run_jobs()、run_job() —— 循序或 ProcessPoolExecutor
  aggregate.py     METRICS、wilson_interval()、aggregate()、compare_branches()、
                   render_comparative_report() —— 純函式，pandas
  conflicts.py     detect_conflicts()、compatible_sets()、build_conflict_package() —— 純函式
  run.py           run_batch() —— 在 engine 之上
src/skyvault/reproducibility/versioning.py   child_version()；failure.apply_stress 改用它
src/skyvault/engine.py                       runtime.scheduled_actions
src/skyvault/actions/resolver.py             execute(..., system_id=None)
src/skyvault/contracts/batch.py              BatchSpec、BatchResult、ConflictPackage（第 14–16 份契約）
src/skyvault/contracts/scenario.py           ScheduledAction、RuntimeSettings.scheduled_actions
data/batches/tactical_reference_001.json     3 版本 + 3 掃描點 + 3 道命令
scripts/run_batch.py                         --batch、--repeats、--workers
pyproject.toml / ci.yml                      pandas>=2、pandas-stubs；run_batch --repeats 10 --workers 2
skyvault.__version__                         0.10.0
```

---

## 4. 這一輪發現的問題

### Phase 9 的 failure map 不是逐位元可重現的

整合時清空 output/ 重跑，`git status` 顯示 failure_map.json 有變動 —— 但輸入沒變。diff 只有兩行對調：

```text
-    "strategic_value too low in 80 of 112 failed runs",
     "risk_growth too low in 80 of 112 failed runs",
+    "strategic_value too low in 80 of 112 failed runs",
```

`_causes` 把每個 run 的 cause 放進 set 再計數。`Counter.most_common` 對同分保留插入順序，而 set 的迭代順序跟著字串雜湊走，每個 process 都不一樣。**同一個探索，在不同的 process 裡寫出不同的 failure map。**

Phase 8 證明的是 result package 的 output_hash 可重現；failure map 不在那個範圍裡，Phase 9 的測試都在同一個 process 內比較，所以兩者都看不到。

改為依（次數遞減, 名稱）排序（ADR 010 第 23 點）。新測試讓每個 run 都先列 time_cost —— 拿掉排序時，插入順序會讓它排在 mission_success 前面，所以這個變異穩定地紅，不靠運氣。修正後用三個不同的 PYTHONHASHSEED 各跑一次，failure_map.json 與四個 batch 輸出逐位元相同。

### 測試的預期值寫錯一次

100 次 run 的平均 hp 損失是 69.05，測試寫成 69.0。錯在測試（憑印象寫了四捨五入過的數字），不在程式。

### 一個反向驗證的變異存活，是測試缺口

把 decision_reason 的同分規則改成「取最後一個」，測試仍然綠。依 Phase 3 回顧改法 2 找反例：測試資料裡兩個分支的 mean_score 本來就同分（都是 0.5），只是沒有斷言。補上斷言後變異會紅。

### mypy 抓到 perspective 可能是 None

batch 請求、profile、scenario 都可能沒有 perspective。第一版直接把 None 塞進 profile；現在明確 raise。

---

## 5. 品質狀態

| 項目 | 結果 |
|---|---|
| pytest | 532 passed（Phase 9 為 467） |
| 全專案覆蓋率 | 98%（3122 statements，51 miss） |
| `batch/` 覆蓋率 | 98–100% |
| ruff / black | 通過 |
| mypy | 通過，66 個檔案 |
| bandit | 0 issues |
| 換工作目錄跑測試 | 532 passed |
| 測試讀 `output/` | 0 處 |
| exporter 程式碼變動 | 0 行 |

### 測試分布

```text
tests/batch/test_variants.py      17   三種變體、set_parameter、scheduled_actions 取代 policy、system_id、契約
tests/batch/test_batch.py         15   勝 / 負 / 平、Wilson、單一 run 標準差 0、compare_branches、平行 = 循序、100 次
tests/batch/test_conflicts.py     32   六種衝突各有觸發與不觸發、極大獨立集、package 不選邊、run_batch 分支
tests/failure/test_analysis.py    +1   同分的 cause 依名稱排序
既有測試                         467   改動：EXPORTED_CONTRACTS 加三份、counting() 接受 system_id
```

### 反向驗證過的測試

```text
test_a_scheduled_order_replaces_the_policy_and_carries…  結果 event 不帶 system_id → 紅；ACTION_SELECTED 用 policy 的 id → 紅
test_compare_branches…（best 同分取第一個）              同分規則反轉 → 紅
test_cost_risk_and_score_are_averaged…                   groupby sort=True → 紅；ddof=0 → 紅
test_wins_losses_and_draws_are_seen_from_the_perspective  拿掉「負 ≠ 勝」→ 紅
test_a_parallel_batch_is_identical_to_a_sequential_one   平行結果反轉順序 → 紅
六種衝突規則                                              priority 不看是否同級、risk 不看等級是否已知、
                                                         harm/support 不分、resource 不看單獨付不付得起、
                                                         不用 rule_set 成本、不認自己為目標、不看 tick、
                                                         不看是否佔位 —— 各自 → 紅
test_compatible_sets_follow_request_order                拿掉排序 → 紅
test_the_recommendation_states_trade_offs…               同分取最後一個 → 原本綠（缺口），補斷言後紅
test_tied_causes_are_ordered_by_name…                    拿掉排序 → 紅
```

---

## 6. 已知限制

| 項目 | 留待 | 原因 |
|---|---|---|
| 衝突偵測只看提案與開場存量 | — | 偵測在模擬之前做，不知道第 N 個 tick 的世界 |
| scheduled_actions 是唯一的外部入口 | Phase 6 | 多 actor 接入時取代 |
| 分支數隨衝突指數成長 | §15 | 極大獨立集最多 3^(n/3) 個；沒有預算與上限 |
| 沒有算力預算、排隊、自動停止 | §15 | 只有 workers 上限 |
| branch 只能是同一 scenario 的變體 | — | 版本資料夾的慣例 |
| comparison 只依平均分數 | — | per-run evaluation 的 comparison 仍為空 |

---

## 7. 驗證

```bash
rm -rf runs output/*.json output/*.txt output/*.md
python3 scripts/run_tactical_reference.py           # RED_survived / 97；output 63090026e137
python3 scripts/explore_failures.py                 # 60% / communication_failure / v0.1-support-rear
python3 scripts/run_batch.py                        # 900 runs；support-rear；P1、P2+P3；decision required
python3 -m pytest tests/ -q                          # 532 passed
cd /tmp && python3 -m pytest ~/SKYVAULT/tests -q     # 532 passed
ruff check . && black --check src/ tests/ scripts/
python3 -m mypy src/
python3 -m bandit -c pyproject.toml -r src/
```

---

## 8. 一句話總結

> Phase 10 讓 SKYVAULT 一次把 3 個部署、3 個敵方命中率與 3 道互相衝突的命令各跑 100 次、平行執行並放在同一張表上 —— 支援組放後方在每個指標上都最好；而 TAC ANGEL 與 HADES 對同一個單位下了相反的命令時，SKYVAULT 沒有選，而是把兩條路都跑完，交出「一條勝率高、一條失敗少」的取捨讓人決定。
