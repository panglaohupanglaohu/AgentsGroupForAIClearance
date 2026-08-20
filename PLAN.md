# PLAN — Lenovo 可管可证的模型准入与运营控制系统

> **系统定位**：以「证据 → 门禁 → 证明 → 运营处置」为主轴的**模型准入控制平面（Model Admission Control Plane）**。
> 把 AgentsGroup 多 Agent 团队、数据采集/分析管线、准入审批与运行时处置整合为闭环：
> 目标不是过度判断“模型来自哪里”，而是确保 Lenovo 能对模型做**直接管理、直接验证、直接处置**。

---

## 0. 设计原则（Architectural Tenets）

这五条决定所有模块边界，违反任一条的实现应被拒绝。

| # | 原则 | 含义 | 反模式 |
| --- | --- | --- | --- |
| **T1** | **Lenovo 直管优先** | 准入先校验 Lenovo 可直接控制项（digest 锁定、运行时基线、kill-switch、回滚路径、责任人） | 仅凭来源/产地标签直接放行或拒绝 |
| **T2** | **扫描器与评审员分离** | 确定性事实由 **Scanner** 产出；跨证据关联、风险叙述、补充信息由 **Agent** 产出 | 把 CVE 查询写进 Agent prompt |
| **T3** | **策略即代码** | 判定规则以声明式规则文件表达，可版本化、可回归测试、可脱离 LLM 复现 | 把「哪些许可证可用」写死在提示词里 |
| **T4** | **失败即拒绝（Fail-Closed）** | 证据缺失 / 采集失败 / 控制项不可验证 → 判定**不通过**或 `needs_info`，且必须触发处置动作 | 扫描超时后默认放行 |
| **T5** | **决策与处置都要可证明** | 每道门禁产出 DSSE attestation；同时保留回滚、撤销、演练与 SLA 证据 | 只在 DB 里记 `approved=true` |

> **本次战略修正**：来源/产地是风险信号，不是单点裁决器。
> 裁决优先级必须遵循：**可控性约束 > 策略规则 > 来源信号**。
> **Scanner 产出 `finding` → Policy 产出 `verdict` → Agent 产出 `opinion`。**

---

## 1. 系统分层

```text
┌─────────────────────────────────────────────────────────────────┐
│ L5 持续验证层  Continuous Assurance                              │
│    配置漂移检测 · 许可证变更监听 · 新 CVE 重评 · 合规报告          │
├─────────────────────────────────────────────────────────────────┤
│ L4 运行时执行层  Data Plane（受控推理运行时）                     │
│    容器基线 · NetworkPolicy · SecurityContext · 资源配额 · 护栏    │
├─────────────────────────────────────────────────────────────────┤
│ L3 准入登记层  Approved Registry                                 │
│    签名准入条目 · 有效期 · 适用范围 Scope · 附加条件               │
├─────────────────────────────────────────────────────────────────┤
│ L2 门禁与裁决层  Gates & Adjudication  ← AgentsGroup 评审团队      │
│    G0..G6 六道门禁 · 策略引擎 · 会签裁决 · attestation 签发        │
├─────────────────────────────────────────────────────────────────┤
│ L1 证据层  Evidence Plane                                        │
│    Scanner 集群产出结构化 finding · 不可变证据库 · 证据溯源         │
├─────────────────────────────────────────────────────────────────┤
│ L0 情报采集层  Intelligence Intake  ← 现有 data-intelligence 管线  │
│    模型发布监听 · 许可证知识库 · Open Weights Letter · CVE/NVD 源  │
└─────────────────────────────────────────────────────────────────┘
```

**与现有系统映射**：L0 复用现有信息源采集（RSS/OPML/目录导入 + Cron 调度）；
L2 复用 AgentsGroup 团队/Agent/事件流机制；L1/L3/L4/L5 为新增。

---

## 2. 门禁模型（Gate Model）

准入不是「一条线性审批」，而是**六道带阻断级别的门禁**。前三道为硬门禁（Blocker 不可豁免）。

