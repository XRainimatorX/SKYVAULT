# Phase 15 — Airspace / HADES / SKYFOX / AEROGRID Domain Pack v1.5

完成報告。這份文件是 Phase 15 結束時的凍結紀錄，寫完不再更新 —— 系統目前的樣子請看 [`../architecture.md`](../architecture.md)。

**狀態：功能完成，沒有已記錄未修的缺陷。**

---

## 1. 這個階段做什麼

Phase 15 開始前，SKYVAULT 沒有空域：偵測在範圍內是確定的、範圍外不可能，沒有航跡、誤報、攔截器，也沒有會飛的東西。SKYFOX 是在格子上走的地面單位，HADES 像步兵一樣移動射擊，AEROGRID 的空域配置在介面上回來的是一個 gap。

目標是開發計劃的原文：低空空域、無人機、防空、感測器覆蓋、攔截窗口、誤判、反應延遲。規格依據是 [`../plan/phase15_airspace_pack.md`](../plan/phase15_airspace_pack.md) 與 Formal Spec §9、§14。

```text
Issue      #33 Phase_15_airspace_pack（milestone #17 Phase 15 — Airspace / HADES / SKYFOX / AEROGRID Domain Pack）
開設       測量：spec 沒有 builder、偵測是確定的、沒有航跡 / 誤報 / 攔截、AEROGRID 回 gap；
           fixture 先 commit：data/domains/airspace/scenarios/airspace_defence_001.json
開發       domains/airspace/（model、scenario、handlers、policy、pack、metrics、failures、report、reference）；
           engine 把 world 傳給 acts；success_outcomes 一律適用；job 契約的 EntityChange.position；
           HADES / SKYFOX / AEROGRID 的空域提交；run_airspace、build_airspace_scenarios；CI 的 Airspace domain pack 步驟
```

十九項決定與開發中的十五項記錄於 [`../decisions/019_airspace_domain_pack.md`](../decisions/019_airspace_domain_pack.md)。

---

## 2. 這次執行發生了什麼

### 開設時的測量

```text
偵測          Phase 5 的觀測在範圍內一定看到、範圍外一定看不到；沒有任何隨機數
航跡 / 誤報   不存在；HADES adapter 直接拿到敵人的位置
SKYFOX       grid 上的步兵單位，沒有高度、沒有被誤認的可能
AEROGRID     介面回 gap「airspace configuration (altitude, corridors) has no model before Phase 15」
```

### airspace_defence_001（seed 42）

```text
16 tick、138 個 event；threats_resolved；defended、verdict pass（score 0.90）
7 個威脅全部被攔截、0 漏過；未覆蓋 21%（84 / 400 格）；升空到第一次偵測平均 2.0 tick（最差 5）
航跡 → 第一次射擊平均 3.7 tick（最差 6）；第一個可交戰 tick → 第一次射擊平均 0.9 tick（最差 2）
```

### 驗收四條

| # | 開發計劃原文 | 如何證明 |
|---|---|---|
| 1 | HADES 能提交防禦行為測試 | HADES 交 hades_rules 的參數；10 個 seed：baseline 守住 70%、平均漏過 0.4；salvo 2 40% / 0.6；engage_at 0.5 0% / 2.9；hold_fire_below 0.6 0% / 3.5。不改變任何東西的規則 → 事件逐筆相同 |
| 2 | SKYFOX 能在空域中模擬 | SKYFOX 的巡邏在同一個空域；identify 0 → 10 個 seed 中有被友軍擊落的（fratricide failure point）；identify 1 → 10 個 seed 都沒有；撞上同高度威脅 = collision；SKYFOX adapter 的提交：兩個航點全部到達、0 個被拒的移動 |
| 3 | AEROGRID 能提交空域配置 | 備用雷達放西邊：未覆蓋 21% → 11%、偵測 2.5 → 1.4 tick；南雷達關掉：40%、守住 70% → 40%；移到地圖外 → 被拒；調參數 → 覆蓋改變 |
| 4 | 能輸出 detection gap / response time / failure points | 每個 run 的 airspace_outcome；每個漏過一個原因（六種，各有造得出它的 scenario）；output/airspace/；NEXUS 的 domain_outcome |

