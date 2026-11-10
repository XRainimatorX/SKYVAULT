# Phase 20 — Full SKYVAULT v2.0

完成報告。這份文件是 Phase 20 結束時的凍結紀錄，寫完不再更新 —— 系統目前的樣子請看 [`../architecture.md`](../architecture.md)。

**狀態：功能完成，沒有已記錄未修的缺陷。roadmap 的二十一個 Phase 全部完成。**

---

## 1. 這個階段做什麼

Phase 20 開始前，每一項能力都有建立它的 Phase 與它自己的測試，但沒有任何東西把開發計劃的十五條最終驗收放在一起跑；而「SKYVAULT 不是決策者」是一個預設值 —— 一份設定檔就能把 SKYVAULT 自己變成決定者。

目標是開發計劃的原文：達成完整 SKYVAULT baseline，加上 Final Authority Boundary。規格依據是 [`../plan/phase20_full_skyvault_v2.md`](../plan/phase20_full_skyvault_v2.md) 與 Formal Spec §13、§17、§22。

```text
Issue      #36 Phase_20_full_skyvault_v2（milestone #20 Phase 20 — Full SKYVAULT v2.0）
開設       測量：governance / edition / handoff 都接受 SKYVAULT 為決定者，SKYVAULT 隨即 decide 成功；十五條沒有一起跑過；
           fixture 先 commit：data/v2/acceptance.json（必備 14、驗收 15、may 6、may not 5）
開發       boundary.py；契約的 Authority 型別；decide / resolve 拒絕 SKYVAULT；/api/boundary；
           acceptance/（service、checks、boundary_checks、run、report）；run_v2_acceptance；tests/layers.py；CI 的 Full v2 acceptance 步驟
```

十四項決定與開發中的六項記錄於 [`../decisions/022_full_v2.md`](../decisions/022_full_v2.md)。

---

## 2. 這次執行發生了什麼

### 開設時的測量

```text
governance   decision_authorities = ["SKYVAULT"] → 通過契約
edition      同樣通過
handoff      以 ("SKYVAULT",) 建立 → decide(handoff, "SKYVAULT", "accept") → decided、decided_by SKYVAULT
十五條       各有建立它的 Phase；沒有一起跑過
```

### 驗收結果（output/v2/acceptance.md）

```text
ACCEPTED — 15/15 acceptance criteria、14/14 must-haves、6/6 things SKYVAULT may do、5/5 things it may not do (refused)
同一個 in-process 內部版 world service，依序約五秒
```

| 群組 | 摘錄的證據 |
|---|---|
| 最終驗收 | NEXUS 的任務 → RED_survived、output 63090026e137；STARTX 的 press / hold；TAC ANGEL 的 ACTION_SELECTED 在世界裡；HADES / AEROGRID / SKYFOX 在空域；PAX 進 virtual test → redesign；normal run 97 events；failure exploration（空域）；replay reproduced；briefing 六個標題；military seed 45 → high_risk_outcome；conflict → required_decision；failure exploration → NEXUS、SOVEREIGN；/api/boundary 的 role、SKYVAULT 決定 → 403 |
| 必備 | 八個 scenario 的 world contract；13 個版本檔；兩次 run 同一 hash；rebuild_world 等於最終狀態；verify_reproducibility；七個系統走完；三個 domain 都跑完 |
| may | 模擬、建議（skyvault_position）、警告（risky + anti-gaming）、failure map、conflict package、invalid scenario 404 / 422 |
| may not | SKYVAULT 三種寫法決定 → 403；NEXUS 決定後 SKYVAULT 推翻 → 403；STARTX 的 intent 原樣；governance / edition 設 SKYVAULT → 拒絕；不選分支、may_execute_final_decision false |

---

## 3. 交付了什麼

```text
src/skyvault/boundary.py               ROLE、MAY、MAY_NOT、declaration、is_skyvault
src/skyvault/contracts/base.py         is_skyvault、Authority 型別（handoff、governance、edition 的決定者）
src/skyvault/interface/handoff.py、conflicts.py   SKYVAULT 一律不能決定（最先檢查）
src/skyvault/worldservice/api.py       /api/boundary
src/skyvault/acceptance/
  service.py          同一個內部版 world service（HTTP 測試客戶端）
  checks.py           十五條、十四項
  boundary_checks.py  may 六條、may not 五條
  run.py、report.py    run_acceptance、acceptance_report
data/v2/acceptance.json
scripts/run_v2_acceptance.py → output/v2/
tests/layers.py（core 的正面清單）、tests/v2/
ci.yml                                 Full v2 acceptance 步驟
skyvault.__version__                   2.0.0
```

