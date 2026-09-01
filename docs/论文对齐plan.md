<!-- docs-signoff: author="GitHub Copilot" kind="llm" doc="plan" ts="2026-08-28T00:00:00Z" -->

# 论文《Agent skill evolution under ecological selection》对齐 Plan

> 目标：把论文声明的 24 项机制与仓库实现逐条对齐，补齐**完全缺失的 7 项**、修正**部分实现的 8 项**，使「变异 → 预选 → 环境选择 → 保留继承」四阶段链路在代码中真实闭合、可审计、可复现实验数据。

---

## 1. 复查结论：论文声明 vs 代码现状

图例：✅ 已实现 · ⚠️ 部分实现/口径不符 · ❌ 完全缺失

### 1.1 变异端（Section 4：Plaza + DART-Net/TSE）

| # | 论文机制 | 代码位置 | 状态 | 差距说明 |
| --- | --- | --- | --- | --- |
| 1 | ORID 四阶段议程 O→R→I→D | [src/backend/agents/plaza_engine.py](src/backend/agents/plaza_engine.py) `_run_orid_phases` | ✅ | 四层已跑通 |
| 2 | 五类仪式信号 SUPPLEMENT/CHALLENGE/AGREE/COURT/DIGRESS | [src/backend/agents/plaza_engine.py](src/backend/agents/plaza_engine.py) `RitualSignal` | ✅ | 枚举齐全 |
| 3 | 五指共识 Eq.(5)：$\rho_k,\mu_k,cons_g^k,strong_g^k$ | [src/backend/agents/plaza_consensus.py](src/backend/agents/plaza_consensus.py) | ⚠️ | 需核对是否输出 $\rho/\mu$ 双阈值与「min>1」阻断位 |
| 4 | 12-Niche 三环拓扑（内/中/外环） | [src/backend/agents/plaza.py](src/backend/agents/plaza.py) `NicheRole` | ⚠️ | 只有平铺角色枚举，**无内/中/外环分层与知识功能覆盖度** |
| 5 | CHALLENGE 路由 $\Gamma_k$ 回退到目标 ORID 阶段 Eq.(3)(4) | — | ❌ | **完全缺失**：质疑不会把议程打回 O/R/I 阶段 |
| 6 | DART-Net 四阶段命名架构 | [src/backend/agents/tse/](src/backend/agents/tse/) | ⚠️ | 实现存在但**无 DART-Net 命名/装配入口**，论文与代码术语不一致 |
| 7 | TCN + 字段查询注意力 + 约束解码 | [src/backend/agents/tse/encoder.py](src/backend/agents/tse/encoder.py)、`decoder.py` | ✅ | BLAKE2b 确定性编码已实现 |

### 1.2 预选端（Section 5：六门 + 版本竞争）

| # | 论文机制 | 代码位置 | 状态 | 差距说明 |
| --- | --- | --- | --- | --- |
| 8 | 六道门禁 $G_s,G_e,G_t,G_x,G_a,G_r$ 与 Eq.(13) 三段式 | [src/backend/agents/skill_verifier.py](src/backend/agents/skill_verifier.py)、[src/backend/agents/skill_publish_gate.py](src/backend/agents/skill_publish_gate.py) | ⚠️ | 检查项散落在 `_semantic_checks`，**没有统一的六门对象与 $P_i=G_sG_eG_t$ / $R_i=G_xG_a$ / $L_i=P_iR_iG_r$ 聚合** |
| 9 | 溯源保真门 $G_e$（evidence_spans 与原始发言核对） | — | ❌ | **完全缺失** |
| 10 | 分层裁决 Eq.(14)(15)：$(b_m,r_m,E_m)$ 与 `prio` = reject ≻ revise ≻ pass | — | ❌ | **完全缺失**：无三态裁决与理由/证据三元组 |
| 11 | 版本竞争 Eq.(18)(19)(20)：配对试验、Student-t 单侧 LCB、$\delta_{min}$ | — | ❌ | **完全缺失**（全仓无 incumbent/challenger/LCB 任何实现） |
| 12 | 任务界定适应度 Eq.(17)：$F_i=w^\top x_i$ 六因子归一化 | [src/backend/agents/evolution/fitness.py](src/backend/agents/evolution/fitness.py) | ⚠️ | 现为 LLM-as-Judge 打分，**不是论文的六因子加权向量**（且论文明确禁止人工评分口径） |
| 13 | 生命周期六态 draft/revision/ready/published/degraded/deprecated | [src/backend/agents/models.py](src/backend/agents/models.py) `SkillLifecycleStage` | ⚠️ | 现为 draft/team_local/published/verified/solidified/degraded，**缺 revision / ready / deprecated** |
| 14 | 三周期「2-of-3 多数」去抖 | [src/backend/agents/skill_classifier.py](src/backend/agents/skill_classifier.py) `classify_with_history` | ⚠️ | 现为**连续 streak 计数**，非论文的最近三周期多数表决 |
| 15 | SkillRouter 召回：BM25 + TF-IDF + 字符 n-gram + 同义扩展 | [src/backend/agents/skill_router.py](src/backend/agents/skill_router.py) | ⚠️ | BM25/TF-IDF 已有，**字符 n-gram 与同义词扩展待补** |
| 16 | 路由状态硬过滤（生产只选 published） | [src/backend/agents/skill_router.py](src/backend/agents/skill_router.py) | ⚠️ | 现为 lifecycle **乘数加权**，非论文的**硬过滤**；degraded 应排除出生产 |

