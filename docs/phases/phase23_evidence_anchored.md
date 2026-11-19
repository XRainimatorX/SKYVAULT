# Phase 23 — Evidence-Anchored Coefficients v2.3

issue：[#39](https://github.com/XRainimatorX/SKYVAULT/issues/39)
決定：[ADR 025](../decisions/025_evidence_anchored_coefficients.md)
runtime：2.3.0

---

## 1. 這個階段做什麼

使用者問「係數是手調的」是什麼意思，並要求搜尋真實資料來校準。信息環境、災害、重建三個城市模型的係數，原本是在幾個 seed 上跑出合理行為的手調值。

公開研究沒有能直接擬合的時間序列，論文全文也讀不到（網路擋住學術網站），只有搜尋摘要可用。所以本 Phase 改做**以型態定錨**：

- 每個係數說得出它從哪裡來、有多可信。
- 有研究依據的係數照研究調整，並用測試確認模型重現研究結果。
- 用敏感度分析找出哪些係數錯了會改變結論。

## 2. 這次執行發生了什麼

### 係數登記檔

`data/domains/city/calibration.json` 共 29 個係數：1 anchored、5 derived、23 assumed，引用 17 個來源。`skyvault calibration` 印出每個係數的值、可信度、重要度，以及哪些需要先找資料。

### 有錨點的調整

| 係數 | 舊 | 新 | 研究 |
|---|---|---|---|
| 變電站修復 | 3 步 | 4 步（1 天） | HAZUS-MH 輕微損壞約 1 天 |
| 被摧毀的工業產能 | 沒有這個機制 | 每步重建 0.0002 | Katrina 後 26 個月約 65% 企業重新開業 |
| 洪水斷電 | 不斷電 | 淹水的區停電 | 2021 德國洪水，97% 受災診所停電 |
| 洪水封路 | 任何嚴重度 | 嚴重度 ≥ 0.6 | 道路淹水 ≥ 60% 不可通行 |
| 反制訊息 | −12 點 | −14% 的壓力 | 澄清真實世界錯誤訊息的效果 r = .14 |
| 停電對壓力與治安 | 整步 | 乘上夜間比例 | 開普敦：停電只在夜間影響犯罪 |

### 行為改變（舊 → 新，5 個 seed）

| scenario | 舊 | 新 | 原因 |
|---|---|---|---|
| city_blackout_001 | 5 個 seed 全是 order_not_restored，治理分數 0.51–0.59 | 1 個 seed 變成 order_restored，0.55–0.70；變電站各晚 1 tick 恢復 | 停電只在夜間扣治安；修復 4 步 |
| city_reconstruction_001 | 工業期末 0.53–0.68 | 0.11 | 戰爭摧毀的是產能；10 天只能重建 0.008 |
| city_takeover_001 | 不變 | 不變 | 沒有停電、災害 |
| urban_crisis_test_001 | order_not_restored | 仍是 order_not_restored；電力晚 6 小時恢復，Harbor 淹水期間停電 | 洪水斷電、修復 4 步 |

重建城市的變化是校準最大的影響：原本 40 tick 內工業就回到六成，現在依 Katrina 的速度，10 天幾乎看不到重建。這比較接近現實，但也表示這個 scenario 量得到的「恢復」主要是電力、醫療、行政和補給，不是工業。

### 敏感度分析

完整結果見 ADR 025 第 7 節與 `data/domains/city/sensitivity.json`。重點：

- 會翻轉結論的只有 `recovery.administer` 和 `order.dark`，兩個都是 assumed，是最需要先找資料的項目。
- 信息環境的 11 個係數都不翻轉結論。

### 測試與閘門

- 新測試：
  - `tests/domains/city/test_calibration.py`（12 條）：登記檔與規則一致；五個錨點型態；每個城市帶著係數的來源。
  - `tests/domains/city/test_sensitivity.py`（4 條）：報告與重新計算的結果一致。
  - `test_cli` 的 calibration 指令。
- 改動的舊測試：
  - 停電城市的趨勢窗口（6–9 → 8–14）
  - 停電城市的 §8.3 分數（0.4691 → 0.5028）
  - 洪水封路要嚴重度 ≥ 0.6
  - 火災也燒掉產能

## 3. 範圍內做完的事

```text
步驟 S  calibration.json；rules.json 加入 information_defaults、disaster_effects、time、recovery.rebuild；registry_problems
步驟 T  六項有錨點的調整；工業產能（industry_capacity）；夜間比例；五個型態測試
步驟 U  每個城市 scenario 的 assumption_registry / data_provenance 帶係數；sensitivity.py；skyvault calibration
步驟 V  ADR 025、本報告、回顧、README / architecture / handoff、runtime 2.3.0
```

順帶：`output/external/` 從 Phase 22 改了 §9.2 的返回項目後就沒有重新產生，本 Phase 一起重新產生。

## 4. 這一輪發現的問題

1. **研究的單位和模型的單位對不上。** 大部分研究給的是機率變化或相關係數，模型是 0–100 的分數。29 個係數裡只有 6 個換算得過去。其餘的硬換算會變成假精確，所以誠實標為 assumed。
2. **一個數字描述了兩件事。** `industry_up` 同時代表停電後恢復生產和實體重建。Katrina 的數字只適用後者，直接套用會讓停電後永遠恢復不了生產。所以把產能（`industry_capacity`）拆出來。
3. **最不確定的係數不一定是最重要的。** 信息環境的係數全是 assumed，但都不翻轉結論。真正翻轉結論的是 Phase 14 的 `order.dark` 和 `recovery.administer`。如果沒有敏感度分析，會把找資料的力氣花在錯的地方。
4. **網路限制。** 論文全文讀不到。登記檔的每個來源都標明 `read_from: search abstract`，可信度的上限也因此壓低（provenance 0.5）。

## 5. 驗收怎麼確認

- `registry_problems(rules, calibration) == []`，並有反例：值不同、範圍外、未知來源、未列入的係數各一。
- 五個型態測試重新跑模型，確認重現研究結果。
- 敏感度報告的基準與一個係數重新計算的結果逐位元相同（報告過期就失敗）。
- `skyvault acceptance` 仍是 ACCEPTED。

## 6. 已知限制

| 項目 | 影響 |
|---|---|
| 23 個係數仍是假設 | 方向有些有研究支持，數值沒有 |
| 來源只讀了摘要 | 換算可能漏掉全文的條件；網路允許時要讀全文核對 |
| 研究來自不同國家與事件 | Katrina、德國、開普敦、巴基斯坦，不是 scenario 的城市 |
| HAZUS 修復時間來自地震 | 洪水或戰損的變電站可能不同 |
| 敏感度分析一次只動一個係數、每組 3 個 seed | 係數之間的交互作用沒有量 |
