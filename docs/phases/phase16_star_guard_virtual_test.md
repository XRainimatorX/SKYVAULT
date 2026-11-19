# Phase 16 — Star Guard Virtual Test Support v1.6

完成報告。這份文件是 Phase 16 結束時的凍結紀錄，寫完不再更新 —— 系統目前的樣子請看 [`../architecture.md`](../architecture.md)。

**狀態：功能完成，沒有已記錄未修的缺陷。**

---

## 1. 這個階段做什麼

Phase 16 開始前，STAR GUARD 的裝備 profile 只能覆寫被替換單位的 capabilities / state；物理、工程、作戰參數全部回報為缺口。「可行」只代表模擬裡沒有動作被能力限制拒絕 —— 一台 20 噸、15 公尺、續航 8 小時的機器也「可行」。

目標是開發計劃的原文：支援 EXO / PAX / MSX / ERX / 載具在實體原型前進行 virtual test support，做 Physical Possibility → Engineering Feasibility → Tactical Usefulness 三重篩查。規格依據是 [`../plan/phase16_star_guard_virtual_test.md`](../plan/phase16_star_guard_virtual_test.md) 與 Formal Spec §18、§19 D。

```text
Issue      #34 Phase_16_star_guard_virtual_test（milestone #18 Phase 16 — Star Guard Virtual Test Support）
開設       測量：四份 profile 全部 feasible、與 baseline 相同、每份 7 個缺口；不可能的裝備任務達成率 100%；
           fixture 先 commit：data/virtualtest/profiles/（EXO、PAX、MSX、ERX）
開發       virtualtest/（profile、physics、engineering、solver、stress、external、judgement、tactical、surrogate、report、run）；
           兩份契約；軍事 pack 的 terrain_access 與 endurance_ticks；STAR GUARD 的 §18 路徑；run_virtual_test；CI 的 Virtual test 步驟
```

十九項決定與開發中的十六項記錄於 [`../decisions/020_virtual_test_support.md`](../decisions/020_virtual_test_support.md)。

---

## 2. 這次執行發生了什麼

### 開設時的測量

```text
四份 profile      經 Phase 15 的 STAR GUARD 替換 military_squad_001 的 red_02：全部 feasible、versus_baseline 全為 0、每份 7 個缺口
不可能的裝備      20 噸、15 m、500 kW、續航 8 h、hp 400、move 8 → feasible、任務達成率 100%
軍事 pack         沒有能量、疲勞、散熱；地形對所有單位相同；tick 沒有時間長度
相依              scipy 1.17 / 1.15（3.10）可安裝；numpy 已隨 pandas 存在
```

### 四份 profile（5 個 seed × 四個軍事 scenario）

| profile | 物理 | 工程 | 戰術 | 判斷 | 為什麼 |
|---|---|---|---|---|---|
| EXO_TEST_001 外骨骼 | 0.955 | 0.773 | 0.484 | continue | 六條規則都通過；在 squad 有用、在 urban 變差 |
| ERX_TEST_001 四足機器人 | 0.966 | 0.834 | 0.561 | continue | 在 urban 讓任務達成率 +0.2 |
| PAX_TEST_001 動力裝甲 | 0 | 0.496 | 0.593 | redesign | 電池 15 kWh 撐不起宣告的 3 h × 6 kW；改到 18 kWh 就可能 |
| MSX_TEST_001 機動裝甲 | 0 | 0.214 | 0.523 | reject | 關節超過額定（−6%）、能量不足（−25%），工程分數 0.21（外來材料、每小時運轉 15 小時維修、工廠修理、供應鏈 80%） |

MSX 另外需要外部仿真：穩定（+0.07）、關節（−0.06）、散熱（+0.07）都在 ±0.1 之內。

### 驗收五條

