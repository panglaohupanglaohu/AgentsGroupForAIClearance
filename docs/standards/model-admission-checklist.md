# 标准 A — 模型基础设施准入检查表

> **适用范围**：所有拟在内部部署的开放权重（open-weight）模型，含微调与量化衍生版本。
> **判定语义**：`Blocker` 不可豁免；`Major` 可豁免但须写入 `conditions[]` 并经会签；`Minor` 记录即可。
> **Fail-Closed**：任何检查项因采集失败/超时/证据缺失而无结果，一律判 `fail`，不得默认放行。

**检查项编号规则**：`<Gate>-<维度>-<序号>`，例：`G1-PROV-03`。

---

## 维度 1：来源可追溯（Provenance & Chain of Custody）— Gate G1

**核心问题**：模型从哪里来？能否加密验证其完整性未被篡改？

原则：每个部署的模型都应有**可验证的链式 custody**，从源仓库到微调 / 量化步骤都有加密签名。

| ID | 检查项 | 证据来源 | 判定规则 | 级别 | 自动化 |
| --- | --- | --- | --- | --- | --- |
| `G1-PROV-01` | 源仓库可信性 | 下载 URL + 仓库归属 | 必须为官方组织命名空间（如 HF `meta-llama/*`）；个人 fork 判 `fail` | Blocker | 全自动 |
| `G1-PROV-02` | 版本锁定 | commit SHA / revision | 必须锁定不可变 revision；使用 `main` 等可变引用判 `fail` | Blocker | 全自动 |
| `G1-PROV-03` | 权重文件哈希清单 | SHA-256 逐文件摘要 | 生成完整 manifest（file path, digest）；与下载物比对一致 | Blocker | 全自动 |
| `G1-PROV-04` | 厂商加密签名 | Sigstore bundle / GPG | 存在且验签通过 → `pass`；不存在 → 触发 `G1-PROV-05` | Major | 全自动 |
| `G1-PROV-05` | 平台内部背书签名 | 平台 Sigstore 签名 | 上游无签名时，平台首次下载后自行签名并锁定 digest，标记 `endorsement=platform` | Blocker | 全自动 |
| `G1-PROV-06` | 透明日志可查 | Rekor inclusion proof | 使用 Sigstore 时必须存在 inclusion proof | Major | 全自动 |
| `G1-PROV-07` | custody 链完整性 | CustodyChain[] | 每个变换步骤（finetune / quantize / merge）必须有输入 digest、输出 digest、执行者、时间戳 | Blocker | 半自动 |
| `G1-PROV-08` | 衍生版本溯源 | 父模型引用 | 微调/量化版本必须能追溯到已准入或同批送审的基座模型 | Blocker | 全自动 |
| `G1-PROV-09` | 训练数据来源声明 | 模型卡 | 记录厂商声明，**一律标记 `unverifiable`**（开放权重 ≠ 开放数据），不作为通过依据 | Minor | 全自动 |
| `G1-PROV-10` | 传输通道完整性 | 下载日志 | 必须 HTTPS + 证书校验；重定向需再校验目标 | Blocker | 全自动 |

**实现参考**：Sigstore `model-transparency`（OpenSSF）
`model_signing sign|verify`，产出 DSSE 封装的 in-toto statement，subjects 为 `(file path, digest)` 对，
predicate type `https://model_signing/signature/v1.0`；支持 Sigstore / 公钥 / 证书 / PKCS#11（HSM）四种方式；
企业可部署私有 Rekor / Fulcio 并通过 `--trust-config` 指向。

---

## 维度 2：依赖清单（AI Bill of Materials）— Gate G2

**核心问题**：模型依赖哪些基础镜像、库文件？有哪些已知漏洞？

原则：建立 **AI 物料清单（AI-BOM）**，格式采用 OWASP CycloneDX ML-BOM（ECMA-424）。