| Gate | 名称 | 输入证据 | 判定者 | 阻断性 | Lenovo 可直接控制点 |
| --- | --- | --- | --- | --- | --- |
| **G0** | 登记与去重 | 申请表单 + 许可证知识库补全 | Policy | — | — |
| **G1** | **制品完整性与可追踪性** | 签名验证、哈希清单、下载源、custody 链 | Scanner + Policy | **Blocker** | digest 锁定、签名可验、revision 固定 |
| **G2** | **供应链与漏洞** | AI-BOM、基础镜像 CVE、序列化格式扫描 | Scanner + Policy | **Blocker** | 漏洞阈值、序列化安全、依赖可追溯 |
| **G3** | **许可证与运营义务** | 许可证条款、AUP、出口管制、签署方状态 | Scanner + Agent(Compliance/Legal) | **Blocker** | scope/conditions 模板化、法律责任归属 |
| **G4** | **资源与运行控制** | 显存/存储/拓扑估算、集群调度能力画像 | Scanner + Agent(Infra) | Major | profile 选型、容量保护、降级策略 |
| **G5** | **安全行为与防护效果** | 红队结果、护栏覆盖、越狱率、注入抗性 | Scanner(garak) + Agent(Security) | Major | 阻断阈值、审计策略、隔离动作 |
| **G6** | **会签与上线闸门** | 上述全部 attestation + 运营信息 | 裁决器 + 人工会签 | — | owner / oncall / kill-switch / rollback / SLA |

### 2.1 判定语义

每道门禁产出：`verdict ∈ {pass, fail, needs_info}` + `severity` + `evidence_refs[]`。

- 任一 Blocker `fail` → 整体 `rejected`，**不进入后续门禁**（早失败，省算力）
- 任一 `needs_info` → 整体 `need_info`，回到申请人补充
- 全部 `pass` 但存在 Major → `approved_with_conditions`，附加运行时限制写入 L3 条目 `conditions[]`

### 2.2 为什么 G1/G2 仍是硬门禁但不等于来源决定论

Sigstore 签名验证、SHA-256 清单比对、CVE 匹配都是**确定性计算**。
LLM 参与只会引入不确定性且无法作为审计证据。Agent 从 G3 开始介入——
许可证条款解释、司法辖区风险、资源权衡本质上**需要推理与权衡**。

来源/产地信息仅作为风险分层输入：
- 可触发额外条件（例如更短复评周期、强制 restricted profile）
- 不可单独形成 `fail`，除非触发了明确策略规则（例如许可证限制或制裁命中）

### 2.3 Lenovo 直管优先裁决顺序

1. 先判可控性不变量：digest、基线、回滚、撤销、责任链是否完备
2. 再判合规规则：许可证、司法辖区、使用范围是否满足策略
3. 最后用来源信号调风险档：收紧条件，不替代门禁结论

---

## 3. 数据模型

```text
ModelApplication          申请单，状态机载体
  ├─ ModelIdentity        model_id / vendor / version / weights_uri / revision
  ├─ CustodyChain[]       origin → finetune → quantize，每步带签名与哈希
  ├─ Evidence[]           Scanner 产出的不可变 finding（append-only）
  ├─ Attestation[]        每道门禁的 DSSE 封装判定
  ├─ ReviewOpinion[]      Agent 结构化意见（必须引用 evidence_id）
  └─ Decision             会签结果 + conditions[] + scope + expires_at

ApprovedRegistryEntry     准入清单条目（L3）
  ├─ decision_ref         指向 Decision 的签名摘要
  ├─ scope                允许使用场景（internal / commercial / restricted）
  ├─ conditions[]         必须满足的运行时约束（引用 L4 基线 profile）
  ├─ runtime_profile      安全基线档位（restricted / standard / isolated）
  ├─ service_owner        服务责任人/责任团队
  ├─ security_owner       安全责任人
  ├─ rollback_runbook_ref 回滚预案引用
  ├─ kill_switch_ref      一键撤销/阻断入口引用
  ├─ admission_sla_tier   准入与应急处置 SLA 档位
  └─ reassessment_due     下次强制复评时间

ComplianceDrift           L5 检出的偏离事件（许可证变更 / 新 CVE / 配置漂移）
```

**状态机**：

```text
draft → submitted → gating(G1..G5) ─┬→ rejected（Blocker fail，终态）
                                    ├→ need_info → submitted（回环，最多 3 次）
                                    └→ adjudicating → approved / approved_with_conditions
                                                          ↓
                                              registered → (L5 持续监控)
                                                          ↓
                                        drift_detected → reassessing → revoked / renewed
```

---

## 4. Agent 团队设计（L2）

复用 AgentsGroup 团队机制，新建**准入评审团队 `model_clearance_board`**：

| Agent | 角色 | 消费证据 | 产出 | 禁止行为 |
| --- | --- | --- | --- | --- |
| `security_reviewer` | 安全评审 | G1/G2/G5 findings | 安全风险评级 + 缓解建议 | 禁止自行「回忆」CVE 编号 |
| `compliance_reviewer` | 合规评审 | G3 findings + 许可证全文 | 许可证适用性意见 + 限制条款摘录 | 禁止在证据缺失时给结论 |
| `infra_reviewer` | 基础设施评审 | G4 findings + 集群能力画像 | 资源需求评估 + 建议 runtime_profile | 禁止无视集群实际容量 |
| `legal_reviewer` | 法务评审（条件触发） | G3 + 司法辖区证据 | 法律风险意见 | 仅当 G3 标记 `legal_review_required` |
| `adjudicator` | 会签裁决 | 全部 attestation + opinion | 最终 verdict + conditions | **禁止推翻 Blocker fail** |

