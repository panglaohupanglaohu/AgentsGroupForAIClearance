# AgentsGroup2026 — 智能体数字孪生与效能演进平台

> **一句话愿景**：找出最有效能的智能体团队。效能 = 在给定任务上「完成质量 × 成功率」相对「Token 成本」的综合性价比。

平台围绕这个目标提供两条互相咬合的核心路径：

1. **孪生演练路径（对团队做实验）** — 团队先在数字孪生沙箱里演练、经受混沌故障考验、评分对比、棘轮择优，用低成本仿真筛出最强团队构型与策略，再进入生产环境。
2. **集体智慧路径（对任务做规划）** — 议事广场（Plaza）多智能体结构化讨论「如何高质量完成任务」，形成结构化**执行计划**；计划经人类确认与修改后，通过人机协同与多团队并行执行，结果回流评估。

**两阶段经济学**：

- **Plaza 集体智慧阶段不做 Token 优化** — 讨论追求发散与方案收敛，确保计划能落地。
- **成本纪律从执行计划产生后严格执行** — 同一份计划在孪生沙箱中对「团队 × 技能 × 协作拓扑」多个候选组合反复竞标（[bidding_orchestrator.py](src/backend/sandbox/bidding_orchestrator.py)），质量达标者中 Token 效益最优者获得生产执行权。

```
                ┌── Plaza 议事：怎么干？ ──→ 执行计划 ──→ 人类确认/交互 ─┐
真实任务 ──┤                                                              ├──→ 协作执行 ──→ 效能评分
                └── 孪生演练：谁来干？ ──→ 最优团队/策略 (Ratchet 锁定) ─┘        │
   ▲                                                                             │
   └──── 技能提取(TSE)→验证→入库→路由复用 · Token 治理/门禁 ←────────────────────┘
```

---

## 快速开始

### 环境依赖

- **Node.js** ≥ 22
- **Python** ≥ 3.11

### 启动步骤

**macOS / Linux**

```bash
npm install                                   # 安装前端依赖
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"                       # 安装后端依赖
npm start                                     # 一键启动后端(8080) + 前端开发服务器(5173)
```

**Windows PowerShell**

```powershell
npm install
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
npm start
```

> [scripts/run-python.cjs](scripts/run-python.cjs) 会按 `.venv` → `venv` → 系统 Python 的优先级自动路由解释器；项目根目录还提供开箱即用的 [start.sh](start.sh)、[start.ps1](start.ps1) 与 [start.bat](start.bat)。默认入口见 [src/backend/main.py](src/backend/main.py) 与 [vite.config.mjs](vite.config.mjs)。

---

## 技术栈与项目规模

| 维度 | 指标与说明 |
| --- | --- |
| **后端架构** | 单一 FastAPI 应用（[src/backend/main.py](src/backend/main.py)，默认端口 **8080**），集成 **31 个路由域**，约 **389 个 Python 文件 / 14.4 万行代码** |
| **前端架构** | 多页面原生 ES/JS + Three.js + Taste Light 设计系统，由 Vite 构建驱动（开发端口 **5173**），共 **19 个应用与控制台页面** |
| **测试套件** | 后端单测 **105** 个（[src/backend/tests/](src/backend/tests/)）+ 根目录集成测试 **59** 个（[tests/](tests/)）+ 前端 Vitest 测试 **54** 个（[src/frontend/__tests__/](src/frontend/__tests__/)），合计 **218 个测试模块** |
| **运行依赖** | Python ≥ 3.11（`fastapi` / `uvicorn` / `pydantic` / `httpx` / `aiohttp` / `cryptography` / `edge-tts`）；Node.js ≥ 22（`vite` / `vitest` / `three` / `playwright`） |
| **神经组件** | TSE（Temporal Skill Extraction）技能萃取管线采用 Pure-NumPy 实现（TCN 时序卷积 + 5 维 Skill Query Cross-Attention），**无 GPU 依赖** |

---

## 仓库目录结构

