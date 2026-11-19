# Phase 13 — Military / Tactical Domain Pack v1.3

完成報告。這份文件是 Phase 13 結束時的凍結紀錄，寫完不再更新 —— 系統目前的樣子請看 [`../architecture.md`](../architecture.md)。

**狀態：功能完成，沒有已記錄未修的缺陷。**

---

## 1. 這個階段做什麼

Phase 13 開始前，SKYVAULT 的軍事線只有 tactical reference slice：一張 10 × 10 的空白格子、雙方各 3 個單位、一個標明「暫時」的 policy。沒有地形、士氣、補給、感測，也沒有辦法換掉 policy。

目標是開發計劃的原文：「把現在 tactical reference slice 升級成正式軍事 domain pack。這不是 SKYVAULT core。這是第一個正式 domain pack。」規格依據是 [`../plan/phase13_military_domain_pack.md`](../plan/phase13_military_domain_pack.md)。

```text
Issue      #26 Phase_13_military_domain_pack（milestone #10 Phase 13 — Military / Tactical Domain Pack）
開設       測量 core 的規模與擴充點；fixture 先 commit：九種 profile 與四個 scenario spec
步驟 A     core 的三個擴充點（policy registry、load_domain、WorldState.environment）；profile；build_scenario
步驟 B     軍事規則（掩蔽、壓制、士氣、彈藥、地形移動、rally）；baseline policy（感測、doctrine、後勤、指揮延遲）；任務
步驟 C     四個 reference scenario 與 doctrine 變體、doctrine batch、dataset、外部 policy 範例、腳本、CI
```

十九項決定與開發、整合中的八項記錄於 [`../decisions/012_military_domain_pack.md`](../decisions/012_military_domain_pack.md)。

---

## 2. 這次執行發生了什麼

### 沒有 domain 時，模擬不變

```text
Result          RED_survived
Events          97
reference trace 不變；output_hash 63090026… 不變
```

### 四個 reference scenario，同一個 engine（seed 42）

| Scenario | 地圖 | 單位 | 事件 | 時間 | RED 損失 | BLUE 損失 | RED 任務 | BLUE 任務 | 決定數 |
|---|---|---|---|---|---|---|---|---|---|
| squad | 10 × 10 開闊地 + 樹林 | 4 v 4 | 314 | 78 ms | 3 | 1 | destroy ✗ | hold ✓ | 109 |
| urban | 12 × 12 街區 + 中庭 | 10 v 5 | 528 | 108 ms | 8 | 1 | seize ✗ | hold ✓ | 193 |
| mountain | 12 × 12 稜線 + 岩石 | 8 v 5 | 539 | 113 ms | 7 | 0 | seize ✗ | hold ✓ | 213 |
| junction | 14 × 10 河 + 一座橋 | 5 v 4 | 420 | 106 ms | 2 | 1 | seize ✗ | delay ✓ | 170 |

### 20 個 seed 的任務達成率

```text
squad      RED destroy  0/20   BLUE hold   20/20
urban      RED seize    7/20   BLUE hold   11/20   （兩邊都沒達成的 2 次：中庭裡同時有雙方的人）
mountain   RED seize    0/20   BLUE hold   20/20
junction   RED seize    0/20   BLUE delay  20/20
```

**防守在四個中的三個完全佔優。** 掩蔽、壓制與指揮延遲都偏向原地不動、在掩蔽後射擊的一方；攻方要在開闊地上一格一格接近。這是規則與部署的結果，不是錯誤；urban 是唯一有爭議的 scenario，所以 doctrine 比較放在它上面。

### doctrine 比較（urban，每種 50 次）

| RED 的 doctrine | 勝率（RED_survived） | 被判 fail | hp 損失 | 分數 | 20 seed 任務達成 |
|---|---|---|---|---|---|
| **aggressive** | **18%** | 92% | 201.6 | **0.201** | **7/20** |
| overwatch | 0% | 98% | 209.8 | 0.182 | 0/20 |
| defensive | 10% | 98% | 189.2 | 0.065 | 1/20 |

在這個中庭，aggressive 最好：overwatch 每 tick 只有一半的人前進，25 個 tick 到不了；defensive 看到敵人就停下找掩蔽，永遠不進中庭。

### 驗收三條

