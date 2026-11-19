# Phase 8 — Reproducibility + Version Control v0.8

完成報告。這份文件是 Phase 8 結束時的凍結紀錄，寫完不再更新 —— 系統目前的樣子請看 [`../architecture.md`](../architecture.md)，契約的現行規格請看 [`../spec/contracts.md`](../spec/contracts.md)。

**狀態：功能完成，沒有已記錄未修的缺陷。**

---

## 1. 這個階段做什麼

Phase 8 開始前，行為可重現，但每一筆 event 與 action 的 id 都是 uuid4。同一輸入跑兩次，輸出檔每一行 id 都不同；要比較兩次 run，得先把 id 換成序號（`tests/reference_trace.py` 就是這樣做的）。result package 也沒有任何東西說明它來自哪個輸入、哪個版本。

目標：同一輸入得到同一結果並能證明、不同版本的 scenario 能比較、result package 能追蹤來源。規格依據是 [`../plan/phase8_reproducibility.md`](../plan/phase8_reproducibility.md) 與 [`../plan/formal_spec.md`](../plan/formal_spec.md) §11、§12。

```text
Issue      #22 Phase_8_reproducibility（milestone #6 Phase 8 — Reproducibility）
開設       fixture 先 commit：reference 搬進版本資料夾、新增 v0.2
步驟 A     決定性 id + hashing
步驟 B     版本、reproducibility 區塊、契約 0.5
步驟 C     scenario 比較、run registry、replay 驗證、runner / scripts
```

三步都在 issue 寫好的綠燈狀態結束。十六項決定記錄於 [`../decisions/008_reproducibility.md`](../decisions/008_reproducibility.md)。

---

## 2. 這次執行發生了什麼

### 模擬行為不變

```text
Result          RED_survived
Events          97
reference trace 97 筆不變；digest 14f5ab21…（與 Phase 7 相同）
```

### 同一輸入，同一結果

```text
event id          event_0000000001 … event_0000000097
action id         action_0000000001 起
兩次 v0.1 run      result package 去掉 reproducibility 後逐鍵相同
output_hash       63090026e13734f596339fe2129a4d17cbd43499f72c87cb0dbec5cdf9f5fd09（兩次相同）
run_id            兩次不同（時間不同），後綴 c9314004 相同（同一輸入）
```

### 一個 reproducibility 區塊（v0.1）

```json
{
  "run_id": "run_20261108T020450734250Z_c9314004",
  "scenario_id": "tactical_reference_001",
  "scenario_version": "v0.1",
  "random_seed_policy": "fixed",
  "random_seed": 42,
  "runtime_version": "0.8.0",
  "ruleset_version": "rules-080701976398",
  "input_hash": "c931400462e53ea4c65b47550471f3928a42b1c6aee8fbd9bfa0be4f5f4ef492",
  "output_hash": "63090026e13734f596339fe2129a4d17cbd43499f72c87cb0dbec5cdf9f5fd09",
  "deterministic_replay_available": true,
  "run_metadata": {
    "started_at": "2026-11-08T02:04:50.734250+00:00",
    "ended_at": "2026-11-08T02:04:50.752121+00:00",
    "compute_profile": "python 3.11.18",
    "operator_system": "Linux-6.18.44-fc-v310-x86_64-with-glibc2.39"
  }
}
```

### 兩個版本，兩種結果

```text
compare_scenarios(v0.1, v0.2)
  data_changed   entities[blue_002].capabilities.accuracy: 0.55 -> 0.75
  其餘四類        空
  —— 與 v0.2 檔內 version_control.changed_from_previous 完全相同

compare_runs(v0.1 run, v0.2 run)
  same_input     false        same_rules   true
  outcome        RED_survived → BLUE_survived
  event_count    97 → 91
  status         risky → fail
  mission_success 1.0 → 0.0
```

### 重跑驗證