**强制约束（写入每个 Agent 系统提示）**：

1. 每条结论必须携带 `evidence_ref`；无引用结论视为无效并触发重跑
2. 证据不足时**必须**输出 `needs_info` 并列出缺失项，不得猜测
3. 输出必须符合固定 JSON Schema；校验失败 → 重试 → 仍失败则升级人工
4. **Agent 只能收紧，不能放宽**：可把 Policy 的 `pass` 降级为 `needs_info`，反之不可

---

## 5. 四份标准文档（工作项 1–4 交付物）

| 文档 | 工作项 | 位置 |
| --- | --- | --- |
| 模型基础设施准入检查表 | 1 | [docs/standards/model-admission-checklist.md](docs/standards/model-admission-checklist.md) |
| 模型运行时安全基线配置规范 | 2 | [docs/standards/runtime-security-baseline.md](docs/standards/runtime-security-baseline.md) |
| 模型运行时监控与审计标准 | 3 | [docs/standards/runtime-monitoring-audit.md](docs/standards/runtime-monitoring-audit.md) |
| 基础设施能力差距清单及 Phase 2 改造建议 | 4 | [docs/standards/infrastructure-gap-analysis.md](docs/standards/infrastructure-gap-analysis.md) |

---

## 6. 外部框架对齐

| 框架 | 用途 | 落点 |
| --- | --- | --- |
| **Google SAIF**（6 核心要素） | 总体安全框架 | 要素1→L4 基线；2→L5 检测响应；3→Scanner 自动化；4→统一 runtime_profile；5→复评回路；6→scope 与业务上下文绑定 |
| **NIST AI RMF** | 治理方法论 | Govern→门禁策略；Map→证据模型；Measure→评分卡；Manage→conditions 与复评 |
| **OWASP CycloneDX ML-BOM**（ECMA-424） | AI 物料清单格式 | G2 的 AI-BOM 产物格式，含 model / dataset / config 组件 |
| **Sigstore model-transparency**（OpenSSF） | 权重签名与验证 | G1 签名验证实现；DSSE + in-toto manifest；可选私有 Rekor/Fulcio |
| **OWASP LLM Top 10** | 运行时威胁分类 | G5 红队用例映射；L4 护栏配置 |
| **EU AI Act** | 监管义务判定 | G3「微调/实质修改 → 可能承担 provider 义务」触发判定 |

---

## 7. 分阶段交付

### Phase 1 — 定义标准（本阶段）

产出四份标准文档 + 策略规则文件 + 数据模型，**不追求全自动化**。
**验收**：
1. 对 3 个真实模型（permissive / conditional / restricted 各一）走完 G0–G6 并产出签名 attestation
2. 至少 1 个来源信息不完整模型在控制项完备时可 `approved_with_conditions`（restricted）
3. 完成 kill-switch 与 rollback 双演练，并产出带时间戳的处置证据

### Phase 2 — 工具化 · 自动化 · 常态化

| 工作项 | 内容 |
| --- | --- |
| **工具链建设** | Scanner 集群（签名验证、AI-BOM 生成、CVE 匹配、序列化格式扫描、资源估算）；CI/CD 安全闸门 |
| **监控平台** | 统一运行时监控面板：安全事件、性能、成本、合规态势 |
| **控制平面** | 模型 / 代理 / 工具 / 端点 / 属主 / 访问模式中央清单 |
| **自动化合规验证** | 周期性基线符合性检查 + 自动合规报告生成 |

---

## 8. 命名与词汇约束（强制）

系统中**禁止**出现：`stock` / `StockAgents` / 投资 / 股票 / 投资组合 / Portfolio（金融语义）/ 纸面成交 / 市场表现 / ticker。

| 禁用 | 替换 |
| --- | --- |
| `StockAgents` | `ModelClearance` |
| 投资引擎 | AI 模型基础设施准入过程控制 |
| 引擎装配台 | 准入控制台 |
| Portfolio / 投资组合 | Approved Registry / 准入清单 |
| 股票 / ticker | 模型 / `model_id` |
| 市场表现 | 合规态势 |
| 不构成投资建议 | 不构成法律或采购建议 |

页面：`/investment-engine.html` → **`/ai-model-entry-clearance.html`**；导航 id `investment-engine` → `model-clearance`。

---

## 9. 非目标（Explicit Non-Goals）

