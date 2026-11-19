# 023 — Standalone SKYVAULT：只靠完成的系統本身運作

狀態：已採納
日期：2026-11-10
階段：Phase 21 — Standalone SKYVAULT v2.1（roadmap 之後由使用者加入）

## 背景

使用者的要求（2026-11-09，原文見 [`../plan/phase21_standalone.md`](../plan/phase21_standalone.md)）：SKYVAULT 運作時要靠完成的系統本身，不依賴 Phase 0 設下的 fixture 與背景；reference 的 .py 不應用來啟動，系統不應依賴那些設定腳本；開發用的東西在 SKYVAULT 實際運作時不應被引用。

開設時的測量：核心引擎叫 `SkyVaultTacticalReferenceEngine`，沒有指定 policy 也沒有 domain 時退回 Phase 0 的 `tactical_reference_policy`，`skyvault_tactical_reference_engine` 寫進每筆 engine event；v2 驗收、batch、失敗探索、訓練資料的預設都是 `tactical_reference_001`；啟動靠 `scripts/` 的二十支腳本，網頁介面只讀其中三支寫出的 `output/`；Docker 啟動 `scripts/serve_world.py`。

使用者的三個選擇：引擎改名並移除退回；參考切片「降為開發用」＋「從系統完全刪除」；一個入口＋介面讀服務。

## 決定

### 1. 引擎

`SkyVaultEngine`，system id `skyvault_engine`。scenario 必須說明誰做決定：`runtime.policy` 或 domain pack 的預設 policy；兩者都沒有 → `ContractError`（`require_decider`），world service 在入列前就拒絕（422）。所有 output_hash 因 system id 改名而改變（行為不變：每個 scenario 的結果與事件數相同，reference trace 只差 digest）。

### 2. 參考切片

policy、四個 scenario 版本與 batch 搬到 `tests/fixtures/reference/`，系統裡的副本刪除；`src/`、`data/`、Dockerfile、compose 與 pyproject 不得出現 `tactical_reference`（`tests/test_standalone.py`，含一個會被抓到的植入檔反例），`src/` 不 import、不讀 `tests/` 或 `scripts/`。

### 3. 部署加入自己的東西（測試也用同一個方法）

`skyvault.library`：依名稱找 scenario 與 batch 時，先找 `data/`，再找 `SKYVAULT_SCENARIO_PATH` / `SKYVAULT_BATCH_PATH` 列出的資料夾（每個名稱只能在找到它的資料夾之內解析）；呼叫者自己指定資料夾時只找那裡。`SKYVAULT_POLICY_MODULES`：第一次遇到未知的 policy 名稱時匯入這些模組。`tests/conftest.py` 以這三個變數取得參考切片 —— 不是特例，是部署會用的同一條路，而且測試跑的腳本子程序自然繼承。

### 4. 系統基線

`military_urban_001` v0.2，而不是計劃寫的 `military_squad_001`：測量時 squad 在沒有壓力下 RED 只撐過 2/10 個 seed（failure map 會在第一級就斷，Phase 15 的教訓），urban 是 8/10，五個變數中四個能壓垮它，兩個 doctrine 替代方案較差（5/10、3/10）。v0.2 由 spec 的新欄位 `revisions` 產生（`reference.py` 的 `revised`），doctrine 變體同時寫在 v0.2 旁；v0.1 不變。

### 5. v2 驗收

NEXUS 的任務、normal run、replay、world、conflict 都改用基線，仍是 ACCEPTED（15 / 14 / 6 / 5）。may not 的決定嘗試改用 high-risk run（那是等著權威決定的 run；新基線的 normal run 不需要決定，對它決定是 404 而不是 403）；World Contract 的必備改為「每個 scenario 通過契約且三個 domain 都在」，不再數「至少 8 個」。

### 6. 訓練資料

