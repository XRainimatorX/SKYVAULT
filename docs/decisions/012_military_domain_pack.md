# 012 — Military / Tactical Domain Pack

狀態：已採納
日期：2026-11-08
階段：Phase 13 — Military / Tactical Domain Pack v1.3

## 背景

開發計劃 Phase 13：把 tactical reference slice 升級成正式軍事 domain pack。內容九種 profile（unit、formation、terrain、sensor、weapon capability、logistics、morale / readiness、command delay、mission objective）；功能是小隊 / 排級、城市戰、山地、交通節點 reference scenario、doctrine comparison、TAC ANGEL training dataset export；「這不是 SKYVAULT core。這是第一個正式 domain pack」；驗收三條：同一 core 可跑不同 tactical scenario、TAC ANGEL policy 可替換 baseline policy、可輸出 state-action-outcome dataset。設計報告建議的參數：SUPPRESS_THRESH 60、PANIC_THRESH 85、RETREAT_THRESH 25、通訊 delay 0–3 ticks、loss_prob 0–0.2。

開設時量了 core：3v3 約 45 ms、10v10 約 170 ms、30v30 約 660 ms；WorldState 沒有 environment_state；engine 寫死 policy 與 handler；scenario 已有 optional 的 domain 欄位。

issue #26 第 6 節在寫程式之前列出了十九項決定。這份 ADR 記錄那十九項，以及開發與整合中做的八項。**沒有 domain 的 run 不變**：reference trace 與 output_hash 63090026… 不變。

## 決定

### 1. pack 與 core 的界線

pack 在 `src/skyvault/domains/military/`。core 只多三個擴充點：policy registry（`policies.py`）、`load_domain(name)`、`WorldState.environment`。除了 engine 透過名稱延遲 import，core 的任何模組都不 import pack（測試逐檔檢查）。

### 2. scenario.domain 選 pack

既有的 optional 欄位。`"military"` 才用 pack；null 時 engine 的每一步都與 Phase 17 相同。

### 3. pack 提供 handler、預設 policy、upkeep

handler 取代同名的 core handler；upkeep 是每 tick 開始時 pack 為士氣動搖的單位發出的 `rally` action。upkeep 也經過 resolver，所以世界仍然只由 consequence 改變，每個改變都是帶 action id 的 event（system_id `military_upkeep`）。

### 4. 地形在 environment_state

`world_contract.environment_state.terrain = {rows, legend}`。`WorldState.environment` 唯讀，不進 snapshot —— 地形在一場 run 中不變。

### 5. profile 展開進 scenario

`build_scenario` 把 profile 的值寫進每個單位的 capabilities / state 與 `rule_set.military`。產生的 scenario 自足：重跑、重現、`compare_scenarios` 都不需要 profile 檔。

### 6. 九種 profile

`data/domains/military/profiles.json`；Pydantic 模型在 pack 內（pack 的資料，不是 core 契約），`load_profiles` 補齊預設值。名稱交叉檢查：單位引用的 sensor / weapon 必須存在、地形符號不重複、壓制門檻不高於恐慌門檻、指揮延遲 0–3、遺失率 0–0.2。

### 7. 攻擊

命中率 = 武器 accuracy × (1 − 目標格 cover) × (射手被壓制時 0.5)。命中扣 hp、加武器的 suppression、扣士氣；沒打中也加一半的 suppression（近彈）。每發扣 ammo_per_shot，記成射手的 ENTITY_STATE_CHANGED；沒彈藥不能攻擊。ATTACK / MISS 保留 core 的 data 鍵（damage、hp_before、hp_after、distance），timeline 與 exporter 不用改。

### 8. 壓制、恐慌、撤退

suppression ≥ 60 被壓制（命中減半、不前進、找掩蔽）；≥ 85 恐慌（只 wait）；士氣 < 25 撤退（移到離看得到的敵人最遠的格子）。跨過壓制門檻的那一次多扣士氣。

### 9. 移動

目的地的加權路徑成本（進入每格的 move_cost）≤ move_range；rock、water 不可通行；敵人佔的格子不能進也不能穿過，友軍可以穿過。

### 10. 感測

看得到 = 距離 ≤ sensor range × (1 − 目標格 concealment)。在敵人被看到之前，單位朝敵人的出發位置前進（任務簡報給的情報）。感測在 policy 內 —— core 的觀測層是 Phase 5。

### 11. 指揮延遲

每 tick 做一個新決定送下去；抵達的是 delay_ticks 前的決定，以 loss_prob 遺失。遺失用獨立的 `Random("command:<seed>")`；loss_prob 為 0 時一次都不抽。結果：delay 0、loss 0 時與沒有指揮層逐筆相同（有測試），遺失不擾動戰鬥的擲骰（有測試）。

### 12. doctrine

aggressive：看到就打、否則前進。overwatch：單位依序號與 tick 的奇偶輪流「躍進」與「掩護」。defensive：看到敵人就找掩蔽、從掩蔽射擊，沒看到才前進。每個陣營一個。

