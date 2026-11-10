# 021 — Editions：一顆核心，商業版與內部版兩張臉

狀態：已採納
日期：2026-11-08
階段：Phase 19 — Commercial / Imperial Dual Track v1.9

## 背景

開發計劃 Phase 19：建立對外商業版與內部核心版的分離 —— 外殼可商業化，核心要帝國化；短期可包裝成 simulation / training / planning / crisis tool，但不能封死未來 NEXUS / STARTX / TAC ANGEL 接口。商業版可包裝為六種產品；內部版保留 multi-domain world engine、failure exploration、NEXUS / STARTX / TAC ANGEL adapter、Star Guard equipment testing、full event memory、scenario grammar。驗收三條：商業版能展示價值、內部 core 不被破壞、商業場景產生的技術可反哺核心。

開設時的測量：world service 一律掛上外部介面（33 條路由，/scenario/submit 收九個系統），以 NEXUS 提交 → 202；內部名稱出現在 output/ 的多個檔案，連一般 batch 的衝突包與 briefing 都寫「NEXUS or the user decides」；內部名稱在 core 的 observation、contracts、batch、training、worldservice、airspace pack 都有 —— 用名稱過濾程式碼會破壞核心；handoff 的權威寫死為 NEXUS、SOVEREIGN；沒有任何版本的概念。

issue #35 第 6 節在寫程式之前列出了十四項決定。這份 ADR 記錄那十四項與開發中的九項。**模擬行為不變**：reference trace 與六個 output_hash 不變；內部版的 world service 路由是原本的超集（只多三條 edition 路由），回應不變。

## 決定

### 1. 新的一層 editions/

最上層（與 interface 同層，可 import interface、worldservice、virtualtest、domain pack）：manifest、redact、service、products、feedback。core 不 import 它（測試）；它不改寫核心，只選擇與包裝。

### 2. 版本是資料

data/editions/<id>.json，edition 契約（第 26 份，0.6 之內只新增）：systems、domains、job_kinds、products、decision_authorities、redact。

### 3. 不分叉

兩個版本跑同一套核心函式：商業版的 job 跑出與內部版相同的 output_hash（測試）；products 沒有自己的類別、engine、policy 或隨機數（AST 測試）。

### 4. 內部版

world service 原本的每一條路由都在，只多 /api/edition、/api/products、/api/products/{id}；九個系統都收；redact 為恆等（同一個物件）；handoff 仍是 NEXUS、SOVEREIGN。

### 5. 商業版的介面

systems 為空 → 外部介面不掛（/scenario/submit 404）；job kind 或 scenario 的 domain 不在允許清單 → 403 not_licensed（world service 的 gate）。

### 6. 不封死接口

外部介面的程式不刪：manifest 的 systems 加一個名稱就掛回來，而且只收那個系統（其他 403 not_licensed）。

### 7. redact

只在版本的邊界：每個商業回應（中介層）與產品輸出。名稱整個比對（字中的不算：shades、NEXUSES 不變），大小寫與空白 / 底線 / 連字號都算；小寫的比對（識別碼）換成 snake_case 別名（tac_angel_adapter → tactical_agent_adapter），其他換成原樣的別名；字典的鍵也換（recommendation_to_nexus → recommendation_to_decision_authority）；數字、布林、結構不變。leaks() 找出殘留，測試與 CI 都跑。

### 8. 決定者

governance 契約多一個 optional 的 decision_authorities；jobs 與 persistent world 的 handoff 讀它，沒有時用 interface 的預設。edition 服務把 edition 的 decision_authorities 放進 policy：商業版的 handoff 是 ["customer"]。

### 9. 六個產品

data/editions/products.json 列題目；products.py 每個一條流程：Crisis Planning（city_blackout 的連鎖與治理分數）、Urban Resilience（補給延遲 batch）、AI Scenario Testing（baseline / rule_based / scripted 三個 agent 的分數與 anti-gaming）、Equipment Concept Screening（virtual test）、Training & After-Action Review（軍事 run 的 briefing）、Risk Simulation Studio（airspace 的 failure exploration）。

