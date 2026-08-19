# PLAN — 开放权重模型基础设施准入控制系统

> **系统定位**：以「证据 → 门禁 → 证明」为主轴的**模型准入控制平面（Model Admission Control Plane）**。
> 把 AgentsGroup 多 Agent 团队、数据采集/分析管线、准入审批整合为闭环：
> 从开放权重模型情报采集出发，经确定性证据采集与多角色评审，产出**可审计、可验证、可持续证明**的准入清单。

---

## 0. 设计原则（Architectural Tenets）

这五条决定所有模块边界，违反任一条的实现应被拒绝。

| # | 原则 | 含义 | 反模式 |
| --- | --- | --- | --- |
| **T1** | **证据优先** | 门禁判定必须消费**机器采集的证据**，证据带来源、时间戳、采集器版本 | 让 Agent「凭知识」判断某模型许可证 |
| **T2** | **扫描器与评审员分离** | 确定性事实由 **Scanner** 产出；跨证据关联、风险叙述、补充信息由 **Agent** 产出 | 把 CVE 查询写进 Agent prompt |
| **T3** | **策略即代码** | 判定规则以声明式规则文件表达，可版本化、可回归测试、可脱离 LLM 复现 | 把「哪些许可证可用」写死在提示词里 |
| **T4** | **失败即拒绝（Fail-Closed）** | 证据缺失 / 采集失败 / 签名不可验证 → 判定**不通过**，而非「通过」或「跳过」 | 扫描超时后默认放行 |
| **T5** | **决策即证明** | 每道门禁产出 DSSE 封装的 in-toto 风格 attestation；准入条目是**签名工件**，不是数据库行 | 只在 DB 里记 `approved=true` |

> **T2 是本次重写的核心修正**。上一版把「查 CVE」「识别许可证」当成 Agent 任务，
> 导致不可复现、可幻觉、不可审计。正确切分：
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

| Gate | 名称 | 输入证据 | 判定者 | 阻断性 | 工作项 |
| --- | --- | --- | --- | --- | --- |
| **G0** | 登记与去重 | 申请表单 + 许可证知识库补全 | Policy | — | — |
| **G1** | **来源与完整性** | 签名验证、哈希清单、下载源、custody 链 | Scanner + Policy | **Blocker** | 1 |
| **G2** | **供应链与漏洞** | AI-BOM、基础镜像 CVE、序列化格式扫描 | Scanner + Policy | **Blocker** | 1 |
| **G3** | **许可证与司法辖区** | 许可证条款、AUP、出口管制、签署方状态 | Scanner + Agent(Compliance/Legal) | **Blocker** | 1 |
| **G4** | **资源与运行时适配** | 显存/存储/拓扑估算、集群调度能力画像 | Scanner + Agent(Infra) | Major | 1 + 4 |
| **G5** | **安全行为** | 红队结果、护栏覆盖、越狱率、注入抗性 | Scanner(garak) + Agent(Security) | Major | 2 |
| **G6** | **会签裁决** | 上述全部 attestation | 裁决器 + 人工会签 | — | — |

### 2.1 判定语义

每道门禁产出：`verdict ∈ {pass, fail, needs_info}` + `severity` + `evidence_refs[]`。

- 任一 Blocker `fail` → 整体 `rejected`，**不进入后续门禁**（早失败，省算力）
- 任一 `needs_info` → 整体 `need_info`，回到申请人补充
- 全部 `pass` 但存在 Major → `approved_with_conditions`，附加运行时限制写入 L3 条目 `conditions[]`

### 2.2 为什么 G1/G2 必须在 Agent 之前

Sigstore 签名验证、SHA-256 清单比对、CVE 匹配都是**确定性计算**。
LLM 参与只会引入不确定性且无法作为审计证据。Agent 从 G3 开始介入——
许可证条款解释、司法辖区风险、资源权衡本质上**需要推理与权衡**。

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
**验收**：对 3 个真实模型（permissive / conditional / restricted 各一）手工走完 G0–G6 并产出签名 attestation。

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

---

## 10. 已知风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 上游模型未签名（多数 HF 仓库现状） | G1 无法通过 → 全部拒绝 | 引入 `internal_attestation`：平台首次下载时签名并锁定 digest，记为「平台背书」而非「厂商背书」，风险降一档但不清零 |
| CVE 库对模型权重覆盖不足 | G2 假阴性 | 补充序列化格式扫描（pickle / `torch.load` 任意代码执行面）+ 基础镜像 CVE，双通道 |
| Agent 幻觉出不存在的许可证条款 | 合规误判 | 强制 `evidence_ref` + 条款原文摘录比对；无法在原文定位的结论直接作废 |
| 集群能力画像过期 | G4 误判可调度 | 画像由集群实时 API 生成，TTL 24h，过期即 `needs_info` |
| 策略规则与 Agent 意见冲突 | 裁决歧义 | 策略引擎优先级高于 Agent；Agent 只能收紧不能放宽 |
| 前沿模型资源估算失真 | G4 通过后实际无法部署 | 估算须区分权重显存 / KV-Cache / 激活峰值三项，并按并发与上下文长度参数化 |
