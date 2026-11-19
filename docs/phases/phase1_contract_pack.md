# Phase 1 — Core Contract Pack v0.1

完成報告。這份文件是 Phase 1 結束時的凍結紀錄，寫完不再更新 —— 系統目前的樣子請看 [`../architecture.md`](../architecture.md)，契約的現行規格請看 [`../spec/contracts.md`](../spec/contracts.md)。

**狀態：功能完成，沒有已記錄未修的缺陷。Phase 4 留下的 timeline 傷害數字缺陷已修正。**

---

## 1. 這個階段做什麼

Phase 1 開始前，SKYVAULT 唯一的格式檢查是 scenario 的六個頂層鍵。event 的形狀只寫在 Phase 4 的 issue 裡，沒有任何程式碼強制它 —— 那份形狀還與 Formal Spec 對不上。

目標是把資料格式正式化成契約，讓所有後續程式碼有統一規格。規格依據是 [`../plan/phase1_contract_pack.md`](../plan/phase1_contract_pack.md) 與 [`../plan/formal_spec.md`](../plan/formal_spec.md)。

單一工作者模式：一份 issue、依序三個步驟、各自 commit。

```text
Issue      #17 Phase_1_contract_pack（milestone #2 Phase 1 — Contract Pack）
步驟 A     紀錄類契約 + event 收回巢狀 + 4 個 exporter 遷移
步驟 B     場景類契約 + loader 驗證 + YAML
步驟 C     結果類契約 + evaluation_result 更名 + JSON Schema
```

開設時另外做了兩件事：

```text
docs/plan/     上傳的規劃文件不在 repo、也已不在工作環境的磁碟上。先把開發總計劃
               Phase 0–20 與 Formal Spec 的契約格式寫進 repo，作為之後每個 Phase 的正本
milestone #1   Phase 4 的 milestone「phase 4 completeion」一直沒關，開設時關閉
```

---

## 2. 這次執行發生了什麼

### 模擬行為沒有改變

```text
scenario_id     tactical_reference_001
random_seed     42
Result          RED_survived
Events          97（ACTION_SELECTED 46 / MOVE 26 / ATTACK 14 / MISS 6 /
                    ENTITY_DESTROYED 4 / SCENARIO_END 1）
```

與 Phase 4 完全相同。契約只檢查形狀，不改變任何決策或結算。

### 四個 exporter 的輸出結構也沒變

```text
entity_history   blue_003 有 21 筆紀錄       Phase 4 報告：21
causal_chain     46 條 chain                Phase 4 報告：46
replay           12 個 state（0–10 + final） Phase 4 報告：12
```

遷移只改了它們讀 event 的鍵，產出完全一致 —— 只有 timeline 三個數字變了，那是修正（見第 6 節）。

### 變了的是輸出的形狀

```text
event_memory.json      每個 event 改為巢狀，12 個頂層鍵
result_package.json    evaluation 改名為 evaluation_result
timeline.txt           四次致命一擊顯示引擎實際造成的傷害
```

---

## 3. 核心資料形狀

一個真實的 ATTACK 事件（tick 5，red_002 打 blue_003）：

```json
{
  "event_id": "event_…",
  "time": 5,
  "event_type": "ATTACK",
  "source": {
    "actor_id": "red_002",
    "system_id": "temporary_tactical_reference_policy",
    "action_id": "action_…"
  },
  "target_entity_id": "blue_003",
  "affected": {
    "entities": ["blue_003"],
    "locations": [[3, 5]],
    "resources": [],
    "risks": []
  },
  "before_state": { "…": "blue_003 被擊中前的快照" },
  "after_state":  { "…": "blue_003 被擊中後的快照" },
  "causal_links": { "caused_by": ["event_…"], "caused_events": [] },
  "evaluation_relevance": { "affects_success": true, "affects_cost": true, "affects_risk": false },
  "data": { "damage": 16, "hp_before": 30, "hp_after": 14, "distance": 2 },
  "tags": ["attack", "world_state_mutation", "state_change"]
}
```

| 舊（Phase 4，攤平） | 新（Phase 1，巢狀） |
|---|---|
| `actor_id` | `source.actor_id` |
| `system_id` | `source.system_id` |
| `source_action_id` | `source.action_id` |
| `affected_entities` | `affected.entities` |
| `affected_locations` | `affected.locations` |
| `affected_resources` | `affected.resources` |
| `affected_risks` | `affected.risks` |

決定與理由見 [`../decisions/003_event_nesting.md`](../decisions/003_event_nesting.md)。

---

## 4. 交付了什麼

### 十一份契約

