# TODOS — 开放权重模型基础设施准入控制系统

> **执行者标注**
> **[GF]** = Gemini Flash 可独立完成（机械替换、模板化数据录入、样板代码、已给出伪代码的确定性实现）
> **[HI]** = 需高阶模型或人工（架构决策、评分权重、Agent 提示词、安全判定边界）
>
> **全局约束**
> 1. 每个任务完成后必须跑通 `验收` 一节的命令，输出为准，不接受「应该没问题」
> 2. 违反 [PLAN.md](PLAN.md) 五条设计原则（T1–T5）的实现直接打回
> 3. **T2 铁律**：Scanner 产出 `finding`，Policy 产出 `verdict`，Agent 产出 `opinion`。禁止混淆
> 4. **T4 铁律**：所有 `except` 分支必须落到 `fail` 或 `needs_info`，禁止 `pass`

---

## 目录

| 阶段 | 范围 | 任务 |
| --- | --- | --- |
| P0 | 术语净化 | T001–T007 |
| P1 | 数据底座与知识库 | T101–T108 |
| P2 | 证据层 Scanner | T201–T210 |
| P3 | 策略引擎与门禁 | T301–T308 |
| P4 | Agent 评审团队 | T401–T407 |
| P5 | 准入清单与 attestation | T501–T506 |
| P6 | 运行时基线与校验 | T601–T606 |
| P7 | 持续验证 L5 | T701–T706 |
| P8 | 前端准入控制台 | T801–T808 |

---

# P0 — 术语净化

### T001 [GF] 页面改名 ✅ 已完成
`investment-engine.html` → `ai-model-entry-clearance.html`；同步 JS 与 features 目录；
nav.js / global-nav.js / 5 个前端测试 / `test_domain_api_and_security.py` 已更新。

### T002 [GF] 清除 `stock` 字样 ✅ 已完成
**范围**：全仓 85 处 / 51 文件，重点 `docs/`、`research/`、`CHANGELOG.md`、`CONTRIBUTING.md`、`.github/`

```text
FOR each file IN repo EXCLUDING [.git, node_modules, .venv]:
    content = read(file)
    content = replace(content, "StockAgents", "ModelClearance")
    content = replace(content, "stockagents",  "modelclearance")
    content = replace_word(content, "stock", "model")     # 仅整词，避免 "stockpile" 类误伤
    write(file, content)

ASSERT grep_count(repo, "stock", ignore_case=True) == 0
```

**验收**：`grep -ri "stock" --exclude-dir={.git,node_modules,.venv} . | wc -l` → `0`

### T003 [GF] 清除 `投资` / `股票` 字样 ✅ 已完成
按 [PLAN.md](PLAN.md) 第 8 节替换表逐词替换。
**易漏点**：`login.html` 第 447 行副标题、`login-page-flow.test.js` 第 65 行对应断言必须同步改。

**验收**：`grep -r "投资\|股票\|纸面\|ticker" --exclude-dir={.git,node_modules,.venv} . | wc -l` → `0`

### T004 [GF] 侧边栏菜单重命名 ✅ 已完成
文件：`src/frontend/js/engine-sidebar.js` + `src/frontend/__tests__/engine-sidebar.test.js`

| 原 id | 原 label | 新 id | 新 label | 新 target |
| --- | --- | --- | --- | --- |
| `overview` | 首页 | `overview` | 准入总览 | `clearance-overview` |
| `analysis` | 分析 | `application` | 申请配置 | `clearance-application` |
| `news` | 信息流 | `evidence` | 证据流 | `clearance-evidence` |
| `performance` | 市场表现 | `posture` | 合规态势 | `clearance-posture` |
| `authors` | 我的 Agent | `reviewers` | 评审 Agent | `clearance-board` |
| `research` | 研究组 | `board` | 评审组 | `clearance-board` |
| `timeline` | 运行时间线 | `timeline` | 审批时间线 | `clearance-timeline` |
| `health` | 运行时健康 | `health` | 运行时健康 | `clearance-health` |
| `portfolio` | 纸面组合 | `registry` | 准入清单 | `clearance-registry` |

### T005 [GF] 准入控制台文案 ✅ 已完成
文件：`src/frontend/ai-model-entry-clearance.html`

- `投资引擎装配台` → `准入控制台`
- 路线条 `信息上下文→判断形成→规划路线→风险门禁→纸面成交`
  → `登记 G0 → 来源 G1 → 供应链 G2 → 许可证 G3 → 资源 G4 → 安全行为 G5 → 会签 G6`
- 卡片：`纸面组合`→`准入裁决`；`价值推演`→`资源需求`；`当前判断`→`门禁结论`
- 免责声明 → `仅供内部治理参考，不构成法律或采购建议`

### T006 [GF] 文档路径同步 ✅ 已完成
`docs/new-pages.md`、`docs/architecture.md`、`docs/repository-layout.md`、`docs/engine-live-cockpit-plan.md`
中 `/investment-engine.html` → `/ai-model-entry-clearance.html`

