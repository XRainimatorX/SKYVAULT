# Phase 12 — External System Interface v1.2

完成報告。這份文件是 Phase 12 結束時的凍結紀錄，寫完不再更新 —— 系統目前的樣子請看 [`../architecture.md`](../architecture.md)。

**狀態：功能完成，沒有已記錄未修的缺陷。**

---

## 1. 這個階段做什麼

Phase 12 開始前，外部系統只有一個通用的 job API：得自己把需求翻成 scenario 與 runtime；兩個系統對同一個單位下命令，scenario 契約直接拒絕；結果交回去之後誰來決定，沒有任何約定。

目標是開發計劃的原文：讓 NEXUS、STARTX、TAC ANGEL、EIDEN-01、AEROGRID、SKYFOX、HADES、CYBERHOUND、星衞計劃正式接入，加上 Conflict Package Return 與 Authority Handoff —— 「SKYVAULT 可以模擬、建議、警示，但不做最終決定」。規格依據是 [`../plan/phase12_external_system_interface.md`](../plan/phase12_external_system_interface.md) 與 Formal Spec §9、§13、§17。

```text
Issue      #31 Phase_12_external_system_interface（milestone #15 Phase 12 — External System Interface）
開設       衝突命令的現況、handoff 觸發率、failure threshold、九個系統的模型覆蓋；
           fixture 先 commit：tests/fixtures/external/submissions.json
步驟 A     兩份契約、handoff 的四個觸發與 package、提交窗口、衝突、分支模擬、權威決定、job 帶 handoff
步驟 B     九個系統 adapter；JobRequest 的 entity_changes 與 data_provenance
步驟 C     外部 API（計劃原文的路徑 + /submission、state_action_outcome、run decision）、CI 的 External systems 步驟
整合       scripts/run_external.py → output/external/；打開輸出時找到三個問題（見第 4 節）
```

十五項決定與開發中的十三項記錄於 [`../decisions/017_external_system_interface.md`](../decisions/017_external_system_interface.md)。

---

## 2. 這次執行發生了什麼

### 開設時的測量

```text
衝突的命令        TAC ANGEL 與 STARTX 同一 tick 命令 red_001 → scenario 契約拒絕；改成 batch proposals 才有分支
handoff 觸發率    120 個 run：risky / fail 94%（不能拿來當高風險）；extreme_high_risk_optimization 28%；sacrifice_* 21%
failure threshold 單一 run 0 / 120；failure map 6 個變量中 4 個崩潰，最早在 severe，baseline 存活 0.6 > 門檻 0.5
系統覆蓋          有 observer / adapter：NEXUS、STARTX、TAC ANGEL、HADES、AEROGRID、SKYFOX；
                  EIDEN-01、CYBERHOUND、星衞沒有對應的模型
```

### 同一組衝突的命令，現在

```text
提交      TAC_ANGEL:1（red_001 → [1,1]）、STARTX:2（red_001 → [0,1]、high）、HADES:3（red_002 → [1,1]）進入 tick 1 的窗口
推進      tick 1 一個 action 都不執行；world 停在 tick 0，awaiting_decision conflict_000001；再推進 → 409
分支      TAC_ANGEL:1、STARTX:2+HADES:3、none 各 5 次，從 tick 0、同一個 seed、已執行的 action 開始
package   required_decision true；handoff 觸發 conflicting_branches，may_execute_final_decision false
決定      SKYVAULT、TAC_ANGEL、STARTX、空字串 → 403；NEXUS 選 TAC_ANGEL:1 → 200；SOVEREIGN 再決定 → 409
繼續      tick 1：red_001 由 TAC_ANGEL 移動，HADES 對 red_002 的命令沒有執行；job_events 記錄「NEXUS decided」
```

### 九個系統（fixture 的提交，scripts/run_external.py）

```text
NEXUS       1 job    RED_survived / 97、output 63090026e137；briefing；handoff strategic_tradeoff
STARTX      1 job    press / hold 各 5 次：hold 的 mean_score 0.4303、press 0.3615；對「都不採用」的差
TAC ANGEL   1 job    三個命令全部執行，state-action-outcome 3 筆（tick 1–3，red_001）
EIDEN-01    1 job    blue_002.accuracy 0.75 → mean_score −0.0174、mean_hp_lost +12.67；缺口：blue_009、weather
AEROGRID    1 job    覆蓋率平均 0.93、最低 0.72、2 個 tick 低於 0.8；反應窗口 5 tick；缺口：空域配置
SKYFOX      3 jobs   任務成功率 1.0；9 次被拒的移動（全部 Move target occupied）
HADES       3 jobs   反應時間 1 tick；平均造成 16 傷害；未被交戰的敵人 blue_01、blue_03、blue_04
CYBERHOUND  0 job    supported false；兩個參數各一個缺口
星衞        6 jobs   可行（沒有能力所限的拒絕；三次 occupied 另列）；mean_score +0.1267 對原單位
```

