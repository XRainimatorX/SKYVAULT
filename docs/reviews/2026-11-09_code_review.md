# 2026-11-09 Code review：world service 的十項修正

roadmap 二十一個 Phase 完成後，對 `review_branch`（PR #18，main..6f44797）做了一次 high 等級的 code review。
十項發現每一項都先讀程式碼確認、先寫一個會失敗的測試重現，再修。寫完不再更新。

**結論：模擬核心沒有問題；十項都在 Phase 11 / 12 / 19 的 world service —— 並行、治理與授權。**
模擬行為不變：reference RED_survived / 97 events / output 63090026e137，六個 output_hash 與 v2 驗收（ACCEPTED）不變。

---

## 1. 十項發現

| # | 位置 | 問題 | 修法 | 測試 |
|---|---|---|---|---|
| 1 | `worldservice/jobs.py` `new_job` | 先 `next_job_id()` 再 `create_job()`：兩個同時的提交拿到同一個 job_id → 第二個 500、job 遺失 | `create_job` 用既有的 `_insert_next` 在 insert 時取號（重複鍵重試）並回傳存好的 job；`next_job_id` 移除 | 24 個執行緒同時建立 job，編號 1–24 各一 |
| 2 | `worldservice/store.py` `update_job` / `update_conflict` | 讀-改-寫整份 JSON 不是原子的：worker 與 cancel 同時寫，後寫的蓋掉先寫的（含 cancel 旗標） | 每個 store 一個 `_transaction()`：SQLite 整段持有連線的鎖（改 RLock），PostgreSQL 一個連線、一個 transaction、`SELECT … FOR UPDATE` | 40 個執行緒同時寫欄位與 summary，全部保留 |
| 3 | `worldservice/jobs.py` 各 `_finish` | 結束時以開始時讀到的 summary 重建 summary，丟掉中途寫入的 cancel 旗標（與 2 同一個根因） | `update_job(summary_fields=…)` 與 `merge_summary(…)`：在同一個 transaction 裡合併到當下的 summary；所有 `summary={**job["summary"], …}` 改用它 | 合併後再以 summary_fields 結束，cancel_requested 仍在 |
| 4 | `worldservice/governance.py` | persistent world 的 `max_runtime_seconds` 從建立時算起：閒置 61 秒後，下一個 tick 就被 max_runtime_exceeded 停下 | Governor 只累計 stepping 的時間：`start()` 歸零、`pause()` / `resume()`；world 在 begin 後與每次 advance 之後暫停計時 | 時鐘注入的單元測試；API 測試：上限 0.5 秒、閒置 0.8 秒後仍能 advance |
| 5 | `worldservice/api.py` cancel | persistent world 的 cancel 回 200 但沒有人讀旗標，之後 advance 照常 | cancel 遇到 live world → `world.finish()`（stop "cancelled"，保留 partial result） | cancel 後 lifecycle completed、advance 被拒、結果停在當下 tick |
| 6 | `worldservice/jobs.py` `_governor` | cancel_check 每個 tick 讀整份 job JSON（PostgreSQL 每 tick 開一次連線） | 最多每 0.5 秒問一次 store；問到 cancel 後不再問 | 時鐘注入：七次檢查只讀 store 兩次 |
| 7 | `interface/api.py` `submit_scenario` | world actions 先放進 window，之後 job 被拒或第二個 action 被拒，前面的 action 仍留在 window | 順序：查 world → admit 全部 job（不入列）→ `PersistentWorld.submit_all`（全部或一個都不）→ 入列；任一步被拒，已 admit 的 job 標 failed | 第二個 actor 不存在、第三個 action 格式錯、job 被拒、world action 被拒四種 |
| 8 | `interface/api.py` `queued_together` | 同一份提交的每個 job 都以同一個 `queue.depth()` admit：5000 個 seeded run 全部通過 max_queue_length 100 | `admit(request, ahead)`：queue_length = depth + 已 admit 數；整份提交的 runs 總和 ≤ max_batch_count，否則 422 batch_too_large | max_queue_length 3 擋下 5 個 run；max_batch_count 4 擋下 5、放行 4 |
| 9 | `editions/service.py` `gate_for` | 只有 request 帶 scenario 才檢查 domain：batch 與 replay 繞過授權 | batch 依其 base scenario 的 domain；replay 依它重播的那個 request（world service 的 admit） | 只授權 city 的版本：military batch 403、city batch 202；military run 的 replay 403 |
| 10 | `editions/service.py` `/api/products/{id}`；`worldservice/api.py` `/api/status` | 產品在請求執行緒同步跑、沒有上限；status 未持鎖迭代 worlds dict | 產品：`BoundedSemaphore(max_parallel_runs)`，忙碌時 429 queue_full；worlds 的每一次讀取（兩個 api 檔）都持 `worlds_lock`（放在 app.state） | 第二個同時的產品 429、結束後恢復；測試持鎖時 status 會等 |

---

## 2. 反向驗證

每個修法拿掉後對應測試要紅。第一輪三個存活 —— 補測試後全部紅：

```text
governor 暫停時讀 runtime()                沒有測試在暫停時讀 → 補 runtime() == 1.0 的斷言
submit_all 的 withdraw                     不存在的 actor 在寫入前就被擋 → 補「第三個 action 格式錯」
world action 被拒時把已 admit 的 job 標 failed   只測了 job 被拒 → 補「world action 被拒」
```

---

## 3. 根本原因

```text
並行      store 的每個方法各自是一條 SQL，組合起來的「讀-改-寫」與「取號-寫入」沒有 transaction（#1–#3）；
          Phase 15 修 job_events 時只修了那一張表
治理      Governor 假設一個 run 從頭跑到尾；persistent world 是 Phase 11 才加入的另一種節奏（#4、#5）
提交      「全部或全不」只在 job 之間做到，沒有延伸到 world actions 與整份提交的上限（#7、#8）
授權      gate 以 request 的形狀判斷，而不是以「這個 job 會跑哪個 domain」判斷（#9）
```

---

## 4. 驗證

```text
pytest      1546 passed（Redis + PostgreSQL；之前 1516）、覆蓋率 99.21%；ruff / black / mypy / bandit 通過
不變量      reference RED_survived / 97 / 63090026e137；v2 驗收 ACCEPTED
```