sources 換成基線、它的兩個替代方案、三種嚴重壓力、四個軍事 scenario、空域與城市；batch 換成 military_doctrine 與 airspace_sensors。測量：46 clean、27 risky、47 rejected；7 個真成功、4 個假成功（只用軍事時真成功是 0 —— 驗收「區分成功與假成功」需要兩種都有）。

### 7. 一個入口

`skyvault`（`[project.scripts]`，`src/skyvault/cli.py`）：`serve`（edition 的 world service、內建 worker、UI 掛在最後）、`worker`、`run`、`explore`、`batch`、`replay`、`cancel`、`world`、`status`、`runs`、`result`、`briefing`、`products` 經 HTTP 提交給服務；`virtual-test`、`acceptance` 在本程序計算。拒絕與連不上都是一行理由與 exit 1；`| head` 不出錯。

### 8. 介面讀服務

world service 加 `/api/runs` 與 `/api/runs/{run}/{overview,timeline,map,causal,package,failure,comparison,report.*}`、`/ws/replay?run=`（`service.add_view_routes`，路由只讀、不模擬）。一場 run 的 workspace = 它的 result package ＋ 同一 scenario 最近一次完成的 failure exploration 與 batch（`worldservice.views`）。UI 以 `?run=` 選 run（預設最新），右上角列出服務裡的 run；`service/app.py` 的 workspace 模式刪除。

### 9. scripts

二十支腳本移到 `scripts/dev/`（`run_tactical_reference.py` 改名 `run_scenario.py`，預設基線）；`serve_ui.py`、`serve_world.py`、`world_worker.py` 由 `skyvault` 取代後刪除。`run_external.py` 重播的是測試的外部系統 fixture（建在參考切片上），它自己把參考切片加進三個變數。

### 10. Docker 與 CI

Dockerfile 多一個 Node 階段建 UI，以 editable 安裝（SKYVAULT 讀 repo 的 `data/`），`CMD skyvault serve`；compose 用 `skyvault serve` / `skyvault worker`。CI：開發腳本的逐檔驗證以三個變數取得參考切片、呼叫 `scripts/dev/`；world service 與外部系統的步驟改用 `skyvault serve`；新的「SKYVAULT on its own」步驟在空資料夾、三個變數都 unset 的情況下只用 `skyvault` 跑完 run、explore、batch、runs、briefing、介面路由、拒絕參考切片、acceptance，最後確認沒有 `output/`；UI job 以 `skyvault serve` 提供並提交 run 後逐頁驗證。

### 11. 版本

runtime 2.1.0。

## 開發中的決定

### 12. 比較報告的指標順序

store 以 `sort_keys` 存 JSON；從 store 讀回的 batch 讓 comparative report 的「Best per metric」換了順序。改為固定依 `METRICS` 的順序（回歸測試：sort_keys 往返後報告相同）。

### 13. UI 路由的分層測試原本是空的

「world service 不 import UI 後端」的測試以 `node.module.startswith("..service")` 判斷，但相對 import 的 `node.module` 不含點 —— 這個測試從來不會失敗。現在方向反過來（world service 掛 UI 的路由），改測真正重要的：UI 路由不 import world service、engine、batch，並正確解析相對 import。

### 14. 驗收的 decided_by 目標

見決定 5。

### 15. `cli` 在分層的最上面

`tests/layers.py` 以頂層套件定 rank；頂層模組（`cli.py`）原本一律算 core。改為頂層模組也可以有 rank，`cli` = 6。

## 後果

```text
好處    pip install -e . 之後一個指令就是完整的 SKYVAULT：服務、worker、介面、所有工作；不需要 output/、不需要任何腳本
        Phase 0 的切片仍在測試裡釘住二十個 Phase 建在其上的行為，但系統一個字都不提它
        部署加入自己的 scenario、batch、policy 有正式的方法；測試用的就是它
代價    所有 output_hash 改變一次（行為不變，舊 → 新記錄在完成報告）
        只支援 editable 安裝（data/ 不在套件裡）
        一場 run 的失敗地圖與比較取同一 scenario 最近一次的，不分版本
```
