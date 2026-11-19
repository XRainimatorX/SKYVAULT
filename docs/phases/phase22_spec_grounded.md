# Phase 22 — Spec-Grounded SKYVAULT v2.2

完成報告。這份文件是 Phase 22 結束時的凍結紀錄，寫完不再更新 —— 系統目前的樣子請看 [`../architecture.md`](../architecture.md)。

**狀態：功能完成。SKYVAULT 2.0 以 Formal Spec 與 Definition 驗收：ACCEPTED。**

---

## 1. 這個階段做什麼

使用者的要求（2026-11-18）：2.0 的驗收根據《Long-Term Framework & Formal Spec》與《SKYVAULT Definition》；《全系統開發總計劃》是在這兩份之後才寫的，路徑依賴從兩份文件出發，不從總計劃出發。選擇：契約逐欄照原文、原文不寫進 repo、一個 Phase 完成。

```text
Issue      #38 Phase_22_spec_grounded_skyvault（milestone #22 Phase 22 — Spec-Grounded SKYVAULT v2.2）
開設       對照原文逐節測量（issue 第 1 節）：一致的、不一致的、Definition 與 §21 沒有的
開發       K §3.3 scenario 與 §2 world contract、compiler          9a81baa
           L §8.2 / §8.3 評估                                       fea2b32
           M §10.4 服務、§15.3 governance、§17.2 handoff、§18      51ff0ac
           N §5.2 觀察者、CYBERHOUND、§9.2、NEXUS mission、三角包   51ff0ac、ee5ac4d
           O §14.2 – §14.4 failure exploration                     dc2de35
           P Definition 的用途：危機、災害、重建、接管、星衞         bcba5c9
           Q 驗收改為 Formal Spec + Definition                     0048260
```

決定記錄於 [`../decisions/024_spec_grounded.md`](../decisions/024_spec_grounded.md)。

---

## 2. 這次執行發生了什麼

### 驗收（skyvault acceptance）

```text
Formal Spec §0       9 / 9    世界引擎、共同環境、只提供世界、跨 domain、星衞三重、外部工程仿真、後台服務、雙軌、核心輸出
契約 §2 – §18        19 / 19  原文 YAML 範例的每個欄位都在契約的 JSON Schema；§2.3 對照範例世界 urban_crisis_test_001 本身
§21 Phase A – J      10 / 10  每個 Phase 的通過標準，在同一個服務上跑
Definition Ⅰ – Ⅸ     12 / 12  三角包七步、NEXUS 判斷、四個用途群、星衞、商業前提、最終用處
回歸（Phase 20）     15 / 15、14 / 14、6 / 6、5 / 5
```

### 行為與 output_hash

```text
步驟 K（§3.3 / §2 與執行協議）    16 個 scenario 的事件與遷移前逐筆相同（只有 actor_policy 假設從世界移到 scenario）
步驟 L（§8.3 評估）              事件不變；reference 在 balanced 下 0.5045 → 0.4938（crisis_resilience 加入計分），信心 13/14
系統基線 military_urban_001/v0.2  78aa3fe5bbdf → 1f0a2ea2641a，no_winner_duration_limit、528 events（不變）
其餘                             信息環境、災害、no-fly、新的 failure variable 都是 opt-in：沒有設定時逐位元不變
```

### 新的世界與任務

```text
urban_crisis_test_001        §2.3 範例世界：district network、phase_event_hybrid（6 小時 × 56 = 14 天，結束於第 336 小時）；
                             洪水（第 12 小時，Harbor 的糧食 × 0.4、所有道路切斷 8 個 phase）、火災（第 60 小時）、
                             封路（第 24 小時起）、謠言與反制訊息；order_not_restored
city_reconstruction_001      戰後重建：電力第 1 步倒下、第 10 步恢復；工業在 3 個 seed 中 2 個於第 8 步恢復
city_takeover_branches_001   強攻 / 封鎖 / 談判 / 先恢復供應：封鎖的失敗頻率 1.0，其餘 0
CYBERHOUND（blackout 城市）   有信息環境時平均治安 -15.2；反制訊息讓最終壓力 -28.9
三角包（stand-in）            STARTX 偏好 west_axis；TAC ANGEL 的命令被拒 10 → 調整後 6
```

### 測試與閘門

