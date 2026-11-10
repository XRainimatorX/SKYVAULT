# Phase 13 回顧

Military / Tactical Domain Pack v1.3

這份文件檢討**流程**，不檢討人。所有問題都以「什麼樣的做法讓這件事得以發生」來描述 —— 目標是讓下一個階段不要重蹈，不是追究誰的責任。

寫完不再更新。

---

## 1. 摘要

Phase 13 交付了第一個 domain pack：九種 profile、scenario builder、軍事規則、baseline policy、指揮延遲、任務判定、四個 reference scenario、doctrine 比較、可替換的 policy 與 state-action-outcome dataset。core 只多了三個擴充點，沒有 domain 的 run 逐位元不變。

這一輪最大的收穫來自**第二個使用者**：domain pack 是第一個不是 tactical reference 的 scenario 來源，它一跑就讓 Phase 17 的 briefing 露出問題 —— 計數時把原始 event 型別名念出來。Phase 17 的所有測試都只用 reference run，而 reference run 剛好只有三種 event。

**核心教訓：只被一種輸入測過的輸出，只證明了那一種輸入；新增一種輸入來源時，把每個既有的輸出（timeline、views、briefing）在它上面跑一次、讀一次。**

---

## 2. 時間軸

```text
11-08   開設前測量：core 的規模、擴充點、event 型別；設計報告的參數
11-08   開設：milestone #10、issue #26（19 項決定）、九種 profile 與四個 spec 先 commit
11-08   步驟 A + B：三個擴充點、profile、builder、規則、policy、任務
        —— 外部 policy 的測試用了 reference 沒有的 wait ——
11-08   步驟 C：reference scenario、doctrine batch、dataset、範例、腳本、CI
        —— dataset 以 run_id 命名 episode，不可重現；urban spec 的支援組位置錯 ——
        —— 一個變異「存活」其實是 pattern 沒對上；一個 state 測試的缺口 ——
11-08   整合：在軍事 run 上跑 views 與 briefing
        —— briefing 念出 entity_state_changed ——
```

---

## 3. 做得好的地方

### core 的改動小而可證明

三個擴充點，各有「沒有它時一切照舊」的測試；reference trace 與 output_hash 沒動。pack 的 handler、terrain、policy 用 core handler 的同一個 AST 檢查證明只讀世界。

### Phase 10 與 17 的教訓直接用上

```text
Phase 10 改法 1（跨 hash seed）     dataset 在寫跨 seed 測試前，看欄位就發現 run_id 會讓輸出不同
Phase 10 改法 3（同分配斷言）       policy 的 tie 都用 FixedRng.choice 取第一個，測試斷言是哪一個
Phase 17 改法 2（本機跑 3.10）      推送前在 3.10 venv 跑完整測試
Phase 17 改法 3（commit 前全部閘門） 每個 commit 前 ruff、black、mypy、bandit、pytest 都跑
```

### 量 20 個 seed 才下結論

第一次看到四個 scenario 都是防守方贏，可能以為是 policy 的錯。量了 20 個 seed 才看清楚：三個 scenario 防守完全佔優、urban 有爭議，而 urban 的 doctrine 差別很大。這也順便抓出 urban spec 的支援組放錯位置。

### dataset 用 engine 自己的紀錄核對

dataset 的 state 是從 event 重建的；engine 在每個 ACTION_SELECTED 已經記了 actor 的 snapshot。兩者逐筆比較，是一個不依賴實作細節的獨立證據。

---

## 4. 出了什麼問題

### 問題 1：Phase 17 的輸出只被一種 run 測過

briefing 的 fixture、views 的測試、e2e，全部用 reference workspace。reference 的 event 型別只有三種會被計數，所以「其他型別怎麼念」從沒被問過。

### 問題 2：變異腳本把「沒套用」當成「存活」

pattern 對不上時腳本照跑測試。black 會重排程式，所以 pattern 失效是常態而不是例外。

### 問題 3：測試只看第一筆

「state 是決定當下的單位」只檢查第一筆紀錄 —— 第一筆剛好是初始狀態，所以不追蹤 snapshot 也會過。

### 問題 4：fixture 的 spec 有一個部署錯誤

開設時寫的 urban spec 把支援組放進守軍射程。spec 是「先 commit 的輸入」，但沒有人在 commit 前跑過它。

---

## 5. 根本原因

### 成因 1：測試資料只有一個來源

Phase 1 起所有輸出都以 tactical reference 為唯一的真實 run。只要只有一個 scenario，「對所有 run 都成立」與「對這個 run 成立」就分不出來。

### 成因 2：工具沒有在失敗時大聲說

變異腳本是臨時寫的，只處理了「套用成功」的路徑。

### 成因 3：「第一筆」是最不具代表性的一筆

在任何依時間累積的資料裡，第一筆都是還沒有任何累積的那一筆。

---

## 6. 下一階段要改的事

### 改法 1：輸出在每一種輸入來源上都跑一次

新增 scenario 來源或 domain 時，把 timeline、views、briefing、UI 在它上面跑一次並讀過；有差異的地方加一個用它的測試。

### 改法 2：變異腳本在 pattern 對不上時報錯

已改：對不上就印「NO MATCH」、不跑測試。之後所有反向驗證都用這個版本。

### 改法 3：累積資料的測試要檢查每一筆，或至少檢查最後一筆

檢查第一筆只證明初始化正確。

### 改法 4：先 commit 的 fixture 也要先跑一次

spec、批次請求這類「輸入型」fixture，commit 前用現有系統（或最小的實作）跑一次，確認它描述的是想要的情況。

---

## 7. 沒有結論的一項

**感測該放在哪裡。**

目前「看得到誰」在 pack 的 policy 裡算：距離 × (1 − concealment)。這讓外部 policy（TAC ANGEL 範例）其實能看見所有單位 —— 它直接讀 world。真正的 TAC ANGEL 應該只拿到它的單位看得到的東西，這需要 core 在把 world 交給 policy 之前先過濾，也就是 Phase 5 的 Observation Contract。到時候 pack 的感測規則要搬進觀測層，dataset 的 `seen_enemies` 也應該改由觀測層產生。如何讓 pack 提供感測規則而由 core 執行，留給 Phase 5。

---

## 8. 一句話

> Phase 13 讓 SKYVAULT 有了第一個 domain pack，而 domain pack 作為第一個「不是 reference 的 run」，立刻讓 Phase 17 的 briefing 露出只在 reference 上測過的問題 —— 輸出要在每一種輸入上都跑過，才算真的測過。
