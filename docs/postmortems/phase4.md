# Phase 4 回顧

Event Memory + Replay System v0.4

這份文件檢討**流程**，不檢討人。所有問題都以「什麼樣的做法讓這件事得以發生」來描述 —— 目標是讓下一個階段不要重蹈，不是追究誰的責任。

寫完不再更新。

---

## 1. 摘要

Phase 4 的功能全部交付，四個 exporter 都能用，七個輸出一次產生。

但整合階段暴露出四個問題，其中一個（runner 沒有接上 exporter）讓三個 section 的成果在合併時全部失效，必須重做整合。另有一個缺陷直到撰寫完成報告、逐項核對真實輸出時才被發現，34 個測試全綠也沒抓到。

**核心教訓：每個 section 都通過了自己的驗收，但整個 phase 是壞的。**

---

## 2. 時間軸

```text
06-09   四份 issue 開出（#5 #7 #8 #9），frozen event shape 定案
06-16   Section C 交付 timeline.py 與測試
06-23   Section C 交付 entity_history.py
06-24   Section C 完成，四次 README 更新
06-28   Section B 交付 replay.py、causal_chain.py、runner 改動
        —— 三個 section 各自宣告完成 ——
09-04   整合，發現 runner 從未呼叫任何 exporter
09-04   四個 exporter 重寫為純函式，測試改為呼叫函式
09-04   補上 result_package.initial_world_state，修正 event_count
09-05   收尾品質檢查
09-05   撰寫完成報告時，發現 timeline 傷害數字缺陷
```

從「三個 section 都說完成」到「整個 phase 真的能用」中間隔了一整輪重工。

---

## 3. 做得好的地方

### Frozen event shape 這個機制有效

