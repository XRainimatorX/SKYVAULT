# Phase 10 回顧

Batch Simulation + Branch Comparison v1.0

這份文件檢討**流程**，不檢討人。所有問題都以「什麼樣的做法讓這件事得以發生」來描述 —— 目標是讓下一個階段不要重蹈，不是追究誰的責任。

寫完不再更新。

---

## 1. 摘要

Phase 10 交付了 batch runner、平行執行、pandas 彙整、三種變體、scheduled_actions、衝突偵測與 conflict package。沒有排程時模擬不變，三個步驟都沒有重工。

這一輪最重要的發現與 Phase 10 的功能無關：**Phase 9 的 failure map 在不同 process 裡會寫出不同的內容。**原因是 set 的迭代順序跟著字串雜湊走。它在 Phase 9 的所有測試與整合中都沒被看到，因為那些檢查都在同一個 process 裡比較。這次能抓到，只是因為整合時「清空 output/ 重跑之後看 git status」—— 一個原本用來確認輸出檔有寫出的步驟。

**核心教訓：「同一輸入得到同一輸出」必須跨 process 驗證；同一個 process 內的重跑證明不了它。**

---

## 2. 時間軸

```text
11-08   開設前測量：每次 run 20 ms、900 次 run、pandas 3 只在 3.11
11-08   開設：milestone #8、issue #24（15 項決定、衝突規則表、每步綠燈狀態）、batch 請求先 commit
11-08   步驟 A：child_version、variants、scheduled_actions
11-08   步驟 B：runner、aggregate、三份契約
        —— perspective 可能是 None；測試預期值寫錯一次 ——
11-08   步驟 C：conflicts、package、run_batch、報告
        —— 反向驗證：一個變異存活，補斷言 ——
11-08   整合：清空 output/ 重跑
        —— failure_map.json 有兩行對調：Phase 9 的雜湊順序問題 ——
```

---

## 3. 做得好的地方

### 衝突規則在寫程式前就是一張表

issue 第 6 節第 9 點把六種衝突寫成「條件 → 類型」的表，並寫下 reference 三道命令的預期結果（P1–P2 objective + priority + risk、P1–P3 location、兩個分支）。程式第一次跑出來就與預期相同。測試直接照表寫：每一列一個觸發、一個不觸發。

### 規則的測試資料在寫的時候就問「能不能區分」

Phase 9 回顧改法 3 第一次被當成事前設計用。例如 resource 的不觸發有兩個案例：「合起來付得起」與「單獨就付不起」—— 後者專門讓「單獨付得起」這個條件非它不可。「rule_set 的成本優先」用一個提案自己寫了 30 燃料、但世界只收 1 個零件的 repair 來測。結果：十個衝突規則的變異全部第一次就紅。

### 平行用 pool.map，不用 as_completed

結果順序由輸入決定，不由誰先跑完決定。平行與循序的逐欄比較在第一次就相同。

### 不裁決有一個具體的例子

reference 的兩個分支剛好一個勝率高、一個失敗少。這讓「SKYVAULT 不選」不只是一條規則，而是在完成報告裡能直接指出的理由。

---

## 4. 出了什麼問題

### 問題 1：Phase 9 的 failure map 不可重現

`_causes` 用 set 去重後計數；同分的 cause 依插入順序，插入順序依 set 的迭代順序，而那依 PYTHONHASHSEED。Phase 8 的 output_hash 只涵蓋 result package，failure map 在範圍之外；Phase 9 的測試與整合都在單一 process 內重跑，順序剛好一致。

### 問題 2：一個測試缺口

decision_reason 的同分規則有資料（兩個分支 mean_score 同分）卻沒有斷言。

### 問題 3：測試預期值寫錯一次

平均 hp 損失 69.05 寫成 69.0。憑記憶寫數字，而不是從輸出複製。

---

## 5. 根本原因

### 成因 1：決定性只在「最終 hash」的範圍內被驗證

Phase 8 建立了 output_hash，並證明它跨 run 不變。但之後新增的輸出（failure map、batch 的四個檔）都不經過 output_hash，也沒有人問「它們跨 process 也相同嗎」。測試在同一個 process 內比較兩次結果，雜湊種子相同，所以任何依賴 set 或 dict-of-set 順序的地方都看不出來。

### 成因 2：沒有斷言的資料不算測試

同分資料存在，所以覺得「同分被測過了」。但只有斷言能讓變異變紅。

---

## 6. 下一階段要改的事

### 改法 1：每個新的輸出檔都跨 hash seed 驗證一次

整合時，對每個新增或改動的輸出，用至少兩個不同的 PYTHONHASHSEED 各跑一次並比較位元組。這次已經這樣驗了 failure map 與 batch 的四個輸出；之後列進 issue 第 11 節的固定條目。

### 改法 2：輸出中的排序一律明確

任何寫進輸出的清單，如果來源是 set、Counter 或 dict 的迭代，排序鍵要明確寫出（例如次數遞減、再依名稱）。不依賴插入順序，除非插入順序本身是由輸入決定的。

### 改法 3：同分資料一定配同分斷言

為同分規則準備的資料，一定要有一個斷言直接檢查同分時的結果。

### 改法 4：預期值從輸出複製

測試的預期數字從實際執行的輸出複製，再判斷它是否合理；不憑記憶寫。

---

## 7. 沒有結論的一項

**衝突偵測不知道執行時的世界。**

偵測在模擬開始前進行，所以 resource conflict 用的是開場存量，location conflict 不知道目的地在那個 tick 是否已被佔據，timing conflict 不知道目標是否還活著。對 tick 1 的命令這沒有差別；對更晚的命令，偵測可能多報或漏報。

另一種做法是在 engine 執行到那個 tick 時才偵測 —— 但那時分支已經開始了，偵測的結果反過來決定要開哪些分支，等於要在模擬中途分叉。這需要 Phase 2 的 snapshot 與 rebuild 支援「從 tick N 開始的分支」，屬於更大的設計。留給 Phase 12（仲裁層）或之後需要時再決定。

---

## 8. 一句話

> Phase 10 讓 SKYVAULT 能把版本、參數與互相衝突的命令各跑 100 次並排比較，而且從不替人選；但這一輪最值得記下的是整合時偶然看見的兩行對調 —— Phase 9 的 failure map 在不同 process 裡不一樣，因為「可重現」只在同一個 process 內被驗證過。
