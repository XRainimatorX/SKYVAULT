# 019 — Airspace Domain Pack：2D 空域、機率偵測、航跡、攔截、HADES / SKYFOX / AEROGRID

狀態：已採納
日期：2026-11-08
階段：Phase 15 — Airspace / HADES / SKYFOX / AEROGRID Domain Pack v1.5

## 背景

開發計劃 Phase 15：低空空域、無人機、防空、感測器覆蓋、攔截窗口、誤判、反應延遲。驗收四條：HADES 能提交防禦行為測試、SKYFOX 能在空域中模擬、AEROGRID 能提交空域配置、能輸出 detection gap / response time / failure points。

開設時的測量（Phase 14 的系統，還沒有任何空域程式碼）：spec 沒有 builder 讀得懂；偵測在感測範圍內是確定的、範圍外不可能 —— 觀測層沒有抽任何隨機數；沒有航跡、誤報、攔截器，也沒有會飛的東西：SKYFOX 是在格子上走的地面單位，HADES 像步兵一樣移動射擊，AEROGRID 的空域配置在介面上回來的是一個 gap。

issue #33 第 6 節在寫程式之前列出了十九項決定。這份 ADR 記錄那十九項與開發中的十五項。**模擬行為不變**：reference trace 與六個 output_hash 不變；軍事與 city 的 run 一步都不變。

## 決定

### 1. 新 domain pack domains/airspace/

model（飛行、偵測、覆蓋、攔截窗口的純函式）、scenario（spec → scenario）、handlers、policy、pack、metrics、failures、report、reference。core 不 import airspace（測試）；model 與 metrics 不 import engine、batch 或 random（測試）。

### 2. 空間

2D 格子（spec 的 size），Chebyshev 距離；高度是威脅與無人機的屬性 low / medium（計劃：2D first, 3D later）。pack 宣告 spaces = ("grid",)。

### 3. 陣營與結束

DEFENCE（資產、感測器、攔截器、指揮節點、SKYFOX）與 THREAT。威脅在波次之前待在 reserve，THREAT 一開始可能沒有任何 active 單位，所以 ends_with_last_faction = False；finished(world) 在沒有威脅待命或在空中時回傳 threats_resolved。

### 4. 軌跡

威脅從起點直線飛向目標資產，每 tick speed 格（step_toward）；抵達資產 = 命中：資產 hits + 1（達 rules.asset.hits_to_destroy 即摧毀），威脅狀態 leaked。

### 5. 偵測

每 tick、每個在線的感測器、每個範圍內的飛行物抽一次：p = detection × (1 − 0.5·d/range)，低空再 × low_altitude。距離的形狀沿用 Phase 5 的 confidence。p 的邊界 0 / 1 有測試。

### 6. 誤報

每 tick 每個感測器以 false_alarm 機率在範圍內隨機一格產生假航跡；假航跡一律被當成威脅，會被交戰並吸收齊射（浪費彈藥，測試）。

### 7. 航跡與識別

第一次偵測建立航跡；超過 track_timeout tick 沒再被偵測、或目標已不在，就失去。識別以 identify 機率判對：無人機被判錯 = 威脅（可能被友軍擊落），威脅被判錯 = 友軍（放行）。航跡存在指揮節點的 state.tracks。

### 8. 反應延遲

航跡建立後 reaction_delay tick 才可交戰（engageable_from）。

### 9. 攔截

攔截器對範圍內、已過反應延遲、判為威脅的航跡射擊一輪齊射（metadata.shots，不超過剩餘彈藥），每發以 kill 機率命中；目標必須此刻真的在射程內；第一發命中即摧毀（友軍 = fratricide）。之後 reload tick 不能射；ammo 用完就停。

### 10. 攔截窗口

interception_window(path, interceptors, engageable_from, until)：從可交戰到命中之前，位於任一攔截器射程內的 tick。

### 11. HADES 的防禦行為

交戰規則是參數：engage_at（射程比例）、priority（nearest_to_asset / first_tracked）、salvo、hold_fire_below（航跡信心）。存在 rule_set.airspace.hades；HADES 的提交走註冊的 hades_rules policy，params 逐鍵覆寫。builder 與 policy 都拒絕不認識的規則與越界的值。

### 12. SKYFOX

友軍無人機沿路線巡邏（baseline 的 move；Phase 6 的 SKYFOX adapter 可取代，測試）；被友軍擊落或撞上同高度的威脅 = failure point。

### 13. AEROGRID

提交空域配置：每個感測器可移動（position）、調參數（range、detection、false_alarm、low_altitude）、開關（online）—— 只限 scenario 有的感測器（含預設關閉的 radar_spare）。返回覆蓋、偵測、反應與漏過的原因。

### 14. 指標（純函式，只讀 result package）

detection_gap（沒有任何在線感測器覆蓋的格子比例；每個威脅從升空到第一次被偵測的 tick；從未被偵測就命中的威脅）、response_times、failure_points。airspace_outcome 把三者與誤報、打假航跡、誤擊合在一起。不進 Phase 7 的 11 軸。

### 15. failure variables

sensor_failure（detection × 0.9 / 0.75 / 0.6 / 0.4）、enemy_reaction_speed（speed × 1.25 / 1.5 / 2 / 3，見第 28 點）、equipment_overheat（kill × 0.9 / 0.75 / 0.5 / 0.25）；communication_failure 沿用 core。經 variable_for 與 pack 的 failure_variables()。

### 16. core 的評估