### 模擬不變

```text
reference              RED_survived / 97、output 63090026e137…
六個 run 的 output_hash  與 Phase 11 相同（常數測試）
沒有外部提交的 run       一步都不變；軍事 policy 的修正只在以前會崩潰的情況生效
```

### 驗收十四條

| # | 開發計劃原文 | 如何證明 |
|---|---|---|
| 1 | 外部系統可提交 action | `/action/submit` 進入 world 的窗口；`/scenario/submit` 的 TAC ANGEL world_actions |
| 2 | SKYVAULT 可回傳 state-action-outcome | `/run/{id}/state_action_outcome?system=TAC_ANGEL`：3 筆，只有它自己的命令 |
| 3 | NEXUS 可調用完整 result package | `/submission/{id}`：result package（通過契約）、briefing、job 狀態與 handoff |
| 4 | TAC ANGEL 可在 SKYVAULT 世界中測 tactical action | 在 persistent world 中執行，event 的 system_id 是 TAC_ANGEL；被拒的命令附理由 |
| 5 | STARTX 可提交 branch | branch_compare：每個分支一個無衝突變體 + 都不採用 |
| 6 | 外部系統可以提交互相衝突的 action | fixture 的三個命令經 HTTP 提交 |
| 7 | SKYVAULT 可以標記 conflict | objective、location、priority 衝突；world 停下 |
| 8 | SKYVAULT 可以分支模擬 | 三個分支各 5 次；第一次與實際繼續的 world 逐位元相同 |
| 9 | SKYVAULT 可以回傳 conflict_package | `/conflict/{id}/package`、`/branches` |
| 10 | 高風險結果必須觸發 handoff | squad seed 45 觸發、reference seed 45 不觸發 |
| 11 | 衝突分支必須觸發 handoff | 每個 conflict 都帶 conflicting_branches handoff |
| 12 | failure threshold crossed 必須觸發 handoff | reference seed 43 perspective_eliminated、門檻 0.7 的 failure map 觸發；預設不觸發 |
| 13 | SKYVAULT 不可自行選擇最終方案 | 沒有權威決定時 conflict 一直 awaiting_decision；SKYVAULT / 非權威 → 403；契約的 Literal |
| 14 | 最終決策交回 NEXUS / 陛下 / 指定權威 | NEXUS、SOVEREIGN 決定 conflict 與 run 的 handoff，決定者被記錄 |

---

## 3. 交付了什麼

```text
src/skyvault/interface/
  handoff.py      handoff_triggers、map_crossed、authority_handoff、decide
  conflicts.py    SubmissionWindow、scheduled、find_conflicts、play_out、open_conflict、resolve
  systems.py      九個 adapter、ADAPTERS、KINDS、to_request、to_return
  api.py          add_external_routes、run_submission
src/skyvault/contracts/external.py   external_submission、authority_handoff（第 22、23 份）
src/skyvault/contracts/job.py        branch_compare、branches、entity_changes、data_provenance
src/skyvault/worldservice/           jobs：changed_entities、compare_variants、handoff；store：conflicts 表；
                                     worlds：提交窗口、WorldAwaiting、decide、events；api：awaiting 409、外部路由
src/skyvault/batch/                  run_branches；branch_variant 保留既有命令；平手列出全部
src/skyvault/domains/military/policy.py   沒有格子可走時等待
scripts/run_external.py → output/external/；scripts/serve_world.py 的說明
tests/fixtures/external/submissions.json（開設時 commit）
ci.yml                               External systems 步驟
skyvault.__version__                 0.17.0
```

---

## 4. 這一輪發現的問題

### 打開輸出才看到的三件事

測試全綠之後跑 `scripts/run_external.py`、逐檔打開：

```text
星衞     feasible: false —— 理由是三次 Move target occupied。另一個單位站在那裡，不是裝備做不到。
         → 只算能力所限的拒絕；情境性的另列；加上 drills（ADR 017 第 19 點）
         順手試 move_range 0（固定砲塔）：整個 run 崩潰 —— 軍事 policy 的 advance 對空序列取 min()（第 20 點）
handoff  「Highest win_rate: branch TAC_ANGEL:1 (0)」—— 兩個分支都是 0；Phase 10 平手時寫第一個（第 21 點）
EIDEN    provenance 的 scenario_id 是 null（request 預設值蓋掉了 scenario 的 id）
```

測試沒有抓到任何一個：測試是照程式算出來的數字寫的，而這些數字在程式的意義下都「對」。

### 兩套測試同時跑在同一個 PostgreSQL 上

