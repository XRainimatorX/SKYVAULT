# 016 — Background World Service 與 Resource & Compute Governance

狀態：已採納
日期：2026-11-08
階段：Phase 11 — Background World Service v1.1

## 背景

開發計劃 Phase 11：把 SKYVAULT 從手動 script 變成後台服務 —— standby、triggered scenario、persistent world、batch、monitoring、replay、failure exploration 七種模式 —— 並加上 Resource & Compute Governance（Formal Spec §15）：run priority、compute budget、max scenario duration、max parallel runs、max batch count、estimated cost、auto-stop、queue policy、persistent world resource cap、partial result export。技術：FastAPI、Celery / RQ / Dramatiq、Redis、PostgreSQL、Docker、worker、job queue、scheduler、health monitoring、resource limiter、checkpointing。驗收十一條見 issue #30。

開設時的測量：一個兩方都 hold 的任務跑完 5000 tick（30000 個決定、0 個改變狀態的 event、19.5 秒），沒有任何東西停下它；一個 1,000,000 次 repeat、512 workers 的 batch 通過契約。正常 run（40 seed × 6 scenario）連續沒有狀態改變的 tick 最多 4。Redis、RQ、PostgreSQL、psycopg 都能在此安裝並往返；Docker daemon 不在。

issue #30 第 6 節在寫程式之前列出了十七項決定。這份 ADR 記錄那十七項與開發中的七項。**模擬行為不變**：沒有 governor 的 run 一步都不變；240 個正常 run 在預設 governance 下的 output_hash 與不受管時完全相同。

## 決定

### 1. 新套件 worldservice/

governance、store、queues、jobs、worlds、api。Phase 17 的 service/（唯讀 UI 後端）不動；engine 不 import worldservice（測試）。

### 2. 兩份新契約

resource_compute_governance（政策）與 job（請求 + 紀錄，Spec §10 的 task_intake、world_instance、lifecycle），第 20、21 份；run_metadata 多一個 resource_compute_governance 欄位。只新增，schema 0.6。

### 3. governance 的欄位

§15 的十項；預設值在 data/service/governance.json，依開設測量訂定（最長正常 run 25 tick / 208 決定 → 預算 5000 決定、200 tick、60 秒；reference batch 600、failure exploration 760 → max_batch_count 1000；安靜期最多 4 → no_new_state_change 10）。

### 4. 每個 run 的紀錄

engine 一律寫 reproducibility.run_metadata.resource_compute_governance：policy_id、限制、usage（runs、ticks、decisions、events、runtime_seconds）、estimated_cost、stopped、stop_reason、partial、duration_clamped_from。沒有 governor 是 "ungoverned"。run_metadata 不進 output_hash。

### 5. auto-stop

engine 每個 tick 結束時問 governor（在「本來就會結束」的檢查之後）：cancelled、max_runtime_exceeded、budget_exceeded、resource_cap_reached、failure_threshold_reached、no_new_state_change（單位與資源的指紋連續 N tick 相同）、infinite_loop_detected（同一個指紋不連續地第 k 次出現）。每一種都有一場真實的 run 證明它會觸發（測試）。

### 6. partial result

被停下的 run 照常結束（SCENARIO_END、評估），termination_reason "auto_stop:<原因>"，package 通過契約；partial_result_export false 時只留紀錄。

### 7. max_scenario_duration 夾而不拒

入口把 max_ticks 夾到上限並記錄原本的值。開設時的失控任務（5000 tick）因此被夾到 200，再被 no_new_state_change 在 tick 11 停下。

### 8. 入口檢查

estimated_cost：單位數 × tick 個決定、每個決定 0.7 ms（開設測量）；batch 與 failure exploration 乘上 run 數。run 數 > max_batch_count、每個 run 的估計超過預算、佇列滿 → 拒絕並說明原因。

### 9. queue

InProcessQueue（執行緒、max_parallel_runs 個、critical > high > normal > low、同級 FIFO）與 RQQueue（每個優先序一個 RQ queue；worker 依序取；RQ 的 job_timeout 是 max_runtime_seconds 的兩倍，作為 governor 之後的第二道限制）。

### 10. store

SQLiteStore（預設、標準函式庫）與 PostgresStore（psycopg），同一套 SQL；以 spec 字串命名（sqlite:///相對、sqlite:////絕對、sqlite://、postgresql://），讓另一個程序的 worker 打開同一個 store。

