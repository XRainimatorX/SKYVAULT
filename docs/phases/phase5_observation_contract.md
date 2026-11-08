# Phase 5 — Observation Contract v0.5

完成報告。這份文件是 Phase 5 結束時的凍結紀錄，寫完不再更新 —— 系統目前的樣子請看 [`../architecture.md`](../architecture.md)。

**狀態：功能完成，沒有已記錄未修的缺陷。**

---

## 1. 這個階段做什麼

Phase 5 開始前，SKYVAULT 是上帝視角：每個 policy 拿到整個 world，外部的 TAC ANGEL 範例看得到每一個單位。

目標是開發計劃的原文：「同一個 world state，TAC ANGEL 和 STARTX 看到的 observation 不一樣；hidden state 不會暴露給不該看到的 actor；observation 有 confidence / delay / uncertainty。」規格依據是 [`../plan/phase5_observation_contract.md`](../plan/phase5_observation_contract.md) 與 Formal Spec §5。

```text
Issue      #28 Phase_5_observation_contract（milestone #12 Phase 5 — Observation Contract）
開設       reference 與軍事 run 的可見度測量；fixture 先 commit：data/observers/*.json（五個 profile）
步驟 A     observer_profile、observation 契約；profiles、sensing
步驟 B     observe（五種 view、fog、stale、delay、partial）、history
步驟 C     engine 的 observation 路徑、TAC ANGEL 範例、scripts/observe_run.py、CI
```

十六項決定與開發中的五項記錄於 [`../decisions/014_observation_contract.md`](../decisions/014_observation_contract.md)。

---

## 2. 這次執行發生了什麼

### 模擬不變

```text
Result          RED_survived
Events          97
reference trace 不變；output_hash 63090026… 不變
```

### reference run 的 observation（RED，red_001）

| tick | TAC ANGEL（local） | STARTX（aggregate，延遲 1） | AEROGRID 覆蓋 |
|---|---|---|---|
| 0–1 | 看不到敵人、hidden、confidence 0 | 同（顯示 tick 0） | 0.48 → 0.56 |
| 2 | 三個敵人 visible、confidence 0.5 | 顯示 tick 1：仍看不到 | 0.64 |
| 4 | confidence 0.87；blue_003 in_range、blue_002 can_close | 顯示 tick 3 | 1.0 |
| 5 | blue_003 hp_band critical | 己方 hp 比例 0.82 | 1.0 |
| 6 | blue_003 destroyed（殘骸在視野內） | 趨勢：己方 hp −0.18、敵人接觸 +3 | 0.9（red_003 陣亡） |
| 10 | 三個都 destroyed | | 0.9 |

### 軍事 run（TAC ANGEL 的 local view，每 tick 的 visible / stale / hidden）

```text
squad      tick 0–1 看得到 2 個；tick 2–3 退出視野 → stale 1–2 個；tick 4–6 四個全看得到；tick 7–9 再失去兩個
urban      全程有 hidden；stale 最多 3 個（建築的 concealment 0.5）
mountain   tick 0–1 看不到；之後全看得到
junction   tick 0–2 看不到；之後大多看得到 2–3 個
```

### 只看 observation 的 TAC ANGEL 範例

```text
squad        BLUE_survived / 198 events（範例是兩方共用的 policy）
urban        RED_survived / 249 events
reference    no_winner_duration_limit / 61 events —— 兩方開場都在感測外，範例不探索，就一直不動
```

### 驗收四條

| # | 開發計劃原文 | 如何證明 |
|---|---|---|
| 1–2 | 同一個 world state，TAC ANGEL 和 STARTX 看到的 observation 不一樣 | 同一份歷史、同一個 tick：visible_world_state 不同；STARTX 延遲一 tick、沒有任何位置或敵方 id（測試 + CI 逐 tick） |
| 3 | hidden state 不會暴露給不該看到的 actor | 在 urban 的每個 tick、四種有霧的 view：看不到的敵人 id 不出現在 observation 任何地方；engine 內部每一次呼叫都對照它給的歷史檢查；hidden_state 只有 exists / reason |
| 4 | observation 有 confidence / delay / uncertainty | reference 與三個軍事 scenario、五個 observer 的每一份 observation：confidence_level、delay_ticks、stale_after、source_quality、observed_at，並通過契約 |

---

## 3. 交付了什麼

```text
src/skyvault/contracts/observation.py   ObserverProfile、Observation（第 17、18 份契約）
src/skyvault/schemas/                   observer_profile、observation 的 JSON Schema（共 18 份）
src/skyvault/observation/
  profiles.py      load_observer_profile、OBSERVERS、OBSERVER_DIR
  sensing.py       visible_contacts、grid_distance（純函式）
  observe.py       observe、五種 view（純函式）
  history.py       history_from_package、context_for、concealment_for、available_actions、observations_for_run
src/skyvault/engine.py          observing policy：只給 observation；engine.observed 每 tick 的單位
src/skyvault/policies.py        ObservingPolicy、AnyPolicy
src/skyvault/domains/military/pack.py   concealment、mission_goal
examples/tac_angel_policy.py    只看 observation
data/observers/*.json           五個 profile（開設時 commit）
scripts/observe_run.py          → output/observations/<observer>.json
ci.yml                          Observation contract 步驟（reference 與 urban）
skyvault.__version__            0.14.0
```

