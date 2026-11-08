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

本 repo 目前是 **tactical reference slice** —— 第一個應用場景（軍事戰術）的參考實作，用來驗證整條世界迴圈能跑通：

```text
scenario → world state → actor policy → action → validation
→ consequence → world mutation → event memory → evaluation → result package
```

世界本身由 World Contract 建立（`src/skyvault/runtime/`）：grid / graph / network 三種空間、tick / phase / event-driven 三種時間、實體登記、資源帳，任一時刻的世界都能只靠 event memory 還原。tactical reference 只用其中的 grid + tick。

actor 的每個 action 都走同一條路（`src/skyvault/actions/`）：驗證 → 結算出 Consequence → 套用，每個改動一筆帶 action id 的 event。十種 action type（move、attack、observe、wait、repair、supply、deploy、withdraw、scan、communicate），軍事線使用其中五種。

每次 run 都可重現（Phase 8）：event 與 action 的 id 是決定性的，同一輸入得到同一個 output_hash；每個 result package 帶著 input_hash、規則版本與執行版本；scenario 以版本資料夾管理、可比較差異；run 記在 registry、可從 result package 重跑驗證。

方案可以被故意弄壞（Phase 9）：八個 failure variable、四個壓力等級、多個 seed，找出方案在哪裡、為什麼、多快崩潰，哪個變量壓垮它、哪個替代方案撐更久、現實前必須改什麼。

很多方案可以一起比較（Phase 10）：版本、參數掃描、外部系統的命令，各跑上百次、可平行，並排比較勝率、成本、風險與失敗頻率。互相衝突的命令不替任何人選：每組相容的命令各成一個分支跑完，交出一份 conflict package 讓 NEXUS 或使用者決定。

第一個 domain pack（Phase 13）：軍事 / 戰術 —— 單位、編隊、地形、感測、武器、後勤、士氣、指揮延遲、任務九種 profile，小隊、城市、山地、交通節點四個 reference scenario，doctrine 比較；TAC ANGEL 或任何外部 policy 可以取代 baseline，每個決定都能匯出成 state-action-outcome 訓練資料。domain pack 不是 core：同一個 engine 照跑。

第二個 domain pack（Phase 14）：城市 —— 八個城區在道路網上，治安隨糧食、電力、醫療、警力與行政起落；一座變電站倒下時負載轉給備援、超載的跟著跳脫，連鎖可以逐筆追到源頭；補給車隊沿最短路送糧，延遲真的會晚到；每一場都輸出 governance stability score。城市沒有對手、跑滿時限，結果叫 order_restored 而不是「CITY 存活」。

第三個 domain pack（Phase 15）：空域 —— 低空無人機分波飛向資產，雷達每個 tick 抽一次看不看得到、還會誤報，指揮節點建立航跡、可能認錯敵我、要等反應延遲才放行，攔截器齊射、裝填、打完彈藥就停。HADES 交出交戰規則、AEROGRID 移動或開關雷達、SKYFOX 在同一片天空巡邏（可能被自己人擊落）；每一場都輸出 detection gap、response time，以及每個漏過的原因。

裝備在造出來之前先測（Phase 16）：一份 EXO / PAX / MSX / ERX 的 profile 經過 physics-lite 規則（穩定、關節負載、接地壓力、能量、散熱、尺度）、工程可行性（材料、維修、零件、供應鏈、修復環境）與軍事任務裡和原單位的比較，得到三個分數；壓力條件下列出它在哪一級、按什麼順序垮掉，constraint solver 算出要改到多少，太接近邊線時標明需要真正的工程仿真；最後判斷 continue、redesign、reject 或 require_external_simulation。

一顆核心、兩個版本（Phase 19）：版本是一個 JSON 檔。內部版是核心原樣、一個能力都不少；商業版（SKYVAULT Studio）不掛內部系統的介面、回應裡沒有任何內部系統名稱，提供六個產品 —— 危機規劃、城市韌性、AI 情境測試、裝備概念篩查、訓練與事後回顧、風險模擬 —— 每個都從核心的一次真實 run 讀出 KPI 與結論。客戶做出來的場景帶著來源回到核心。

