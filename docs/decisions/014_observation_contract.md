# 014 — Observation Contract：observer profile、fog of war 與五種 view

狀態：已採納
日期：2026-11-08
階段：Phase 5 — Observation Contract v0.5

## 背景

開發計劃 Phase 5：每個系統依自己的 observer profile 看世界 —— TAC ANGEL 看局部戰術狀態、STARTX 看全局趨勢、HADES 看威脅、AEROGRID 看覆蓋、NEXUS 看任務進度。功能：Observer Profile、Visible / Hidden Entities、Fog of War、Sensor Confidence、Information Delay、Stale Data、Partial Observation。Formal Spec §5 給出 observation 的形狀（observer_id、time、visible_world_state、hidden_state、uncertainty、decision_context），並寫明「SKYVAULT 不是上帝視角沙盤」。驗收四條見 issue #28。

開設時量了 reference 與軍事 run：reference 的 RED 在 tick 0–1 看不到任何敵人（5 格 sensor），之後全看得到；urban 若不計 concealment 全程看得到全部敵人 —— 霧在小地圖上要靠地形。

issue #28 第 6 節在寫程式之前列出了十六項決定。這份 ADR 記錄那十六項與開發中的五項。**模擬行為不變**：沒有 observer_profile 的 run 一步都不變，reference trace 與 output_hash 63090026… 不變。

## 決定

### 1. 新的 core 套件 observation/

純函式，以單位 snapshot 的歷史（tick → {entity id: snapshot}）為輸入；不 import engine（測試逐檔檢查）。

### 2. 兩份新契約

observer_profile 與 observation 成為第 17、18 份 core 契約。只新增，schema 維持 0.6；JSON Schema 重新匯出。

### 3. observation 的形狀

Formal Spec §5 的六個欄位，加上 `view` 與 `viewpoint {faction, actor_id}`；visible_world_state 多一個 `summary`（每種 view 的彙總），uncertainty 多 `delay_ticks` 與 `observed_at`。契約檢查：stale 才有 age、己方只能是 active / destroyed、hidden_state 有 reason 恰好當 exists、observed_at = max(0, time − delay)。

### 4. 看得到

某一方任一存活單位與目標的距離 ≤ 該單位的 sensor_range（capability，否則 profile 的 default_sensor_range）× (1 − 目標格的 concealment)。距離依 space 的 distance_model。concealment 由 domain pack 提供（軍事：地形表），沒有 pack 時為 0。整個陣營共享感測 —— 這與軍事 baseline policy 的「每個單位自己看」不同（見第 15 點）。

### 5. confidence

1 − 0.5 × 距離 / 有效範圍，取所有看得到它的單位中最高者，四捨五入四位。有效範圍為 0 時（只會在同一格發生）為 1。

### 6. fog of war

看不到的敵人不出現在 observation 的任何地方。hidden_state 只有 `exists` 與 `reason`（fog_of_war），不給數量或 id。exists 以觀測的 tick（延遲後）計算，不洩漏現在。

### 7. stale data

之前看過、現在看不到的敵人，在 stale_after_ticks 內以 status stale、last_seen、age 出現在最後被看到的位置與狀態，confidence × (1 − age / (stale_after + 1))。更久就消失。

### 8. information delay

tick t 的 observation 顯示 tick max(0, t − delay_ticks)。歷史缺某個 tick 時用之前最近的一個。

### 9. partial observation

敵人的 hp 依 enemy_detail：exact（數值）、banded（intact > 2/3、critical < 1/3 起始 hp、其餘 damaged）、hidden（都不給）。己方一律精確。

### 10. 五種 view

```text
local      TAC ANGEL：決定的單位、己方全體、看得到與過期的敵人；known_risks = 現在打得到它（in_range）
           或移動一次後打得到它（can_close）的敵人；local_area = 中心、半徑、範圍內已知的單位
aggregate  STARTX：己方與已知敵方的數量、己方 hp 比例、趨勢；沒有任何位置或敵方 id
mission    NEXUS：tick 進度、各方存活 / 損失 / hp 比例；全局、無霧、confidence 1
threat     HADES：看得到與過期的敵人（依 enemy_detail）、各自最近的己方單位與幾 tick 後能打到它、防禦窗口
coverage   AEROGRID：己方感測名目範圍覆蓋的格數、比例、缺口數（四鄰相連的未覆蓋區）
```

### 11. engine 的路徑

policy 有 `observer_profile` 屬性時，engine 每次只給它 observation，呼叫 `decide_from_observation(observation)`；回傳 `{action_type, target, intent, …}` 或 None。engine 用與 scheduled_actions 相同的路徑補上 action id。沒有 observer_profile 的 policy 照舊拿 world。

### 12. engine 的歷史

只在 observing policy 時，engine 記 tick 0 與每個 tick 結束時的單位 snapshot；決定當下再加上現在的單位。沒有 observing policy 時 `engine.observed` 永遠是空的。

### 13. run 之後

`observations_for_run(package, scenario, profile, viewpoint)`：用 replay exporter 的每 tick 狀態重建同一份歷史（測試：與 engine 記的完全相同），每 tick 一份 observation。`scripts/observe_run.py` 寫 output/observations/<observer>.json。

### 14. TAC ANGEL 範例只看 observation

`observer_profile = "TAC_ANGEL"`，沒有 `decide_action`。它在 reference 上兩方都看不到對方、一直原地不動（no_winner）—— 這是霧的誠實結果，不是缺陷。

### 15. 軍事 baseline policy 保留自己的感測

它用同一條規則（每個單位自己看），改由觀測層提供留給 Phase 6（Actor / Agent Layer）。

### 16. 模擬不變

沒有 observer_profile 的 run 一步都不變；reference trace 測試把關。

## 開發中的決定

### 17. ObservingPolicy protocol

policies.py 多一個 protocol（observer_profile、decide_from_observation），`AnyPolicy = Policy | ObservingPolicy`。registry 的 factory 可以回傳任一種。

### 18. 己方單位帶 capabilities

第一版的 TAC ANGEL 範例用 known_risks 的 in_range 決定開火 —— 那是「敵人打得到我」，不是「我打得到敵人」。policy 需要自己的射程，所以己方單位在 known_entities 裡帶 capabilities；敵方永遠沒有（契約檢查）。敵方的 attack_range / move_range 只用在計算 known_risks 與 ticks_to_strike，視為已知的單位類型資料。

### 19. visible_contacts 多一個 space 參數

Frozen Interface 寫的是 `visible_contacts(units, faction, profile, concealment)`；距離要看 space 的 distance_model，所以加了一個有預設值（chebyshev）的關鍵字參數。原本的呼叫方式仍然有效。

### 20. 被看到的殘骸

看得到的已擊毀敵人以 status destroyed 出現（沒有 hp）；最後一次被看到時已是殘骸的敵人不會變成 stale —— 已知它沒了。

### 21. runtime_version 升為 0.14.0

依 ADR 008 的慣例；UI 的 package.json 同步。

## 後果

```text
好處    外部系統拿到的是自己的視角：TAC ANGEL 看局部、STARTX 看趨勢，看不到的就是看不到
        只看 observation 的 policy 結構上拿不到 world —— 不是約定，是 engine 根本不給
        每份 observation 帶 confidence、delay、stale_after、source_quality；跨 PYTHONHASHSEED 逐位元相同
代價    軍事 baseline policy 與訓練資料的 observation 仍用各自的感測（Phase 6）
        只支援 grid（與 tactical engine 相同）
        敵方的射程與移速被當成已知
```