### T007 [GF] 术语回归测试 ✅ 已完成
新建 `src/frontend/__tests__/terminology-guard.test.js`：

```js
// 防止术语回流的守卫测试
const BANNED = [/stock/i, /投资/, /股票/, /纸面/, /ticker/i, /市场表现/];
const SCAN_DIRS = ['src/frontend', 'src/backend', 'docs'];

for (const file of walk(SCAN_DIRS, ['.js','.html','.py','.md'])) {
  const text = readFileSync(file, 'utf8');
  for (const re of BANNED) {
    expect(text, `${file} 含禁用词 ${re}`).not.toMatch(re);
  }
}
```

---

# P1 — 数据底座与知识库

### T101 [GF] 模型许可证知识库 ✅ 已完成
文件：`config/model_license_registry.json`

```jsonc
{
  "schema_version": "1.0",
  "updated_at": "2026-08-20T00:00:00Z",
  "models": [
    {
      "model_id": "meta-llama/Llama-3.1-8B-Instruct",
      "display_name": "Llama 3.1 8B Instruct",
      "vendor": "Meta",
      "vendor_country": "US",
      "params_b": 8,
      "license_id": "llama-3.1-community",
      "license_url": "https://...",          // 必填，禁止编造
      "license_class": "conditional",         // commercial_ok|conditional|restricted
      "license_conditions": ["MAU 上限", "命名归属义务"],
      "aup_url": "https://...",
      "weights_url": "https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct",
      "weights_format": "safetensors",
      "open_weights_signatory": null,          // true|false|null(未知)
      "latest_version": "...",
      "source_url": "https://...",             // 必填，信息出处
      "verified_at": "2026-08-20"
    }
  ]
}
```

**硬性要求**
- ≥ 20 条主流开放权重模型（Llama / Qwen / DeepSeek / Mistral / Gemma / Phi / GLM / Yi / InternLM / Falcon …）
- 每条 `license_url` 与 `source_url` **必须真实可访问**
- 拿不准的字段填 `null`，**严禁编造许可证名称或条款**

### T102 [GF] 知识库校验脚本 ✅ 已完成
文件：`scripts/validate_model_registry.py`

```python
REQUIRED = ["model_id","display_name","vendor","license_id",
            "license_url","license_class","weights_url","source_url"]
ENUM_CLASS = {"commercial_ok","conditional","restricted"}

def validate(path) -> int:
    data, errors = load_json(path), []
    seen = set()
    for i, m in enumerate(data["models"]):
        for f in REQUIRED:
            if not m.get(f):
                errors.append(f"[{i}] 缺必填字段 {f}")
        if m.get("license_class") not in ENUM_CLASS:
            errors.append(f"[{i}] license_class 非法: {m.get('license_class')}")
        for uf in ("license_url","weights_url","source_url"):
            if m.get(uf) and not m[uf].startswith("https://"):
                errors.append(f"[{i}] {uf} 必须为 https")
        if m["model_id"] in seen:
            errors.append(f"[{i}] model_id 重复: {m['model_id']}")
        seen.add(m["model_id"])
    for e in errors: print("FAIL:", e)
    return 1 if errors else 0
```

**验收**：`python scripts/validate_model_registry.py` → 退出码 0

### T103 [HI] 申请单数据模型 ✅ 已完成
文件：`src/backend/domain/model_clearance/models.py`

```python
class AppStatus(str, Enum):
    DRAFT="draft"; SUBMITTED="submitted"; GATING="gating"
    NEED_INFO="need_info"; ADJUDICATING="adjudicating"
    APPROVED="approved"; APPROVED_COND="approved_with_conditions"
    REJECTED="rejected"; REGISTERED="registered"
    REASSESSING="reassessing"; REVOKED="revoked"

@dataclass
class CustodyStep:
    step_type: str          # origin|finetune|quantize|merge
    input_digest: str
    output_digest: str
    performed_by: str
    performed_at: str
    signature_ref: str | None

@dataclass
class Evidence:                    # 不可变，append-only
    evidence_id: str
    gate: str                      # G1..G5
    check_id: str                  # 如 G1-PROV-03
    collector: str                 # scanner 名称
    collector_version: str
    collected_at: str
    payload: dict                  # 原始结果
    digest: str                    # payload 的 sha256，防篡改

@dataclass
class GateVerdict:
    gate: str
    verdict: str                   # pass|fail|needs_info
    severity: str                  # blocker|major|minor|none
    failed_checks: list[str]
    evidence_refs: list[str]
    decided_by: str                # policy|agent|human
    decided_at: str

@dataclass
class ModelApplication:
    application_id: str
    applicant: str
    identity: ModelIdentity
    custody_chain: list[CustodyStep]
    evidence: list[Evidence]
    verdicts: list[GateVerdict]
    opinions: list[ReviewOpinion]
    status: AppStatus
    need_info_count: int = 0       # 上限 3
```

