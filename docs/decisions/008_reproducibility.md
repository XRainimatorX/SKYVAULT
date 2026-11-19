# 008 — Reproducibility、版本控制與 schema 0.5

狀態：已採納
日期：2026-11-08
階段：Phase 8 — Reproducibility + Version Control v0.8

## 背景

開發計劃 Phase 8：讓每一次 run 可重跑、可比較、可追蹤。功能清單是 scenario_version、ruleset_version、runtime_version、random_seed、input_hash、output_hash、run_id、run_metadata、deterministic replay；技術欄是 hashlib、metadata registry、versioned scenario folder、run registry、snapshot store。驗收三條：

```text
同一 scenario + 同一 seed + 同一 ruleset 會得到同一結果 / 不同版本 scenario 可比較差異 /
result package 能追蹤來源
```

Phase 8 開始前，行為可重現，但 event_id 與 action_id 是 uuid4：同一輸入跑兩次，輸出檔每一行 id 都不同，Reproducibility 契約（Phase 1 定義）沒有任何 run 能誠實填出 output_hash。

issue #22 第 6 節在寫程式之前列出了十六項決定。這份 ADR 記錄那十六項，以及開發中做的六項。**模擬行為不變**：reference trace 的 97 筆與 digest 都沒變。

## 決定

### 1. id 是每個 run 的計數器

`runtime/ids.py`：`IdSequence(prefix).next()` 產生 `event_0000000001`、`action_0000000001`…。十位數字仍符合 Phase 1 的 `^(event|action)_[0-9a-f]{10}$`，契約與 exporter 都不用改。計數器屬於 world（`WorldState.ids`），policy 從 `world.ids.action()` 取 action id。專案內不再 import uuid（有測試檢查）。

### 2. 「同一結果」= 同一 output_hash

Spec 的 run_metadata 有 started_at / ended_at，兩次 run 的 result package 不可能逐位元相同。**output_hash 是 result package 去掉 reproducibility 區塊後的 SHA-256；兩次 run 的 output_hash 相同，就是同一結果。** 實測：兩次 v0.1 的 package 去掉 reproducibility 後逐鍵相同，output_hash 都是 `63090026…`。

### 3. canonical JSON

`sort_keys=True`、`separators=(",", ":")`、`ensure_ascii=False`、UTF-8。鍵的插入順序不影響 hash。

### 4. input_hash 包含 profile

Phase 7 起同一 scenario 換 profile 會得到不同的 result package，所以 profile 是輸入的一部分：`input_hash = content_hash({scenario, evaluation_profile})`。

### 5. runtime_version = skyvault.__version__

沒有自動的版本來源。`skyvault.__version__ = "0.8.0"`，pyproject 同步（從 0.1.0 直接跳到 0.8.0，對齊開發計劃的 v0.8）。之後每個 Phase 調升 minor。

### 6. ruleset_version 是規則內容的 hash

Spec 沒定義。`"rules-" + content_hash({world_contract.rule_set, 登記的 action type, SCHEMA_VERSION})[:12]`。改 entity 資料不會動它；改 rule_set、多登記一種 action、契約升版會動它（都有測試）。

### 7. run_id = 時間 + 輸入

同一輸入可能跑很多次，run registry 要能區分：`run_<UTC 時間到微秒>Z_<input_hash 前 8 碼>`。同一輸入的 run 共用後綴，一眼可以看出是同一個輸入。

### 8. seed policy

`runtime.random_seed_policy` 有寫就用；沒寫且 seed 是整數 → `fixed`。`stochastic` 的 run 刻意用不帶 seed 的 `Random()`，記錄 `random_seed: null`、`deterministic_replay_available: false`。`controlled_random` 目前與 fixed 相同（批量時各 repeat 的 seed 變化是 Phase 10 的事）。

### 9. result package 的 reproducibility 必填

ADR 004 承諾 Phase 8 把它改為必填。input_hash / output_hash 必須是 64 個小寫 hex。schema 升為 `"0.5"`。

### 10. scenario 的 version_control

Spec §11 的 scenario_version_control 成為 scenario 的 optional 區塊：version、parent_version、changed_from_previous（五類）、change_reason。**version 必須等於 scenario_version**，兩者不能說不同的故事。

### 11. compare_scenarios 與 compare_runs

