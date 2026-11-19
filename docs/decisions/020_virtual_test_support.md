# 020 — Star Guard Virtual Test Support：物理可能性、工程可行性、戰術價值的三重篩查

狀態：已採納
日期：2026-11-08
階段：Phase 16 — Star Guard Virtual Test Support v1.6

## 背景

開發計劃 Phase 16：EXO / PAX / MSX / ERX / 載具在實體原型前的 virtual test —— Physical Possibility → Engineering Feasibility → Tactical Usefulness；SKYVAULT 不取代 CAD / CAE / FEA，而是做前期篩查。技術：physics-lite rule model、constraint solver、surrogate model、external simulation adapter、FMI / FMU later。輸出：三個分數、failure_points、redesign_triggers、require_external_simulation flag。驗收五條：輸入一個 EXO / PAX / MSX profile；判斷大致物理是否合理、工程是否值得投入、任務中是否有價值、在哪些條件下會失敗。

開設時的測量：四份 profile（data/virtualtest/profiles/，§18 的形狀）經 Phase 15 的 STAR GUARD adapter 替換 military_squad_001 的 red_02 —— 四份全部 feasible、與 baseline 完全相同（被替換的單位保持步槍兵的數值）、每份 7 個缺口。一台 20 噸、15 m、500 kW、續航 8 h 的 profile 也是 feasible、任務達成率 100%。軍事 pack 沒有能量、疲勞或散熱，地形對所有單位都一樣。

issue #34 第 6 節在寫程式之前列出了十九項決定。這份 ADR 記錄那十九項與開發中的十六項。**模擬行為不變**：reference trace 與六個 output_hash 不變；軍事、city、airspace 的 run 在沒有新能力時一步都不變。

## 決定

### 1. 新的一層 virtualtest/

在 engine 與 batch 之上，與 failure/ 同層：profile、physics、engineering、solver、stress、external、judgement（純函式，不跑模擬，測試逐檔檢查）、tactical、surrogate、report、run。core 不 import 它（interface 除外，測試）。

### 2. 兩份契約

equipment_profile、equipment_test_result（第 24、25 份），照 §18 的形狀；SCHEMA_VERSION 0.6 之內只新增。profile 的 capabilities / state 是 Phase 12 的路徑，保留。

### 3. 增補的物理參數

§18 的 physical_parameters 算不出穩定與能量收支：增補 base_width、footprint、load_bearing_joints、energy_capacity、cooling_capacity。每個參數都是 optional。

### 4. 類別與規則

data/virtualtest/rules.json：每個類別的動態負載係數、最小穩定比、尺度密度範圍、hp 係數；地形承載；門檻；工程權重；戰術對應；壓力條件。不認識的類別 → 外部仿真。

### 5. 六條 physics-lite 規則

stability（(base_width/2) / center_of_gravity 對類別最小值）、joint_load（m·g·動態係數 / 一半的支撐關節）、ground_pressure（m·g / footprint 對 open 的承載）、energy（energy_capacity 對 power × endurance）、heat（cooling 對 heat_output）、scale（mass / height³ 對類別範圍）。每條輸出 margin：可用量 / 需要量 − 1。

### 6. 狀態與分數

margin < 0 → impossible（heat 在 duty ≥ 0.5 時、scale 一律是 warning）；< 0.25 → warning；缺輸入 → unknown（列出，不算通過）。分數是已知 margin 的 0.5 + m（夾在 0–1）的平均；任何 impossible → 0。

### 7. 工程

material、maintenance（1 / (1 + 維修時間 / 續航)）、parts、supply（1 − risk）、repair，加權平均。「值得投入」= ≥ 0.5；缺的成分不算進平均，列為風險。

### 8. 戰術對應

profile 替換一個軍事單位（STAR GUARD 指名的，或角色對應的第一個 RED 單位）：hp × 類別係數、move_range 依功率質量比 ±1、命中依疲勞（見第 20 點）、地形 = 承載與高度推得的地形 ∩ profile 宣告的、endurance_ticks = 有效續航（一個軍事 tick 記為 10 分鐘 —— 假設）。

### 9. 軍事 pack 的兩個可選能力

terrain_access：只能進入與穿越列出的地形（拒絕理由「Move target is impassable for this unit」）；endurance_ticks：超過後不能移動與攻擊（「Insufficient endurance: power spent」）。兩者都以 Phase 12 的 capability limit 前綴開頭。沒有時一步都不變（六個 hash、新測試）。

### 10. 戰術價值

四個軍事 scenario × 5 個 seed，裝備 vs baseline：分數、任務達成、單位存活的差；useful / weak（見第 21 點）；分數 = 0.5 + 2·Δscore + 0.5·Δmission 的平均；logistics_burden 由運輸、維修、部署時間、供應鏈計點。

### 11. surrogate

profile 與六個變體（mass、power、energy 各 × 0.8 / 1.2）在一個 scenario 上跑戰術，numpy 最小平方擬合 Δscore；回報 r²、範圍；範圍外的預測標 out_of_range。用來預測 redesign 後的戰術價值而不重跑。

### 12. 壓力條件

payload、heat、soft_ground、extended_mission、supply_disruption × 四級，重算物理與工程（不跑模擬）。

### 13. failure points 與 collapse sequence

每個條件在哪一級「新」斷了什麼（已經斷的不算新）；全部一起加壓時依序斷掉的限制。

### 14. constraint solver