```
src/
  backend/
    main.py              FastAPI 核心入口（鉴权 / CORS / 静态托管 / 31 个路由域注册）
    agents/
      teams/             内置团队构型（build、ai_coding、energy、cloud_ops、aws_ops、xops）
      plaza*.py          Plaza 议事引擎（engine / consensus / stream / store / routes）
      tse/               TSE 技能萃取神经管线（TCN + cross-attention + 约束解码）
      skill_*.py         技能库 / 路由 / 验证 / 演化 / 分类 / 追踪 / 发布门禁
      runtime/           tool_loop / plan_loop / state_machine（多域共享执行底座）
      evolution/         fitness / mutator / optimizer + Ratchet 棘轮状态机
      token_governance/  任务 Token 治理（prepare 管线与 9 大优化杠杆目录）
      budget/            预算门禁与额度控制
      agent_memory_*.py  拟生记忆系统（core / lifecycle / share / transfer / runtime）
      pet_ecosystem.py   仿生生态仿真（Perception → Intention → Behavior 范式）
      cost_*.py          成本度量、归因、告警与门禁（Token 北极星）
      chat_harness.py    团队对话执行 Harness（Token 治理管线挂载点）
    sandbox/             数字孪生沙箱（twin_loop / world_state / bidding_orchestrator /
                         orchestrator / eco_drill / scenario_* / trial_* / global_critic）
    domain/              AI 模型准入与情报采集域（直管优先矩阵、Kill-Switch、存证审计）
    tests/               后端测试套件（105 个测试模块）
  frontend/
    *.html               19 个前端页面（见下表）
    js/  css/            页面业务逻辑、3D 视效与 Taste Light 样式表
    __tests__/           前端 Vitest 测试套件（54 个测试模块）
config/                  系统配置（[settings.json](config/settings.json)、[model_pool.json](config/model_pool.json)、[users.json](config/users.json)、准入策略等）
storage/                 运行时状态持久化（技能库、记忆、棘轮账本、团队配置等）
docs/                    Plan/Todos 设计与演进文档（签名规范见 [docs/SIGNING_RULE.md](docs/SIGNING_RULE.md)）
scripts/                 运维、评测与启动脚本（含解释器自动路由 [run-python.cjs](scripts/run-python.cjs)）
docker/  k8s/            容器化与云原生部署配置（含 K8s 成本标签 Mutating Webhook）
tests/                   根目录全局端到端与集成测试（59 个测试模块）
```

---

## 九大核心业务域

后端严格按域解耦，每个域在「议事 → 演练 → 萃取 → 进化 → 经济性执行」闭环中承担明确职责：