### T104 [GF] 申请单存储 ✅ 已完成
文件：`src/backend/domain/model_clearance/store.py`
参照 `domain/investment_simulation/store.py` 的 JSON 落盘模式，仅替换实体。
**要求**：`Evidence` 与 `GateVerdict` 一经写入不可修改，只能追加。

```python
def append_evidence(self, app_id: str, ev: Evidence) -> None:
    app = self.load(app_id)
    if any(e.evidence_id == ev.evidence_id for e in app.evidence):
        raise ImmutableViolation(f"evidence {ev.evidence_id} 已存在，禁止覆盖")
    ev.digest = sha256_of(canonical_json(ev.payload))
    app.evidence.append(ev)
    self.save(app)
```

### T105 [GF] 状态机实现 ✅ 已完成
```python
ALLOWED = {
  "draft":        {"submitted"},
  "submitted":    {"gating"},
  "gating":       {"rejected","need_info","adjudicating"},
  "need_info":    {"submitted","rejected"},
  "adjudicating": {"approved","approved_with_conditions","rejected"},
  "approved":     {"registered"},
  "approved_with_conditions": {"registered"},
  "registered":   {"reassessing"},
  "reassessing":  {"registered","revoked"},
  "rejected":     set(),      # 终态
  "revoked":      set(),      # 终态
}

def transition(app, target):
    if target not in ALLOWED[app.status]:
        raise IllegalTransition(f"{app.status} -> {target} 非法")
    if target == "submitted" and app.need_info_count > 3:
        return transition(app, "rejected")   # 补充信息超限自动拒绝
    app.status = target
```

### T106 [GF] Open Weights Letter 签署方名单 ✅ 已完成
文件：`config/open_weights_signatories.json`，字段 `{organization, signed_at, source_url}`。
**要求**：仅录入能提供 `source_url` 的条目；无法核实一律不录。

### T107 [HI] 集群能力画像接口 ✅ 已完成
```python
@dataclass
class ClusterCapability:
    generated_at: str
    ttl_seconds: int = 86400       # 24h
    gpu_pools: list[GpuPool]       # {card_model, memory_gb, count_total, count_free}
    max_single_node_gpus: int
    supports_multi_node_serving: bool

    def is_stale(self) -> bool:
        return now() - parse(self.generated_at) > timedelta(seconds=self.ttl_seconds)
```
**T4 约束**：`is_stale()` 为真时 G4 必须判 `needs_info`，禁止用过期画像判 `pass`。

### T108 [GF] 数据模型单测 ✅ 已完成
覆盖：非法状态跃迁抛异常、evidence 不可覆盖、`need_info_count > 3` 自动拒绝、过期画像判 `needs_info`。

---

# P2 — 证据层 Scanner

> **统一契约**：每个 Scanner 实现同一接口，产出 `Evidence`，**永不产出 verdict**。

### T201 [HI] Scanner 基类契约 ✅ 已完成
```python
class Scanner(ABC):
    name: str
    version: str
    check_ids: list[str]
    timeout_seconds: int = 300

    @abstractmethod
    def collect(self, identity: ModelIdentity) -> dict: ...

    def run(self, identity) -> Evidence:
        try:
            payload = with_timeout(self.collect, self.timeout_seconds)(identity)
            payload["_status"] = "ok"
        except TimeoutError:
            payload = {"_status": "timeout", "_error": "采集超时"}   # T4: 不吞掉
        except Exception as e:
            payload = {"_status": "error", "_error": str(e)}
        return Evidence(
            evidence_id=uuid7(), gate=self.gate, check_id=self.check_ids[0],
            collector=self.name, collector_version=self.version,
            collected_at=now_iso(), payload=payload,
            digest=sha256_of(canonical_json(payload)),
        )
```

### T202 [HI] 签名验证 Scanner（G1） ✅ 已完成
```python
class SignatureScanner(Scanner):
    name, gate = "sigstore-verify", "G1"
    check_ids = ["G1-PROV-04","G1-PROV-05","G1-PROV-06"]

    def collect(self, identity):
        sig = locate_signature(identity.weights_uri)   # model.sig / *.sigstore
        if not sig:
            return {"vendor_signature": "absent",
                    "action_required": "platform_endorsement"}   # → 触发 T203
        result = model_signing_verify(
            model_path=identity.local_path, signature=sig,
            identity=identity.expected_signer_identity,
            oidc_issuer=identity.expected_oidc_issuer,
        )
        return {
            "vendor_signature": "present",
            "verified": result.ok,
            "signer_identity": result.identity,
            "rekor_inclusion_proof": result.inclusion_proof_present,
            "manifest_entries": len(result.manifest),
        }
```