### 1.3 环境选择端（Section 5.7 + 7.10）

| # | 论文机制 | 代码位置 | 状态 | 差距说明 |
| --- | --- | --- | --- | --- |
| 17 | 资源丰度 / 捕食压力 / 生态位容量 | [src/backend/sandbox/eco_drill.py](src/backend/sandbox/eco_drill.py) | ✅ | 三要素齐备 |
| 18 | 生存时长为唯一适应度 | [src/backend/tests/test_eco_drill_engine.py](src/backend/tests/test_eco_drill_engine.py) | ✅ | 已有回归测试 |
| 19 | 差异化留存证据回流到下一轮变异/版本竞争 | — | ❌ | **完全缺失**：eco 结果不进 Plaza 下一轮议题，也不进版本竞争 |

### 1.4 保留继承端（Section 6：四层记忆 + SWEI）

| # | 论文机制 | 代码位置 | 状态 | 差距说明 |
| --- | --- | --- | --- | --- |
| 20 | 四层记忆 $(E_m,P_m,I_m,A_m)$ | [src/backend/agents/agent_memory_core.py](src/backend/agents/agent_memory_core.py) | ✅ | 事件/感知/意图/风险倾向齐备 |
| 21 | 风险倾向半衰期衰减 $a\cdot2^{-\Delta t/T_{1/2}}$ | [src/backend/agents/agent_memory_core.py](src/backend/agents/agent_memory_core.py) | ✅ | 72h 半衰期已实现 |
| 22 | SWEI 四阶段 + 事务回滚 | [src/backend/agents/agent_memory_migration.py](src/backend/agents/agent_memory_migration.py) | ✅ | Seal/Will/Export/Import + 快照回滚齐备 |
| 23 | 导入门 Eq.(25)：$g_{imp}=\bigwedge_{v\in V_{imp}}g_v$ 五道具名门 | [src/backend/agents/agent_memory_migration.py](src/backend/agents/agent_memory_migration.py) `validate_export_v2` | ⚠️ | 校验存在但**未拆成 scope/schema/integrity/provenance/conflict 五道具名门并逐门产出证据** |
| 24 | 污染筛查（恶意记录拦截，recall/precision，实验 7.14） | — | ❌ | **完全缺失**：无任何污染/恶意记录检测代码 |

### 1.5 缺口总览

- **完全缺失（7 项）**：#5 CHALLENGE 路由、#9 溯源门、#10 分层裁决、#11 版本竞争 LCB、#19 生态证据回流、#24 污染筛查，以及 #12 论文口径适应度。
- **部分实现（8 项）**：#3 共识公式、#4 三环拓扑、#6 DART-Net 命名、#13 生命周期六态、#14 去抖口径、#15 召回通道、#16 状态硬过滤、#23 导入五门。

---

## 2. 分期规划

### P0 — 论文核心声明补全（缺失即等于论文不可复现）
1. **六门统一裁决引擎**（#8 #9 #10）：新建 `skill_gates.py`，产出 $(b_m,r_m,E_m)$ 与 `prio` 聚合。
2. **版本竞争 LCB 引擎**（#11）：新建 `version_competition.py`，实现配对试验 + Student-t 单侧下界 + 硬约束 $C_i,H_i$。
3. **任务界定适应度**（#12）：新建 `task_bounded_fitness.py`，六因子归一化加权，权重随评估配置落盘。
4. **污染筛查**（#24）：新建 `memory_contamination.py`，接入 SWEI Import 前置。

### P1 — 口径修正（实现存在但与论文不符）
5. **生命周期六态**（#13）+ **2-of-3 去抖**（#14）。
6. **路由状态硬过滤 + 字符 n-gram + 同义扩展**（#15 #16）。
7. **导入五道具名门**（#23）。

### P2 — 链路闭合与术语统一
8. **CHALLENGE 议程路由**（#5）。
9. **生态证据回流**（#19）。
10. **DART-Net 命名装配 + 12-Niche 三环**（#6 #4）+ **共识公式核对**（#3）。

---

## 3. 验收标准

| 阶段 | 验收 |
| --- | --- |
| P0 | `pytest -k "gates or competition or fitness or contamination"` 全绿；六门对任一候选返回完整 `(decision, reason, evidence)`；LCB 在 $\Delta F=0$ 时判定 reject |
| P1 | 生命周期六态枚举与状态机测试全绿；生产路由查询返回结果中 `lifecycle_stage` 恒为 `published` |
| P2 | 一次 Plaza 讨论中 CHALLENGE 能把 `current_phase` 打回目标阶段；eco drill 结束后产出的证据出现在下一次讨论的开场上下文 |

详细可执行任务与逐函数伪代码见 [docs/论文对齐todos.md](docs/论文对齐todos.md)。
