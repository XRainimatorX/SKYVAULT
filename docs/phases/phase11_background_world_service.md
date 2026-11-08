# Phase 11 — Background World Service v1.1

完成報告。這份文件是 Phase 11 結束時的凍結紀錄，寫完不再更新 —— 系統目前的樣子請看 [`../architecture.md`](../architecture.md)。

**狀態：功能完成，沒有已記錄未修的缺陷。**

---

## 1. 這個階段做什麼

Phase 11 開始前，SKYVAULT 只能由一個人手動跑 script；沒有任務、沒有排隊、沒有任何上限。

目標是開發計劃的原文：「把 SKYVAULT 從 script 變成後台服務」，加上 Resource & Compute Governance：「不能無限制燒算力、無限跑 scenario、無限開 branch」。規格依據是 [`../plan/phase11_background_world_service.md`](../plan/phase11_background_world_service.md) 與 Formal Spec §10、§15。

```text
Issue      #30 Phase_11_background_world_service（milestone #14 Phase 11 — Background World Service）
開設       失控任務、過大 batch、正常 run 的安靜期、成本基準、外部服務（Redis / RQ / PostgreSQL / Docker）；
           fixture 先 commit：data/service/governance.json、tests/fixtures/service/jobs.json
步驟 A     governance 與 job 契約、Governor、engine 的 begin / step / stop / finish、每個 run 的紀錄
步驟 B     store（SQLite / PostgreSQL）、queue（in-process / RQ）、jobs（四種）、入口檢查
步驟 C     API、persistent world、serve_world / world_worker、Dockerfile / compose、CI（redis / postgres service）
```

十七項決定與開發中的七項記錄於 [`../decisions/016_background_world_service.md`](../decisions/016_background_world_service.md)。

---

## 2. 這次執行發生了什麼

### 開設時的測量

```text
失控任務        兩方 hold、max_ticks 5000 → 5000 tick、30000 決定、0 個改變狀態的 event、19.5 秒；沒有東西停下它
過大 batch      repeat_count 1,000,000、workers 512 → 通過契約
正常 run        40 seed × 6 scenario：連續沒有狀態改變的 tick 最多 4（中位數 0–1）
成本基準        reference 46 決定 / 34 ms、urban 208 / 138 ms → 約 0.7 ms / 決定
觀測路徑        100 → 1000 → 5000 tick：0.15 → 2.1 → 19.5 s（超線性）
```

### 同一個失控任務，現在

```text
入口      max_ticks 5000 → 夾到 200（duration_clamped_from 5000）；估計 1200 決定、0.84 秒
執行      tick 11 被 no_new_state_change 停下（tick 2–11 重複 tick 1 的狀態），0.05 秒
結果      no_winner_stopped_early；partial result 通過契約、被保留；governance 紀錄 66 決定 / 67 events
```

### 模擬不變

```text
reference              RED_survived / 97、output 63090026e137…
六個 run 的 output_hash  與 Phase 6 相同（常數測試）
240 個正常 run          預設 governance 下沒有一個被停下；output_hash 與不受管時全部相同
```

### 驗收十一條

| # | 開發計劃原文 | 如何證明 |
|---|---|---|
| 1 | API 可以提交 scenario run | POST /api/jobs → 202；CI 對真正的 uvicorn 送出 |
| 2 | worker 可以背景執行 | in-process 執行緒與 RQ worker（另一個程序）；兩種 store 都在 CI 跑 |
| 3 | 可查詢 run status | GET /api/jobs/{id}：lifecycle 與 job_events；GET /api/status |
| 4 | 可下載 result package | GET /api/jobs/{id}/result；未完成 409、沒有保留 404 並說明原因 |
| 5 | 可重播歷史 run | replay job 重跑原請求：output_hash 相同、回傳 replay frames；原 job 變成 replayed |
| 6 | 可限制 compute budget | 預算 20 決定的 reference 在 tick 4 被停下（每 tick 6 決定）；入口拒絕估計超過預算的任務 |
| 7 | 每個 run 必須有 resource_compute_governance metadata | engine 一律寫入 run_metadata（script 跑的是 ungoverned） |
| 8 | background worker 不可無限制運行 | 失控任務在 tick 11 被停下；牆鐘時間上限；RQ 的 job_timeout |
| 9 | batch 必須受 max_batch_count 控制 | 900 萬 run 的 batch 被拒（422 batch_too_large）；45 run 的 batch 跑的正是被接受的 45 個 |
| 10 | persistent world 必須有 resource cap | tick cap 12：第三次推進停在 12；checkpoint cap 2：第二次推進後停止 |
| 11 | run 被中止要能輸出 partial result | auto-stop、cancel（等待中與執行中）、cap、提早 finish 都交出 partial result |

---

## 3. 交付了什麼

```text
src/skyvault/worldservice/
  governance.py   load_governance、estimate_run、scale、clamp_duration、admit、Rejected、fingerprint、Governor
  store.py        JobStore、SQLiteStore、PostgresStore、open_store
  queues.py       InProcessQueue、RQQueue、run_queued
  jobs.py         plan、new_job、execute_job、scenario_for、exploration_runs、NotFound
  worlds.py       PersistentWorld、WorldClosed
  api.py          create_world_service、in_process_queue
src/skyvault/contracts/governance.py、job.py   第 20、21 份契約；run_metadata.resource_compute_governance
src/skyvault/engine.py          begin / step / stop / finish、governor、governance_record
src/skyvault/evaluator.py       no_winner_stopped_early
src/skyvault/batch/run.py       planned_variants（run_batch 與估計共用）
src/skyvault/observation/       歷史不再每次複製
scripts/serve_world.py、scripts/world_worker.py、Dockerfile、docker-compose.yml
data/service/governance.json、tests/fixtures/service/jobs.json（開設時 commit）
pyproject.toml / ci.yml         rq、redis、psycopg；CI 的 redis / postgres service、World service 步驟
skyvault.__version__            0.16.0
```

