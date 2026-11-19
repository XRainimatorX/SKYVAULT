# Phase 2 回顧

World Runtime Core v0.2

這份文件檢討**流程**，不檢討人。所有問題都以「什麼樣的做法讓這件事得以發生」來描述 —— 目標是讓下一個階段不要重蹈，不是追究誰的責任。

寫完不再更新。

---

## 1. 摘要

Phase 2 交付了 runtime 套件（三種空間、三種時間、實體登記、資源、規則、快照、event sourcing），契約升到 0.2，模擬行為沒有改變，沒有任何一輪重工。

Phase 1 回顧的四條改法都被執行了，其中兩條直接抓到問題：開設時先列規格矛盾，讓八項決定在寫程式之前就定案；反向驗證抓到一個無效的分層測試。

但也發現：**凍結介面只寫了簽名，沒寫行為**，同一個 `phase_length` 在兩個步驟被理解成兩樣；而簽名本身的落差，要到整合時逐條比對才浮現。

**核心教訓：凍結的東西要在寫的當下就對照，不能等整合；凍結介面要寫一行行為，不能只寫型別。**

---

## 2. 時間軸

```text
11-08   開設：milestone #3、issue #19（八項規格矛盾先決定）、兩份 0.2 fixture 先 commit
11-08   步驟 A：space.py、clock.py
11-08   步驟 B：registry、resources、rules、create_world；契約升 0.2
        —— phase clock 的說明與已 commit 的實作不一致，測試紅了才發現 ——
11-08   步驟 C：rebuild_world、SnapshotStore
        —— 反向驗證：兩個變異存活，查明為等價變異，刪掉一段多餘的特例 ——
11-08   整合：凍結介面逐條比對，SnapshotStore 簽名不符
        —— 分層測試抓不到 from .. import engine ——
```

沒有任何一步需要回頭重做。

---

## 3. 做得好的地方

### 開設時先列規格矛盾（Phase 1 改法 3）

Formal Spec 的範例與開發計劃在位置型別、空間型別名稱、phase_length 格式、時間型別、資源格式上都有落差。這次在開 issue 時就逐項寫出決定，**寫程式時沒有一次停下來想「這裡該怎麼辦」**。Phase 1 有兩處矛盾是寫到那份契約時才撞見的，這次是零。

### 上一階段的數字再次當回歸基準

entity_history 21、causal_chain 46、replay 12、攻擊整句 14 —— Phase 1 報告記下的數字，這次原樣對上。加上新的不變量「重建 == final_world_state」，回歸基準從「數字對」升級成「結構上可以證明對」。

### 把新不變量放進 CI

`rebuild_world(initial, events) == final` 不只是一個單元測試，CI 也用 pipeline 剛產生的 `result_package.json` 跑一次。之後任何人改了世界卻沒記 event，CI 會在乾淨環境擋下來。

### 型別擴充把隱含假設翻出來

`Location` 擴成 `tuple | str` 後，mypy 立刻指出 tactical policy 假設位置一定能拆成 `(x, y)`。這是型別檢查在做它該做的事 —— 假設從隱含變成明寫。

---

## 4. 出了什麼問題

### 問題 1：分層測試在缺陷存在時仍然會過（最嚴重）

runtime 不得 import engine。第一版測試只看 `ImportFrom.module`，而 `from .. import engine` 的 module 是 `None`。把這行放進 `rules.py`，測試全綠。

這和 Phase 1 的 timeline 測試是同一類問題：**測試檢查的是「常見寫法」，不是「所有寫法」。** 這次在推送前就抓到了，因為改法 1 被當成必做步驟。

### 問題 2：凍結介面只有簽名，行為各自理解

issue #19 第 6 節寫了「整數 phase_length + optional time_unit」，沒寫 `advance()` 前進多少。步驟 A 實作成每次一整個 phase；步驟 B 寫契約說明時理解成「phase_length 個 tick 為一個 phase」，同步驟的測試也照這個寫。

