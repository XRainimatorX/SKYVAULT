# 接手指南

給下一個接手 SKYVAULT 的人。假設你沒參與過先前任何階段。

先讀 [`architecture.md`](architecture.md) 了解系統怎麼運作 —— 這份文件只講「接手時要注意什麼」。

---

## 1. 三十分鐘上手

```bash
git clone https://github.com/XRainimatorX/SKYVAULT.git
cd SKYVAULT
python3 -m pip install pydantic pyyaml networkx pandas fastapi uvicorn websockets python-docx reportlab pyarrow pytest httpx pypdf
python3 scripts/run_tactical_reference.py
python3 -m pytest tests/ -q
```

應該看到：

```text
Result: RED_survived
Events: 97
Verdict: risky (score 0.50, profile balanced)
Run: run_<時間>_<input 前 8 碼> (output 63090026e137)
793 passed
```

**如果數字不一樣，先停下來查清楚再繼續。** 這個 scenario 用固定 seed，結果應該永遠相同。不一樣代表有東西被改動了。output_hash 的前 12 碼（`63090026e137`）也應該一樣 —— Phase 8 起連 event id 都是決定性的；不一樣就跑 `python3 scripts/verify_run.py output/result_package.json` 看是輸入變了還是行為變了。

接著打開 `output/timeline.txt` 從頭讀到尾。三分鐘就能理解這個引擎在做什麼 —— 這比讀程式碼快。

---

## 2. 動手前必須知道的五條規則

這四條違反了不會立刻報錯，會在整合階段才爆。Phase 4 就是這樣浪費掉一輪。

### 規則 1：`event_memory` 是唯一真相來源

其他所有輸出都由它推導。任何模組都不得修改它。

如果你要新增一種輸出，它的輸入應該是 `result_package` 的欄位，**不是 scenario 檔，也不是別的輸出檔**。

### 規則 2：exporter 是純函式

```python
def build_something(data) -> data:
    ...
    return result
```

不開檔、不寫檔、module 層級不執行任何東西。

自我檢查：

```bash
python3 -c "import skyvault.your_module"
```

如果 `output/` 冒出檔案，你的模組在做不該做的事。

### 規則 3：寫檔只在 runner

`scripts/run_tactical_reference.py` 只做 `import exporter → call exporter → write file`。

模組決定「內容是什麼」，runner 決定「寫去哪」。

### 規則 4：禁止向上 import

依賴階層見 [`architecture.md`](architecture.md) 第 2 節。

最常犯的：在 `world_state.py` 裡 import policy，或在 exporter 裡 import 任何專案模組。`runtime/` 也不得 import engine、policy、exporter，`tests/runtime/test_event_sourcing.py` 逐檔檢查。

### 規則 5：改世界只有一條路

actor 的 action 一律交給 `ActionResolver.execute()`。新增一種 action 就寫一個 handler：`validate()` 與 `resolve()` **只讀**世界，把改變寫成 `DirectEffect` 放進 Consequence，由 `apply_consequence()` 套用。handler 裡任何 `.state[...] =`、`.position =`、`record_event()` 都會被 AST 測試擋下。

不屬於任何 action 的改變（腳本事件、測試）用 `world.mutate_entity()`、`world.update_entity_state()` 或 `world.change_resource()` —— 它們都會記 event。

**`rebuild_world(initial_world_state, event_memory) == final_world_state` 是不變量**，CI 每次都驗。偷偷改世界不記 event，重建就對不上。

---

## 3. 測試要測函式，不要測檔案

這是 Phase 4 最貴的一課。

```python
# 錯：測的是磁碟上剛好放著什麼
def test_something():
    with open("output/replay_state_at_tick.json") as f:
        replay = json.load(f)
    assert "states" in replay

# 對：測的是你的程式
def test_something():
    replay = build_replay_state_at_tick(initial, events, final)
    assert "states" in replay
```

讀檔的測試在殘留檔存在時會**假通過**，在檔案被覆寫時會**假失敗**，兩種情況下受測程式都沒被執行。

自我檢查：

```bash
grep -rn "open(" tests/
```

任何一筆指向 `output/` 都要改。

