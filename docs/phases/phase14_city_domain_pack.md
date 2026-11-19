# Phase 14 — Logistics / Governance / City Domain Pack v1.4

完成報告。這份文件是 Phase 14 結束時的凍結紀錄，寫完不再更新 —— 系統目前的樣子請看 [`../architecture.md`](../architecture.md)。

**狀態：功能完成，沒有已記錄未修的缺陷。**

---

## 1. 這個階段做什麼

Phase 14 開始前，SKYVAULT 只跑格子上的戰鬥：非格子的空間被 engine 拒絕，只剩一方就結束，補給延遲只是庫存打折，沒有電力、治安、行政，也沒有「治理穩不穩」的分數。

目標是開發計劃的原文：「做城市治理、補給、治安、停電、災害、戰後重建等世界」。規格依據是 [`../plan/phase14_city_governance_logistics_pack.md`](../plan/phase14_city_governance_logistics_pack.md) 與 Formal Spec §2、§14、§19 C。

```text
Issue      #32 Phase_14_city_governance_logistics_pack（milestone #16 Phase 14 — Logistics / Governance / City Domain Pack）
開設       圖空間被拒、只剩一方就結束且判 pass、supply_delay 只是打折、沒有電力與治安；
           fixture 先 commit：data/domains/city/scenarios/city_takeover_001.json、city_blackout_001.json
步驟 A+B   engine 的 pack 宣告（spaces、ends_with_last_faction、acts、finished、outcome_label、end_reasons）；
           city 的模型、builder、handlers、policy、score；success_outcomes 與 domain 結束原因
步驟 C     city 的 failure variables、batch 計勝負、NEXUS 的 domain_outcome、report、run_city、CI 的 City domain pack 步驟
```

十七項決定與開發中的十六項記錄於 [`../decisions/018_city_domain_pack.md`](../decisions/018_city_domain_pack.md)。

---

## 2. 這次執行發生了什麼

### 開設時的測量

```text
空間          reference scenario 搬到道路圖 → engine 拒絕；拿掉檢查 → 跑得完，55 個 event 中 36 個 NO_ACTION
只有一方      tick 1 結束、1 個 event、判定 pass、stability_impact 1.0
補給延遲      supply_delay = 庫存 × 0.9 / 0.75 / 0.5 / 0.25；沒有東西晚到
觀測          tac_angel / aerogrid / hades / startx 的 view 在非格子空間拋 ValueError
```

### 兩座城市（seed 42）

```text
city_takeover_001   跑滿 30 tick、570 個 event；order_restored、verdict pass；governance score 0.82（開始 0.52）
                    成分：order 0.93、services 0.82、administration 0.62、trend 0.74
city_blackout_001   tick 4 sub_center 失效（incident）→ sub_north（13.5 > 11）與 sub_south（9.9 > 8）在 tick 5 跳脫，
                    兩者的 caused_by_event 都指向 tick 4 的那筆 event；7 個 district 斷電；
                    維修：sub_center tick 10、sub_north 13、sub_south 19，之後沒有再跳脫
                    order_not_restored、verdict fail；governance score 0.47
```

### 驗收四條

| # | 開發計劃原文 | 如何證明 |
|---|---|---|
| 1 | 能模擬一座城市的秩序恢復 | takeover 在 10 個 seed 全部 order_restored、verdict pass（20 個 seed 測量亦同）；沒有警力與車隊 → 不恢復；一開始就穩定的城市是 order_held，不是「恢復」 |
| 2 | 能看到停電連鎖反應 | blackout：失效 → 超載（strain）→ 下一個 tick 跳脫，caused_by_event 可追；report.cascade 深度 1、最多 7 區斷電；沒有 incident → 沒有斷電；backup 撐得住的失效 → 沒有連鎖 |
| 3 | 能測補給延遲對治安的影響 | 10 個 seed 的平均結束治安：延遲 ×1 96.1、×1.5 90.3、×2 65.1、×2.5 35.5、×3 21.3；每次送達與出發相差正好路徑 × 係數；batch 的勝率 100% → 0% |
| 4 | 能輸出 governance stability score | 每個 city run：分數、四個成分、逐 tick 序列、每個 district；output/city/governance_*.json；NEXUS 的 domain_outcome |

