# 017 — External System Interface：系統 adapter、Conflict Package Return、Authority Handoff

狀態：已採納
日期：2026-11-08
階段：Phase 12 — External System Interface v1.2

## 背景

開發計劃 Phase 12：讓 NEXUS、STARTX、TAC ANGEL、EIDEN-01、AEROGRID、SKYFOX、HADES、CYBERHOUND、星衞計劃正式接入 SKYVAULT —— 各系統的 adapter、外部 API（`/scenario/submit`、`/world/create`、`/action/submit`、`/run/{run_id}`、`/failure_exploration/run`、`/branch_compare/run`、`/branch_conflict/resolve`、`/conflict/{id}`）、Conflict Package Return 與 Authority Handoff。驗收十四條見 issue #31。Formal Spec §9（各系統提交什麼、拿回什麼）、§13（衝突不由 SKYVAULT 裁決）、§17（SKYVAULT 可以模擬、建議、警示，不能做最終決定）。

開設時的測量：TAC ANGEL 與 STARTX 在同一個 tick 命令 red_001，scenario 契約直接拒絕（「red_001 has two scheduled actions」）—— 不是 conflict package；120 個 run（6 scenario × 20 seed）中 verdict risky / fail 有 113 個（94%），Phase 7 自己的 extreme_high_risk_optimization 旗標 34 個（28%）、兩個 sacrifice_* 旗標 25 個（21%）；單一 run 的 failure threshold 120 個 run 一次都沒達到，failure map 的 6 個變量中 4 個在某個等級崩潰。九個系統中 EIDEN-01、CYBERHOUND、星衞沒有對應的模型。

issue #31 第 6 節在寫程式之前列出了十五項決定。這份 ADR 記錄那十五項與開發中的十三項。**模擬行為不變**：沒有外部提交的 run 一步都不變；reference trace 與六個 output_hash 不變（常數測試）。

## 決定

### 1. 新套件 interface/

handoff.py（觸發與 package，純函式）、conflicts.py（提交窗口、衝突、分支、決定）、systems.py（九個 adapter）、api.py（外部路由）。API 掛在 world service 的同一個 app 上，共用 store、queue、worlds 與入口檢查。engine 與 batch 不 import interface（測試）。

### 2. 兩份新契約

external_submission（system、kind、scenario 名稱、content）與 authority_handoff（第 22、23 份）。只新增，schema 0.6。

### 3. 路徑

開發計劃的原文；run_id 是 world service 的 job_id，persistent world 的 id 也是它的 job_id。

### 4. 外部 action

`POST /action/submit {world_id, system, tick, actor_id, order}` 進入該 world 那個 tick 的提交窗口（proposal_id `<system>:<n>`）；world 推進到那個 tick 時，沒有衝突的 action 以 scheduled order 執行，event 的 system_id 是提交的系統。已經過去的 tick → 422、沒有的單位 → 404、已結束的 world → 409。

### 5. 衝突

同一個窗口內用 Phase 10 的 detect_conflicts。有衝突 → 那個 tick 一個 action 都不執行，world 停在前一個 tick（awaiting_decision），advance 回 409。

### 6. 分支模擬

每個相容集合與「都不採用」各一個分支；從 tick 0 以同一個 seed 重跑 scenario，加上已執行的外部 action 與該分支的 action —— 決定論就是 fork（engine 不能序列化）。每個分支 5 次，seed 從 world 的 seed 往上：第一次就是這個 world 的延續（測試：與實際繼續的 world 逐位元相同）。

### 7. conflict package

Phase 10 的 build_conflict_package，不選邊；`/conflict/{id}/package` 加上 conflict_id、world_id、tick、status。

### 8. 決定

`POST /branch_conflict/resolve {conflict_id, branch_id, decided_by}`：decided_by 必須是指定權威（NEXUS、SOVEREIGN）；SKYVAULT 或任何非權威 → 403。決定後採用該分支的 action、world 繼續；決定與決定者記錄在 conflict 與 job_events。

### 9. handoff 的四個觸發

