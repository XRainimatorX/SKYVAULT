# 005 — World Runtime 與 schema 0.2

狀態：已採納
日期：2026-11-08
階段：Phase 2 — World Runtime Core v0.2

## 背景

開發計劃 Phase 2 要求：建立 world instance、entity registry、多種時間與空間模型、資源變動、event sourcing 與 snapshot。技術欄點名 networkx（graph space），儲存寫明「in-memory first，SQLite / PostgreSQL later」。

ADR 004 承諾：World Contract 的 entity_model、environment_state、resource_state、rule_set 在 Phase 2 落地時改為必填並調升 `schema_version`。

Formal Spec §2.3 的範例與這些要求有幾處對不上。issue #19 第 6 節在寫程式之前列出了八項（Phase 1 回顧改法 3），這份 ADR 記錄那八項的決定，以及開發中多做的五項。

**總原則照舊：文件有寫就照字面；文件沒寫，選正式化現有行為、改動最小的做法。** tactical reference 的模擬行為不變。

## 決定

### 1. 位置可以是格子或節點 id

```text
grid             [x, y]
graph / network  非空字串的節點 id
```

契約新增 `Location = Position | NonEmptyStr`，`EntityRecord.position` 與 `EventAffected.locations` 都改用它。程式內 `Entity.position` 是 `tuple[int, int] | str | None`。

`entity_from_record()` 只把 JSON list 轉成 tuple，字串原樣保留。過去的寫法若對字串呼叫 `list()` 會得到 `["d", "e", "p", "o", "t"]`，`Entity._location_snapshot()` 也已避開這個陷阱。

### 2. 空間型別只接受 grid / graph / network

Spec §2.3 的範例寫 `type: "district_network"`。那是 domain 名稱，不是空間的數學結構。**0.2 只接受三個結構名稱**，`district_network` 這種 domain 名稱留給 Phase 14 的 domain pack 自己對應。

封閉成 `Literal` 的好處：拼錯的型別在載入時就被拒，不會建出一個什麼都沒有的空間。

### 3. phase_length 是整數

Spec 範例寫 `phase_length: "6_hours"`。字串要解析單位，而且「6_hours」與「6 hours」誰合法沒有定義。**0.2 用整數 `phase_length`（時間單位數）加 optional 的 `time_unit`。**

`PhaseClock.advance()` 每次前進 `phase_length` 個單位：`phase_length: 6, time_unit: "hours"` 讓時間走 0 → 6 → 12，`clock.phase` 是已經過的 phase 數。時間保持在基本單位，所以不同 phase 的事件仍可直接比較先後。

### 4. 時間型別只接受 tick / phase / event_driven

Spec 範例有 `phase_event_hybrid`。目前沒有任何 Phase 需要它，**0.2 不提供**，需要它的 Phase 再加並調升版本。

### 5. 資源是「名稱 → 數量」，不得為負

Spec 只列了資源種類，沒有給格式。**`resource_state` 是 `dict[str, float]`，每個數量 ≥ 0。**

`ResourceState.change()` 扣到負數時 raise，**不夾成 0**。夾住會讓一個行動消耗了根本不存在的補給，而且沒人知道。事前檢查夠不夠是 Phase 3 action 層的工作；這裡是最後一道防線。

### 6. 世界快照增加 resources 與 space.type

event sourcing 要能驗證重建出來的資源，所以 `WorldState.snapshot()` 增加 `resources`；`space` 改由 `Space.describe()` 產生，帶 `type`，讀快照的人才知道 `width` / `nodes` 該怎麼解讀。`WorldSnapshot` 契約把 `resources` 列為必填。

### 7. event sourcing 以套用 after_state 為法

現有的 event 存的是**快照，不是差量**：entity 事件的 `after_state` 是那個 entity 事後的完整快照。所以重建不需要為每種事件寫還原邏輯：

```text
after_state 有 entity_id     取代該 entity
RESOURCE_CHANGED             after_state {resource_id, amount} 設定存量
其他                          不套用（SCENARIO_END 的 after_state 是整個世界的摘要，不是一個變動）
```

`rebuild_world(start_state, event_memory, at_time=None)` 是純函式，只 import 標準函式庫。它只套用 `start_state` 的 tick **之後**的事件，所以從 SnapshotStore 的任一快照起算，與從 tick 0 起算結果相同。`at_time=None` 代表重建到最後一個事件。