### 每一種輸入

```text
scenario run      兩個 city scenario；reference 與軍事一步都不變（trace 與六個 output_hash）
batch             data/batches/city_supply_delay.json：5 個延遲 × 20 次
failure map       supply_delay、civilian_pressure、resource_shortage 在 severe 崩潰；communication_failure 從 mild 就傷
world service     NEXUS 提交 city scenario：result package、briefing、domain_outcome.governance_outcome
views             七個 view 都跑得完（map_view 已能排 network 的節點）
```

---

## 3. 交付了什麼

```text
src/skyvault/domains/city/
  model.py       order_state、consumption、demand、order_delta、power_flow、eta
  scenario.py    build_city_scenario
  handlers.py    travel、patrol、dispatch、restore_power、administer；power_update、arrive、district_update
  policy.py      CityAdministrationPolicy
  pack.py        CITY（spaces、ends_with_last_faction、end_reasons、acts、upkeep、finished、outcome_label、
                 governance_outcome、failure_variables、mission_goal）
  score.py       governance_stability、population_order
  failures.py    city_failure_variables
  report.py      cascade、city_report
  reference.py   reference_scenarios、load_rules
src/skyvault/engine.py            pack 的宣告；domain 在 build_world 之前載入
src/skyvault/evaluation/evaluate.py   success_outcomes、domain 結束原因與 end_reasons
src/skyvault/contracts/scenario.py    evaluation.success_outcomes（optional）
src/skyvault/batch/、failure/、interface/systems.py、timeline.py   見 ADR 018 第 27–29 點
data/domains/city/（rules.json、兩個 spec）、data/scenarios/city_*/v0.1.json、data/batches/city_supply_delay.json
scripts/build_city_scenarios.py、scripts/run_city.py → output/city/
ci.yml                            City domain pack 步驟
skyvault.__version__              0.18.0
```

---

## 4. 這一輪發現的問題

### 第一次跑：崩潰的城市被判 pass

city 沒有對手，Phase 7 的軸大多不適用，strategic_value（保住的實體）恆為 1 —— 一座全部 riot 的城市 verdict pass。若不讀 verdict 欄而只看結果名稱，會以為評估是對的。修正：scenario 的 success_outcomes 與 domain 結束原因（ADR 018 第 20、21 點）。

### 讀輸出找到的四件事

```text
維修隊    開 4 個 tick 到 Old Center，抵達時改去 North，什麼都沒修（每個 tick 都重新選目標）
再跳脫    修好 Old Center 的那一刻它接下兩個仍跳脫的 substation 的負載（23.4 > 9）又跳 —— 每次修復都再跳一次
briefing  「Failure threshold 'governance_collapsed' is not evaluated yet」—— 它每個 tick 都在檢查
briefing  「What happened」只數行動，停電本身不在裡面 → NEXUS 改拿 domain_outcome
```

### 邊界測試找到的缺陷

送往 depot 所在 district 的車隊旅程是 0 tick：arrives_at 等於當下，而當下的抵達已經處理過 —— 車隊永遠困在路上。第一版的測試裡沒有一個 seed 會把車隊派到 harbor；「到達時間 ≥ 1」的斷言與反向驗證各抓到一次（出發與回程）。

### 校準

第一版：兩座城市都崩潰（20 個 tick 只送糧 7 次，飢餓主導）。第二版：takeover 每個 seed 治安 99、blackout 4。量了 20 個 seed 三輪才到現在的梯度（ADR 018 第 30 點）。

### 其他

```text
schema     scenario 契約加欄位 → scenario.schema.json 過期（漂移測試）
軍事測試   一個測試用 "city" 當「不存在的 domain」的例子 → 改成 "airspace"
另一個     test_the_reference_policy_is_registered_and_others_can_join 單獨跑檔案時失敗、全套通過 ——
           在 Phase 14 之前就是如此（git stash 驗證），與本 Phase 無關，記錄於此
```

---

## 5. 品質狀態