### T203 [HI] 平台背书签名器（G1-PROV-05） ✅ 已完成
```python
def platform_endorse(identity) -> dict:
    """上游无签名时，平台自签并锁定 digest。标记为平台背书而非厂商背书。"""
    manifest = build_manifest(identity.local_path)      # [(path, sha256), ...]
    bundle   = model_signing_sign(
        model_path=identity.local_path,
        method="pkcs11" if HSM_ENABLED else "key",
        key_ref=PLATFORM_SIGNING_KEY,
    )
    return {
        "endorsement": "platform",       # 非 vendor
        "risk_adjustment": +1,           # 风险等级 +1 档
        "min_runtime_profile": "restricted",
        "locked_digest": manifest_root_digest(manifest),
        "bundle_ref": store_bundle(bundle),
    }
```

### T204 [GF] 哈希清单 Scanner（G1-PROV-03） ✅ 已完成
```python
def collect(self, identity):
    entries = []
    for f in walk_files(identity.local_path, ignore=[".git", "*.md"]):
        entries.append({"path": rel(f), "sha256": sha256_file(f), "bytes": size(f)})
    return {"manifest": entries,
            "root_digest": sha256_of(canonical_json(entries)),
            "file_count": len(entries)}
```

### T205 [GF] 序列化格式 Scanner（G2-BOM-02/03） ✅ 已完成
```python
SAFE  = {".safetensors", ".gguf"}
UNSAFE = {".bin", ".pt", ".pth", ".ckpt", ".pkl"}   # pickle → 任意代码执行面

def collect(self, identity):
    findings = []
    for f in walk_files(identity.local_path):
        ext = suffix(f)
        if ext in UNSAFE:
            findings.append({"path": rel(f), "format": ext,
                             "risk": "arbitrary_code_execution"})
    return {
        "unsafe_files": findings,
        "safe_only": len(findings) == 0,
        "requires_trust_remote_code": has_custom_code(identity.local_path),
    }
```

### T206 [GF] AI-BOM 生成 Scanner（G2-BOM-01） ✅ 已完成
产出 CycloneDX ML-BOM（ECMA-424），组件类型含 `machine-learning-model` / `data` / `library`。
```python
def collect(self, identity):
    bom = cyclonedx.Bom(spec_version="1.6")
    bom.add_component(type="machine-learning-model",
                      name=identity.model_id, version=identity.revision,
                      hashes=[{"alg":"SHA-256","content":identity.root_digest}])
    for lib in parse_requirements(identity.local_path):
        bom.add_component(type="library", name=lib.name, version=lib.version,
                          purl=lib.purl, licenses=lib.licenses)
    bom.add_component(type="data", name="training-data",
                      description="厂商声明，不可独立验证",
                      properties={"provenance_verifiable": "false"})   # 开放权重≠开放数据
    return {"bom": bom.to_dict(), "component_count": bom.count()}
```

### T207 [GF] CVE 匹配 Scanner（G2-BOM-04/05） ✅ 已完成
```python
def collect(self, identity):
    purls = [c["purl"] for c in load_bom(identity)["components"] if c.get("purl")]
    vulns = osv_batch_query(purls)          # OSV / NVD
    by_sev = group_by(vulns, "severity")
    return {
        "queried": len(purls),
        "vulnerabilities": vulns,
        "critical": len(by_sev.get("CRITICAL", [])),
        "high":     len(by_sev.get("HIGH", [])),
        "db_snapshot_date": osv_snapshot_date(),   # 供审计复现
    }
```

### T208 [HI] 资源估算 Scanner（G4） ✅ 已完成
```python
def estimate(cfg, quant_bits, concurrency, ctx_len) -> dict:
    """三段式估算：权重 + KV-Cache + 激活峰值。禁止只算权重。"""
    weight_gb = cfg.params * quant_bits / 8 / 1e9

    # KV-Cache = 2(K,V) × 层数 × KV头数 × 头维 × ctx × 并发 × dtype字节
    kv_gb = (2 * cfg.num_layers * cfg.num_kv_heads * cfg.head_dim
             * ctx_len * concurrency * KV_DTYPE_BYTES) / 1e9

    activation_gb = weight_gb * ACTIVATION_HEADROOM_RATIO   # 经验余量
    total = weight_gb + kv_gb + activation_gb

    return {
        "quant_bits": quant_bits, "concurrency": concurrency, "context_length": ctx_len,
        "weight_gb": round(weight_gb, 2), "kv_cache_gb": round(kv_gb, 2),
        "activation_gb": round(activation_gb, 2), "total_gb": round(total, 2),
        "min_gpus": ceil(total / target_card_memory_gb),
        "requires_multi_node": total > max_single_node_memory_gb,
    }

def collect(self, identity):
    cfg = read_model_config(identity)      # config.json
    return {"estimates": [estimate(cfg, b, c, l)
                          for b in (16, 8, 4)
                          for (c, l) in TARGET_WORKLOAD_POINTS]}
```

### T209 [HI] 红队 Scanner（G5） ✅ 已完成
封装 garak 等对抗框架，产出越狱率、提示注入抗性、有害内容触发率。
**只产出数值与用例引用，不产出「是否安全」的结论**。

