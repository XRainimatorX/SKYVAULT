# Phase 9 — Failure Exploration Engine v0.9

完成報告。這份文件是 Phase 9 結束時的凍結紀錄，寫完不再更新 —— 系統目前的樣子請看 [`../architecture.md`](../architecture.md)，契約的現行規格請看 [`../spec/contracts.md`](../spec/contracts.md)。

**狀態：功能完成，沒有已記錄未修的缺陷。**

---

## 1. 這個階段做什麼

Phase 9 開始前，SKYVAULT 跑一次 run，告訴你這次發生了什麼。它不會告訴你：換個條件會怎樣、方案在哪裡最脆弱、有沒有更好的替代方案。

目標是 Definition 說的「讓帝國在現實行動前，先把決策放進虛擬世界裡死一千次」：給一個方案，故意惡化它，找出它在哪裡、為什麼、多快失敗，哪個變量壓垮它，哪個替代方案撐更久，現實行動前必須改什麼。規格依據是 [`../plan/phase9_failure_exploration.md`](../plan/phase9_failure_exploration.md) 與 [`../plan/formal_spec.md`](../plan/formal_spec.md) §14。

```text
Issue      #23 Phase_9_failure_exploration（milestone #7 Phase 9 — Failure Exploration）
開設       測量基線、天氣、替代部署；fixture 先 commit：兩個替代方案
步驟 A     八個變量、fault injection、契約 0.6
步驟 B     explore_failures：基線、掃描、分支、替代方案
步驟 C     analysis、四個輸出、第 13 份契約、scripts/explore_failures.py
```

十四項決定與開發中的六項記錄於 [`../decisions/009_failure_exploration.md`](../decisions/009_failure_exploration.md)。

---

## 2. 這次執行發生了什麼

### 沒有惡化時，模擬不變

```text
Result          RED_survived
Events          97
reference trace 不變；output_hash 63090026… 不變
```

### v0.1 被惡化 760 次的結果

設定：六個變量 × 四級 × 10 次 + 基線 + 分支，加兩個替代方案的同樣掃描，共 760 次 run，約 12 秒。balanced profile，RED 視角。

```text
基線            存活 60%（BLUE 勝 4、RED 勝 2、平手 4，seed 42–51）
```

| 變量 | mild | moderate | severe | collapse | 崩潰等級 | sensitivity |
|---|---|---|---|---|---|---|
| sensor_failure | 0.6 | 0.7 | 0.7 | 0.6 | — | 0.0 |
| communication_failure | 0.7 | 0.8 | 0.5 | **0.0** | collapse | **0.6** |
| weather_degradation | 0.7 | 0.8 | 1.0 | 0.6 | — | 0.0 |
| enemy_reaction_speed | 0.5 | 0.5 | **0.4** | 0.2 | **severe** | 0.4 |
| equipment_overheat | 0.6 | 0.7 | 0.7 | **0.0** | collapse | **0.6** |
| civilian_pressure | 0.8 | 0.7 | 0.7 | 0.1 | collapse | 0.5 |

### 驗收六條的答案

```text
在哪裡失敗     red_003（指揮官）在 tick 5–6 被擊倒是最常見的第一個損失（112 個失敗 run 中前五名都是它）
為什麼失敗     112 個失敗 run 全部 mission_success 過低；其次 recovery_ability、time_cost
多快           第一個損失平均在 tick 6.1；全滅平均在 tick 9.35
壓垮的變量     communication_failure（攻擊 actor_policy 假設）—— 與 equipment_overheat 同為 0.6，
               同在 collapse 崩潰，依名稱取前者；enemy_reaction_speed 雖然 sensitivity 較低，卻最早崩潰（severe）
替代方案       v0.1-support-rear：基線存活 90%，enemy_reaction_speed 撐到 collapse 都不崩潰 → holds_longer（最佳）
               v0.1-spread：基線 90%，但 communication_failure 在 severe 就崩潰 → mixed
必須改什麼     recommended_modifications.md 列出五條：四個崩潰的變量各自的對策，加上採用 v0.1-support-rear
```

### 兩個值得記下的發現