```text
$ python3 scripts/verify_run.py output/result_package.json
Recorded output: 63090026e13734f596339fe2129a4d17cbd43499f72c87cb0dbec5cdf9f5fd09
Rerun output:    63090026e13734f596339fe2129a4d17cbd43499f72c87cb0dbec5cdf9f5fd09
Reproduced: yes
```

---

## 3. 交付了什麼

```text
src/skyvault/runtime/ids.py              IdSequence、RunIds
src/skyvault/reproducibility/
  hashing.py                             canonical_json、content_hash、input_hash、output_hash
  versioning.py                          RUNTIME_VERSION、ruleset_version、seed_policy、
                                         compare_scenarios、compare_runs
  registry.py                            RunRegistry（JSON Lines）
src/skyvault/verification.py             locate_inputs、verify_reproducibility
src/skyvault/__init__.py                 __version__ = "0.8.0"
contracts/                               schema 0.5：reproducibility 必填；scenario.version_control
engine.py                                seed policy；reproducibility 區塊
scripts/run_tactical_reference.py        --scenario、--registry；印出 run_id 與 output_hash
scripts/verify_run.py                    從 package 重跑
data/scenarios/tactical_reference_001/   v0.1.json、v0.2.json（各帶 version_control）
.github/workflows/ci.yml                 verify_run 兩次、v0.2 結果、registry 三筆
```

### 驗收三條

| # | 開發計劃原文 | 如何證明 |
|---|---|---|
| 1 | 同一 scenario + 同一 seed + 同一 ruleset 會得到同一結果 | 兩次 run 的 package（去掉 reproducibility）逐鍵相同、output_hash 相同；換 seed → 兩個 hash 都變；換規則 → ruleset_version 變 |
| 2 | 不同版本 scenario 可比較差異 | compare_scenarios 指出 blue_002 的 accuracy；compare_runs 指出 RED → BLUE、97 → 91 |
| 3 | result package 能追蹤來源 | reproducibility 區塊必填；verify_run 只靠 package 就找回 scenario 版本與 profile 並重跑 |

---

## 4. 這一輪發現的問題

### 在驗證之前算的 output_hash 對不上

第一版在 `validate_result_package` 之前算 output_hash。`test_the_block_hashes_match_what_was_run_and_produced` 立刻失敗：記錄的 hash 是 `c3015d52…`，重算的是 `63090026…`。

原因：驗證會正規化數值。score_breakdown 的 `raw` 宣告為 float，引擎給的是 int `3`，驗證後變成 `3.0`。canonical JSON 裡 `3` 與 `3.0` 是不同的字，hash 就不同。**記錄的 hash 描述的是一份沒有人會拿到的 package。**

改成對驗證過的 package 算。這個測試是在 issue 寫了「output_hash 必須能從 package 重算」之後才寫的 —— 如果只測「兩次 run 的 hash 相同」，兩次都在驗證前算，會一致地錯下去。

### 只比 hash 的驗證會放過被改過的 package

`verify_reproducibility` 的第一個念頭是「重跑的 hash == 記錄的 hash」。反向驗證時把條件改成只比這兩者，「改過內容但沒改 hash 的 package」測試就紅了 —— 證明測試抓得到，也證明了這個念頭是錯的：記錄的 hash 是 package 自己說的，不能拿來證明 package 沒被改過。現在三個值都要相等：重算的、記錄的、重跑的。

### 循環 import 在反向驗證時現形

驗證「reproducibility 不 import engine」時，在 registry.py 加 `from ..verification import …`，結果不是測試失敗，而是 import 時就 `ImportError: partially initialized module`。這正是設計上把重跑放在 engine 之上的原因（ADR 008 第 22 點），反向驗證把它具體化了。這次依 Phase 7 回顧改法 3，先用 `python3 -c "import …"` 確認變異真的被執行。

### v0.1 的 input_hash 中途變了一次

在 v0.1 加上 version_control 之後，它的 input_hash 從加之前的值變成 `c9314004…`。output_hash 不變。這是正確的（輸入的文字變了），但如果有人在 Phase 8 中途記下了 v0.1 的 input_hash，那筆紀錄就對不上了。記入 ADR 008 第 21 點。