### T210 [GF] Scanner 单测 ✅ 已完成
每个 Scanner 至少覆盖：正常路径、超时路径、异常路径。
**断言超时与异常时 `payload["_status"] != "ok"`**，为 T4 的 fail-closed 提供依据。

---

# P3 — 策略引擎与门禁

### T301 [HI] 策略规则文件（T3 策略即代码） ✅ 已完成
文件：`config/clearance_policy.yaml`

```yaml
version: 1
gates:
  G1:
    blocker_checks: [G1-PROV-01, G1-PROV-02, G1-PROV-03, G1-PROV-05,
                     G1-PROV-07, G1-PROV-08, G1-PROV-10]
    rules:
      - id: G1-PROV-02
        expr: "evidence.revision_pinned == true"
        on_false: fail
        message: "必须锁定不可变 revision，禁止 main/latest"
      - id: G1-PROV-05
        expr: "evidence.vendor_signature == 'present' or evidence.endorsement == 'platform'"
        on_false: fail
  G2:
    blocker_checks: [G2-BOM-01, G2-BOM-02, G2-BOM-03, G2-BOM-04, G2-BOM-05]
    rules:
      - id: G2-BOM-02
        expr: "evidence.safe_only == true"
        on_false: fail
        message: "检出 pickle 类序列化文件，存在任意代码执行面"
      - id: G2-BOM-04
        expr: "evidence.critical == 0"
        on_false: fail
  G3:
    blocker_checks: [G3-LIC-01, G3-LIC-02, G3-JUR-01, G3-JUR-02]
    rules:
      - id: G3-LIC-02
        expr: "evidence.license_class != 'restricted'"
        on_false: fail
license_classes:
  commercial_ok: { scope: [internal, commercial], risk: 0 }
  conditional:   { scope: [internal],             risk: 1, requires_agent_review: true }
  restricted:    { scope: [],                     risk: 3, verdict: fail }
```

### T302 [HI] 策略求值器 ✅ 已完成
```python
def evaluate_gate(gate_id, evidences, policy) -> GateVerdict:
    spec = policy["gates"][gate_id]
    failed, needs_info = [], []

    for rule in spec["rules"]:
        ev = find_evidence(evidences, rule["id"])

        # T4 fail-closed：证据缺失或采集失败 → 绝不 pass
        if ev is None or ev.payload.get("_status") != "ok":
            (failed if rule["id"] in spec["blocker_checks"] else needs_info).append(rule["id"])
            continue

        if not safe_eval(rule["expr"], {"evidence": ev.payload}):
            (failed if rule["id"] in spec["blocker_checks"] else needs_info).append(rule["id"])

    if failed:
        return GateVerdict(gate_id, "fail", "blocker", failed, refs(evidences), "policy", now())
    if needs_info:
        return GateVerdict(gate_id, "needs_info", "major", needs_info, refs(evidences), "policy", now())
    return GateVerdict(gate_id, "pass", "none", [], refs(evidences), "policy", now())
```

### T303 [HI] 门禁编排器（早失败） ✅ 已完成
```python
GATE_ORDER = ["G1", "G2", "G3", "G4", "G5"]

def run_gates(app, policy):
    for gate in GATE_ORDER:
        evidences = [s.run(app.identity) for s in scanners_for(gate)]
        store.append_evidence_batch(app.application_id, evidences)

        verdict = evaluate_gate(gate, evidences, policy)
        store.append_verdict(app.application_id, verdict)

        if verdict.verdict == "fail":
            transition(app, "rejected")      # Blocker 失败：不跑后续门禁，省算力
            return app
        if verdict.verdict == "needs_info":
            app.need_info_count += 1
            transition(app, "need_info")
            return app

        if gate in AGENT_GATES:              # G3/G4/G5 追加 Agent 意见
            opinion = run_agent_review(gate, app, evidences, verdict)
            store.append_opinion(app.application_id, opinion)
            if opinion.tightens_verdict:     # T2/第4节：Agent 只能收紧
                transition(app, "need_info"); return app

    transition(app, "adjudicating")
    return app
```

### T304 [GF] `safe_eval` 表达式求值 ✅ 已完成
仅支持属性访问、比较、`and/or/not`、字面量。
**禁止** `eval`/`exec`/导入/函数调用——用 AST 白名单实现。

### T305 [GF] 策略回归测试（T3 可脱离 LLM 复现） ✅ 已完成
```python
@pytest.mark.parametrize("fixture,expected", [
    ("fixtures/pickle_weights.json",    ("G2", "fail")),      # 序列化不安全
    ("fixtures/critical_cve.json",      ("G2", "fail")),
    ("fixtures/restricted_license.json",("G3", "fail")),
    ("fixtures/mutable_revision.json",  ("G1", "fail")),
    ("fixtures/scanner_timeout.json",   ("G1", "fail")),      # T4 fail-closed
    ("fixtures/clean_permissive.json",  ("G3", "pass")),
])
def test_policy(fixture, expected):
    gate, want = expected
    got = evaluate_gate(gate, load_evidence(fixture), load_policy())
    assert got.verdict == want
```