### 13. 任務在 run 之後判定

destroy / seize / hold / delay；`mission_outcome(package, scenario)` 是純函式，讀終局的世界。不改 core 的 evaluation —— 任務是 pack 的概念。

### 14. 後勤

world resource `ammo`（logistics profile 的存量）；core 的 supply handler，`rule_set.action_costs.supply = {ammo: resupply_amount}`。logistics 單位補給 supply_range 內、彈藥低於一半的友軍；存量不夠一次補給就不補。

### 15. TAC ANGEL 可替換

`engine(policy=...)`，或 `runtime.policy.name`（已註冊的名稱）。policy 有 `system_id` 時，它決定的每個 event 都記這個 id。scenario 檔只能選已註冊的名稱，不能載入任意模組；腳本的 `--policy-module` 由執行的人明確指定要 import 的程式。

### 16. reference scenario 由 spec 產生

spec（開設時 commit）→ `build_scenario` → `data/scenarios/<id>/v0.1.json`；測試重建後逐檔比較，不一致就失敗。

### 17. doctrine 比較用 batch

urban 的 overwatch / defensive 是 `doctrine_variant` 產生的子版本（`v0.1+overwatch`），`compare_scenarios` 記下 doctrine 與 actor_policy 假設的變化。`data/batches/military_doctrine.json` 用 Phase 10 的 `run_batch` 比較。

### 18. dataset

每個 ACTION_SELECTED 一筆：state（自身、地形與掩蔽、看得到的敵人、友軍）、action、outcome（後續 event、傷害、是否擊毀、是否命中、被拒的原因）、episode（結果、所屬陣營的任務是否達成）。state 從 event 的 snapshot 重建；測試用 engine 自己在 ACTION_SELECTED 記的 actor snapshot 逐筆核對。紀錄模型在 pack 內。

### 19. schema 維持 0.6

只新增 optional 的 `runtime.policy`。

### 20. episode 以 hash 命名，不以 run_id

第一版 dataset 的 episode 帶 run_id，而 run_id 含執行時間 —— 同一組 run 每次匯出的檔都不同。依 Phase 10 回顧改法 1 跨 hash seed 驗證前就改成 `input_hash` + `output_hash`：同樣的 run 匯出同樣的位元組（有測試，兩個 PYTHONHASHSEED）。

### 21. dataset 不進版本控制

reference 的匯出（4 scenario × 3 run）1906 筆、2.8 MB。它是由程式產生的訓練資料，`output/tac_angel_dataset.jsonl` 加進 .gitignore。

### 22. 「military_baseline」不是註冊的 policy 名稱

baseline 需要 scenario（陣營、任務、出發位置），是 pack 的預設 policy，不是可以只靠名稱建立的 policy。registry 給外部 policy 用。

### 23. urban 的支援組改在出發線

spec 原本把 marksman 與 logistics 放在 [4, 3]，在守軍步槍射程內；RED 的命令有一個 tick 延遲，兩人在第一個 tick 就被擊倒。改到 [4, 0]（與兩個班同一條線）。這是 spec 的錯誤，不是規則的。

### 24. briefing 的每 tick 計數改用人話（修正 Phase 17）

軍事 run 有 ENTITY_STATE_CHANGED（彈藥、rally）、ACTION_REJECTED、NO_ACTION，Phase 17 的 briefing 把它們原樣印成「1 entity_state_changed」「2 action_rejecteds」。reference run 從來沒有這些型別，所以沒被發現。現在不計彈藥與 rally 的記帳、稱為「refused order」「idle unit」、複數照英文；reference 的 briefing 逐位元不變。

### 25. 防守在四個 scenario 中的三個佔優

量了每個 scenario 20 個 seed：squad、mountain、junction 的攻方任務達成 0/20，urban 7/20（aggressive）。這是規則與部署的結果（掩蔽、壓制、指揮延遲都偏向防守方），不是錯誤；urban 是有爭議的那一個，doctrine 比較放在它上面。

### 26. 外部 policy 的範例在 examples/

`examples/tac_angel_policy.py` 不是 pack 的一部分：它示範介面（看到最近的敵人就打，否則接近），並註冊為 `tac_angel_example`。

### 27. runtime_version 升為 0.12.0

依 ADR 008 的慣例；UI 的 package.json 同步。

## 後果

```text
好處    同一個 core 跑出小隊、城市、山地、交通節點四種戰術問題，結果與事件數各不相同
        policy 可以換：TAC ANGEL 或任何外部系統只要實作 decide_action
        每個決定都能成為訓練資料，而且可重現
        之後的 domain pack（Phase 14 城市、15 空域）照同樣的三個擴充點接入
代價    感測、任務、doctrine 都在 pack 內；core 的觀測層與 evaluation 還不知道它們
        batch 的指標是 core 的（勝率、失敗頻率），不含任務達成率
        tactical engine 仍只支援 grid + tick；交通節點用的是格子上的道路與橋
```