```text
pytest            1788 passed（Phase 21：1578），覆蓋率 99%；Redis + PostgreSQL 服務都跑
Python 3.10 venv  1786 passed（加最後兩個反向驗證的測試之前）
跨 PYTHONHASHSEED skyvault acceptance 的 acceptance.json 在 seed 1 與 99 逐位元相同，且等於 commit 的 output/v2
ruff / black / mypy / bandit   全綠
本機 CI           check 與 ui 兩個 job 逐步跑過（CI 的步驟本身同時重新產生 output/）
反向驗證          16 個變異（§9.2 返回、rule_changes、信息模型 opt-in、步數計時、inform、compare_plans、契約逐欄、
                  封路繞行、no-fly、handoff 的決定、傳播方向、包圍的地形、tempo 保留命令、七問、stress、
                  CYBERHOUND 非城市）：14 個被抓到；包圍放到水上、tempo 覆蓋已下的命令兩個存活 → 補上測試，全部紅
```

---

## 3. 範圍內做完的事

Final Done Criteria 逐條結果貼在 issue #38。重點：

- scenario 只接受 §3.3 分組格式；世界獨立、§2.2 十三個元素必填；`compile_scenario` 實作 §4 第 2 步；result package 帶 §4.2 十四步。
- evaluation_result 的 scores 是 §8.3 的 11 個 key；§8.2 其餘的軸在 additional_axes，不能判斷的寫明原因。
- §10.4 service contract：七種 mode、十個 lifecycle 狀態都可達、九個 service actions、persistent world 重啟後恢復、Monitoring Mode。
- §5.2 九個觀察者、§9.2 九個系統的返回項目、CYBERHOUND 信息環境模型。
- §21 Phase I：NEXUS mission 與 mission-to-scenario compiler；Definition 三角包。
- §14.2 每一列有對應、§14.4 七問。
- Definition 的用途：危機（§2.3 世界、災害）、戰後重建、接管四分支、星衞「可以測什麼」。
- `skyvault acceptance` 以兩份文件逐條驗收並 ACCEPTED。

---

## 4. 這一輪發現的問題

```text
1. 全套測試測到別的副本     本機 CI 在乾淨副本裡 pip install -e，套件從此指向那個副本；之後的全套測試其實在測
                           舊的 commit。發現於一個 smoke 跑出「模型沒有作用」—— 從此 CI 之後一律重裝並印出 __file__
2. 推送前沒跑本機 CI         51ff0ac 推上去後 GitHub CI 紅：ci.yml 仍讀 NEXUS 的 briefing（已改名 scenario_report）；
                           下一次又抓到觀察者斷言仍是五個。之後每次推送前都跑過 CI 的步驟
3. phase 時鐘上的 world.tick 城市的到達、事故、謠言都比對 world.tick，而 phase_event_hybrid 的 tick 是時鐘時間（小時）：
                           一趟兩步的路「在第 8 小時到達」永遠等不到。改為以步數計時（step_of），唯讀的世界加上 phase_length
4. fratricide 是次數不是清單  §9.2 的空域項目在 fixture 的測試裡沒有走到空域路徑，第一次跑驗收才炸；補上空域的 §9.2 測試
5. 重建 scenario 第一版六步就崩  兩座變電站同時倒下、糧食又少：沒有恢復可量。先量三個 seed 再寫 spec
6. 替身的命令全部被拒         TAC ANGEL 替身不讀地形成本，兩格的移動在城市裡超出 move_range；調整改為朝同一格走一步
7. 包圍可能放到不能站的格子    encirclement 只排除有人的格子；補上地形的 move_cost null
8. 失敗地圖的 None           沒有變量壓垮方案時報告寫「Crushed first by: None」
9. 測試期間改檔              全套測試跑的時候改 src，覆蓋率把新的檔案算成 0%、子程序讀到一半的改動；之後新模組先寫在 scratchpad
```

---

## 5. 驗收怎麼確認

```text
逐欄          acceptance/spec_fields.py 是原文 YAML 範例的欄位（抽取的程式在開設時跑過一次，結果寫進檔案）；
              一個測試在 §6.2 加一個不存在的欄位，檢查就失敗
§21 與 Definition  每條都跑系統：同一個服務上的 job、world、mission、三角包、failure map、virtual test
回歸          Phase 20 的 40 條先跑，它們的 run 與 handoff 供後面的檢查讀
```

---

## 6. 已知限制

```text
信息環境、災害、重建的係數       手調的預設值；城市的醫療不會自行恢復
STARTX / TAC ANGEL 替身         驗收與三角包用的是固定規則；真正的系統以 mission 或各自的提交接入
契約逐欄比的是欄位名稱           值域與位置由各契約自己的測試把關
§19 / §20 的技術族群             graph DB、time-series DB、object storage、gRPC、HLA、RL 不在本 Phase
真實外部系統與校準               不存在；係數不是以真實資料校準
```

先前各 Phase 的其餘限制見 README 的「已知限制」。