---

## 4. 現有測試的盲點

Phase 4 的測試**只檢查結構，不檢查數值**，所以 `timeline.txt` 的致命一擊傷害數字錯了三處，34 個測試全綠。

Phase 1 補了數值測試，過程中又發現一個更隱蔽的盲點：

```python
# 不夠：另一筆傷害值相同的攻擊也會讓它成立
assert f"(damage = {damage})" in text

# 要這樣：整句精確比對，別的行不可能剛好吻合
assert f"HP {hp_before} -> {shown_after} (damage = {damage})" in text
```

第一種寫法在缺陷存在時**仍然會過** —— Phase 4 回顧裡建議的測試就是這種寫法。Phase 1 把缺陷放回去實際跑過才發現。

**寫完一個要抓缺陷的測試，把缺陷放回去跑一次，確認它真的會紅。** 沒做這一步，就不知道它是「有效的測試」還是「會過的測試」。

其餘三個 exporter 的測試仍以結構為主；Phase 1 的契約測試補上了形狀的部分。Phase 2 的 `rebuild_world()` 測試則逐 tick 對照 replay exporter 的 entity 狀態，等於替 replay 補上了數值對照。

Phase 3 又發現 Phase 2 留下兩個全綠的缺陷：節點位置被 `Event.to_dict()` 拆成字元（測試用的是手寫 dict），tick 0 的事件不被重放（測試資料從 tick 1 開始）。**新能力要用觸發它的資料、走過真正產生資料的程式碼來測。**

Phase 2 也發現：**守護不變量的測試也要反向驗證。** 分層測試第一版看不到 `from .. import engine`，放回去跑才發現。變異存活時先判斷是不是等價變異 —— 判斷方法是**找一個讓兩者結果不同的輸入**，找得到就是測試缺口；找不到且說得出原因，才是等價、該刪程式碼。Phase 2 曾把「現有測試分不出來」當成等價，結果是一個 Phase 3 才發現的缺陷。

Phase 7 再發現：**設定值也會沉默。** profile 的 hidden_risk 門檻原本是 0.5，契約通過、手調門檻的測試也會觸發，但 reference scenario 的 300 個 seed 裡沒有一場會讓它觸發。每個門檻都要有一場真實的 run 證明它會觸發。反向驗證的變異也要確認真的被執行 —— 插在 docstring 裡的 import 不是 import。

Phase 8 再發現：**指紋要在資料交出去的那一刻算，驗證要用獨立的證據。** output_hash 一度取自驗證前的 dict，兩次 run 仍然相同（同樣地錯），只有「從呼叫端拿到的 package 重算」的測試抓得到。

Phase 9 再發現：**規則的測試資料要能區分有無這條規則。** crushing 同分規則的測試用了兩個名稱順序剛好等於崩潰順序的變量，拿掉規則照樣綠。寫測試前先問：拿掉這條規則，結果會不同嗎？

Phase 10 再發現：**同一個 process 內的重跑證明不了可重現。** failure map 的同分 cause 從 set 計數，順序跟著字串雜湊走，每個 process 不同；所有測試都在同一個 process 裡比較，所以看不到。新增或改動輸出檔時，用兩個不同的 `PYTHONHASHSEED` 各跑一次，比較位元組。

Phase 17 再發現：**本機能跑不等於宣告的相依能跑。** websockets 是開設測量時手動裝的，沒有宣告，CI 的 replay 就連不上；本機只有 3.11，3.10 上 `asyncio.TimeoutError` 不是 `TimeoutError` 的問題只在 CI 出現。測量工具用 scratch venv；推送前用 uv 的 3.10 venv 跑一次完整測試。

Phase 13 再發現：**只被一種輸入測過的輸出，只證明了那一種輸入。** briefing 在 reference run 上完美，第一次跑軍事 run 就念出「1 entity_state_changed」。新增 scenario 來源或 domain 時，把 timeline、views、briefing 在它上面跑一次並讀過。另外：反向驗證的 pattern 對不上時（black 重排過），腳本必須報錯而不是照跑沒變異的程式。