| # | 開發計劃原文 | 如何證明 |
|---|---|---|
| 1 | 同一 SKYVAULT core 可跑不同 tactical scenario | 四個軍事 scenario 與 tactical reference 用同一個 engine 跑完，事件數與 output_hash 五個都不同；可重現 |
| 2 | TAC ANGEL policy 可替換 baseline policy | `examples/tac_angel_policy.py` 以 `--policy-module … --policy tac_angel_example` 驅動 squad：每個決定的 system_id 都是 TAC_ANGEL；也可 `engine(policy=…)` |
| 3 | 可輸出 state-action-outcome dataset | `scripts/export_dataset.py`：4 scenario × 3 run = 1906 筆，每筆通過紀錄模型；筆數 = ACTION_SELECTED 數 |

---

## 3. 交付了什麼

```text
src/skyvault/policies.py            Policy protocol、register_policy、build_policy、import_policy_module
src/skyvault/domains/__init__.py    DomainPack protocol、load_domain（依名稱延遲 import）
src/skyvault/domains/military/
  profiles.py      九種 profile 的模型、load_profiles（補齊預設值）
  scenario.py      build_scenario、doctrine_variant
  terrain.py       terrain_at、reachable（加權最短路）、path_cost
  handlers.py      MilitaryMoveHandler、MilitaryAttackHandler、RallyHandler（+ core 的 supply、wait）
  policy.py        MilitaryBaselinePolicy：感測、士氣狀態、三種 doctrine、後勤、指揮延遲
  pack.py          MILITARY：handlers、default_policy、upkeep
  mission.py       mission_outcome（純函式）
  dataset.py       build_dataset、validate_record、TrainingRecord（純函式）
  reference.py     reference_scenarios、DOCTRINE_VARIANTS
src/skyvault/engine.py              policy 參數；scenario.domain → pack；每 tick 的 upkeep
src/skyvault/world_state.py         environment（唯讀、不進 snapshot）
src/skyvault/contracts/scenario.py  runtime.policy（optional）
data/domains/military/              profiles.json、scenarios/*.json（開設時 commit）
data/scenarios/military_*/          四個 v0.1 + urban 的 v0.1+overwatch、v0.1+defensive（產生的）
data/batches/military_doctrine.json
examples/tac_angel_policy.py
scripts/build_military_scenarios.py、scripts/export_dataset.py；run_tactical_reference.py 加 --policy、--policy-module
src/skyvault/report/briefing.py     每 tick 的計數改用人話（修正 Phase 17）
skyvault.__version__                0.12.0
```

---

## 4. 這一輪發現的問題

### dataset 第一版不可重現

episode 帶 run_id，而 run_id 含執行時間 —— 同一組 run 每次匯出的檔都不同。這是在寫跨 hash seed 測試之前、照 Phase 10 回顧改法 1 檢查時發現的：測試還沒跑，看欄位就知道會不同。改成以 input_hash 與 output_hash 命名 episode。

### Phase 17 的 briefing 在軍事 run 上念出原始型別名

「Tick 3: 1 action_rejected; … 1 entity_state_changed」。briefing 的每 tick 計數涵蓋所有 event 型別，而 reference run 只有 move、attack、miss，所以 Phase 17 的 fixture 與測試都看不到。這是第一次有不同的 scenario 跑過 briefing。修正後 reference 的 briefing 逐位元不變。

### urban spec 的支援組放錯位置

開設時 commit 的 spec 把 marksman 與 logistics 放在守軍步槍射程內；RED 有一個 tick 的命令延遲，兩人第一個 tick 就倒下。量 20 個 seed 時看到才改。fixture 先 commit 的好處是它的改動會出現在 diff 裡、要寫進 ADR（第 23 點）。

### 反向驗證的工具有一個盲點

變異腳本在 pattern 對不上時（black 重排了那段程式）仍然照跑測試 —— 跑的是沒變異的程式，結果「全綠」看起來像變異存活。一個 dataset 的變異就是這樣。改了腳本：pattern 對不上就報「NO MATCH」、不跑測試；用正確的 pattern 重跑，變異被抓到。

### 一個測試缺口

「state 是決定當下的單位」的測試只看第一筆 —— 拿掉 snapshot 的追蹤也會過。改成每一筆都對照 engine 自己在 ACTION_SELECTED 記下的 actor snapshot。

### 外部 policy 的測試一開始用了 reference 沒有的 action

reference 的 action 集是 move / attack / observe / supply / repair，沒有 wait；測試用的 stand-in policy 改成 observe 自己。錯在測試。

---

## 5. 品質狀態