### T306 [GF] 门禁事件流 ✅ 已完成
事件类型：`gate_started` / `evidence_collected` / `gate_verdict` / `agent_opinion` /
`adjudication_started` / `decision_made`。复用现有事件流机制。

### T307 [HI] 会签裁决器 ✅ 已完成
```python
def adjudicate(app, policy) -> Decision:
    if any(v.verdict == "fail" and v.severity == "blocker" for v in app.verdicts):
        return Decision("rejected", reason="blocker_failed")   # 任何人不得推翻

    majors = [v for v in app.verdicts if v.severity == "major"]
    conditions = [map_major_to_condition(v) for v in majors]

    profile = "standard"
    if any(e.payload.get("endorsement") == "platform" for e in app.evidence):
        profile = "restricted"                # 平台背书而非厂商签名 → 至少 restricted
    if majors:
        profile = "restricted"
    if requires_legal(app) and not has_human_signoff(app):
        return Decision("need_info", reason="legal_signoff_required")

    return Decision(
        "approved_with_conditions" if conditions else "approved",
        conditions=conditions, runtime_profile=profile,
        scope=derive_scope(app, policy),
        expires_at=now() + timedelta(days=90),
    )
```

### T308 [GF] 编排器集成测试 ✅ 已完成
三条真实路径：Blocker 拒绝 / 需补充信息回环 / 带条件通过。

---

# P4 — Agent 评审团队

### T401 [HI] 团队定义 `model_clearance_board` ✅ 已完成
5 个 Agent：`security_reviewer` / `compliance_reviewer` / `infra_reviewer` /
`legal_reviewer`（条件触发）/ `adjudicator`。

### T402 [HI] 评审意见 Schema ✅ 已完成
```json
{
  "gate": "G3",
  "reviewer": "compliance_reviewer",
  "verdict_suggestion": "pass|needs_info|tighten",
  "risk_level": "low|medium|high",
  "findings": [
    { "statement": "该许可证限制月活用户数",
      "evidence_ref": "ev_01H...",
      "quoted_text": "…许可证原文摘录…" }
  ],
  "missing_evidence": ["AUP 全文未采集"],
  "recommended_conditions": ["仅限内部使用", "禁止对外提供推理服务"]
}
```

### T403 [HI] 提示词模板与硬约束 ✅ 已完成
每个 Agent 提示词必须包含：
1. 「你只能基于提供的 evidence 作答；**不得引用记忆中的 CVE 编号或许可证条款**」
2. 「每条 `findings.statement` 必须有 `evidence_ref` 与 `quoted_text`」
3. 「证据不足时输出 `needs_info` 并填 `missing_evidence`，**不得猜测**」
4. 「你可以把 Policy 的 pass 收紧为 needs_info，**不得把 fail 放宽为 pass**」

### T404 [GF] 输出校验与重试 ✅ 已完成
```python
def run_agent_review(gate, app, evidences, policy_verdict) -> ReviewOpinion:
    for attempt in range(MAX_RETRY := 3):
        raw = llm_call(prompt_for(gate, app, evidences))
        ok, err = validate_schema(raw, REVIEW_OPINION_SCHEMA)
        if not ok:
            continue
        # 幻觉守卫：引用必须真实存在
        if not all(ref_exists(f["evidence_ref"], evidences) for f in raw["findings"]):
            continue
        # 摘录守卫：quoted_text 必须能在证据原文中定位
        if not all(quote_locatable(f["quoted_text"], evidences) for f in raw["findings"]):
            continue
        # 单向守卫：只能收紧
        if policy_verdict.verdict == "fail" and raw["verdict_suggestion"] == "pass":
            raise PolicyOverrideAttempt(gate)
        return ReviewOpinion.from_dict(raw)
    return escalate_to_human(gate, app, reason="agent_output_invalid")
```

### T405 [GF] `quote_locatable` 实现 ✅ 已完成
归一化空白后在证据原文中做子串匹配；未命中即判定为幻觉。

### T406 [HI] `legal_reviewer` 触发条件 ✅ 已完成
命中任一即触发：`G3-JUR-02` 命中管制清单 / `G3-REG-01` 判定可能承担 provider 义务 /
`license_class == conditional` 且 scope 含 `commercial`。

### T407 [GF] Agent 层测试 ✅ 已完成
用固定 evidence fixture + mock LLM 返回，断言：
无 `evidence_ref` 被拒、伪造 `quoted_text` 被拒、试图放宽 fail 抛异常、连续 3 次非法升级人工。

---

# P5 — 准入清单与 attestation

