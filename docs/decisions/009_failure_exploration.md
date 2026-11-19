# 009 — Failure Exploration 與 schema 0.6

狀態：已採納
日期：2026-11-08
階段：Phase 9 — Failure Exploration Engine v0.9

## 背景

開發計劃 Phase 9：讓 SKYVAULT 故意讓方案失敗、找出弱點。功能是 failure_variables、四個 stress level、fault injection、branch search、sensitivity analysis、collapse sequence detection、failure map、recommended modifications；初期變量八個；輸出四個檔；驗收六條：給定一個方案，能跑出它在哪裡失敗、為什麼、哪個變量壓垮、哪個替代方案撐更久、現實前必須改什麼。

開設時先量了三件事：v0.1 在 seed 42–71 只有 63% 不被判 fail、RED 只贏 7%；壞天氣讓不被判 fail 的比例升到 93%；把支援組放後方的替代部署升到 83%。這些數字決定了「失敗」的定義與分析方式。

issue #23 第 6 節在寫程式之前列出了十四項決定。這份 ADR 記錄那十四項，以及開發中做的六項。**沒有惡化時模擬行為不變**：reference trace 不變。

## 決定

### 1. 方案 = scenario 版本 + evaluation profile + perspective

Spec 沒有定義「方案」。在 SKYVAULT 裡能被評估的單位就是一個 scenario 在一個 profile 下、從一個陣營的角度的結果，所以這三者合起來就是方案。

### 2. 失敗 = verdict 為 fail

「失敗」交給 profile 決定（Phase 7 的判斷規則），failure exploration 不另訂一套。存活率 = 非 fail 的 run 的比例。後果是：在 balanced 下，一場誰都沒打死誰的平局會因為 mission_success 為 0 而被判 fail —— 通訊全斷時方案「癱瘓」而失敗，不是被殲滅。

### 3. 八個變量都是 scenario 轉換

現有模型沒有感測、通訊、天氣，只有能力值、hp、資源與 action。**每個變量都是一個 scenario 轉換**，改的只有這些東西；強度表見 architecture.md。沒有對應目標的變量（沒有資源的世界裡的 supply_delay、resource_shortage）回報「不適用」與原因，不假裝施加了壓力。

這也意味著變量是近似：sensor_failure = 己方命中率下降、weather_degradation = 全體命中率下降、civilian_pressure = 己方起始 hp 下降。記為已知限制。

### 4. 四個固定等級

Spec 的 stress_levels 是 `{mild: {}, ...}`。強度由 failure engine 的表決定，scenario 的設定只列要跑哪幾級。讓每個 scenario 自訂強度，會讓不同 scenario 的「severe」無法比較。

### 5. 通訊失效用 fault injection

八個變量中只有通訊失效無法用改數值表達。**`rule_set.faults.drop_actions = {faction, rate}`**：該陣營的 action 在 validate 之前以 rate 的機率被拒，原因「Communication failure: order not received」。

它用獨立的 `Random("faults:<seed>")`。這樣注入失效不會讓主 rng 的抽取順序改變 —— 否則通訊失效的效果會混入「整場戰鬥的擲骰全部錯位」，分不清是哪個造成的。測試證明：rate 0 的 faults 下 trace 與 reference 完全相同。

### 6. 惡化後的 scenario 是新版本

`scenario_version = "<原版>+<變量>:<等級>"`，`version_control.parent_version` 指回原版，`changed_from_previous` 由 `compare_scenarios` 算出 —— Phase 8 handoff 的建議。這讓每個惡化 run 都帶著完整的 reproducibility 區塊與可比較的版本紀錄。

### 7. repeat 用 controlled_random

第 i 次 repeat 的 seed = 原 seed + i。fixed 則每次同一個 seed（因為決定性，重複等於沒重複；照實執行）。

### 8. sensitivity 與 crushing variable

sensitivity = 基線存活率 − 最差等級的存活率。**它可以是負的**：weather_degradation 在 v0.1 上就是（severe 時存活率 1.0 > 基線 0.6），因為壞天氣讓雙方都打不中。crushing variable 是 sensitivity 最大者，同分取較早崩潰者，再同分取名稱。

### 9. breaking_level