| ID | 检查项 | 证据来源 | 判定规则 | 级别 | 自动化 |
| --- | --- | --- | --- | --- | --- |
| `G2-BOM-01` | AI-BOM 生成 | CycloneDX ML-BOM | 必须产出含 model / dataset / config 组件的 BOM 文件 | Blocker | 全自动 |
| `G2-BOM-02` | 序列化格式安全 | 文件格式扫描 | `.safetensors` → `pass`；`.bin` / `.pt` / pickle → `fail`（任意代码执行面） | Blocker | 全自动 |
| `G2-BOM-03` | 权重文件恶意载荷扫描 | ModelScan 类工具 | 检出不安全序列化载荷即 `fail` | Blocker | 全自动 |
| `G2-BOM-04` | 推理框架依赖 CVE | SBOM + NVD/OSV | 存在 Critical 未修复 CVE → `fail`；High → `Major` | Blocker | 全自动 |
| `G2-BOM-05` | 基础镜像 CVE | 镜像扫描 | 同上；镜像必须 pin **digest** 而非可变 tag | Blocker | 全自动 |
| `G2-BOM-06` | 依赖许可证传染性 | SBOM 许可证字段 | 存在 copyleft 传染风险 → 转 G3 复核 | Major | 全自动 |
| `G2-BOM-07` | 远程代码信任 | `trust_remote_code` | 模型需要 `trust_remote_code=True` → `Major`，必须人工审阅自定义代码 | Major | 全自动 |
| `G2-BOM-08` | 分词器/配置文件完整性 | 哈希比对 | tokenizer、config 等随附文件纳入 manifest | Major | 全自动 |
| `G2-BOM-09` | BOM 时效性 | 生成时间戳 | BOM 超过 30 天 → 复评时强制重新生成 | Minor | 全自动 |

---

## 维度 3：许可证合规（License & Jurisdiction）— Gate G3

**核心问题**：许可证是否允许在内部 / 商业场景使用？来源司法辖区是否带来管制风险？

> 许可证从宽松到「带使用量上限或可接受使用条款（AUP）的修改条款」差异极大；
> 来源同样重要——受出口管制或采购限制辖区的模型，无论技术指标多好，都可能不适用于特定客户或受监管工作负载。

| ID | 检查项 | 证据来源 | 判定规则 | 级别 | 自动化 |
| --- | --- | --- | --- | --- | --- |
| `G3-LIC-01` | 许可证识别 | 许可证知识库 + 仓库 LICENSE | 必须定位到许可证**原文**；无法定位 → `needs_info` | Blocker | 全自动 |
| `G3-LIC-02` | 许可证分类 | 策略规则表 | `commercial_ok` / `conditional` / `restricted`；`restricted` → `fail` | Blocker | 全自动 |
| `G3-LIC-03` | 商用条款 | 许可证原文 | 是否允许商用；是否有 MAU / 收入上限（如部分社区许可证） | Blocker | 半自动 |
| `G3-LIC-04` | 可接受使用政策（AUP） | AUP 原文 | 摘录禁止用途清单，与拟定 scope 比对 | Blocker | Agent |
| `G3-LIC-05` | 再分发与衍生条款 | 许可证原文 | 微调产物是否须继承许可证 / 标注来源 | Major | Agent |
| `G3-LIC-06` | 归属与标注义务 | 许可证原文 | 是否要求保留 NOTICE、标注 "Built with X" | Major | Agent |
| `G3-JUR-01` | 开发商注册地 | 厂商工商信息 | 映射为风险等级（高 / 中 / 低），依内部管制清单 | Blocker | 半自动 |
| `G3-JUR-02` | 出口管制 / 采购限制 | 管制清单比对 | 命中限制清单 → `fail` 或强制 `legal_review_required` | Blocker | 半自动 |
| `G3-JUR-03` | Open Weights Letter 签署方状态 | 签署方名单 | 已签署 / 未签署，作为风险修正因子（非单独阻断项） | Minor | 全自动 |
| `G3-REG-01` | EU AI Act 义务判定 | 使用方式声明 | 若将进行微调或实质性修改 GPAI 模型 → 可能承担 **provider 义务** → `legal_review_required` | Major | Agent |
| `G3-REG-02` | 高风险用途识别 | scope 声明 | 拟用于自动化决策等高风险场景 → 提升审查等级 | Major | Agent |

---

## 维度 4：资源需求（Capacity & Runtime Fit）— Gate G4

**核心问题**：需要多少 GPU 显存、存储？现有集群调度能力是否支撑？

> 量化能把中等规模模型（约 20–70B）压到单卡或双卡可跑；但前沿开放权重模型完全是另一回事——
> 例如 4-bit 下仍需约 400GB 内存量级的模型，必须规划多卡乃至多节点服务与相应预算。
> **估算必须分解为三项**：权重显存 / KV-Cache / 激活峰值，并按并发数与上下文长度参数化。