### 10. 展示價值

每個產品：它回答的問題、KPI（從這次真的 run 讀出）、一段結論；「價值」= KPI 非空、來自真的 run、商業版看不到內部名稱（測試逐個產品）。

### 11. 反哺

feedback.contribute：客戶的 scenario 連同 data_provenance（source_id commercial:<product>、modified_by commercial edition）、這次 run 的結果與訓練 transitions，以商業版看到的樣子（redact 後）成為 contribution；import_contribution 把別名還原為內部名稱並以 scenario 契約驗證 → 內部核心跑出同一個 output_hash、跑 failure exploration、transitions 進入訓練過濾（測試）。產品的流程本身就是核心的函式，技術不必搬。

### 12. 每一種輸入

兩個 edition 的 world service、六個產品（函式與 HTTP）、feedback、serve_world --edition、run_products 都跑過並讀過輸出。

### 13. 邊界值

不認識的 edition、壞的 manifest（未知系統、空的決定者）、redact 表為空、產品不在允許清單、不存在的產品、domain 不允許、非 JSON 的回應（/api/docs）。

### 14. 模擬不變

reference RED_survived / 97、output_hash 63090026e137；六個 output_hash 的常數測試不變。

## 開發中的決定

### 15. world service 的兩個掛鉤

create_world_service 多 external_routes（預設 True）與 gate（預設 None）；refuse 把 PermissionError 對應為 403 not_licensed。add_external_routes 多 systems（預設 None：全部）。預設一步都不變。

### 16. edition 服務自己建佇列

第一次 smoke test：商業版批次的 handoff 是「Decision Authority、Executive Authority」—— NEXUS / SOVEREIGN 被改名而不是被換掉。佇列在套用 edition 之前就以原本的 policy 建好，jobs 讀的是那份。queue 為 None 時，edition 服務以 edition 的 policy 建 in-process 佇列；RQ 佇列由呼叫者以 edition_policy 建（serve_world --edition --queue rq 這樣做）。

### 17. /api/edition 不回傳 redact 表

redact 表的鍵就是內部名稱：public() 只給 edition_id、title、domains、job_kinds、products（測試、變異）。

### 18. 名稱整個比對

名稱前後不可是英數字：沒有這個邊界，shades 裡的 hades 也會被換掉（測試；拿掉邊界的變異是紅的）。

### 19. 還原別名

import_contribution 的反向表：每個別名對應到第一個映射到它的內部名稱；snake_case 別名對應到內部名稱的 snake_case（air_defence_operator_rules → hades_rules）。

### 20. 「至少一半」

讀產品報告：延遲 ×2.0 只有一半的 run 恢復秩序，結論卻寫「most runs」。改為「at least half the runs」，並以剛好一半的情況測門檻。

### 21. 產品的 briefing 帶 run id

產品輸出在兩個 PYTHONHASHSEED 下只有 briefing 的「Run: run_<時間>」一行不同 —— Phase 8 起 run id 含牆鐘時間，output hash 相同。與 output/briefing.md 一樣，保留。

### 22. 分層測試

city 與 virtualtest 的「core 不 import」測試把 editions 列為上層（與 domains、interface 同樣排除）。

### 23. runtime_version 升為 0.21.0

## 後果

```text
好處    同一份程式碼、同一顆核心，兩個可部署的版本；版本只是一個 JSON 檔
        商業版的六個產品各自回答一個客戶的問題，數字來自真的 run，看不到任何內部名稱
        內部版一個能力都不少；外部介面隨時可以為某個系統打開
        客戶做出來的場景帶著來源回到核心，跑核心的每一個工具
代價    redact 是字串層級的：新增內部名稱時要記得加進 commercial.json（CI 的外洩掃描會抓到）
        RQ worker 用它自己的 governance：edition 的決定者要由呼叫者帶進佇列
        授權、計費、帳號、UI 品牌化都不在範圍內
```
