# Phase 18 回顧

Data / AI / Training Pipeline v1.8

這份文件檢討**流程**，不檢討人。所有問題都以「什麼樣的做法讓這件事得以發生」來描述 —— 目標是讓下一個階段不要重蹈，不是追究誰的責任。

寫完不再更新。

---

## 1. 摘要

Phase 18 交付了通用的 transition 資料、六個 anti-gaming 標籤、三個集合的過濾、STARTX 的分支評估、JSONL / Parquet、registry 與 RAG index。模擬不變，沒有重工。

這一輪有兩件事值得記下。第一，**開設時的測量再次在寫程式之前改變了設計**，而且這次抓到的是上一個 Phase 的缺陷：軍事 pack 讓每一場都像在刷分。第二，**這個 Phase 是在使用者問「為什麼停了」之後才開始的**：Phase 13 收尾後我結束了那一輪，沒有任何阻塞。

**核心教訓：一個 Phase 的收尾不是終點，下一個 Phase 的開設才是；而「過濾器正確」不代表「過濾的結果正確」—— 上游資料的偏差要在過濾之前量出來。**

---

## 2. 時間軸

```text
11-08   Phase 13 收尾後停下（沒有阻塞）；使用者詢問；計畫寫明「最後一步是開設下一個 Phase」
11-08   開設前測量：pyarrow（scratch venv）；100 個 run 的分布
        —— 軍事 run 100% 判為 risk spike：Phase 13 的 risk 標記錯誤，先修正 ——
        —— triggered 未 flagged 為 0：risky 的定義改用 Phase 7 的判斷 ——
11-08   開設：milestone #11、issue #27（18 項決定）、sources.json 先 commit（已用現有系統跑過）
11-08   A + B + C：transitions、labels、filter、branches、export、registry、RAG、pipeline、CI
        —— 一個佔位、變異腳本的輸出被打亂、一個 NO MATCH ——
11-08   整合：管線結果與開設時的測量完全一致（41 / 20 / 39；2 / 6 / 92）
```

---

## 3. 做得好的地方

### 先量分布再寫 filter

如果先寫 filter，所有測試都會綠 —— filter 的邏輯是對的。問題在輸入：軍事 run 的 risk 標記被膨脹，所以每一場都是「刷分」。只有在寫程式之前看真實的分布，才會問「為什麼 100%？」。

### fixture 先跑過才 commit

sources.json commit 前已經用現有系統跑過（Phase 13 回顧改法 4），描述裡直接寫了量到的分布。管線完成後的結果與它逐項相同，等於一個免費的端到端檢查。

### 輸出在三種輸入上都跑過

transition 的主要測試對 reference、軍事、惡化版本三種 run 參數化（Phase 13 回顧改法 1）；observation 的兩種路徑都測到。

### 守護測試由兩處把關

「rejected 不進 clean」在 pytest 與 CI 的端到端步驟各檢查一次，而且反向驗證過。

---

## 4. 出了什麼問題

### 問題 1：Phase 13 收尾後停了下來

使用者的指示是「做完不要停，繼續下一個 Phase」。三個允許停下的條件一個都沒發生，我卻用一則總結結束了那一輪。

### 問題 2：Phase 13 的 risk 標記與 core 不一致

軍事 attack 的 evaluation_relevance 是新寫的，沒有對照 core 的 attack。Phase 13 的測試只看模擬行為，沒有看評估的輸入。

### 問題 3：一個佔位寫進了程式

`x if False else 0.0` —— 寫的時候留了一個「之後再接」的位置。在第一次執行前看到，但它本不該被寫下。

### 問題 4：變異腳本的輸出格式

多行的 pattern 讓結果跑到下一行，讀不出哪個變異對應哪個結果。

---

## 5. 根本原因

### 成因 1：收尾的清單沒有「下一步」

每個 Phase 的收尾清單到「更新 PR 描述」為止。清單結束，就容易把它當成整件工作的結束。

### 成因 2：pack 照著自己的需要寫，沒有照 core 的慣例寫

軍事 handler 從 core handler 改寫，但只保留了 data 的鍵（因為 exporter 需要），沒有保留 evaluation_relevance（因為沒有東西「需要」它 —— 直到 Phase 18）。

### 成因 3：佔位比待辦更容易被忘記

一個能執行的佔位不會讓任何東西失敗。

---

## 6. 下一階段要改的事

### 改法 1：收尾清單的最後一項是「開設下一個 Phase」

已寫進計畫。PR 更新後，同一輪就開始下一個 Phase 的測量。

### 改法 2：pack 改寫 core 的元件時，逐欄對照

handler 的每個輸出欄位（data、evaluation_relevance、tags）都與 core 對照；刻意的差異寫進 ADR，其餘照抄。之後的 domain pack（Phase 14、15）適用。

### 改法 3：不寫能執行的佔位

不知道值的時候寫 `raise NotImplementedError`，讓它在第一次執行時失敗。

### 改法 4：變異腳本的每一行自成一筆

已修正：pattern 壓成一行、結果與 pattern 在同一行。

---

## 7. 沒有結論的一項

**什麼樣的 run 該進主訓練集。**

目前 clean 包含真失敗（verdict fail 但沒有刷分）。對模仿學習，失敗的示範可能有害；對強化學習或離線評估，失敗是必要的負例。SKYVAULT 不知道下游要怎麼用，所以用 success_type 標明、不替下游決定。如果 TAC ANGEL 的訓練方式確定了，可能需要第四個集合（例如 demonstration：只有 genuine_success），或讓 sources 檔指定過濾規則。留給 Phase 12（外部系統接口）或 TAC ANGEL 的需求出現時決定。

---

## 8. 一句話

> Phase 18 讓 SKYVAULT 的資料在交給 AI 之前先分辨真成功與假成功，而它最重要的一步發生在寫程式之前：量出軍事 run「全部都是刷分」，才發現問題不在過濾器，而在上一個 Phase 的資料。
