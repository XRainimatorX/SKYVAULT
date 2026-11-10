# Phase 15 回顧

Airspace / HADES / SKYFOX / AEROGRID Domain Pack v1.5

這份文件檢討**流程**，不檢討人。所有問題都以「什麼樣的做法讓這件事得以發生」來描述 —— 目標是讓下一個階段不要重蹈，不是追究誰的責任。

寫完不再更新。

---

## 1. 摘要

Phase 15 交付了第三個 domain pack：2D 空域、機率偵測與誤報、航跡與識別、反應延遲、攔截與裝填，以及 HADES、SKYFOX、AEROGRID 在同一片空域裡的提交。模擬不變，沒有重工。

這一輪最值得記下的是：**場景的第一版只守住 10%，於是 failure exploration 回報「沒加壓就失敗」—— 而這是在寫 failure exploration 的測試時才發現的，不是在校準時。** 校準看的是 HADES 與 AEROGRID 的比較有沒有差異，沒有看 core 的其他工具在這個基線上還能不能工作。

**核心教訓：校準一個新場景時，除了 domain 自己的指標，也要跑一次 core 的每個工具（failure map、batch），確認基線讓它們說得出東西。**

---

## 2. 時間軸

```text
11-08   Phase 14 收尾後開設 Phase 15：測量確定性的偵測、沒有航跡與攔截、AEROGRID 回 gap
11-08   milestone #17、fixture 先 commit、issue #33（19 項決定）
11-08   模型、builder、handlers、policy、pack —— 第一次跑：沒有威脅升空（待命者不能行動）
11-08   逐欄讀 verdict：漏過判 pass、攔截器被標 inaction → success_outcomes 一律適用、acts(entity, world)
11-08   metrics、介面、run_airspace；讀輸出：離線雷達算進覆蓋、response 誤導、巡邏卡住
11-08   寫測試：failure map「沒加壓就失敗」→ 校準三輪；速度進位讓三級相同 → 小數速度；擊落那一 tick 不在窗口 → 修
11-08   CI 步驟本機逐字執行；整合：/tmp、3.10、兩個 hash seed；19 個變異（兩個存活 → 補測試）
```

---

## 3. 做得好的地方

### 第一個 run 逐欄讀 verdict

Phase 14 回顧改法 1 的第一次實踐，當場抓到兩件事：漏過的 run 被判 pass、防空在等目標時被當成「不作為刷分」。兩件都在寫任何測試之前修掉。

### 判斷詞先寫定義

「漏過的原因」在 metrics 的 docstring 先寫成有順序的六種，每一種隨後都造了一個只會產生它的 scenario（只有 missed_in_window 同時會產生 not_engaged —— 不能殺傷的砲也會被佔住，測試寫明了這一點）。

### 一次只跑一套用到外部服務的測試

/tmp（沒有服務）與 3.10 venv（有服務）依序跑，沒有撞 PostgreSQL。

---

## 4. 出了什麼問題

### 問題 1：校準只看了 domain 的比較

第一版的數字讓 HADES 的五種規則、AEROGRID 的四種配置都有差異，看起來「可以用」；但基線只守住 10%，failure exploration 的每個變數在 mild 就「斷」，failure map 沒有資訊。

### 問題 2：整數化掩蓋了程度

failure variable 對整數速度 × 1.25 進位，mild 與 severe 一樣。第一版的 failure variable 測試只斷言「速度變快」，沒有斷言程度之間有差。

### 問題 3：快照的時間點

攔截窗口用「tick 結束時 active」決定威脅在哪；一發擊落的威脅，在它被擊落的 tick 已不 active —— 它被攔截的那一刻不在它自己的攔截窗口裡。

### 問題 4：反向驗證有兩個存活

舊航跡（目標已飛出射程）與 acts 的反應延遲判斷都沒有測試資料走到那條邊（Phase 14 改法 3 只做了一半：寫守護時沒造反例）。

---

## 5. 根本原因

### 成因 1：校準的目標只寫了 domain 指標

Phase 14 改法 4 說「係數從一輪測量開始」，量的是 domain 的分布；沒有說 core 的工具也要在基線上量。

### 成因 2：程度的測試只測方向

「加壓會變差」是方向；「每一級比前一級更差」才是程度。測試只寫了前者。

### 成因 3：從快照讀事件時刻

history 是每 tick 結束時的快照；被改變的那一 tick，快照已是改變之後。metrics 用快照回答「當時在哪」時沒有想到這一點。

### 成因 4：守護條件與它的反例不在同一個 commit

engage 的 reachable 檢查、acts 的 engageable_from 檢查都在第一版就寫了，反例到反向驗證時才補。

---

## 6. 下一階段要改的事

### 改法 1：校準時跑一次 core 的工具

新場景的基線定下前：failure map 的 baseline 不能「沒加壓就失敗」、batch 的變體要有差異。量的結果寫進 ADR。

### 改法 2：failure variable 的測試要斷言程度之間有差

mild、moderate、severe、collapse 四級套到場景後的參數必須兩兩不同；整數參數要特別檢查。

### 改法 3：從快照讀「當時」時，寫明是哪個時刻

metrics 讀 history 時，docstring 說明快照是 tick 結束時；被改變那一 tick 的狀態要從前一個快照或事件本身讀。

### 改法 4：每個 guard 一個走到邊上的測試，同一個 commit

沿用 Phase 14 改法 3，並在 issue 第 6 節的共同規則裡把它列為逐項檢查。

---

## 7. 沒有結論的一項

**core 的 11 軸要不要讓 domain 提供自己的軸**（Phase 14 留下）。

空域再出現一次同樣的需要：verdict 靠 success_outcomes 才對，真正的判斷在 airspace_outcome。Phase 16 的裝備 pack 是第三次 —— 那時一起決定。

---

## 8. 一句話

> Phase 15 讓 SKYVAULT 有了第一片天空，而它最該記住的一課是：一個只守得住一成的基線，讓 failure exploration 在每個變數的第一級就宣告崩潰 —— 校準新場景時，要確認 core 的每一個工具在它上面還說得出話。
