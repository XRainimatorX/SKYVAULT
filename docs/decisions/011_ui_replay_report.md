# 011 — UI、Replay 與 briefing report

狀態：已採納
日期：2026-11-08
階段：Phase 17 — UI / Replay / Report System v1.7

## 背景

開發計劃 Phase 17：讓非技術使用者能看懂 SKYVAULT 結果。功能是 event timeline、map view、replay view、scenario comparison dashboard、failure map view、causal chain view、result package viewer、PDF / DOCX export；技術欄是 React / Next.js、FastAPI backend、WebSocket replay、Plotly / ECharts、map visualisation、report generator；驗收四條：不用打開 JSON 也能看懂 simulation process、可以看到 tick-by-tick timeline、可以看到 failure map、可以匯出 briefing report。

開設時先量了：reference workspace 是 19 個檔（result package 225 KB、batch_result 379 KB）；四個 exporter 已經能從 result package 推導出畫面需要的一切；Node 22、Next.js 16、React 19、ECharts 6、FastAPI、python-docx、reportlab 都裝得到；Next.js 靜態匯出 build 4 秒。

issue #25 第 6 節在寫程式之前列出了十八項決定。這份 ADR 記錄那十八項，以及開發與第一次 CI 中做的十項。**模擬行為不變**，四個 exporter 沒有改。

## 決定

### 1. 資料來源是 workspace 目錄

UI 讀一個目錄（預設 `output/`）：`result_package.json` 必要，failure 四檔與 batch 四檔 optional。server 不跑模擬 —— 那是 Phase 11（後台服務）的事。所有畫面都由純函式從這些檔案推導。

### 2. 一個 process、同源

FastAPI 提供 `/api/*` 與 `/ws/replay`，並把 Next.js 的靜態匯出（`ui/out`）掛在 `/`。不需要 CORS，不需要另一個 Node server；`next dev` 不是必要的。

### 3. React / Next.js → Next.js 靜態匯出

技術欄寫「React / Next.js」。Next.js 是 React 的框架，選它就兩者都有。`output: "export"` 讓 build 產生純檔案；頁面是 client component，執行時 fetch `/api`。`trailingSlash: true` 讓每頁是一個帶 `index.html` 的資料夾，正好是 StaticFiles 找的東西。

### 4. Plotly / ECharts → ECharts

純前端，不增加 Python 相依。用在軸分數、失敗地圖的存活率曲線、方案比較。

### 5. 地圖

grid 畫成 SVG 格子；graph / network 的節點座標放在圓上（依空間列出節點的順序，`math` 算，不用 networkx），在 view model 裡算好，前端只畫。reference 只用 grid；graph 有測試。

### 6. WebSocket replay 協定

```text
server → {type: ready, first, last}
client → {type: seek, tick}                     server → {type: frame, frame}
client → {type: play, from, interval_ms}        server → frame … frame {type: end, tick}
client → {type: pause}（播放中）                 server → {type: paused, tick}
不存在的 tick / 不認識的 type                    server → {type: error, message}，socket 不關
```

### 7. timeline 重用 exporter 的句子

`timeline.write_event` 逐 tick 產生的句子就是畫面上的句子；另列每個 tick 被摧毀的單位。不重寫敘述邏輯 —— 畫面與 timeline.txt 永遠說同一件事。

### 8. causal chain 重用 causal_chain

每條鏈補上 actor / target 的名字與 tick。

### 9. failure map view

變量 × 等級的存活率表（依 mild → collapse 排序；某變量沒跑的等級為空）、崩潰等級、sensitivity、collapse sequence、存活條件、建議。

### 10. comparison dashboard

batch_result 的變體表 + 各指標最佳 + conflict package。不帶每個 run 的紀錄（900 筆）—— 畫面比較的是變體。

### 11. result package viewer

每個頂層欄位一節：人話標籤（「Everything that happened」）、摘要（「97 events」）、收合的原始 JSON。

### 12. briefing 的結構

`build_briefing(workspace)` 回傳 `{title, created, sections}`，每節 `{title, paragraphs, bullets, table}`。三個渲染器回傳字串或 bytes，不寫檔。節：Summary / What happened / Losses / Evaluation / Trade-offs / [Failure exploration] / [Plan comparison] / Reproducibility —— 方括號的只在對應檔存在時出現。briefing 由 views 組成，所以它說的每一句話畫面上都有。

### 13. briefing 可重現

同一 workspace 兩次輸出逐位元相同：PDF 用 reportlab 的 invariant 模式；DOCX 的 core properties 固定為 run 的 `ended_at`，zip 內每個 entry 的時間也蓋成同一個（python-docx 預設用當下時間）。不同 PYTHONHASHSEED 下也相同（Phase 10 回顧改法 1，有測試）。