每個系統看到自己的世界（Phase 5）：observer profile 決定 TAC ANGEL 看一個單位周圍、STARTX 看趨勢、NEXUS 看任務、HADES 看威脅、AEROGRID 看覆蓋；看不到的敵人不出現，看得到的帶 confidence，過期的接觸標明幾 tick 前、延遲的系統看到較早的 tick。外部 policy 可以只拿 observation 決定 —— engine 根本不給它 world。

誰來決定被拆出 core（Phase 6）：每個單位可以由不同的 participant 決定 —— 規則、腳本、人、外部系統、LLM 輔助，或 TAC ANGEL / STARTX / HADES / AEROGRID / SKYFOX 的 adapter —— 它們只能交出 Action 意圖。讀世界的 policy 拿到唯讀的世界，任何寫入當場被擋下；tactical reference policy 可以被拔掉。

SKYVAULT 可以當後台服務跑（Phase 11）：任務從 HTTP API 進來、排隊（優先序、上限）、在 worker 上跑（同一個程序，或 RQ + Redis 的 worker），結果存在 SQLite 或 PostgreSQL，可查、可下載、可重播；persistent world 可以一次推進幾個 tick。每個 run 都受 Resource & Compute Governance 約束：失控的 run 被自動停下並交出 partial result，過大的 batch 在門口被拒。

其他系統用自己的語言接入（Phase 12）：NEXUS 交任務、拿回完整的 result package 與 briefing；STARTX 交分支、拿回分支比較；TAC ANGEL 在進行中的世界下命令、拿回自己命令的 state-action-outcome；EIDEN-01 的情報、SKYFOX 的路線、HADES 的防禦、星衞的裝備、AEROGRID 的覆蓋各自得到 Formal Spec §9 寫明的返回；沒有模型的（CYBERHOUND 的資訊環境）得到缺口，而不是假的模擬。兩個系統的命令互相衝突時，世界停下、每個分支從同一段歷史分叉跑完、交回 conflict package；需要決定的結果（高風險、策略取捨、衝突分支、跨過 failure threshold）一律以 authority handoff 交給 NEXUS 或指定權威 —— SKYVAULT 自己想決定，得到的是 403。

模擬結果可以變成訓練資料（Phase 18）：每個決定一筆 transition（state、observation、action、consequence、reward、next_state…），每個 run 標記六種刷分行為；刷分的 run 進 rejected、不進主訓練集，「成功」與「假成功」分開標示；STARTX 拿到分支評估；匯出 JSONL / Parquet，登記在 training data registry，並建 RAG index。

結果不用打開 JSON 就能看懂（Phase 17）：一個網頁介面有總覽、逐 tick 的時間線、地圖 replay、因果鏈、失敗地圖、方案比較與 result package；briefing report 可匯出成 PDF、Word 或 Markdown，同一份結果每次逐位元相同。

每次 run 結束後依 evaluation profile 做多軸評估（`src/skyvault/evaluation/`）：11 軸分數、pass / fail / risky / needs_more_test 的判斷與信心、失敗原因、建議下一步測試，並標記靠不行動、犧牲穩定或忽略風險拿到的高分。

各階段的實際進度與交付紀錄在 [`docs/phases/`](docs/phases/)，開發順序見 roadmap。

---

## 快速開始

```bash
git clone https://github.com/XRainimatorX/SKYVAULT.git
cd SKYVAULT
python3 -m pip install pydantic pyyaml networkx pandas fastapi uvicorn websockets python-docx reportlab pyarrow scipy
python3 scripts/run_tactical_reference.py
```

需要 Python 3.10+。模擬本身的相依有四個：`pydantic`（契約與 JSON Schema）、`PyYAML`（YAML scenario）、`networkx`（graph / network 空間的最短路與衝突分支）、`pandas`（批量彙整）；介面與 briefing 另用 `fastapi`、`uvicorn`、`websockets`、`python-docx`、`reportlab`。裝備篩查的 constraint solver 用 `scipy`。全部宣告在 `pyproject.toml`。建 UI 需要 Node 22。

跑完會在 `output/` 產生十一個檔案，最後一行是評估判斷：

```text
Verdict: risky (score 0.50, profile balanced)
```

驗證這次的結果可以重現、換另一個 scenario 版本：