### T501 [HI] attestation 签发（T5） ✅ 已完成
```python
def issue_attestation(app, verdict) -> dict:
    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": app.identity.model_id,
                     "digest": {"sha256": app.identity.root_digest}}],
        "predicateType": "https://modelclearance/gate-verdict/v1",
        "predicate": {
            "gate": verdict.gate, "verdict": verdict.verdict,
            "severity": verdict.severity, "failed_checks": verdict.failed_checks,
            "evidence_refs": verdict.evidence_refs,
            "policy_version": load_policy()["version"],
            "decided_by": verdict.decided_by, "decided_at": verdict.decided_at,
        },
    }
    return dsse_sign(statement, key=PLATFORM_SIGNING_KEY)   # DSSE 封装
```

### T502 [GF] 准入清单条目 ✅ 已完成
```python
@dataclass
class ApprovedRegistryEntry:
    entry_id: str
    model_id: str
    locked_digest: str            # 运行时必须与之一致
    decision_ref: str             # 指向 Decision attestation
    scope: list[str]              # internal|commercial|restricted
    conditions: list[str]
    runtime_profile: str          # isolated|restricted|standard
    approved_at: str
    reassessment_due: str
    status: str                   # active|reassessing|revoked
```

### T503 [GF] 清单 API ✅ 已完成
```text
GET    /api/v1/model-clearance/registry
GET    /api/v1/model-clearance/registry/{entry_id}
GET    /api/v1/model-clearance/registry/{entry_id}/attestations
POST   /api/v1/model-clearance/registry/{entry_id}/revoke
GET    /api/v1/model-clearance/applications
POST   /api/v1/model-clearance/applications
POST   /api/v1/model-clearance/applications/{id}/submit
GET    /api/v1/model-clearance/applications/{id}/events
```

### T504 [GF] 验签接口 ✅ 已完成
```python
def verify_entry(entry_id) -> dict:
    entry = registry.get(entry_id)
    results = [{"gate": a["predicate"]["gate"], "signature_valid": dsse_verify(a)}
               for a in load_attestations(entry.decision_ref)]
    return {"entry_id": entry_id,
            "all_valid": all(r["signature_valid"] for r in results),
            "attestations": results}
```

### T505 [GF] 合规证据库归档 ✅ 已完成
按标准 C 第 3 节保留期归档；attestation 与检查表实例**永久**保留。

### T506 [GF] 端到端测试 ✅ 已完成
从提交到登记全链路，断言：登记条目可验签、`locked_digest` 与扫描结果一致。

---

# P6 — 运行时基线与校验

### T601 [GF] 三档 profile 配置文件 ✅ 已完成
`config/runtime_profiles.yaml`，落地标准 B 第 0 节 `isolated` / `restricted` / `standard`。

### T602 [GF] K8s 清单模板 ✅ 已完成
`deploy/templates/` 下产出 NetworkPolicy（deny-all + allowlist）、
SecurityContext Pod 模板、ResourceQuota、LimitRange——内容取自标准 B。

### T603 [HI] 基线符合性校验器 ✅ 已完成
```python
INVARIANTS = [
  ("runAsNonRoot",        lambda p: p.spec.securityContext.runAsNonRoot is True),
  ("nonRootUser",         lambda p: p.spec.securityContext.runAsUser != 0),
  ("readOnlyRootFs",      lambda p: all(c.securityContext.readOnlyRootFilesystem for c in p.containers)),
  ("noPrivEscalation",    lambda p: all(c.securityContext.allowPrivilegeEscalation is False for c in p.containers)),
  ("capsDropAll",         lambda p: all("ALL" in c.securityContext.capabilities.drop for c in p.containers)),
  ("notPrivileged",       lambda p: not any(c.securityContext.privileged for c in p.containers)),
  ("noHostNamespaces",    lambda p: not (p.spec.hostNetwork or p.spec.hostPID or p.spec.hostIPC)),
  ("resourceLimitsSet",   lambda p: all(c.resources.limits for c in p.containers)),
  ("imagePinnedByDigest", lambda p: all("@sha256:" in c.image for c in p.containers)),
  ("saTokenNotMounted",   lambda p: p.spec.automountServiceAccountToken is False),
  ("promptLoggingOff",    lambda p: env_of(p, "DISABLE_PROMPT_LOGGING") == "true"),
]

def check_baseline(pod, entry) -> list[str]:
    violations = [name for name, pred in INVARIANTS if not safe(pred, pod)]
    if pod_weight_digest(pod) != entry.locked_digest:
        violations.append("weightDigestMismatch")      # 最高危
    if not namespace_has_deny_all(pod.metadata.namespace):
        violations.append("missingDenyAllNetworkPolicy")
    return violations
```

### T604 [GF] 权重 digest 启动校验 ✅ 已完成
```python
def preflight(entry):
    actual = compute_manifest_root_digest(MOUNTED_WEIGHTS_PATH)
    if actual != entry.locked_digest:
        log_security_event("D-FS-02", severity="critical",
                           expected=entry.locked_digest, actual=actual)
        sys.exit(1)          # T4：拒绝启动，绝不降级运行
```

### T605 [GF] Dockerfile 模板 ✅ 已完成
落地标准 B 第 6 节：多阶段构建、distroless、非 root、
`HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` 纵深防御。

