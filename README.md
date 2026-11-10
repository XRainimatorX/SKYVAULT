# SKYVAULT

一套 **AI-operated world / environment engine**。

SKYVAULT 創造可運行的虛擬世界與環境，讓其他 AI、系統、人類決策、裝備方案、戰術方案、治理方案可以進入其中被**測試、運行、記錄與分析**。

它回答的問題是：**如果這樣做，世界會怎麼變化？**

```text
世界
  ├─ 空間      ├─ 行動      ├─ 狀態變化
  ├─ 時間      ├─ 事件      ├─ 記錄
  ├─ 實體      ├─ 因果      └─ 結果分析
  └─ 規則
```

## 它不是什麼

```text
❌ 不是單純戰棋遊戲        遊戲只是表面形式，目標是測試決策與系統後果
❌ 不是單純軍事模擬器      軍事只是第一個應用場景，不是全部
❌ 不是 TAC ANGEL          那是戰術決策者；SKYVAULT 是戰術可被測試的世界
❌ 不是 STARTX             那做戰略推演；SKYVAULT 提供可驗證世界
❌ 不是 NEXUS              那是總入口與編排者；SKYVAULT 是被調用的世界環境
```

## 定位

SKYVAULT 是**接口型核心環境**，不是任何系統的上級：

```text
NEXUS       調度 SKYVAULT，讀取其結果
STARTX      把戰略方案交給 SKYVAULT 驗證
TAC ANGEL   在 SKYVAULT 世界內測試戰術行動
EIDEN-01    將情報轉成 SKYVAULT 的世界參數
```

它的重要性不來自統治其他系統，而來自：**很多系統需要一個共同環境來測試自己。**

---

## 目前的實作

SKYVAULT 是一個完整的系統，用一個指令 `skyvault` 啟動與使用（Phase 21）：它啟動 world service、worker 與網頁介面，所有工作都經服務提交，介面從服務讀任何 run。運作時不依賴任何開發用的腳本或測試資料 —— Phase 0 的 tactical reference slice 只留在 `tests/` 當回歸測試。每一場 run 都走同一條世界迴圈：

```text
scenario → world state → actor policy → action → validation
→ consequence → world mutation → event memory → evaluation → result package
```

世界本身由 World Contract 建立（`src/skyvault/runtime/`）：grid / graph / network 三種空間、tick / phase / event-driven 三種時間、實體登記、資源帳，任一時刻的世界都能只靠 event memory 還原。scenario 必須說明誰做決定：`runtime.policy` 指名一個 policy，或它的 domain pack 帶預設 policy —— 都沒有就被拒絕，SKYVAULT 不替它挑一個。系統的基線是 `military_urban_001` v0.2。

actor 的每個 action 都走同一條路（`src/skyvault/actions/`）：驗證 → 結算出 Consequence → 套用，每個改動一筆帶 action id 的 event。十種 action type（move、attack、observe、wait、repair、supply、deploy、withdraw、scan、communicate），軍事線使用其中五種。

每次 run 都可重現（Phase 8）：event 與 action 的 id 是決定性的，同一輸入得到同一個 output_hash；每個 result package 帶著 input_hash、規則版本與執行版本；scenario 以版本資料夾管理、可比較差異；run 記在 registry、可從 result package 重跑驗證。

方案可以被故意弄壞（Phase 9）：八個 failure variable、四個壓力等級、多個 seed，找出方案在哪裡、為什麼、多快崩潰，哪個變量壓垮它、哪個替代方案撐更久、現實前必須改什麼。

很多方案可以一起比較（Phase 10）：版本、參數掃描、外部系統的命令，各跑上百次、可平行，並排比較勝率、成本、風險與失敗頻率。互相衝突的命令不替任何人選：每組相容的命令各成一個分支跑完，交出一份 conflict package 讓 NEXUS 或使用者決定。