`compare_scenarios(old, new)` 依 Spec 五類列出每個不同的葉值，格式 `"<path>: <old> -> <new>"`；entity 依 entity_id 對齊，重新排序不算變更；類別以外的欄位（id、名稱、版本欄位）不比較。

```text
assumptions_changed        assumption registry
data_changed               entities、space / entity / environment / resource、data_provenance、participants
rules_changed              rule_set、time_model、runtime、allowed_actions
metrics_changed            evaluation、evaluation_targets
failure_variables_changed  failure_variables、failure_exploration
```

seed 歸在 rules_changed（它屬於 runtime，決定怎麼跑）。

`compare_runs(a, b)` 列出 same_input、same_output 與結果、事件數、分數的前後值。

### 12. versioned scenario folder

`data/scenarios/<scenario_id>/<version>.json`。reference scenario 從 `data/scenarios/tactical_reference_001.json` 搬到 `data/scenarios/tactical_reference_001/v0.1.json`，16 個檔案的路徑一併修改。新增 v0.2：只把 blue_002 的 accuracy 從 0.55 調到 0.75，結果從 RED_survived（97 筆）變成 BLUE_survived（91 筆）。

### 13. run registry 是 JSON Lines 檔

技術欄點名 run registry，沒有指定儲存。**一行一個 run 的 JSON Lines 檔**：活得過程序、diff 友善、只追加。預設 `runs/registry.jsonl`，不進版本控制。

### 14. deterministic replay

`verify_reproducibility(package, scenario, profile)` 重跑並比對。`scripts/verify_run.py <package>` 只靠 package 找回輸入。

### 15. compute_profile 與 operator_system

`compute_profile = "python <版本>"`、`operator_system = platform.platform()`。

### 16. reference trace 的 digest 去掉 reproducibility

原本對整包算；reproducibility 有時間戳，必須排除。排除後 digest 仍是 `14f5ab21…`，與 Phase 7 相同 —— id 的正規化把舊的 uuid 與新的計數器對映成同樣的序號。

### 17. output_hash 取自驗證過的 package

第一版在驗證之前算 hash。測試發現 `block["output_hash"] != output_hash(package)`：**驗證會正規化數值**，score_breakdown 的 `raw: 3`（int）經過 `raw: float` 變成 `3.0`，canonical JSON 不同。

改為：先放一個佔位的 hash、驗證、再對驗證過的 package（呼叫端拿到的那一份）算 output_hash。寫檔再讀回來，hash 仍相同（已驗證）。

### 18. verification 多了 locate_inputs 與兩個欄位（凍結介面之外）

凍結介面只有 `verify_reproducibility`。為了讓 `verify_run.py` 只靠 package 運作，加了 `locate_inputs(package)`：由 scenario_id + scenario_version 找版本資料夾裡的檔，由 profile_id 找 profile。回傳值多了 `replay_available` 與 `recorded_output_hash`，讓 stochastic 與「package 被改過」兩種失敗可以分辨。

### 19. 「package 被改過」也算沒有重現

`expected_output_hash` 從 package 本身重算，而不是讀 reproducibility 區塊裡的值。若只比 rerun 與記錄的 hash，一個被改過內容但沒改 hash 的 package 會被判為重現成功（反向驗證時確認了這一點）。

### 20. compare_runs 多了三個欄位

凍結介面列 same_input、same_output 與結果、事件數、分數。實作多了 same_rules、status、overall_score、scenario_version，比較兩個版本時最常需要的就是這幾個。

### 21. v0.1 加上 version_control 會改變它的 input_hash

version_control 是 scenario 的一部分，所以 v0.1 的 input_hash 在 Phase 8 中途變了一次。output_hash 不變（模擬沒變）。這是預期的：輸入的文字變了，就是不同的輸入。

### 22. verification 放在 engine 之上

engine 需要 reproducibility 的 hash 與版本；verification 需要 engine 才能重跑。放在同一個套件會循環 import（反向驗證時親眼見到）。**hashing / versioning / registry 在 reproducibility/，不 import engine；重跑在 `skyvault/verification.py`，與 scripts 同層。**

## 後果

```text
好處    同一輸入 → 同一個 output_hash；結果可以被審計、重播、比較
        result package 自己說明來源：scenario 版本、input_hash、規則版本、執行版本
        output/ 的檔案只有 reproducibility 區塊會在每次 run 之間變動
代價    reference scenario 搬了位置，所有引用它的路徑都要改
        run registry 只在本機；共享需要另外的儲存
```
