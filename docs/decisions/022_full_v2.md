# 022 — Full SKYVAULT v2.0：一起跑完的驗收，與改不掉的 Final Authority Boundary

狀態：已採納
日期：2026-11-08
階段：Phase 20 — Full SKYVAULT v2.0

## 背景

開發計劃 Phase 20：所有核心、接口、多 domain、失敗探索、報告、後台服務整合成完整系統。Full v2.0 必須具備十四項；新增 Final Authority Boundary（可以模擬、建議、警告、返回 failure map 與 conflict package、拒絕 invalid scenario；不可以做主權決定、override NEXUS、override STARTX 的戰略意圖、取代人類權威、自行決定最終戰略方案）；最終驗收十五條。

開設時的測量：十五條各有建立它的 Phase，但沒有任何東西把它們一起跑；而第 15 條（role 永遠是 world-environment engine）在設定層可以被破壞 —— governance 與 edition 都接受 decision_authorities = ["SKYVAULT"]，以 ("SKYVAULT",) 建立的 handoff 讓 decide(handoff, "SKYVAULT", "accept") 成功。這是 Phase 19 讓決定者可設定之後才出現的缺口。

issue #36 第 6 節在寫程式之前列出了十四項決定。這份 ADR 記錄那十四項與開發中的六項。**模擬行為不變**：reference trace 與六個 output_hash 不變；沒有把 SKYVAULT 設為決定者的部署一步都不變。

## 決定

### 1. 邊界放哪

src/skyvault/boundary.py：ROLE = "world_environment_engine"、MAY（六條）、MAY_NOT（五條，照計劃原文）、declaration()；is_skyvault 由契約提供（見第 15 點）。

### 2. 契約層強制

contracts/base.py 的 Authority 型別（不得是 SKYVAULT，任何寫法）：AuthorityHandoff.decision_authority、ResourceComputeGovernance.decision_authorities、Edition.decision_authorities 都用它。SCHEMA 0.6 之內：只收緊一個本來就不該被允許的值。

### 3. decide

interface.handoff.decide 與 interface.conflicts.resolve：SKYVAULT 一律 PermissionError，而且在任何其他檢查之前 —— 即使有人繞過契約把它放進名單、即使 conflict 已經決定過。

### 4. 宣告

world service 的 /api/boundary 回傳 role、may、may_not；兩個版本都有（商業版經 redact：「override NEXUS」讀作「override Decision Authority」，邊界本身不變）。

### 5. 驗收是一個套件

src/skyvault/acceptance/：service（同一個 in-process 內部版 world service，透過 HTTP 測試客戶端）、checks（十五條與十四項）、boundary_checks（may 與 may not）、run、report。不另寫模擬，只呼叫既有的路由與核心。

### 6. 十五條的證據

每條回傳 {passed, evidence}：submission / job / world / conflict 的 id、output hash、事件數、handoff 的 triggers 與 required_decision、decision_authority、briefing 的標題。

### 7. 十四項必備

每項一個檢查：World Contract（八個 scenario 的 world_contract 通過契約）、Scenario Grammar（13 個版本檔載入、未知名稱被拒）、Execution Protocol 穩定（同一 scenario 兩次 run 同一 hash）、Observation（每 tick 一份）、Action & Consequence（ACTION_SELECTED 與 causal links）、Event Memory + Replay（rebuild_world 等於最終狀態）、Evaluation、Failure Exploration、Reproducibility（verify_reproducibility）、Background Service（佇列完成的 job 與 governance 紀錄）、External Adapter（七個系統的提交真的走完）、Multi-Domain（military、city、airspace 都跑完）、UI / Report（overview 與 briefing）、Authority Handoff。

### 8. may

每條一個正面證據：模擬跑完、skyvault_position 的建議、risky 的判斷與 anti-gaming 旗標、failure map、conflict package、invalid scenario 被 404 / 422 拒絕。

