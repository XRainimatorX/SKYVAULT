# 010 — Batch Simulation、Branch Comparison 與 conflict package

狀態：已採納
日期：2026-11-08
階段：Phase 10 — Batch Simulation + Branch Comparison v1.0

## 背景

開發計劃 Phase 10：一次跑很多方案、每個很多次，並排比較；兩個 action 互相衝突時不選邊，分支跑完交給 NEXUS / 使用者。功能是 batch runner、Monte Carlo、parameter sweep、parallel execution、branch comparison、conflict detection、conflict package；技術欄點名 pandas / polars；驗收七條：同一 scenario 可跑 100 次、不同 branch 可並排比較、輸出 win rate / cost / risk / failure frequency、衝突時不直接選一個、分支跑不同選項、每個 branch 有 result summary、輸出 conflict_package。

開設時先量了：每次 run 約 20 ms；reference 的 batch 請求（3 版本 + 3 掃描點 + 3 衝突分支，各 100 次）是 900 次 run；pandas 3 需要 Python 3.11，3.10 上 pip 會選 2.x。

issue #24 第 6 節在寫程式之前列出了十五項決定。這份 ADR 記錄那十五項，以及開發與整合中做的九項。**沒有 scheduled_actions 時模擬行為不變**：reference trace 不變，output_hash 63090026… 不變。

## 決定

### 1. branch = 一個 scenario 變體

Spec 沒有定義 branch 的資料形狀。SKYVAULT 能被比較的單位一直是一個 scenario，所以 branch 就是 base 的一個變體：其他版本、參數掃描的一點、或一組衝突 action 的選擇。掃描點與衝突分支都是 base 的子版本（`child_version`），version_control 由 `compare_scenarios` 算出 —— 與 Phase 9 的惡化版本同一套。

### 2. 參數掃描的路徑沿用 compare_scenarios

`entities[<id>].capabilities.accuracy`、`world_contract.rule_set.x`。版本號 `<base>+sweep:<路徑>=<值>`。不另訂一套路徑語法，讓掃描點的 changed_from_previous 與掃描路徑一模一樣。

### 3. Monte Carlo 沿用 Phase 9 的 seed 規則

controlled_random：第 i 次 seed = base seed + i；fixed：每次同一個 seed（照實執行，雖然決定性下重複等於沒重複）。

### 4. 平行 = 循序

`ProcessPoolExecutor(workers)`，`pool.map` 保持輸入順序，所以結果依（變體順序, seed）排列，與循序完全相同。workers = 1 不開 pool。唯一的差別是 batch_result 的 `workers` 欄位本身 —— 測試逐欄比較時排除它。900 次 run：循序 16.4 秒，4 workers 4.6 秒。

### 5. 勝 / 負 / 平以 perspective 陣營判定

`winner_or_result == "<P>_survived"` 為勝，其他陣營 survived 為負，其餘（時間到、同歸於盡）為平。

### 6. cost、risk、failure frequency 取自 evaluation 的原始值

cost = 己方損失的 hp（resource_cost 軸的 raw）；risk = 以己方為目標的風險事件數（risk_growth 軸的 raw）；failure frequency = verdict 為 fail 的比例 —— 與 Phase 9 的「失敗」同一個定義。不另算一套，讓 batch 的數字能對回單一 run 的評估。

### 7. 勝率的信賴區間用 Wilson 95%

100 次中 6 勝時常態近似的下界會是負的；Wilson 區間永遠在 [0, 1] 內，0 勝與全勝時也有意義。

### 8. 外部 action 的入口是 runtime.scheduled_actions

Spec §13 的衝突來自「多個系統」（TAC ANGEL、HADES…），但 SKYVAULT 還沒有接入外部系統的機制（Phase 6）。`runtime.scheduled_actions` 是最小的入口：指定 tick、指定 actor 的 action 取代 policy 的選擇。action id 仍由 `world.ids` 產生，所以有排程的 run 一樣可重現；`ACTION_SELECTED` 與結果 event 的 `source.system_id` 是提案系統（`resolver.execute(..., system_id=None)`）。契約檢查：actor 必須存在、tick 不超過 max_ticks、同 tick 同 actor 不可重複。

### 9. 衝突偵測：同一 tick 的提案兩兩比較

| 條件 | 類型 |
|---|---|
| 同一 actor 兩個 action | objective（同 priority 時加 priority） |
| 不同 actor 移入 / 部署到同一位置 | location（同 priority 時加 priority） |
| 同一目標，一個傷害、一個支援 | objective |
| 同一目標，兩個都改變它 | timing |
| 各自付得起、合起來超過存量 | resource |
| 以上任一成立且 risk_profile.level 不同 | 加 risk |

reference 的三個提案：P1–P2 objective + priority + risk，P1–P3 location。

### 10. 分支 = 衝突圖的極大獨立集，加一個基準

每個分支是一組彼此不衝突的提案，而且無法再加入任何一個；不衝突的提案每個分支都有。用 networkx 在衝突圖的補圖上找極大團。另跑一個「沒有任何提案」的基準分支（`branch:none`），evaluation_delta 相對於它。reference 的分支是 {P1}、{P2, P3} + 基準。

