# Phase 21 — Standalone SKYVAULT v2.1

這份是**凍結紀錄**：roadmap 二十一個 Phase（0–20）完成之後，使用者於 2026-11-09 加入的要求，與當時一起定下的決定。
它不在上傳的開發總計劃裡；寫完不再更新。系統目前的樣子請看 [`../architecture.md`](../architecture.md)。

---

## 在路線中的位置

```text
執行順序    第 22 位（roadmap 之後）
對應 Spec   §0 硬性要求「SKYVAULT 是共同環境底座」「成熟期是 background-operated world service」；§10
```

人話：SKYVAULT 運作時只靠完成的系統本身 —— 不靠 Phase 0 的參考切片，也不靠開發時寫的腳本。

---

## 1. 使用者原文

> and also transfer from using tatictal refrence to actual skyvault systems whrere dont need to rely on te fixture or
> baseground that is set at phase 0 (ie the that refrence py should not be used for starting and the systems shouldnt be
> rely on those set up scripts, it should be and need to be rely on the finished systems itself hence all things set for
> devlopment should not be refernced when skyvault system are actually working)

## 2. 使用者的選擇（2026-11-09）

```text
引擎          改名並移除退回：SkyVaultTacticalReferenceEngine → SkyVaultEngine；沒有指定 policy、也沒有 domain 的 scenario
              不再默默用 Phase 0 的 policy
參考切片      「降為開發用」＋「完全刪除」：從系統（src、data、scripts）刪除；開發用的副本只留在 tests/；
              驗收、產品、失敗探索、batch 改用真正的 domain scenario
啟動方式      一個入口＋UI 讀服務：`skyvault` 指令啟動 world service、worker 與 UI；run / explore / batch 等經服務提交；
              UI 從 world service 的 API 讀任何 run，不再依賴 output/；現有 scripts 移到 scripts/dev/
```

## 3. 驗收

```text
src/、data/、Dockerfile、docker-compose 與使用者的指令不出現 tactical_reference，也不 import 開發用腳本
沒有指定 policy 也沒有 domain 的 scenario 被拒絕（引擎與提交都拒絕）
新目錄 pip install 之後：skyvault serve → skyvault run <domain scenario> → skyvault result → UI 看得到那個 run，
不需要執行任何 scripts/、不需要 output/
v2 驗收（skyvault acceptance）在 domain scenario 上仍 ACCEPTED：15 / 14 / 6 / 5
參考切片的回歸測試仍在 tests/ 裡釘住結果；系統的新基線（military_squad_001）的結果與 output_hash 被釘住
```
