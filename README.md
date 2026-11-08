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

每個系統看到自己的世界（Phase 5）：observer profile 決定 TAC ANGEL 看一個單位周圍、STARTX 看趨勢、NEXUS 看任務、HADES 看威脅、AEROGRID 看覆蓋；看不到的敵人不出現，看得到的帶 confidence，過期的接觸標明幾 tick 前、延遲的系統看到較早的 tick。外部 policy 可以只拿 observation 決定 —— engine 根本不給它 world。

誰來決定被拆出 core（Phase 6）：每個單位可以由不同的 participant 決定 —— 規則、腳本、人、外部系統、LLM 輔助，或 TAC ANGEL / STARTX / HADES / AEROGRID / SKYFOX 的 adapter —— 它們只能交出 Action 意圖。讀世界的 policy 拿到唯讀的世界，任何寫入當場被擋下；tactical reference policy 可以被拔掉。

SKYVAULT 可以當後台服務跑（Phase 11）：任務從 HTTP API 進來、排隊（優先序、上限）、在 worker 上跑（同一個程序，或 RQ + Redis 的 worker），結果存在 SQLite 或 PostgreSQL，可查、可下載、可重播；persistent world 可以一次推進幾個 tick。每個 run 都受 Resource & Compute Governance 約束：失控的 run 被自動停下並交出 partial result，過大的 batch 在門口被拒。

模擬結果可以變成訓練資料（Phase 18）：每個決定一筆 transition（state、observation、action、consequence、reward、next_state…），每個 run 標記六種刷分行為；刷分的 run 進 rejected、不進主訓練集，「成功」與「假成功」分開標示；STARTX 拿到分支評估；匯出 JSONL / Parquet，登記在 training data registry，並建 RAG index。

結果不用打開 JSON 就能看懂（Phase 17）：一個網頁介面有總覽、逐 tick 的時間線、地圖 replay、因果鏈、失敗地圖、方案比較與 result package；briefing report 可匯出成 PDF、Word 或 Markdown，同一份結果每次逐位元相同。

每次 run 結束後依 evaluation profile 做多軸評估（`src/skyvault/evaluation/`）：11 軸分數、pass / fail / risky / needs_more_test 的判斷與信心、失敗原因、建議下一步測試，並標記靠不行動、犧牲穩定或忽略風險拿到的高分。

各階段的實際進度與交付紀錄在 [`docs/phases/`](docs/phases/)，開發順序見 roadmap。

---

## 快速開始

```bash
git clone https://github.com/XRainimatorX/SKYVAULT.git
cd SKYVAULT
python3 -m pip install pydantic pyyaml networkx pandas fastapi uvicorn websockets python-docx reportlab pyarrow
python3 scripts/run_tactical_reference.py
```

需要 Python 3.10+。模擬本身的相依有四個：`pydantic`（契約與 JSON Schema）、`PyYAML`（YAML scenario）、`networkx`（graph / network 空間的最短路與衝突分支）、`pandas`（批量彙整）；介面與 briefing 另用 `fastapi`、`uvicorn`、`websockets`、`python-docx`、`reportlab`。全部宣告在 `pyproject.toml`。建 UI 需要 Node 22。

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
  contracts/        21 份資料契約（Pydantic，schema 0.6）
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
  training/         訓練資料：transition、anti-gaming 標籤與過濾、分支評估、registry、RAG index
  observation/      觀測層：observer profile、fog of war、confidence、delay、stale、五種 view
  actors/           誰決定：唯讀世界、十種 actor 與 adapter、ActionQueue、participants
  worldservice/     後台服務：governance、store、queue、jobs、persistent world、HTTP API
ui/                 網頁介面（Next.js、ECharts）
  schemas/          由契約產生的 JSON Schema
scripts/            執行入口
data/scenarios/     scenario 輸入，每個 scenario 一個資料夾、每個版本一個檔
data/evaluation_profiles/   評估 profile（balanced、tactical）
data/batches/       batch 請求
data/domains/       domain pack 的 profile 與 scenario spec
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
| 衝突偵測只看命令本身與開場存量 | 不知道執行到那個 tick 時的世界；對 tick 1 的命令沒有差別 | Phase 12 起 |
| 沒有算力預算、排隊、自動停止 | 只有 workers 上限；分支數隨衝突數指數成長 | §15 |
| 軍事 baseline policy 用自己的感測 | 每個單位自己看；觀測層是整個陣營共享；沒有視線 | Phase 6 |
| 軍事任務不在 core 的評估與 batch 指標裡 | doctrine 比較的 batch 比勝率與失敗頻率，任務達成率另由 mission_outcome 判定 | 未定 |
| 訓練資料的 observation 不是觀測層產生 | 軍事用 pack 的感測，其他是整個世界的狀態 | Phase 6 / 12 |
| 觀測只支援 grid | 與 tactical engine 相同 | 對應的 engine 出現時 |
| 讀世界的 policy 慢約 18%（軍事） | 唯讀代理的成本 | 有需要時 |
| persistent world 不能跨程序恢復 | engine 不能序列化；checkpoint 與結果留在 store | 需要時 |
| batch 內的每個 run 不受 auto-stop | 受 max_batch_count 與 scenario 時限約束 | 需要時 |
| Docker 只做靜態驗證 | 此環境沒有 daemon；CI 跑 `docker compose config` | — |
| adapter 用內建替身 | 真正的 TAC ANGEL 等以 callable 接入；沒有 LLM SDK、沒有網路傳輸 | Phase 12 |
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

完整清單見 [`docs/phases/phase11_background_world_service.md`](docs/phases/phase11_background_world_service.md)。

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