```bash
python3 scripts/verify_run.py output/result_package.json
# Reproduced: yes
python3 scripts/run_tactical_reference.py --scenario data/scenarios/tactical_reference_001/v0.2.json
# Result: BLUE_survived（v0.2 只把 blue_002 的命中率從 0.55 調到 0.75）
```

故意惡化這個方案（約 12 秒；`--repeats 2` 約 3 秒）：

```bash
python3 scripts/explore_failures.py
# Survives without stress: 60%
# Crushed by: communication_failure
# Best alternative: v0.1-support-rear
```

把三個部署、三個敵方命中率與三道互相衝突的命令各跑 100 次（900 次 run，4 個 worker 約 5 秒）：

```bash
python3 scripts/run_batch.py
# Best mean score: support-rear
# Conflicts: 2; branches: P1, P2+P3; decision required: True
```

把上面三個腳本的結果寫成 briefing，或打開網頁介面：

```bash
python3 scripts/export_briefing.py              # output/briefing.md、.pdf、.docx
(cd ui && npm ci && npm run build)              # 第一次需要
python3 scripts/serve_ui.py                     # http://127.0.0.1:8000
```

跑軍事 domain pack 的 scenario、讓外部 policy 指揮、匯出訓練資料：

```bash
python3 scripts/run_tactical_reference.py --scenario data/scenarios/military_urban_001/v0.1.json
python3 scripts/run_tactical_reference.py --scenario data/scenarios/military_squad_001/v0.1.json \
    --policy-module examples/tac_angel_policy.py --policy tac_angel_example
python3 scripts/run_batch.py --batch data/batches/military_doctrine.json   # 三種 doctrine 並排
python3 scripts/export_dataset.py                                          # output/tac_angel_dataset.jsonl
python3 scripts/build_training_data.py --workers 4                         # output/training/：三個集合與報告
python3 scripts/observe_run.py                                             # output/observations/：五個系統各自看到什麼
python3 scripts/run_tactical_reference.py --scenario data/scenarios/military_squad_001/v0.1.json \
    --participants tests/fixtures/actors/participants_squad.json            # RED 由 TAC ANGEL / HADES、BLUE 由 baseline
python3 scripts/serve_world.py                                             # world service：http://127.0.0.1:8100/api/docs
python3 scripts/run_external.py                                            # output/external/：九個系統各自拿回什麼、一個衝突
python3 scripts/run_tactical_reference.py --scenario data/scenarios/city_blackout_001/v0.1.json   # 一座停電的城市
python3 scripts/run_city.py                                                # output/city/：governance score、連鎖、補給延遲
python3 scripts/run_airspace.py                                            # output/airspace/：偵測缺口、反應、漏過原因、規則與雷達配置比較
python3 scripts/run_virtual_test.py                                        # output/virtual_test/：四份裝備的三重篩查與判斷
python3 scripts/run_products.py --edition commercial                       # output/products/：商業版六個產品的 KPI 與結論
python3 scripts/serve_world.py --edition commercial                        # 商業版的 world service
docker compose up --build                                                  # API + worker + Redis + PostgreSQL
```

用另一個 profile 評同一場：

```bash
python3 scripts/run_tactical_reference.py --profile data/evaluation_profiles/tactical.json
# Verdict: pass (score 0.78, profile tactical)
```

想快速知道發生了什麼，先看 `output/timeline.txt`：

```text
Tick 6

- Red Rifleman selected ATTACK against Blue Commander
- Red Rifleman successfully attacked Blue Commander: HP 7 -> 0 (damage = 10)
- Blue Commander in the BLUE faction was destroyed by Red Rifleman
```

跑測試：

```bash
python3 -m pytest tests/ -q
```

---

## 產出什麼

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
| `external/<system>.json` | （run_external）九個系統各自拿回什麼；`conflict_*.json`：一個衝突的 package、handoff 與決定 |

timeline 到 causal_chain 四個與評估四個，都是從 result package 推導出來的，刪掉重跑會一樣。

---

## 文件

