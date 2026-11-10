# Phase 19 — Commercial / Imperial Dual Track v1.9

完成報告。這份文件是 Phase 19 結束時的凍結紀錄，寫完不再更新 —— 系統目前的樣子請看 [`../architecture.md`](../architecture.md)。

**狀態：功能完成，沒有已記錄未修的缺陷。**

---

## 1. 這個階段做什麼

Phase 19 開始前，SKYVAULT 只有一張臉：world service 一律掛上九個內部系統的介面，任何人都能以 NEXUS 身分提交；連一般批次的衝突包都告訴讀者「NEXUS or the user decides」；沒有可以拿給客戶看的產品。

目標是開發計劃的原文：建立對外商業版與內部核心版的分離 —— 外殼可商業化，核心要帝國化，不能封死 NEXUS / STARTX / TAC ANGEL 的接口。規格依據是 [`../plan/phase19_commercial_imperial_dual_track.md`](../plan/phase19_commercial_imperial_dual_track.md) 與 Formal Spec §1、§8.2。

```text
Issue      #35 Phase_19_commercial_imperial_dual_track（milestone #19 Phase 19 — Commercial / Imperial Dual Track）
開設       測量：33 條路由、NEXUS 提交 202、output/ 多個檔案寫內部名稱、權威寫死；
           fixture 先 commit：data/editions/internal.json、commercial.json
開發       editions/（manifest、redact、service、products、feedback）；edition 契約；world service 的 gate 與 external_routes；
           interface 的 systems；governance 的 decision_authorities；run_products、serve_world --edition；CI 的 Editions 步驟
```

十四項決定與開發中的九項記錄於 [`../decisions/021_editions.md`](../decisions/021_editions.md)。

---

## 2. 這次執行發生了什麼

### 開設時的測量

```text
API        create_world_service 一律掛外部介面：33 條路由；/scenario/submit 收九個系統；NEXUS 提交 → 202
輸出       內部名稱出現在 output/ 的檔案：NEXUS 8、HADES 7、TAC ANGEL 6、STARTX 5、SOVEREIGN 3、AEROGRID 3 ……
程式       內部名稱在 core 的 observation、contracts、batch、training、worldservice、airspace pack 都有
權威       AUTHORITIES = ("NEXUS", "SOVEREIGN")，沒有設定
```

### 兩個版本

| | 內部版（SKYVAULT Core） | 商業版（SKYVAULT Studio） |
|---|---|---|
| 路由 | world service 的全部 + 3 條 edition 路由（36） | 不掛外部介面（21） |
| 系統提交 | 九個系統 | 無（加一個名稱就只掛回那個） |
| job kind | 六種 | scenario_run、batch、failure_exploration、replay |
| handoff 的決定者 | NEXUS、SOVEREIGN | customer |
| 回應 | 核心原樣 | 每個 JSON 回應 redact，外洩掃描為空 |
| 同一個 reference run | output 63090026e137 | output 63090026e137 |

### 驗收三條

| # | 開發計劃原文 | 如何證明 |
|---|---|---|
| 1 | 商業版能展示價值 | 六個產品在商業版跑完，各有問題、KPI 與結論：Crisis Planning（連鎖 1 步、7 區斷電、治理 0.52 → 0.47、秩序未恢復）；Urban Resilience（延遲 ×2.0 以內至少一半的 run 恢復）；AI Scenario Testing（scripted 分數最高但被標刷分，最好的誠實 agent 是 baseline）；Equipment Screening（EXO continue、PAX redesign、MSX reject）；Training & AAR（20 tick、314 事件、tick 5 首次交火、7 個單位損失）；Risk Studio（未加壓存活 100%、最先壓垮的變數）。沒有任何內部名稱 |
| 2 | 內部 core 不被破壞 | 內部版的路由是原本的超集、九個系統都收、handoff 不變、redact 為恆等；兩個版本的 reference run output hash 相同；core 不 import editions；products 沒有自己的類別或隨機數；reference trace 與六個 hash 不變 |
| 3 | 商業場景產生的技術可反哺核心 | 客戶的城市（南變電站容量加倍）在商業版成為 contribution（帶來源、結果、transitions，沒有內部名稱）→ 匯入內部：output hash 相同、跑 failure exploration、transitions 進入訓練過濾；客戶寫的 air_defence_operator_rules 還原為 hades_rules 並跑完 |

### 每一種輸入

```text
world service     兩個 edition 各跑 scenario_run、batch、branch_compare（商業版 403）、系統提交（商業版 404 / 403）
產品              函式與 HTTP（/api/products、/api/products/{id}）；不在允許清單 403、不存在 404
feedback          城市與空域的 contribution
腳本              run_products --edition commercial → output/products/；serve_world --edition commercial
```

---

## 3. 交付了什麼

