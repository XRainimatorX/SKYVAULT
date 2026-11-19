# Phase 6 回顧

Actor Policy / External Agent Layer v0.6

這份文件檢討**流程**，不檢討人。所有問題都以「什麼樣的做法讓這件事得以發生」來描述 —— 目標是讓下一個階段不要重蹈，不是追究誰的責任。

寫完不再更新。

---

## 1. 摘要

Phase 6 交付了唯讀世界、order 契約、十種 actor、ActionQueue 與 participants。模擬不變，沒有重工。

這一輪值得記下的是兩件事。第一，**開設時寫一個「壞人」再寫程式**：作弊 policy 的測量直接定義了驗收 3 的測試，也決定了這個 Phase 的第一件事。第二，**唯讀世界的第一版慢了三倍**，而最後一段差距藏在 profiler 看不到的地方。

**核心教訓：要證明一條規則被守住，先寫一個違反它的程式，看它今天能不能得逞；要量效能，用牆鐘時間比較兩個版本，不要只看 profiler 的分布。**

---

## 2. 時間軸

```text
11-08   Phase 5 收尾的同一輪開設 Phase 6：作弊 policy 的測量、world policy 的讀取清單、複製的成本
11-08   milestone #13、fixture 先 commit（scripted 已當 scheduled_actions 跑過：三個 move 接受、一個攻擊被拒）
11-08   issue #29（15 項決定）
11-08   A：WorldView —— 第一版 urban 360 ms（原本 104 ms）→ 四輪修正 → 129 ms
11-08   B + C：actor、佇列、adapter、participants；SKYFOX 的佔位 → 己方單位帶 state
11-08   整合：讀 participants run 的逐單位統計 → HADES 機槍手整場不動 → 改替身
```

---

## 3. 做得好的地方

### 先寫一個違反規則的程式

「actor 只能透過 Action 提交意圖」在 Phase 5 時看起來已經成立：policy 回傳 Action、engine 結算。寫一個直接改世界的 policy，4 筆 event 就「贏」了。沒有這個測量，這個 Phase 會只做 adapter 與 participants，而驗收 3 會被一個只檢查回傳型別的測試「證明」。

### 不變性用常數釘住

唯讀世界改了每一個 world policy 讀取世界的方式。六個 run 的 output_hash 前 16 碼寫進測試；四輪效能修正每一輪都比對，任何一輪改變了行為都會立刻看到。

### 讀 run 的逐單位統計，而不只是結果

participants_squad 的結果是 no_winner —— 看起來合理。逐單位數 event 才看到機槍手 20 個 NO_ACTION。

---

## 4. 出了什麼問題

### 問題 1：唯讀世界的第一版慢了三倍

通用的代理在每次讀取時建立新的包裝，每讀一格地形就把整張表轉成 tuple。

### 問題 2：profiler 與牆鐘時間不一致

修到第三輪時 cProfile 顯示兩個版本總時間幾乎相同，實際卻差 45%。差距在 `__getattr__`：Python 先找一般屬性、失敗時在內部丟出並接住 AttributeError，才呼叫 `__getattr__`。這個成本不出現在 profiler 的函式列表裡。

### 問題 3：又寫了一個佔位

SKYFOX 替身缺 energy 資料時，我寫了一行永遠不會執行的條件加 `raise NotImplementedError`，打算之後再補。它沒有被執行到就被看見，但本不該寫下。

### 問題 4：替身只在一種配置下看過

HADES 替身在每個單位都能成為「最近的己方單位」的配置下合理；在有後排單位的 squad 就不行。

---

## 5. 根本原因

### 成因 1：設計時只估了「複製」的成本，沒有估「代理」的成本

開設時量了複製（約慢一倍）並否決它，然後假設代理很便宜。代理的成本取決於讀取的次數 —— 軍事 policy 的路徑搜尋每場讀 1.3 萬次地形。

### 成因 2：用 profiler 的分布判斷「差距在哪裡」

profiler 回答「時間花在哪些函式」，不回答「兩個版本差在哪裡」。

### 成因 3：缺資料時的反射是「先放著」

observation 沒有 energy；正確的動作是回頭補契約，但「先寫出 adapter 再說」比較快。

### 成因 4：替身被當成範例，不被當成被測的系統

替身會進到真實的 run 裡，但它的邏輯只用手造的單一配置測過。

---

## 6. 下一階段要改的事

### 改法 1：每條「只能」的規則，開設時寫一個違反它的程式

Phase 11（Background World Service）、Phase 12（External System Interface）適用：例如一個任務能不能超出它的算力預算繼續跑、外部系統能不能讀到別的系統的 observation、能不能送出別人的單位的 order。

### 改法 2：效能比較用牆鐘時間、兩個版本交替跑

`best of 3`、舊新交替；profiler 只用來找熱點，不用來判斷差距。

### 改法 3：缺資料就補資料，不寫佔位

缺的是契約的欄位就先改契約（只新增），再寫用它的程式。

### 改法 4：會進 run 的替身，在每一個 fixture 上看逐單位統計

每個 adapter 的替身至少在一個軍事 scenario 上跑過，數每個單位的 NO_ACTION 與被拒的 action。

---

## 7. 沒有結論的一項

**被拒的 action 太多算不算問題。**

AEROGRID 替身在 urban 有 128 個移動被拒（遠離友軍時走出地圖或撞上單位）。SKYVAULT 拒絕它們是對的 —— 但一個 actor 一直提出不可能的 action，評估上應該怎麼看？Phase 7 的評估沒有「被拒比例」這一軸。若外部系統接入後（Phase 12）這個比例成為判斷系統品質的指標，也許需要在 evaluation 加一軸，或在 anti-gaming 加一種行為（例如用大量無效 action 拖時間）。留給 Phase 12 或 Phase 14 以後有真實外部系統時決定。

---

## 8. 一句話

> Phase 6 讓 actor 只能交出意圖，而它最重要的一步是在寫程式之前先寫一個作弊的 policy —— 它在 Phase 5 的系統上用 4 筆 event 贏了一場仗，現在它在第一次寫入時就被擋下。