| 域 | 业务价值与定位 | 关键模块 | 核心 API 路径 |
| --- | --- | --- | --- |
| **智能体团队 Team** | 组织与执行载体：定义团队编制、成员 Agent、通道拓扑与执行工作流，经 `chat_harness` + `runtime/tool_loop` 闭环执行 | [agents/api.py](src/backend/agents/api.py)、[agent_team_api.py](src/backend/agent_team_api.py)、[chat_harness.py](src/backend/agents/chat_harness.py)、[employee_routes.py](src/backend/agents/employee_routes.py) | `/api/v1/agent-teams`<br>`/api/v1/agent-config`<br>`/api/v1/agent-employee` |
| **议事广场 Plaza** | 集体智慧中枢：多 Agent 结构化辩论产出可落地的执行计划，支持多团队并行派发与 SSE 实时推流 | [plaza_engine.py](src/backend/agents/plaza_engine.py)、[plaza_consensus.py](src/backend/agents/plaza_consensus.py)、[plaza_routes.py](src/backend/agents/plaza_routes.py)、[tts_routes.py](src/backend/agents/tts_routes.py) | `/api/v1/agent-config/plaza`<br>`/api/v1/tts` |
| **孪生沙箱 Twin** | 核心差异化试验田：`world_state` 状态快照，`twin_loop` 派生 What-if 推演副本，注入混沌故障，评估多分支策略收益；计划经竞标编排分配执行权 | [sandbox/twin_loop.py](src/backend/sandbox/twin_loop.py)、[orchestrator.py](src/backend/sandbox/orchestrator.py)、[bidding_orchestrator.py](src/backend/sandbox/bidding_orchestrator.py)、[trial_api.py](src/backend/sandbox/trial_api.py)、[scenario_api.py](src/backend/sandbox/scenario_api.py) | `/api/v1/sandbox`<br>`/api/v1/twin-trials`<br>`/api/v1/scenarios` |
| **技能萃取 TSE** | 知识沉淀与复用（省 Token 的根本手段）：TCN + Cross-Attention 定位技能时刻 → 约束解码 → 沙箱 A/B 验证 → BM25 双阶段路由 | [agents/tse/](src/backend/agents/tse/)、[skill_router.py](src/backend/agents/skill_router.py)、[skill_verifier.py](src/backend/agents/skill_verifier.py)、[skill_evolver.py](src/backend/agents/skill_evolver.py) | `/api/v1/teams/{id}/skill-extract/*`<br>`/api/v1/skill-router`<br>`/api/v1/extraction`<br>`/api/v1/skill-classification` |
| **拟生记忆 Memory** | 动态记忆系统：感觉痕迹 / 情节 / 语义核 / 工作台四层分级，情绪电荷场（Affect）驱动巩固与遗忘，支持 ACL 共享与传承迁移 | [agent_memory_core.py](src/backend/agents/agent_memory_core.py)、[agent_memory_lifecycle.py](src/backend/agents/agent_memory_lifecycle.py)、[agent_memory_share.py](src/backend/agents/agent_memory_share.py)、[agent_memory_transfer.py](src/backend/agents/agent_memory_transfer.py) | `/api/v1/agent-config/.../memory-core`<br>`/api/v1/agent-memory` |
| **Token 治理 Cost** | 北极星度量与执行纪律：`prepare_request` 管线（简化/压缩/缓存/路由/预算）+ 细粒度 Token 归因与门禁 | [token_governance/](src/backend/agents/token_governance/)、[token_governance_routes.py](src/backend/agents/token_governance_routes.py)、[cost_gate_routes.py](src/backend/agents/cost_gate_routes.py)、[cost_routes.py](src/backend/agents/cost_routes.py) | `/api/v1/cost`<br>`/api/v1/cost/token-governance/*`<br>`/api/v1/cost-gate`<br>`/api/v1/token-factory` |
| **生态演化 Evolution** | 演化马达：物竞天择（以生存时长 $T_i$ 为唯一客观适应度）+ Ratchet 棘轮（新策略经孪生证明优于基线方可晋升锁定，绝不倒退） | [eco_drill.py](src/backend/sandbox/eco_drill.py)、[pet_ecosystem.py](src/backend/agents/pet_ecosystem.py)、[evolution/](src/backend/agents/evolution/)、[ratchet_ledger.py](src/backend/agents/ratchet_ledger.py) | `/api/v1/pet-ecosystem`<br>`/api/v1/eco-runtime`<br>`/api/v1/twin-evolution`<br>`/api/v1/ratchet`<br>`/api/v1/sustainability` |
| **模型准入 Clearance** | 生产级模型准入治理：直管优先矩阵（Owner、Kill-Switch、Rollback、SLA、可验签证据存证），联动开放权重情报采集 | [domain/api_routes.py](src/backend/domain/api_routes.py)、[model_clearance_service.py](src/backend/domain/model_clearance_service.py)、[information_sources.py](src/backend/domain/information_sources.py) | `/api/v1/information-sources`<br>`/api/v1/model-clearance` |
| **运行时基础设施 Runtime** | 执行基石：多轮 Tool-Loop、状态机、多模型网关适配、Kubernetes 成本标签注入 Webhook 与自检服务 | [runtime/](src/backend/agents/runtime/)、[operation_api.py](src/backend/agents/operation_api.py)、[k8s_webhook_handler.py](src/backend/agents/k8s_webhook_handler.py)、[startup_check.py](src/backend/startup_check.py) | `/api/v1/operations`<br>`/api/v1/evidence-runs`<br>`/api/v1/webhook/mutate-cost-labels`<br>`/api/v1/startup-check` |