Phase 18 再發現：**過濾器正確不代表過濾的結果正確。** 軍事 run 100% 被判刷分，原因是 Phase 13 的 handler 把每一發都標成風險；filter 的邏輯完全對。寫任何「分類」之前，先量真實資料的分布，任何 0% 或 100% 都要問為什麼。

Phase 5 再發現：**跑得完不等於用得對。** TAC ANGEL 範例把 known_risks 的 in_range（敵人打得到我）當成「我打得到敵人」，在每個 scenario 都跑得完、測試全綠。新介面的第一個使用者要逐欄讀過：它讀的每個欄位是什麼意思、它拿來做什麼。另外：policy registry 是 process 層級的狀態，同一個 .py 檔載入兩次會撞名 —— 單一測試檔綠、全套紅；推送前一定跑全套。

**reference run 被釘住了。** `tests/fixtures/reference_trace.json` 記錄 97 筆 event 的 (time, type, actor, target, data) 與整包去 uuid 後的雜湊。模擬行為有任何變化，`test_reference_run_matches_the_committed_trace` 就紅。刻意改變時用 `python3 tests/reference_trace.py > tests/fixtures/reference_trace.json` 重新產生，並在完成報告記錄新舊數字。

---

## 5. 地雷區

| 位置 | 注意什麼 |
|---|---|
| `engine.py` 的 `self.rng` | 整場模擬唯一的隨機來源，交給 policy 共用。多建一個 `Random()` 會破壞決定論 |
| `Entity.position` | 型別是 `Location \| None`：grid 上是 `(x, y)`，graph / network 上是節點 id 字串。算距離前先確認不是 None；需要拆 `x, y` 的地方先確認不是字串 |
| `EntityRegistry.get()` | Mapping 原生語意，找不到回傳 None。要 raise 用 `require()` 或 `world.get_entity()` |
| `ResourceState.change()` | 扣到負數 raise，不夾 0。行動前自己檢查夠不夠 |
| `PhaseClock` | 每次 `advance()` 前進一整個 `phase_length`，不是 1 |
| `Action.target` | Phase 3 起是 `ActionTarget(entity_id, location, system_id)`，沒有 `target_entity_id` / `target_position` 屬性了 |
| handler | 只讀。要改世界就回傳 `DirectEffect`；連 `target.state.update(...)` 都會被 AST 測試擋 |
| 致命一擊 | 是 ATTACK effect 加一個 ENTITY_DESTROYED chain reaction，兩筆 event 的 before / after 相同 |
| `rule_set.action_costs` | 有定義的 action type 以它收費，actor 的 `required_resources` 被忽略；supply 運送的就是收的費 |
| failure variable | 是 scenario 轉換，不碰執行中的世界。新增一個要同時加進 `failure/variables.py`、`contracts/failure.py` 的名稱清單與 `failure/analysis.py` 的 RECOMMENDATIONS（有測試比對） |
| `rule_set.faults` | 只有 failure exploration 會設。它用 `ActionContext.fault_rng`，不碰主 rng；沒有 faults 時 fault_rng 一次都不抽 |
| 驗證過的設定少了欄位 | `check()` 只回傳提供的欄位，預設值不會被填。讀設定的地方要自己補（`failure/explore.py` 的 `_with_defaults`） |
| sensitivity 為負 | 不是 bug：壓力讓方案更常存活（例如壞天氣保護守方） |
| `runtime.scheduled_actions` | 該 tick 該 actor 的命令取代 policy；action id 仍由 `world.ids` 產生。只有 batch 的衝突分支會設 |
| 輸出清單的排序 | 來源是 set / Counter / dict 時，排序鍵要明確（次數遞減、再依名稱）。依賴 set 的迭代順序 = 不同 process 寫出不同的檔 |
| batch 的平行 | `pool.map` 保持輸入順序，所以平行 = 循序；唯一不同的是 batch_result 的 `workers` 欄位本身 |
| conflict package | 永不選邊。`decision_reason` 只列每個指標誰領先；改它時不要加「建議採用」 |
| `tests/conftest.py` 的 workspace | reference workspace（1 + 760 + 900 次模擬）每個 session 產生一次，約 20 秒。測試不讀 `output/`；要 workspace 就用 `reference_workspace` / `run_only_workspace` fixture |
| briefing 的可重現 | PDF 用 invariant 模式；DOCX 的日期與 zip 內時間固定為 run 的 ended_at。加新內容時不要放當下時間 |
| `asyncio.wait_for` 逾時 | 要接 `asyncio.TimeoutError`；在 3.10 上它不是內建 `TimeoutError`（ruff 會建議改，不要改） |
| uvicorn 與 WebSocket | uvicorn 本身不支援 WebSocket，靠 `websockets`（已宣告）。少了它 replay 會連不上，server 只印一行警告 |
| `ui/` | 改頁面後 `npm run build`；`npm run e2e` 需要 server 在跑（`SKYVAULT_URL`）。playwright 釘在 1.63.0 |
| `scenario.domain` | `"military"` 才載入 pack；null 時 engine 完全照舊。新增 domain 要在 `domains/__init__.py` 的 KNOWN_DOMAINS 登記名稱 → `module:attr` |
| policy 的選擇順序 | `engine(policy=…)` → `runtime.policy.name`（已註冊）→ domain 的預設 → tactical reference。policy 有 `system_id` 屬性就會記在 event 上 |
| 軍事 scenario 是產生的 | 改 `data/domains/military/` 的 profile 或 spec 後跑 `scripts/build_military_scenarios.py`；漂移測試會在不一致時失敗 |
| 軍事 pack 的 handler | 與 core handler 同樣只讀世界（同一個 AST 檢查）；ATTACK / MISS 的 data 鍵與 core 相同，exporter 才能照讀 |
| 指揮延遲 | 延遲的命令在抵達時才驗證，所以「Move target occupied」的 ACTION_REJECTED 是正常的摩擦 |
| `tac_angel_dataset.jsonl` | 不進版本控制（2.8 MB）；episode 以 input / output hash 命名，可重現 |
| `training/` 的集合 | rejected（有違規）永不進 clean；clean 包含沒有刷分的真失敗，以 success_type 區分 |
| reference run 是假成功 | RED 存活但穩定性被 flagged → success_type false_success、進 rejected。這是正確的 |
| pack 改寫 core handler | evaluation_relevance 要與 core 一致（只有擊毀算 risk），否則評估與訓練資料都會偏 |
| 訓練資料 | `output/training/` 不進版本控制；由 `data/training/sources.json` 重產，跨 PYTHONHASHSEED 相同 |
| reference scenario 的位置 | Phase 8 起在 `data/scenarios/tactical_reference_001/v0.1.json`（版本資料夾），不是 `data/scenarios/tactical_reference_001.json` |
| event / action id | 每個 world 自己的計數器（`event_0000000001`）。policy 要從 `world.ids.action()` 取 id；不要再用 uuid（有測試擋） |
| output_hash | 在**驗證過的** package 上算。驗證會把 int 正規化成 float；在驗證前算的 hash 對不上呼叫端拿到的 package |
| verify_reproducibility | 比三個值：從 package 重算的、記錄的、重跑的。只比後兩者會放過被改過的 package |
| `runs/registry.jsonl` | runner 每跑一次追加一行；已 gitignore。測試一律用 tmp_path |
| `skyvault.__version__` | 每個 Phase 調升 minor，pyproject 同步；它就是 reproducibility 的 runtime_version |
| evaluation/ | 與 exporter 同級：只吃 plain dict，不 import 專案模組。評估只能看見 event memory 記下的東西 |
| SCENARIO_END.data vs evaluation_result | SCENARIO_END 存的是勝負摘要；package 的 evaluation_result 是摘要 + 多軸判斷，key_findings 多三條 |
| evaluation profile | 不給就是 balanced；perspective 為 null 時取 scenario.evaluation.perspective，再沒有就取第一個 entity 的陣營 |
| profile 的 `pass` | Python 關鍵字，model 用 alias；`check()` 依 alias 輸出，所以驗證後仍是 `pass` |
| 新增評估軸 | 要同時加進 `evaluation/metrics.py` 的 registry 與 `contracts/evaluation_profile.py` 的 METRIC_NAMES（有測試比對兩者） |
| `git stash` 切版本比對 | 同大小、同一秒改寫的檔案會讓 Python 沿用舊 `.pyc`。切換後先 `find . -name __pycache__ -prune -exec rm -rf {} +` |
| tactical engine | 只接受 grid + tick；其他世界在 `build_world()` 就 raise。要跑別的世界用 `create_world()` |
| `runtime/__init__.py` | 不匯出 `create_world`（會循環 import），從 `skyvault.runtime.world` 取 |
| scenario 的 `schema_version` | 必須是 `"0.2"`。0.1 檔案被拒，遷移方式見 `spec/contracts.md` 第 3 節 |
| `snapshot()` | 回傳深拷貝。改成淺拷貝會讓已記錄的事件被後續變動污染，回放就失效了 |
| `evaluation_result.event_count` | 在 `SCENARIO_END` 寫入前計算，所以由 `run()` 明確傳入 `len(...) + 1`；result package 契約會檢查它等於 `len(event_memory)` |
| `Event` 的屬性 vs `to_dict()` | 屬性是攤平的，輸出是巢狀的。engine 用屬性；exporter 與測試讀的是巢狀輸出 |
| 新的事件型別 | 要先登記到 `contracts/event.py` 的 `EVENT_TYPES`，否則 `record_event()` 直接 raise |
| PATH 上的 `mypy` | 可能是隔離環境裝的，看不到 pydantic。一律用 `python3 -m mypy src/` |
| 契約的 docstring | 會被寫進 JSON Schema 的 `description`。改了要重跑 `scripts/export_schemas.py`，否則漂移測試失敗 |
| `tests/` 與 `scripts/` 的 `sys.path` 區塊 | 這是刻意的，`pyproject.toml` 已為它豁免 E402。根治方式是讓套件可安裝 |