**壞天氣保護守方。** weather_degradation 在 severe 時存活率 1.0，比基線還高。命中率全體下降，雙方都打不死人，RED 被判 fail 的機會反而少了。sensitivity 0.0、never breaks —— 這是真的結果，不是錯誤。

**通訊全斷是「癱瘓」，不是殲滅。** collapse sequence 取的是 communication_failure collapse 的第一個失敗 run（seed 42）：整場只損失 red_003 一個單位，結果是平手，但 mission_success 為 0 而被判 fail。命令傳不到，方案什麼都沒做成。

---

## 3. 交付了什麼

```text
src/skyvault/failure/
  variables.py     STRESS_LEVELS、FailureVariable、FAILURE_VARIABLES（8 個）、apply_stress()
  explore.py       explore_failures() —— 在 engine 之上
  analysis.py      build_failure_map()、build_collapse_sequence()、build_survival_conditions()、
                   render_recommended_modifications()、RECOMMENDATIONS —— 純函式
src/skyvault/actions/resolver.py    rule_set.faults.drop_actions；ActionContext.fault_rng
src/skyvault/contracts/failure.py   FailureExplorationSpec、FailureMap（第 13 份契約）
contracts/                          schema 0.6：failure_variables 必填
data/scenarios/tactical_reference_001/
  v0.1.json                         failure_variables、failure_exploration
  v0.1-support-rear.json、v0.1-spread.json   兩個替代方案
scripts/explore_failures.py         --scenario、--profile、--repeats
.github/workflows/ci.yml            explore_failures --repeats 2，驗證四個輸出
skyvault.__version__                0.9.0
```

### 驗收六條

| # | 開發計劃原文 | 如何證明 |
|---|---|---|
| 1 | 給定一個方案 | explore_failures(v0.1, balanced)；方案 = scenario 版本 + profile + perspective |
| 2 | 能跑出它在哪裡失敗 | failure_points：「red_003 lost at tick 6 to blue_001 (23 of 112 failed runs)」… |
| 3 | 為什麼失敗 | failure_causes：「mission_success too low in 112 of 112 failed runs」… |
| 4 | 哪個變量壓垮 | crushing_variable communication_failure、crushing_assumption actor_policy；每個變量的 breaking_level 與 sensitivity |
| 5 | 哪個替代方案撐更久 | best_alternative v0.1-support-rear（holds_longer on baseline、enemy_reaction_speed） |
| 6 | 現實前必須改什麼 | recommended_modifications.md |

---

## 4. 這一輪發現的問題

### 契約驗證拿掉了預設值

`validate_failure_exploration` 通過後，沒寫 `branch_comparison` 的設定裡根本沒有這個鍵，explore 第一次就 KeyError。原因是 Phase 1 的設計：`check()` 只回傳呼叫端提供的欄位，「驗證不改變形狀」。這個設計對 scenario 很合理（驗證前後相等），但對「有預設值的設定」就意味著每個使用者都得自己補預設值。explore 現在明確補上（ADR 009 第 16 點）。

Phase 7 的 evaluation profile 沒踩到，只是因為兩份 profile 檔剛好每個欄位都寫了。

### compare_scenarios 把設定當成了世界

v0.1 加上 failure_exploration 後，v0.2 的 version_control 就與 compare_scenarios 的結果對不上：比較把「v0.2 沒有壓力測試設定」報成 failure_variables_changed。壓力測試的設定不是 scenario 所描述的世界，從比較類別中移除（ADR 009 第 15 點，修正 ADR 008 第 11 點）。

### 兩個反向驗證的變異存活，都是測試缺口

拿掉「crushing 同分時取較早崩潰者」、拿掉「替代方案基線較高算 holds longer」—— 測試都還是綠的。依 Phase 3 回顧改法 2 找反例，兩個都找得到：

```text
同分規則     測試用的 weather 與 equipment_overheat，名稱的字母順序剛好就是崩潰順序
基線規則     所有測試的方案基線都是 100%，替代方案不可能超過
```

補上讓規則「非它不可」的資料後，兩個變異都會紅。**Phase 3 的改法 2 這次直接找出了兩個缺口。**

### 測試的預期值寫錯一次