### 9. may not

每條一個真實的嘗試：SKYVAULT（三種寫法）決定 handoff → 403；NEXUS 決定 conflict 後 SKYVAULT 再決定 → 403、紀錄仍是 NEXUS；STARTX 的 intent 原樣出現在 conflict package；governance 與 edition 把 SKYVAULT 設為決定者 → ContractError，預設權威仍含 SOVEREIGN；conflict package 不選分支、may_execute_final_decision 為 False。

### 10. 報告

output/v2/acceptance.json（證據）與 acceptance.md（ACCEPTED / NOT ACCEPTED、每條一行 ✅ / ❌ 與證據）。

### 11. 11 軸的未決項（Phase 14 起）

決定：core 的 11 軸不開放給 domain。domain 的成功定義經 scenario.evaluation.success_outcomes 進入 verdict，domain 自己的判斷經 domain_outcome hook（mission / governance / airspace）與產品的 KPI 旁行。理由：evaluation profile 的權重、anti-gaming 規則與訓練標籤都假設固定的軸；四個 Phase（city、airspace、virtual test、editions）都用這個做法完成而沒有說謊的 verdict。若未來需要，再以 profile 層級的擴充處理。

### 12. 分層測試

tests/layers.py：每個頂層套件一個 rank（domains 1、virtualtest 2、interface 與 worldservice 3、editions 4、acceptance 5），沒列出的是 core（0）；各「core 不 import X」測試共用 modules_below(X)。新套件從加入那天就被檢查。

### 13. 邊界值

SKYVAULT 的十種寫法（含 SKYVAULTS、skyvault_team 不算）、偽造的 handoff、已決定的 conflict、壞掉的服務（每條檢查以錯誤失敗）、沒有檢查的項目（LookupError）。

### 14. 模擬不變

reference RED_survived / 97、output_hash 63090026e137；六個 output_hash 的常數測試不變。

## 開發中的決定

### 15. is_skyvault 放在契約

contracts 是最底層、不 import 專案的其他模組；強制在那裡發生，所以 is_skyvault 定義在 contracts/base.py，boundary.py 由那裡取用。

### 16. decided_by 不另加型別

反向驗證找到：decided_by 用 Authority 型別與「decided_by 必須在 decision_authority 裡」等價 —— 名單本身不能含 SKYVAULT，所以 decided_by 永遠不會是它（等價變異）。decided_by 保持 NonEmptyStr，由名單規則守住。

### 17. conflict 的守護在最前面

反向驗證找到：拿掉 resolve 的 SKYVAULT 守護時測試仍過 —— 之後呼叫的 handoff.decide 也會拒絕。差別在順序：已經決定的 conflict 原本會回 ValueError；守護在最前面時一律是 PermissionError（測試）。

### 18. 外部轉接器的檢查要有證據

第一版的 External Adapter 檢查寫死為通過；改為記錄前面的檢查裡哪些系統的提交真的走完，七個都到才通過（測試：少一個就不過）。

### 19. httpx 列為執行相依

驗收透過 FastAPI 的測試客戶端呼叫服務（in process）；httpx 原本只是開發相依。

### 20. runtime_version 升為 2.0.0

開發計劃把這個 Phase 命名為 Full SKYVAULT v2.0：照字面。Phase 8 的版本測試原本把格式釘在 0.N.0，放寬為 M.N.0。

## 後果

```text
好處    一個指令、約五秒：十五條最終驗收、十四項必備、十一條邊界在同一個服務上跑完，交出誰都讀得懂的報告
        「SKYVAULT 不決定」不再是預設值：任何設定、任何寫法都改不掉
        11 軸的未決項有了決定；分層測試不再需要逐個維護排除清單
代價    驗收是 in-process 的：它證明系統能做到，不證明某個部署的網路、身分驗證與資料庫設定正確
        提交者的身分（誰可以自稱 NEXUS）仍由部署環境負責
```
