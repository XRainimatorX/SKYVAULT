# Phase 14 回顧

Logistics / Governance / City Domain Pack v1.4

這份文件檢討**流程**，不檢討人。所有問題都以「什麼樣的做法讓這件事得以發生」來描述 —— 目標是讓下一個階段不要重蹈，不是追究誰的責任。

寫完不再更新。

---

## 1. 摘要

Phase 14 交付了第二個 domain pack：道路網上的城市、治安狀態機、電力連鎖、補給延遲、governance stability score，以及 engine 對其他空間與「不靠陣營結束」的世界的開放。模擬不變，沒有重工。

這一輪最值得記下的是：**第一次跑 city，一座全部 riot 的城市被判為 pass。** core 的評估是戰鬥的形狀：沒有對手時，大多數軸不適用，剩下的（保住多少實體）在城市裡永遠是滿分。

**核心教訓：一個新 domain 的第一個 run，先讀 core 給它的判斷 —— 每個不適用的軸、每個恆為滿分的軸，都要問它在這個 domain 裡說的是什麼。**

---

## 2. 時間軸

```text
11-08   Phase 12 收尾後開設 Phase 14：測量圖空間被拒、只剩一方就結束且判 pass、supply_delay 只是打折
11-08   milestone #16、fixture 先 commit、issue #32（17 項決定）
11-08   A+B：engine 的 pack 宣告；city 的模型與 handlers —— 第一次跑：兩座城市都崩潰、而且都判 pass
11-08   校準三輪（20 個 seed）；讀連鎖的輸出：維修隊半途改目標、修好就再跳脫 → 跳脫隔離、維修順序
11-08   success_outcomes 與 domain 結束原因；邊界測試找到 0 tick 的送貨
11-08   C：failure variables、batch 勝負、NEXUS 的 domain_outcome、report、run_city、CI 步驟（本機逐字執行）
11-08   整合：跨 hash seed 相同；21 個變異全部紅（一個存活 → 補測試）
```

---

## 3. 做得好的地方

### 每個判斷詞先寫定義與反例

Phase 12 回顧改法 1 的第一次實踐：order_restored 寫下定義的同時就寫了 order_held（一開始就穩定的城市不是「恢復」）、「連鎖」寫下定義的同時寫了「backup 撐得住的失效不是連鎖」。兩個反例都成為測試。

### 邊界值先跑

改法 2：人口 0、糧食 0、容量 0、沒有道路、沒有 depot、沒有 actor、沒有電廠 —— 開設時就列進 issue，開發時第一批測試就跑。0 tick 的送貨就是在這組附近被抓到的。

### 一次只跑一套用到外部服務的測試

改法 3：/tmp 與 3.10 venv 依序跑，沒有再撞 PostgreSQL。

---

## 4. 出了什麼問題

### 問題 1：崩潰的城市被判 pass

engine 的 verdict 欄在第一次執行就印出來了（"status: pass"），但注意力在結果名稱與分數上。

### 問題 2：讀輸出才看到的模型錯誤

維修隊每個 tick 重新選目標，開到一半就改去別處；修好的 substation 接下仍跳脫者的負載又跳。測試在這之前已經全綠 —— 它們斷言的是「有連鎖」，沒有斷言「修好之後不再跳」。

### 問題 3：反向驗證有一個存活

回程至少一個 tick 的守護沒有測試會因為它被拿掉而失敗：沒有一個 seed 把車隊派到 depot 所在的 district。

### 問題 4：校準花了三輪

係數第一次寫下時沒有任何測量；兩個方向的極端各跑出一次才收斂。

---

## 5. 根本原因

### 成因 1：新 domain 沿用了 core 評估，卻沒有問 core 評估在這裡量什麼

Phase 7 的軸是 Phase 7 時唯一的世界（戰鬥）定義的。domain pack 的形狀（Phase 13）給了 mission_outcome 這樣的 hook，但 core 的 verdict 從來沒有在「沒有對手」的世界裡被檢查過。

### 成因 2：動態系統的測試只看「發生了」，沒看「之後怎樣」

連鎖的測試斷言跳脫發生、caused_by_event 正確；沒有任何測試讀修復之後的那段時間。

### 成因 3：測試資料剛好避開了邊角

reference spec 的 harbor 有 4 單位糧食，從來不是最餓的 district。改法 4（守護的測試資料要能區分兩種寫法）在寫守護時沒有被想起。

### 成因 4：係數在模型之前寫

rules.json 是在第一次執行之前寫的，數字是「看起來合理」。

---

## 6. 下一階段要改的事

### 改法 1：新 domain 的第一個 run，逐欄讀 core 的評估

verdict、每個軸的 applicable 與分數、failure_causes、recommended_next_tests —— 每一欄都問「在這個 domain 裡它說的是真的嗎」。恆為滿分或恆為零的軸是警訊。Phase 15 的空域、Phase 16 的裝備都會遇到。

### 改法 2：動態的測試要讀「之後」

任何「X 發生」的測試，加一條「X 之後一段時間的狀態」：修好之後不再跳、恢復之後不再掉、停止之後不再動。

### 改法 3：寫守護時就造它的反例資料

每加一條 max(1, …)、一個邊界條件，就在同一個 commit 加一個走到那條邊的輸入。

### 改法 4：係數從一輪測量開始

新模型的係數先放一組，跑一輪多 seed 的分布（每個結果的比例、關鍵量的範圍），再寫進 rules；把測量結果寫進 ADR。

---

## 7. 沒有結論的一項

**core 的 11 軸要不要讓 domain 提供自己的軸。**

現在 city 的判斷分兩處：core 的 verdict（靠 success_outcomes 才不說謊）與 pack 的 governance score。讓 pack 註冊軸（例如 governance_stability 作為一個 metric）可以把兩者合一，但 evaluation profile 的權重、anti-gaming 的規則都要跟著知道 domain。Phase 15、16 再出現一次同樣的需要時一起決定。

---

## 8. 一句話

> Phase 14 讓 SKYVAULT 跑起第一座城市，而它最該記住的一課是：一座全部陷入暴動的城市，第一次被判定為 pass —— 新 domain 的第一個 run，要逐欄讀 core 對它說了什麼。