[issue #9](https://github.com/XRainimatorX/SKYVAULT/issues/9) 在開工前凍結 event 的 17 個欄位，讓三個 section 不必等彼此就能開始。

**結果是資料形狀真的對上了。** 整合時沒有出現「A 寫的格式 B 讀不懂」這種問題 —— 而那正是這個機制要防的事。這個做法應該保留。

### 演算法本身全部正確

replay 的 tick 邊界處理（含最容易漏掉的迴圈結束後補存）、causal chain 的分組與排序、timeline 的八種 event 措辭、entity_history 的九鍵統一 record —— 這些困難的部分都做對了。

重工重的是包裝，不是思路。

### 函式邊界讓重構變便宜

Section C 的模組有真正的函式與參數說明，整合時邏輯幾乎原樣搬移。Section B 的模組沒有函式，必須整個重寫外層。

**同樣的重構工作，成本差了數倍，差別只在交付時有沒有留下函式邊界。**

### 文件邊做邊寫

Section C 隨著每個檔案落地更新 README，共四次。趁程式還新鮮時寫的文件才是正確的文件 —— 相對地，Phase 4 結束後才補的文件就出現了不一致（見第 5 節）。

---

## 4. 出了什麼問題

### 問題 1：runner 從未呼叫 exporter（最嚴重）

runner 把整包 `result_package` 寫進 `causal_chain.json` 與 `replay_state_at_tick.json`，而檔案頂端根本沒有 import 這兩個模組。

**檔案存在、內容全錯。** 21 條 Done Criteria 裡有 11 條在看這兩個檔的內容。

### 問題 2：測試測產物，不測函式

四份測試都是 `open("output/xxx.json")` 後 assert。

**這種測試在檔案殘留時假通過、在檔案被覆寫時假失敗，兩種情況下受測程式都沒被執行。** 之所以曾經全綠，是因為有人手動跑過 exporter，磁碟上留著正確的檔案。

### 問題 3：`result_package` 缺 `initial_world_state`

replay 與 entity_history 需要 tick 0 的世界狀態，但 result_package 沒有這個欄位，只好回頭讀 scenario 檔 —— 直接違反 issue #9 共同規則第 1、2 條。

### 問題 4：測試只驗結構，不驗數值

`timeline.txt` 的致命一擊傷害數字是錯的（4 次擊殺中 3 次），34 個測試全綠。

`test_timeline.py` 只檢查 `"attacked"` 這類關鍵字有沒有出現，不比對任何數字與 `event_memory` 的對應欄位。四個 exporter 的測試都是這個模式。

**這個缺陷至今未修，而且盲點還在。**

---

## 5. 根本原因

上面四個問題不是四件獨立的事，背後是三個共同的結構性成因。

### 成因 1：契約只凍結了 event shape，沒凍結模組介面

issue #9 花了整份文件定義 event 的 17 個欄位，做得很好。

但它**沒有定義 exporter 的函式簽名**，也沒有定義 `result_package` 該有哪些欄位。

於是：

```text
event 的形狀    →  三個 section 完全對得上
exporter 的形狀 →  一個寫成腳本、一個寫成函式，runner 兩個都接不上
result_package  →  沒人負責，缺了 initial_world_state 也沒人發現
```

**凍結資料形狀防住了資料不相容，但沒防住介面不相容。**

### 成因 2：沒有人負責整合，Done Criteria 也不涵蓋整合

每個 section 的 Final Done Criteria 都只檢查自己那一半：

```text
#7 第 5 條   replay_state_at_tick.json generated
#8 第 5 條   timeline.txt generated after full Phase 4 integration
```

「generated」是檔案存在，不是內容正確。而「full Phase 4 integration」沒有指定由誰執行、如何驗證。

結果是**每個 section 都誠實地通過了自己的驗收，而整體是壞的**。沒有任何一條標準會在這種情況下變紅。

### 成因 3：測試的對象從一開始就選錯，而且沒人質疑

四個 section 獨立寫測試，卻不約而同都用了「讀輸出檔」的模式。

這不是巧合 —— 它是最直覺的做法：跑一次程式、看看檔案、寫個 assert。問題是**這種測試無法區分「程式對」與「磁碟上剛好有正確的檔案」**。

沒有人在 review 時指出這件事，因為當時它們全都是綠的。

---

## 6. 下一階段要改的事

### 改法 1：契約要包含介面，不只包含資料

下一個 phase 的共同 issue 除了凍結資料形狀，還要凍結：

```text
每個新模組的函式簽名（收什麼、回傳什麼）
共用資料結構的完整欄位清單（例如 result_package）
```

如果 Phase 4 的 #9 有寫「exporter 一律是 `def build_x(data) -> data`」，問題 1 與 3 都不會發生。

### 改法 2：Done Criteria 要有「整合」這一條，而且要指定執行者

在每份 issue 的 Final Done Criteria 加上：

```text
N. 跑完整條 pipeline，打開產生的檔案確認內容正確
   （檔案存在不算，要實際讀內容）
N+1. 由 <指定的人> 在合併前執行上述驗證
```

「檔案存在」與「檔案正確」是兩件事，這句話要寫進驗收標準，不能只存在於口頭。

### 改法 3：測試必須驗數值，不能只驗結構

新增一類斷言，直接對照 truth source：

```python
def test_timeline_damage_matches_event_memory():
    result_package = _run_reference_scenario()
    text = render_timeline(
        result_package["scenario_id"], result_package["event_memory"]
    )
    for event in result_package["event_memory"]:
        if event["event_type"] != "ATTACK":
            continue
        assert f"(damage = {event['data']['damage']})" in text
```

這個測試在現在的程式碼下**會失敗** —— 它抓得到問題 4 的缺陷。這就是「有效的測試」與「會過的測試」的差別。

### 改法 4：測試不得讀 `output/`

寫進共同規則。自我檢查一行：

```bash
grep -rn "open(" tests/
```

任何一筆指向 `output/` 就是在測檔案系統。

---

## 7. 沒有結論的一項

**問題 4 的缺陷決定不修，留到後續階段。**

這是明知有錯而選擇出貨。記錄在此是為了讓後面的人知道這是**已知的取捨**，不是沒發現。

代價：`timeline.txt` 目前有 3 行數字是錯的，而且沒有測試會在它擴散時發出警告。

---

## 8. 一句話

> Phase 4 的資料契約做對了，介面契約沒有做；每個人都通過了自己的驗收，沒有人驗收整體；測試檢查了形狀，沒有檢查內容 —— 三件事各自看都不嚴重，加起來讓一個功能完整的階段在合併時失效了一輪。