### 調 hp 找不到變體，調命中率找到了

為 v0.2 找「只改一個值、結果明顯不同」的變體。第一個念頭是調 hp —— Phase 7 已經知道那會讓 threat score 改變、整場戰局重來。改調 blue_002 的 accuracy：0.65 不變、0.70 平手、0.75 BLUE 勝。選 0.75。

---

## 5. 品質狀態

| 項目 | 結果 |
|---|---|
| pytest | 393 passed（Phase 7 為 353） |
| 全專案覆蓋率 | 98%（2214 statements，42 miss） |
| `reproducibility/`、`verification.py` 覆蓋率 | 98–100% |
| ruff / black | 通過 |
| mypy | 通過，54 個檔案 |
| bandit | 0 issues |
| 換工作目錄跑測試 | 393 passed |
| 測試讀 `output/` | 0 處 |
| exporter 程式碼變動 | 0 行 |

### 測試分布

```text
tests/reproducibility/test_determinism.py          10   兩次 run 相同；id 每個 world 各自計數；不用 uuid；hash
tests/reproducibility/test_metadata.py             13   reproducibility 區塊；hash 可重算；版本；seed policy；version_control
tests/reproducibility/test_versions_and_registry.py 14  compare_scenarios / runs；registry；replay；竄改；stochastic；分層
既有測試                                           356   改動：路徑搬家、0.4 被拒、fixture 加 reproducibility
```

### 反向驗證過的測試

```text
test_the_block_hashes_match_what_was_run_and_produced   第一版實作（驗證前算 hash）→ 紅
test_an_edited_package_does_not_reproduce               只比 rerun 與記錄的 hash → 紅
test_the_registry_records_and_finds_runs                by_input 不過濾 → 紅
test_reproducibility_never_imports_the_engine           registry.py 加 from ..verification import → import 失敗（紅）
                                                        （先以 python3 -c "import …" 確認變異被執行）
```

---

## 6. 已知限制

| 項目 | 留待 | 原因 |
|---|---|---|
| run registry 是本機 JSON Lines 檔 | 需要共享時 | 文件沒有指定儲存；`runs/` 不進版本控制 |
| controlled_random 與 fixed 相同 | Phase 10 | 每個 repeat 的 seed 變化屬於批量模擬 |
| runtime_version 手動維護 | — | 每個 Phase 調升 minor；忘記調就會兩個版本同名 |
| locate_inputs 只認得版本資料夾的慣例 | — | 不在 `data/scenarios/<id>/<version>.json` 的 scenario 要自己傳給 verify_reproducibility |
| verify 只支援 tactical engine | domain pack | 目前只有這一個 engine |

---

## 7. 驗證

```bash
rm -rf runs output/*.json output/*.txt output/*.md
python3 scripts/run_tactical_reference.py                       # RED_survived / 97；Run: run_…_c9314004
python3 scripts/verify_run.py output/result_package.json        # Reproduced: yes
python3 scripts/run_tactical_reference.py --scenario data/scenarios/tactical_reference_001/v0.2.json   # BLUE_survived / 91
python3 -m pytest tests/ -q                                      # 393 passed
cd /tmp && python3 -m pytest ~/SKYVAULT/tests -q                 # 393 passed
ruff check . && black --check src/ tests/ scripts/
python3 -m mypy src/
python3 -m bandit -c pyproject.toml -r src/
```

---

## 8. 一句話總結

> Phase 8 讓每一次 run 都能證明自己 —— id 改成每個 run 的計數器，同一輸入得到同一個 output_hash；每個 result package 帶著它的輸入、規則與執行版本；scenario 有版本資料夾，v0.1 → v0.2 的一個命中率變化被精確指出並讓結果翻盤；任何 package 都能只靠自己找回輸入、重跑並驗證，而 tactical reference 的模擬一點都沒變。
