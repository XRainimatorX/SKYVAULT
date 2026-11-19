# Phase 21 — Standalone SKYVAULT v2.1

完成報告。這份文件是 Phase 21 結束時的凍結紀錄，寫完不再更新 —— 系統目前的樣子請看 [`../architecture.md`](../architecture.md)。

**狀態：功能完成。roadmap 之後由使用者加入的第一個 Phase。**

---

## 1. 這個階段做什麼

使用者的要求（原文見 [`../plan/phase21_standalone.md`](../plan/phase21_standalone.md)）：SKYVAULT 運作時只靠完成的系統本身 —— 不靠 Phase 0 的參考切片，也不靠開發時寫的腳本。

```text
Issue      #37 Phase_21_standalone_skyvault（milestone #21 Phase 21 — Standalone SKYVAULT v2.1）
開設       測量：src 14 個檔、27 處引用 tactical_reference；引擎沒指定 policy 時退回 Phase 0 的 policy；
           驗收、batch、失敗探索、訓練資料的預設都是參考切片；介面只讀 output/；Docker 啟動 scripts/
           fixture 先 commit：military_urban_001 v0.2（spec 的 revisions；doctrine 變體同時寫在旁邊）
開發       E 引擎改名、移除退回；F 參考切片搬進 tests、scenario library 與 policy modules；G 系統基線；
           H skyvault 指令、scripts/dev、Docker、CI；I 介面讀服務
```

決定與開發中的發現記錄於 [`../decisions/023_standalone.md`](../decisions/023_standalone.md)。同一輪開頭先完成了 code review 的十項修正（[`../reviews/2026-11-09_code_review.md`](../reviews/2026-11-09_code_review.md)）。

---

## 2. 這次執行發生了什麼

### 開設時的測量

```text
沒有 domain 也沒有 policy 的 scenario    只有參考切片的 4 個版本與 tests/fixtures 的 5 個
基線候選（沒有壓力，10 個 seed 的存活）  military_squad_001 2/10、military_junction_001 1/10、
                                         military_mountain_001 3/10、military_urban_001 8/10
                                         → urban；計劃原本寫的是 squad
urban v0.2 的 failure map                 基線 80%；communication_failure 0.7、equipment_overheat 0.6、
                                         enemy_reaction_speed 0.5（第一級就斷）、sensor_failure 0.4；
                                         weather_degradation 不影響；替代方案 overwatch 50%、defensive 30%
```

### output_hash：舊 → 新（只因引擎的 system id 改名）

```text
tactical_reference_001/v0.1        63090026e13734f5 -> 7debca2af33238c2   RED_survived、97 events（不變）
military_squad_001/v0.1            7ea5ffe9ef0ba801 -> f49c7eb730cef464   314 events（不變）
military_urban_001/v0.1            f0cd3cae5b7bfa47 -> 203bd68cf56c1e80   528 events（不變）
military_mountain_001/v0.1         014c894cc4ae9483 -> 33b6e3aad8fdcbcc   539 events（不變）
military_junction_001/v0.1         ef399a40e1a015f8 -> d79218652b949905   420 events（不變）
military_urban_001/v0.1+overwatch  fa32c17875f01a61 -> 721eea5f8477bdd6   576 events（不變）
系統基線 military_urban_001/v0.2   78aa3fe5bbdfc1b2                       no_winner_duration_limit、528 events
```

reference trace 逐筆相同，只有 digest 一行改變。

### 驗收

```text
v2 驗收（skyvault acceptance）   ACCEPTED —— 15/15、14/14、6/6、5/5，證據換成 military_urban_001 v0.2
乾淨啟動                         空資料夾、三個 SKYVAULT_* 變數 unset：skyvault serve → run（528 events、78aa3fe5bbdf）→
                                 explore → batch → runs → briefing → 介面路由；參考切片 404；acceptance ACCEPTED；沒有 output/
介面                             Chromium 打開 skyvault serve 的每一頁：10 項檢查（含 run 選單、?run= 跨頁保留、390px 寬）
```

---

## 3. 交付了什麼

```text
src/skyvault/engine.py            SkyVaultEngine、skyvault_engine、require_decider（沒有決定者 → ContractError）
src/skyvault/library.py           依名稱找 scenario 與 batch：data/ 之後是 SKYVAULT_SCENARIO_PATH / SKYVAULT_BATCH_PATH
src/skyvault/policies.py          SKYVAULT_POLICY_MODULES：未知名稱時匯入部署的 policy 模組；不再知道 tactical_reference
src/skyvault/cli.py               skyvault：serve、worker、run、explore、batch、replay、cancel、world、status、runs、
                                  result、briefing、products、virtual-test、acceptance；pyproject [project.scripts]
src/skyvault/service/app.py       add_view_routes、mount_ui（workspace 模式移除）
src/skyvault/worldservice/views.py  runs、workspace_from_store；world service 的 /api/runs 與 /api/runs/{run}/…
src/skyvault/acceptance/          基線 military_urban_001 v0.2
src/skyvault/domains/military/reference.py  spec 的 revisions → child version
src/skyvault/batch/aggregate.py   比較報告的指標順序固定
data/domains/military/scenarios/military_urban_001.json   revisions：v0.2
data/scenarios/military_urban_001/v0.2*.json              新的基線與兩個 doctrine 替代方案
data/training/sources.json        只用系統 scenario
tests/fixtures/reference/         Phase 0 的 policy、4 個 scenario 版本、batch（從系統搬來）
tests/conftest.py                 以三個 SKYVAULT_* 變數取得參考切片
tests/test_standalone.py、test_library.py、test_cli.py
scripts/dev/                      18 支開發腳本（run_scenario.py 取代 run_tactical_reference.py）
ui/                               ?run=、run 選單、e2e 改為讀服務
Dockerfile、docker-compose.yml    Node 階段建 UI；skyvault serve / worker
.github/workflows/ci.yml          scripts/dev、skyvault serve、SKYVAULT on its own、UI 經 skyvault serve
skyvault.__version__              2.1.0
```