### 每一種輸入

```text
scenario run      airspace_defence_001；reference 與軍事、city 一步都不變（trace 與六個 output_hash）
batch             data/batches/airspace_sensors.json：南雷達開 70% 勝、關 40%（各 10 次）
failure map       baseline 存活 1.0；sensor_failure 在 moderate 斷、equipment_overheat 在 severe、
                  enemy_reaction_speed 從 mild 起漸進下降（0.4 → 0.2 → 0）、communication_failure 在 severe
world service     NEXUS 提交：result package、domain_outcome.airspace_outcome；HADES / SKYFOX / AEROGRID 的提交
```

---

## 3. 交付了什麼

```text
src/skyvault/domains/airspace/
  model.py       distance、step_toward、detection_probability、covered、interception_window
  scenario.py    build_airspace_scenario(spec, rules, behavior)
  handlers.py    launch、fly、sense（upkeep）；engage、move（actor）
  policy.py      AirDefencePolicy（HADES 的交戰規則與巡邏）；註冊為 hades_rules
  pack.py        AIRSPACE（spaces、ends_with_last_faction、end_reasons、acts、upkeep、finished、outcome_label、
                 failure_variables、mission_goal、airspace_outcome）
  metrics.py     detection_gap、response_times、failure_points、airspace_outcome
  failures.py    airspace_failure_variables
  report.py      airspace_report
  reference.py   reference_scenarios、load_rules、load_spec
src/skyvault/engine.py                acts(entity, world)
src/skyvault/evaluation/evaluate.py   success_outcomes 只要宣告就適用
src/skyvault/contracts/job.py         EntityChange.position（schema 重新匯出）
src/skyvault/worldservice/jobs.py     entity_changes 會移動單位
src/skyvault/interface/systems.py     HADES / SKYFOX / AEROGRID 在空域的提交與返回；domain_outcome 含 airspace_outcome
data/domains/airspace/（rules.json、spec）、data/scenarios/airspace_defence_001/v0.1.json、data/batches/airspace_sensors.json
scripts/build_airspace_scenarios.py、scripts/run_airspace.py → output/airspace/
ci.yml                                Airspace domain pack 步驟
skyvault.__version__                  0.19.0
```

---

## 4. 這一輪發現的問題

### 第一次讀 verdict（Phase 14 回顧改法 1）

```text
漏過也判 pass         success_outcomes 只在沒有對手時使用 → 改為只要宣告就適用
inaction 被標記       每個攔截器每 tick 一個 NO_ACTION —— 等目標是防空的工作 → acts 收 world，只在有機會時才有回合
沒有威脅升空          待命的威脅不是 active，resolver 不收它的 action → 指揮節點下令升空
```

### 讀輸出找到的

```text
AEROGRID 開備用雷達沒有改變覆蓋     離線的感測器也算進覆蓋 → 只算 online
response time 讓早看到的配置變差     它包含飛進射程的時間 → 另加 reaction_ticks
巡邏卡在第一個航點                   目標就是腳下的格子 → 站上就換下一段
```

### 寫測試與測量找到的

```text
一發擊落的威脅沒有攔截窗口       那一 tick 結束時已是 destroyed、被排除 → 路徑含「上一 tick 結束時 active」
enemy_reaction_speed 三級相同    整數速度 × 1.25 進位 = 2 → 威脅累積小數格（state.carry）
基線「沒加壓就失敗」              第一版只守住 10% → 三輪測量後加 gun_north、kill 0.75、identify 0.98 → 70%
```

### 反向驗證

19 個變異；第一輪兩個存活（射程外的真實目標仍被擊落、acts 不看反應延遲）→ 各補一個測試 → 全部紅。

### 其他

