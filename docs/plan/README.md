# 開發計劃

各 Phase 的原文規格。每一份都是**凍結紀錄**，抽自上傳的三份規劃文件，作為開設與驗收的依據 —— 系統目前的樣子請看 [`../architecture.md`](../architecture.md)。

```text
來源一    《SKYVAULT 全系統開發總計劃》            每個 Phase 的目標、功能、技術、Repo 方向、輸出、驗收
來源二    《SKYVAULT Long-Term Framework & Formal Spec》   16 條核心契約的格式，見 formal_spec.md
來源三    《SKYVAULT 各 Phase 人話版（重新排序後版本）》   開發順序與人話說明，見下表
```

原始 PDF / docx 不在 repo 裡。**這個目錄就是它們在 repo 內的正本**，之後每個 Phase 以這裡為準。

---

## 開發順序

不照 Phase 編號走。左欄是實際執行順序：

| 順序 | Phase | 名稱 | 人話 |
|---|---|---|---|
| 1 | [Phase 0](phase0_baseline.md) | 現有成果整理與技術基線固定 | 先承認 Step 1 已完成，把現在能跑的 tactical slice 保存成基線，不再亂改。 |
| 2 | [Phase 4](phase4_event_memory_replay.md) | Event Memory + Replay System v0.4 | 把「發生過什麼」完整記下來，讓人能復盤，不只是看最後誰贏。 |
| 3 | [Phase 1](phase1_contract_pack.md) | Core Contract Pack v0.1 | 先定「資料格式法律」：世界怎樣寫、scenario 怎樣寫、action/event/result 要長什麼樣。 |
| 4 | [Phase 2](phase2_world_runtime_core.md) | World Runtime Core v0.2 | 做真正的世界底盤：時間、空間、實體、資源、狀態都能存在和變化。 |
| 5 | [Phase 3](phase3_action_consequence_engine.md) | Action & Consequence Engine v0.3 | 讓 actor 做事，世界判斷能不能做，做完造成什麼後果。這是 SKYVAULT 心臟。Formal Spec 也把它定成 Action Attempt → Validation → Resolution → Consequence → World Mutation → Event Memory。 |
| 6 | [Phase 7](phase7_evaluation_engine.md) | Evaluation Engine v0.7 | 不只判斷勝負，而是評估成本、風險、時間、後勤、戰術價值、戰略價值。Spec 明確要求 Evaluation 不是 win/lose，而是多軸評估。 |
| 7 | [Phase 8](phase8_reproducibility.md) | Reproducibility + Version Control v0.8 | 讓同一個 scenario 可以重跑、對照、查原因。否則結果不可審計。 |
| 8 | [Phase 9](phase9_failure_exploration.md) | Failure Exploration Engine v0.9 | 故意把方案搞壞：斷補給、壞感測器、通訊中斷、天氣惡化，找出它怎樣死。Spec 把這列為核心能力之一。 |
| 9 | [Phase 10](phase10_batch_branch_comparison.md) | Batch Simulation + Branch Comparison v1.0 | 一次跑很多方案，比誰成本低、風險小、撐得久。 |
| 10 | [Phase 17](phase17_ui_replay_report.md) | UI / Replay / Report System v1.7 | 做人類能看的介面：時間線、地圖、replay、failure map、報告匯出。 |
| 11 | [Phase 13](phase13_military_domain_pack.md) | Military / Tactical Domain Pack v1.3 | 把戰術軍事場景正式化：小隊、地形、火力、後勤、任務、doctrine 比較。 |
| 12 | [Phase 18](phase18_data_ai_training_pipeline.md) | Data / AI / Training Pipeline v1.8 | 把模擬結果變成訓練資料，例如 state-action-outcome，給 TAC ANGEL / STARTX 用。 |
| 13 | [Phase 5](phase5_observation_contract.md) | Observation Contract v0.5 | 不同系統看到不同世界。例如 TAC ANGEL 看局部戰場，STARTX 看大局，不再全部上帝視角。 |
| 14 | [Phase 6](phase6_actor_agent_layer.md) | Actor Policy / External Agent Layer v0.6 | 把「誰來決定行動」拆出去。SKYVAULT 不自己當戰術腦，只接收 actor 的 action。 |
| 15 | [Phase 11](phase11_background_world_service.md) | Background World Service v1.1 | 把 SKYVAULT 從手動 script 變成後台服務，可 standby、跑任務、保存狀態、回傳結果。 |
| 16 | [Phase 12](phase12_external_system_interface.md) | External System Interface v1.2 | 讓 NEXUS、STARTX、TAC ANGEL、HADES、AEROGRID、SKYFOX 等系統正式接入。 |
| 17 | [Phase 14](phase14_city_governance_logistics_pack.md) | Logistics / Governance / City Domain Pack v1.4 | 做城市治理、補給、治安、停電、災害、戰後重建等世界。 |
| 18 | [Phase 15](phase15_airspace_pack.md) | Airspace / HADES / SKYFOX / AEROGRID Domain Pack v1.5 | 做空域、無人機、反無人機、防空配置測試。 |
| 19 | [Phase 16](phase16_star_guard_virtual_test.md) | Star Guard Virtual Test Support v1.6 | 讓 EXO / PAX / MSX / ERX 等裝備在造實體前先進 SKYVAULT 測物理可能性、工程可行性、戰術價值。Definition 明確列出這三重測試。 |
| 20 | [Phase 19](phase19_commercial_imperial_dual_track.md) | Commercial / Imperial Dual Track v1.9 | 做對外可賣的乾淨商業版，同時保留內部完整核心能力。 |
| 21 | [Phase 20](phase20_full_skyvault_v2.md) | Full SKYVAULT v2.0 | 所有核心、接口、多 domain、失敗探索、報告、後台服務全部整合成完整系統。 |
| 22 | [Phase 21](phase21_standalone.md) | Standalone SKYVAULT v2.1 | roadmap 之後由使用者加入：系統只靠完成的系統本身運作，不再依賴 Phase 0 的參考切片與開發用腳本。 |

