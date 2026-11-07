# Phase 9 — Failure Exploration Engine v0.9

這份是**凍結紀錄**：從上傳的《SKYVAULT 全系統開發總計劃》抽出本 Phase 的原文規格，作為開設與驗收的依據，寫完不再更新。
系統目前的樣子請看 [`../architecture.md`](../architecture.md)；所有 Phase 的順序見 [`README.md`](README.md)。

---

## 在路線中的位置

```text
執行順序    第 8 位（共 21 個 Phase）
對應 Spec   §14 Failure Exploration Spec
```

人話：故意把方案搞壞：斷補給、壞感測器、通訊中斷、天氣惡化，找出它怎樣死。Spec 把這列為核心能力之一。

---

## 1. 目標

讓 SKYVAULT 不只是證明方案能成功，而是故意讓方案失敗，找出弱點。

Definition 中說 SKYVAULT 的根本價值，是讓帝國在現實行動前，先把決策放進虛擬世界裡死一千次。Formal Spec 也將 Failure Exploration 定義為核心能力：故意讓方案、scenario、系統、裝備與治理流程失敗，以找出現實行動前必須修正的弱點。

## 2. 要做的功能

```text
failure_variables
stress_levels: mild / moderate / severe / collapse
fault injection
branch search
sensitivity analysis
collapse sequence detection
failure map
recommended modifications
```

## 3. 初期 failure variables

```text
supply_delay
sensor_failure
communication_failure
weather_degradation
enemy_reaction_speed
equipment_overheat
civilian_pressure
resource_shortage
```

## 4. 輸出

```text
failure_map.json
collapse_sequence.json
survival_conditions.json
recommended_modifications.md
```

## 5. 驗收標準

```text
給定一個方案
SKYVAULT 能跑出它在哪裡失敗
為什麼失敗
哪個變量壓垮
哪個替代方案撐更久
現實前必須改什麼
```
