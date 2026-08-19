/**
 * P12 — Multi-dimensional judgment matrix for Engine Live Cockpit.
 * Fixture-safe, as_of aware; never invents revenue/valuation as hard facts.
 */
(function (global) {
  'use strict';

  var DIMENSION_KEYS = [
    'quant',
    'analyst',
    'consensus',
    'valuation',
    'growth',
    'profitability',
    'momentum',
    'risk',
    'eps_revision',
    'liquidity',
    'event_impact',
  ];

  var GROUPS = {
    summary: { id: 'summary', label: '评级摘要', keys: ['quant', 'analyst', 'consensus'] },
    fundamentals: {
      id: 'fundamentals',
      label: '基本面',
      keys: ['valuation', 'growth', 'profitability'],
    },
    revisions: { id: 'revisions', label: '预期与修正', keys: ['eps_revision', 'consensus'] },
    market: { id: 'market', label: '市场行为', keys: ['momentum', 'liquidity'] },
    risk: { id: 'risk', label: '风险与事件', keys: ['risk', 'event_impact'] },
  };

  var LABELS = {
    quant: '量化综合',
    analyst: '分析师观点',
    consensus: '市场共识',
    valuation: '估值',
    growth: '成长',
    profitability: '盈利能力',
    momentum: '动量',
    risk: '风险',
    eps_revision: 'EPS 修正',
    liquidity: '流动性',
    event_impact: '事件冲击',
  };

  function clamp(n, lo, hi) {
    return Math.max(lo, Math.min(hi, n));
  }

  function emptyDim(key, asOf) {
    return {
      key: key,
      score: null,
      label: LABELS[key] || key,
      direction: 'unknown',
      confidence: 0,
      as_of: asOf || '',
      evidence_count: 0,
      source_domains: [],
      rationale: '暂无证据',
      state: 'missing',
      progress: 'pending',
    };
  }

  function directionFromScore(score) {
    if (score == null || !isFinite(score)) return 'unknown';
    if (score >= 0.58) return 'up';
    if (score <= 0.42) return 'down';
    return 'flat';
  }

  function hashSeed(str) {
    var h = 0;
    var s = String(str || '');
    for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
    return Math.abs(h);
  }

  /**
   * Build fixture/demo dimensions from ticker + cutoff (deterministic, no future leak).
   */
  function buildFixtureDimensions(opts) {
    opts = opts || {};
    var ticker = String(opts.ticker || 'NVDA').toUpperCase();
    var asOf = opts.as_of || opts.trade_date || '';
    var seed = hashSeed(ticker + '|' + asOf);
    var dims = [];
    DIMENSION_KEYS.forEach(function (key, idx) {
      var base = ((seed >> (idx % 12)) & 97) / 100;
      var score = clamp(0.35 + base * 0.5 + (idx % 3) * 0.03, 0.05, 0.95);
      var missing = key === 'eps_revision' && ticker.length > 5;
      if (missing) {
        dims.push(emptyDim(key, asOf));
        return;
      }
      dims.push({
        key: key,
        score: Math.round(score * 100) / 100,
        label: LABELS[key],
        direction: directionFromScore(score),
        confidence: Math.round((0.45 + (seed % 40) / 100) * 100) / 100,
        as_of: asOf,
        evidence_count: 1 + ((seed + idx) % 4),
        source_domains: ['fixture.local', 'research.sim'],
        rationale:
          key === 'valuation'
            ? '模拟估值带：仅研究用途，非真实市值/PE。'
            : key === 'risk'
              ? '风险启发式：波动与事件不确定性（模拟）。'
              : '基于 as_of 前 fixture 证据的可解释演示分数。',
        state: key === 'valuation' && score > 0.7 ? 'conflict' : 'ok',
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
        bull: [],
        bear: [],
      };
    }
    var sum = 0;
    var conf = 0;
    usable.forEach(function (d) {
      sum += d.score;
      conf += d.confidence || 0;
    });
    var score = sum / usable.length;
    var sorted = usable.slice().sort(function (a, b) {
      return (b.score || 0) - (a.score || 0);
    });
    return {
      score: Math.round(score * 100) / 100,
      label: score >= 0.58 ? '偏多（模拟）' : score <= 0.42 ? '偏空（模拟）' : '中性（模拟）',
      confidence: Math.round((conf / usable.length) * 100) / 100,
      coverage: Math.round((usable.length / DIMENSION_KEYS.length) * 100) / 100,
      as_of: asOf || usable[0].as_of || '',
      bull: sorted
        .filter(function (d) {
          return d.direction === 'up';
        })
        .slice(0, 3)
        .map(function (d) {
          return d.label + ' ' + d.score;
        }),
      bear: sorted
        .filter(function (d) {
          return d.direction === 'down';
        })
        .slice(0, 3)
        .map(function (d) {
          return d.label + ' ' + d.score;
        }),
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
    if (dir === 'up') return '上行 ↑';
    if (dir === 'down') return '下行 ↓';
    if (dir === 'flat') return '中性 →';
    return '未知 ·';
  }

  function render(root, state) {
    if (!root || !global.document) return;
    var dims = state.dimensions || [];
    var overall = state.overall || overallFromDimensions(dims, state.as_of);
    var groupId = state.group || 'summary';

    var scoreEl = root.querySelector('#overall-score') || global.document.getElementById('overall-score');
    var metaEl = root.querySelector('#overall-meta') || global.document.getElementById('overall-meta');
    var bull = global.document.getElementById('judgment-bull-signals');
    var bear = global.document.getElementById('judgment-bear-signals');
    var tabs = global.document.getElementById('judgment-tabs');
    var body = global.document.getElementById('judgment-matrix-body');

    if (scoreEl) scoreEl.textContent = overall.score == null ? '—' : String(overall.score);
    if (metaEl) {
      metaEl.textContent =
        (overall.label || '—') +
        ' · 置信 ' +
        (overall.confidence != null ? overall.confidence : '—') +
        ' · 覆盖 ' +
        Math.round((overall.coverage || 0) * 100) +
        '% · as_of ' +
        (overall.as_of || '—');
    }
    if (bull) {
      bull.innerHTML = (overall.bull && overall.bull.length
        ? overall.bull
        : ['—']
      )
        .map(function (x) {
          return '<li>' + String(x) + '</li>';
        })
        .join('');
    }
    if (bear) {
      bear.innerHTML = (overall.bear && overall.bear.length
        ? overall.bear
        : ['—']
      )
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
          '<tr><td colspan="8" style="color:#91a9c3">该分组暂无维度数据</td></tr>';
      } else {
        body.innerHTML = rows
          .map(function (d) {
            return (
              '<tr class="judgment-row" data-key="' +
              d.key +
              '"><td>' +
              (d.label || d.key) +
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
    emptyDim: emptyDim,
    buildFixtureDimensions: buildFixtureDimensions,
    overallFromDimensions: overallFromDimensions,
    mergeEventDimension: mergeEventDimension,
    filterGroup: filterGroup,
    dirLabel: dirLabel,
    render: render,
  };
})(typeof window !== 'undefined' ? window : globalThis);