## 為什麼這樣排

| 步驟 | 核心邏輯 |
|---|---|
| 1 | 先固定已完成成果 |
| 2 | 先讓人看得懂事件流程 |
| 3 | 再正式化資料格式 |
| 4 | 再擴世界核心 |
| 5 | 再強化 action / consequence |
| 6 | 再做 evaluation / failure / batch |
| 7 | 再做 UI |
| 8 | 再正式化 military domain |
| 9 | 再產出訓練資料 |
| 10 | 再接 TAC / STARTX |
| 11 | 再做後台服務與外部接口 |
| 12 | 再擴展城市、空域、星衞、商業版 |
| 13 | 最終整合 full SKYVAULT |

---

## 技術總棧建議（開發總計劃原文）

```text
Core            Python 3.11+ / Pydantic / dataclass / FastAPI / NetworkX / NumPy /
                Pandas / Polars / SQLite first / PostgreSQL later / Redis /
                Celery / RQ / Dramatiq / Docker
Simulation      Discrete Event Simulation / Agent-Based Modeling / State Machine /
                Causal Graph / Monte Carlo / Fault Injection / Sensitivity Analysis
Data            JSON / YAML / JSON Schema / Parquet / JSONL / Event Sourcing /
                Snapshot Store / Graph DB later / Object Storage later
AI / Agent      Rule-based policy first / Planning agents later /
                LLM-assisted scenario builder later / RL / multi-agent training later /
                RAG for scenario construction later
UI              React / Next.js / FastAPI backend / WebSocket / ECharts / Plotly /
                timeline viewer / map viewer / failure map viewer / report export
Infrastructure  Docker Compose / GitHub Actions / pytest / ruff / black / mypy later /
                CI smoke tests / job queue / health monitoring
```

## 一句話總結（開發總計劃原文）

> 先把世界、scenario、action、consequence、event、evaluation 做成穩定核心；再加入可重跑、失敗探索、批量比較、衝突分支、資源治理與反刷分；再變成後台服務；再接 NEXUS / STARTX / TAC ANGEL / HADES / 星衞；最後擴展成多 domain、可商業化、可訓練 AI、可審判方案、並永遠把最終決策交回 NEXUS / 陛下 / 指定權威的完整 world-environment engine。
