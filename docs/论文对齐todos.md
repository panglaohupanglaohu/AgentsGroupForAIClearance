<!-- docs-signoff: author="GitHub Copilot" kind="llm" doc="todos" ts="2026-08-28T04:00:00Z" -->

# 论文对齐 TODOS（全量已完成 · 100% 验证）

> 依据：[docs/论文对齐plan.md](docs/论文对齐plan.md) 24 项论文机制对比缺口。
> 状态：P0-1 至 P2-10 全部 10 项任务均已落地，50 项单元与集成测试全部通过。

---

## P0-1 · 六门统一裁决引擎 ✅ 已完成
- **实现文件**：[src/backend/agents/skill_gates.py](src/backend/agents/skill_gates.py)
- **接线**：[src/backend/agents/skill_verifier.py](src/backend/agents/skill_verifier.py)
- **测试**：[src/backend/tests/test_skill_gates.py](src/backend/tests/test_skill_gates.py)（10 项测试全部通过）
- **依据**：论文 Eq.(13) $P_i=G_s G_e G_t, R_i=G_x G_a, L_i=P_i R_i G_r$；Eq.(14) $\gamma_m(c_i)=(b_m, r_m, E_m)$；Eq.(15) $V_i=prio(b_1..b_6)$。

---

## P0-2 · 版本竞争 + Student-t 下置信界 ✅ 已完成
- **实现文件**：[src/backend/agents/version_competition.py](src/backend/agents/version_competition.py)
- **测试**：[src/backend/tests/test_version_competition.py](src/backend/tests/test_version_competition.py)（5 项测试全部通过）
- **依据**：论文 Eq.(18) $\Delta f_{i,t}=f(c_i;x_t)-f(v_s^i;x_t)$；Eq.(19) $LCB_{1-\alpha}=\overline{\Delta F_i}-t_{1-\alpha,N-1}\frac{s_{\Delta,i}}{\sqrt N}$；Eq.(20) $G_r=\mathbb{1}[LCB\ge\delta_{min}]\cdot C_i\cdot H_i$。Cornish-Fisher 展开实现零 scipy 依赖。

---

## P0-3 · 任务界定适应度（六因子） ✅ 已完成
- **实现文件**：[src/backend/agents/task_bounded_fitness.py](src/backend/agents/task_bounded_fitness.py)
- **测试**：[src/backend/tests/test_task_bounded_fitness.py](src/backend/tests/test_task_bounded_fitness.py)（3 项测试全部通过）
- **依据**：论文 Eq.(16) $\xi_{i,t}=(y,r,l,e,\iota,f,v)$；Eq.(17) $F_i(D)=w^\top x_i, \mathbf{1}^\top w=1$ 六因子归一化与评估配置指纹落盘。

---

## P0-4 · 记忆污染筛查 ✅ 已完成
- **实现文件**：[src/backend/agents/memory_contamination.py](src/backend/agents/memory_contamination.py)
- **接线**：[src/backend/agents/agent_memory_migration.py](src/backend/agents/agent_memory_migration.py)
- **测试**：[src/backend/tests/test_memory_contamination.py](src/backend/tests/test_memory_contamination.py)（2 项测试全部通过）
- **依据**：论文 Section 7.14 恶意记录筛查规则（Recall=100%, 宁误标不漏放）。

---

## P1-5 · 生命周期六态 + 2-of-3 多数去抖 ✅ 已完成
- **修改文件**：[src/backend/agents/models.py](src/backend/agents/models.py)（补齐 REVISION, READY, DEPRECATED 及合法迁移表）、[src/backend/agents/skill_classifier.py](src/backend/agents/skill_classifier.py)（2-of-3 多数去抖与安全违规旁路）
- **测试**：[src/backend/tests/test_lifecycle_v2.py](src/backend/tests/test_lifecycle_v2.py)（3 项测试全部通过）
- **依据**：论文 Section 5.6 生命周期模型与状态跃迁去抖算法。

---

## P1-6 · 路由状态硬过滤 + 字符 n-gram + 同义扩展 ✅ 已完成
- **修改文件**：[src/backend/agents/skill_router.py](src/backend/agents/skill_router.py)（增加 `production_only` 硬过滤、字符 n-gram Jaccard 计算与 `state_filter` 日志字段）
- **测试**：[src/backend/tests/test_skill_router_paper_alignment.py](src/backend/tests/test_skill_router_paper_alignment.py)（3 项测试全部通过）
- **依据**：论文 Section 5.6 生产路由只选 published 硬过滤，以及多通道召回设计。