### T606 [GF] 基线校验器单测 ✅ 已完成
每条不变量各一条正例 + 一条反例；`weightDigestMismatch` 必须被检出。

---

# P7 — 持续验证 L5

### T701 [GF] 30 分钟基线巡检 ✅ 已完成
```python
def periodic_baseline_audit():          # 复用现有 30 分钟 Cron
    for entry in registry.list_active():
        for pod in k8s.pods_of(entry.model_id):
            v = check_baseline(pod, entry)
            if v:
                emit_drift("config", entry.entry_id, v)
                if any(x in CRITICAL_VIOLATIONS for x in v):
                    k8s.evict(pod)      # 高危自动阻断
```

### T702 [GF] 每日 CVE 重评 ✅ 已完成
```python
def daily_cve_reassessment():
    for entry in registry.list_active():
        vulns = osv_batch_query(purls_of(entry))
        new_critical = [v for v in vulns
                        if v.severity == "CRITICAL" and v.id not in known_of(entry)]
        if new_critical:
            emit_drift("cve", entry.entry_id, new_critical)
            registry.transition(entry, "reassessing")
```

### T703 [GF] 每日许可证变更监听 ✅ 已完成
复用 L0 采集管线抓取许可证页；与知识库快照做 diff，变更即触发 G3 重评。

### T704 [GF] 到期复评调度 ✅ 已完成
```python
def due_reassessment():
    for entry in registry.list_active():
        if now() > parse(entry.reassessment_due):
            registry.transition(entry, "reassessing")
            if now() > parse(entry.reassessment_due) + timedelta(days=14):
                entry.runtime_profile = "restricted"    # 逾期自动降档
```

### T705 [GF] 安全事件检测规则 ✅ 已完成
落地标准 C 第 2 节 `D-*` 规则，接入既有告警通道。

### T706 [GF] 月度合规报告 ✅ 已完成
按标准 C 第 5 节七节内容生成，报告本体签名留存。

---

# P8 — 前端准入控制台

### T801 [GF] 六门禁路线条替换现有 route-strip ✅ 已完成
### T802 [GF] 门禁卡片（G1–G5）显示 verdict + 失败检查项 + 证据引用 ✅ 已完成
### T803 [GF] 证据流视图：按 gate 分组，展示 collector / 版本 / 时间 / digest ✅ 已完成
### T804 [GF] 评审意见视图：`findings` 与 `quoted_text` 并排显示，可跳证据 ✅ 已完成
### T805 [GF] 准入清单页替换原组合卡片区 ✅ 已完成
### T806 [GF] 合规态势看板：待处理 / 本周新增 / 高风险运行中 / 逾期复评 ✅ 已完成
### T807 [GF] 申请表单 + 知识库自动补全 ✅ 已完成
### T808 [GF] 前端测试更新 ✅ 已完成

---

# 验收总清单

```bash
# 术语
grep -ri "stock" --exclude-dir={.git,node_modules,.venv} . | wc -l    # 期望 0
grep -r "投资\|股票\|纸面\|ticker" --exclude-dir={.git,node_modules,.venv} . | wc -l  # 期望 0

# 知识库
python scripts/validate_model_registry.py                            # 退出码 0

# 策略（可脱离 LLM 复现 —— T3）
pytest src/backend/tests/test_clearance_policy.py -q

# fail-closed（T4）
pytest src/backend/tests/test_clearance_policy.py -k timeout -q

# Agent 幻觉守卫
pytest src/backend/tests/test_clearance_agents.py -q

# 基线校验
pytest src/backend/tests/test_runtime_baseline.py -q

# 前端
npm run test:frontend

# 烟测
make test-smoke
```

**Phase 1 出口条件**：对 3 个真实模型（permissive / conditional / restricted 各一）
走完 G0–G6，产出可验签 attestation，且 `restricted` 模型确实在 G3 被拒绝。

---

# 验收总清单

```bash
# 术语
grep -ri "stock" --exclude-dir={.git,node_modules,.venv} . | wc -l    # 期望 0
grep -r "投资\|股票\|纸面\|ticker" --exclude-dir={.git,node_modules,.venv} . | wc -l  # 期望 0

# 知识库
python scripts/validate_model_registry.py                            # 退出码 0

# 策略（可脱离 LLM 复现 —— T3）
pytest src/backend/tests/test_clearance_policy.py -q

# fail-closed（T4）
pytest src/backend/tests/test_clearance_policy.py -k timeout -q

# Agent 幻觉守卫
pytest src/backend/tests/test_clearance_agents.py -q

# 基线校验
pytest src/backend/tests/test_runtime_baseline.py -q

# 前端
npm run test:frontend

# 烟测
make test-smoke
```

**Phase 1 出口条件**：对 3 个真实模型（permissive / conditional / restricted 各一）
走完 G0–G6，产出可验签 attestation，且 `restricted` 模型确实在 G3 被拒绝。
