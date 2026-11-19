# Phase 17 — UI / Replay / Report System v1.7

完成報告。這份文件是 Phase 17 結束時的凍結紀錄，寫完不再更新 —— 系統目前的樣子請看 [`../architecture.md`](../architecture.md)。

**狀態：功能完成，沒有已記錄未修的缺陷。**

---

## 1. 這個階段做什麼

Phase 17 開始前，SKYVAULT 的結果是 19 個 JSON、Markdown 與文字檔。timeline.txt 可以讀，但判斷、失敗地圖、方案比較與 conflict package 都要打開 JSON 才看得懂；沒有地圖、沒有圖表，也沒有一份能帶進會議的文件。

目標是開發計劃的一句話：「讓非技術使用者能看懂 SKYVAULT 結果。」規格依據是 [`../plan/phase17_ui_replay_report.md`](../plan/phase17_ui_replay_report.md) 與 [`../plan/formal_spec.md`](../plan/formal_spec.md) §19.J。

```text
Issue      #25 Phase_17_ui_replay_report（milestone #9 Phase 17 — UI / Replay / Report System）
開設       測量 workspace、可重用的 exporter、Node / Python 工具鏈；fixture 先 commit：briefing 必須說的話
步驟 A     views/（七個畫面的 view model）、report/（briefing + Markdown / DOCX / PDF）、export_briefing
步驟 B     service/（FastAPI：REST、briefing 下載、WebSocket replay、靜態 UI）、serve_ui
步驟 C     ui/（Next.js 八個頁面 + ECharts + SVG 地圖）、e2e smoke（Playwright）、CI ui job
```

十八項決定與開發、第一次 CI 中的十項記錄於 [`../decisions/011_ui_replay_report.md`](../decisions/011_ui_replay_report.md)。

---

## 2. 這次執行發生了什麼

### 模擬不變

```text
Result          RED_survived
Events          97
reference trace 不變；output_hash 63090026… 不變；四個 exporter 0 行變動
```

### 八個頁面

```text
Overview         結果、判斷（risky，信心 92%）、分數 0.50、雙方損失；軸分數長條圖；findings、失敗原因、下一步測試
Timeline         十個 tick，每個 tick 是 timeline exporter 的句子；被摧毀的那一句標紅
Replay           10 × 10 格子上的六個單位與 hp 條；Previous / Play / Next / 拉桿，經 WebSocket 逐 tick 取 frame
Causal chain     46 個 action：誰、對誰、造成什麼；可只看造成摧毀的 4 個
Failure map      存活率熱度表（6 變量 × 4 級）、曲線圖、壓垮的變量、最佳替代方案、建議
Compare          9 個變體的勝率 / 失敗率長條圖與完整表；衝突的命令、每個分支相對「不下命令」的結果、Decision required: yes
Result package   十個部分的人話標籤與摘要，原始 JSON 收合
Briefing         預覽與 PDF / Word / Markdown 下載
```

### briefing

reference workspace 的 briefing 是 3 頁 A4，八節。fixture 在寫程式之前凍結的 19 句話，三種格式都包含。同一 workspace 輸出兩次逐位元相同；兩個不同的 PYTHONHASHSEED 下也相同。

### 驗收四條

| # | 開發計劃原文 | 如何證明 |
|---|---|---|
| 1 | 不用打開 JSON 也能看懂 simulation process | e2e 打開八個頁面，斷言出現的是句子與表格，`main` 的文字中沒有 JSON |
| 2 | 可以看到 tick-by-tick timeline | Timeline 頁 10 個 tick；Replay 頁按 Next 六次到 tick 6，Red Commander 變成 destroyed；Play 播到 tick 10 |
| 3 | 可以看到 failure map | Failure 頁的 communication failure 一列是 70% / 80% / 50% / 0% |
| 4 | 可以匯出 briefing report | 頁面下載的 PDF 以 `%PDF` 開頭、Word 以 `PK` 開頭；`scripts/export_briefing.py` 寫出三個檔 |

---

## 3. 交付了什麼

