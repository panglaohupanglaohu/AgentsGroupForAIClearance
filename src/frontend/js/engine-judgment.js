/**
 * 准入门禁矩阵 —— 对齐 Lenovo AI 模型准入标准 §3/§6/§7/§8。
 *
 * 一个门禁一行，直接映射后端 GateVerdict；不再虚构后端不产出的子维度，
 * 也不在未取证时编造分数（fail-closed：缺证即 missing，绝不默认放行）。
 */
(function (global) {
  'use strict';

  /** 与 domain/model_clearance/standard.py 的 GATE_DEFINITIONS 一一对应。 */
  var GATES = [
    {
      key: 'G0',
      section: '3',
      label: '禁止部署筛查',
      blocker: true,
      group: 'context',
      rationale: '标准 §3 硬红线：命中任一禁止部署形态即不可通过，且不受其它门禁结果影响。',
    },
    {
      key: 'G1',
      section: '6.1',
      label: '模型制品与溯源',
      blocker: true,
      group: 'context',
      rationale: '来源血缘、不可变版本与哈希、许可条款、签名完整性与训练数据透明度可独立验证。',
    },
    {
      key: 'G2',
      section: '6.2',
      label: '软件供应链',
      blocker: true,
      group: 'analysis',
      rationale: 'AI-BOM 完备、序列化格式安全、CVE 已清、受控仓库与版本锁定、回滚路径可用。',
    },
    {
      key: 'G3',
      section: '6.3',
      label: '安全、安全性与行为评估',
      blocker: false,
      group: 'analysis',
      rationale: '提示注入、数据外泄、不安全代码生成、越狱易感性、隐私泄露与偏见的量化评估。',
    },
    {
      key: 'G4',
      section: '6.4',
      label: '威胁情报与红队',
      blocker: false,
      group: 'planning',
      rationale: '已知漏洞与攻击手法情报比对，以及对抗与红队测试发现项的定级与处置。',
    },
    {
      key: 'G5',
      section: '7.1',
      label: '部署与数据流',
      blocker: true,
      group: 'planning',
      rationale: '托管环境受控、出向流量受限、工作负载隔离、监控审计与技术护栏就位。',
    },
    {
      key: 'G6',
      section: '7.2',
      label: '模型权限与工具访问',
      blocker: true,
      group: 'risk',
      rationale: '工具访问白名单、最小权限、自主动作受限、后果性操作需人工批准、生成代码视为不可信。',
    },
    {
      key: 'G7',
      section: '7.3',
      label: '用例、数据与法务',
      blocker: true,
      group: 'risk',
      rationale: '许可证商用条款、禁止用途、隐私影响、知识产权与人工监督责任的法务判定。',
    },
    {
      key: 'G8',
      section: '8',
      label: '持续保障',
      blocker: false,
      group: 'portfolio',
      rationale: '具名负责人、监控、漏洞管理、事件响应、回滚与暂停/吊销能力的可执行性核验。',
    },
  ];

  var GATE_BY_KEY = {};
  GATES.forEach(function (g) {
    GATE_BY_KEY[g.key] = g;
  });

  var DIMENSION_KEYS = GATES.map(function (g) {
    return g.key;
  });

  var LABELS = {};
  var GATE_OF = {};
  var BLOCKER_KEYS = {};
  var RATIONALE = {};
  GATES.forEach(function (g) {
    LABELS[g.key] = '§' + g.section + ' ' + g.label;
    GATE_OF[g.key] = g.key;
    if (g.blocker) BLOCKER_KEYS[g.key] = true;
    RATIONALE[g.key] = g.rationale;
  });

  /** 分组即流水线站点，与后端 GATE_PHASE 一致。 */
  var GROUPS = {
    summary: { id: 'summary', label: '全部门禁', keys: DIMENSION_KEYS.slice() },
    context: { id: 'context', label: '登记 §3/§6.1', keys: ['G0', 'G1'] },
    analysis: { id: 'analysis', label: '供应链与行为 §6.2/§6.3', keys: ['G2', 'G3'] },
    planning: { id: 'planning', label: '红队与部署 §6.4/§7.1', keys: ['G4', 'G5'] },
    risk: { id: 'risk', label: '权限与法务 §7.2/§7.3', keys: ['G6', 'G7'] },
    portfolio: { id: 'portfolio', label: '持续保障 §8', keys: ['G8'] },
  };

  function emptyDim(key, asOf) {
    var g = GATE_BY_KEY[key] || {};
    return {
      key: key,
      gate: key,
      score: null,
      label: LABELS[key] || key,
      direction: 'unknown',
      confidence: 0,
      as_of: asOf || '',
      evidence_count: 0,
      source_domains: [],
      rationale: g.rationale || '证据缺失，按 fail-closed 处理，不得默认放行',
      state: 'missing',
      progress: 'pending',
    };
  }

  /** 未取证时的初始矩阵：9 行全部 missing，不编造分数。 */
  function emptyDimensions(asOf) {
    return DIMENSION_KEYS.map(function (key) {
      return emptyDim(key, asOf);
    });
  }

  function directionFromScore(score) {
    if (score == null || !isFinite(score)) return 'unknown';
    if (score >= 0.75) return 'pass';
    if (score <= 0.5) return 'fail';
    return 'needs_info';
  }

  /** 把 GateOrchestrator 的 verdict + evidence 映射成矩阵行。 */
  function dimensionsFromVerdicts(app, asOf) {
    if (!app) return [];
    var appAsOf = asOf || (app.identity && app.identity.as_of) || (app.created_at || '').slice(0, 10);

    var verdictByGate = {};
    (app.verdicts || []).forEach(function (v) {
      if (v && v.gate) verdictByGate[v.gate] = v;
    });

    var evidenceByGate = {};
    (app.evidence || []).forEach(function (e) {
      if (e && e.gate) {
        if (!evidenceByGate[e.gate]) evidenceByGate[e.gate] = [];
        evidenceByGate[e.gate].push(e);
      }
    });

    return DIMENSION_KEYS.map(function (key) {
      var v = verdictByGate[key];
      if (!v) return emptyDim(key, appAsOf);

      var evList = evidenceByGate[key] || [];
      var dir = v.verdict === 'pass' ? 'pass' : v.verdict === 'fail' ? 'fail' : 'needs_info';
      var score = dir === 'pass' ? 0.95 : dir === 'fail' ? 0.2 : 0.6;
      var state = BLOCKER_KEYS[key] && dir === 'fail' ? 'conflict' : dir === 'needs_info' ? 'missing' : 'ok';
      var rationale = RATIONALE[key] || '门禁检查结果';
      if (v.failed_checks && v.failed_checks.length) {
        rationale = (dir === 'fail' ? '未通过检查项: ' : '待补证检查项: ') + v.failed_checks.join(', ');
      }

      var sources = [];
      evList.forEach(function (e) {
        if (e.collector && sources.indexOf(e.collector) === -1) sources.push(e.collector);
      });
      if (!sources.length) sources = ['gate.' + key.toLowerCase()];

      return {
        key: key,
        gate: key,
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
      };
    });
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

    // Blocker 门禁失败或缺证即整体阻断，平均分不得覆盖（标准 §9）。
    var blocked = (dims || []).some(function (d) {
      return d && BLOCKER_KEYS[d.key] && (d.direction === 'fail' || d.state === 'missing');
    });

    var label;
    if (blocked) label = '不予准入 / 阻断';
    else if (score >= 0.75) label = '准入';
    else label = '带条件准入';

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
    for (var i = 0; i < next.length; i++) {
      if (next[i].key === payload.key) {
        next[i] = Object.assign({}, next[i], payload);
        return next;
      }
    }
    next.push(Object.assign(emptyDim(payload.key, payload.as_of), payload));
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
          return (
            '<button type="button" role="tab" class="judgment-tab" data-group="' +
            id +
            '" aria-selected="' +
            (id === groupId ? 'true' : 'false') +
            '">' +
            GROUPS[id].label +
            '</button>'
          );
        })
        .join('');
    }
    if (body) {
      var rows = filterGroup(dims, groupId);
      if (!rows.length) {
        body.innerHTML = '<tr><td colspan="8" style="color:#91a9c3">该门禁分组暂无维度数据</td></tr>';
      } else {
        body.innerHTML = rows
          .map(function (d) {
            return (
              '<tr class="judgment-row" data-key="' +
              d.key +
              '"><td><span class="judgment-gate">' +
              (d.gate || d.key) +
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
                ? ' <small style="color:#7894b2">[' + d.source_domains.join(', ') + ']</small>'
                : '') +
              '</td></tr>'
            );
          })
          .join('');
      }
    }
  }

  global.EngineJudgment = {
    GATES: GATES,
    DIMENSION_KEYS: DIMENSION_KEYS,
    GROUPS: GROUPS,
    LABELS: LABELS,
    GATE_OF: GATE_OF,
    BLOCKER_KEYS: BLOCKER_KEYS,
    emptyDim: emptyDim,
    emptyDimensions: emptyDimensions,
    dimensionsFromVerdicts: dimensionsFromVerdicts,
    overallFromDimensions: overallFromDimensions,
    mergeEventDimension: mergeEventDimension,
    filterGroup: filterGroup,
    directionFromScore: directionFromScore,
    dirLabel: dirLabel,
    render: render,
  };
})(typeof window !== 'undefined' ? window : globalThis);