---

## 前端页面全景图（19 个功能页面）

| 页面文件 | 界面定位与核心功能 | 所属业务域 |
| --- | --- | --- |
| [index.html](src/frontend/index.html) | 站点统一门户与各系统功能导航总入口 | 全局导航 |
| [agent-team-config.html](src/frontend/agent-team-config.html) | 智能体团队工作台：向导式创建 Agent、编排组织架构、配置模型连接与通道关系 | 智能体团队 |
| [agent-team-config-new.html](src/frontend/agent-team-config-new.html) | 团队配置实验版：支持新版团队元数据与关系调试 | 智能体团队 |
| [tasks.html](src/frontend/tasks.html) | 任务调度中心：业务任务下发、单条/批量/分步执行、多智能体协同流水线与状态监控 | 智能体团队 / 运行 |
| [plaza.html](src/frontend/plaza.html) | 议事广场：3D 圆桌多智能体结构化辩论、实时 SSE 推流、多语言切换与执行计划派发 | 议事广场 |
| [Agent-digital-twin.html](src/frontend/Agent-digital-twin.html) | 试炼导演台：场景选择、故障注入、分支推演、增益评估；`?office3d=1` 开启 3D 生态仿真 | 孪生沙箱 / 生态 |
| [sandbox-twin.html](src/frontend/sandbox-twin.html) | SECS 演练总台：沙箱环境状态控制、混沌推演与智能体实时交互 | 孪生沙箱 |
| [digital-twin-cli.html](src/frontend/digital-twin-cli.html) | 命令行式孪生控制台：高密度流式推演日志与指令调试 | 孪生沙箱 |
| [skill-extract.html](src/frontend/skill-extract.html) | 技能萃取中心：TSE 萃取草稿审核、分类划分（特质/储备/公共）、演化与验证 | 技能萃取 |
| [extraction-pipeline.html](src/frontend/extraction-pipeline.html) | 萃取流水线视图：端到端转录、注意力定位、解码与入库的流水线状态 | 技能萃取 |
| [agent-memory.html](src/frontend/agent-memory.html) | 智能体拟生记忆总枢：四层架构视图、情绪电荷监控、ACL 共享矩阵与继承迁移 | 拟生记忆 |
| [cost-dashboard.html](src/frontend/cost-dashboard.html) | Token 成本治理工作台：Prepare 九大杠杆调节、Token 消耗归因、节省统计与预算门禁 | Token 治理 |
| [datacenter-ratchet-evolution.html](src/frontend/datacenter-ratchet-evolution.html) | 数据中心场景棘轮演进：展示数据中心故障与调优场景下的棘轮演进轨迹 | 生态演化 |
| [pet-config.html](src/frontend/pet-config.html) | 仿生生态参数实验室：调节感知-意图-行为范式参数与生境客观压力 | 生态演化 |
| [system-evolution.html](src/frontend/system-evolution.html) | 系统演进看板：代际演化追踪、适应度曲线与 Ratchet 锁定记录 | 生态演化 |
| [data-intelligence.html](src/frontend/data-intelligence.html) | 数据采集与分析：信息来源配置、健康检查、AI 60 秒情报与世界趋势动态渲染 | 模型准入 / 情报 |
| [ai-model-entry-clearance.html](src/frontend/ai-model-entry-clearance.html) | AI 模型准入控制台：模型准入申请、证据采集器、Kill-Switch 与审计报告 | 模型准入 / 治理 |
| [open-weights-models.html](src/frontend/open-weights-models.html) | 开放权重模型情报中心：开源模型库浏览、许可证合规评估与准入治理联动 | 模型准入 / 情报 |
| [login.html](src/frontend/login.html) | 统一用户登录与身份鉴权入口 | 基础设施 |

---

## 质量验证与测试

