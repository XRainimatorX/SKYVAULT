# 018 — City Domain Pack：道路網上的城市、治安、電力連鎖、補給延遲、governance stability score

狀態：已採納
日期：2026-11-08
階段：Phase 14 — Logistics / Governance / City Domain Pack v1.4

## 背景

開發計劃 Phase 14：城市治理、補給、治安、停電、災害、戰後重建的世界 —— district network、road graph、population pressure、public order、food supply、medical capacity、power grid、communication、industry recovery、administration capacity。技術：networkx、GIS later、agent-based simulation、state machine、resource flow simulation。驗收四條：能模擬一座城市的秩序恢復、能看到停電連鎖反應、能測補給延遲對治安的影響、能輸出 governance stability score。

開設時的測量：reference scenario 搬到道路圖上被 engine 拒絕（「needs a grid space and a tick clock」）；拿掉檢查後 engine 跑得完，只有 reference policy 不會在圖上移動 —— 檢查保護的是 policy 而不是世界。所有單位同一陣營 → tick 1 結束、1 個 event、判定 pass。failure variable supply_delay 只把庫存打折。沒有電力、治安、行政，也沒有治理分數；觀測 view 只支援格子（mission view 除外）。

issue #32 第 6 節在寫程式之前列出了十七項決定。這份 ADR 記錄那十七項與開發中的十六項。**模擬行為不變**：reference trace 與六個 output_hash 不變；沒有 domain 或 domain 是 military 的 run 一步都不變。

## 決定

### 1. 新 domain pack domains/city/

model（治安、電力、旅程的純函式）、scenario（spec → scenario）、handlers、policy、pack、score、failures、report、reference。core 不 import city（測試）。

### 2. 空間

DomainPack 可宣告 spaces；city 是 network 與 graph。沒有 domain，或 domain 沒宣告 → 只接受 grid（測試：沒有 domain 的圖空間 scenario 仍被拒）。道路網是 NetworkSpace，權重是通行 tick。

### 3. 結束

ends_with_last_faction = False：city 跑滿 max_ticks；finished(world) 在每個 district 都 riot 時回傳 governance_collapsed，run 以 termination_condition_met:governance_collapsed 結束。

### 4. 結果名稱

outcome_label(world) 依人口加權治安命名：governance_collapsed（全部 riot）、order_restored（結束時 ≥ stable 門檻、開始時低於它）、order_held（開始與結束都 ≥）、order_not_restored（結束時低於）。order_held 是「看起來像恢復但不是」的反例（測試）。

### 5. 實體

district（每個節點一個）、power_plant、substation、depot、city_office、police、convoy、repair_crew，全部屬於 CITY 陣營。

### 6. 治安狀態機

stable ≥ 70、tense ≥ 50、unrest ≥ 30、riot 以下；每個改變治安的 event 帶 from_state / to_state（patrol 與 district_update 首尾相接，測試）。

### 7. 每 tick 的動態

upkeep 依序：power_update → arrive → district_update（每個 district 一個 action）。全部經 resolver，每個改動一筆 event。

### 8. 治安的變動

order_delta：斷糧（依人口加壓）、糧食不足、斷電、醫療與行政偏離基準、吃飽且有電時回升、鄰區 riot；再加 ±noise 的抽樣。係數在 data/domains/city/rules.json，scenario 帶一份。

### 9. 電力

substation 的負載 = 服務的 district 的需求；失效的 substation 把 district 依序交給 backup，backup 超載會跳脫 —— 連鎖。跳脫的 event 在 data.caused_by_event 指向造成它的那次斷電。

### 10. 補給

convoy 從 depot 沿最短路送糧；到達 = 出發 + 路徑通行 tick × supply.delay_factor（無條件進位）；到達時一筆 SUPPLY，帶 dispatched_at。

### 11. 警力與修復

police 沿道路旅行、在場時 patrol 提高治安（rules.order.patrol 範圍內抽樣）；repair_crew 到離線的 substation 做 restore_power。

### 12. baseline policy

城市行政：車隊送往「剩幾 tick 糧食」最少的 district、警力去治安最差而沒人負責的 district、維修隊去讓最多人沒電的 substation、市府補行政最弱的 district。不抽隨機數。

### 13. governance stability score

score.py，純函式、只讀 result package：每 tick 四個成分（order、services、administration、trend，人口加權、各 0–1），加權成分數；run 的分數是最後三分之一 tick 的平均。輸出分數、成分、逐 tick 序列、tick 0 的分數、每個 district 的結局。不進 Phase 7 的 11 軸（pack 的模型，同 mission_outcome）。

### 14. failure variables

city 自己解讀三個：supply_delay（delay_factor × 1.25 / 1.5 / 2 / 3，真的晚到）、civilian_pressure（起始治安 × 0.9 / 0.75 / 0.6 / 0.4）、resource_shortage（depot 糧食 × 0.75 / 0.5 / 0.25 / 0）；communication_failure 沿用 core。經 failure.variables.variable_for 與 pack 的 failure_variables()。

### 15. 每一種輸入

scenario run、batch（data/batches/city_supply_delay.json）、failure exploration、world service job 與 NEXUS 提交都在 city 上跑過並讀過輸出。