---

## 6. 送 PR 前

```bash
python3 -c "import skyvault.your_module"          # output/ 有東西冒出來就是有副作用
grep -rn "open(" tests/                            # 指向 output/ 的都要改
python3 scripts/run_tactical_reference.py          # 然後真的打開產生的檔案讀一次
python3 -m pytest tests/ -q
ruff check . && black --check src/ tests/ scripts/
python3 -m mypy src/
python3 scripts/export_schemas.py && git status src/skyvault/schemas/   # 改過契約就要有變動
cd /tmp && python3 -m pytest ~/SKYVAULT/tests -q   # 換個目錄再跑一次
git diff                                           # 註解掉的除錯碼、死變數，推之前刪掉
```

第三行是重點：**「檔案存在」和「檔案內容正確」是兩回事。**

這些檢查 CI 也會在乾淨環境再跑一次（[`.github/workflows/ci.yml`](../.github/workflows/ci.yml)）。**「測試過不過」以 CI 為準**，本機結果只是參考 —— 本機可能留著舊的 `output/`，也可能裝著另一個環境的工具。

---

## 7. 這個專案怎麼運作

工作以 **phase** 為單位，順序照 [`plan/README.md`](plan/README.md) 的重排序版本，不照編號。

每個 phase 開設時：

```text
1. 規格已在 docs/plan/phase<N>_<name>.md
2. 建 milestone：Phase <N> — <名稱>
3. 開 issue，固定十二節，第 11 節 Final Done Criteria 是驗收的唯一依據
4. 先 commit fixture，再寫程式
```