| 項目 | 結果 |
|---|---|
| pytest | 1233 passed（有 Redis / PostgreSQL 時；沒有時 1165 passed、68 skipped）（Phase 12 為 1130） |
| Python 3.10 venv | 1233 passed |
| 從 /tmp 執行 | 1233 passed |
| 全專案覆蓋率 | 99%；domains/city/ 99–100% |
| ruff / black / mypy / bandit | 通過（mypy 134 個檔案） |
| 跨 PYTHONHASHSEED | output/city/ 逐位元相同；兩個 city scenario 的 output_hash 相同 |

### 測試分布

```text
tests/domains/city/test_city.py           86   治安門檻（含 69.99）；order_delta 各部分；power_flow（轉移、隔離、無 backup、滿載不算超載）；
                                               eta；builder 與它拒絕的 12 種城市；engine 的開放（沒有 domain 的圖空間仍被拒）；
                                               驗收 1–3 的觸發與不觸發；8 種邊界城市；handler 的 16 種拒絕；policy
tests/domains/city/test_city_outputs.py   17   score 的公式、視窗、人口加權、趨勢；cascade 與 report；run_city；city 的 failure variables
                                               與 failure map；batch 勝負；NEXUS 的 domain_outcome；崩潰門檻
既有測試                                  1130  軍事的「不存在的 domain」例子一行
```

### 反向驗證過的測試（21 個變異全部紅）

```text
engine：只剩一方就結束 / 預設接受 graph / acts 不篩 / finished 不問 / outcome_label 不用              → 紅
evaluate：success_outcomes 不用 / end_reasons 當未評估                                               → 紅
model：stable 門檻差一 / 跳脫也轉移 / 滿載算超載；handlers：不等 strain 就跳脫                         → 紅
回程可以 0 tick                                                                                       → 第一次存活 → 補「送到隔壁」的測試 → 紅
policy 不先修腳下的 / aggregate 不看 success_outcomes / variable_for 不用 pack 的 / 視窗用 floor       → 紅
飢餓不依人口加壓 / held 一律叫 restored / pressure 不重算 order_state / NEXUS 不給 domain_outcome      → 紅
```

---

## 6. 已知限制

| 項目 | 留待 | 原因 |
|---|---|---|
| 係數是手調的 | 有真實資料時 | rules.json 依 20 個 seed 的測量訂定，不是校準過的城市 |
| GIS（真實地圖、座標） | 計劃寫 later | 道路網是抽象節點 |
| briefing 不敘述城市的狀態變化 | 需要時 | 「What happened」只數行動；NEXUS 拿 domain_outcome、人讀 output/city/city_report.md |
| Phase 7 對不適用的軸仍建議「Exercise X」 | 需要時 | 軸是戰鬥的形狀；city 的判斷在 governance score |
| failure map 的 first_loss 欄位在 city 為空 | 需要時 | 城市沒有被摧毀的實體 |
| 電廠輸出不是限制 | 需要時 | 總負載 24.6 遠低於 100 |
| 觀測 view 只支援格子 | 對應的需求出現時 | city 的 baseline 讀 WorldView |
| 只有一個維修隊、一個 depot | 需要時 | reference spec 的設定；模型支援多個 |

---

## 7. 驗證

```bash
python3 scripts/run_tactical_reference.py                         # RED_survived / 97；output 63090026e137
python3 scripts/build_city_scenarios.py                           # 兩個 city scenario 與 commit 的相同
python3 scripts/run_tactical_reference.py --scenario data/scenarios/city_blackout_001/v0.1.json   # order_not_restored
python3 scripts/run_city.py                                       # output/city/：分數、連鎖、補給延遲、報告
python3 -m pytest tests/ -q                                       # 1165 passed、68 skipped（有 Redis / PostgreSQL 時 1233）
```

---

## 8. 一句話總結

> Phase 14 讓 SKYVAULT 跑第一座城市：Old Center 的變電站在 tick 4 倒下，隔一個 tick 北區與南區跟著跳脫，七個城區斷電、治安一路掉；同一座城市在補給準時時三十個 tick 內恢復秩序，補給慢三倍時再也恢復不了 —— 每一場都交出它的 governance stability score。