| 你想知道 | 去哪 |
|---|---|
| 系統怎麼運作、模組怎麼分工 | [`docs/architecture.md`](docs/architecture.md) |
| 我要接手這個專案 | [`docs/handoff.md`](docs/handoff.md) |
| 完整技術參考（1510 行） | [`docs/phases/phase4_tactical_slice.md`](docs/phases/phase4_tactical_slice.md) |
| 某個階段做了什麼 | [`docs/phases/`](docs/phases/) |
| 資料格式長什麼樣 | [`docs/spec/contracts.md`](docs/spec/contracts.md) |
| 每個 Phase 要做什麼、照什麼順序 | [`docs/plan/`](docs/plan/) |
| 為什麼這樣設計 | [`docs/decisions/`](docs/decisions/) |
| 上個階段的回顧 | [`docs/postmortems/`](docs/postmortems/) |

各階段的任務規格與驗收標準寫在 [GitHub Issues](https://github.com/XRainimatorX/SKYVAULT/issues)。

---

## Repo 結構

```text
src/skyvault/       引擎與 exporter
  contracts/        26 份資料契約（Pydantic，schema 0.6）
  runtime/          世界的積木：空間、時間、實體登記、資源、規則、快照、event sourcing
  actions/          action 的驗證、結算與套用；十種 action type
  evaluation/       多軸評估、防刷分、trade-off report
  reproducibility/  hash、版本、scenario 比較、run registry
  failure/          failure variables、壓力測試、failure map
  batch/            批量、平行、參數掃描、衝突分支、conflict package
  views/            每個畫面的內容，從輸出檔推導
  report/           briefing（Markdown / Word / PDF）
  service/          網頁介面的後端（FastAPI、replay WebSocket）
  policies.py       policy registry：外部 policy 從這裡接入
  domains/military/ 第一個 domain pack（不是 core）
  domains/city/     第二個 domain pack：道路網上的城市、治安、電力連鎖、補給、governance score
  domains/airspace/ 第三個 domain pack：空域、機率偵測、航跡、攔截、HADES / SKYFOX / AEROGRID
  virtualtest/      裝備的三重篩查：physics-lite、工程、戰術、壓力、solver、surrogate、外部仿真、判斷
  editions/         一顆核心兩個版本：manifest、redact、edition 服務、六個產品、反哺
  training/         訓練資料：transition、anti-gaming 標籤與過濾、分支評估、registry、RAG index
  observation/      觀測層：observer profile、fog of war、confidence、delay、stale、五種 view
  actors/           誰決定：唯讀世界、十種 actor 與 adapter、ActionQueue、participants
  worldservice/     後台服務：governance、store、queue、jobs、persistent world、HTTP API
  interface/        外部系統：九個 adapter、conflict 的分支與決定、authority handoff、外部 API
ui/                 網頁介面（Next.js、ECharts）
  schemas/          由契約產生的 JSON Schema
scripts/            執行入口
data/scenarios/     scenario 輸入，每個 scenario 一個資料夾、每個版本一個檔
data/evaluation_profiles/   評估 profile（balanced、tactical）
data/batches/       batch 請求
data/domains/       domain pack 的 profile、rules 與 scenario spec（military、city、airspace）
data/virtualtest/   virtual test 的規則與四份裝備 profile
data/editions/      版本（internal、commercial）與產品目錄
data/training/      訓練資料要匯出哪些 run
data/observers/     五個系統的 observer profile
data/service/       world service 的 governance 政策
examples/           外部 policy 範例（TAC ANGEL 的介面）
tests/              測試
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
| 權威名單不能由政策擴充 | 固定 NEXUS、SOVEREIGN（authorities 是參數） | Phase 19 |
| CYBERHOUND、EIDEN 的世界參數 | 回報為缺口，不模擬（AEROGRID 的空域、星衞的裝備參數已有模型） | 需要時 |
| 商業版的 redact 是字串層級 | 新增內部名稱要加進 data/editions/commercial.json；CI 掃描外洩 | 需要時 |
| 裝備篩查的係數是假設 | physics-lite 門檻、一個軍事 tick = 10 分鐘、hp 係數代表防護；FMI / FMU 尚未接上 | 有真實資料時 |
| 城市的係數是手調的 | 依 20 個 seed 的測量訂定，不是校準過的真實城市；沒有 GIS | 有真實資料時 |
| 空域只有 2D、兩種高度，威脅只會直線飛 | 沒有閃避、改目標；HADES 不能指定攔截器、AEROGRID 不能新增感測器 | 計劃寫 3D later |
| briefing 不敘述城市的狀態變化 | 「What happened」只數行動；NEXUS 拿 domain_outcome，人讀 output/city/city_report.md | 需要時 |
| 沒有算力預算、排隊、自動停止 | 只有 workers 上限；分支數隨衝突數指數成長 | §15 |
| 軍事 baseline policy 用自己的感測 | 每個單位自己看；觀測層是整個陣營共享；沒有視線 | Phase 6 |
| 軍事任務不在 core 的評估與 batch 指標裡 | doctrine 比較的 batch 比勝率與失敗頻率，任務達成率另由 mission_outcome 判定 | 未定 |
| 訓練資料的 observation 不是觀測層產生 | 軍事用 pack 的感測，其他是整個世界的狀態 | Phase 6 / 12 |
| 觀測只支援 grid | 與 tactical engine 相同 | 對應的 engine 出現時 |
| 讀世界的 policy 慢約 18%（軍事） | 唯讀代理的成本 | 有需要時 |
| persistent world 不能跨程序恢復 | engine 不能序列化；checkpoint 與結果留在 store | 需要時 |
| batch 內的每個 run 不受 auto-stop | 受 max_batch_count 與 scenario 時限約束 | 需要時 |
| Docker 只做靜態驗證 | 此環境沒有 daemon；CI 跑 `docker compose config` | — |
| adapter 用內建替身 | 真正的 TAC ANGEL 等以 callable 或 HTTP 提交接入；沒有 LLM SDK、沒有真正的外部系統連線 | — |
| 介面只讀一個 workspace | 看另一個 run 要重跑腳本或換資料夾重啟；不能編輯 scenario | Phase 11 |
| run registry 是本機 JSON Lines 檔 | 不跨機器共享；`runs/` 不進版本控制 | 需要共享時 |
| tactical reference 只跑 grid + tick | 其他空間與時間要直接用 `create_world()` 建；action framework 已支援圖上的 action，但還沒有 policy 會在圖上決策 | domain pack（Phase 13 起） |
| `expected_duration` 只是宣告 | action 都在一步內完成；沒有持續多個 tick 的 action | 需要排程的 Phase |
| `state_changes`（環境變動）一律 raise | WorldState 沒有建模 environment_state | 需要它的 domain |
| risk_growth、stability_impact 是代理指標 | 沒有風險與穩定模型；用 affects_risk 事件與摧毀比例代替 | Phase 9 起 |
| Spec §8.3 的六個軸不評（physical_possibility 等） | 模擬中沒有資料來源 | 需要它們的 domain |
| consequence 的 evaluation_impact 不進評估 | consequence 不在 result package 裡，評估只讀紀錄 | 未定 |
| 單一 run 的 comparison 恆為空 | 單一 run 沒有比較對象；batch 的 branch_comparison 依平均分數填 | — |
| 快照只存在記憶體 | 程序結束就沒了；可由 event memory 重建 | 文件寫明 SQLite / PostgreSQL later |

完整清單見 [`docs/phases/phase19_editions.md`](docs/phases/phase19_editions.md)。

---

## 開發

```bash
python3 -m pytest tests/ -q --cov                # 測試與覆蓋率
ruff check .                                      # linter
black --check src/ tests/ scripts/                # 排版
python3 -m mypy src/                              # 型別
python3 scripts/export_schemas.py                 # 改契約後重新產生 JSON Schema
python3 -m bandit -c pyproject.toml -r src/       # 安全掃描
```

所有設定集中在 `pyproject.toml`。

每次 push 與 PR 由 [`.github/workflows/ci.yml`](.github/workflows/ci.yml) 在乾淨環境（Python 3.10 與 3.11）跑上面全部檢查，外加：換工作目錄跑測試、檢查測試沒有讀 `output/`、JSON Schema 與契約一致、從空的 `output/` 跑完整 pipeline 並讀內容驗證（含由 event memory 重建終局世界）；另一個 job 建 UI、啟動 server，用 Chromium 打開每個頁面驗證。

送 PR 前的檢查清單見 [`docs/handoff.md`](docs/handoff.md)。