| 項目 | 結果 |
|---|---|
| pytest | 687 passed（Phase 17 為 590） |
| Python 3.10 venv | 687 passed |
| 全專案覆蓋率 | 98% |
| `domains/military/` 覆蓋率 | 89–100% |
| ruff / black | 通過 |
| mypy | 通過，86 個檔案 |
| bandit | 0 issues |
| 換工作目錄跑測試 | 通過 |
| 測試讀 `output/` | 0 處 |
| exporter 程式碼變動 | 0 行 |
| 新 event 型別 | 0 |

### 測試分布

```text
tests/domains/military/test_core_extension.py         7   registry、外部 policy 取代 baseline、runtime.policy、load_domain、environment、core 不 import pack
tests/domains/military/test_profiles_and_builder.py  23   九種 profile、預設值、錯誤；四個 spec；單位的 profile；spec 的錯誤
tests/domains/military/test_rules.py                 19   掩蔽、壓制、士氣、近彈、彈藥、射程、擊毀；地形移動、不可通行、敵人擋路；rally、upkeep；不改世界
tests/domains/military/test_policy_and_mission.py    24   感測、恐慌、撤退、找掩蔽、目標、三種 doctrine、後勤；指揮延遲；四種任務
tests/domains/military/test_reference_and_dataset.py 18   漂移、doctrine 變體、驗收三條、doctrine batch、dataset 逐筆核對、跨 hash seed、briefing 的人話
tests/report/test_briefing.py                        +6   複數規則
既有測試                                             590   改動：無
```

### 反向驗證過的測試

```text
外部 policy 被忽略 / 不記它的 system_id                          → 紅
命中率不算掩蔽 / 不算射手被壓制                                   → 紅
跨門檻的士氣懲罰每次都扣 / 近彈加滿額壓制                         → 紅
移動時敵人不擋路                                                  → 紅
感測不算 concealment                                              → 紅
loss_prob 為 0 也抽 / 遺失用戰鬥的 rng                            → 紅
「彈藥不足」用 <= / upkeep 對所有單位 rally                        → 紅
hold 不要求有自己的單位 / delay 不看 deadline                      → 紅
dataset 不追蹤 snapshot / 不算 concealment / 永遠 accepted / 任務取錯 → 紅（snapshot 的那個原本是缺口）
spec 展開的射程錯一格（漂移）                                     → 紅
import_policy_module 不執行檔案                                   → 紅
briefing 計入 ENTITY_STATE_CHANGED / 不換人話 / 複數規則錯        → 紅
```

---

## 6. 已知限制

| 項目 | 留待 | 原因 |
|---|---|---|
| 感測在 policy 內 | Phase 5 | core 的觀測層 |
| 任務不在 core 的 evaluation 與 batch 指標裡 | — | 任務是 pack 的概念；batch 比的是勝率與失敗頻率 |
| 防守在三個 scenario 中佔優 | 調整規則或部署時 | 規則與部署的結果 |
| 沒有視線（LOS） | — | 只有距離 × concealment |
| tactical engine 只支援 grid + tick | — | 交通節點用格子上的道路與橋 |
| UI 的地圖不畫地形 | — | result package 不帶 environment_state |
| 真正的 TAC ANGEL | 外部 | 只提供介面與範例 |

---

## 7. 驗證

```bash
rm -rf runs output/*.json output/*.txt output/*.md output/*.pdf output/*.docx
python3 scripts/run_tactical_reference.py           # RED_survived / 97；output 63090026e137
python3 scripts/build_military_scenarios.py         # 六個 scenario 檔（與已 commit 的相同）
python3 scripts/run_tactical_reference.py --scenario data/scenarios/military_urban_001/v0.1.json
python3 scripts/run_tactical_reference.py --scenario data/scenarios/military_squad_001/v0.1.json \
    --policy-module examples/tac_angel_policy.py --policy tac_angel_example
python3 scripts/run_batch.py --batch data/batches/military_doctrine.json   # aggressive 最佳
python3 scripts/export_dataset.py                   # 1906 筆
python3 -m pytest tests/ -q                          # 687 passed
```

---

## 8. 一句話總結

> Phase 13 把 tactical reference 變成第一個正式的 domain pack：九種 profile 描述單位、地形、士氣與指揮，四個 reference scenario 在同一個 core 上跑出小隊、城市、山地與渡橋的交戰 —— 防守在其中三個完全佔優，而在唯一有爭議的城市中庭，doctrine 的差別一目了然；TAC ANGEL 只要實作一個方法就能接手指揮，每一個決定都能匯出成可重現的訓練資料。