```bash
npm run lint           # Python compileall 对后端进行编译检查
npm run typecheck      # 类型与编译检查
npm run build          # Vite 生产级静态打包

npm test               # 全部 Python 测试（根目录 + 后端单元测试）
npm run test:backend   # 仅后端测试（src/backend/tests/）
npm run test:root      # 仅根目录集成测试（tests/）
npm run test:frontend  # 前端 Vitest 测试（src/frontend/__tests__/）

node scripts/check-docs-signoff.cjs --strict   # 校验 docs/ 文档签名规范
```

当前仓库的验证基线与已知问题详见 [docs/VALIDATION.md](docs/VALIDATION.md)；优化演进路线详见 [docs/OPTIMIZATION_TODOS_2026H2.md](docs/OPTIMIZATION_TODOS_2026H2.md)。

---

## 核心机制与架构亮点

### 1. 孪生推演与闭环反馈（TwinLoop）

- 实现于 [src/backend/sandbox/twin_loop.py](src/backend/sandbox/twin_loop.py)。
- 执行闭环：`snapshot_world` → `spawn_twins` → `run_simulation` → `evaluate_outcomes` → `inject_best_strategy`。
- 支持混沌故障注入与多策略分支并行对抗，胜出后将最优策略与技能熟练度回灌至物理团队。

### 2. 物竞天择与生态生境（EcoDrill）

- 实现于 [src/backend/sandbox/eco_drill.py](src/backend/sandbox/eco_drill.py) 与 [pet_ecosystem.py](src/backend/agents/pet_ecosystem.py)。
- **单一客观适应度**：以「生存时长 $T_i$」为唯一适应度标准，拒绝人工主观打分。
- **生境压力控制**：11 个环境加压客观旋钮（性选择强度、负频率依赖、上位效应、生命衰老速率等），自然筛选最抗压、最契合当前任务的技能基因。

### 3. TSE 神经技能萃取与生命周期路由（SkillRouter）

- 实现于 [src/backend/agents/tse/](src/backend/agents/tse/) 与 [skill_router.py](src/backend/agents/skill_router.py)。
- **无 GPU 依赖的神经萃取**：TCN 时序卷积提取对话流上下文表征，结合 5 维 Skill Query Cross-Attention 定位技能片段，约束 JSON 解码生成结构化 Skill。
- **双阶段生命周期路由**：BM25 / TF-IDF 词法检索 + 技能生命周期乘数动态加权（已验证技能权重上调、草稿降级技能权重下调），向 Agent 系统提示词注入 Top-K 技能。

### 4. 任务 Token 全流程治理与 Prepare 管线

- 实现于 [token_governance/](src/backend/agents/token_governance/) 与 [chat_harness.py](src/backend/agents/chat_harness.py)。
- **Token 为唯一北极星**：以 Token 消耗与净节省量作为唯一成本衡量标准。
- **Prepare 优化管线**：

  $$\text{Input} \xrightarrow{\text{simplify}} \xrightarrow{\text{ponytail/caveman}} \xrightarrow{\text{rtk\_tool}} \xrightarrow{\text{compress}} \xrightarrow{\text{progressive\_mem}} \xrightarrow{\text{codegraph}} \xrightarrow{\text{cache}} \xrightarrow{\text{skill}} \xrightarrow{\text{cost\_tier+model}} \xrightarrow{\text{budget}} \text{Execute}$$

- 集成工具输出去噪（RTK）、渐进式对话折叠、本地代码图谱切片、分级语义缓存与硬预算门禁。

### 5. 拟生记忆架构与情绪电荷场（Bio-mimetic Memory）

- 实现于 [agent_memory_core.py](src/backend/agents/agent_memory_core.py) 与 [agent_memory_lifecycle.py](src/backend/agents/agent_memory_lifecycle.py)。
- **四层分级存储**：
  1. *感觉痕迹（Sensory Traces）*：近轮多模态/工具交互原始日志。
  2. *情节记忆（Episodic Memory）*：关键任务成功/失败场景事件流。
  3. *语义核（Semantic Core）*：经反思与巩固提炼出的规则性知识。
  4. *工作台记忆（Working Memory）*：当前正在执行的任务上下文。