---

## 4. 這一輪發現的問題

### batch 的估計少算了三分之一

第一版用 build_variants 數 batch 的 run：reference batch 估 30、實際跑 45 —— 衝突分支（Phase 10）沒有算進去，max_batch_count 可以被繞過。是第一次把 fixture 的每個 job 跑完、印出「估計 / 實際」時看到的。修正：抽出 planned_variants，估計與 run_batch 用同一個函式（ADR 016 第 19 點）。failure exploration 的估計也以實際 run 數校正（78 → 76）。

### 停下的 run 被叫做「跑到時限」

no_winner_duration_limit 是 evaluator 對「不只一方存活」的唯一說法；被 governance 停下的 run 也這樣說。

### 我自己的 conftest 讓 14 個軍事測試出錯

worldservice 的 fixture 第一版放在 conftest.py，測試檔又 `from conftest import ...`。軍事測試在函式內 `from conftest import spec`，拿到的是最後註冊的 conftest —— 我的。單獨跑 worldservice 全綠，全套 14 個錯誤（ADR 016 第 23 點）。

### 三個斜線的 SQLite 路徑在 repo 裡建了資料夾

`sqlite:///tmp/service.sqlite` 依 SQLAlchemy 的慣例是相對路徑；CI 步驟與我的探測都寫成三個斜線，repo 裡多了 tmp/ 與 var/。在 commit 前的 git status 看到；CI 改成四個斜線，加了慣例的測試。

### 背景程序讓步驟卡住

CI 步驟的兩個 uvicorn 以 `&` 放到背景，但繼承了步驟的輸出；本機重現時整個管線不會結束。改成各自寫 log 檔。

---

## 5. 品質狀態

| 項目 | 結果 |
|---|---|
| pytest | 1023 passed（有 Redis / PostgreSQL 時；沒有時 974 passed、49 skipped）（Phase 6 為 881） |
| Python 3.10 venv | 1023 passed |
| 全專案覆蓋率 | 99% |
| ruff / black / mypy / bandit | 通過（mypy 118 個檔案） |
| 測試讀 `output/` | 0 處 |
| exporter 程式碼變動 | 0 行 |

### 測試分布

```text
tests/worldservice/test_governance.py   35   政策與壞政策；估計、夾、入口的每種拒絕；Governor 的七種原因（觸發與不觸發）；
                                             五種真實 run 證明門檻；受管 = 不受管；每個 run 都有紀錄；begin / step / finish
tests/worldservice/test_jobs.py         47   store（兩種）；plan 的每種 job 與拒絕、路徑穿越；執行四種 job、partial、失敗、
                                             取消（等待中 / 執行中）；in-process queue 的優先序 / FIFO / 平行上限 / 取消；RQ
tests/worldservice/test_api.py          60   提交到下載、409 / 404 / 422 / 429；取消與重播；status 的模式與 health；
                                             persistent world 的推進、checkpoint、兩種 cap、finish、delete、併發；
                                             worker 腳本；compose；分層
既有測試                                881   匯出契約清單加兩份；store 參數化的測試在 SQLite 與 PostgreSQL 各跑一次
```

### 反向驗證過的測試（21 個變異全部紅）

```text
no_new_state_change / loop / budget 的門檻差一                 → 紅
engine 不問 governor / 有 governor 仍寫 ungoverned              → 紅
入口不擋 max_batch_count / 不夾時限                              → 紅（兩個第一次 NO MATCH，以實際程式碼重跑）
planned_variants 不算分支 / exploration 的 alternatives 加 branch → 紅
partial_result_export 被忽略 / 等待中取消不擋 / governor 不讀 store 的取消 → 紅（一個 NO MATCH 後重跑）
queue 不看優先序 / 只有一個 worker                               → 紅
world 的 checkpoint cap 拿掉 / max_ticks 不加一 / advance 不上鎖   → 紅
API 佇列滿回 422 / store 不 upsert / evaluator 不分 auto_stop / failure ratio 拿掉 → 紅
```

---

## 6. 已知限制

| 項目 | 留待 | 原因 |
|---|---|---|
| persistent world 不能跨程序恢復 | 需要時 | engine 不能序列化；checkpoint 與結果留在 store |
| batch / exploration 內的每個 run 不受 auto-stop | 需要時 | run_batch 在 process pool 裡建 engine |
| 每決定秒數是常數 | 有更多測量時 | 0.7 ms 來自 reference 與 urban |
| Docker 只做靜態驗證 | 有 daemon 的環境 | 此環境 daemon 不在；`docker compose config` 在 CI 驗證 |
| 同步的外部 client 逾時後執行緒仍在跑（Phase 6） | — | Python 不能終止執行緒 |
| `/api/status` 的 health 規則很簡單 | 需要時 | 最近 10 個結束的 job 一半失敗 → degraded |

---

## 7. 驗證

```bash
python3 scripts/run_tactical_reference.py   # RED_survived / 97；output 63090026e137
python3 scripts/serve_world.py              # http://127.0.0.1:8100/api/docs
python3 -m pytest tests/ -q                 # 974 passed、49 skipped（設定 SKYVAULT_TEST_REDIS / _POSTGRES 時 1023 passed）
```

---

## 8. 一句話總結

> Phase 11 讓 SKYVAULT 成為後台的世界服務：任務從 API 進來、排隊、在 worker 上跑、可查可下載可重播 —— 開設時一個什麼都不做的任務跑了五千個 tick，現在它在第十一個 tick 被停下並交出結果；一個九百萬次的 batch 在門口就被擋下。