第一個存活率 < survival_threshold（預設 0.5）的等級；都沒有就是 null。基線本身低於門檻時，failure map 的 `fails_without_stress` 為 true，建議的第一條就是「不加壓就已經失敗」。

### 10. 分支 = 兩個最敏感的變量在 moderate

Spec 的 branch_comparison。只取 sensitivity > 0 的前兩名；不足兩個就不跑。moderate 不在要跑的等級裡時用第一個等級。

### 11. 替代方案 = 同 scenario 的其他版本

設定列出版本號，在版本資料夾裡找。每個替代方案跑同樣的掃描（不跑分支），依各變量的崩潰等級與基線存活率比較，給 holds_longer / breaks_sooner / mixed / same。best_alternative 是 holds_longer 中整體存活率最高者。

### 12. 每個變量對應一個假設

failure map 要說「哪個假設害死」。每個變量標註它攻擊的 assumption：weather / sensor / overheat / enemy → combat_resolution；communication → actor_policy；civilian → force_availability；supply / resource → resource_model。前兩個名字對應 reference 的 assumption_registry 裡實際存在的鍵。

### 13. 四個輸出；failure map 是第 13 份契約

failure_map.json 通過 `FailureMap` 契約；collapse_sequence.json、survival_conditions.json 是它的視圖；recommended_modifications.md 是 Markdown。

### 14. failure_variables 必填；schema 0.6

ADR 004 承諾 Phase 9 把 World Contract 的 failure_variables 改為必填。只能是八個變量名。scenario.failure_exploration 從 `dict` 變成正式的契約形狀，而且只能探索 world contract 列出的變量。

### 15. compare_scenarios 不再比較 failure_exploration（修正 ADR 008 第 11 點）

v0.1 加上 failure_exploration 後，`compare_scenarios(v0.1, v0.2)` 把它的缺席報成 failure_variables_changed，v0.2 的 version_control 就對不上了。failure_exploration 是「怎麼壓力測試這個 scenario」的請求，不是 scenario 所描述的世界。**從比較類別中移除**；`world_contract.failure_variables` 仍在。ADR 008 凍結，以本點為準。

### 16. 契約驗證後要補回預設值

`check()` 只回傳呼叫端提供的欄位（Phase 1 的設計：驗證不改變形狀）。所以驗證過的 exploration 設定裡，沒寫的 `branch_comparison`、`alternatives` 根本不存在，第一版 explore 因此 KeyError。`explore_failures` 在驗證後明確補上契約的預設值。

### 17. 分析放在純函式，跑 run 的放在 engine 之上

variables（scenario 轉換）與 analysis（統計）都不 import engine；explore 建 engine，與 verification 同層。所以 failure map 的所有規則都能用手造的 run 測試，不必真的跑模擬。

### 18. 替代方案只換部署

v0.1-support-rear（步槍兵前移到 [1, 1]、支援組到 [0, 0]）與 v0.1-spread（支援組到 [0, 2]）。tactical policy 是固定的，能換的方案只有部署與編組；這兩個是開設時量過、確實有差異的選擇。

### 19. runtime_version 升為 0.9.0；版本測試不再寫死

依 ADR 008 的慣例調升。版本測試原本斷言 `"0.8.0"`，每個 Phase 都得改；改為斷言 `skyvault.__version__`、pyproject 與 package 的 runtime_version 三者一致。

### 20. 測試資料要讓規則「非它不可」

反向驗證時兩個變異存活：拿掉「同分取較早崩潰者」、拿掉「替代方案基線存活率較高」。依 Phase 3 回顧改法 2 找反例：前者的測試資料剛好讓名稱順序與崩潰順序一致；後者沒有任何測試讓替代方案的基線勝過方案。兩者都是測試缺口，已補上讓規則「非它不可」的資料。

## 後果

```text
好處    給一個方案，就能得到它在哪裡、為什麼、多快、被什麼壓垮，以及哪個替代方案撐更久
        每個惡化 run 都是可重現、可比較的 scenario 版本
        分析規則可以完全脫離模擬測試
代價    變量是現有模型上的近似，不是真的感測 / 通訊 / 天氣模型
        reference 設定一次 760 個 run，約 12 秒；更大的探索需要 Phase 10 的平行化
```