```text
src/skyvault/contracts/
  errors.py          ContractError —— 一次列出全部錯誤，是 ValueError 的子類別
  base.py            ContractModel（extra="forbid"）、check()、SCHEMA_VERSION = "0.1"
  entity.py          EntityRecord
  action.py          ActionRecord                actor_id 必填（驗收 2）
  consequence.py     ConsequenceRecord
  event.py           EventRecord + EVENT_TYPES   before_state / after_state 必填（驗收 3）
  world.py           WorldContract
  scenario.py        Scenario                    scenario_id 必填（驗收 1）
  assumption.py      AssumptionRegistry
  provenance.py      DataProvenance
  evaluation.py      EvaluationResult
  result_package.py  ResultPackage               evaluation_result 必填（驗收 4）
  reproducibility.py ReproducibilityMetadata
  json_schema.py     CONTRACTS、build_json_schemas()
```

每份契約一個純函式 `validate_<x>(data) -> dict`。必填與 optional 的劃分、每個 optional 欄位留待哪個 Phase，見 [`../decisions/004_contract_scope.md`](../decisions/004_contract_scope.md)。

### 四個強制驗證點

```text
scenario_loader.load_scenario()   validate_scenario         world 不會從壞 scenario 建立
engine 結算 action 之前             validate_action           壞 action raise，不會被記錄
world_state.record_event()         validate_event            壞 event 永遠進不了 event_memory
engine.run() 回傳之前              validate_result_package   含 event_count == len(event_memory)
```

### 驗證不改變資料形狀

`validate_<x>()` 只回傳呼叫端給的欄位，不補 optional 欄位的預設值。這一點有測試：每份 fixture 與實際執行的 97 個 event、整包 result_package，都斷言「驗證前後相等」。

### JSON Schema

```text
src/skyvault/schemas/<name>.schema.json    11 份，draft 2020-12，$id 帶版本
scripts/export_schemas.py                  重新產生
```

產生的 schema 直接編碼了四條驗收：`scenario.required` 含 `scenario_id`、`action.required` 含 `actor_id`、`event.required` 含 `before_state` 與 `after_state`、`result_package.required` 含 `evaluation_result`。

### Scenario 支援 YAML、帶 schema_version

`load_scenario()` 依副檔名讀 `.json`、`.yaml`、`.yml`，結果一律通過同一份契約。scenario 加上 `schema_version: "0.1"`，其他版本的檔案直接被拒。

---

## 5. 這一輪發現的問題

這一節是這份報告最有價值的部分 —— 下一個階段不要重蹈。

### Phase 4 回顧建議的測試抓不到它要抓的缺陷

Phase 4 回顧的「改法 3」建議用這個測試抓 timeline 的傷害缺陷，並說它「在現在的程式碼下會失敗」：

```python
assert f"(damage = {event['data']['damage']})" in text
```

**它不會失敗。** 致命一擊顯示錯的 `(damage = 7)` 時，真實值 `(damage = 10)` 這個字串仍然出現在 timeline 的別處 —— 同一個攻擊者其他非致命的攻擊也打 10。子字串比對被另一行滿足了。

Phase 1 是把缺陷放回去實際跑過才發現的。改成整句精確比對後，缺陷存在時確實會紅、修正後確實會綠，兩個方向都驗證過：

```python
assert f"HP {hp_before} -> {shown_after} (damage = {damage})" in text
```

**教訓：寫完要抓缺陷的測試，把缺陷放回去跑一次，確認它真的會紅。** 已寫進 [`../handoff.md`](../handoff.md) 第 4 節。

### PATH 上的 mypy 看不到 pydantic

`mypy src/` 報出五個 `Cannot find implementation or library stub for module named "pydantic"`。原因是 PATH 上的 `mypy` 是 uv 隔離環境裝的，有自己的直譯器。改用 `python3 -m mypy src/` 後零錯誤。所有文件與 CI 都改用這個寫法。

### 改契約的 docstring 會讓 JSON Schema 過期

Pydantic 把 model 的 docstring 寫進 schema 的 `description`。修一行說明文字，漂移測試就紅了。這是預期行為 —— schema 的說明本來就該跟著契約 —— 但不知道的人會以為測試壞了。已寫進 handoff 地雷區。

### Formal Spec 自己有兩處前後不一

```text
assumption_registry   §2.3 是扁平對照，§11.2 是結構化清單
data_provenance       §2.3 是扁平四欄，§11.3 是結構化清單
```

前者兩種形狀並存、各有位置；後者因為沒有既有資料，一律用 §11.3。見 ADR 004 第 4、5 點。

### 凍結文件在凍結當下就已經過時

`phase4_tactical_slice.md` 寫 `build_replay_state_at_tick(scenario, …)` 與 `evaluate(termination_reason)`，實際程式碼是 `(initial_world_state, …)` 與 `(termination_reason, event_count)`。那兩處是 09-04 的修正，舊 README 沒跟著改就被凍結了。

這證明了規則：**程式碼與文件衝突時以 `architecture.md` 為準，凍結文件只當歷史參考。** 凍結文件依規定不修改。

### Phase 4 的三份工作 issue 格式不一致