第一個 run 逐欄讀 verdict（Phase 14 回顧改法 1），並把讀到的問題變成第 21、22 點。scenario 宣告 success_outcomes = ["defended"]、perspective DEFENCE。

### 17. 每一種輸入

scenario run、batch（data/batches/airspace_sensors.json：南雷達開 / 關）、failure exploration、world service（NEXUS 的 domain_outcome）、HADES / SKYFOX / AEROGRID 的提交都在空域跑過並讀過輸出。

### 18. 邊界值

沒有感測器、沒有攔截器、沒有巡邏、沒有威脅、空的波次、威脅出生在資產上、偵測 0 / 1、ammo 0、速度 0 都跑完（測試）。

### 19. 模擬不變

reference RED_survived / 97、output_hash 63090026e137；六個 output_hash 的常數測試不變。

## 開發中的決定

### 20. 指揮節點下令升空

第一次跑：沒有任何威脅升空。待命的威脅不是 active，resolver 不接受不活躍 actor 的 action。改由指揮節點在 upkeep 發 launch（target = 威脅）。

### 21. acts(entity, world)：攔截器只在有機會時才有回合

第一次讀 verdict：anti_gaming 對 reference 標出 maximize_score_by_inaction —— 每 tick 每個攔截器都記一個 NO_ACTION，等目標本來就是防空的工作。pack 的 acts 多收 world（engine 傳入；city 的簽名相容）：攔截器有彈藥、已裝填、射程內有已放行的威脅航跡時才決定；那時不開火才是「選擇」。

### 22. success_outcomes 只要宣告就適用

Phase 14 只在沒有對手時使用它。空域有對手（THREAT），第一版把漏過的 run 判為 pass。改為：scenario 宣告 success_outcomes 就依它給 mission_success；軍事與 reference 沒有宣告，不變（六個 hash 不變）。

### 23. 離線的感測器不覆蓋

AEROGRID 的「開備用雷達」一開始沒有改變覆蓋 —— detection_gap 把離線的 radar_spare 也算進去。只算 online 的感測器（測試：打開後未覆蓋比例下降）。

### 24. response 與 reaction 分開

response_ticks（航跡建立 → 第一次射擊）包含威脅飛進射程的時間 —— 越早看到反而越長，讀 AEROGRID 的比較時是誤導。另加 reaction_ticks（第一個可交戰 tick → 第一次射擊）。

### 25. 被擊落的那一 tick 屬於攔截窗口

寫測試時找到：一發擊落的威脅，在那一 tick 結束時已是 destroyed，路徑被排除，窗口為空、reaction 為 None。路徑改為「這一 tick 或上一 tick 結束時 active」。

### 26. EntityChange 多一個 position

AEROGRID 要移動感測器，job 契約的 entity_changes 新增 optional 的 position（additive，schema 重新匯出）；位置仍由 world 檢查在空間內（測試：移到 [40, 40] 被拒）。Phase 12 的測試原本用 position 當「不允許的欄位」例子，改用 faction。

### 27. 巡邏：站上航點就換下一段

無人機卡在第一個航點 —— policy 的目標就是它站的格子。站上航點就前進 leg（policy 與 move handler 一致）。

### 28. 威脅速度可以是小數

測量 failure exploration 時看到：speed 是整數，× 1.25 無條件進位 = 2 —— mild、moderate、severe 都是加倍。威脅的 state.carry 累積小數格：1.25 = 每 tick 一格、每第四 tick 兩格（測試）。enemy_reaction_speed 現在依程度漸進（存活 0.4 → 0.2 → 0）。

### 29. scenario 的數值是量出來的

第一版（20 個 seed）只守住 10%：基線「沒加壓就失敗」，failure exploration 找不到斷點。三輪測量後：加 gun_north（[12, 8]、射程 3）、兩門砲 kill 0.75、identify 0.98 → 守住 70%、平均漏過 0.35。failure exploration：sensor_failure 在 moderate 斷、equipment_overheat 在 severe、communication_failure 在 severe。

### 30. 漏過的原因依序判定

never_detected → misidentified → detected_too_late → no_window → missed_in_window → not_engaged；每個漏過只有一個原因，每個原因各有一個造得出它的 scenario（測試）。無人機的 fratricide / collision 也是 failure point。

### 31. 介面的 gap

AEROGRID 在空域裡沒有 gap；在其他 scenario 的 gap 改為「airspace configuration has a model only in airspace scenarios (Phase 15)」。HADES 在空域交的是交戰規則（hades_rules），不是單位清單。

### 32. 一個與 Phase 15 無關的測試順序問題

test_core_extension 單獨跑時 tactical_reference 尚未註冊（只有別的測試先 import 過才會）。測試先 build_policy 一次（已知名稱會自行註冊）。

### 33. 報告的數字

報告表格的平均四捨五入到一位，沒有值時印「—」。

### 34. runtime_version 升為 0.19.0

## 後果

```text
好處    第一個機率偵測的世界：同一場景不同 seed 有不同的偵測、攔截與結局；誤報、誤認、誤擊都看得到
        HADES、SKYFOX、AEROGRID 第一次在同一個空域裡交出各自的東西並拿回可比較的數字
        每個漏過都有一個原因與可重現它的場景；failure exploration 在空域找得到斷點
代價    係數是手調的（依測量）；只有 2D、兩種高度；威脅只會直線飛向目標，不會閃避或改目標
        HADES 不能指定哪些攔截器；AEROGRID 不能新增感測器（只能用 scenario 已有的，含備用）
        指揮節點的航跡是集中的（一個節點），沒有通訊延遲或分散的航跡融合
```