```text
src/skyvault/editions/
  manifest.py    edition_ids、load_edition、allows、public
  redact.py      redact、redact_text、leaks
  service.py     create_edition_service、edition_policy、gate_for
  products.py    六個產品、run_product、product_report、catalogue
  feedback.py    contribute、import_contribution
src/skyvault/contracts/edition.py       edition（schema 匯出 26 份）
src/skyvault/contracts/governance.py    decision_authorities（optional）
src/skyvault/worldservice/api.py        external_routes、gate；PermissionError → 403 not_licensed
src/skyvault/worldservice/jobs.py、worlds.py   handoff 的決定者讀 policy
src/skyvault/interface/api.py           add_external_routes 的 systems
data/editions/（internal.json、commercial.json、products.json）
scripts/run_products.py → output/products/；scripts/serve_world.py --edition
ci.yml                                  Editions 步驟
skyvault.__version__                    0.21.0
```

---

## 4. 這一輪發現的問題

### smoke test 找到的

商業版批次的 handoff 是「Decision Authority、Executive Authority」—— NEXUS / SOVEREIGN 被改名，不是被換掉。佇列在套用 edition 之前就以原本的 policy 建好；edition 服務改為自己以 edition 的 policy 建佇列（ADR 021 第 16 點）。

### 以讀者的眼光讀產品報告找到的

延遲 ×2.0 只有一半的 run 恢復秩序，結論卻寫「most runs」→「at least half the runs」，並以剛好一半的情況測門檻。

### 反向驗證

20 個變異；第一輪兩個存活（產品輸出本身沒有內部名稱，「產品經過 redact」沒被走到；「至少一半」的門檻沒有斷言）→ 各補一個測試（自訂 redact 表的產品、剛好一半）→ 全部紅。

### 其他

```text
分層測試     city 與 virtualtest 的「core 不 import」把 editions 誤算為 core → 列為上層
契約測試     EXPORTED_CONTRACTS 加 edition；governance 的 schema 重新匯出
hash seed    產品輸出只有 briefing 的 run id（含牆鐘時間）不同；output hash 相同
```

---

## 5. 品質狀態

| 項目 | 結果 |
|---|---|
| pytest | 1483 passed（沒有服務時 1414 passed、69 skipped） |
| 全專案覆蓋率 | 99%；editions/ 100% |
| ruff / black / mypy / bandit | 通過（mypy 164 個檔案） |
| 跨 PYTHONHASHSEED | output/products/ 除 briefing 的 run id 外逐位元相同 |

### 測試分布

```text
tests/editions/test_editions.py   45   manifest 與契約；redact 的 8 種寫法、結構不變、內部恆等；內部版的路由與系統與決定者；
                                       同一個 hash；分層；商業版不掛介面、拒絕 kind 與 domain、加一個系統、回應無外洩、
                                       決定者是 customer；六個產品的 KPI；產品的允許清單與 HTTP；報告；
                                       feedback（來源、hash、failure exploration、訓練過濾、別名還原）；腳本；serve_world
既有測試                          1438  三個測試改動（兩個分層測試、匯出的契約清單）
```

---

## 6. 已知限制

| 項目 | 留待 | 原因 |
|---|---|---|
| redact 是字串層級 | 需要時 | 新增內部名稱要加進 commercial.json；CI 的外洩掃描會抓到 |
| RQ worker 用它自己的 governance | 需要時 | edition 的決定者要由呼叫者以 edition_policy 帶進佇列 |
| 授權、計費、帳號 | 商業營運 | 不是世界模擬 |
| UI 的品牌化 | 需要時 | UI 讀 workspace；名稱在 API 的 redact 處理 |
| contribution 不自動寫進 repo | 需要時 | import_contribution 給出 scenario；存放與審核由人決定 |

---

## 7. 驗證

```bash
python3 scripts/run_tactical_reference.py                  # RED_survived / 97；output 63090026e137
python3 scripts/run_products.py --edition commercial       # output/products/：六個產品與 products.md
python3 scripts/serve_world.py --edition commercial        # 商業版的 world service
python3 -m pytest tests/ -q
```

pytest：1483 passed（有 Redis / PostgreSQL 時；沒有時 1414 passed、69 skipped）（Phase 16 為 1438）；Python 3.10 venv 1483 passed；從 /tmp 執行 1414 passed、69 skipped。

---

## 8. 一句話總結

> Phase 19 讓同一顆核心有了兩張臉：商業版的 SKYVAULT Studio 告訴客戶一座城市停電後治理分數掉到多少、哪個 AI agent 的高分是刷出來的、哪台裝備值得造 —— 卻說不出一個內部系統的名字；內部版一個能力都不少，而客戶改過的城市，會帶著它的來源回到核心裡被再試一千次。