3.10 venv 與 /tmp 的全套測試同時跑，各自 DROP 同一組表：6 個與 5 個 `[postgres]` 失敗。分開重跑都是 1129 passed。

### CI 步驟寫錯的 finish

External systems 步驟的 helper 沒有 body 就送 GET，`/finish` 是 POST。本機逐字執行時 405 → 409（Phase 11 回顧改法 4 的效果）。

### 其他

```text
分層測試     systems.py 第一版 import 軍事 pack 的 mission_outcome → 改經 domain hook
schema       job 契約加欄位後 job.schema.json 過期 → 重新匯出（漂移測試抓到）
決定的順序   world 先檢查「是否在等這個 conflict」再檢查權威 → 已決定的 conflict 讓 SKYVAULT 拿到 404 而不是 403；
             改為權威優先
live events  world 進行中的 event 是 Event 物件，不是契約的形狀 → world.events() 在鎖內轉換
```

---

## 5. 品質狀態

| 項目 | 結果 |
|---|---|
| pytest | 1130 passed（有 Redis / PostgreSQL 時；沒有時 1062 passed、68 skipped）（Phase 11 為 1023） |
| Python 3.10 venv | 全部通過（與 3.11 同一組） |
| 從 /tmp 執行 | 全部通過 |
| 全專案覆蓋率 | 99%；interface/ 100% |
| ruff / black / mypy / bandit | 通過（mypy 124 個檔案） |
| 測試讀 `output/` | 0 處 |

### 測試分布

```text
tests/interface/test_handoff_conflicts.py   28   四個觸發的真實 run（觸發與不觸發）；package；decide；契約的拒絕；窗口；
                                                 world 的衝突流程；SKYVAULT 從不選；fork 的逐位元相同；job 帶 handoff
tests/interface/test_systems.py             37   九個 adapter 的請求與返回（每個數值對照儲存的結果）；缺口；entity_changes；
                                                 drills 與能力限制；砲塔不崩潰；provenance
tests/interface/test_external_api.py        42   每個路徑（SQLite 與 PostgreSQL）；403 / 404 / 409 / 422 / 429；
                                                 提交在全部 run 結束前不回傳；半個提交不會跑；腳本；分層
既有測試                                    1023  平手的文字一行；step A 的一行（已決定 → ValueError）
```

### 反向驗證過的測試（20 個變異，全部紅）

```text
可行性只看限制 / 限制清單少一項 / 能力檢查拿掉 / kind 不檢查 / hp 不夾 0     → 紅
TAC ANGEL 的拒絕不分系統 / EIDEN 排序含 all_intel                           → 第一次存活 → 補測試 → 紅
被拒時前面的 job 不標 failed / 403 改 409 / 空 decision / 未完成就回傳 / unsupported 的回答 → 紅
world 先檢查等待再檢查權威 / awaiting 不回 409 / 沒有的單位可改                 → 紅
provenance 不補 scenario_id                                                 → 第一次存活（adapter 自己補）→ 補測試 → 紅
分支的 entity_changes 不套用 / capabilities 不合併 / 平手只寫第一個           → 紅
沒有格子時不等待                                                            → 第一次 NO MATCH（同樣的兩行出現兩次）→ 以實際程式碼重跑 → 紅
```

---

## 6. 已知限制

| 項目 | 留待 | 原因 |
|---|---|---|
| 權威名單不能由政策擴充 | 需要時 | governance 契約是 §15 的欄位；authorities 是參數 |
| 衝突時分支從 tick 0 重跑 | engine 可序列化時 | 決定論 = fork；5 次 × 分支數 |
| CYBERHOUND、EIDEN 的世界參數、AEROGRID 的空域、星衞的物理欄位 | Phase 14–16 | 沒有模型 → 缺口 |
| 真正的外部系統連線 | — | adapter 定義格式；fixture 與替身代替 |
| persistent world 不能跨程序恢復（Phase 11） | 需要時 | conflict 的紀錄在 store，但 world 在記憶體 |

---

## 7. 驗證

```bash
python3 scripts/run_tactical_reference.py   # RED_survived / 97；output 63090026e137
python3 scripts/run_external.py             # output/external/：九個系統的返回與一個衝突
python3 scripts/serve_world.py              # http://127.0.0.1:8100/api/docs（外部路徑在同一個 app）
python3 -m pytest tests/ -q                 # 1062 passed、68 skipped（設定 SKYVAULT_TEST_REDIS / _POSTGRES 時 1130 passed）
```

---

## 8. 一句話總結

> Phase 12 讓九個系統用自己的語言接入 SKYVAULT：命令在同一個世界裡執行，互相衝突時世界停下、每個分支從同一段歷史分叉跑完、交回 conflict package —— 而不論是 SKYVAULT 自己還是任何下命令的系統，想替權威做決定，得到的都是 403。