high_risk_outcome = Phase 7 的 extreme_high_risk_optimization（28%，而不是 risky / fail 的 94%）；strategic_tradeoff = sacrifice_long_term_stability… 或 sacrifice_strategic_value…（21%）；conflicting_branches = conflict package 的 required_decision；failure_threshold_crossed = run 的 failure_causes 有「Failure threshold reached」，或 failure map 的 baseline 存活率低於門檻、或任一變量在 mild / moderate 就崩潰。每個觸發都有一場真實的 run 觸發、一場不觸發（測試）。

### 10. handoff package

開發計劃的七項（result_summary、branch_comparison、failure_map、required_decision、skyvault_position、may_recommend: true、may_execute_final_decision: false）加上 handoff_id（內容 hash）、triggers、decision_authority、status、decided_by、decision。may_recommend 與 may_execute_final_decision 在契約裡是 Literal：不可能是別的值。skyvault_position 只陳述事實與建議的下一步測試。

### 11. 每個 job 判斷 handoff

scenario_run、batch、failure_exploration 結束時算，存在 job summary；`GET /run/{id}` 帶 handoff；`POST /run/{id}/decision` 由權威決定（非權威 403、已決定 409、沒有 decision 文字 422、沒有 handoff 404）。

### 12. 九個 adapter

to_request(submission) → {system, supported, jobs, world_actions, gaps}；to_return(results, submission) → Spec §9 的返回欄。

```text
NEXUS       任務 → scenario_run / batch / failure_exploration；返回 result package、briefing（markdown，單一 run）、job 狀態與 handoff
STARTX      分支 → branch_compare；返回每個分支的後果、風險、資源壓力、評分與對「都不採用」的差
TAC ANGEL   行動 → 有 world_id 時進 world 的窗口，否則是一個 run 的 scheduled orders；返回自己命令的
            state-action-outcome（training.transitions，只取 system_id = TAC_ANGEL）、被拒的命令、單位結果、任務成敗
EIDEN-01    情報參數 → 對得到單位與能力的參數各一個分支（加上全部一起），data_provenance 記錄來源；
            其餘（沒有的單位、沒有的能力、世界參數）→ 缺口
AEROGRID    覆蓋設定 → 一個 run 的 coverage observation；返回覆蓋率、缺口、反應窗口；空域配置 → 缺口
SKYFOX      無人機 + 路線 → skyfox_adapter 控制那架無人機的 run；返回任務成功率、路線風險、被拒的移動
HADES       防禦單位 → hades_adapter 控制那些單位的 run；返回防禦有效性、反應時間、覆蓋缺口
CYBERHOUND  資訊環境 → 沒有模型：supported false、每個參數一個缺口，什麼都不跑
星衞        裝備 profile → 替換一個單位的 run 與原 scenario 的 run；返回物理可行性、戰術用途
```

### 13. 提交的形狀

external_submission；每個系統只能提交自己的 kind（TAC ANGEL 提交 actions、STARTX 提交 branches…），否則 422。scenario 只能是名稱（`../` 被契約擋下）。

### 14. 不選邊的守護

沒有任何程式路徑在沒有權威決定時採用分支：conflict 一直停在 awaiting_decision，SKYVAULT 與每個提交過 action 的系統都被拒（測試）。

### 15. 模擬不變

## 開發中的決定

### 16. Frozen Interface 的三個名字改了

issue 寫 `SubmissionWindow.close(tick) -> {accepted, conflict}` 與 `simulate_branches(...)`；實作是 `take(tick)` + `find_conflicts(base, proposals)`（取出與判斷分開，world 決定要執行還是開 conflict）與 `play_out(base, applied, proposals, profile, perspective, repeat_count, horizon)`（分支要從 world 的 seed 與已執行的 action 開始）。authority_handoff 多一個 authorities 參數。

### 17. JobRequest 多兩個欄位：entity_changes 與 data_provenance

EIDEN-01 與星衞要改單位的能力，而 job 只能以名稱指定 scenario。entity_changes `{entity_id: {name, entity_type, capabilities, state}}`：名稱與類型取代、capabilities 與 state 逐鍵合併；沒有的單位 → NotFound（只能改 SKYVAULT 有的，不能新增）；其他欄位（例如 position）被契約拒絕。data_provenance 寫進 scenario 的 data_provenance（Spec §11.3，Phase 1 定義後第一次有人填）。branch_compare 的分支也可以帶 entity_changes。只新增。