### 16. 邊界值

人口 0、糧食 0、容量 0、沒有道路、沒有 depot、沒有任何 actor、沒有電廠都跑完；通行 0 tick 的道路由 builder 拒絕（見第 31 點）。

### 17. 模擬不變

## 開發中的決定

### 18. pack 也可以宣告 acts(entity)

district 與設施是實體但不決定；不篩的話每 tick 多 14 個 NO_ACTION。city：只有 actor、而且不在路上時才決定（測試：旅途中沒有 ACTION_SELECTED）。

### 19. pack 宣告 end_reasons

讀 briefing 時看到「Failure threshold 'governance_collapsed' is not evaluated yet」—— 它其實每個 tick 都在檢查，只是沒發生。core 分不出「domain 的結束原因」與「不認識的名稱」，所以 pack 宣告它會用的原因；這些門檻沒達到時不再列為未評估。

### 20. scenario.evaluation.success_outcomes

第一次跑：完全崩潰的城市被 Phase 7 判為 pass —— core 的軸是戰鬥的形狀，city 沒有對手，strategic_value（保住的實體）恆為 1。scenario 可宣告哪些結果算任務達成；沒有對手時 mission_success 依它為 1 或 0。order_restored → pass、not restored / collapsed → fail（10 個 seed 驗證）。scenario 契約只新增 optional 欄位。

### 21. domain 結束原因 = 同名的 failure threshold 已達到

termination_condition_met:<name> 達到 scenario 列出的 <name> 門檻。core 不需要知道 city。

### 22. 失效轉移、跳脫隔離

第一版裡任何離線的 substation 都把 district 交給 backup：修好 Old Center 的那一刻，它接下兩個仍跳脫中的 substation 的負載（23.4 > 9）又跳脫 —— 每次修復都再跳一次。改為：失效（incident）才自動轉移；保護跳脫的 substation 隔離它的 district，直到復歸。

### 23. 超載一個 tick 後才跳脫

超載先標記（strain），下一次 power_update 仍超載才跳脫 —— 連鎖在 event 裡看得到先後（tick 4 strain、tick 5 trip）。

### 24. 維修隊：先完成腳下的，失效優先於跳脫

第一版讀輸出時看到：維修隊開 4 個 tick 到 Old Center，抵達時改去 North，什麼都沒修；而先修跳脫的 substation 會因為失效的還在而再跳。改為：腳下有離線的就修；否則失效的優先，再依沒電的人口。

### 25. 每趟送貨與回程至少一個 tick

邊界測試找到的缺陷：送往 depot 所在 district 的車隊旅程是 0 tick，arrives_at 等於當下，而這個 tick 的抵達已經處理過 —— 車隊永遠困在路上。

### 26. 跨 tick 的因果放在 data.caused_by_event

event 的 causal_links 只串同一個 action 的 event；跨 action 的連結要改 consequence 契約。連鎖改用 data 欄位，report.cascade 依它重建鏈與深度。

### 27. 路上與抵達

出發是 ENTITY_STATE_CHANGED（位置變成 None），抵達才是 MOVE（from / to）—— timeline 依 core 的 MOVE 慣例讀；timeline 對節點位置印名稱，不再 tuple("center")。

### 28. NEXUS 拿到 domain 的判斷

briefing 的「What happened」只數行動，停電本身不會出現。NEXUS 的返回多一個 domain_outcome：pack 有的 mission_outcome / governance_outcome hook 的結果（軍事與城市；reference 是 None）。

### 29. batch 依 success_outcomes 計勝負

勝利原本是 outcome == "<perspective>_survived"，city 會永遠 0%。scenario 宣告 success_outcomes 時，那些是勝、其他是負、沒有平手。沒有宣告時不變（測試）。

### 30. rules.json 的數值是量出來的

第一版兩個 scenario 都崩潰（運糧太慢：20 tick 只送 7 次）；第二版走到另一個極端（takeover 每個 seed 治安 99、blackout 4）。最後一版（20 個 seed）：takeover 全部恢復（分數 0.83）、延遲 ×2 治安 54–68、×3 14–24、blackout 15–36。

### 31. 通行 0 tick 的道路由 builder 拒絕

network 空間的契約要求正權重；builder 先以自己的訊息拒絕。

### 32. 電廠輸出不是限制

plant 的 output 記錄在 capabilities，但總負載（24.6）遠低於 100，不參與計算（已知限制）。

### 33. runtime_version 升為 0.18.0

## 後果

```text
好處    第一個不是戰鬥的世界：秩序恢復、停電連鎖、補給延遲都有多個 seed 的證明，governance score 有成分與序列
        engine 對其他空間與「不靠陣營結束」的世界開放，但只經由 pack 的宣告（空域、裝備 pack 沿用）
        core 的評估在沒有對手的世界裡不再說謊（success_outcomes、domain 結束原因）
代價    係數是手調的（依測量），不是校準過的真實城市
        briefing 的「What happened」不敘述城市的狀態變化；Phase 7 對不適用的軸仍建議「Exercise X」
        沒有 GIS、UI 沒有城市專屬的畫面、觀測 view 仍只支援格子
```