#5 用 `##` 章節、內文自稱「Section 1」、結語是英文；#7 #8 用 `#` 章節、結語是中文引言區塊。#17 統一採用後者。

### ruff 的豁免規則沒涵蓋子目錄

`"tests/*.py" = ["E402"]` 不匹配新的 `tests/contracts/*.py`。改為 `"tests/**/*.py"`。

---

## 6. Phase 4 缺陷的修正

`src/skyvault/timeline.py`：

```python
# 修正前
if hp_after <= 0:
    hp_after = 0
    damage = hp_before - hp_after     # ← 用夾過的值回推，覆寫真實傷害

# 修正後
if hp_after <= 0:
    hp_after = 0                      # 只為顯示夾住負血；damage 維持引擎實際套用的值
```

| tick | attacker | target | 真實傷害 | Phase 4 顯示 | Phase 1 顯示 |
|---|---|---|---|---|---|
| 6 | red_001 | blue_003 | 10 | 7 ✗ | 10 ✓ |
| 6 | blue_002 | red_003 | 16 | 3 ✗ | 16 ✓ |
| 7 | red_002 | blue_002 | 16 | 16 ✓（巧合） | 16 ✓ |
| 10 | red_002 | blue_001 | 16 | 5 ✗ | 16 ✓ |

`tests/test_timeline.py::test_timeline_damage_matches_event_memory` 逐筆比對 14 次攻擊的整句。

---

## 7. 品質狀態

| 項目 | 結果 |
|---|---|
| pytest | 91 passed（Phase 4 為 34） |
| 全專案覆蓋率 | 96%（893 statements，34 miss；Phase 4 為 93%） |
| `contracts/` 覆蓋率 | 14 個檔案全部 100% |
| ruff | 通過 |
| black | 通過 |
| mypy（`python3 -m mypy src/`） | 通過，29 個檔案 |
| bandit | 0 issues |
| 換工作目錄跑測試 | 91 passed |
| import 副作用 | 0 個檔案 |
| 測試讀 `output/` | 0 處 |

### 測試分布

```text
tests/contracts/test_record_contracts.py      17   驗收 2、3；Entity、Consequence；分層
tests/contracts/test_scenario_contracts.py    23   驗收 1；YAML；schema_version；文法規則
tests/contracts/test_result_contracts.py      16   驗收 4；Reproducibility；JSON Schema 漂移
tests/test_timeline.py                         7   含新增的整句傷害比對
既有其餘 5 個檔案                              28   改讀巢狀鍵，內容不變
```

---

## 8. 已知限制

這些是刻意的取捨，不是錯誤。

| 項目 | 留待 | 原因 |
|---|---|---|
| `event_id` / `action_id` 用 `uuid4()`，不受 seed 控制 | Phase 8 | 行為可重現，輸出檔無法跨 run 逐位元比對；Reproducibility 契約因此無法誠實填值 |
| event 的 `affected.resources` / `affected.risks` 恆為空 | Phase 2 / Phase 7、9 | 資源與風險模型還不存在 |
| World Contract 的 entity_model / environment_state / resource_state / rule_set 只是 optional | Phase 2 | 沒有任何引擎部分使用它們 |
| Evaluation Result 的多軸評估欄位只是 optional | Phase 7 | evaluator 仍只有勝負與計數 |
| Scenario 維持扁平佈局，未採用 Spec §3.3 的分組 | 調升 schema 版本時 | 改佈局不帶來新能力，見 ADR 004 第 3 點 |
| 每個 event 驗證兩次（record_event 與 result package） | Phase 10 | 97 個 event 成本可忽略；批量模擬若成為瓶頸再改 |
| 套件不可安裝，tests / scripts 仍靠 `sys.path` | 未定 | `pyproject.toml` 已有 `[project]`，缺 build-system；改動會影響所有人的執行方式 |

---

## 9. 驗證

```bash
python3 -m pip install pydantic pyyaml pytest pytest-cov ruff black mypy bandit
rm -f output/*.json output/timeline.txt
python3 scripts/run_tactical_reference.py           # RED_survived / 97 events
python3 -m pytest tests/ -q                          # 91 passed
cd /tmp && python3 -m pytest ~/SKYVAULT/tests -q     # 91 passed
ruff check . && black --check src/ tests/ scripts/
python3 -m mypy src/
python3 -m bandit -c pyproject.toml -r src/          # 0 issues
python3 scripts/export_schemas.py && git status src/skyvault/schemas/   # 無變動
```

---

## 10. 一句話總結

> Phase 1 把 SKYVAULT 的資料格式正式化成 11 份有驗證、有 JSON Schema 的契約，並在 scenario 載入、action 結算、event 記錄、result package 輸出四處強制執行 —— event 收回 Spec §7.2 的巢狀形狀、Phase 4 的 timeline 缺陷一併修正，模擬行為一點沒變；Spec 有但系統還沒建模的欄位目前只是 optional，各自留待 Phase 2、3、7、8 落地時改為必填。
