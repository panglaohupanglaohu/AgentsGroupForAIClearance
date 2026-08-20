# 标准 C — 模型运行时监控与审计标准

> **核心问题**：如何证明一个**正在运行**的模型始终符合安全标准？
> 准入是一次性的，合规是持续的。本标准定义「持续证明（Continuous Assurance）」的最小充分集。

---

## 1. 监控指标（Metrics）

### 1.1 运行时指标

| 指标 | 类型 | 采集频率 | 告警阈值（建议） |
| --- | --- | --- | --- |
| `inference_requests_total{model_id,caller}` | Counter | 15s | 环比突增 > 300% |
| `inference_latency_seconds{model_id,quantile}` | Histogram | 15s | P99 > SLO |
| `inference_errors_total{model_id,type}` | Counter | 15s | 错误率 > 5% |
| `inference_tokens_total{model_id,direction}` | Counter | 15s | 用于成本归因 |
| `gpu_memory_used_bytes{pod,device}` | Gauge | 15s | > 90% 持续 5min |
| `gpu_utilization_ratio{pod,device}` | Gauge | 15s | 长期 < 10%（资源浪费） |
| `container_memory_working_set_bytes{pod}` | Gauge | 15s | > limit 的 90% |
| `inference_queue_depth{model_id}` | Gauge | 15s | > 阈值（背压） |
| `model_weight_digest_match{model_id}` | Gauge(0/1) | 启动 + 1h | **== 0 立即告警** |

### 1.2 合规态势指标

| 指标 | 含义 |
| --- | --- |
| `clearance_entries_total{status}` | 准入清单条目分布（approved / conditional / revoked） |
| `clearance_reassessment_overdue_total` | 逾期未复评数量 |
| `runtime_baseline_violations_total{control}` | 基线不符合项数量 |
| `model_high_risk_running_total` | 高风险档位模型在运行数 |
| `drift_events_total{type}` | 漂移事件数（license / cve / config） |

---

## 2. 安全事件检测与处置动作映射（Detection & Remediation Mapping）

**原则**：模型运行时的异常行为几乎都表现为「它试图做准入时没说要做的事」。所有事件必须具备清晰的处置动作、响应时限与责任归属。

| ID | 检测项 | 触发条件 | 严重级 | 默认处置动作 (`default_action`) | 最长响应时限 (`max_response_time`) | 责任角色 (`owner_role`) |
| --- | --- | --- | --- | --- | --- | --- |
| `D-NET-01` | 异常出站流量 | 出现 NetworkPolicy 白名单外的连接尝试 | Critical | 立即隔离 Pod + 告警 | 5 分钟 | Security Ops |
| `D-NET-02` | 出站数据量异常 | 出站字节数环比突增 | High | 告警 + 人工研判 | 15 分钟 | Security Ops |
| `D-NET-03` | DNS 异常查询 | 查询非内部域名 | High | 阻断并告警 | 15 分钟 | Platform Ops |
| `D-PRV-01` | 提权尝试 | 容器内出现 setuid / capability 请求 | Critical | 立即终止 Pod | 1 分钟 | Platform Ops |
| `D-PRV-02` | 非预期进程 | 出现基线外可执行文件（如 shell、curl） | Critical | 立即终止 Pod | 1 分钟 | Platform Ops |
| `D-FS-01` | 只读文件系统写入尝试 | 根文件系统写失败事件 | High | 告警 + 隔离排查 | 30 分钟 | Platform Ops |
| `D-FS-02` | 权重文件变更 | 权重 digest 与登记值不符 | Critical | 立即终止 + 触发 Kill-Switch 撤销准入 | 2 分钟 | Security Ops |
| `D-CFG-01` | 配置漂移 | 实际 Pod spec 与基线不符 | High | 自动修复或阻断调度 | 10 分钟 | Platform Ops |
| `D-CFG-02` | 镜像漂移 | 运行镜像 digest 不在允许列表 | Critical | 立即终止并回滚至上一基线镜像 | 5 分钟 | Platform Ops |
| `D-USE-01` | 越权调用 | 调用方身份不在授权 scope | High | 拒绝调用 + 告警 | 即时 (自动化) | Security Ops |
| `D-USE-02` | 速率异常 | 单调用方请求速率突破限流 | Medium | 限流 + 记录日志 | 即时 (自动化) | Platform Ops |
| `D-SEC-01` | 提示注入特征 | 输入命中注入模式库 | Medium | 拦截 + 记录特征（不记原文） | 即时 (自动化) | AI Governance |
| `D-SEC-02` | 输出泄露特征 | 输出命中敏感数据模式 | High | 拦截 + 阻断输出 + 告警 | 即时 (自动化) | AI Governance |
| `D-LOG-01` | 提示词日志被开启 | `DISABLE_PROMPT_LOGGING != true` | High | 阻断部署 | 5 分钟 | Platform Ops |

