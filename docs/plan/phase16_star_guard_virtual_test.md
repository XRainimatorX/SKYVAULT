# Phase 16 — Star Guard Virtual Test Support v1.6

這份是**凍結紀錄**：從上傳的《SKYVAULT 全系統開發總計劃》抽出本 Phase 的原文規格，作為開設與驗收的依據，寫完不再更新。
系統目前的樣子請看 [`../architecture.md`](../architecture.md)；所有 Phase 的順序見 [`README.md`](README.md)。

---

## 在路線中的位置

```text
執行順序    第 19 位（共 21 個 Phase）
對應 Spec   §18 星衞計劃 Virtual Test Support Spec
```

人話：讓 EXO / PAX / MSX / ERX 等裝備在造實體前先進 SKYVAULT 測物理可能性、工程可行性、戰術價值。Definition 明確列出這三重測試。

---

## 1. 目標

支援 EXO / PAX / MSX / ERX / 載具在實體原型前進行 virtual test support。

Definition 明確要求三重測試：Physical Possibility → Engineering Feasibility →Tactical Usefulness，並說 SKYVAULT 不取代 CAD / CAE / FEA，而是做前期物理可能性、工程投入價值、戰術價值篩查。

## 2. 包含內容

```text
equipment_profile
mass
height
center_of_gravity
joint_load
power_requirement
heat_output
endurance
maintenance_time
supply_chain_risk
operator_fatigue
terrain_accessibility
transport_requirement
```

## 3. 技術

```text
physics-lite rule model
constraint solver
surrogate model
external simulation adapter
FMI / FMU later
```

## 4. 輸出

```text
physical_possibility_score
engineering_feasibility_score
tactical_usefulness_score
failure_points
redesign_triggers
require_external_simulation flag
```

## 5. 驗收標準

```text
輸入一個 EXO / PAX / MSX profile
SKYVAULT 能判斷大致物理是否合理
工程是否值得投入
任務中是否有價值
在哪些條件下會失敗
```