套用 after_state 是冪等的：重放一個起始快照已包含的事件不會出錯，跳過它們只是省時間。這一點由反向驗證發現（見完成報告第 5 節）。

### 8. schema_version 升為 0.2，0.1 檔案被拒

照 ADR 004 的承諾，四個欄位改為必填（允許 `{}`）。reference scenario 與所有 fixture 一併遷移。scenario 契約的 `schema_version` 是 `Literal["0.2"]`，**0.1 檔案直接被拒，不做自動升級** —— 自動升級會讓人以為舊檔仍被支援。遷移只需兩步，寫在 `docs/spec/contracts.md` 第 3 節。

### 9. `EntityRegistry.get()` 維持 Mapping 語意（偏離 issue #19 Frozen Interface）

issue #19 凍結的介面寫 `EntityRegistry.add / get / active`，第 7 節要求「get 找不到 raise KeyError」。

`EntityRegistry` 繼承 `collections.abc.Mapping`，讓所有把 `world.entities` 當 dict 用的既有程式碼不用改。Mapping 的 `get()` 規定找不到回傳 `None`（或預設值）—— 覆寫成 raise 會讓 `registry.get(x, default)` 這種標準寫法行為反常。

**決定：找不到要 raise 的版本叫 `require()`，`get()` 維持 Mapping 語意。** `WorldState.get_entity()` 呼叫 `require()`，所以「錯的 id 當場炸掉」的既有不變量不變。

`SnapshotStore.record()` 原本寫成 `record(snapshot)`，整合時發現與凍結介面 `record(time, snapshot)` 不符，已改成凍結的簽名。

### 10. 新增 ENTITY_STATE_CHANGED

issue 只要求登記 `RESOURCE_CHANGED`。驗收 4「可以更新 state」需要一個不屬於 tactics 的通用入口，所以 `WorldState.update_entity_state()` 記錄 `ENTITY_STATE_CHANGED`，前後都是 entity 完整快照 —— 與 MOVE、ATTACK 同形，event sourcing 不需要特例。

tactical engine 仍記錄自己的 MOVE / ATTACK，沒有改走這個方法：改了會改變事件型別，違反「模擬行為不變」。統一改世界的路徑是 Phase 3 的工作。

### 11. 位置合法性在契約與 create_world 各查一次

```text
Scenario 契約       grid entity 必須是界內的 [x, y]；graph / network entity 必須是已知節點
create_world()      再用建好的 Space.is_inside() 查一次
```

契約先擋，錯誤訊息帶欄位路徑；`create_world()` 再查，是因為它可能被直接呼叫（測試、之後的 domain pack），而且只有建好的空間能權威地回答「這個位置存在嗎」。

### 12. tactical engine 維持 grid + tick 專用

`create_world()` 能建任一種世界，但 tactical policy 在格子間一步一步走。給它 graph 或 phase clock，它不會報錯，只會跑出沒意義的結果。**`engine.build_world()` 對 grid + tick 以外的世界直接 raise。** policy 的型別檢查也加了一行：遇到節點 id 就不移動。

### 13. networkx 是第三個執行時期相依；快照只存記憶體

```text
networkx>=3        開發計劃 Phase 2 技術欄點名；graph / network 的最短路
types-networkx     mypy 用的型別 stub（dev）
```

宣告在 `pyproject.toml`，CI 安裝清單同步更新。

SnapshotStore 只存記憶體（文件寫明 in-memory first）。engine 用 `SNAPSHOT_INTERVAL = 5`：這個值沒有文件依據，選它只因為 10 tick 的 reference run 會存下 0、5、10 三份，足以測試「從中途快照重建」。SQLite / PostgreSQL 記為已知限制。

## 後果

```text
好處    世界由契約建立；三種空間、三種時間在同一套積木上
        任一時刻可由 event memory 重建，CI 每次驗「重建 == final_world_state」
        資源變動第一次填進 affected.resources
代價    所有 0.1 scenario 檔必須遷移（目前只有 repo 內的一份與 fixture）
        改世界的路徑有兩條（tactical 的 MOVE / ATTACK 與 runtime 的方法），Phase 3 收斂
```