---

## 3. 合规证据留存（Evidence Retention）

> **约束**：安全日志本身不得成为数据泄露向量。留存的是**元数据与判定**，不是**内容**。

| 证据类型 | 内容 | 保留期 | 存储要求 |
| --- | --- | --- | --- |
| 准入 attestation | 各门禁 DSSE 签名判定 | **永久** | 不可变、可验签 |
| 检查表实例 | 逐项 verdict + evidence_ref | **永久** | 不可变 |
| 会签记录 | 裁决人、时间、conditions | **永久** | 不可变 |
| AI-BOM 快照 | CycloneDX ML-BOM | 3 年 | 版本化 |
| 扫描原始结果 | CVE / 签名 / 格式扫描输出 | 3 年 | 版本化 |
| 部署基线快照 | 实际生效的 Pod spec | 1 年 | 版本化 |
| 访问日志（元数据） | 时间、调用方、model_id、token 数、状态 | 180 天 | 追加写 |
| **请求/响应正文** | — | **不留存** | — |
| 安全告警与处置 | 事件、判定、动作 | 1 年 | 不可变 |
| 漂移事件 | 类型、检出时间、处置 | 3 年 | 不可变 |

**审计可回答性要求**：任意时刻应能对任一运行中的模型回答：

1. 它是**谁**、在**何时**、基于**哪些证据**批准的？
2. 当时的许可证结论与依据条款原文是什么？
3. 它现在跑的权重 digest 与批准时**是否一致**？
4. 它现在的运行时配置与基线**是否一致**？
5. 自批准以来发生过哪些漂移事件、如何处置的？

---

## 4. 审计频率（Audit Cadence）

| 检查 | 频率 | 方式 | 不符合处置 |
| --- | --- | --- | --- |
| 权重 digest 校验 | 启动时 + 每小时 | 自动 | 立即终止 |
| 运行时基线符合性 | **每 30 分钟** | 自动 | 高危项自动阻断 |
| 镜像 CVE 重扫 | 每日 | 自动 | Critical → 强制升级窗口 |
| 许可证变更监听 | 每日 | 自动（复用 L0 采集管线） | 触发 G3 重评 |
| 新 CVE 影响面重评 | 每日 | 自动 | 命中则 `revoked` |
| 准入条目到期复评 | 90 天 | 半自动 | 逾期自动降级为 `restricted` |
| 全量合规报告 | 每月 | 自动生成 | 提交治理评审 |
| 红队复测 | 每季度 | 半自动 | 结果回写 G5 |
| 标准本身评审 | 每半年 | 人工 | 版本化更新 |

> **30 分钟**这一节拍与现有系统的 Cron 调度周期一致，可直接复用调度器，不引入新组件。

---

## 5. 合规报告（Compliance Report）

月度报告最小内容：

```text
1. 准入清单总览      approved / conditional / revoked / 逾期复评
2. 运行时符合性       各控制项通过率、Top 不符合项
3. 安全事件           按严重级统计、平均处置时长
4. 漂移事件           许可证变更 / 新 CVE / 配置漂移，及处置结果
5. 资源与成本         按 model_id 归因的 GPU 卡时与 token 量
6. 高风险项           isolated 档位模型清单及其存在理由
7. 待办               逾期项、未闭环告警、下期计划
```

报告本身签名留存，作为审计工件。

---

## 6. 与 SAIF 的对应

| SAIF 核心要素 | 本标准落点 |
| --- | --- |
| 扩展安全基础到 AI 生态 | 第 1 节指标接入既有可观测性栈 |
| 将 AI 纳入检测与响应 | 第 2 节检测规则接入既有 SIEM/SOC 流程 |
| 自动化防御 | 第 4 节自动审计 + 自动阻断 |
| 统一平台级控制 | runtime_profile 统一下发，禁止逐个部署自定义 |
| 调整控制形成快速反馈回路 | 漂移 → 重评 → 更新 conditions 的闭环 |
| 在业务流程中理解 AI 风险 | scope 与调用方身份绑定，成本与风险按业务归因 |