**單一工作者時，一個 phase 只開一份 issue**，Frozen Shape / Frozen Interface 寫在它的第 6 節，不拆 section、不另開共同基準 issue。範例：[#17](https://github.com/XRainimatorX/SKYVAULT/issues/17)（Phase 1，19 條）、[#19](https://github.com/XRainimatorX/SKYVAULT/issues/19)（Phase 2，17 條）、[#20](https://github.com/XRainimatorX/SKYVAULT/issues/20)（Phase 3，18 條）、[#21](https://github.com/XRainimatorX/SKYVAULT/issues/21)（Phase 7，19 條）、[#22](https://github.com/XRainimatorX/SKYVAULT/issues/22)（Phase 8，18 條）、[#23](https://github.com/XRainimatorX/SKYVAULT/issues/23)（Phase 9，17 條）、[#24](https://github.com/XRainimatorX/SKYVAULT/issues/24)（Phase 10，18 條）、[#25](https://github.com/XRainimatorX/SKYVAULT/issues/25)（Phase 17，17 條）、[#26](https://github.com/XRainimatorX/SKYVAULT/issues/26)（Phase 13，18 條）、[#27](https://github.com/XRainimatorX/SKYVAULT/issues/27)（Phase 18，18 條）、[#28](https://github.com/XRainimatorX/SKYVAULT/issues/28)（Phase 5，16 條）。

設計依賴現有系統的行為時，**開設前先量**，把數字寫進 issue 第 1 節（Phase 9 回顧改法 4）。

第 6 節開頭先列規格矛盾與決定（Phase 1 回顧改法 3）；Frozen Interface 的每個函式附一行行為，不只寫簽名（Phase 2 回顧改法 2）。每個步驟 commit 前，對照第 6 節檢查這一步新增的公開函式 —— **簽名與語意分開對照**（Phase 3 回顧改法 3）。拆步驟時寫下每一步結束時哪些測試是綠的；寫不出來就和下一步合併（Phase 3 回顧改法 4）。

**多人平行開發時**，每個 section 一份 issue，另開一份共同基準 issue，**同時凍結資料形狀與函式簽名** —— Phase 4 的 [#9](https://github.com/XRainimatorX/SKYVAULT/issues/9) 只凍了資料形狀，結果三組的介面對不上。範例：[#7](https://github.com/XRainimatorX/SKYVAULT/issues/7)、[#8](https://github.com/XRainimatorX/SKYVAULT/issues/8)。

---

## 8. 文件放哪

判準只有一條：**這份文件會不會因為程式碼改動而過期？**

```text
會過期   →  放 repo，跟程式碼一起改、一起 review
不會過期 →  放哪都行
```

目前的配置：

```text
README.md              路標，不放技術細節
docs/architecture.md   系統怎麼運作（會隨程式碼改）
docs/handoff.md        這份
docs/phases/           各階段的凍結紀錄（寫完就不改）
                       phase4_tactical_slice.md 是 Phase 4 結束時的
                       完整技術文件，1510 行，未刪節
docs/plan/             每個 phase 的原文規格（抽自上傳的規劃文件，寫完就不改）
docs/spec/             契約的現行規格（會隨程式碼改）
docs/decisions/        ADR，寫完就不改
docs/postmortems/      回顧，寫完就不改
GitHub Issues          任務規格與驗收
GitHub Wiki            Phase 0 原稿的存檔，不再更新
```

**wiki 不要拿來放技術文件。** 它是獨立的 git repo，不會出現在任何 PR diff 裡，所以沒有任何機制能逼人更新它 —— 它現在停留在 Phase 0，就是這個原因。

---

## 9. 下一步

依 roadmap，下一個是 **Phase 6 — Actor Policy / External Agent Layer**：把「誰來決定行動」完全拆出 core —— SKYVAULT 只決定能不能做、做了會怎樣、怎麼記錄、怎麼評估；各種 actor（規則、腳本、人、外部系統、TAC ANGEL / STARTX / HADES / AEROGRID / SKYFOX adapter）只透過 Action 提交意圖。規格見 [`plan/phase6_actor_agent_layer.md`](plan/phase6_actor_agent_layer.md)。

前面的 Phase 留下與它直接相關的東西：

```text
ObservingPolicy（Phase 5）     外部 policy 已能只拿 observation 決定；agent 的協定可以建在它上面
軍事 baseline 的感測            每個單位自己看；觀測層是整個陣營共享 —— 要不要統一、是否讓 profile 指定（Phase 5 回顧第 7 節）
訓練資料的 observation          full_state / military_sensor，之後改由觀測層產生
scheduled_actions（Phase 10）  外部系統的命令；agent 的決定可能走同一條路
```

開工前先讀 [`phases/phase5_observation_contract.md`](phases/phase5_observation_contract.md) 的第 4 節與 [`postmortems/phase5.md`](postmortems/phase5.md)。