| # | 開發計劃原文 | 如何證明 |
|---|---|---|
| 1 | 輸入一個 EXO / PAX / MSX profile | 四份 §18 形狀的 profile（契約驗證）；STAR GUARD 提交、world service、run_virtual_test 都收它；舊式 profile 仍可用 |
| 2 | 判斷大致物理是否合理 | 六條規則各有 margin；每個 impossible flag 都有造得出它與不會的 profile；缺參數是 unknown、不算通過；PAX 的 energy、MSX 的 joint_load 與 energy |
| 3 | 工程是否值得投入 | 五個成分加權；排序 ERX > EXO > PAX > MSX；PAX 0.496 低於 0.5（報告三位小數）；MSX 四個瓶頸 |
| 4 | 任務中是否有價值 | 裝備在每個 scenario 裡改變結果、與 baseline 逐項比較；EXO / PAX / MSX 都有有用與無用的情境；只能走 open / road 的 MSX 在山地變差；地形與續航真的被拒絕 |
| 5 | 在哪些條件下會失敗 | 五種壓力條件 × 四級：EXO 在 extended_mission moderate 斷（6.5 kWh 撐不起 7.2）、payload 要到 collapse；collapse sequence 依序列出；solver 給出改到多少（代回去剛好通過） |

### 每一種輸入

```text
四份 profile        run_virtual_test → output/virtual_test/；兩個 PYTHONHASHSEED 逐位元相同
STAR GUARD 提交     PAX：gaps 為空、virtual_test 判 redesign；電池在 tick 16 耗盡，延遲抵達的命令以
                    「Insufficient endurance: power spent」被拒 → feasible false
舊式 profile        沒有 §18 群組：行為同 Phase 12，沒有 virtual_test
world service       run_submission（SQLite store）
軍事 scenario       四個 scenario × 5 seed × 裝備 / baseline；沒有新能力的 run 一步都不變（reference trace 與六個 hash）
```

---

## 3. 交付了什麼

```text
src/skyvault/virtualtest/
  profile.py      load_rules、load_profile、reference_profiles、with_param、has_equipment_parameters
  physics.py      physical_possibility、margins、accessible_terrain、effective_endurance、ground_pressure_kpa
  engineering.py  engineering_feasibility、maintenance_ratio
  solver.py       solve、mass_limit、redesign_triggers（scipy.optimize.brentq）
  stress.py       stressed、explore_equipment（failure_points、collapse_sequence）
  external.py     ExternalSimulator protocol、StandInSimulator、external_simulation
  judgement.py    final_judgement
  tactical.py     replaced_unit、unit_changes、tactical_usefulness、logistics_burden
  surrogate.py    variants、fit、predict（numpy）
  report.py       virtual_test_report
  run.py          virtual_test
src/skyvault/contracts/equipment.py   equipment_profile、equipment_test_result（schema 匯出 25 份）
src/skyvault/domains/military/        terrain_access、endurance_ticks（terrain.py、handlers.py、policy.py）
src/skyvault/interface/systems.py     STAR GUARD 的 §18 路徑與 virtual_test 返回
data/virtualtest/（rules.json、units.json、四份 profile）
scripts/run_virtual_test.py → output/virtual_test/
pyproject.toml、ci.yml                scipy、numpy、scipy-stubs；Virtual test 步驟
skyvault.__version__                  0.20.0
```

---

## 4. 這一輪發現的問題

### 讀戰術輸出找到的

```text
EXO 的命中比步槍兵還低     baseline 的步兵沒有疲勞模型，任何疲勞都變成懲罰 → 疲勞相對於步兵（0.1 / h）
ERX 讓任務更常達成卻不算有用  只看分數差 → 任務達成率上升、分數沒掉超過門檻也算有用
同一份 profile 的情境浮動    3 個 seed → 5 個
```

### 以不看程式的讀者讀報告找到的

```text
PAX 工程 0.4961 顯示為 0.50    剛好是門檻、但沒達到 → 三位小數（報告與腳本）
MSX「payload 下撐得住」        其實是關節本來就不可能 → 「nothing new fails」並指向 impossible
PAX 的關節 trigger            看起來像不可能 → trigger 標明「讓它可能」或「解除警告」
```

### 測試與邊界找到的