scipy.optimize.brentq：每條 impossible 的限制求到 margin 0、warning 求到 0.25，參數依限制而定（base_width、joint_load、footprint、energy_capacity、cooling_capacity）；mass_limit 求最大質量。

### 15. 外部仿真

margin 在 ±0.1 之內、scale 超出、類別不認識、缺參數 → required；adapter 是 protocol，替身回報 not_run 與問題，不編造結果。FMI / FMU 之後接在同一個呼叫後面。

### 16. final_judgement

reject（不可能且工程 < 0.3，或修正要改超過 50%、或沒有槓桿）→ redesign（不可能但改得到、工程不足、沒有任何有用的任務）→ require_external_simulation → continue。

### 17. 每一種輸入

四份 profile、STAR GUARD 提交（含舊式 profile）、world service（run_submission）、軍事 scenario run、壓力條件都跑過並讀過輸出。

### 18. 邊界值

質量 0、高度 0、續航 0、功率 0、footprint 0、重心 0、發熱 0、只有 id 的 profile、不認識的類別（測試）。

### 19. 模擬不變

reference RED_survived / 97、output_hash 63090026e137；六個 output_hash 的常數測試不變。

## 開發中的決定

### 20. 疲勞相對於步兵

第一版：命中 × (1 − 疲勞 × 時數 / 2)。讀戰術輸出時看到 EXO（疲勞 0.08 / h）的命中比被替換的步槍兵還低 —— baseline 的步兵本身沒有疲勞模型，任何疲勞都變成懲罰。改為相對於 infantry_fatigue 0.1：累得比步兵慢就加分（上限 ×1.2、命中 0.95）。

### 21. 「有用」也包括任務達成率上升

ERX（後勤機器人）在 urban 讓任務達成率 +0.2、分數只 +0.01 → 第一版判為「既不有用也不無用」。任務更常達成、分數沒有掉超過門檻，也算有用。

### 22. seed 從 3 增為 5

3 個 seed 時同一份 profile 的有用 / 無用情境在重跑間浮動；5 個 seed 的時間仍可接受（四份約 20 秒）。

### 23. 質量 0 的尺度

邊界測試找到：mass 0 → 密度 0 → 除以零。massless 設計的 scale margin 為 −1（超出任何範圍 → 外部仿真）。

### 24. 報告的分數三位小數

PAX 的工程分數 0.4961 在兩位小數下顯示為 0.50 —— 剛好是「值得投入」的門檻、但它沒達到。報告與腳本改為三位小數。

### 25. 「沒有新的失敗」

MSX 的 payload 條件在報告上寫「撐得住」—— 其實是關節本來就已經不可能，加重不會「新」斷什麼。改寫為「nothing new fails under」並指向上方的 impossible。

### 26. redesign trigger 標明目的

warning 也有 trigger（解除警告），impossible 的 trigger 是「讓它可能」；報告分開寫，避免讀者以為 PAX 的關節是不可能。

### 27. solver 的捨入方向

brentq 的解可能差一點點：required 向上取到 4 位、mass_limit 向下取到 3 位 —— 給出的數字代回去一定滿足（測試）。

### 28. surrogate 的範圍與常數

redesign 後的電池剛好是 × 1.2 —— 浮點差 4e-7 讓預測被標為範圍外；範圍邊界容許 1e-4。量測完全不變時 r² 為 1（第一版因浮點得到 −2）。

### 29. EXO fixture 的兩個數字

fixture commit 後量到 EXO 的能量與散熱 margin 都剛好 0.25 —— 浮點決定它是 pass 還是 warning。energy_capacity 6.0 → 6.5、cooling 1.0 → 1.1（與開發一起 commit，記錄於此）。

### 30. 用完續航的單位停在原地

baseline policy 不對 exhausted 的單位下令；但指揮延遲讓之前下的命令在耗盡後才抵達 → 被拒絕，在 STAR GUARD 的 capability_limits 裡看得到（PAX 在 tick 16）。這是預期的：它說的是「電池在任務中途耗盡」。

### 31. STAR GUARD 的 virtual_test

profile 帶 §18 群組時，adapter 用同一套對應改單位，返回多一個 virtual_test（同一個 scenario、同一組 seed、同一個被替換的單位 —— 測試斷言兩邊分數相同）。缺口訊息改為指出 §18 的三個群組。

### 32. 戰術比較用被替換單位的陣營

不是固定 RED：STAR GUARD 可以替換 BLUE 的單位。

### 33. scipy 與 scipy-stubs

scipy 宣告為相依（計劃點名 constraint solver）、numpy 明列；mypy 用 scipy-stubs。

### 34. Phase 12 的缺口測試

「has no model before Phases 14-16」的文字已不成立，測試改為新文字。

### 35. runtime_version 升為 0.20.0

## 後果

```text
好處    一份 profile 就拿到三重判斷與理由：物理（哪條規則、差多少）、工程（瓶頸）、任務（哪裡有用、哪裡沒用）
        在哪些條件下、按什麼順序垮掉；要改到多少才行（solver 的數字代回去剛好通過）；什麼時候需要真正的仿真
        STAR GUARD 的提交不再有缺口；軍事 pack 多了地形限制與續航，其他 domain 也能用
代價    physics-lite 的每個係數都是篩查假設，不是工程值；一個軍事 tick = 10 分鐘也是假設
        戰術價值只在既有的四個軍事 scenario 裡測；武器與裝甲沒有新模型（hp 係數代表）
        FMI / FMU 尚未接上；surrogate 只是三個參數的線性模型
```