第一個 domain pack（Phase 13）：軍事 / 戰術 —— 單位、編隊、地形、感測、武器、後勤、士氣、指揮延遲、任務九種 profile，小隊、城市、山地、交通節點四個 reference scenario，doctrine 比較；TAC ANGEL 或任何外部 policy 可以取代 baseline，每個決定都能匯出成 state-action-outcome 訓練資料。domain pack 不是 core：同一個 engine 照跑。

第二個 domain pack（Phase 14）：城市 —— 八個城區在道路網上，治安隨糧食、電力、醫療、警力與行政起落；一座變電站倒下時負載轉給備援、超載的跟著跳脫，連鎖可以逐筆追到源頭；補給車隊沿最短路送糧，延遲真的會晚到；每一場都輸出 governance stability score。城市沒有對手、跑滿時限，結果叫 order_restored 而不是「CITY 存活」。

第三個 domain pack（Phase 15）：空域 —— 低空無人機分波飛向資產，雷達每個 tick 抽一次看不看得到、還會誤報，指揮節點建立航跡、可能認錯敵我、要等反應延遲才放行，攔截器齊射、裝填、打完彈藥就停。HADES 交出交戰規則、AEROGRID 移動或開關雷達、SKYFOX 在同一片天空巡邏（可能被自己人擊落）；每一場都輸出 detection gap、response time，以及每個漏過的原因。

裝備在造出來之前先測（Phase 16）：一份 EXO / PAX / MSX / ERX 的 profile 經過 physics-lite 規則（穩定、關節負載、接地壓力、能量、散熱、尺度）、工程可行性（材料、維修、零件、供應鏈、修復環境）與軍事任務裡和原單位的比較，得到三個分數；壓力條件下列出它在哪一級、按什麼順序垮掉，constraint solver 算出要改到多少，太接近邊線時標明需要真正的工程仿真；最後判斷 continue、redesign、reject 或 require_external_simulation。

一顆核心、兩個版本（Phase 19）：版本是一個 JSON 檔。內部版是核心原樣、一個能力都不少；商業版（SKYVAULT Studio）不掛內部系統的介面、回應裡沒有任何內部系統名稱，提供六個產品 —— 危機規劃、城市韌性、AI 情境測試、裝備概念篩查、訓練與事後回顧、風險模擬 —— 每個都從核心的一次真實 run 讀出 KPI 與結論。客戶做出來的場景帶著來源回到核心。

完整的 v2.0（Phase 20）：一個指令在同一個服務上跑完開發計劃的十五條最終驗收、十四項必備能力與 Final Authority Boundary 的十一條，交出一份每條附證據的驗收報告。SKYVAULT 可以模擬、建議、警告、返回 failure map 與 conflict package、拒絕 invalid scenario；它不可以做主權決定、推翻 NEXUS 或 STARTX、取代人類權威、自行決定最終戰略 —— 而且這在契約層強制：任何設定、任何寫法都不能讓 SKYVAULT 成為決定者。

每個系統看到自己的世界（Phase 5）：observer profile 決定 TAC ANGEL 看一個單位周圍、STARTX 看趨勢、NEXUS 看任務、HADES 看威脅、AEROGRID 看覆蓋；看不到的敵人不出現，看得到的帶 confidence，過期的接觸標明幾 tick 前、延遲的系統看到較早的 tick。外部 policy 可以只拿 observation 決定 —— engine 根本不給它 world。

誰來決定被拆出 core（Phase 6）：每個單位可以由不同的 participant 決定 —— 規則、腳本、人、外部系統、LLM 輔助，或 TAC ANGEL / STARTX / HADES / AEROGRID / SKYFOX 的 adapter —— 它們只能交出 Action 意圖。讀世界的 policy 拿到唯讀的世界，任何寫入當場被擋下；core 不 import 任何 policy，部署自己的 policy 以 `SKYVAULT_POLICY_MODULES` 帶進來。

SKYVAULT 可以當後台服務跑（Phase 11）：任務從 HTTP API 進來、排隊（優先序、上限）、在 worker 上跑（同一個程序，或 RQ + Redis 的 worker），結果存在 SQLite 或 PostgreSQL，可查、可下載、可重播；persistent world 可以一次推進幾個 tick。每個 run 都受 Resource & Compute Governance 約束：失控的 run 被自動停下並交出 partial result，過大的 batch 在門口被拒。