單一工作者都會出現這種落差，多人平行時只會更嚴重。

### 問題 3：凍結簽名的落差到整合時才發現

`SnapshotStore.record(snapshot)` vs 凍結的 `record(time, snapshot)`；`EntityRegistry.require()` vs 凍結的 `get()`。寫程式時手邊有 issue，但沒有逐條對照。

### 問題 4：變異存活時差點直接補測試

兩個變異存活時，第一反應是「測試不夠，再補」。查下去才知道是等價變異 —— 程式碼裡有一段永遠不影響結果的特例。補測試會把多餘的程式碼「保護」起來。

### 問題 5：機械式遷移差點改寫整份檔案的格式

用 `json.dumps` 遷移 reference scenario，diff 從 6 行膨脹成 64 行。review 的人得在 58 行純格式變動裡找那 6 行真正的變更。

---

## 5. 根本原因

### 成因 1：反向驗證只對「抓缺陷的測試」做

改法 1 寫的是「為抓特定缺陷而寫的測試」。分層測試不是為某個已知缺陷寫的，差點被排除在外。**守護不變量的測試，跟抓缺陷的測試一樣需要反向驗證** —— 它們都在宣稱「這件事壞了我會紅」。

### 成因 2：Frozen Interface 的模板只有簽名欄

issue 第 6 節的 Frozen Interface 是一段 Python 簽名。簽名能表達型別，表達不了「advance 一次走多遠」「找不到時回傳什麼」。模板沒有行為欄，就不會有人寫。

### 成因 3：對照凍結介面被放在整合，而不是開發中

整合清單有「逐條核對第 11 節」，沒有「逐條核對第 6 節」。第 6 節的凍結內容在寫程式時只是參考，沒有一個步驟強制比對。

---

## 6. 下一階段要改的事

### 改法 1：所有守護型測試都做反向驗證

把 Final Done Criteria 的反向驗證條改為：

```text
N. 抓缺陷的測試與守護不變量的測試（分層、不可為負、重建相等……）都把違規放回去跑過，確認會紅
```

變異存活時，先判斷是否等價：等價就簡化程式碼，不等價才補測試。

### 改法 2：Frozen Interface 每個函式附一行行為

```python
PhaseClock.advance() -> int     # now += phase_length；回傳新的 now
EntityRegistry.require(id)      # 找不到 raise KeyError
```

開設時寫，作為該 Phase 的凍結內容。

### 改法 3：每個步驟 commit 前比對第 6 節

步驟的品質閘門加一條：這一步新增的公開函式，簽名與行為和 issue 第 6 節一致；不一致就改程式，或在 ADR 記錄偏離理由。

### 改法 4：資料檔遷移用最小文字取代

遷移手寫的資料檔（scenario、設定檔）時，用文字取代只改需要改的地方；只有本來就是程式產生的檔案才整份重寫。

---

## 7. 沒有結論的一項

**tactical engine 與 runtime 有兩條改世界的路徑。**

runtime 提供 `update_entity_state()` 與 `change_resource()`，每次改動都記 event。tactical engine 仍直接改 entity、自己記 MOVE / ATTACK。兩者結果相同 —— after_state 都是完整快照，所以重建不受影響 —— 但「改世界要經過記錄 event 的方法」這條規則目前靠慣例，不是靠結構。

收斂它會改變事件型別或順序，違反 Phase 2「模擬行為不變」的前提，所以留給 Phase 3 的 Action & Consequence 框架。

---

## 8. 一句話

> Phase 2 證明了 event memory 真的是真相，而 Phase 1 的改法有用：先列矛盾讓決定不再臨場、反向驗證又抓到一個會過的測試 —— 但凍結介面只寫簽名、而且直到整合才比對，讓同一個參數在兩個步驟被理解成兩樣；凍結的東西要寫行為，並且在寫程式的當下對照。