---

## 4. 這一輪發現的問題

### 範例的「打得到」方向弄反了

第一版的 TAC ANGEL 範例用 known_risks 裡的 in_range 決定開火。但 known_risks 是「打得到我的敵人」，開火要看的是「我打得到的敵人」。範例在每個 scenario 都跑得完，所以這不會讓任何東西失敗 —— 是重讀範例時看到的。修正：己方單位在 observation 裡帶 capabilities（ADR 014 第 18 點）。

### 同一個 .py 被載入兩次

新測試與 Phase 13 的測試都 `import_policy_module("examples/tac_angel_policy.py")`。檔案路徑載入每次都產生新的 factory，第二次註冊就撞名。單獨跑任一個檔案都綠，全套才紅。測試改成「沒註冊才載入」。

### 兩個變異存活、一個不會結束

```text
ticks_to_strike 的 ceil 換成 floor   存活：測試的每個案例都剛好整除 → 加一個 3 格 / 每 tick 2 格的敵人
engine 不記 tick 0                  存活：一致性測試只比對 engine 有記的 tick → 改為比對 tick 集合與內容
缺口計數不標記已走過的格子           不會結束：測試卡住直到被系統終止 —— 抓得到，但不是以「紅」的方式
```

### 我自己的預期值算錯兩次

threat view 的同距離（4 與 4）用 id 決勝，我預期了另一個；5×5 地圖中央 2 格的感測覆蓋全部 25 格，我寫了 21。兩次都是先跑程式、對照規則確認程式正確，再改測試。

---

## 5. 品質狀態

| 項目 | 結果 |
|---|---|
| pytest | 793 passed（Phase 18 為 718） |
| Python 3.10 venv | 793 passed |
| 全專案覆蓋率 | 99% |
| `observation/` 覆蓋率 | 100% |
| ruff / black / mypy / bandit | 通過（mypy 102 個檔案） |
| 測試讀 `output/` | 0 處 |
| exporter 程式碼變動 | 0 行 |

### 測試分布

```text
tests/observation/test_observation.py   75   五個 profile 與壞 profile；感測（範圍、capability、concealment、
                                             confidence、殘骸、三種距離）；驗收 1–4；delay、stale、partial、
                                             五種 view 的精確內容；契約拒絕七種壞 observation；歷史與 context；
                                             engine 的 observation 路徑（不給 world、不給看不到的敵人、action id、
                                             None、歷史一致、world policy 不記歷史）；範例；分層；腳本跨 hash seed
tests/contracts                         +2   匯出的契約清單與 schema 檔
既有測試                                718   未改
```

### 反向驗證過的測試

```text
concealment 拿掉 / 軍事 pack 的 concealment 回 0     → 紅
confidence 取最低 / 陣亡單位仍能感測                   → 紅
hidden 永遠 False / delay 被忽略                       → 紅
stale 不衰減 / 殘骸被記成 stale / stale 蓋掉 visible    → 紅
banded 時給出 hp / 敵方帶 capabilities                  → 紅
aggregate 給出 known_entities / 趨勢窗口固定從 0 開始   → 紅
can_close 拿掉 / ticks_to_strike 用 floor              → 紅（第二次）
engine 不走 observation 路徑 / 不記 tick 0 / 不記 tick 結束 → 紅（tick 0 第二次）
歷史缺 tick 時不沿用前一個                              → 紅
缺口計數不標記已走過的格子                              → 不會結束
```

---

## 6. 已知限制

| 項目 | 留待 | 原因 |
|---|---|---|
| 軍事 baseline policy 用自己的感測 | Phase 6 | 每個單位自己看；觀測層是整個陣營共享 |
| 訓練資料的 observation 不是觀測層產生 | Phase 6 / 12 | full_state 與 military_sensor 保留 |
| 只支援 grid | 對應的 engine 出現時 | tactical engine 本身只接受 grid |
| 敵方射程與移速被當成已知 | 有需要時 | known_risks 與 ticks_to_strike 需要它 |
| resources_visible 在 run 之後是終局的帳 | — | result package 沒有每 tick 的資源帳 |
| TAC ANGEL 範例不探索 | 不改 | 範例只示範介面；reference 上兩方不動是霧的結果 |

---

## 7. 驗證

```bash
python3 scripts/run_tactical_reference.py    # RED_survived / 97；output 63090026e137
python3 scripts/observe_run.py               # 五個 observer × 11 份；TAC ANGEL 2 份有 hidden
python3 -m pytest tests/ -q                  # 793 passed
```

---

## 8. 一句話總結

> Phase 5 讓 SKYVAULT 不再是上帝視角：同一場 run，TAC ANGEL 在開場兩個 tick 什麼都看不到、STARTX 永遠慢一拍且看不到任何位置、HADES 算出敵人幾 tick 後打得到我們 —— 而只看 observation 的 policy 根本拿不到 world。
