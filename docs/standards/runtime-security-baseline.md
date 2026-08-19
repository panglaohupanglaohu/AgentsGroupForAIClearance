# 标准 B — 模型运行时安全基线配置规范

> **核心问题**：模型在运行时，如何确保它不会危害其他系统或泄露数据？
> **总原则**：开放权重模型必须在**容器化环境中执行，遵循最小权限，与生产网络和敏感数据存储隔离**。

---

## 0. 三档运行时档位（Runtime Profile）

准入决策（标准 A 的 G6）会给每个模型指派一个档位，档位决定实际下发的基线配置强度。

| 档位 | 适用 | 出站网络 | 文件系统 | 数据可达性 |
| --- | --- | --- | --- | --- |
| `isolated` | 高风险来源 / 未通过厂商签名 / 首次引入 | **全禁**（仅 DNS 到内部解析器 + 指标上报） | 全只读 + tmpfs | 无任何生产数据 |
| `restricted` | 带条件准入（存在 Major 项） | 白名单出站 | 只读根 + 指定可写卷 | 仅脱敏数据 |
| `standard` | 全项 pass 且厂商签名有效 | 白名单出站 | 只读根 + 指定可写卷 | 按 scope 授权 |

**默认档位为 `isolated`**。降低档位（放宽）必须由会签显式授予，不得由部署方自行选择。

---

## 1. 网络隔离（Network Isolation）

**要求**：默认禁用一切非必要出口。推理服务只允许被批准的客户端子网访问，服务间通信强制 mTLS。

| 控制项 | 要求 |
| --- | --- |
| 命名空间隔离 | 模型部署在**专用 namespace**，不与业务应用混布 |
| 默认拒绝 | 该 namespace 默认 **deny-all ingress + deny-all egress** |
| 入站白名单 | 仅允许网关 / 已批准客户端子网访问推理端口 |
| 出站白名单 | 仅允许：内部 DNS、指标采集端点、模型仓库（**仅拉取阶段**，运行期关闭） |
| 权重拉取隔离 | 权重下载在独立的 init 阶段完成，运行容器**不具备**访问外部仓库的能力 |
| 服务间加密 | 全链路 mTLS |
| 边界防护 | 推理端点前置 WAF + 速率限制 |
| 凭据 | 身份感知代理 + **短时凭据**，禁止长期 API Key |

### NetworkPolicy 模板（deny-all 基线）

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: model-runtime-deny-all
  namespace: model-runtime
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
# 无 ingress/egress 规则 = 全部拒绝
```

### NetworkPolicy 模板（`standard` / `restricted` 档位的最小放行）

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: model-runtime-allowlist
  namespace: model-runtime
spec:
  podSelector:
    matchLabels: { app: model-inference }
  policyTypes: [Ingress, Egress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels: { role: api-gateway }
      ports:
        - protocol: TCP
          port: 8000
  egress:
    # 仅内部 DNS
    - to:
        - namespaceSelector:
            matchLabels: { kubernetes.io/metadata.name: kube-system }
          podSelector:
            matchLabels: { k8s-app: kube-dns }
      ports:
        - protocol: UDP
          port: 53
    # 仅指标采集端点
    - to:
        - namespaceSelector:
            matchLabels: { role: observability }
      ports:
        - protocol: TCP
          port: 4317
```

> `isolated` 档位仅保留上面 egress 的两条，且**不得**添加任何模型仓库或公网目标。

---

## 2. 文件系统（Filesystem）

| 控制项 | 要求 |
| --- | --- |
| 根文件系统 | **只读**（`readOnlyRootFilesystem: true`） |
| 权重存储 | 只读挂载；**静态加密**（存储层加密） |
| 临时数据 | `emptyDir` + `medium: Memory`（tmpfs），设置 `sizeLimit` |
| 日志落盘 | 不落容器本地磁盘，直接输出到采集管道 |
| 提示词/响应缓存 | **禁止**持久化到磁盘 |
| 权重完整性 | 启动时校验 digest 与准入登记条目一致，不一致则拒绝启动 |

---

## 3. 权限最小化（Least Privilege）

| 控制项 | 要求 |
| --- | --- |
| 运行用户 | 非 root，固定非特权 UID/GID |
| 提权 | `allowPrivilegeEscalation: false` |
| Capabilities | `drop: ["ALL"]`，不添加任何 capability |
| 特权容器 | 禁止 `privileged: true` |
| hostPath / hostNetwork / hostPID | 全部禁止 |
| Seccomp | `RuntimeDefault` |
| ServiceAccount | 专用 SA，`automountServiceAccountToken: false` |
| Pod Security | namespace 强制 `restricted` Pod Security Standard |

### SecurityContext 模板

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: model-inference
  namespace: model-runtime
