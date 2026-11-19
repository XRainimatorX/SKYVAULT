# Phase 8 回顧

Reproducibility + Version Control v0.8

這份文件檢討**流程**，不檢討人。所有問題都以「什麼樣的做法讓這件事得以發生」來描述 —— 目標是讓下一個階段不要重蹈，不是追究誰的責任。

寫完不再更新。

---

## 1. 摘要

Phase 8 讓 id 決定化、為每個 result package 加上 Spec §12 的 reproducibility 區塊、把 scenario 放進版本資料夾並能比較、加上 run registry 與重跑驗證。模擬行為不變，reference trace 的 digest 一個字都沒變，沒有任何一輪重工。

這一輪最重要的發現是兩個「hash 說了謊」的情況：一個是 hash 取自驗證前的 dict，描述的是一份沒有人會拿到的 package；另一個是驗證時信任了 package 自己記錄的 hash。**兩者都被事先寫好的測試抓到，因為測試問的是「這個 hash 能不能從呼叫端拿到的東西重算出來」，而不是「兩次算出來的 hash 一不一樣」。**

**核心教訓：驗證一個指紋，要拿它和「從實物重算的指紋」比，不能拿它和「另一份同樣方法算出的指紋」比 —— 同樣的錯誤會一致地出現在兩份裡。**

---

## 2. 時間軸

```text
11-08   開設：milestone #6、issue #22（16 項決定、每步綠燈狀態）
        fixture：reference 搬進版本資料夾（16 個檔的路徑）、v0.2（命中率 0.55 → 0.75）
11-08   步驟 A：決定性 id + hashing；reference digest 不變
11-08   步驟 B：版本、reproducibility 區塊、契約 0.5
        —— output_hash 對不上：驗證會把 int 變 float ——
11-08   步驟 C：compare、registry、verify_run
        —— 反向驗證：只比記錄的 hash 會放過被改過的 package ——
        —— 反向驗證：在 registry 加 import 直接循環 import ——
11-08   整合：兩次 run 只有 reproducibility 區塊不同
```

---

## 3. 做得好的地方

### 「從實物重算」寫進了 issue 與測試

issue 第 6 節寫 output_hash 的定義，第 8 節要求「hash 可重算」。測試 `test_the_block_hashes_match_what_was_run_and_produced` 直接拿呼叫端收到的 package 重算 —— 這是它能抓到驗證前後不一致的唯一原因。

### digest 在決定化前後保持不變

Phase 3 留下的 reference digest 用「依首次出現順序換成序號」處理 id。換成計數器後，同樣的正規化把兩種 id 對映成同樣的序號，digest 不變，等於免費證明了「只有 id 的字面值變了」。

### 變體用一個值翻盤

v0.2 只改一個數字（blue_002 accuracy），結果從 RED 勝變 BLUE 勝。compare_scenarios 只有一行輸出、compare_runs 有明顯的差異，示範與測試都很清楚。掃 0.65 / 0.70 / 0.75 / 0.80 的過程也記下了，未來想要「平手」的變體可以直接用 0.70。

### Phase 7 改法都用上了

```text
改法 1（門檻要有觸發與不觸發的真實 run）   seed policy 三種情況都用真的 engine run
改法 3（變異要確認被執行）                 用 python3 -c "import …" 先確認，才看測試結果
改法 4（數字要有命令出處）                 完成報告的 hash、時間、行數都是從命令輸出貼的
```

---

## 4. 出了什麼問題

### 問題 1：hash 取自驗證前的 dict（最嚴重）

engine 先組 package、算 hash、再驗證。驗證會把 `raw: 3` 正規化成 `3.0`，所以記錄的 hash 對應的是驗證前的版本。兩次 run 的 hash 仍然相同 —— 兩次都在同一個位置算 —— 所以只測「兩次相同」不會發現。

### 問題 2：驗證的第一個念頭信任了 package 自己

「重跑的 hash == 記錄的 hash」聽起來就是驗證。但記錄的 hash 寫在 package 裡，改 package 的人不改它，驗證就通過了。這個錯誤沒有進到 commit，是寫的時候想到、再用反向驗證確認的。

### 問題 3：中途修改了 v0.1 的內容

為 v0.1 加 version_control 讓它的 input_hash 改變。它是正確的行為，但「v0.1 的 input_hash」在 Phase 8 裡有兩個值，若有人引用了前一個，就對不上。

### 問題 4：fixture commit 必須連帶改 16 個檔

把 reference 搬進版本資料夾是 fixture 的一部分，但它讓 fixture commit 同時改了 16 個測試與腳本的路徑。fixture 先行的原則讓「搬家」與「功能」分在不同 commit，這是好的；但開設時沒有預估到搬家的範圍。

---

## 5. 根本原因

### 成因 1：hash 的計算位置與資料的最終形態沒有綁在一起

「在回傳前的哪一刻算 hash」沒有被當成設計決定，只是寫在組 package 的程式碼旁邊。資料在那之後還會被轉換，hash 就過期了。

### 成因 2：驗證把自我申報當成證據

package 裡的 output_hash 是 package 對自己的申報。驗證需要獨立的證據 —— 從內容重算，或從輸入重跑。

### 成因 3：版本化的資料在版本確定前就被引用

v0.1 在 Phase 8 的步驟 A、B 都被跑過、hash 被印出來，步驟 C 才補上 version_control。

---

## 6. 下一階段要改的事

### 改法 1：指紋在資料的最終形態上算

任何 hash、簽章、計數，都在資料「交給呼叫端的那一刻」的形態上計算，並有一個測試從呼叫端拿到的東西重算比對。

### 改法 2：驗證不使用被驗證物的自我申報

驗證函式的每個判斷，都要指出它的證據來自哪裡：重算、重跑、外部紀錄。只來自被驗證物本身的欄位不算證據。

### 改法 3：版本化的資料，版本欄位在第一個 commit 就到位

新增或搬移有版本概念的資料（scenario、profile、規則）時，version 相關欄位在 fixture commit 就寫好，之後的步驟不再修改它的內容。

### 改法 4：開設時估計 fixture 的連帶範圍

fixture 若會搬移檔案或改名，開設時用 grep 算出會連帶修改的檔案數，寫進 issue 第 2 節。

---

## 7. 沒有結論的一項

**runtime_version 是手動維護的。**

每個 Phase 調升 minor 是寫在 ADR 裡的慣例，沒有任何機制強制。如果某個 Phase 改了引擎行為卻忘了調版本，兩個行為不同的引擎會有同一個 runtime_version，reproducibility 區塊就會誤導人。

可行的做法有：從 git commit 取版本（但 tarball 安裝時沒有 git）、對 src/ 的內容算 hash（但改註解也會變）、或在 CI 檢查「src/ 有變動時 __version__ 也要變」。每種都有代價，這一輪沒有做決定。

---

## 8. 一句話

> Phase 8 讓同一輸入得到同一個 output_hash，而這一輪的兩個問題都是 hash 說了謊：一個取自驗證前的資料，一個被拿去和自己比 —— 指紋要在資料交出去的那一刻算，驗證要用重算或重跑的獨立證據，不能信任被驗證物的自我申報。