---

## P1-7 · SWEI 导入五道具名门 ✅ 已完成
- **修改文件**：[src/backend/agents/agent_memory_migration.py](src/backend/agents/agent_memory_migration.py)（实现 `evaluate_import_gates`，支持 scope, schema, integrity, provenance, conflict）
- **测试**：[src/backend/tests/test_swei_import_gates.py](src/backend/tests/test_swei_import_gates.py)（2 项测试全部通过）
- **依据**：论文 Eq.(25) $g_{imp}=\bigwedge_{v\in V_{imp}}g_v$ 五道具名门逐门产出证据。

---

## P2-8 · CHALLENGE 议程路由 ✅ 已完成
- **实现文件**：[src/backend/agents/plaza_challenge_routing.py](src/backend/agents/plaza_challenge_routing.py)
- **接线**：[src/backend/agents/plaza_engine.py](src/backend/agents/plaza_engine.py)
- **测试**：[src/backend/tests/test_paper_p2_routing_feedback.py](src/backend/tests/test_paper_p2_routing_feedback.py)（8 项 P2-8 测试全部通过）
- **依据**：论文 Eq.(3)(4) $\omega_{k,t+1}=\Phi(\omega_{k,t},\sigma_{k,t};\Gamma_k)$ CHALLENGE 按 Niche 环回退 ORID 阶段，双重防死循环。

---

## P2-9 · 生态证据回流 ✅ 已完成
- **实现文件**：[src/backend/sandbox/eco_feedback.py](src/backend/sandbox/eco_feedback.py)
- **接线**：[src/backend/sandbox/eco_drill.py](src/backend/sandbox/eco_drill.py)、[src/backend/agents/plaza_engine.py](src/backend/agents/plaza_engine.py)
- **测试**：[src/backend/tests/test_paper_p2_routing_feedback.py](src/backend/tests/test_paper_p2_routing_feedback.py)（9 项 P2-9 测试全部通过）
- **依据**：论文 Section 5.7 差异化留存证据回流至下一轮变异与版本竞争。

---

## P2-10 · DART-Net 命名装配 + 12-Niche 三环 + 共识公式核对 ✅ 已完成
- **实现文件**：[src/backend/agents/tse/dartnet.py](src/backend/agents/tse/dartnet.py)
- **修改文件**：[src/backend/agents/plaza.py](src/backend/agents/plaza.py)（12-Niche 三环与 $C_{role}$ 覆盖度指标）、[src/backend/agents/plaza_consensus.py](src/backend/agents/plaza_consensus.py)（Eq.(5) $\rho_k, \mu_k$ 双阈值与强共识判定）
- **测试**：[src/backend/tests/test_dartnet_and_niche.py](src/backend/tests/test_dartnet_and_niche.py)（5 项测试全部通过）
- **依据**：论文 Section 4.2、Section 4.4、Eq.(5)、Eq.(8)。

---

## 验收汇总

| 任务 | 模块 | 测试文件 | 测试用例数 | 状态 |
| --- | --- | --- | --- | --- |
| P0-1 | `skill_gates.py` | `test_skill_gates.py` | 10 | ✅ PASS |
| P0-2 | `version_competition.py` | `test_version_competition.py` | 5 | ✅ PASS |
| P0-3 | `task_bounded_fitness.py` | `test_task_bounded_fitness.py` | 3 | ✅ PASS |
| P0-4 | `memory_contamination.py` | `test_memory_contamination.py` | 2 | ✅ PASS |
| P1-5 | `models.py` / `skill_classifier.py` | `test_lifecycle_v2.py` | 3 | ✅ PASS |
| P1-6 | `skill_router.py` | `test_skill_router_paper_alignment.py` | 3 | ✅ PASS |
| P1-7 | `agent_memory_migration.py` | `test_swei_import_gates.py` | 2 | ✅ PASS |
| P2-8 | `plaza_challenge_routing.py` | `test_paper_p2_routing_feedback.py` | 8 | ✅ PASS |
| P2-9 | `eco_feedback.py` | `test_paper_p2_routing_feedback.py` | 9 | ✅ PASS |
| P2-10 | `dartnet.py` / `plaza.py` / `plaza_consensus.py` | `test_dartnet_and_niche.py` | 5 | ✅ PASS |
| **总计** | **全套 10 项论文机制** | **9 个测试套件** | **50** | **100% 绿** |