```text
src/skyvault/views/
  workspace.py     load_workspace()：result package 必要，其餘 optional（None）
  screens.py       overview_view、timeline_view、map_view、causal_view、failure_view、
                   comparison_view、package_view、losses —— 純函式，只用標準函式庫與 exporter
src/skyvault/report/
  briefing.py      build_briefing() —— 由 views 組成
  render.py        render_markdown()、render_docx()、render_pdf() —— 回傳字串或 bytes，可重現
src/skyvault/service/
  app.py           create_app()：/api/{health,overview,timeline,map,causal,failure,comparison,package}、
                   /api/report.{md,pdf,docx}、/ws/replay、靜態 UI
ui/                Next.js 16（App Router、靜態匯出）、React 19、ECharts 6；八個頁面；e2e/smoke.mjs
scripts/export_briefing.py、scripts/serve_ui.py
tests/conftest.py  reference workspace 在 tmp_path 由程式產生（測試不讀 output/）
tests/fixtures/briefing_reference.json   briefing 必須說的話（開設時 commit）
pyproject.toml     fastapi、uvicorn、python-docx、reportlab；dev：httpx、pypdf、types-reportlab
.github/workflows/ci.yml   check job 加 briefing 匯出；新增 ui job（build + 瀏覽器 e2e）
skyvault.__version__       0.11.0
```

---

## 4. 這一輪發現的問題

### briefing 的一句話與 fixture 不同

fixture 寫 `Best mean score: support-rear`，第一版 briefing 印 `Best mean_score: support-rear`。fixture 是在寫程式前依 `run_batch.py` 的輸出凍結的；程式照 fixture 改。**這正是先 commit fixture 的用處**：如果預期值是看了輸出才寫，這個不一致會被當成「預期」寫進去。

### 致命一擊的 hp 是 −13

地圖測試預期被摧毀的單位 hp 為 0，實際是 −13。event 確實記錄了 hp_after −13；timeline exporter 顯示時夾到 0。地圖改用同一個慣例（ADR 011 第 19 點）；紀錄不變。

### 測試的預期值錯了兩次

timeline 的 SCENARIO_END 那句沒有 `- ` 前綴，測試卻加了；failure map 測試以為 supply_delay 在 v0.1 的探索裡（它不在 —— 只探索 6 個變量）。都錯在測試，從輸出確認後改正（Phase 10 回顧改法 4：預期值從輸出複製 —— 這兩個是沒照做的地方）。

### bandit 標了 xml.sax.saxutils

`escape` 只是跳脫字元，但 bandit 依 import 判斷。已 commit 才發現，下一個 commit 改用 `html.escape`。教訓：commit 前的閘門要全部跑完，不只跑測試。

### 手機寬度下 report 頁 602 px 寬

截圖檢查才看到：64 字元的 hash 無法斷行。全站加 `overflow-wrap: anywhere`，比較圖的長標籤截斷，e2e 加一條手機寬度檢查（ADR 011 第 25 點）。

### 一個 WebSocket 變異讓測試卡住而不是失敗

拿掉 `end` 訊息後，測試在等第五則訊息，TestClient 的 receive 沒有逾時。這等於被抓到，但在 CI 裡會卡到工作逾時。記為已知限制。

### 第一次推送：CI 兩個 job 紅

本機全綠的程式，推上去後兩個 job 失敗，原因都是「本機環境比 CI 多了一樣東西或少了一個版本」：

```text
ui job           Replay 頁的 Next 一直 disabled：WebSocket 沒連上。uvicorn 沒有 WebSocket 函式庫就不支援 upgrade；
                 本機手動裝過 websockets，CI 沒有 → 宣告 websockets 相依（ADR 011 第 27 點）
check (3.10)     asyncio.wait_for 在 3.10 拋 asyncio.TimeoutError，它不是內建 TimeoutError（3.11 才是同一個類別）
                 → 播放 replay 崩潰；改接 asyncio.TimeoutError（第 28 點）
```

兩者都先在本機重現再修：移除 websockets 後 e2e 同樣卡在 Replay；用 uv 裝 Python 3.10，舊程式失敗、新程式通過，整套 590 個測試在 3.10 上也通過。

### 本機的系統 Pillow 與 cryptography 壞掉

reportlab 依賴 Pillow、pypdf 會探測 cryptography；這個容器裡兩者都是 Debian 打包、對不上 Python 3.11 的版本。本機用 `pip install --ignore-installed` 裝了可用的版本；CI 的乾淨環境由 pip 直接安裝，不受影響。不是程式的問題。

