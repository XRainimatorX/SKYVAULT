# 025 — Evidence-Anchored Coefficients：城市模型係數以公開研究定錨

狀態：已採納
日期：2026-11-19
階段：Phase 23 — Evidence-Anchored Coefficients v2.3（使用者於 2026-11-19 加入）

## 背景

Phase 22 的已知限制：信息環境、災害、重建三個城市模型的係數是手調的預設值，挑選方法只是在幾個 seed 上跑出合理行為。使用者要求搜尋真實資料來校準。

開設時的測量（issue #39）：

- 公開研究**沒有能直接擬合的時間序列**。模型用 0–100 的抽象分數，研究給的是比例、機率變化、恢復天數。
- 這個環境的網路擋住學術網站，論文全文讀不到，只有搜尋結果的摘要可用。

## 決定

### 1. 以型態定錨，不做擬合

每個係數記下來源、換算方法和可信度。有研究依據、單位換算得過去的才照研究調整，並用測試確認模型重現研究結果。其餘標為假設，交給敏感度分析找出它們對結論的影響。

### 2. 係數登記檔

`data/domains/city/calibration.json` 每個係數一筆，共 29 筆，涵蓋：

- `information_defaults`、`disaster_effects`、`recovery`、`repair` 四組的全部係數
- `order.dark`

每筆的欄位：

| 欄位 | 內容 |
|---|---|
| value、unit | 值和單位 |
| confidence | 可信度，分三級（見下表） |
| finding | 研究結果；沒有就寫「None found」 |
| sources | 來源 |
| method | 換算方法 |
| range | 敏感度分析掃描的範圍 |
| criticality | 由敏感度分析填入 |

| 可信度 | 意思 | 筆數 |
|---|---|---|
| anchored | 研究數值可以直接換算 | 1 |
| derived | 研究數值經過一個寫明的換算假設 | 5 |
| assumed | 沒有研究給出數值，有些只支持方向 | 23 |

時間換算：一步 = 6 小時，即 Formal Spec 2.3 的 phase。tick 時鐘的城市也以 6 小時換算，這一點記為假設；tick 時鐘沒有一天中的時刻，每個 tick 算一半是夜間。

### 3. 規則是唯一的執行來源，登記檔必須一致

- `rules.json` 新增 `information_defaults`、`disaster_effects`、`time` 三組，以及 `recovery.rebuild`。
- `information.DEFAULTS` 和 `disasters.EFFECTS` 只在規則沒寫這兩組時才用，測試守護它們的值與規則相同。
- `registry_problems` 列出三類不一致：登記檔與規則的值不同、值不在範圍內、規則裡有係數但登記檔沒有。
- 規則與登記檔不一致的城市，在 world 的 assumption_registry 記為 custom，也不聲稱任何係數來源。

### 4. 有錨點的係數（舊 → 新）

| 係數 | 舊 | 新 | 依據 |
|---|---|---|---|
| `repair.failure_ticks` | 3 | 4 | 依 HAZUS-MH，變電站輕微損壞修 1 天（24 小時 / 每步 6 小時） |
| `recovery.rebuild`（新） | — | 0.0002 / 步 | Katrina 後 26 個月約 65% 企業重新開業 |
| `disaster_effects.flood.power_cut_at`（新） | 洪水不斷電 | 淹水的區停電 | 2021 年德國洪水，97% 受災診所停電 |
| `disaster_effects.flood.road_cut_at`（新） | 任何嚴重度都封路 | 嚴重度 ≥ 0.6 才封路 | 道路淹水 ≥ 60% 不可通行 |
| `information_defaults.counter_share` | 固定 −12 | 移除 14% 的壓力 | 澄清訊息對真實世界錯誤訊息的效果 r = .14 |
| 停電對壓力和治安的影響 | 整步 | 乘上這一步的夜間比例 | 開普敦研究：只在夜間影響犯罪 |

`recovery.rebuild` 是新的工業產能機制：

- 區有 `industry_capacity`（產能）。戰爭或火災摧毀的產能以 rebuild 的速度重建。
- 工業產出以 `industry_up` 恢復，但不超過產能。
- 這樣分開是因為 Katrina 的數字描述的是實體重建，不是停電後恢復生產。
- 重建 scenario 的工業起點就是被戰爭摧毀後的產能。

### 5. 每個城市 scenario 帶著係數的來源

- scenario 的 assumption_registry（§11.2）：每個係數一條 assumption。confidence 換算為 anchored 0.7、derived 0.5、assumed 0.3；criticality 來自敏感度分析；high 的係數列進 critical_assumptions。
- data_provenance（§11.3）：每個用到的來源一條，可信度 0.5（只讀了摘要）；未知的數值逐項列在 missing_data。
- world 的 assumption_registry：`coefficients` 記登記檔版本和三級的數量。

### 6. 敏感度分析

`domains/city/sensitivity.py`：把每個係數推到範圍的兩端，一次只動一個，四個參考城市各跑 3 個 seed。比較兩種結論：

- 每個 scenario 多數決的結果
- 接管四方案中治理分數最高的方案

判定：

- **high**：任一端翻轉了結論
- **medium**：任一 scenario 的平均治理分數移動 ≥ 0.05
- **low**：其餘

可信度 assumed 又是 high 的係數，就是最需要先找資料的項目。結果存在 `data/domains/city/sensitivity.json`，`skyvault calibration` 印出來，`--sweep` 重新計算。

### 7. 敏感度分析的結果

基準結論：

- 停電城市：order_not_restored
- 重建、接管城市：order_restored
- 危機城市：order_not_restored
- 接管最佳方案：談判，治理分數 0.86；強攻 0.84、先恢復供應 0.84、封鎖 0.64

| 係數 | 可信度 | 重要度 | 結果 |
|---|---|---|---|
| `recovery.administer` | assumed | **high** | 0.1 時停電城市翻成 order_restored |
| `order.dark` | assumed | **high** | 0（德州研究：停電無影響）時停電城市翻成 order_restored |
| `repair.failure_ticks` | derived | medium | 12 步（中度損壞）時治理分數移動 0.30，不翻轉結論 |
| `recovery.administration_down` | assumed | medium | 0.04 時治理分數移動 0.08 |
| 其餘 25 個 | — | low | 不翻轉結論，治理分數移動 < 0.05 |

最需要找資料的是 `recovery.administer` 和 `order.dark`，兩者都是 assumed 且會翻轉結論。

信息環境的 11 個係數在參考城市裡都不翻轉結論，原因有兩個：

- 信息模型只在危機城市和強攻方案裡開啟。
- 它對治安的拉力（`order_weight`）比糧食、電力、行政小。

所以這些係數的不確定性目前不影響結論；但信息模型若用在更依賴輿情的世界，要重新跑這個分析。

## 後果

- 城市的行為改變（舊 → 新見完成報告第 3 節）。所有城市 scenario 的 output_hash 改變，已重新釘住。
- 不在範圍：
  - 用真實時間序列擬合（找不到這種資料）
  - Phase 14 城市秩序模型中與這三個模型無關的係數（hunger、patrol 等）
  - 論文全文核對
