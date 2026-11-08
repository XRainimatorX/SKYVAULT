# Phase 17 回顧

UI / Replay / Report System v1.7

這份文件檢討**流程**，不檢討人。所有問題都以「什麼樣的做法讓這件事得以發生」來描述 —— 目標是讓下一個階段不要重蹈，不是追究誰的責任。

寫完不再更新。

---

## 1. 摘要

Phase 17 交付了七個 view model、briefing 的三種格式、FastAPI 後端與 WebSocket replay、Next.js 的八個頁面與瀏覽器 e2e。模擬與 exporter 都沒有改。

這一輪的主題是**環境**。本機全綠、推上去兩個 CI job 紅；兩個原因都是本機比 CI 多了一樣東西（手動裝過的 websockets）或少了一個版本（只有 Python 3.11）。另外本機兩個系統套件（Pillow、cryptography）是壞的，裝了可用的版本才能跑測試 —— 這也是「本機與 CI 不同」，只是方向相反。

**核心教訓：新增一個執行環境（瀏覽器、server、另一個語言的工具鏈）時，相依要從乾淨的環境推導，不從「本機能跑」推導；支援的每個 Python 版本都要在本機跑得到。**

---

## 2. 時間軸

```text
11-08   開設前測量：workspace 19 檔、四個 exporter 可重用、Node / Python 工具鏈可裝、靜態匯出 4 秒
11-08   開設：milestone #9、issue #25（18 項決定、WebSocket 協定、每步綠燈狀態）、briefing fixture 先 commit
11-08   步驟 A：views、report、export_briefing
        —— briefing 一句話與 fixture 不同；致命一擊 hp −13；bandit 在 commit 後才跑 ——
11-08   步驟 B：service、WebSocket、serve_ui
        —— 一個變異讓測試卡住 ——
11-08   步驟 C：Next.js 八頁、e2e
        —— 截圖發現手機寬度溢出 ——
11-08   整合、推送
        —— CI：ui job（沒有 websockets）、3.10（asyncio.TimeoutError）——
```

---

## 3. 做得好的地方

### fixture 在寫程式之前凍結了 briefing 要說的話

`briefing_reference.json` 列了八節與 19 句話。第一版 briefing 有一句寫成 `Best mean_score`，測試立刻抓到。如果預期值是看了輸出才寫，這個不一致會被原封不動寫進測試。

### 畫面、timeline 與 briefing 共用同一組純函式

timeline view 直接用 `timeline.write_event` 的句子；briefing 由 views 組成。結果是三者不可能說不同的話 —— 地圖上的 hp 要不要低於 0，也是照 timeline exporter 既有的慣例決定。

### 截圖是驗證的一部分

e2e 的斷言全過，但截圖才看出手機寬度下 report 頁 602 px 寬、失敗地圖的卡片值溢出。修正後把「手機寬度不得溢出」加進 e2e，變成可重複的檢查。

### CI 失敗先重現再修

兩個 CI 失敗都在本機重現後才改：移除 websockets 看到同樣的卡住；用 uv 裝 3.10 看到舊程式失敗、新程式通過。沒有一個修正是猜的。

---

## 4. 出了什麼問題

### 問題 1：相依是從本機推導的

uvicorn 不帶 WebSocket 實作。本機在開設測量時手動裝過 websockets，之後一切正常，所以沒人注意到它沒被宣告。

### 問題 2：只有一個 Python 版本在本機

專案宣告 Python 3.10+，CI 跑 3.10 與 3.11，但本機只有 3.11。`asyncio.TimeoutError` 與 `TimeoutError` 的差別只在 3.10 出現。

### 問題 3：commit 前沒有跑完所有閘門

步驟 A 的 commit 只跑了測試，bandit 在 commit 之後才發現 `xml.sax.saxutils`。下一個 commit 修掉，但 CI 若在中間跑就會紅。

### 問題 4：WebSocket 測試沒有逾時

拿掉 `end` 訊息的變異讓測試永遠等下去。它算被抓到，但在 CI 裡會卡到工作逾時才失敗。

### 問題 5：測試預期值仍有兩處是憑印象寫的

SCENARIO_END 的句子有沒有 `- `、v0.1 探索了哪些變量 —— Phase 10 回顧改法 4 說「預期值從輸出複製」，這兩處沒照做。

---

## 5. 根本原因

### 成因 1：「開設時的測量」會污染環境

開設時為了確認工具可裝，直接在工作環境裡 pip install。測量完的套件就留在環境裡，之後的開發都建立在一個比宣告多的環境上。

### 成因 2：版本矩陣只存在 CI

本機沒有 3.10，所以「在 3.10 上能不能跑」只能等 CI 回答 —— 也就是推送之後。

### 成因 3：commit 的習慣檢查清單只有測試

ruff / black / mypy / bandit 在每步結束時跑，但「每步結束」和「commit」之間有時插了一個修正，修正之後只重跑了測試。

---

## 6. 下一階段要改的事

### 改法 1：開設時的工具測量在 scratch 環境做

用 `uv venv` 或 scratch 目錄測量可安裝性，不裝進工作環境。工作環境只裝 pyproject / CI 宣告的東西 —— 讓「本機能跑」等於「宣告的相依能跑」。

### 改法 2：本機也跑最低支援的 Python 版本

用 uv 建一個 3.10 的 venv，推送前至少跑一次完整測試。這次已經裝好，之後每個 Phase 都用。

### 改法 3：commit 前一律跑完整閘門

ruff、black、mypy、bandit、pytest 一個指令跑完，任何一個失敗就不 commit。

### 改法 4：等待外部訊息的測試要有上限

WebSocket、子行程、網路 —— 任何「等下一則訊息」的測試都要有逾時，讓變異或缺陷表現為失敗，而不是卡住。

---

## 7. 沒有結論的一項

**UI 只讀一個 workspace。**

目前 server 對應一個資料夾；要看另一個 run，就得重新跑腳本或換資料夾重啟。這對單人使用夠了，但 NEXUS 或多個使用者需要的是「列出所有 run、挑一個看、比較兩個」—— 那需要 run registry（Phase 8 已有）與後台服務（Phase 11）的 run 管理。是讓 UI 直接讀 registry，還是等 Phase 11 提供 run API，留給 Phase 11 決定。

---

## 8. 一句話

> Phase 17 讓 SKYVAULT 的結果第一次可以被不看 JSON 的人讀懂，而這一輪最值得記下的是兩個只在 CI 出現的失敗 —— 一個手動裝過的套件、一個本機沒有的 Python 版本 —— 它們說明「本機能跑」必須建立在與 CI 相同的宣告上。