其他系統用自己的語言接入（Phase 12）：NEXUS 交任務、拿回完整的 result package 與 briefing；STARTX 交分支、拿回分支比較；TAC ANGEL 在進行中的世界下命令、拿回自己命令的 state-action-outcome；EIDEN-01 的情報、SKYFOX 的路線、HADES 的防禦、星衞的裝備、AEROGRID 的覆蓋各自得到 Formal Spec §9 寫明的返回；沒有模型的（CYBERHOUND 的資訊環境）得到缺口，而不是假的模擬。兩個系統的命令互相衝突時，世界停下、每個分支從同一段歷史分叉跑完、交回 conflict package；需要決定的結果（高風險、策略取捨、衝突分支、跨過 failure threshold）一律以 authority handoff 交給 NEXUS 或指定權威 —— SKYVAULT 自己想決定，得到的是 403。

模擬結果可以變成訓練資料（Phase 18）：每個決定一筆 transition（state、observation、action、consequence、reward、next_state…），每個 run 標記六種刷分行為；刷分的 run 進 rejected、不進主訓練集，「成功」與「假成功」分開標示；STARTX 拿到分支評估；匯出 JSONL / Parquet，登記在 training data registry，並建 RAG index。

結果不用打開 JSON 就能看懂（Phase 17）：一個網頁介面有總覽、逐 tick 的時間線、地圖 replay、因果鏈、失敗地圖、方案比較與 result package；briefing report 可匯出成 PDF、Word 或 Markdown，同一份結果每次逐位元相同。介面由 world service 本身提供（Phase 21）：選單列出服務裡的每一場 run，失敗地圖與比較取自同一個 scenario 最近一次的 failure exploration 與 batch。

每次 run 結束後依 evaluation profile 做多軸評估（`src/skyvault/evaluation/`）：11 軸分數、pass / fail / risky / needs_more_test 的判斷與信心、失敗原因、建議下一步測試，並標記靠不行動、犧牲穩定或忽略風險拿到的高分。

各階段的實際進度與交付紀錄在 [`docs/phases/`](docs/phases/)，開發順序見 roadmap。

---

## 快速開始

```bash
git clone https://github.com/XRainimatorX/SKYVAULT.git
cd SKYVAULT
python3 -m pip install -e .                       # 安裝 SKYVAULT 與 skyvault 指令
(cd ui && npm ci && npm run build)                # 第一次需要：網頁介面（Node 22）
skyvault serve                                    # world service + worker + 介面：http://127.0.0.1:8000
```

需要 Python 3.10+；相依全部宣告在 `pyproject.toml`。用 `-e`（editable）安裝：SKYVAULT 讀它自己在 repo 裡的 `data/`。

另開一個終端機，所有工作都經服務提交（`--url` 或 `SKYVAULT_URL` 指向別的服務）：

```bash
skyvault run military_urban_001/v0.2              # 跑一場，等它結束，印出結果
# job_000001  completed
#   events: 528
#   output_hash: 78aa3fe5bbdf…
#   result: no_winner_duration_limit
skyvault explore military_urban_001/v0.2          # 在哪裡失敗、被什麼壓垮、哪個替代方案撐更久
skyvault batch military_doctrine                  # 三種 doctrine 各跑 100 次並排比較
skyvault runs                                     # 介面能看的每一場 run
skyvault briefing latest --format pdf             # 帶進會議的文件（md / pdf / docx）
skyvault replay job_000001                        # 重跑一場，確認逐位元重現
skyvault world create military_squad_001/v0.1     # persistent world：然後 advance / finish
skyvault products                                 # 這個版本的產品（serve --edition commercial 是商業版）
skyvault status
```

打開 http://127.0.0.1:8000 看同一場：總覽、時間線、replay、因果鏈、失敗地圖、比較、result package、briefing；右上角選另一場 run。

