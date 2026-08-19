/**
 * AI Model Entry Clearance — Live Cockpit controller (P8).
 * Depends on: engine-state.js, engine-reducer.js, api.js
 */
(function () {
  'use strict';

  var ES = window.EngineState;
  var ER = window.EngineReducer;
  var engineState = ES.create();
  var draftModules = []; // localStorage draft only
  var pollTimer = null;
  var eventSource = null;
  var sidebarApi = null;
  var badgeCache = {
    docs_ai: '—',
    modules_team: 0,
    sources_selected: 0,
  };
  var judgmentState = {
    dimensions: [],
    overall: null,
    group: 'summary',
    as_of: '',
  };

  function api() { return window.api; }
  function $(id) { return document.getElementById(id); }
  function esc(s) { return ER.esc(s); }
  function safeText(s) { return ER.safeText(s); }

  function today() {
    return new Date().toISOString().slice(0, 10);
  }

  function readForm() {
    return {
      ticker: ($('ticker').value || '').trim().toUpperCase(),
      trade_date: $('trade_date').value,
      sector: $('sector') ? $('sector').value : '',
      initial_cash: Number($('cash').value || 100000),
      debate_rounds: Number($('debate').value || 1),
      risk_rounds: Number($('risk').value || 1),
      mode: $('mode').value || 'fixture',
    };
  }

  function runView() {
    if (!engineState.runId) return null;
    return { run_id: engineState.runId, status: engineState.status };
  }

  function renderReportIndex(index) {
    var root = $('reports');
    if (!root) return;
    index = index || {};
    var decision = index.final_decision || {};
    var sections = index.sections || {};
    var labels = {
      market: '市场环境', sentiment: '情绪观察', news: '新闻与事件', fundamentals: '基本面',
      bull_bear_debate: '多空辩论', trade_plan: '交易规划', risk_debate: '风险辩论', final_decision: '最终裁决'
    };
    var keys = Object.keys(sections);
    if (!keys.length && !decision.action) {
      root.innerHTML = '<div class="report-empty">模拟尚未生成报告。启动后，这里会把技术索引整理成易读的研究小结。</div>';
      return;
    }
    var action = decision.action || '待定';
    var confidence = decision.confidence == null ? '—' : Math.round(Number(decision.confidence) * 100) + '%';
    var rationale = safeText(decision.rationale || '等待组合管理 Agent 给出裁决。');
    root.innerHTML = renderPipelineFlow(index) + '<div class="report-summary">' +
      '<div class="report-summary-card"><strong>这次模拟看什么</strong><span>' + safeText(index.ticker || '未指定标的') + ' · 截止 ' + safeText(index.trade_date || '—') + '</span></div>' +
      '<div class="report-summary-card"><strong>模拟结论</strong><span>' + safeText(action) + ' · 置信度 ' + safeText(confidence) + '</span></div>' +
      '<div class="report-summary-card"><strong>证据上下文</strong><span>' + (Array.isArray(index.context_versions) ? index.context_versions.length : 0) + ' 个已冻结研究版本 · ' + safeText(index.mode || 'fixture') + ' 模式</span></div>' +
      '</div><div class="report-summary-card"><strong>一句话解读</strong><span>' + rationale + '</span></div>' +
      '<div class="report-sections">' + keys.map(function (key) { return '<div class="report-section"><b>' + safeText(labels[key] || key) + '</b><small>已生成研究小节，可在运行目录中追溯</small></div>'; }).join('') + '</div>';
  }

  function renderPipelineFlow(index) {
    var versions = Array.isArray(index.context_versions) ? index.context_versions.slice(0, 8) : [];
    var stage2 = ['market_analyst', 'sentiment_analyst', 'news_analyst', 'fundamentals_analyst'];
    var stage3 = ['bull_researcher', 'bear_researcher', 'research_manager'];
    var stage4 = ['trader', 'aggressive_risk', 'neutral_risk', 'conservative_risk'];
    var final = index.final_decision || {};
    var cols = [90, 310, 530, 750, 970];
    var names = { market_analyst:'Market', sentiment_analyst:'Sentiment', news_analyst:'News', fundamentals_analyst:'Fundamentals', bull_researcher:'Bull Researcher', bear_researcher:'Bear Researcher', research_manager:'Research Manager', trader:'Trader', aggressive_risk:'Aggressive Risk', neutral_risk:'Neutral Risk', conservative_risk:'Conservative Risk' };
    function node(x, y, label, tone) { var width = Math.max(92, Math.min(160, label.length * 8 + 24)); return '<g class="flow-node ' + tone + '"><rect x="' + (x - width / 2) + '" y="' + (y - 18) + '" width="' + width + '" height="36" rx="8"></rect><text x="' + x + '" y="' + (y + 4) + '" text-anchor="middle">' + esc(label) + '</text></g>'; }
    function edge(x1, y1, x2, y2, tone) { return '<line class="flow-edge ' + tone + '" x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 + '" marker-end="url(#flow-arrow)"></line>'; }
    var versionNodes = versions.map(function (v, i) { return { x:cols[0], y:92 + i * 48, label:'AI 60 v' + (v.version || '—'), tone:'source' }; });
    var analystNodes = stage2.map(function (key, i) { return { x:cols[1], y:125 + i * 105, label:names[key], tone:'analyst' }; });
    var debateNodes = stage3.map(function (key, i) { return { x:cols[2], y:150 + i * 130, label:names[key], tone:'debate' }; });
    var riskNodes = stage4.map(function (key, i) { return { x:cols[3], y:105 + i * 105, label:names[key], tone:'risk' }; });
    var finalNode = { x:cols[4], y:270, label:(final.action || 'PENDING') + ' · ' + (final.ticker || index.ticker || '—') + ' (' + Math.round(Number(final.confidence || 0) * 100) + '%)', tone:'decision' };
    var allNodes = versionNodes.concat(analystNodes, debateNodes, riskNodes, [finalNode]);
    var edges = '';
    versionNodes.forEach(function (s) { analystNodes.forEach(function (a) { edges += edge(s.x + 48, s.y, a.x - 70, a.y, 'source-edge'); }); });
    analystNodes.forEach(function (a) { debateNodes.forEach(function (d) { edges += edge(a.x + 74, a.y, d.x - 80, d.y, 'analysis-edge'); }); });
    debateNodes.forEach(function (d) { riskNodes.forEach(function (r) { edges += edge(d.x + 82, d.y, r.x - 76, r.y, 'risk-edge'); }); });
    riskNodes.forEach(function (r) { edges += edge(r.x + 78, r.y, finalNode.x - 92, finalNode.y, r.label === 'Trader' ? 'approved-edge' : 'counter-edge'); });
    var headings = [['阶段 1','数据获取'], ['阶段 2','专业分析'], ['阶段 3','辩论与综合'], ['阶段 4','风险控制'], ['阶段 5','最终执行']];
    return '<section class="report-flow" aria-label="模型准入评审流程"><div class="report-flow-head"><div><strong>Model Clearance Pipeline</strong><span>信息版本 → 专业分析 → 规则策略 → 风险门禁 → 会签裁决</span></div><b>动态评审图</b></div><svg viewBox="0 0 1060 520" role="img" aria-label="从证据采集到最终准入裁决的流程图"><defs><marker id="flow-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z"></path></marker></defs>' + headings.map(function (h, i) { return '<text class="flow-stage" x="' + cols[i] + '" y="26" text-anchor="middle">' + h[0] + '</text><text class="flow-stage-sub" x="' + cols[i] + '" y="45" text-anchor="middle">' + h[1] + '</text>'; }).join('') + edges + allNodes.map(function (n) { return node(n.x, n.y, n.label, n.tone); }).join('') + '</svg></section>';
  }

  function syncPrimaryButton() {
    var form = readForm();
    var d = ES.deriveStartState(form, runView());
    var btn = $('btn-engine-start');
    if (btn) {
      btn.textContent = d.label;
      btn.disabled = !!d.disabled;
      btn.dataset.action = d.action;
    }
    var hint = $('engine-start-hint');
    if (hint) {
      if (d.errors && d.errors.length) {
        hint.textContent = d.errors.join('；');
        hint.className = 'stat warning-hint';
      } else if (!draftModules.length) {
        hint.textContent = '未装配信息模块时将使用默认上下文（as_of 截止内可见文档）。';
        hint.className = 'stat muted';
      } else {
        hint.textContent = '已装配 ' + draftModules.length + ' 个模块；运行将冻结为不可变快照。';
        hint.className = 'stat muted';
      }
    }
    // Sync side buttons
    if ($('btn-start')) {
      $('btn-start').disabled =
        !engineState.runId ||
        engineState.status === 'running' ||
        engineState.status === 'completed';
    }
    if ($('btn-cancel')) {
      $('btn-cancel').disabled =
        engineState.status !== 'running' && engineState.status !== 'queued';
    }
    if ($('run-id')) $('run-id').textContent = engineState.runId || '—';
    if ($('run-status')) $('run-status').textContent = engineState.status || 'idle';
  }

  function setInsight(id, text, tone, active) {
    var card = $(id);
    if (!card) return;
    var p = card.querySelector('p');
    if (p) p.textContent = safeText(text);
    card.classList.remove('active', 'positive', 'warning');
    if (tone) card.classList.add(tone);
    if (active) card.classList.add('active');
  }

  function refreshOverflowHints() {
    document.querySelectorAll('.parts-bank').forEach(function (rail) {
      var overflowing = rail.scrollWidth > rail.clientWidth + 1;
      rail.classList.toggle('is-overflowing', overflowing);
      rail.setAttribute(
        'aria-label',
        (rail.getAttribute('aria-label') || '零件栏') + (overflowing ? '（可横向滚动）' : '')
      );
    });
    var road = $('road-modules-scroll');
    var hint = $('road-scroll-hint');
    if (road && hint) {
      var ov = road.scrollWidth > road.clientWidth + 1;
      hint.classList.toggle('is-visible', ov);
      hint.style.display = ov ? 'inline' : 'none';
    }
    var ph = $('parts-scroll-hint');
    if (ph) {
      var any = false;
      document.querySelectorAll('.parts-bank').forEach(function (r) {
        if (r.scrollWidth > r.clientWidth + 1) any = true;
      });
      ph.classList.toggle('is-visible', any);
    }
  }

  function renderJudgmentPanel() {
    if (!window.EngineJudgment) return;
    var form = readForm();
    if (!judgmentState.dimensions.length) {
      judgmentState.as_of = form.trade_date || today();
      judgmentState.dimensions = window.EngineJudgment.buildFixtureDimensions({
        ticker: form.ticker,
        as_of: judgmentState.as_of,
      });
      judgmentState.overall = window.EngineJudgment.overallFromDimensions(
        judgmentState.dimensions,
        judgmentState.as_of
      );
    }
    window.EngineJudgment.render(document, judgmentState);
  }

  function renderFromState() {
    var s = engineState;
    var phase = s.phase || 'assembly';
    var route = ER.routeKey(phase);
    var routeOrder = ['context', 'judgment', 'plan', 'risk', 'portfolio'];
    var routeIndex = routeOrder.indexOf(route);
    if (routeIndex < 0) routeIndex = 0;

    var phaseLabels = {
      assembly: '装配中',
      context: '装载证据',
      analysis: '形成判断',
      planning: '规划路线',
      debate: '合规辩论',
      trading: '资源推演',
      risk: '风险门禁',
      portfolio: '准入签发',
      reflection: '准入审计',
      budget: '预算门禁',
    };

    if ($('engine-phase')) {
      $('engine-phase').textContent = phaseLabels[phase] || s.status || '待启动';
    }
    if ($('engine-progress')) {
      $('engine-progress').textContent = (s.progress || 0) + '%';
    }
    if ($('engine-progress-bar')) {
      $('engine-progress-bar').style.width = (s.progress || 0) + '%';
    }
    if ($('engine-hud')) {
      $('engine-hud').classList.toggle('live', s.status === 'running');
      $('engine-hud').classList.toggle('reconnect', s.connection === 'reconnecting');
    }
    if ($('engine-conn')) {
      var connMap = {
        idle: '未连接',
        polling: '轮询',
        live: 'SSE',
        reconnecting: '重连中',
        error: '连接错误',
      };
      $('engine-conn').textContent = connMap[s.connection] || s.connection;
    }

    document.querySelectorAll('.route-stop').forEach(function (stop) {
      var key = stop.getAttribute('data-route');
      var idx = routeOrder.indexOf(key);
      stop.classList.toggle('active', key === route);
      stop.classList.toggle('done', idx >= 0 && idx < routeIndex);
    });

    // Insights from reducer
    var c = s.insights.context;
    setInsight(
      'context-card',
      c
        ? c.summary
        : '等待信息源团队和历史文档装载。',
      null,
      route === 'context'
    );
    var j = s.insights.judgment;
    setInsight(
      'judgment-card',
      j
        ? (j.claim +
            (j.confidence != null ? ' · 置信 ' + Math.round(j.confidence * 100) + '%' : '') +
            (j.direction ? ' · ' + j.direction : ''))
        : '等待市场分析师启动。',
      null,
      route === 'judgment'
    );
    var p = s.insights.plan;
    setInsight(
      'plan-card',
      p
        ? p.objective ||
            JSON.stringify({
              base: p.base_case && p.base_case.action,
              bull: p.bull_case && p.bull_case.action,
              bear: p.bear_case && p.bear_case.action,
            })
        : '等待研究图谱规划路线。',
      null,
      route === 'plan'
    );
    var v = s.insights.valuePath;
    setInsight(
      'revenue-card',
      v
        ? (v.summary || '') +
            (v.action ? ' · 推荐动作 ' + v.action : '') +
            '（资源推演路径，非法律保证）'
        : '尚未形成资源与成本路径。',
      null,
      route === 'risk' && !!v
    );
    var r = s.insights.risk;
    setInsight(
      'risk-card',
      r ? (r.gate + '：' + r.reason) : '等待策略引擎与红队审查节点。',
      r && r.gate === 'rejected' ? 'warning' : r ? 'warning' : null,
      route === 'risk'
    );
    var pf = s.insights.portfolio;
    setInsight(
      'portfolio-card',
      pf
        ? pf.summary + (pf.disclaimer ? ' · ' + pf.disclaimer : '')
        : '待审，等待 Clearance Board 裁决。',
      'positive',
      route === 'portfolio'
    );

    // P12: refresh multi-dim matrix when analysis phase advances
    if (window.EngineJudgment && (route === 'judgment' || s.status === 'running' || s.status === 'completed')) {
      var formJ = readForm();
      judgmentState.as_of = formJ.trade_date || judgmentState.as_of || today();
      if (!judgmentState.dimensions.length || s.status === 'completed') {
        judgmentState.dimensions = window.EngineJudgment.buildFixtureDimensions({
          ticker: formJ.ticker,
          as_of: judgmentState.as_of,
        });
      }
      // Merge structured judgment from last analysis event if present
      s.events.forEach(function (ev) {
        if (ev && ev.structured && ev.structured.judgment_dimensions) {
          (ev.structured.judgment_dimensions || []).forEach(function (d) {
            judgmentState.dimensions = window.EngineJudgment.mergeEventDimension(
              judgmentState.dimensions,
              d
            );
          });
        }
        if (ev && ev.structured && ev.structured.dimension) {
          judgmentState.dimensions = window.EngineJudgment.mergeEventDimension(
            judgmentState.dimensions,
            ev.structured.dimension
          );
        }
      });
      judgmentState.overall = window.EngineJudgment.overallFromDimensions(
        judgmentState.dimensions,
        judgmentState.as_of
      );
      renderJudgmentPanel();
    }

    refreshOverflowHints();

    // Timeline — text only
    var box = $('timeline');
    if (box) {
      if (!s.events.length) {
        box.innerHTML = '<div class="empty">创建并启动 Engine 后显示节点进度</div>';
      } else {
        box.innerHTML = s.events
          .slice()
          .sort(function (a, b) { return (a.seq || 0) - (b.seq || 0); })
          .map(function (e) {
            return (
              '<div class="event" data-seq="' +
              esc(e.seq) +
              '"><div class="meta">#' +
              esc(e.seq) +
              ' · ' +
              esc(e.phase) +
              ' · ' +
              esc(e.participant) +
              ' · ' +
              esc(e.status) +
              '</div><div>' +
              esc(safeText(e.content)) +
              '</div></div>'
            );
          })
          .join('');
        box.scrollTop = box.scrollHeight;
      }
    }

    syncPrimaryButton();
  }

  function applySim(sim) {
    if (!sim) return;
    engineState.runId = sim.application_id || sim.run_id;
    engineState.status = sim.status || engineState.status;
    engineState.graphShape = sim.graph_shape || engineState.graphShape || ['G1', 'G2', 'G3', 'G4', 'G5', 'G6'];
    if (sim.assembly_snapshot) {
      engineState.assembly = {
        modules: sim.assembly_snapshot.modules || [],
        snapshotHash: sim.assembly_snapshot.snapshot_hash || null,
        warnings: sim.assembly_snapshot.warnings || [],
      };
    }
    if (sim.error) engineState.error = sim.error;
    if (sim.status === 'completed' || sim.status === 'approved' || sim.status === 'approved_with_conditions') {
      engineState.progress = 100;
    }
  }

  function ingestEvents(list) {
    engineState = ER.reduceMany(engineState, list || []);
  }

  // ── Draft assembly (local only) ───────────────────────────
  function saveDraft() {
    try {
      localStorage.setItem('sa_invest_sources', JSON.stringify(draftModules));
    } catch (e) { /* ignore */ }
  }

  function loadDraft() {
    try {
      var raw = localStorage.getItem('sa_invest_sources');
      if (raw) draftModules = JSON.parse(raw) || [];
    } catch (e) {
      draftModules = [];
    }
    renderSelectedSources();
  }

  function computeModuleBadges() {
    var teamN = draftModules.filter(function (m) {
      return m.kind === 'team' || String(m.sourceId || '').indexOf('team:') === 0;
    }).length;
    var srcN = draftModules.filter(function (m) {
      var id = String(m.sourceId || '');
      if (m.kind === 'team' || id.indexOf('team:') === 0) return false;
      if (m.kind === 'document' || id.indexOf('document:') === 0) return false;
      if (m.kind === 'market' || m.kind === 'engine' || id.indexOf('market:') === 0) return false;
      return true;
    }).length;
    badgeCache.modules_team = teamN;
    badgeCache.sources_selected = srcN;
    if (sidebarApi && sidebarApi.setBadges) sidebarApi.setBadges(badgeCache);
  }

  function renderSelectedSources() {
    var box = $('source-selected');
    var empty = $('source-empty');
    if (!box) return;
    if (!draftModules.length) {
      if (empty) empty.style.display = 'block';
      box.innerHTML = '';
      if ($('assembly-count')) $('assembly-count').textContent = '0 个信息模块';
      var emptyRoad = $('source-drop');
      if (emptyRoad) emptyRoad.classList.add('is-empty');
      computeModuleBadges();
      syncPrimaryButton();
      if (typeof fitAssemblyZoom === 'function') fitAssemblyZoom();
      return;
    }
    if (empty) empty.style.display = 'none';
    var filledRoad = $('source-drop');
    if (filledRoad) filledRoad.classList.remove('is-empty');
    box.innerHTML = draftModules
      .map(function (s, i) {
        var type =
          s.kind === 'team'
            ? 'TEAM'
            : s.kind === 'document'
              ? 'DOC'
              : s.kind === 'market' || s.kind === 'engine'
                ? 'ENGINE'
                : 'SOURCE';
        return (
          '<div class="assembled-part"><button type="button" data-i="' +
          i +
          '" aria-label="移除模块">×</button><span class="part-type">' +
          type +
          '</span><b>#' +
          (s.priority || i + 1) +
          ' ' +
          esc(s.name || s.sourceId) +
          '</b><small>草稿 · 启动时冻结为快照</small></div>'
        );
      })
      .join('');
    if ($('assembly-count')) {
      $('assembly-count').textContent = draftModules.length + ' 个信息模块';
    }
    box.querySelectorAll('button').forEach(function (btn) {
      btn.addEventListener('click', function () {
        draftModules.splice(parseInt(btn.getAttribute('data-i'), 10), 1);
        draftModules.forEach(function (s, idx) {
          s.priority = idx + 1;
        });
        renderSelectedSources();
        saveDraft();
      });
    });
    computeModuleBadges();
    syncPrimaryButton();
    if (typeof fitAssemblyZoom === 'function') fitAssemblyZoom();
  }

  function addModule(id, name, kind) {
    if (!id) return;
    if (draftModules.some(function (x) { return x.sourceId === id; })) return;
    // Disabled source check is soft — server may still reject
    draftModules.push({
      sourceId: id,
      priority: draftModules.length + 1,
      name: name || id,
      kind: kind || 'source',
    });
    renderSelectedSources();
    saveDraft();
  }

  function bindDrag(el) {
    el.addEventListener('dragstart', function (ev) {
      el.classList.add('dragging');
      ev.dataTransfer.setData('text/plain', el.getAttribute('data-id'));
      ev.dataTransfer.setData('text/name', el.getAttribute('data-name'));
      ev.dataTransfer.setData('text/kind', el.getAttribute('data-kind') || 'source');
    });
    el.addEventListener('dragend', function () {
      el.classList.remove('dragging');
    });
    // Mobile / keyboard: click to add
    el.addEventListener('click', function () {
      addModule(
        el.getAttribute('data-id'),
        el.getAttribute('data-name'),
        el.getAttribute('data-kind') || 'source'
      );
    });
    el.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' || ev.key === ' ') {
        ev.preventDefault();
        addModule(
          el.getAttribute('data-id'),
          el.getAttribute('data-name'),
          el.getAttribute('data-kind') || 'source'
        );
      }
    });
    if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '0');
  }

  // ── Networking ────────────────────────────────────────────
  async function loadRuntimeHealth() {
    try {
      var h = await api().request('/api/v1/trading-runtime/health');
      $('runtime-health').textContent = JSON.stringify(h, null, 2);
    } catch (e) {
      $('runtime-health').textContent = e.message || String(e);
    }
  }

  async function loadSourceLibrary() {
    var lib = $('source-library');
    if (!lib) return;
    try {
      var data = await api().request('/api/v1/information-sources');
      var rows = (data && data.sources) || [];
      if (!rows.length) {
        lib.innerHTML = '<div class="empty">无来源，可使用上方团队零件</div>';
      } else {
        lib.innerHTML = rows
          .map(function (s) {
            return (
              '<div class="part-card" draggable="true" role="button" data-id="' +
              esc(s.source_id) +
              '" data-name="' +
              esc(s.name || s.source_id) +
              '" data-kind="source">' +
              '<span class="part-type">SOURCE</span><strong>' +
              esc(s.name || s.source_id) +
              '</strong><small>' +
              esc(s.kind) +
              ' · ' +
              (s.enabled ? '启用' : '停用') +
              '</small></div>'
            );
          })
          .join('');
        lib.querySelectorAll('.part-card').forEach(bindDrag);
      }
    } catch (e) {
      lib.innerHTML = '<div class="empty">' + esc(e.message || e) + '</div>';
    }
    // Re-fit after asynchronously loaded source parts change the road density.
    window.setTimeout(fitAssemblyZoom, 0);
    // Soft badge: AI 60s docs — failure must not block Engine
    try {
      var docs = await api().request('/api/v1/information-documents?channel=ai_news_60s&limit=30');
      var n = ((docs && docs.documents) || []).length;
      badgeCache.docs_ai = n;
      if (sidebarApi && sidebarApi.setBadges) sidebarApi.setBadges(badgeCache);
    } catch (e2) {
      badgeCache.docs_ai = '—';
      if (sidebarApi && sidebarApi.setBadges) sidebarApi.setBadges(badgeCache);
    }
  }

  function buildCreateBody(autoStart) {
    var form = readForm();
    var modules = ES.modulesFromDraft(draftModules);
    return {
      ticker: form.ticker,
      trade_date: form.trade_date,
      sector: form.sector,
      initial_cash: form.initial_cash,
      debate_rounds: form.debate_rounds,
      risk_rounds: form.risk_rounds,
      mode: form.mode,
      auto_start: !!autoStart,
      sources: draftModules.map(function (s) {
        return {
          sourceId: s.sourceId,
          name: s.name,
          kind: s.kind || 'source',
          priority: s.priority,
        };
      }),
      assembly: modules,
      deep_model: { provider: 'deepseek', name: 'deepseek-reasoner', model_id: 'deep_think' },
      quick_model: { provider: 'deepseek', name: 'deepseek-chat', model_id: 'quick_think' },
    };
  }

  async function createSim(autoStart) {
    var form = readForm();
    var errors = ES.validateEngineForm(form);
    if (errors.length) {
      engineState.formErrors = errors;
      syncPrimaryButton();
      alert(errors.join('\n'));
      return null;
    }
    var app = null;
    try {
      app = await api().request('/api/v1/model-clearance/applications', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model_id: form.ticker,
          applicant: 'security-admin',
          revision: form.trade_date || 'v1.0',
          auto_submit: !!autoStart,
        }),
      });
    } catch (e) {
      // Fallback to simulations endpoint if needed
      app = await api().request('/api/v1/investment-simulations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildCreateBody(!!autoStart)),
      });
    }

    engineState = ES.create();
    applySim(app);
    engineState.lastSeq = 0;
    engineState.events = [];
    try {
      localStorage.setItem('sa_invest_run', app.application_id || app.run_id);
    } catch (e) { /* ignore */ }
    renderFromState();
    if (app.status === 'running' || app.status === 'gating' || autoStart) {
      beginLiveJourney();
    }
    return app;
  }

  async function startSim() {
    if (!engineState.runId) return;
    var res = null;
    try {
      res = await api().request(
        '/api/v1/model-clearance/applications/' + encodeURIComponent(engineState.runId) + '/submit',
        { method: 'POST' }
      );
    } catch (e) {
      res = await api().request(
        '/api/v1/investment-simulations/' + encodeURIComponent(engineState.runId) + '/start',
        { method: 'POST' }
      );
    }
    applySim(res);
    renderFromState();
    beginLiveJourney();
  }

  async function cancelSim() {
    if (!engineState.runId) return;
    stopLiveJourney();
    engineState.status = 'cancelled';
    renderFromState();
  }

  async function onPrimaryStart() {
    var form = readForm();
    var d = ES.deriveStartState(form, runView());
    if (d.action === 'validate') {
      alert((d.errors || []).join('\n') || '请检查配置');
      return;
    }
    if (d.action === 'create_start' || d.action === 'rerun' || d.action === 'retry') {
      await createSim(true);
      return;
    }
    if (d.action === 'start') {
      await startSim();
    }
  }

  function stopLiveJourney() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    if (eventSource) {
      try {
        eventSource.close();
      } catch (e) { /* ignore */ }
      eventSource = null;
    }
    if (engineState.connection === 'live' || engineState.connection === 'polling') {
      engineState.connection = 'idle';
    }
  }

  function beginLiveJourney() {
    stopLiveJourney();
    // Prefer SSE, fall back to polling
    var useSSE = typeof EventSource !== 'undefined';
    if (useSSE && engineState.runId) {
      try {
        connectSSE();
        return;
      } catch (e) {
        /* fall through */
      }
    }
    engineState.connection = 'polling';
    pollTimer = setInterval(poll, 500);
    poll();
  }

  function connectSSE() {
    var url =
      '/api/v1/investment-simulations/' +
      encodeURIComponent(engineState.runId) +
      '/events/stream?after_seq=' +
      (engineState.lastSeq || 0);
    eventSource = new EventSource(url);
    engineState.connection = 'live';
    renderFromState();

    eventSource.onmessage = function (msg) {
      try {
        var ev = JSON.parse(msg.data);
        ingestEvents([ev]);
        renderFromState();
        // soft refresh sim status periodically via poll once
      } catch (e) {
        console.warn(e);
      }
    };
    eventSource.addEventListener('done', function () {
      stopLiveJourney();
      poll(); // final state
    });
    eventSource.onerror = function () {
      if (eventSource) {
        try {
          eventSource.close();
        } catch (e) { /* ignore */ }
        eventSource = null;
      }
      engineState.connection = 'reconnecting';
      renderFromState();
      // Fallback poll + reconnect later
      poll().finally(function () {
        engineState.connection = 'polling';
        pollTimer = setInterval(poll, 600);
      });
    };
  }

  async function poll() {
    if (!engineState.runId) return;
    try {
      var app = null;
      var evData = null;
      try {
        app = await api().request(
          '/api/v1/model-clearance/applications/' + encodeURIComponent(engineState.runId)
        );
        evData = await api().request(
          '/api/v1/model-clearance/applications/' + encodeURIComponent(engineState.runId) + '/events'
        );
      } catch (e) {
        app = await api().request(
          '/api/v1/investment-simulations/' + encodeURIComponent(engineState.runId)
        );
        evData = await api().request(
          '/api/v1/investment-simulations/' +
            encodeURIComponent(engineState.runId) +
            '/events?after_seq=' +
            (engineState.lastSeq || 0)
        );
      }
      if (app) applySim(app);
      if (evData && evData.events) ingestEvents(evData.events);
      renderPortfolio(null);
      if (app && (app.status === 'approved' || app.status === 'approved_with_conditions' || app.status === 'rejected' || app.status === 'completed' || app.status === 'failed' || app.status === 'cancelled')) {
        stopLiveJourney();
        engineState.progress = 100;
      }
      renderFromState();
    } catch (e) {
      console.warn(e);
      engineState.connection = 'error';
      renderFromState();
    }
  }

  function renderPortfolio(pf) {
    var el = $('portfolio');
    if (!el) return;
    if (!pf || pf.empty || !pf.portfolio) {
      // Also try to query model clearance registry if available
      api().request('/api/v1/model-clearance/registry').then(function(res) {
        var list = (res && res.registry) || [];
        if (!list.length) {
          el.innerHTML = '<div class="empty">空状态：尚无准入条目</div>';
          return;
        }
        var rows = list.map(function(item) {
          var badgeCls = item.status === 'active' ? 'status-ok' : 'status-bad';
          return '<div class="stat" style="border-bottom:1px solid #1e3554;padding:6px 0">' +
            '<strong>' + esc(item.model_id) + '</strong> (' + esc(item.runtime_profile || 'standard') + ')' +
            '<br><small class="muted">Digest: ' + esc((item.locked_digest || '').slice(0, 16)) + '… · 状态: <span class="' + badgeCls + '">' + esc(item.status) + '</span></small>' +
            (item.conditions && item.conditions.length ? '<br><small style="color:#fbbf24">约束: ' + esc(item.conditions.join('; ')) + '</small>' : '') +
            '</div>';
        }).join('');
        el.innerHTML = '<div style="font-size:12px">' + rows + '</div>';
      }).catch(function() {
        el.innerHTML = '<div class="empty">空状态：尚无准入条目</div>';
      });
      return;
    }
    var p = pf.portfolio;
    if (p.error) {
      el.innerHTML = '<div class="status-bad">失败：' + esc(p.error) + '</div>';
      return;
    }
    el.innerHTML =
      '<div class="stat">准入编号: ' +
      esc(p.entry_id || 'REG-PENDING') +
      '</div>' +
      '<div class="stat">运行时环境 Profile: ' +
      esc(p.runtime_profile || 'standard') +
      '</div>' +
      '<div class="stat">适用范围 Scope: ' +
      esc(JSON.stringify(p.scope || ['internal'])) +
      '</div>' +
      '<div class="stat muted">' +
      esc(p.disclaimer || '仅供内部治理参考，不构成法律或采购建议。') +
      '</div>';
  }

  async function restore() {
    try {
      var id = localStorage.getItem('sa_invest_run');
      if (!id) return;
      var app = null;
      var evData = null;
      try {
        app = await api().request('/api/v1/model-clearance/applications/' + encodeURIComponent(id));
        evData = await api().request('/api/v1/model-clearance/applications/' + encodeURIComponent(id) + '/events');
      } catch (e) {
        app = await api().request('/api/v1/investment-simulations/' + encodeURIComponent(id));
        evData = await api().request('/api/v1/investment-simulations/' + encodeURIComponent(id) + '/events?after_seq=0');
      }
      applySim(app);
      engineState.lastSeq = 0;
      engineState.events = [];
      if (evData && evData.events) ingestEvents(evData.events);
      renderPortfolio(null);
      renderFromState();
      if (app && (app.status === 'running' || app.status === 'gating' || app.status === 'queued')) {
        beginLiveJourney();
      }
    } catch (e) {
      /* ignore */
    }
  }

  // ── Wire UI ───────────────────────────────────────────────
  if ($('trade_date') && !$('trade_date').value) {
    $('trade_date').value = today();
  }

  document.querySelectorAll('.part-card').forEach(bindDrag);

  var assemblyZoom = 1;
  function setAssemblyZoom(value) {
    assemblyZoom = Math.max(0.65, Math.min(1.35, Number(value) || 1));
    var viewport = document.querySelector('.assembly-viewport');
    var road = $('source-drop');
    if (road) road.style.setProperty('--road-zoom', String(assemblyZoom));
    var reset = $('assembly-zoom-reset');
    if (reset) reset.textContent = Math.round(assemblyZoom * 100) + '%';
    if (viewport) viewport.setAttribute('aria-label', '装配主干道缩放 ' + Math.round(assemblyZoom * 100) + '%');
  }
  function fitAssemblyZoom() {
    var road = $('source-drop');
    var track = $('road-modules-scroll');
    if (!road || !track) return setAssemblyZoom(0.85);
    var count = draftModules.length;
    var hasOverflow = track.scrollWidth > track.clientWidth + 20;
    var target = count === 0 ? 0.78 : count <= 2 ? 0.88 : count <= 5 ? 0.95 : 1;
    setAssemblyZoom(hasOverflow ? Math.min(target, 0.82) : target);
  }
  if ($('assembly-zoom-out')) $('assembly-zoom-out').addEventListener('click', function () { setAssemblyZoom(assemblyZoom - 0.1); });
  if ($('assembly-zoom-in')) $('assembly-zoom-in').addEventListener('click', function () { setAssemblyZoom(assemblyZoom + 0.1); });
  if ($('assembly-zoom-reset')) $('assembly-zoom-reset').addEventListener('click', function () { setAssemblyZoom(1); });
  if ($('assembly-zoom-fit')) $('assembly-zoom-fit').addEventListener('click', fitAssemblyZoom);
  setAssemblyZoom(1);
  window.setTimeout(fitAssemblyZoom, 0);

  var drop = $('source-drop');
  if (drop) {
    drop.addEventListener('dragover', function (ev) {
      ev.preventDefault();
      drop.classList.add('over');
    });
    drop.addEventListener('dragleave', function () {
      drop.classList.remove('over');
    });
    drop.addEventListener('drop', function (ev) {
      ev.preventDefault();
      drop.classList.remove('over');
      addModule(
        ev.dataTransfer.getData('text/plain'),
        ev.dataTransfer.getData('text/name'),
        ev.dataTransfer.getData('text/kind') || 'source'
      );
    });
  }

  if ($('btn-engine-start')) {
    $('btn-engine-start').addEventListener('click', function () {
      onPrimaryStart().catch(function (e) {
        alert(e.message || e);
      });
    });
  }
  if ($('btn-create')) {
    $('btn-create').addEventListener('click', function () {
      createSim(false).catch(function (e) {
        alert(e.message || e);
      });
    });
  }
  if ($('btn-start')) {
    $('btn-start').addEventListener('click', function () {
      startSim().catch(function (e) {
        alert(e.message || e);
      });
    });
  }
  if ($('btn-cancel')) {
    $('btn-cancel').addEventListener('click', function () {
      cancelSim().catch(function (e) {
        alert(e.message || e);
      });
    });
  }
  document.querySelectorAll('[data-ticker]').forEach(function (button) {
    button.addEventListener('click', function () {
      $('ticker').value = button.dataset.ticker;
      syncPrimaryButton();
    });
  });
  ['ticker', 'trade_date', 'cash', 'mode', 'sector'].forEach(function (id) {
    if ($(id)) {
      $(id).addEventListener('input', syncPrimaryButton);
      $(id).addEventListener('change', syncPrimaryButton);
    }
  });

  if (window.EngineSidebar && typeof window.EngineSidebar.init === 'function') {
    sidebarApi = window.EngineSidebar.init({ badges: badgeCache });
  }

  document.addEventListener('click', function (ev) {
    var t = ev.target;
    if (!t || !t.closest) return;
    var tab = t.closest('.judgment-tab');
    if (tab && tab.getAttribute('data-group')) {
      judgmentState.group = tab.getAttribute('data-group');
      renderJudgmentPanel();
    }
  });

  window.addEventListener('resize', function () {
    refreshOverflowHints();
  });

  loadDraft();
  loadSourceLibrary();
  loadRuntimeHealth();
  renderFromState();
  renderJudgmentPanel();
  refreshOverflowHints();
  restore();
})();