- **不做**模型能力基准评测平台（MMLU 等由外部评测系统提供证据，本系统只消费）
- **不做**推理服务本身（L4 只定义基线与校验，不实现 serving）
- **不替代**法务终审——`legal_reviewer` 产出风险意见，终审仍需人工签字
- **不声称**能验证训练数据来源——开放权重 ≠ 开放数据，训练数据声明一律标记 `unverifiable`
- **不以**来源国家/厂商标签做单点拒绝——必须落在可执行策略规则与控制证据上

---

## 10. 已知风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 过度依赖来源/产地标签 | 误杀可控模型或放过不可控模型 | 在策略层强制 `origin_signal_only`：仅可调风险档与条件，不可直接裁决 |
| 上游模型未签名（多数 HF 仓库现状） | G1 无法通过 → 全部拒绝 | 引入 `internal_attestation`：平台首次下载时签名并锁定 digest，记为「平台背书」而非「厂商背书」，风险降一档但不清零 |
| CVE 库对模型权重覆盖不足 | G2 假阴性 | 补充序列化格式扫描（pickle / `torch.load` 任意代码执行面）+ 基础镜像 CVE，双通道 |
| Agent 幻觉出不存在的许可证条款 | 合规误判 | 强制 `evidence_ref` + 条款原文摘录比对；无法在原文定位的结论直接作废 |
| 集群能力画像过期 | G4 误判可调度 | 画像由集群实时 API 生成，TTL 24h，过期即 `needs_info` |
| 策略规则与 Agent 意见冲突 | 裁决歧义 | 策略引擎优先级高于 Agent；Agent 只能收紧不能放宽 |
| 前沿模型资源估算失真 | G4 通过后实际无法部署 | 估算须区分权重显存 / KV-Cache / 激活峰值三项，并按并发与上下文长度参数化 |

---

## 11. 控制台与准入引擎的对接现状（P10 待收口）

> **结论先行**：后端准入引擎（L1–L5）已完成且 12 套测试全绿，但**前端控制台并没有接它**。
> 页面此前只做了「文案改名」，底层仍连着上一代的模拟引擎，因此界面看起来像旧报表。

### 11.1 已核实的断点

| # | 断点 | 证据 | 影响 |
| --- | --- | --- | --- |
| B1 | 控制台「创建/启动」调用 `/api/v1/investment-simulations/*` | `js/ai-model-entry-clearance.js` 6 处 | 走的是旧模拟引擎，不是 `GateOrchestrator` |
| B2 | 旧引擎依赖的模块**在仓库中不存在** | `orchestrator.py` `from integrations.tradingagents.graph_adapter import ...`；`src/backend/integrations/tradingagents/` 查无此目录 | 启动即 ImportError，运行链路事实上是死的 |
| B3 | 表单校验拒绝页面自己的默认值 | `engine-state.js` 要求 `^[A-Za-z0-9.]{1,12}$`，而默认值是 `meta-llama/Llama-3.1-8B-Instruct` | 点「启动」必然弹「请填写合法 Ticker」，功能不可用 |
| B4 | 表单字段仍是金融语义 | `#ticker` `#cash` `#trade_date` `#debate` `#risk` `#sector` | 标签改了、`id` 与校验语义没改，改一次错一次 |
| B5 | 门禁矩阵曾是金融维度 | `engine-judgment.js`（**本轮已修**：G1–G6 十一维 + Blocker 阻断） | 已解决，其余断点未解决 |

### 11.2 目标形态

```text
准入控制台 (ai-model-entry-clearance.html)
  └─ 表单：model_id / revision / weights_uri / as_of / 并发画像 / 评审模式
       ↓  POST /api/v1/model-clearance/applications          （已存在）
       ↓  POST /api/v1/model-clearance/applications/{id}/submit（已存在，跑 GateOrchestrator）
       ↓  GET  /api/v1/model-clearance/applications/{id}/events（已存在，门禁事件流）
  └─ 渲染：gate_verdict → 门禁矩阵 / evidence_collected → 证据流 / agent_opinion → 评审意见
  └─ 结果：registry 条目 + 责任人 / Kill-Switch / Rollback / SLA
```

**原则**：控制台不得再自造分数。矩阵每一格都必须能追到后端 `GateVerdict.failed_checks` 与 `Evidence.digest`；
拿不到证据就显示 `missing`，不得用 fixture 分数冒充已评估（T1/T4）。

### 11.3 旧模拟引擎的处置

`domain/investment_simulation/` 与 `/api/v1/investment-simulations/*` 已无可用依赖、无前端消费方（P10 切换后），
按「先断引用、再删实现」两步走，避免一次性删除掩盖仍在使用的调用点。