- **情绪电荷场（Affect Field）**：任务成败转化为正负电荷强度，随时间呈半衰期衰减，作为环境选择压驱动记忆的自主巩固与遗忘。支持基于 ACL 的跨智能体共享与传承封存。

### 6. 不退化演进承诺（Ratchet Ledger）

- 实现于 [ratchet_ledger.py](src/backend/agents/ratchet_ledger.py) 与 [evolution/](src/backend/agents/evolution/)。
- 保证演化**只进不退**：任何新的智能体策略、提示词变异或技能版本，必须在孪生沙箱中经受基准测试验证且净增益超过门禁阈值，才被允许写入棘轮账本并升级代际。

### 7. 模型准入治理（Model Clearance）

- 实现于 [model_clearance_service.py](src/backend/domain/model_clearance_service.py) 与 [api_routes.py](src/backend/domain/api_routes.py)。
- 「可管理、可验证」准入原则：审核责任主体（Owner）、一键熔断（Kill-Switch）、快速回滚（Rollback）、SLA 承诺及可验签处置证据链，将模型来源转化为风险加权信号。

---

## 核心设计文档导航

| 领域 / 规划 | 权威设计文档 | 核心内容说明 |
| --- | --- | --- |
| **文档总则与索引** | [docs/README.md](docs/README.md) | 规范文档入口、可信度规则与体系说明 |
| **测试与基线验证** | [docs/VALIDATION.md](docs/VALIDATION.md) | 仓库验证状态、全量测试基线与已知问题清单 |
| **2026 下半年优化规划** | [docs/OPTIMIZATION_PLAN_2026H2.md](docs/OPTIMIZATION_PLAN_2026H2.md) | 平台最新架构演进、孪生验证与 Token 最优路径目标 |
| **执行任务清单 (Todos)** | [docs/OPTIMIZATION_TODOS_2026H2.md](docs/OPTIMIZATION_TODOS_2026H2.md) | 分层分工的实施清单与推进状态 |
| **任务 Token 治理体系** | [docs/任务Token治理plan.md](docs/任务Token治理plan.md) | Prepare 请求预处理管线与 9 大治理杠杆详细设计 |
| **智能体拟生记忆系统** | [docs/拟生记忆架构plan.md](docs/拟生记忆架构plan.md) | 四层记忆与情绪电荷场理论及 API 设计 |
| **物竞天择与 Skill 遗传** | [docs/物竞天择任务闭环与Skill遗传plan.md](docs/物竞天择任务闭环与Skill遗传plan.md) | 任务契约生境、11 个加压旋钮与遗传演化数学模型 |
| **宠物生态与仿生范式** | [docs/宠物团队生态仿真plan.md](docs/宠物团队生态仿真plan.md) | Perception-Intention-Behavior 仿生架构与猫鼠 3D 办公室仿真 |
| **仓库阶段性重构路线** | [docs/全仓库分阶段重构路线.md](docs/全仓库分阶段重构路线.md) | 模块解耦、废弃路由收口与工程治理路线图 |
| **文档签名制度** | [docs/SIGNING_RULE.md](docs/SIGNING_RULE.md) | docs/ 下设计与计划文件的签名防伪规范 |

---

## 部署与生产运维

- **容器化部署**：标准 [Dockerfile](Dockerfile) 及 [docker/](docker/) 镜像构建（含沙箱镜像 [scripts/build_sandbox_image.sh](scripts/build_sandbox_image.sh)）。
- **Kubernetes 云原生编排**：配置位于 [k8s/](k8s/)，内置自动注入成本追踪标签的 Mutating Webhook。
- **链路追踪与可观测性**：可选 OpenTelemetry 分布式链路追踪（`pip install -e ".[otel]"` 安装）。
- **模型凭据管理**：团队模型 `api_key` 支持 `env:VARIABLE_NAME` 环境变量安全引用；可用 [setup_keys.ps1](scripts/setup_keys.ps1) / [setup_keys.sh](scripts/setup_keys.sh) 交互式配置密钥。