---

## 5. 品質狀態

| 項目 | 結果 |
|---|---|
| pytest | 590 passed（Phase 10 為 532） |
| 全專案覆蓋率 | 99%（3541 statements，53 miss） |
| `views/`、`report/`、`service/` 覆蓋率 | 99–100% |
| ruff / black | 通過 |
| mypy | 通過，74 個檔案 |
| bandit | 0 issues |
| next build（含 TypeScript） | 通過 |
| e2e smoke | 9 項通過 |
| 換工作目錄跑測試 | 590 passed |
| 測試讀 `output/` | 0 處 |
| exporter 程式碼變動 | 0 行 |

### 測試分布

```text
tests/views/test_views.py        15   七個 view、grid 與 graph 地圖、等級排序與空格、缺檔、分層
tests/report/test_briefing.py    17   fixture 的節與句（三種格式）、可選節、複數、表格、逐位元可重現、跨 hash seed
tests/service/test_app.py        26   每個端點 = 它的 view、404 與說明、不重啟即更新、下載、靜態 UI、WebSocket 協定
ui/e2e/smoke.mjs                  9   八個頁面在瀏覽器裡 + 手機寬度
既有測試                         532   未改
```

測試時間由約 15 秒增加到約 60 秒：reference workspace（1 + 760 + 900 次模擬）每個 session 產生一次。

### 反向驗證過的測試

```text
test_units_move_lose_hp_and_are_destroyed_frame_by_frame       拿掉 hp 夾到 0 → 紅
test_levels_follow_stress_order_and_gaps_stay_empty            等級依出現順序 → 紅
test_a_graph_space_is_drawn_on_a_circle_in_node_order          拿掉 -0.0 的修正 → 紅
test_the_word_document_is_dated_by_the_run_not_by_the_clock    不改 zip 時間 → 紅
test_the_same_briefing_renders_to_the_same_bytes               拿掉 invariant → 紅
test_without_failure_or_batch_outputs_their_sections_are_left_out   無條件加 failure 節 → 紅
test_ticks_count_what_was_done_with_plurals                    複數一律加 s → 紅
test_pause_stops_the_stream_where_it_is                        播放中忽略 pause → 紅
test_a_bad_request_gets_an_error_and_the_socket_stays_open     seek 不檢查範圍 → 紅
test_a_missing_optional_output_is_a_404…                       不回 404 → 紅
test_new_outputs_show_up_without_a_restart                     啟動時只讀一次 → 紅
test_play_streams_every_tick_in_order_to_the_end               不送 end → 卡住（等同被抓到）
```

---

## 6. 已知限制

| 項目 | 留待 | 原因 |
|---|---|---|
| server 只讀一個 workspace | Phase 11 | 多個 run 的切換需要後台服務的 run 管理 |
| 不能編輯 scenario | — | scenario studio 在 §19.J，不在 Phase 17 的功能清單 |
| graph / network 的節點放在圓上 | domain pack | 沒有座標資料；有地理資料的 domain 再改 |
| WebSocket 測試沒有逾時 | — | TestClient 的 receive 會一直等 |
| 沒有登入與權限 | — | 沒有任何文件要求 |
| UI 與 briefing 只有英文 | — | 與既有輸出一致 |

---

## 7. 驗證

```bash
rm -rf runs output/*.json output/*.txt output/*.md output/*.pdf output/*.docx
python3 scripts/run_tactical_reference.py           # RED_survived / 97；output 63090026e137
python3 scripts/explore_failures.py
python3 scripts/run_batch.py
python3 scripts/export_briefing.py                  # 八節；briefing.md / .pdf / .docx
cd ui && npm ci && npm run build && cd ..
python3 scripts/serve_ui.py &                        # http://127.0.0.1:8000
cd ui && npm run e2e                                 # 9 checks passed
python3 -m pytest tests/ -q                          # 590 passed
```

---

## 8. 一句話總結

> Phase 17 讓不看 JSON 的人也能讀懂 SKYVAULT：打開一個網址，就能從總覽讀到逐 tick 的時間線、在地圖上一步步看 Red Commander 在 tick 6 倒下、看通訊全斷如何壓垮方案、比較九個方案與兩條衝突分支，最後下載一份三頁、每次都逐位元相同的 briefing。