不需要服務的兩個：

```bash
skyvault virtual-test pax_test_001                # 一份裝備 profile 的三重篩查與判斷
skyvault acceptance                               # 完整 v2.0 的驗收：15 / 14 / 6 / 5 → ACCEPTED
```

部署自己的 scenario、batch 與 policy 不需要改 SKYVAULT：`SKYVAULT_SCENARIO_PATH`、`SKYVAULT_BATCH_PATH` 加資料夾（排在 `data/` 之後），`SKYVAULT_POLICY_MODULES` 加 policy 模組。用 Redis 與 PostgreSQL：`skyvault serve --queue rq --redis … --store postgresql://…` 加上 `skyvault worker`；或 `docker compose up --build`。

跑測試：

```bash
python3 -m pytest tests/ -q
```

## 產出什麼

服務保存每個 job 的紀錄與結果（SQLite 或 PostgreSQL）：`skyvault result <job>` 下載 result package，`/api/runs/<run>/…` 是介面的每個畫面，`skyvault briefing` 是 briefing。開發用腳本（見「開發」）把同樣的內容寫進 `output/`：

| 檔案 | 這是什麼 |
|---|---|
| `event_memory.json` | **真相來源。** 這場發生過的每一件事 |
| `result_package.json` | 一次執行的完整包裝（起始狀態、終局狀態、事件、評估） |
| `final_state.json` | 終局世界狀態 |
| `timeline.txt` | 人類可讀的過程 |
| `replay_state_at_tick.json` | 每個 tick 結束時的世界 |
| `entity_history.json` | 每個單位的一生 |
| `causal_chain.json` | 哪個 action 造成哪些 event |
| `evaluation_result.json` | 多軸判斷：值不值得、危不危險、為什麼 |
| `score_breakdown.json` | 每一軸的分數、原始值與說明 |
| `anti_gaming_report.json` | 高分是不是刷出來的 |
| `tradeoff_report.md` | 得到什麼、付出什麼 |
| `failure_map.json` | （explore_failures）在哪裡失敗、為什麼、哪個變量壓垮、哪個替代方案撐更久 |
| `collapse_sequence.json` | （explore_failures）崩潰時己方單位依序怎麼倒下 |
| `survival_conditions.json` | （explore_failures）每個變量撐到哪一級 |
| `recommended_modifications.md` | （explore_failures）現實前必須改什麼 |
| `batch_result.json` | （run_batch）每個變體的勝率、成本、風險、失敗頻率與每個 run |
| `branch_comparison.json` | （run_batch）變體並排、各指標誰最好 |
| `conflict_package.json` | （run_batch）哪些命令衝突、每個分支的結果、等人決定 |
| `comparative_report.md` | （run_batch）給人讀的比較報告 |
| `briefing.md`、`.pdf`、`.docx` | （export_briefing）以上全部，一份帶進會議的文件 |
| `city/` | （run_city）每座城市的 governance stability score、停電連鎖、補給延遲研究與 city_report.md |
| `airspace/` | （run_airspace）reference 空域的 detection gap、response time、failure points；HADES 規則與 AEROGRID 配置的比較；airspace_report.md |
| `virtual_test/` | （run_virtual_test）每份裝備的 equipment_test_result 與 virtual_test_report.md |
| `products/` | （run_products）一個版本的每個產品：問題、KPI、結論（redact 後）與 products.md |
| `v2/` | （run_v2_acceptance）acceptance.json（每條檢查與證據）與 acceptance.md |
| `external/<system>.json` | （run_external）九個系統各自拿回什麼；`conflict_*.json`：一個衝突的 package、handoff 與決定 |

timeline 到 causal_chain 四個與評估四個，都是從 result package 推導出來的，刪掉重跑會一樣。

---

## 文件