```text
Phase 12 測試    用 position 當「不允許的欄位」→ 改用 faction（position 現在允許）
軍事測試         "airspace" 不再是「不存在的 domain」→ 改用 "maritime"
順序問題         test_core_extension 單獨跑時失敗（Phase 14 記錄過）→ 測試先 build_policy 一次，已修
CI 的一次紅      push 的 CI 在 PostgreSQL 撞 job_events 的主鍵：store 的 log、add_checkpoint、save_conflict 先讀最大編號
                 再插入，worker 與停止請求同時寫時拿到同一個號碼（Phase 11 起就在）→ 並行測試重現（SQLite 也會）→
                 撞主鍵時換新號碼重試
```

---

## 5. 品質狀態

| 項目 | 結果 |
|---|---|
| pytest | 1346 passed（有 Redis / PostgreSQL 時；沒有時 1277 passed、69 skipped）（Phase 14 為 1233） |
| Python 3.10 venv | 1344 passed（store 修正前；修正後 CI 的 3.10 job）|
| 從 /tmp 執行 | 通過（沒有服務：68 skipped） |
| 全專案覆蓋率 | 99%；domains/airspace/ 每個檔案 100% |
| ruff / black / mypy / bandit | 通過（mypy 144 個檔案） |
| 跨 PYTHONHASHSEED | output/airspace/ 逐位元相同 |

### 測試分布

```text
tests/domains/airspace/test_airspace.py           82   model（距離、飛行、偵測的形狀與 0 / 1 邊界、覆蓋、窗口）；builder 與它拒絕的 8 種空域；
                                                       pack 與 engine；seed 之間不同、同 seed 相同；launch / fly / collision / sense / 誤報 /
                                                       航跡 / 逾時 / 識別 / engage 的 5 種拒絕 / 齊射 / 誤擊 / 假航跡 / move；HADES 的規則；
                                                       驗收 1；6 種邊界空域
tests/domains/airspace/test_airspace_outputs.py   29   detection gap、response、六種漏過原因與 collision；驗收 2、3 的介面；EntityChange.position；
                                                       NEXUS；failure variables 與小數速度；failure map；batch；report；run_airspace
既有測試                                          1233  三個測試各改一行（見第 4 節「其他」）
```

---

## 6. 已知限制

| 項目 | 留待 | 原因 |
|---|---|---|
| 只有 2D、兩種高度 | 計劃寫 3D later | 高度是屬性 |
| 威脅只會直線飛向目標 | 需要時 | 沒有閃避、改目標、飽和戰術 |
| HADES 不能指定攔截器、AEROGRID 不能新增感測器 | 需要時 | 只能用 scenario 已有的（含備用） |
| 航跡集中在一個指揮節點 | 需要時 | 沒有通訊延遲與分散的航跡融合 |
| 係數是手調的 | 有真實資料時 | 依 20 個 seed 的測量訂定 |
| Phase 7 的軸仍是戰鬥的形狀 | Phase 14 回顧第 7 節的未決項 | 空域的判斷在 airspace_outcome |

---

## 7. 驗證

```bash
python3 scripts/run_tactical_reference.py                         # RED_survived / 97；output 63090026e137
python3 scripts/build_airspace_scenarios.py                       # 與 commit 的 scenario 相同
python3 scripts/run_tactical_reference.py --scenario data/scenarios/airspace_defence_001/v0.1.json   # defended
python3 scripts/run_airspace.py                                   # output/airspace/：outcome、behaviors、configs、報告
python3 -m pytest tests/ -q
```

---

## 8. 一句話總結

> Phase 15 讓 SKYVAULT 有了第一片天空：七架低空無人機分兩波撲向發電站與指揮所，雷達每個 tick 抽一次看不看得到，指揮節點可能把自家的 SKYFOX 認成敵機 —— HADES 換一組交戰規則、AEROGRID 移一座雷達，漏過的數字就變，而每一個漏過都說得出它為什麼漏過。