| ID | 检查项 | 证据来源 | 判定规则 | 级别 | 自动化 |
| --- | --- | --- | --- | --- | --- |
| `G4-CAP-01` | 权重显存估算 | 参数量 × 量化位宽 | 给出 FP16 / INT8 / INT4 三档估算值 | Major | 全自动 |
| `G4-CAP-02` | KV-Cache 估算 | 层数 / 头数 / 上下文长度 / 并发 | 必须给出目标并发与上下文下的峰值 | Major | 全自动 |
| `G4-CAP-03` | 激活峰值余量 | 经验系数 | 预留余量，避免 OOM | Major | 全自动 |
| `G4-CAP-04` | 单卡 / 多卡 / 多节点判定 | 上述合计 vs 集群卡型显存 | 输出最小可行拓扑（TP / PP 切分方案） | Major | 全自动 |
| `G4-CAP-05` | 权重存储容量 | 文件总大小 | 含多量化版本共存需求 | Minor | 全自动 |
| `G4-CAP-06` | 集群调度能力匹配 | 集群实时画像（TTL 24h） | 画像过期 → `needs_info`；容量不足 → `fail` | Major | 全自动 |
| `G4-CAP-07` | 加速器兼容性 | 卡型 / 驱动 / CUDA 版本 | 量化格式与卡型不兼容 → `fail` | Major | 全自动 |
| `G4-CAP-08` | 冷启动与权重分发 | 镜像/权重拉取时长 | 影响弹性伸缩 SLO | Minor | 半自动 |
| `G4-CAP-09` | 成本估算 | 卡时单价 × 预估用量 | 输出月度成本区间，供会签参考 | Minor | 半自动 |

---

## 受控准入模板：来源不完整/上游无签名模型 (`origin_uncertain_controlled_admission`)

> **适用场景**：上游开源社区未提供厂商 Sigstore 签名或来源厂商背景信息不完备，但业务团队具备明确的内部使用需求。
> **核心原则**：不因来源信息不完全而一刀切拒绝，而是通过 **Lenovo 技术与运营直接控制**（Platform Endorsement + 锁定 Digest + 强制 Restricted Profile + 缩短复评周期 + 明确责任人）实现受控准入。

| 控制项 | 要求 | 验证方式 |
| --- | --- | --- |
| **权重完整性** | 平台下载首次计算并锁定 SHA-256 Manifest Root Digest | G1-PROV-03 校验 |
| **背书签名** | 由 Lenovo 内部签名服务签发 Platform Endorsement | G1-PROV-05 验签 |
| **序列化安全** | 仅允许 `.safetensors` 或 `.gguf`，禁止任何 pickle/bin 权重 | G2-BOM-02 扫描 |
| **运行时隔离** | 强制采用 `restricted` 运行时 Profile（只读根、Deny-All 出站、非 root、丢弃所有 Capability） | G4/G6 绑定 |
| **责任链完备** | 必须指定明确的 `service_owner`、`security_owner` 及应急 On-Call 轮值 | G6 会签表单 |
| **应急处置通道** | 必须预配置有效 `kill_switch_ref` 与 `rollback_runbook_ref` | L3 清单登记 |
| **复评与有效期** | 准入有效期由 90 天缩短为 **30 天**，强制定期重评 | 自动调度 |

**裁决结果**：`approved_with_conditions`（带条件通过），`runtime_profile = restricted`，`scope = [internal]`。

---

## 会签裁决矩阵（G6）

| 条件 | 结果 |
| --- | --- |
| 任一 Blocker `fail` | `rejected`（终态，需重新提交新申请） |
| 任一检查项 `needs_info` | `need_info`（回环，最多 3 次） |
| 全部 `pass`，无 Major | `approved`，`runtime_profile = standard` |
| 全部 `pass`，存在 Major | `approved_with_conditions`，Major 项转为 `conditions[]`，`runtime_profile = restricted` |
| 命中 `legal_review_required` | 强制 `legal_reviewer` 参与 + 人工签字 |
| `G1-PROV-04` 为平台背书而非厂商签名 | 风险等级 +1 档，`runtime_profile` 至少 `restricted` |

---

## 准入有效期与复评触发

| 触发条件 | 动作 |
| --- | --- |
| 定期到期（默认 90 天） | 强制复评 G2 + G3 |
| 上游发布新版本 | 新版本视为**新申请**，旧版本保持原状态 |
| 许可证条款变更 | 立即触发 G3 重评，期间状态置 `reassessing` |
| 新增 Critical CVE | 立即触发 G2 重评；命中则 `revoked` |
| 运行时配置漂移 | 触发 L5 处置流程（见标准 C） |

---

## 检查表使用方式

1. 每个申请生成一份检查表实例，逐项填 `verdict` + `evidence_ref`
2. `evidence_ref` 必须指向证据库中不可变条目，不接受「人工确认」作为唯一证据
3. 检查表实例本身在会签后被 DSSE 签名，作为审计工件长期留存
4. **本检查表输出仅供内部治理参考，不构成法律或采购建议**