### 18. 多個 job 的提交

一個提交可以是好幾個 job（SKYFOX 3 個 seed、星衞 3 + 3）。全部先通過入口，才一起排入佇列 —— 第二個被拒時第一個標 failed，不會跑半個提交。提交本身寫進每個 job 的 summary（在 worker 看得到之前），`GET /submission/{id}`（id = 第一個 job）在全部結束後組回系統的返回：服務重啟後仍然組得回來。

### 19. 物理可行性只算能力的限制

整合時打開輸出：星衞的 EXO-1 是 `feasible: false`，理由是三次「Move target occupied」—— 另一個單位站在那裡，不是裝備做不到。改為只有能力所限的拒絕（超出移動範圍、射程、彈藥、無法通過的地形、資源不足）算不可行；情境性的拒絕另列。另加可選的 drills：指定 tick 的命令（例如「一回合走三格」），在裝備與原單位的 run 都執行。

### 20. 沒有格子可走的單位改為等待

`move_range: 0` 的裝備（固定砲塔）讓軍事 policy 的 advance 在 `min()` 空序列上崩潰。沒有選項時等待（intent cannot_move）。以前會崩潰的情況才走這條路：其他 run 一步都不變。

### 21. 平手時列出所有並列的分支（修正 Phase 10）

conflict package 的 decision_reason 原本在平手時寫第一個分支（ADR 010 的測試釘住「a tie names the first」）。整合時打開 handoff：「Highest win_rate: branch TAC_ANGEL:1 (0)」—— 兩個分支都是 0。這段文字在 Phase 12 交到權威手上，只寫一個就像在選。改為「tied between A, B」；ADR 010 不改，以本條取代那一點。

### 22. EIDEN-01 的敏感變量不設門檻

每個參數單獨一個分支，依 |Δ mean_score| 排序全部列出，不判斷「敏感 / 不敏感」—— 門檻沒有測量依據。

### 23. 反應時間與覆蓋缺口的定義

AEROGRID 的反應窗口：第一個進入覆蓋的敵人（tick）到第一次命中己方。HADES 的反應時間：HADES 觀測第一次看到威脅到第一個 hades_intercept；覆蓋缺口：打中己方、卻從未被 HADES 單位交戰的敵人。

### 24. 任務成敗經由 domain 的 hook

adapter 讀 `load_domain(...).mission_outcome`，不 import 軍事 pack（既有的分層測試擋下了第一版）。

### 25. 同步的執行路徑與輸出

`interface.api.run_submission` 在這個執行緒上規劃、執行、讀回（governance 仍然把關）；`scripts/run_external.py` 用它把九個系統的返回與一個衝突（package、handoff、NEXUS 決定後的紀錄 —— 腳本代 NEXUS 選名稱排序第一個分支）寫到 output/external/。

### 26. 「政策可加」的權威沒有做

§6 第 8 項寫權威「預設 NEXUS、SOVEREIGN；政策可加」。authority_handoff 與 open_conflict 收 authorities 參數，但 governance 政策沒有加欄位：那份契約是 Spec §15 的欄位，權威不屬於算力治理。留待需要時（已知限制）。

### 27. 預設的重複次數

SKYFOX、HADES、星衞、EIDEN-01 預設 3 次（seed 從 scenario 的 seed 往上），STARTX 的 fixture 5 次，衝突分支 5 次。提交可以自己指定 repeat_count。

### 28. runtime_version 升為 0.17.0

依 ADR 008 的慣例；UI 的 package.json 同步。

## 後果

```text
好處    九個系統各用自己的語言提交、拿回 §9 寫明的東西；沒有模型的系統得到缺口而不是假的模擬
        衝突的命令不再被契約擋掉：被標記、從同一段歷史分叉模擬、交回 conflict package，世界等權威決定
        需要決定的結果一律以 handoff 交出，SKYVAULT 自己（或任何非權威）決定一律 403
代價    world 停在衝突時，分支要從 tick 0 重跑（5 次 × 分支數）
        權威名單不能由政策擴充；EIDEN-01 的世界參數、AEROGRID 的空域、CYBERHOUND 都還沒有模型
        真正的外部系統連線不在此：adapter 定義格式，測試資料與替身代替
```