`sweep(4, 0, 0, 0)` 是 mild 存活、moderate 崩潰，測試卻預期「mild 崩潰」。錯在測試，不在程式。

### 一句測試註解說得太滿

「failing verdict always has mission_success at zero」—— 在這組 run 裡是真的，但 fail 也可能來自 overall 低於門檻。改成「在這次探索中，每個失敗的 run 都是」。

### 數字在文件裡先寫錯

README 草稿寫「600 多次 run」，architecture 的 run 數公式把分支也算進替代方案。實際是 760。依 Phase 7 回顧改法 4，用命令算過才寫進去。

---

## 5. 品質狀態

| 項目 | 結果 |
|---|---|
| pytest | 467 passed（Phase 8 為 393） |
| 全專案覆蓋率 | 98%（2658 statements，49 miss） |
| `failure/` 覆蓋率 | 96–100% |
| ruff / black | 通過 |
| mypy | 通過，59 個檔案 |
| bandit | 0 issues |
| 換工作目錄跑測試 | 467 passed |
| 測試讀 `output/` | 0 處 |
| exporter 程式碼變動 | 0 行 |

### 測試分布

```text
tests/failure/test_variables.py   41   八個變量 × 四級的數值；版本紀錄；fault injection 的實際拒絕率；契約
tests/failure/test_explore.py     12   真實 engine 的小型探索（3 repeat、4 變量、2 級、2 替代方案）
tests/failure/test_analysis.py    21   手造 run：每條規則與邊界（負的 sensitivity、基線就失敗、同分、四種替代方案判斷）
既有測試                         393   改動：schema 0.6、failure_variables 必填、版本測試不寫死
```

### 反向驗證過的測試

```text
test_a_zero_rate_fault_never_shifts_the_battle                      fault_rng 改用主 rng → 紅
test_dropped_orders_match_the_rate_and_only_hit_the_stressed_side   拿掉陣營檢查 → 紅
test_the_crushing_variable_has_the_largest_drop_and_ties_go_to_...  拿掉崩潰等級的同分規則 → 原本綠（缺口），補資料後紅
test_an_alternative_that_survives_more_unstressed_holds_longer      拿掉基線比較 → 原本無測試（缺口），新增後紅
test_the_runtime_version_is_the_package_version                     __version__ 與 pyproject 不一致 → 紅
```

---

## 6. 已知限制

| 項目 | 留待 | 原因 |
|---|---|---|
| 變量是現有模型上的近似 | 需要感測 / 通訊 / 天氣模型的 domain | sensor_failure = 己方命中率下降，不是真的感測器 |
| 強度表固定 | — | 讓不同 scenario 的等級可以比較；需要時再開放覆寫 |
| 循序執行 | Phase 10 | 760 次 run 約 12 秒 |
| 替代方案只能是同 scenario 的其他版本 | — | 版本資料夾的慣例 |
| 替代方案不跑分支 | — | 只比較單一變量的崩潰等級 |
| crushing 同分時最後依名稱 | — | v0.1 上 communication_failure 與 equipment_overheat 完全同分 |
| 建議是每個變量一句固定文字 | domain pack | RECOMMENDATIONS 不認識具體的 scenario |

---

## 7. 驗證

```bash
rm -rf runs output/*.json output/*.txt output/*.md
python3 scripts/run_tactical_reference.py           # RED_survived / 97；output 63090026e137
python3 scripts/explore_failures.py                 # 60% / communication_failure / v0.1-support-rear
python3 -m pytest tests/ -q                          # 467 passed
cd /tmp && python3 -m pytest ~/SKYVAULT/tests -q     # 467 passed
ruff check . && black --check src/ tests/ scripts/
python3 -m mypy src/
python3 -m bandit -c pyproject.toml -r src/
```

---

## 8. 一句話總結

> Phase 9 讓 SKYVAULT 能把一個方案故意弄壞 760 次 —— v0.1 不加壓就只撐 60%，通訊全斷與武器過熱在 collapse 讓它完全崩潰，敵方反應加快在 severe 就壓垮它，而把支援組放後方的替代部署撐得更久；所有惡化都是可重現的 scenario 版本，分析規則都能脫離模擬單獨驗證。