| 你想知道 | 去哪 |
|---|---|
| 系統怎麼運作、模組怎麼分工 | [`docs/architecture.md`](docs/architecture.md) |
| 我要接手這個專案 | [`docs/handoff.md`](docs/handoff.md) |
| Phase 4 時的完整技術參考（凍結） | [`docs/phases/phase4_tactical_slice.md`](docs/phases/phase4_tactical_slice.md) |
| 某個階段做了什麼 | [`docs/phases/`](docs/phases/) |
| 資料格式長什麼樣 | [`docs/spec/contracts.md`](docs/spec/contracts.md) |
| 每個 Phase 要做什麼、照什麼順序 | [`docs/plan/`](docs/plan/) |
| 為什麼這樣設計 | [`docs/decisions/`](docs/decisions/) |
| 上個階段的回顧 | [`docs/postmortems/`](docs/postmortems/) |

各階段的任務規格與驗收標準寫在 [GitHub Issues](https://github.com/XRainimatorX/SKYVAULT/issues)。

---

## Repo 結構

```text
src/skyvault/       SKYVAULT 本身
  cli.py            skyvault 指令：serve、worker、run、explore、batch、briefing、acceptance…
  library.py        依名稱找 scenario 與 batch：data/ 之後是 SKYVAULT_SCENARIO_PATH / SKYVAULT_BATCH_PATH
  contracts/        26 份資料契約（Pydantic，schema 0.6）
  runtime/          世界的積木：空間、時間、實體登記、資源、規則、快照、event sourcing
  actions/          action 的驗證、結算與套用；十種 action type
  evaluation/       多軸評估、防刷分、trade-off report
  reproducibility/  hash、版本、scenario 比較、run registry
  failure/          failure variables、壓力測試、failure map
  batch/            批量、平行、參數掃描、衝突分支、conflict package
  views/            每個畫面的內容，從一場 run 的結果推導
  report/           briefing（Markdown / Word / PDF）
  service/          網頁介面的路由（一場 run 的畫面、replay WebSocket、靜態 UI），掛在 world service 上
  policies.py       policy registry：外部 policy 從這裡接入
  domains/military/ 第一個 domain pack（不是 core）
  domains/city/     第二個 domain pack：道路網上的城市、治安、電力連鎖、補給、governance score
  domains/airspace/ 第三個 domain pack：空域、機率偵測、航跡、攔截、HADES / SKYFOX / AEROGRID
  virtualtest/      裝備的三重篩查：physics-lite、工程、戰術、壓力、solver、surrogate、外部仿真、判斷
  editions/         一顆核心兩個版本：manifest、redact、edition 服務、六個產品、反哺
  acceptance/       完整 v2.0 的驗收：十五條、十四項、十一條邊界，在同一個服務上
  boundary.py       Final Authority Boundary：role、may、may not
  training/         訓練資料：transition、anti-gaming 標籤與過濾、分支評估、registry、RAG index
  observation/      觀測層：observer profile、fog of war、confidence、delay、stale、五種 view
  actors/           誰決定：唯讀世界、十種 actor 與 adapter、ActionQueue、participants
  worldservice/     後台服務：governance、store、queue、jobs、persistent world、HTTP API、介面讀的 runs
  interface/        外部系統：九個 adapter、conflict 的分支與決定、authority handoff、外部 API
ui/                 網頁介面（Next.js、ECharts）
  schemas/          由契約產生的 JSON Schema
scripts/dev/        開發用腳本：重產 output/、建 domain scenario、匯出 schema（SKYVAULT 運作時不用）
data/scenarios/     scenario 輸入，每個 scenario 一個資料夾、每個版本一個檔
data/evaluation_profiles/   評估 profile（balanced、tactical）
data/batches/       batch 請求
data/domains/       domain pack 的 profile、rules 與 scenario spec（military、city、airspace）
data/virtualtest/   virtual test 的規則與四份裝備 profile
data/editions/      版本（internal、commercial）與產品目錄
data/v2/            完整 v2.0 的驗收清單
data/training/      訓練資料要匯出哪些 run
data/observers/     五個系統的 observer profile
data/service/       world service 的 governance 政策
examples/           外部 policy 範例（TAC ANGEL 的介面）
tests/              測試；fixtures/reference/ 是 Phase 0 的參考切片（policy、scenario、batch），只供回歸測試
output/             執行產物
docs/               文件
```

細節見 [`docs/architecture.md`](docs/architecture.md)。

---

## 已知限制

| 項目 | 影響 | 留待 |
|---|---|---|
| failure variable 只改既有能力值、hp、資源與命令傳達 | 沒有真的感測、通訊、天氣模型；例如感測失效 = 己方命中率下降 | 需要那些模型的 domain |
| failure exploration 循序執行 | reference 的設定共 760 次 run，約 12 秒；batch 已可平行，explore 尚未改用 | 需要時 |
| 衝突偵測只看命令本身與開場存量 | 不知道執行到那個 tick 時的世界；對 tick 1 的命令沒有差別 | 需要時 |
| 衝突時分支從 tick 0 重跑 | engine 不能序列化；每個分支 5 次 | engine 可序列化時 |
| CYBERHOUND、EIDEN 的世界參數 | 回報為缺口，不模擬（AEROGRID 的空域、星衞的裝備參數已有模型） | 需要時 |
| 商業版的 redact 是字串層級 | 新增內部名稱要加進 data/editions/commercial.json；CI 掃描外洩 | 需要時 |
| 裝備篩查的係數是假設 | physics-lite 門檻、一個軍事 tick = 10 分鐘、hp 係數代表防護；FMI / FMU 尚未接上 | 有真實資料時 |
| 城市的係數是手調的 | 依 20 個 seed 的測量訂定，不是校準過的真實城市；沒有 GIS | 有真實資料時 |
| 空域只有 2D、兩種高度，威脅只會直線飛 | 沒有閃避、改目標；HADES 不能指定攔截器、AEROGRID 不能新增感測器 | 計劃寫 3D later |
| briefing 不敘述城市的狀態變化 | 「What happened」只數行動；NEXUS 拿 domain_outcome，人讀 output/city/city_report.md | 需要時 |
| 軍事 baseline policy 用自己的感測 | 每個單位自己看；觀測層是整個陣營共享；沒有視線 | 需要時 |
| 軍事任務不在 core 的評估與 batch 指標裡 | doctrine 比較的 batch 比勝率與失敗頻率，任務達成率另由 mission_outcome 判定 | 未定 |
| 訓練資料的 observation 不是觀測層產生 | 軍事用 pack 的感測，其他是整個世界的狀態（標明 observation_model: full_state） | 需要時 |
| 觀測只支援 grid | 與 tactical engine 相同 | 對應的 engine 出現時 |
| 讀世界的 policy 慢約 18%（軍事） | 唯讀代理的成本 | 有需要時 |
| persistent world 不能跨程序恢復 | engine 不能序列化；checkpoint 與結果留在 store | 需要時 |
| batch 內的每個 run 不受 auto-stop | 受 max_batch_count 與 scenario 時限約束 | 需要時 |
| Docker 只做靜態驗證 | 此環境沒有 daemon；CI 跑 `docker compose config` | — |
| RQ worker 用它自己的 governance | edition 的決定者要由呼叫者以 edition_policy 帶進佇列 | 需要時 |
| v2 驗收是 in-process | 證明系統能做到，不證明某個部署的網路、身分驗證、資料庫設定 | 部署時 |
| 提交者的身分 | 誰可以自稱 NEXUS 不由 SKYVAULT 驗證 | 部署環境 |
| adapter 用內建替身 | 真正的 TAC ANGEL 等以 callable 或 HTTP 提交接入；沒有 LLM SDK、沒有真正的外部系統連線 | — |
| 介面不能編輯 scenario | 介面讀服務裡的 run；新的 run 經 skyvault 或 API 提交 | 需要時 |
| 一場 run 的失敗地圖與比較取同一 scenario 最近一次的 | 不分版本；要看某一次 exploration 得先讓它是最近的 | 需要時 |
| 只支援 editable 安裝 | SKYVAULT 讀 repo 裡的 data/；`pip install .` 的套件找不到它（Docker 也用 -e） | 打包 data 時 |
| 產品在請求裡同步執行 | 同時執行數受 max_parallel_runs 限制，多的回 429；不經佇列 | 需要時 |
| run registry 是本機 JSON Lines 檔 | 不跨機器共享；`runs/` 不進版本控制 | 需要共享時 |
| engine 只跑 tick | phase / event-driven 時間要直接用 `create_world()` 建；空間由 domain pack 宣告（城市用 graph） | 需要它們的 domain |
| `expected_duration` 只是宣告 | action 都在一步內完成；沒有持續多個 tick 的 action | 需要排程的 Phase |
| `state_changes`（環境變動）一律 raise | WorldState 沒有建模 environment_state | 需要它的 domain |
| risk_growth、stability_impact 是代理指標 | 沒有風險與穩定模型；用 affects_risk 事件與摧毀比例代替 | Phase 9 起 |
| Spec §8.3 的六個軸不評（physical_possibility 等） | 模擬中沒有資料來源 | 需要它們的 domain |
| consequence 的 evaluation_impact 不進評估 | consequence 不在 result package 裡，評估只讀紀錄 | 未定 |
| 單一 run 的 comparison 恆為空 | 單一 run 沒有比較對象；batch 的 branch_comparison 依平均分數填 | — |
| 快照只存在記憶體 | 程序結束就沒了；可由 event memory 重建 | 文件寫明 SQLite / PostgreSQL later |

完整清單見 [`docs/phases/phase21_standalone.md`](docs/phases/phase21_standalone.md) 與先前各 Phase 的完成報告。

---

## 開發

```bash
python3 -m pytest tests/ -q --cov                # 測試與覆蓋率
ruff check .                                      # linter
black --check src/ tests/ scripts/                # 排版
python3 -m mypy src/                              # 型別
python3 scripts/dev/export_schemas.py             # 改契約後重新產生 JSON Schema
python3 -m bandit -c pyproject.toml -r src/       # 安全掃描
```

所有設定集中在 `pyproject.toml`。

開發用腳本在 `scripts/dev/`：它們不經服務、直接呼叫函式庫，把結果寫進 `output/`（上表），用來重產 commit 的輸出與 CI 的逐檔驗證。SKYVAULT 運作時不 import、不需要它們（`tests/test_standalone.py` 守住）。

```bash
python3 scripts/dev/run_scenario.py               # 一場 run（預設 military_urban_001 v0.2）的十一個輸出
python3 scripts/dev/explore_failures.py           # failure_map 等四個
python3 scripts/dev/run_batch.py                  # batch_result 等四個（預設 military_doctrine）
python3 scripts/dev/export_briefing.py            # 從 output/ 寫 briefing
python3 scripts/dev/build_military_scenarios.py   # 由 spec 重建 data/scenarios/military_*（city、airspace 同）
python3 scripts/dev/build_training_data.py        # output/training/
python3 scripts/dev/run_v2_acceptance.py          # output/v2/
```

Phase 0 的參考切片在 `tests/fixtures/reference/`：測試以部署加資料的同一種方式取得它（`tests/conftest.py` 設定 `SKYVAULT_SCENARIO_PATH`、`SKYVAULT_BATCH_PATH`、`SKYVAULT_POLICY_MODULES`），它的回歸測試仍釘住 RED_survived / 97 events。

每次 push 與 PR 由 [`.github/workflows/ci.yml`](.github/workflows/ci.yml) 在乾淨環境（Python 3.10 與 3.11）跑上面全部檢查，外加：換工作目錄跑測試、檢查測試沒有讀 `output/`、JSON Schema 與契約一致、開發腳本的逐檔驗證、在空資料夾只用 `skyvault` 跑完一整輪（SKYVAULT on its own）；另一個 job 建 UI、以 `skyvault serve` 提供、提交 run，再用 Chromium 打開每個頁面驗證。

送 PR 前的檢查清單見 [`docs/handoff.md`](docs/handoff.md)。
