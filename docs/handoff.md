# 接手指南

給下一個接手 SKYVAULT 的人。假設你沒參與過先前任何階段。

先讀 [`architecture.md`](architecture.md) 了解系統怎麼運作 —— 這份文件只講「接手時要注意什麼」。

---

## 1. 三十分鐘上手

```bash
git clone https://github.com/XRainimatorX/SKYVAULT.git
cd SKYVAULT
python3 scripts/run_tactical_reference.py
python3 -m pytest tests/ -q
```

應該看到：

```text
Result: RED_survived
Events: 97
34 passed
```

**如果數字不一樣，先停下來查清楚再繼續。** 這個 scenario 用固定 seed，結果應該永遠相同。不一樣代表有東西被改動了。

接著打開 `output/timeline.txt` 從頭讀到尾。三分鐘就能理解這個引擎在做什麼 —— 這比讀程式碼快。

---

## 2. 動手前必須知道的四條規則

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

最常犯的：在 `world_state.py` 裡 import policy，或在 exporter 裡 import 任何專案模組。

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

目前 34 個測試**只檢查結構，不檢查數值**。

`tests/test_timeline.py` 確認 `"attacked"` 這類關鍵字有出現，但不比對任何數字與 `event_memory` 的對應欄位。四個 exporter 的測試都是這個模式。

實際後果：`timeline.txt` 的致命一擊傷害數字是錯的，34 個測試全綠也沒抓到。

如果你要加強測試，第一優先是補上「輸出數值必須符合 `event_memory`」這一類斷言。

---

## 5. 地雷區

| 位置 | 注意什麼 |
|---|---|
| `engine.py` 的 `self.rng` | 整場模擬唯一的隨機來源，交給 policy 共用。多建一個 `Random()` 會破壞決定論 |
| `Entity.position` | 型別是 `Position \| None`。任何算距離的地方都要先確認不是 None |
| `snapshot()` | 回傳深拷貝。改成淺拷貝會讓已記錄的事件被後續變動污染，回放就失效了 |
| `evaluation.event_count` | 在 `SCENARIO_END` 寫入前計算，所以由 `run()` 明確傳入 `len(...) + 1` |
| `tests/` 與 `scripts/` 的 `sys.path` 區塊 | 這是刻意的，`pyproject.toml` 已為它豁免 E402。根治方式是讓套件可安裝 |

---

## 6. 送 PR 前

```bash
python3 -c "import skyvault.your_module"          # output/ 有東西冒出來就是有副作用
grep -rn "open(" tests/                            # 指向 output/ 的都要改
python3 scripts/run_tactical_reference.py          # 然後真的打開產生的檔案讀一次
python3 -m pytest tests/ -q
ruff check . && black --check src/ tests/ scripts/
mypy src/
cd /tmp && python3 -m pytest ~/SKYVAULT/tests -q   # 換個目錄再跑一次
git diff                                           # 註解掉的除錯碼、死變數，推之前刪掉
```

第三行是重點：**「檔案存在」和「檔案內容正確」是兩回事。**

---

## 7. 這個專案怎麼運作

工作以 **phase** 為單位，每個 phase 拆成幾個 section，每個 section 一份 GitHub issue。

issue 的格式固定十二節，最重要的是最後的 **Final Done Criteria** —— 編號、可逐條打勾。驗收就是照那張表核對，不另立標準。

參考範例：[#7](https://github.com/XRainimatorX/SKYVAULT/issues/7)（21 條）、[#8](https://github.com/XRainimatorX/SKYVAULT/issues/8)（23 條）、[#9](https://github.com/XRainimatorX/SKYVAULT/issues/9)（共同規則）。

多人平行開發時，先用一份 issue 凍結共用的資料形狀（像 #9 對 event shape 做的那樣），否則整合一定出事。

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
docs/decisions/        ADR，寫完就不改
docs/postmortems/      回顧，寫完就不改
GitHub Issues          任務規格與驗收
GitHub Wiki            Phase 0 原稿的存檔，不再更新
```

**wiki 不要拿來放技術文件。** 它是獨立的 git repo，不會出現在任何 PR diff 裡，所以沒有任何機制能逼人更新它 —— 它現在停留在 Phase 0，就是這個原因。

---

## 9. 下一步

依 roadmap，下一個是 **Phase 1 — Core Contract Pack**：把目前散落在程式碼裡的資料格式正式化成 schema。

Phase 4 留下兩件與它直接相關的事：

- event 目前是攤平的 17 欄，Formal Spec §7.2 要的是巢狀的 `source:` / `affected:` 結構。當初為了不阻擋三個 section 平行開發而維持攤平，決定與理由記在 [`docs/decisions/002_event_shape.md`](decisions/002_event_shape.md)
- `affected_resources` 與 `affected_risks` 兩個欄位存在但恆為空，因為資源與風險模型還不存在

開工前先讀 `docs/phases/phase4_event_memory.md` 的第 5 節與第 6 節 —— 那裡記著上一輪踩過的坑。
