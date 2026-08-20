/**
 * P12 — Multi-dimensional clearance matrix for the Model Admission Cockpit.
 * Fixture-safe, as_of aware; missing evidence stays `missing` instead of being
 * scored as passing (T4 fail-closed).
 */
(function (global) {
  'use strict';

  var DIMENSION_KEYS = [
    'artifact_integrity',
    'signature_trust',
    'revision_lock',
    'bom_completeness',
    'vulnerability',
    'serialization_safety',
    'license_compliance',
    'jurisdiction_risk',
    'resource_fit',
    'safety_behavior',
    'operational_control',
  ];

  var GROUPS = {
    summary: {
      id: 'summary',
      label: '准入摘要',
      keys: ['artifact_integrity', 'license_compliance', 'operational_control'],
    },
    integrity: {
      id: 'integrity',
      label: '完整性 G1',
      keys: ['artifact_integrity', 'signature_trust', 'revision_lock'],
    },
    supply_chain: {
      id: 'supply_chain',
      label: '供应链 G2',
      keys: ['bom_completeness', 'vulnerability', 'serialization_safety'],
    },
    compliance: {
      id: 'compliance',
      label: '许可证 G3',
      keys: ['license_compliance', 'jurisdiction_risk'],
    },
    runtime: {
      id: 'runtime',
      label: '资源与安全 G4/G5',
      keys: ['resource_fit', 'safety_behavior'],
    },
    governance: {
      id: 'governance',
      label: 'Lenovo 直管 G6',
      keys: ['operational_control'],
    },
  };

  var LABELS = {
    artifact_integrity: '制品完整性',
    signature_trust: '签名可验性',
    revision_lock: '版本锁定',
    bom_completeness: 'AI-BOM 完备性',
    vulnerability: '漏洞暴露面',
    serialization_safety: '序列化安全',
    license_compliance: '许可证合规',
    jurisdiction_risk: '司法辖区风险',
    resource_fit: '资源与算力适配',
    safety_behavior: '安全行为（红队）',
    operational_control: '运营可控性',
  };

  var GATE_OF = {
    artifact_integrity: 'G1',
    signature_trust: 'G1',
    revision_lock: 'G1',
    bom_completeness: 'G2',
    vulnerability: 'G2',
    serialization_safety: 'G2',
    license_compliance: 'G3',
    jurisdiction_risk: 'G3',
    resource_fit: 'G4',
    safety_behavior: 'G5',
    operational_control: 'G6',
  };

  /** Blocker 维度失败即整体阻断，平均分不得覆盖（对齐 PLAN 2.1）。 */
  var BLOCKER_KEYS = {
    artifact_integrity: true,
    signature_trust: true,
    revision_lock: true,
    bom_completeness: true,
    vulnerability: true,
    serialization_safety: true,
    license_compliance: true,
    jurisdiction_risk: true,
  };

  var RATIONALE = {
    artifact_integrity: '逐文件 SHA-256 清单已生成，root digest 可锁定运行时权重。',
    signature_trust: '厂商签名或平台背书签名可验；无签名时按平台背书降档处理。',
    revision_lock: '已锁定不可变 revision（tag/commit），未使用 main/latest 可变引用。',
    bom_completeness: 'CycloneDX ML-BOM 已产出，模型/依赖/配置组件可追溯。',
    vulnerability: '依赖与基础镜像 CVE 扫描结果；Critical 未清零即触发阻断。',
    serialization_safety: '权重格式扫描：safetensors/gguf 放行，pickle 类判定为代码执行面。',
    license_compliance: '许可证类别与商用条款判定，附加义务转为运行时 conditions。',
    jurisdiction_risk: '出口管制与采购限制清单比对，命中则强制法务会签。',
    resource_fit: '权重显存 + KV-Cache + 激活峰值三段式估算与集群容量比对。',
    safety_behavior: '红队越狱率、提示注入抗性与有害内容触发率的量化结果。',
    operational_control: '责任人、Kill-Switch、回滚预案与处置 SLA 的可执行性核验。',
  };

  function clamp(n, lo, hi) {
    return Math.max(lo, Math.min(hi, n));
  }

  function emptyDim(key, asOf) {
    return {
      key: key,
      gate: GATE_OF[key] || '',
      score: null,
      label: LABELS[key] || key,
      direction: 'unknown',
      confidence: 0,
      as_of: asOf || '',
      evidence_count: 0,
      source_domains: [],
      rationale: '证据缺失，按 fail-closed 处理，不得默认放行',
      state: 'missing',
      progress: 'pending',
    };
  }

  function directionFromScore(score) {
    if (score == null || !isFinite(score)) return 'unknown';
    if (score >= 0.75) return 'pass';
    if (score <= 0.5) return 'fail';
    return 'needs_info';
  }

  function hashSeed(str) {
    var h = 0;
    var s = String(str || '');
    for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
    return Math.abs(h);
  }

  /**
   * TA04: Map real GateOrchestrator ModelApplication verdicts + evidence into judgment matrix rows.
   */
  function dimensionsFromVerdicts(app, asOf) {
    if (!app) return [];
    var appAsOf = asOf || (app.identity && app.identity.as_of) || (app.created_at || '').slice(0, 10);
    var verdicts = app.verdicts || [];
    var evidences = app.evidence || [];

    var verdictByGate = {};
    verdicts.forEach(function (v) {
      if (v && v.gate) verdictByGate[v.gate] = v;
    });

    var evidenceByGate = {};
    evidences.forEach(function (e) {
      if (e && e.gate) {
        if (!evidenceByGate[e.gate]) evidenceByGate[e.gate] = [];
        evidenceByGate[e.gate].push(e);
      }
    });

    var dims = [];
    DIMENSION_KEYS.forEach(function (key) {
      var gate = GATE_OF[key] || '';
      var v = verdictByGate[gate];
      var evList = evidenceByGate[gate] || [];

      // G6 operational_control check
      if (key === 'operational_control' || gate === 'G6') {
        var isApproved = app.status === 'approved' || app.status === 'approved_with_conditions' || app.status === 'registered';
        var isRejected = app.status === 'rejected' || app.status === 'revoked';
        if (isApproved) {
          dims.push({
            key: key,
            gate: 'G6',
            score: 0.95,
            label: LABELS[key],
            direction: 'pass',
            confidence: 0.98,
            as_of: appAsOf,
            evidence_count: evidences.length,
            source_domains: ['registry.control_plane'],
            rationale: '责任人矩阵、Kill-Switch、回滚预案与处置 SLA 均已完备登记。',
            state: 'ok',
            progress: 'done',
          });
        } else if (isRejected) {
          dims.push({
            key: key,
            gate: 'G6',
            score: 0.2,
            label: LABELS[key],
            direction: 'fail',
            confidence: 0.95,
            as_of: appAsOf,
            evidence_count: evidences.length,
            source_domains: ['registry.control_plane'],
            rationale: '前置门禁阻断或会签未通过，未达成准入基线。',
            state: 'conflict',
            progress: 'done',
          });
        } else {
          dims.push(emptyDim(key, appAsOf));
        }
        return;
      }

      if (!v) {
        dims.push(emptyDim(key, appAsOf));
        return;
      }

      var dir = v.verdict === 'pass' ? 'pass' : (v.verdict === 'fail' ? 'fail' : 'needs_info');
      var score = dir === 'pass' ? 0.95 : (dir === 'fail' ? 0.2 : 0.6);
      var state = (BLOCKER_KEYS[key] && dir === 'fail') ? 'conflict' : (dir === 'needs_info' ? 'missing' : 'ok');
      var rationale = RATIONALE[key] || '门禁检查结果';
      if (v.failed_checks && v.failed_checks.length) {
        rationale = (dir === 'fail' ? '未通过检查项: ' : '待补证检查项: ') + v.failed_checks.join(', ');
      }

      var sources = [];
      evList.forEach(function (e) {
        if (e.collector && sources.indexOf(e.collector) === -1) sources.push(e.collector);
      });
      if (!sources.length) sources = ['gate.' + gate.toLowerCase()];

      dims.push({
        key: key,
        gate: gate,
        score: score,
        label: LABELS[key],
        direction: dir,
        confidence: 0.95,
        as_of: (v.decided_at || appAsOf || '').slice(0, 10),
        evidence_count: (v.evidence_refs && v.evidence_refs.length) || evList.length || 1,
        source_domains: sources,
        rationale: rationale,
        state: state,
        progress: 'done',
      });
    });

    return dims;
  }

  /**
   * Build fixture/demo dimensions from model_id + cutoff (deterministic, no future leak).
   */
  function buildFixtureDimensions(opts) {
    opts = opts || {};
    var modelId = String(opts.model_id || opts.ticker || 'meta-llama/Llama-3.1-8B-Instruct');
    var asOf = opts.as_of || opts.trade_date || '';
    var seed = hashSeed(modelId + '|' + asOf);
    var dims = [];
    DIMENSION_KEYS.forEach(function (key, idx) {
      var base = ((seed >> (idx % 12)) & 97) / 100;
      var score = clamp(0.58 + base * 0.38, 0.05, 0.97);
      if (key === 'vulnerability') score = clamp(score * 0.62, 0.05, 0.97);
      if (key === 'resource_fit') score = clamp(score * 0.86, 0.05, 0.97);
      // 红队评测在 fixture 模式常缺席：判缺证，不假设已通过
      if (key === 'safety_behavior' && seed % 4 === 0) {
        dims.push(emptyDim(key, asOf));
        return;
      }
      score = Math.round(score * 100) / 100;
      dims.push({
        key: key,
        gate: GATE_OF[key] || '',
        score: score,
        label: LABELS[key],
        direction: directionFromScore(score),
        confidence: Math.round((0.45 + (seed % 40) / 100) * 100) / 100,
        as_of: asOf,
        evidence_count: 1 + ((seed + idx) % 4),
        source_domains: ['scanner.local', 'policy.rules'],
        rationale: RATIONALE[key] || '基于 as_of 前扫描证据的可解释判定。',
        state: BLOCKER_KEYS[key] && score <= 0.5 ? 'conflict' : 'ok',
        progress: 'done',
      });
    });
    return dims;
  }

  function overallFromDimensions(dims, asOf) {
    var usable = (dims || []).filter(function (d) {
      return d && d.score != null && d.state !== 'missing';
    });
    if (!usable.length) {
      return {
        score: null,
        label: '证据不足',
        confidence: 0,
        coverage: 0,
        as_of: asOf || '',
        blocked: false,
        passed: [],
        risks: [],
      };
    }
    var sum = 0;
    var conf = 0;
    usable.forEach(function (d) {
      sum += d.score;
      conf += d.confidence || 0;
    });
    var score = sum / usable.length;

    var blocked = (dims || []).some(function (d) {
      return d && BLOCKER_KEYS[d.key] && (d.direction === 'fail' || d.state === 'missing');
    });

    var label;
    if (blocked) label = '建议阻断（模拟）';
    else if (score >= 0.75) label = '建议准入（模拟）';
    else label = '带条件准入（模拟）';

    var sorted = usable.slice().sort(function (a, b) {
      return (b.score || 0) - (a.score || 0);
    });
    function describe(d) {
      return (d.gate ? d.gate + ' ' : '') + d.label + ' ' + d.score;
    }
    return {
      score: Math.round(score * 100) / 100,
      label: label,
      confidence: Math.round((conf / usable.length) * 100) / 100,
      coverage: Math.round((usable.length / DIMENSION_KEYS.length) * 100) / 100,
      as_of: asOf || usable[0].as_of || '',
      blocked: blocked,
      passed: sorted
        .filter(function (d) {
          return d.direction === 'pass';
        })
        .slice(0, 3)
        .map(describe),
      risks: sorted
        .slice()
        .reverse()
        .filter(function (d) {
          return d.direction === 'fail' || d.direction === 'needs_info';
        })
        .slice(0, 3)
        .map(describe),
    };
  }

  function mergeEventDimension(dims, payload) {
    if (!payload || !payload.key) return dims;
    var next = (dims || []).slice();
    var found = false;
    for (var i = 0; i < next.length; i++) {
      if (next[i].key === payload.key) {
        next[i] = Object.assign({}, next[i], payload);
        found = true;
        break;
      }
    }
    if (!found) next.push(Object.assign(emptyDim(payload.key, payload.as_of), payload));
    return next;
  }

  function filterGroup(dims, groupId) {
    var g = GROUPS[groupId] || GROUPS.summary;
    var set = {};
    g.keys.forEach(function (k) {
      set[k] = true;
    });
    return (dims || []).filter(function (d) {
      return set[d.key];
    });
  }

  function dirLabel(dir) {
    if (dir === 'pass') return '达标 ✓';
    if (dir === 'fail') return '阻断 ✗';
    if (dir === 'needs_info') return '待补证 ?';
    return '未采集 ·';
  }

  function render(root, state) {
    if (!root || !global.document) return;
    var dims = state.dimensions || [];
    var overall = state.overall || overallFromDimensions(dims, state.as_of);
    var groupId = state.group || 'summary';

    var scoreEl = root.querySelector('#overall-score') || global.document.getElementById('overall-score');
    var metaEl = root.querySelector('#overall-meta') || global.document.getElementById('overall-meta');
    var passedEl = global.document.getElementById('judgment-pass-signals');
    var riskEl = global.document.getElementById('judgment-risk-signals');
    var tabs = global.document.getElementById('judgment-tabs');
    var body = global.document.getElementById('judgment-matrix-body');

    if (scoreEl) scoreEl.textContent = overall.score == null ? '—' : String(overall.score);
    if (metaEl) {
      metaEl.textContent =
        (overall.label || '—') +
        ' · 置信 ' +
        (overall.confidence != null ? overall.confidence : '—') +
        ' · 门禁覆盖 ' +
        Math.round((overall.coverage || 0) * 100) +
        '% · as_of ' +
        (overall.as_of || '—');
    }
    if (passedEl) {
      passedEl.innerHTML = (overall.passed && overall.passed.length ? overall.passed : ['—'])
        .map(function (x) {
          return '<li>' + String(x) + '</li>';
        })
        .join('');
    }
    if (riskEl) {
      riskEl.innerHTML = (overall.risks && overall.risks.length ? overall.risks : ['—'])
        .map(function (x) {
          return '<li>' + String(x) + '</li>';
        })
        .join('');
    }
    if (tabs) {
      tabs.innerHTML = Object.keys(GROUPS)
        .map(function (id) {
          var g = GROUPS[id];
          return (
            '<button type="button" role="tab" class="judgment-tab" data-group="' +
            id +
            '" aria-selected="' +
            (id === groupId ? 'true' : 'false') +
            '">' +
            g.label +
            '</button>'
          );
        })
        .join('');
    }
    if (body) {
      var rows = filterGroup(dims, groupId);
      if (!rows.length) {
        body.innerHTML =
          '<tr><td colspan="8" style="color:#91a9c3">该门禁分组暂无维度数据</td></tr>';
      } else {
        body.innerHTML = rows
          .map(function (d) {
            return (
              '<tr class="judgment-row" data-key="' +
              d.key +
              '"><td><span class="judgment-gate">' +
              (d.gate || GATE_OF[d.key] || '—') +
              '</span> ' +
              (d.label || d.key) +
              (BLOCKER_KEYS[d.key] ? ' <small class="judgment-blocker">Blocker</small>' : '') +
              '</td><td>' +
              (d.score == null ? '—' : d.score) +
              '</td><td class="judgment-dir ' +
              (d.direction || 'unknown') +
              '">' +
              dirLabel(d.direction) +
              '</td><td>' +
              (d.confidence == null ? '—' : d.confidence) +
              '</td><td>' +
              (d.evidence_count || 0) +
              '</td><td>' +
              (d.as_of || '—') +
              '</td><td><span class="judgment-state ' +
              (d.state || '') +
              '">' +
              (d.state || 'missing') +
              '</span></td><td>' +
              String(d.rationale || '') +
              (d.source_domains && d.source_domains.length
                ? ' <small style="color:#7894b2">[' +
                  d.source_domains.join(', ') +
                  ']</small>'
                : '') +
              '</td></tr>'
            );
          })
          .join('');
      }
    }
  }

  global.EngineJudgment = {
    DIMENSION_KEYS: DIMENSION_KEYS,
    GROUPS: GROUPS,
    LABELS: LABELS,
    GATE_OF: GATE_OF,
    BLOCKER_KEYS: BLOCKER_KEYS,
    emptyDim: emptyDim,
    buildFixtureDimensions: buildFixtureDimensions,
    dimensionsFromVerdicts: dimensionsFromVerdicts,
    overallFromDimensions: overallFromDimensions,
    mergeEventDimension: mergeEventDimension,
    filterGroup: filterGroup,
    directionFromScore: directionFromScore,
    dirLabel: dirLabel,
    render: render,
  };
})(typeof window !== 'undefined' ? window : globalThis);
