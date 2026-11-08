# Phase 11 回顧

Background World Service v1.1

這份文件檢討**流程**，不檢討人。所有問題都以「什麼樣的做法讓這件事得以發生」來描述 —— 目標是讓下一個階段不要重蹈，不是追究誰的責任。

寫完不再更新。

---

## 1. 摘要

Phase 11 交付了 governance、兩種 store、兩種 queue、四種 job、persistent world、HTTP API、worker、Docker 與 CI 的真實服務。模擬不變，沒有重工。中途 worker 重啟過一次（plan mode），計畫照舊繼續。

這一輪最值得記下的是：**估計與實際由兩段程式碼各自算的時候，限制就能被繞過。** batch 的估計少算了衝突分支，max_batch_count 擋的是 30、放進來的是 45。

**核心教訓：一個「限制」只有在它檢查的數字與真正發生的事由同一個函式算出來時才算數；寫完限制，先把每個 fixture 的「估計 / 實際」並排印出來。**

---

## 2. 時間軸

```text
11-08   Phase 6 收尾後開設 Phase 11：worker 重啟（plan mode）→ 計畫更新、核准、繼續
11-08   測量：失控任務 5000 tick 沒人擋、百萬 batch 過契約、正常安靜期 ≤ 4、Redis / RQ / PostgreSQL 往返、Docker daemon 不在
11-08   milestone #14、fixture 先 commit、issue #30（17 項決定）
11-08   A：契約、Governor、engine 拆成 begin / step / finish；失控任務停在 tick 11；240 個正常 run 沒有一個被停
11-08   B：store、queue、jobs —— 「估計 / 實際」並排：batch 30 / 45、exploration 78 / 76 → planned_variants
11-08   C：API、persistent world、腳本、Docker、CI —— conftest 撞名、三個斜線、背景程序卡住步驟
11-08   整合：21 個變異全部紅（三個 NO MATCH 重跑）
```

---

## 3. 做得好的地方

### 失控任務在開設時就寫成 fixture

Phase 6 回顧改法 1：先寫一個違反規則的任務。它同時是驗收 8 的測試、auto-stop 門檻的依據，也揭露了觀測路徑的超線性成本（每個決定複製整份歷史）—— 這個成本在 run 只有 25 tick 時永遠看不到。

### 門檻兩面都用真實資料驗證

每個 auto-stop 都有一場真實的 run 證明它會觸發（Phase 7 的教訓）；反過來，240 個正常 run 在預設 governance 下沒有一個被停下、output_hash 全部不變。門檻不只會觸發，也不會誤觸發。

### 真正的服務，而不只是替身

Redis、RQ、PostgreSQL 在此裝得起來，就用真的：兩種 store × 兩種 queue 同一組測試，CI 以 service container 跑；Docker daemon 不在，就只承諾靜態驗證並寫明。

---

## 4. 出了什麼問題

### 問題 1：batch 的估計少算了衝突分支

估計呼叫 build_variants；run_batch 在 build_variants 之後另外加上分支。兩段程式碼各自決定「一個 batch 有幾個 run」。

### 問題 2：evaluator 只有一種「沒有贏家」

被停下的 run 被標成 no_winner_duration_limit。evaluator 寫的時候只有兩種結束方式。

### 問題 3：conftest 的名字是全域的

worldservice 的測試 import 自己的 conftest，蓋掉了軍事測試在執行期 import 的 conftest。

### 問題 4：路徑慣例與背景程序

三個斜線的 SQLite 路徑是相對的；背景的 uvicorn 繼承了步驟的輸出。兩個都是在本機完整重現 CI 步驟時才看到。

---

## 5. 根本原因

### 成因 1：限制與被限制的東西沒有共用來源

入口的檢查是「之後」才寫的，於是重新推導了一次 batch 的規模，而不是問 run_batch。

### 成因 2：新的結束方式沒有回頭檢查所有讀 termination 的地方

auto-stop 加了一種 termination_reason，但 evaluator 依「剩幾方」決定結果名稱，從不看 termination_reason。

### 成因 3：測試的輔助模組沿用了別人的慣例

`from conftest import` 在軍事測試裡可行，是因為那時只有一個這樣的 conftest。

### 成因 4：CI 步驟先寫、後在本機跑

步驟是照著「應該會動」寫的；在本機逐字執行時兩個問題都立刻出現。

---

## 6. 下一階段要改的事

### 改法 1：限制必須呼叫被限制的程式碼來計數

任何「最多 N 個」的檢查，計數用的函式要與實際執行用的是同一個；測試把每個 fixture 的估計與實際並排比較。Phase 12 的外部請求大小、Phase 14 以後的 domain 規模都適用。

### 改法 2：新增一種狀態值時，grep 所有讀它的地方

新增 termination_reason、lifecycle、status 等值時，先 grep 讀取者，逐一決定它要不要分辨新值。

### 改法 3：測試輔助模組用自己的名字

fixture 放在專屬名稱的模組，以 pytest_plugins 載入；不新增 conftest.py 到已經有 `from conftest import` 慣例的 repo。

### 改法 4：CI 步驟在本機逐字執行過才推送

把步驟的 run 區塊抽出來在本機跑（含背景程序、路徑），再推。

---

## 7. 沒有結論的一項

**batch 裡的每個 run 要不要受 auto-stop 約束。**

現在 batch 與 failure exploration 受 max_batch_count 與 scenario 時限約束，但內部的每個 run 不經過 Governor —— run_batch 在 process pool 裡建 engine。一個「會失控」的變體跑一百次，就是一百次跑到時限。把 Governor 傳進 process pool 需要它可序列化（policy 是純資料，可以），而 batch 的統計要決定被停下的 run 怎麼算（失敗？排除？）。留給 Phase 12（外部系統的大量提交）或真的出現失控變體時決定。

---

## 8. 一句話

> Phase 11 讓 SKYVAULT 成為受預算約束的後台服務，而它最該記住的一課是：max_batch_count 擋的是估計的 30 個 run，放進來的卻是 45 個 —— 限制必須和它所限制的東西用同一個函式計數。