spec:
  automountServiceAccountToken: false
  serviceAccountName: model-inference-sa
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 10001
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: inference
      image: registry.internal/model-serving@sha256:<PINNED_DIGEST>   # 必须 pin digest
      imagePullPolicy: IfNotPresent
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        privileged: false
        capabilities:
          drop: ["ALL"]
      resources:
        requests: { cpu: "4", memory: "32Gi", nvidia.com/gpu: "1" }
        limits:   { cpu: "8", memory: "64Gi", nvidia.com/gpu: "1" }
      volumeMounts:
        - name: weights
          mountPath: /models
          readOnly: true
        - name: scratch
          mountPath: /tmp
      env:
        - name: DISABLE_PROMPT_LOGGING       # 见第 5 节
          value: "true"
  volumes:
    - name: weights
      persistentVolumeClaim:
        claimName: model-weights-ro
    - name: scratch
      emptyDir:
        medium: Memory
        sizeLimit: 2Gi
```

---

## 4. 资源限制（Resource Limits）

**目的**：防止 DoS 条件——单个模型耗尽节点资源导致其他工作负载不可用。

| 控制项 | 要求 |
| --- | --- |
| CPU / 内存 | 必须同时设置 `requests` 与 `limits` |
| GPU | 显式 `nvidia.com/gpu` 配额；禁止共享未隔离的 GPU |
| 命名空间配额 | `ResourceQuota` 限制该 namespace 总量 |
| 默认值 | `LimitRange` 保证未声明的容器也有上限 |
| 推理并发 | 服务层设置最大并发与队列深度上限 |
| 请求体大小 | 网关层限制单请求最大 token 数与 body 大小 |
| 速率限制 | 按调用方身份限流 |

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: model-runtime-quota
  namespace: model-runtime
spec:
  hard:
    requests.cpu: "64"
    requests.memory: 512Gi
    limits.cpu: "128"
    limits.memory: 1Ti
    requests.nvidia.com/gpu: "8"
    pods: "20"
```

---

## 5. 日志与监控（Logging）

> **关键约束**：自托管场景下，「零数据保留」的等价控制是
> **关闭提示词日志，并确保可观测性代理永不捕获请求体**。
> 安全日志本身不得成为数据泄露向量。

| 控制项 | 要求 |
| --- | --- |
| 请求体（prompt） | **默认不记录**。需诊断时仅记录哈希与长度 |
| 响应体 | **默认不记录** |
| 必记字段 | 时间戳、调用方身份、model_id、token 计数、时延、状态码、错误类型 |
| 脱敏 | 任何进入日志管道的文本必须经过 PII 脱敏 |
| APM/追踪 | 显式关闭 body 捕获 |
| 日志完整性 | 追加写，防篡改存储 |
| 保留期 | 见标准 C |

---

## 6. 容器镜像基线

| 控制项 | 要求 |
| --- | --- |
| 基础镜像 | 最小化发行版（distroless / slim） |
| 镜像引用 | **pin digest**，禁止可变 tag |
| 镜像扫描 | 构建期 + 周期性 CVE 扫描 |
| 镜像签名 | 镜像必须签名，准入控制器验签后方可拉起 |
| 构建来源 | 仅允许内部构建管线产物 |

### Dockerfile 模板（要点）

```dockerfile
# 构建阶段与运行阶段分离，运行阶段不含编译工具链
FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM gcr.io/distroless/python3-debian12:nonroot
# 非 root 运行
USER 10001:10001
COPY --from=builder /install /usr/local
COPY --chown=10001:10001 serve.py /app/serve.py
WORKDIR /app
# 权重不打进镜像，运行时只读挂载
ENV DISABLE_PROMPT_LOGGING=true \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1
EXPOSE 8000
ENTRYPOINT ["python", "/app/serve.py"]
```

> `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` 是**纵深防御**：即使 NetworkPolicy 被误配，
> 运行期也不会主动回连模型仓库。

---

## 7. 推理护栏（Inference Guardrails）

| 控制项 | 要求 |
| --- | --- |
| 输入过滤 | 提示注入检测、上下文边界强制 |
| 输出过滤 | 有害内容检测；生成代码需扫描已知漏洞模式与不安全依赖 |
| 结构化输出 | 尽量以固定 schema 约束响应，缩小攻击面 |
| 人工复核 | 安全关键场景（代码生成、配置变更、自动化修复）在产出落地前强制人工复核 |
| 输出信任级别 | **所有模型输出默认视为不可信** |

---

## 8. 微调数据治理

微调内容会固化进权重，权重既是知识产权也是**潜在外泄通道**（成员推断 / 数据抽取攻击）。
微调语料必须适用与生产数据库同等的数据分级与最小化要求。

---

## 9. 基线符合性校验

部署前由准入控制器校验以下不变量，任一不满足则拒绝调度：

```text
✓ 镜像已签名且 digest 在允许列表
✓ 权重 digest == 准入登记条目记录值
✓ runAsNonRoot == true 且 runAsUser != 0
✓ readOnlyRootFilesystem == true
✓ allowPrivilegeEscalation == false
✓ capabilities.drop 包含 ALL
✓ privileged / hostNetwork / hostPID / hostPath 均未启用
✓ resources.limits 已设置（cpu/memory/gpu）
✓ namespace 存在 deny-all NetworkPolicy
✓ automountServiceAccountToken == false
✓ 提示词日志开关处于关闭态
```
