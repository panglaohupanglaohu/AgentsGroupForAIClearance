# 标准 D — 基础设施能力差距清单及 Phase 2 改造建议

> **核心问题**：现有平台（Kubernetes 集群、推理服务框架、可观测性栈）是否已支持标准 A/B/C 的控制？
> 不支持的部分，Phase 2 需要做什么改造？

---

## 0. 差距评估方法

每项能力按四级评定：

| 级别 | 含义 |
| --- | --- |
| **L0 缺失** | 平台完全不具备该能力 |
| **L1 具备但未启用** | 平台支持，但未在模型工作负载上强制 |
| **L2 已启用未强制** | 有配置但可被绕过（无准入控制器拦截） |
| **L3 强制且可证明** | 强制执行 + 有审计证据 |

**目标状态：所有 Blocker 相关能力达到 L3。**

> **本清单为模板**：`现状` 列需要由基础设施团队用实际集群探测结果填写，
> 不得凭印象填写。探测脚本见第 6 节。

---

## 1. 网络控制能力

| 能力 | 目标 | 现状 | 差距影响 | Phase 2 改造 |
| --- | --- | --- | --- | --- |
| NetworkPolicy 支持 | L3 | _待探测_ | 无法隔离模型出站，标准 B 第 1 节全部失效 | 确认 CNI 支持 NetworkPolicy（Calico/Cilium）；不支持则更换 CNI |
| 默认 deny-all 策略 | L3 | _待探测_ | 新建命名空间默认全通 | 命名空间创建时由控制器自动注入 deny-all |
| 出站 FQDN 级管控 | L2+ | _待探测_ | 只能按 IP 放行，仓库域名 IP 漂移导致误配 | 引入支持 FQDN 策略的 CNI 或出站代理 |
| 服务间 mTLS | L3 | _待探测_ | 明文东西向流量 | 引入服务网格或 mTLS sidecar |
| 入口 WAF + 限流 | L3 | _待探测_ | 推理端点暴露、无法防滥用 | 网关层增加 WAF 与按身份限流 |
| 身份感知代理 + 短时凭据 | L3 | _待探测_ | 长期 API Key 泄露风险 | 接入 OIDC + 短时 token |

---

## 2. 容器安全上下文能力

| 能力 | 目标 | 现状 | 差距影响 | Phase 2 改造 |
| --- | --- | --- | --- | --- |
| Pod Security Standards（restricted） | L3 | _待探测_ | 特权容器可运行 | namespace 打 `pod-security.kubernetes.io/enforce=restricted` |
| 准入控制器（策略引擎） | L3 | _待探测_ | 基线无法强制，只能靠自觉 | 部署策略准入控制器，实现标准 B 第 9 节不变量校验 |
| 镜像签名验签 | L3 | _待探测_ | 任意镜像可拉起 | 部署镜像验签准入控制器 |
| 镜像 digest 强制 | L3 | _待探测_ | 可变 tag 导致运行内容不可知 | 准入策略拒绝非 digest 引用 |
| seccomp RuntimeDefault | L3 | _待探测_ | 系统调用面过宽 | 基线模板统一设置 |
| 只读根文件系统 | L3 | _待探测_ | 容器内可落盘 | 基线模板 + 准入校验 |
| GPU 隔离 | L2+ | _待探测_ | 多模型共享 GPU 互相影响 | 明确 GPU 分配策略（整卡独占 / MIG） |
| ResourceQuota / LimitRange | L3 | _待探测_ | 单模型可耗尽节点（DoS） | 每个模型 namespace 强制配额 |

---

## 3. 模型注册表与版本管理

| 能力 | 目标 | 现状 | 差距影响 | Phase 2 改造 |
| --- | --- | --- | --- | --- |
| 统一模型注册表 | L3 | _待探测_ | 无法回答「现在跑着哪些模型」 | 建设 L3 准入清单作为唯一事实源 |
| 权重制品库 | L3 | _待探测_ | 从公网直拉，无内部副本 | 建内部制品库，运行期不出网 |
| 权重静态加密 | L3 | _待探测_ | 权重明文存储 | 存储层加密 |
| digest 锁定与校验 | L3 | _待探测_ | 无法证明跑的就是批准的 | 启动时校验 + 周期校验 |
| 模型签名基础设施 | L3 | _待探测_ | 无法建立 custody 链 | 部署 Sigstore（可私有 Rekor/Fulcio）或 PKCS#11 HSM 签名 |
| 版本与血缘 | L3 | _待探测_ | 微调产物无法溯源到基座 | 注册表记录 parent_digest |

---

## 4. 可观测性与日志管道

| 能力 | 目标 | 现状 | 差距影响 | Phase 2 改造 |
| --- | --- | --- | --- | --- |
| 统一指标采集 | L3 | _待探测_ | 标准 C 第 1 节无法落地 | 接入既有指标栈，补 GPU 与推理指标 |
| GPU 指标采集 | L3 | _待探测_ | 无法做容量与成本归因 | 部署 GPU exporter |
| 日志集中与防篡改 | L3 | _待探测_ | 审计证据不可信 | 追加写存储 + 完整性保护 |
| **请求体不落盘保证** | L3 | _待探测_ | 日志成为泄露向量 | 审计 APM/日志 SDK 配置，显式关闭 body 捕获 |
| PII 脱敏管道 | L3 | _待探测_ | 元数据仍可能含敏感串 | 日志管道增加脱敏处理器 |
| 运行时行为检测 | L2+ | _待探测_ | 标准 C 第 2 节多数规则无数据源 | 部署运行时安全传感器（进程/网络/文件事件） |
| SIEM 联动 | L3 | _待探测_ | 告警无人响应 | 接入既有 SOC 流程与值班 |