---

## 4. 這一輪發現的問題

```text
基線的選擇       計劃寫 military_squad_001；量了才知道它沒有壓力時只撐過 2/10 —— 改用 urban（8/10）
驗收的決定目標   新基線的 normal run 不需要決定，對它決定是 404 而不是 403 —— may not 的檢查改用 high-risk run
World Contract   「至少 8 個 scenario」是 Phase 20 時的數量，不是能力 —— 改為三個 domain 都在且全部通過契約
訓練資料         只用軍事 scenario 時真成功是 0 —— 加入空域與城市（7 真、4 假）
比較報告         store 以 sort_keys 存 JSON，讀回的 batch 讓「Best per metric」換順序（原本就存在，介面改讀 store 才露出）
UI 路由的分層測試   以 node.module 比對 "..service"，相對 import 的 module 不含點 —— 那個測試從來不會失敗
serve 的 SQLite   sqlite:////abs 的資料夾沒有建立（測試抓到）
UI 路由的 404    以 LookupError 判斷「沒有這場 run」，KeyError 也是 LookupError —— 壞掉的結果被讀成 404，
                 也遮住了兩個變異（exploration 的完成狀態、同一 scenario）→ NoSuchRun
skyvault | head   BrokenPipeError（實際使用時抓到）
run 選單         隱藏的 <option> 被 e2e 的文字搜尋先找到；390px 時選單把頁面撐到 446px
egg-info         pip install -e 寫出的 SOURCES.txt 仍列著舊的 policy 檔 —— 守護測試跳過 pip 的產物，.gitignore 加上
cli 的分層       頂層模組一律算 core —— tests/layers.py 讓頂層模組也能有 rank（cli = 6）
```

---

## 5. 品質狀態

| 項目 | 結果 |
|---|---|
| pytest | 1578 passed（Redis + PostgreSQL；code review 前 1516、code review 後 1546）；沒有服務、從 /tmp：1496 passed、82 skipped；Python 3.10 venv 1578 passed |
| 覆蓋率 | 99.22% |
| 跨 PYTHONHASHSEED | skyvault acceptance 的 acceptance.json 逐位元相同，且等於 commit 的 output/v2 |
| ruff / black / mypy / bandit | 通過（mypy 173 個檔案） |
| CI 步驟 | 在乾淨的複本裡逐字執行，全部通過 |
| 介面 | Chromium 10 項檢查通過（本機與 CI 的 ui job） |
| 反向驗證 | 13 個變異；兩個存活（exploration 的完成狀態與同一 scenario）→ 發現 404 吞掉 KeyError → NoSuchRun 與兩個測試 → 全部紅 |

---

## 6. 已知限制

| 項目 | 留待 | 原因 |
|---|---|---|
| 只支援 editable 安裝 | 打包 data 時 | SKYVAULT 讀 repo 裡的 data/；Docker 也用 -e |
| 一場 run 的失敗地圖與比較取同一 scenario 最近一次的 | 需要時 | 不分版本 |
| 參考切片的回歸依賴 fork | 需要時 | batch 的 process pool 在 Linux 以 fork 繼承已註冊的 policy；spawn 時靠 SKYVAULT_POLICY_MODULES 重新匯入 |
| 介面不能提交工作 | 需要時 | 提交經 skyvault 或 API |

---

## 7. 驗證

```bash
pip install -e .
skyvault acceptance                       # ACCEPTED，15 / 14 / 6 / 5
skyvault serve & skyvault run military_urban_001/v0.2   # 528 events、78aa3fe5bbdf
python3 -m pytest tests/ -q              # 1578 passed（有 Redis / PostgreSQL；沒有時 1496 passed、82 skipped）
```

---

## 8. 一句話總結

> Phase 21 讓 SKYVAULT 成為一個只靠自己就能運作的系統：一個指令啟動服務、worker 與介面，每一項工作都經服務提交，介面從服務讀結果 —— Phase 0 的參考切片與開發腳本退回到它們該在的地方，而部署加入自己的 scenario 與 policy 用的，正是測試取得參考切片的同一條路。