```text
質量 0              scale 除以零 → massless 的 margin 為 −1
solver 的解差一點    brentq 的根代回去可能是 −1e-9 → required 向上取、mass_limit 向下取
surrogate           ×1.2 的電池被判範圍外（浮點 4e-7）→ 邊界容許 1e-4；常數量測 r² 得到 −2 → 1
EXO fixture         能量與散熱 margin 都剛好 0.25，pass / warning 由浮點決定 → 6.5 kWh、1.1 kW
```

### 反向驗證

22 個變異；第一輪兩個存活（維修比 1.33 的瓶頸沒有被斷言、「不值得工程」的 reject 被「沒有修正」的 reject 遮住）→ 各補一個走到邊上的測試 → 全部紅。

### 其他

```text
Phase 12 測試    STAR GUARD 的缺口文字「before Phases 14-16」→ 指向 §18 的三個群組
契約測試         EXPORTED_CONTRACTS 加兩份；schema 在 docstring 修改後過期一次（漂移測試抓到）
```

---

## 5. 品質狀態

| 項目 | 結果 |
|---|---|
| pytest | 1438 passed（有 Redis / PostgreSQL 時；沒有時 1369 passed、69 skipped）（Phase 15 為 1346） |
| Python 3.10 venv | 見第 7 節 |
| 從 /tmp 執行 | 通過（沒有服務：69 skipped） |
| 全專案覆蓋率 | 99%；virtualtest/ 每個檔案 100% |
| ruff / black / mypy / bandit | 通過（mypy 157 個檔案） |
| 跨 PYTHONHASHSEED | output/virtual_test/ 逐位元相同 |

### 測試分布

```text
tests/virtualtest/test_virtualtest.py           67   契約（6 種拒絕）；六條規則的公式、貼邊、違反、unknown；工程的成分與排序；
                                                     solver 代回去剛好通過、mass_limit；壓力每級不同、failure points、collapse sequence；
                                                     外部仿真的四種理由與 adapter；判斷的 10 種情況；8 種邊界；分層
tests/virtualtest/test_virtualtest_outputs.py   25   對應（hp、move、命中、地形、續航、覆寫）；軍事 pack 的地形與續航拒絕、policy 停下、
                                                     沒有新能力時不變；戰術比較；四份判斷；redesign 後不再不可能；外部仿真的觸發；
                                                     surrogate；STAR GUARD；報告；run_virtual_test
既有測試                                        1346  兩個測試改動（STAR GUARD 缺口文字、匯出的契約清單）
```

---

## 6. 已知限制

| 項目 | 留待 | 原因 |
|---|---|---|
| 係數是篩查假設 | 有真實資料時 | rules.json 的每個門檻與係數不是工程值 |
| 一個軍事 tick = 10 分鐘 | 需要時 | 軍事 scenario 本身沒有時間長度 |
| 戰術只在四個軍事 scenario 裡測 | 需要時 | 沒有空域或城市的裝備任務 |
| 武器與裝甲沒有新模型 | 需要時 | hp 係數代表防護；武器沿用被替換的單位 |
| FMI / FMU 未接上 | 計劃寫 later | adapter 介面與替身已在 |
| surrogate 是三個參數的線性模型 | 需要時 | 只在 profile 附近 ±20% 有意義（範圍外標明） |

---

## 7. 驗證

```bash
python3 scripts/run_tactical_reference.py         # RED_survived / 97；output 63090026e137
python3 scripts/run_virtual_test.py               # output/virtual_test/：四份結果與 virtual_test_report.md
python3 -m pytest tests/ -q
```

Python 3.10 venv（有 Redis / PostgreSQL）：1437 passed。

---

## 8. 一句話總結

> Phase 16 讓 SKYVAULT 在裝備造出來之前先問三個問題：外骨骼站得住、值得造、在小隊任務裡有用；動力裝甲的電池少了五分之一，改到 18 kWh 就行；十二公尺的機動裝甲關節撐不住、電池不夠、每運轉一小時要修十五小時 —— 不值得造，而且它離物理的邊線太近，要真正的工程仿真才說得準。
