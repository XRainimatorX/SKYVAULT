# 接手指南

給下一個接手 SKYVAULT 的人。假設你沒參與過先前任何階段。

先讀 [`architecture.md`](architecture.md) 了解系統怎麼運作 —— 這份文件只講「接手時要注意什麼」。

---

## 1. 三十分鐘上手

```bash
git clone https://github.com/XRainimatorX/SKYVAULT.git
cd SKYVAULT
python3 -m pip install pydantic pyyaml networkx pytest
python3 scripts/run_tactical_reference.py
python3 -m pytest tests/ -q
```

應該看到：

```text
Result: RED_survived
Events: 97
182 passed
```

**如果數字不一樣，先停下來查清楚再繼續。** 這個 scenario 用固定 seed，結果應該永遠相同。不一樣代表有東西被改動了。

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

### 規則 5：改世界要記 event

改 entity 用 `world.update_entity_state()`，改資源用 `world.change_resource()`，或自己 `record_event()` 並把完整快照放進 `after_state`。

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

Phase 2 又發現：**守護不變量的測試也要反向驗證。** 分層測試第一版看不到 `from .. import engine`，放回去跑才發現。變異存活時先判斷是不是等價變異 —— 是的話該刪的是程式碼，不是補測試。

---

## 5. 地雷區

| 位置 | 注意什麼 |
|---|---|
| `engine.py` 的 `self.rng` | 整場模擬唯一的隨機來源，交給 policy 共用。多建一個 `Random()` 會破壞決定論 |
| `Entity.position` | 型別是 `Location \| None`：grid 上是 `(x, y)`，graph / network 上是節點 id 字串。算距離前先確認不是 None；需要拆 `x, y` 的地方先確認不是字串 |
| `EntityRegistry.get()` | Mapping 原生語意，找不到回傳 None。要 raise 用 `require()` 或 `world.get_entity()` |
| `ResourceState.change()` | 扣到負數 raise，不夾 0。行動前自己檢查夠不夠 |
| `PhaseClock` | 每次 `advance()` 前進一整個 `phase_length`，不是 1 |
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

**單一工作者時，一個 phase 只開一份 issue**，Frozen Shape / Frozen Interface 寫在它的第 6 節，不拆 section、不另開共同基準 issue。範例：[#17](https://github.com/XRainimatorX/SKYVAULT/issues/17)（Phase 1，19 條）、[#19](https://github.com/XRainimatorX/SKYVAULT/issues/19)（Phase 2，17 條）。

第 6 節開頭先列規格矛盾與決定（Phase 1 回顧改法 3）；Frozen Interface 的每個函式附一行行為，不只寫簽名（Phase 2 回顧改法 2）。每個步驟 commit 前，對照第 6 節檢查這一步新增的公開函式。

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

依 roadmap，下一個是 **Phase 3 — Action & Consequence Engine**：一般化的 action 驗證與後果結算，含直接效果、次級效果、連鎖反應。規格見 [`plan/phase3_action_consequence_engine.md`](plan/phase3_action_consequence_engine.md)。

Phase 2 留下與它直接相關的事：

```text
改世界有兩條路徑
    tactical 的 MOVE / ATTACK 直接改 entity；runtime 有 update_entity_state / change_resource
    Phase 3 的框架應該讓所有改動走同一條路
Action 契約的 required_resources 等六欄仍是 optional
    ADR 004 列為 Phase 3；資源帳已經存在，可以開始扣
Consequence 的 secondary_effects / chain_reactions 仍是 optional
    ADR 004 列為 Phase 3
RuleSet 只存參數
    規則本身（什麼 action 合法、造成什麼）是 Phase 3
```

開工前先讀 [`phases/phase2_world_runtime_core.md`](phases/phase2_world_runtime_core.md) 的第 5 節與 [`postmortems/phase2.md`](postmortems/phase2.md)。