### 11. 不裁決

`recommendation_to_nexus.required_decision` 有衝突就是 true。`decision_reason` 只陳述取捨 —— 每個指標由哪個分支領先 —— 最後一句固定是「SKYVAULT does not choose between the branches」。

### 12. comparison 在 batch 層填

Phase 7 留空的 `better_than` / `worse_than`：單一 run 沒有可比較的對象，所以 per-run 的 evaluation 仍為空；branch_comparison 依平均分數為每個變體填上。

### 13. 四個輸出

batch_result.json（通過 BatchResult 契約，含每個 run 的紀錄）、branch_comparison.json、conflict_package.json（通過 ConflictPackage 契約）、comparative_report.md。

### 14. schema 維持 0.6

只新增三份契約（batch_spec、batch_result、conflict_package）與一個 optional 欄位（scheduled_actions）。沒有任何既有的 scenario 或 package 會因此不合法，所以不調升 —— ADR 004 的規則是「optional 改為必填時調升」。

### 15. pandas

技術欄點名 pandas / polars，選 pandas（生態較成熟、有 stubs）。aggregate.py 用 DataFrame groupby（`sort=False` 保持變體順序）；回傳的全是 plain Python 值，所以 JSON 輸出在 pandas 2 與 3 之間相同。宣告 `pandas>=2`：Python 3.10 上 pip 會選 2.x，3.11 上選 3.x，CI 兩個版本都跑。

### 16. 提案的 id 記在 metadata

`Proposal` 是 `ScheduledAction` 加上 `proposal_id`。排進 scenario 時 proposal_id 移到 `metadata.proposal_id`：scheduled action 本身沒有 id 欄位（action id 在執行時產生），但分支的 event 需要能追回是哪一道命令。

### 17. 「改變目標」的 action 表

`TARGET_EFFECTS`：attack 傷害；repair、supply 支援；deploy、withdraw 改變。repair 與 withdraw 沒有 target 時目標是 actor 自己（與 handler 一致）。傷害對支援已是 objective，不再重複記成 timing。

### 18. resource 用世界實際會收的成本

`rule_set.action_costs[action_type]` 優先，否則用提案的 required_resources —— 與 `validation.action_cost` 相同。否則一個在 rule_set 下只花 1 個零件的 repair，會因為提案寫了 30 單位燃料而被誤判為資源衝突。存量取 `world_contract.resource_state`，也就是開場的存量：衝突偵測在模擬之前做，不知道第 N 個 tick 時還剩多少。

### 19. risk 只在雙方都標了等級時比較

一邊有 risk_profile.level、一邊沒有，不算 risk conflict —— 沒有資料不等於「不同」。

### 20. 基準分支只換版本標籤

`branch:none` 是 base 加上新的 scenario_version，沒有 scheduled_actions。所以它的統計與 base 版本完全相同（測試與 reference batch 都驗證了），output_hash 因版本號不同而不同。

### 21. 掃描到 base 的值就是 base

`sweep:…accuracy=0.55` 的統計與 plan 完全相同，因為 0.55 就是 blue_002 原本的命中率。這是正確的結果，不是重複；comparative report 照實列出。

### 22. 沒有衝突時也產生 package

提案彼此不衝突時，compatible_sets 只有一組（全部提案），package 的 required_decision 為 false、conflicting_actions 為空，decision_reason 說明它們一起跑了。這讓「送了提案」永遠得到一份 package，呼叫端不用分兩種情況。

### 23. failure causes 的同分改依名稱排序（修正 Phase 9）

整合時兩次執行同一個 explore_failures，failure_map.json 的 `failure_causes` 有兩行對調：strategic_value 與 risk_growth 都是「80 of 112」。原因是 `_causes` 從 set 計數，`Counter.most_common` 對同分保留插入順序，而 set 的迭代順序跟著字串雜湊走 —— 每個 process 的 PYTHONHASHSEED 不同。**同一個輸入寫出不同的 failure map**，違反 Phase 8 的承諾（failure map 不在 output_hash 範圍內，所以沒有被抓到）。

改為依（次數遞減, 名稱）排序，並用有序的 dict 去重。行為變更：同分的 cause 從「隨機」變成「依名稱」；v0.1 的 failure map 中 risk_growth 排在 strategic_value 之前。三個不同的 PYTHONHASHSEED 下 failure_map.json 與四個 batch 輸出逐位元相同。

### 24. runtime_version 升為 0.10.0

依 ADR 008 的慣例調升；版本測試（ADR 009 第 19 點）不需改。

## 後果

```text
好處    一個請求就能把版本、參數掃描、互相衝突的命令放在同一張表上比較，每個上百次
        平行與循序結果完全相同，平行讓 900 次 run 從 16 秒降到 5 秒
        衝突永遠不被裁決：每個相容的選項都跑過，交出的是取捨，不是答案
        scheduled_actions 是 Phase 6 多 actor 接入的入口
代價    衝突偵測只看提案本身與開場存量，不知道執行到那個 tick 時的世界
        branch 只能是同一 scenario 的變體；不同 scenario 之間不比較
        沒有算力預算、排隊與自動停止（§15）
```