---

## 4. 這一輪發現的問題

### 開設的測量

Final Authority Boundary 在設定層可以被抹掉 —— Phase 19 讓決定者可設定，卻沒有同時規定誰不能是決定者。

### 寫驗收時找到的

```text
External Adapter 的檢查寫死為通過     改為記錄前面的提交真的走完的系統
STARTX 的返回是分支的 dict、重播的 summary 沒有 output_hash、failure exploration 的結果本身就是 failure map
                                     —— 三個檢查第一版讀錯欄位，以錯誤失敗（驗收沒有跳過，直接說出哪一條、為什麼）
摘要行把 may 與 may not 都寫成「final authority boundary」 → 分開寫
```

### 轉換分層測試時

替換測試函式的腳本以「下一個 def」為界，跳過了一個前面有裝飾器的測試 —— 誤刪 test_the_rules_run_no_simulation；git diff 檢查刪除的 def 時找到並補回。

### 反向驗證

17 個變異；第一輪四個存活：conflict 的 SKYVAULT 守護被 handoff 的守護遮住（補「已決定的 conflict 仍先拒絕 SKYVAULT」）、decided_by 的型別與名單規則等價（移除重複）、normal run 的 hash 檢查與 External Adapter 檢查沒有反例（補 stub 測試）→ 其餘全部紅。

---

## 5. 品質狀態

| 項目 | 結果 |
|---|---|
| pytest | 1516 passed（沒有服務時 1447 passed、69 skipped）；Python 3.10 venv 1516 passed |
| 全專案覆蓋率 | 99%；acceptance/ 與 boundary.py 100% |
| ruff / black / mypy / bandit | 通過（mypy 171 個檔案） |
| 跨 PYTHONHASHSEED | output/v2/acceptance.json 逐位元相同 |

### 測試分布

```text
tests/v2/test_v2.py   33   邊界的宣告；SKYVAULT 的十種寫法；三個繞過被拒；偽造的 handoff；conflict（含已決定）；
                           權威仍能決定、預設不變；兩個版本的 /api/boundary；驗收全部通過與證據；每個項目都有檢查；
                           壞掉的邊界被看出來；壞掉的服務每條都失敗；報告；腳本；服務的拒絕；分層的正面清單
既有測試               1483  四個分層測試改用 tests/layers.py；版本格式測試放寬為 M.N.0（2.0.0）
```

---

## 6. 已知限制

| 項目 | 留待 | 原因 |
|---|---|---|
| 驗收是 in-process | 部署時 | 證明系統能做到，不證明某個部署的網路、身分驗證、資料庫設定 |
| 提交者的身分 | 部署環境 | 誰可以自稱 NEXUS 不由 SKYVAULT 驗證 |
| 11 軸不開放給 domain | 有需要時 | ADR 022 第 11 點：domain 的判斷經 success_outcomes 與 domain_outcome 旁行 |

---

## 7. 驗證

```bash
python3 scripts/run_tactical_reference.py   # RED_survived / 97；output 63090026e137
python3 scripts/run_v2_acceptance.py        # output/v2/：ACCEPTED，15 / 14 / 6 / 5
python3 -m pytest tests/ -q
```

pytest：1516 passed（有 Redis / PostgreSQL 時；沒有時 1447 passed、69 skipped）（Phase 19 為 1483）。Python 3.10 venv 1516 passed；從 /tmp 執行 1447 passed、69 skipped。

---

## 8. 一句話總結

> Phase 20 讓二十個 Phase 建好的每一塊在同一個服務上五秒內一起跑完 —— NEXUS 交任務、STARTX 交分支、TAC ANGEL 在世界裡行動、空域與裝備各就其位、高風險與衝突都交回權威 —— 並讓「SKYVAULT 模擬、建議、警告，但從不做決定」從一個預設值，變成任何設定都改不掉的事實。