### 11. persistent world

engine 拆成 begin / step / stop / finish（run() = 三者相加，reference trace 與六個 output_hash 把關）。world 留在 API 程序的記憶體，advance(n) 推進後存 checkpoint（snapshot、tick、決定數、event 數）；tick 與 event 的 cap 由 governor 檢查，checkpoint 數的 cap 在 world 裡；碰到 cap → resource_cap_reached 與 partial result。engine 不能序列化 → 程序重啟後不能恢復。

### 12. job 種類

scenario_run、batch、failure_exploration、replay（重跑原 job 的請求、比對 output_hash、回傳 replay frames）、persistent_world。scenario、batch、profile 只能以名稱指定，解析後必須在 data/ 底下。

### 13. lifecycle

Spec §10 的狀態：job 用 created / running / completed / failed / replayed；persistent world 另用 initialized / paused / deleted。

### 14. API

POST /api/jobs、GET /api/jobs、GET /api/jobs/{id}（含 job_events）、GET /api/jobs/{id}/result、POST /api/jobs/{id}/cancel、POST /api/jobs/{id}/replay、POST /api/worlds、POST /api/worlds/{id}/advance、GET /api/worlds/{id}、GET /api/worlds/{id}/checkpoints、POST /api/worlds/{id}/finish、DELETE /api/worlds/{id}、GET /api/status、GET /api/health。404 沒有的東西、422 格式錯誤或 governance 拒絕、429 佇列滿、409 尚未完成或不能取消。

### 15. 七種模式

service_status.mode 依執行中的任務：failure_exploration > batch > persistent > running，都沒有是 standby；monitoring 是 /api/status 與 job_events 本身；replay 是 replay job。health：最近 10 個結束的 job 有一半以上失敗 → degraded。

### 16. 觀測路徑的成本

engine 不再每個決定複製整份 tick 歷史，observe 直接索引 tick。hold-only 從 1000 → 2000 tick 的時間比由 2.6 倍降為 2.1 倍；結果逐位元相同。

### 17. 模擬不變

## 開發中的決定

### 18. 被 governance 停下的 run 叫 no_winner_stopped_early

第一版沿用 no_winner_duration_limit —— 但它沒有跑到時限。evaluator 對 termination_reason 以 auto_stop: 開頭的 run 給 no_winner_stopped_early；其他 run 不受影響。

### 19. batch 的 run 數與 run_batch 用同一個函式算

第一版的估計用 build_variants：reference batch 估 30 run（5 repeat），實際跑 45 —— 衝突分支沒有算進去，max_batch_count 可以被繞過。抽出 batch.run.planned_variants，run_batch 與估計都用它。

### 20. failure exploration 的 run 數

alternatives 只有 sweep、沒有 branch：76 而不是第一版算的 78（以實際 run 數驗證）。變量不適用時仍是上限。

### 21. usage 多 runs，ticks / decisions 可為 null

batch 與 exploration 的 job 數 run 與 event，看不到每個 run 的 tick 與決定。

### 22. 取消經由 store

waiting 的 job 從 queue 拿掉；running 的 job 在 store 標 cancel_requested，governor 每個 tick 讀它 —— in-process 與另一個程序的 RQ worker 用同一條路。

### 23. 測試的 fixture 不放在 conftest.py

軍事測試在測試函式內 `from conftest import spec`；第二個 conftest 模組會蓋掉它（單檔綠、全套 14 個錯誤）。worldservice 的 fixture 放在 service_fixtures.py，以 pytest_plugins 載入；資料放在 service_data.py。

### 24. runtime_version 升為 0.16.0

依 ADR 008 的慣例；UI 的 package.json 同步。

## 後果

```text
好處    任務從 API 進來、排隊、在 worker 上跑、可查可下載可重播；兩種 queue × 兩種 store 都在 CI 跑
        失控的任務會被停下並交出 partial result；過大的 batch 在入口被拒；每個 run 都說得出它用了什麼
        engine 可以一步一步推進：persistent world 與之後的外部系統互動都能用
代價    persistent world 不能跨程序恢復
        batch 與 exploration 內的每個 run 不受 auto-stop 約束（受 max_batch_count 與 scenario 時限約束）
        estimated_cost 的每決定秒數是一個常數；Docker 只做靜態驗證（daemon 不在）
```