### 14. 英文

UI 與 briefing 用英文，與 timeline、key_findings、既有報告一致。

### 15. 分層

views/、report/briefing 只 import 標準函式庫與 exporter；渲染器只 import docx / reportlab；service 只 import views / report。三者都不 import engine（AST 測試逐檔檢查）。

### 16. 相依

fastapi、uvicorn、python-docx、reportlab 進 dependencies；httpx、pypdf、types-reportlab 進 dev。`ui/package.json` 釘死版本並 commit lockfile；playwright 釘在 1.63.0，與環境內建的瀏覽器同一版。

### 17. 不新增契約

view model 是畫面的形狀，不是 SKYVAULT 對外的資料格式。schema 維持 0.6。

### 18. 「不用打開 JSON」用瀏覽器證明

e2e smoke 打開八個頁面，斷言出現的是句子與表格，而且 `main` 的文字裡沒有 `{"key":` 形式的 JSON。result package 頁的原始 JSON 收合在 `<details>` 裡，打開才看得到。

### 19. 地圖上的 hp 不低於 0

致命一擊的 event 記錄 hp −13（3 hp 吃了 16 傷害）。timeline exporter 顯示時夾到 0；地圖照同一個慣例。紀錄本身不變，result package 頁看得到 −13。

### 20. 每個 request 重讀 workspace

重新跑腳本後，畫面不用重啟 server 就會更新。workspace 最大的檔 379 KB，重讀的成本可以忽略。建立 app 時仍檢查一次 result package，讓錯誤的目錄立刻失敗。

### 21. 播放時另一個 task 讀訊息

播放中必須能收到 pause。直接 `wait_for(receive_json())` 在逾時時會取消 ASGI 的 receive；改成一個讀取 task 把訊息放進 `asyncio.Queue`，播放迴圈只在 queue 上等。取消 `queue.get()` 是安全的。

### 22. 「Best mean score」而不是「Best mean_score」

fixture 在寫程式之前凍結了 `Best mean score: support-rear`（與 `run_batch.py` 印出的一致）；第一版 briefing 印出底線版。程式照 fixture 改：指標名的底線換成空白。

### 23. PDF 的跳脫用 html.escape

reportlab 的段落是類 XML 標記，只需要跳脫 `& < >`。第一版用 `xml.sax.saxutils.escape`，被 bandit 標為低風險（它只檢查 import）；改用 `html.escape(text, quote=False)`。

### 24. 「What happened」每 tick 一行

每 tick 列出動作的種類與次數（「4 attacks; 2 misses」）與誰被誰摧毀。逐句的版本在 Timeline 頁；briefing 要的是一頁看得完。

### 25. 手機寬度不得水平捲動

截圖檢查時發現手機寬度下 report 頁有 602 px 寬：hash 這類無法斷行的長字串。全站加 `overflow-wrap: anywhere`、卡片的值也可斷行、比較圖的長標籤截斷。e2e 加一條：八個頁面在 390 px 寬度下都不超出。

### 26. runtime_version 升為 0.11.0

依 ADR 008 的慣例調升。

### 27. websockets 是宣告的相依

第一次推送後，CI 的 ui job 在 Replay 頁失敗：Next 按鈕一直是 disabled，因為 WebSocket 從未連上。uvicorn 本身不實作 WebSocket，要有 websockets 或 wsproto；本機剛好手動裝過 websockets，CI 沒有。uvicorn 的訊息是「No supported WebSocket library detected」。把 `websockets` 加進 dependencies 與 CI；在本機移除它可以重現同樣的失敗。

### 28. 等待逾時要接 asyncio.TimeoutError

同一次推送，Python 3.10 的 check job 失敗：`asyncio.wait_for` 逾時時拋的是 `asyncio.TimeoutError`，它要到 3.11 才是內建 `TimeoutError` 的別名，所以 3.10 上播放 replay 會直接崩潰。本機只有 3.11，看不到；用 uv 裝了 3.10 重現（舊程式在 3.10 失敗、新程式通過），整套 590 個測試在 3.10 上也都通過。程式改接 `asyncio.TimeoutError`，並加註解說明為什麼不照 ruff 的建議改回 `TimeoutError`。

## 後果

```text
好處    非技術使用者打開一個網址就能讀完一次 run、它的失敗地圖與方案比較，並帶走一份 briefing
        畫面、timeline.txt 與 briefing 永遠一致：都從同一組純函式推導
        briefing 可重現，可以放進版本控制或附在決策紀錄上
代價    多了一套 Node 工具鏈（443 MB node_modules，只在 build 時需要）
        server 只讀一個 workspace；多個 run 之間的切換、scenario 編輯不在範圍內
        測試時間由 15 秒增加到約 60 秒（reference workspace 要跑 1660 次模擬）
```