---

## 5. 供应链扫描能力

| 能力 | 目标 | 现状 | 差距影响 | Phase 2 改造 |
| --- | --- | --- | --- | --- |
| SBOM 生成 | L3 | _待探测_ | G2 无法出具依赖清单 | 构建管线集成 SBOM 生成 |
| AI-BOM（ML-BOM）生成 | L3 | _待探测_ | 模型/数据集组件缺失 | 采用 CycloneDX ML-BOM |
| 镜像 CVE 扫描 | L3 | _待探测_ | G2-BOM-05 无证据 | 构建期 + 周期性扫描 |
| 序列化格式扫描 | L3 | _待探测_ | pickle 代码执行面无人检查 | 引入模型扫描工具 |
| CVE 数据源接入 | L3 | _待探测_ | 无法做每日重评 | 接入 NVD / OSV 同步 |
| CI/CD 安全闸门 | L3 | _待探测_ | 不合规产物可进制品库 | 流水线增加阻断式安全门 |

---

## 6. 现状探测脚本（填表用）

以下命令用于**客观填写**上表 `现状` 列，禁止凭印象填写：

```bash
# 1. CNI 是否支持 NetworkPolicy —— 建测试策略并验证实际阻断效果
kubectl get networkpolicies -A
kubectl get pods -n kube-system -o name | grep -Ei 'calico|cilium|weave|antrea'

# 2. Pod Security Standards 是否启用
kubectl get ns -o custom-columns='NS:.metadata.name,ENFORCE:.metadata.labels.pod-security\.kubernetes\.io/enforce'

# 3. 是否存在准入控制器（策略引擎 / 验签）
kubectl get validatingwebhookconfigurations -o name
kubectl get mutatingwebhookconfigurations -o name

# 4. 配额与限制
kubectl get resourcequota -A
kubectl get limitrange -A

# 5. 现网工作负载的基线符合度抽样
kubectl get pods -A -o json | jq -r '
  .items[] | select(.spec.containers[]?.securityContext.readOnlyRootFilesystem != true)
  | "\(.metadata.namespace)/\(.metadata.name) 根文件系统可写"'

kubectl get pods -A -o json | jq -r '
  .items[] | select(.spec.securityContext.runAsNonRoot != true)
  | "\(.metadata.namespace)/\(.metadata.name) 可能以 root 运行"'

kubectl get pods -A -o json | jq -r '
  .items[] | select(any(.spec.containers[]?; .image | test("@sha256:") | not))
  | "\(.metadata.namespace)/\(.metadata.name) 镜像未 pin digest"'

# 6. GPU 资源与调度
kubectl get nodes -o custom-columns='NODE:.metadata.name,GPU:.status.capacity.nvidia\.com/gpu'

# 7. 指标与日志管道
kubectl get svc -A | grep -Ei 'prometheus|otel|loki|fluent'
```

---

## 7. Phase 2 改造优先级

按「阻断 Blocker 门禁的能力优先」排序：

| 优先级 | 改造项 | 理由 | 依赖 |
| --- | --- | --- | --- |
| **P0** | 准入控制器（基线强制） | 没有它，标准 B 全部是建议而非控制 | — |
| **P0** | NetworkPolicy deny-all 默认注入 | 出站不受控是最高危风险 | CNI 支持 |
| **P0** | 模型签名与 digest 校验 | G1 Blocker 的实现前提 | 制品库、签名设施 |
| **P0** | 序列化格式与权重扫描 | G2 Blocker 的实现前提 | 扫描工具 |
| **P1** | 内部权重制品库 + 静态加密 | 使运行期完全不出网成为可能 | 存储 |
| **P1** | AI-BOM 生成管线 | G2 证据来源 | SBOM 工具链 |
| **P1** | 请求体不落盘审计与整改 | 防止日志成为泄露向量 | 日志栈配置 |
| **P1** | GPU 指标与容量画像 API | G4 判定的数据源，TTL 24h | 指标栈 |
| **P2** | 服务网格 mTLS | 东西向加密 | 网格组件 |
| **P2** | 运行时行为检测传感器 | 标准 C 第 2 节多数规则 | 节点级 agent |
| **P2** | CI/CD 安全闸门 | 防止不合规产物入库 | 流水线改造 |
| **P3** | 红队自动化回归 | G5 持续化 | 红队框架 |

---

## 8. Phase 2 四大工作项对应

| 工作项 | 覆盖本清单条目 |
| --- | --- |
| **工具链建设** | 第 5 节全部 + P0 的签名/扫描 |
| **监控平台** | 第 4 节全部 |
| **控制平面** | 第 3 节全部（模型、代理、工具、端点、属主、访问模式中央清单） |
| **自动化合规验证** | 标准 C 第 4 节审计节拍的自动化实现 |

---

## 9. 差距未闭合期间的临时缓解

在 P0 改造完成前，任何模型部署必须满足：

1. 仅允许 `isolated` 档位
2. 部署需人工二次审批（补偿准入控制器缺位）
3. 部署后 24 小时内人工核对实际 Pod spec 与基线
4. 不得接触任何生产数据
