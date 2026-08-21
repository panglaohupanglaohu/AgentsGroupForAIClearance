/** ModelClearance data intelligence workbench: sources, trace, reports and schedules. */
(function () {
  'use strict';
  var state = { sources: [], schedules: [], latest: {}, directory: { url: '', candidates: [] }, openweights: [] };
  var teamState = {
    ai_news_60s: { agents: [], running: false, liveTimer: null },
    dufu_world_intel: { agents: [], running: false, liveTimer: null },
    open_weights: { agents: [], running: false, liveTimer: null }
  };
  var teamMeta = {
    ai_news_60s: {
      row: 'ai60-agent-row', grid: 'ai60-box-grid', note: 'ai60-run-note', start: 'btn-start-ai60',
      boxes: [['主题与信号', '把原始信息聚类成 AI 主题，并计算可解释的信号强度。'], ['证据综合', 'Scout/Checker 合并重复来源，核对日期、实体、数字和引用。'], ['判断路径', '从观察 → 聚类 → 核验，说明为什么这组信息值得关注。'], ['业务影响', 'Market Mapper 推演能力、成本、采用到收入/利润池的路径。'], ['反证与开放问题', '保留来源偏差、样本不足、时间滞后和替代解释。'], ['动态研判驾驶舱', 'Publisher 将主题、指标、路径、关系图和 HTML 版本发布。']],
      boxAgents: [0, 2, 0, 3, 2, 5]
    },
    dufu_world_intel: {
      row: 'dufu-agent-row', grid: 'dufu-slide-grid', note: 'dufu-run-note', start: 'btn-start-dufu',
      boxes: [['事件事实', '建立事件卡：发生了什么、何时发生、谁发布。'], ['历史时间线', '把关键节点按时间排列，避免把相关性写成因果。'], ['关键驱动', '提取政策、资本、技术与地缘变量。'], ['数据趋势', '清洗数据、对齐口径并识别趋势与异常。'], ['观点与反证', 'Red Team 提供替代解释和证据缺口。'], ['三情景树', '乐观 / 基准 / 悲观，附触发条件与观察指标。'], ['市场传导', '事件 → 行业 → 公司 → 资产的路径，仅供模拟。'], ['来源与截止', '记录来源、发布时间、抓取时间和版本号。']],
      boxAgents: [0, 1, 2, 2, 4, 5, 5, 6]
    },
    open_weights: {
      row: 'ow-agent-row', grid: 'ow-box-grid', note: 'ow-run-note', start: 'btn-start-ow',
      boxes: [['模型发布与权重', '追踪 HuggingFace/ModelScope 最新 safetensors 权重与模型卡发布。'], ['许可证合规', '提取商用约束、MAU 上限与衍生分发条款。'], ['评测基准', '收集客观 MMLU/GSM8K 等能力与长上下文测试证据。'], ['部署资源', '显存、量化 (GGUF/AWQ)、KV-Cache 与多卡并发开销。'], ['红队安全', '越狱攻击抗性、提示注入与有害内容防御表现。'], ['准入映射', '映射到 G1–G6 门禁证据库与控制台。']],
      boxAgents: [0, 1, 2, 3, 4, 5]
    }
  };
  var liveScripts = {
    ai_news_60s: [
      'Scout：正在读取 {count} 个来源，先返回标题、时间与原文片段。',
      'Checker：正在去重并交叉核对实体、日期、数字和引用。',
      'Lead：已把首批证据归入主题簇，信号强度正在更新。',
      'Market Mapper：正在把技术变化映射到采用、成本与收入路径。',
      'Red Team：正在寻找反证、样本偏差与尚未验证的替代解释。',
      'Publisher：正在编排引用、推理链和动态 HTML 交付物。'
    ],
    dufu_world_intel: [
      '采集员：正在拉取 {count} 个来源，建立事件与发布时间索引。',
      '数据分析员：正在清洗重复条目，统一单位、时间窗和地区口径。',
      '趋势分析员：正在把事件放入时间线，标记政策、资本和技术驱动。',
      '反证员：正在检查因果跳跃、数据缺口和相反方向的证据。',
      '市场分析员：正在推演事件 → 行业 → 公司 → 资产的传导路径。',
      'Presenter：正在生成 16:9 故事板、情景树和来源截止说明。'
    ],
    open_weights: [
      'Weights Collector：正在拉取 {count} 个开放权重来源，建立模型与版本索引。',
      'Data Engineer：正在清洗模型卡，提取不可变 revision、权重格式与 SHA-256。',
      'Model Analyst：正在分析模型架构、参数规模与上下文窗口。',
      'License Watch：正在抽取许可证类别与商业使用限制。',
      'Red Team：正在检验安全行为与漏洞暴露面。',
      'Presenter：正在生成开放权重研判报告与准入路径建议。'
    ]
  };
  var $ = function (id) { return document.getElementById(id); };
  function setText(id, value) { var el = $(id); if (el) el.textContent = value; }
  var client = function () { return window.api; };
  var esc = function (v) { return String(v == null ? '' : v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); };
  var request = function (path, opts) { return client().request(path, opts || {}); };

  function switchTab(name) {
    document.querySelectorAll('.tab').forEach(function (tab) { tab.classList.toggle('active', tab.dataset.tab === name); });
    document.querySelectorAll('.panel').forEach(function (panel) { panel.classList.toggle('active', panel.id === 'panel-' + name); });
    if (name === 'ai60' || name === 'world' || name === 'openweights') {
      loadLatestDocs();
      var ch = name === 'world' ? 'dufu_world_intel' : name === 'openweights' ? 'open_weights' : 'ai_news_60s';
      loadBriefs(ch);
    }
    if (name === 'openweights') loadOpenWeights();
    if (name === 'docs') loadHistory();
  }
  document.querySelectorAll('.tab').forEach(function (tab) { tab.addEventListener('click', function () { switchTab(tab.dataset.tab); }); });

  function toggleBriefItem(item) {
    var expanded = item.classList.toggle('is-expanded');
    item.setAttribute('aria-expanded', expanded ? 'true' : 'false');
  }
  function bindExpandableBrief(root) {
    if (!root) return;
    root.addEventListener('click', function (event) {
      var item = event.target.closest('.brief-expandable');
      if (item && root.contains(item)) toggleBriefItem(item);
    });
    root.addEventListener('keydown', function (event) {
      var item = event.target.closest('.brief-expandable');
      if (item && root.contains(item) && (event.key === 'Enter' || event.key === ' ')) {
        event.preventDefault();
        toggleBriefItem(item);
      }
    });
  }
  bindExpandableBrief($('brief-strip'));
  bindExpandableBrief($('executive-brief'));

  function initials(name) { return String(name || 'A').trim().slice(0, 1).toUpperCase(); }
  function renderAgentRow(teamId) {
    var meta = teamMeta[teamId], root = $(meta.row), info = teamState[teamId];
    if (!root) return;
    var agents = info.agents || [];
    root.innerHTML = agents.length ? agents.map(function (agent) {
      var state = agent.uiState || 'idle';
      return '<div class="agent-chip ' + (state === 'running' ? 'running' : state === 'done' ? 'done' : '') + '" data-agent-id="' + esc(agent.agent_id) + '"><span class="agent-avatar">' + esc(initials(agent.name)) + '</span><span><b>' + esc(agent.name || agent.agent_id) + '</b><small>' + esc(agent.role || 'agent') + '</small></span><span class="agent-state" aria-label="' + esc(state) + '"></span></div>';
    }).join('') : '<div class="muted">团队尚未加载</div>';
  }
  function renderInfoBoxes(teamId, values) {
    var meta = teamMeta[teamId], root = $(meta.grid); if (!root) return;
    var agents = teamState[teamId].agents || [];
    root.innerHTML = meta.boxes.map(function (item, index) {
      var value = values && values[index] ? values[index] : item[1];
      var agent = agents[(meta.boxAgents || [])[index] == null ? index : meta.boxAgents[index]] || {};
      var skills = Array.isArray(agent.skills) ? agent.skills : [];
      var tools = Array.isArray(agent.tools) ? agent.tools : [];
      var capability = (skills.length ? '技能：' + skills.slice(0, 3).join('、') : '技能待配置') + ' · ' + (tools.length ? '工具：' + tools.slice(0, 3).join('、') : '工具待配置');
      return '<article class="info-box" data-box-index="' + index + '"><h4>' + esc(item[0]) + '</h4><span class="box-agent">' + esc(agent.name || '等待 Agent 接管') + '</span><span class="box-capabilities" title="' + esc(capability) + '">' + esc(capability) + '</span><p>' + esc(value) + '</p><div class="box-progress" aria-hidden="true"><i></i></div><div class="box-meta"><span class="box-status">待命</span><span class="box-elapsed">交付盒</span></div></article>';
    }).join('');
  }
  function setAgentProgress(teamId, stepIndex, state) {
    var info = teamState[teamId], agents = info.agents || [], meta = teamMeta[teamId];
    agents.forEach(function (agent, index) { agent.uiState = index < stepIndex ? 'done' : index === stepIndex ? state : 'idle'; });
    renderAgentRow(teamId);
    renderInfoBoxes(teamId);
    var boxes = $(meta.grid) ? $(meta.grid).querySelectorAll('.info-box') : [];
    Array.prototype.forEach.call(boxes, function (box, index) {
      box.classList.toggle('filling', state === 'running' && index === stepIndex);
      box.classList.toggle('filled', index < stepIndex || (state === 'done' && index === stepIndex));
      var label = box.querySelector('.box-status'); if (label) label.textContent = index < stepIndex || state === 'done' && index === stepIndex ? '已填充' : state === 'running' && index === stepIndex ? 'Agent 运行中' : '待命';
    });
  }
  function liveBoxText(teamId, index, sourceCount, elapsed) {
    var scripts = liveScripts[teamId] || [], template = scripts[Math.min(index, scripts.length - 1)] || 'Agent 正在处理上游交付。';
    return template.replace('{count}', String(sourceCount || 0)) + ' · ' + elapsed + 's';
  }
  function updateLiveBoxes(teamId, stageIndex, sourceCount, elapsed) {
    var meta = teamMeta[teamId], root = $(meta.grid), boxes = root ? root.querySelectorAll('.info-box') : [], scripts = liveScripts[teamId] || [];
    if (!boxes.length) return;
    Array.prototype.forEach.call(boxes, function (box, index) {
      var p = box.querySelector('p'), agent = box.querySelector('.box-agent'), status = box.querySelector('.box-status'), meter = box.querySelector('.box-progress i'), clock = box.querySelector('.box-elapsed');
      var active = index === stageIndex, complete = index < stageIndex;
      box.classList.toggle('filling', active); box.classList.toggle('filled', complete);
      if (agent) agent.textContent = active ? (scripts[index] || 'Agent') .split('：')[0] : complete ? '阶段输出已交接' : '等待上游交付';
      if (p) p.textContent = active || complete ? liveBoxText(teamId, index, sourceCount, elapsed) : '等待上游交付：' + meta.boxes[index][1];
      if (status) status.textContent = active ? 'Agent 工作中' : complete ? '阶段完成' : '排队中';
      if (clock) clock.textContent = active ? elapsed + 's' : complete ? '已交接' : '未开始';
      if (meter) meter.style.width = (complete ? 100 : active ? Math.min(92, 24 + (elapsed % 4) * 15) : 6) + '%';
    });
  }
  function startLiveProgress(teamId, sourceCount, startedAt) {
    var info = teamState[teamId], meta = teamMeta[teamId], scripts = liveScripts[teamId] || [];
    var tick = function () {
      var elapsed = Math.max(0, Math.round((Date.now() - startedAt) / 1000)), stage = Math.min(scripts.length - 1, Math.floor(elapsed / 2));
      info.liveStage = stage; updateLiveBoxes(teamId, stage, sourceCount, elapsed); setAgentProgress(teamId, Math.min(stage, Math.max(0, info.agents.length - 1)), 'running');
      $(meta.note).textContent = ' running / collecting · Agent ' + (stage + 1) + '/' + scripts.length + ' · ' + sourceCount + ' sources · ' + elapsed + 's';
    };
    tick(); info.liveTimer = window.setInterval(tick, 900); return tick;
  }
  function stopLiveProgress(teamId) { var info = teamState[teamId]; if (info.liveTimer) { window.clearInterval(info.liveTimer); info.liveTimer = null; } }
  async function animateTeamProgress(teamId, result) {
    var meta = teamMeta[teamId], info = teamState[teamId], steps = (result && result.steps) || [];
    info.running = true; $(meta.note).textContent = ' running / fixture';
    var total = Math.max(info.agents.length, meta.boxes.length, steps.length || 1);
    for (var i = 0; i < total; i += 1) {
      setAgentProgress(teamId, i, 'running');
      await new Promise(function (resolve) { window.setTimeout(resolve, 180); });
      var box = $(meta.grid) && $(meta.grid).querySelector('[data-box-index="' + i + '"]');
      if (box && steps[i]) { var p = box.querySelector('p'); if (p) p.textContent = steps[i].summary || steps[i].step || meta.boxes[i][1]; }
    }
    setAgentProgress(teamId, total, 'done'); info.running = false; $(meta.note).textContent = ' completed / fixture';
  }
  async function loadTeamAgents(teamId) {
    try {
      var data = await request('/api/v1/agent-config/teams/' + encodeURIComponent(teamId));
      var agents = data && data.agents ? data.agents : [];
      if (!Array.isArray(agents)) agents = Object.keys(agents).map(function (key) { return agents[key]; });
      teamState[teamId].agents = agents.map(function (agent) { return { agent_id: agent.agent_id, name: agent.name, role: agent.role, skills: agent.skills || [], tools: agent.tools || [], uiState: 'idle' }; });
    } catch (e) { teamState[teamId].agents = []; }
    renderAgentRow(teamId);
  }

  function updateKpis() {
    $('kpi-sources').textContent = state.sources.length;
    $('kpi-schedules').textContent = state.schedules.filter(function (x) { return x.enabled; }).length;
    $('kpi-health').textContent = state.sources.filter(function (x) { return x.last_health && x.last_health.ok; }).length || '—';
  }

  var sourceProfiles = {
    ai60: { label: 'AI 60 秒信息播报', order: 1 },
    dufu: { label: '独夫之心世界趋势', order: 2 },
    openweights: { label: '开放权重资源', order: 3 },
    shared: { label: '多团队共享', order: 4 },
    other: { label: '未分类来源', order: 5 }
  };
  var sourceKinds = { rss: 'RSS / Atom', web: '网页', json_api: 'JSON API', fixture: 'Fixture 演示', other: '其他连接器' };

  function sourceProfileKey(source) {
    var options = source.options || {}, teams = Array.isArray(options.target_teams) ? options.target_teams : [];
    var profile = String(options.collection_profile || '').toLowerCase();
    if (teams.length > 1 || profile === 'both' || profile === 'all') return 'shared';
    if (teams.indexOf('ai_news_60s') >= 0 || profile === 'ai60') return 'ai60';
    if (teams.indexOf('dufu_world_intel') >= 0 || profile === 'dufu') return 'dufu';
    if (teams.indexOf('open_weights') >= 0 || profile === 'openweights') return 'openweights';
    return 'other';
  }

  function sourceKindKey(source) { return sourceKinds[source.kind] ? source.kind : 'other'; }

  function updateSourceSelectionButton() {
    var button = $('btn-select-all-sources'), boxes = document.querySelectorAll('.source-check');
    if (!button) return;
    var all = boxes.length > 0 && Array.prototype.every.call(boxes, function (box) { return box.checked; });
    button.textContent = all ? '取消全选' : '全选';
    button.setAttribute('aria-pressed', all ? 'true' : 'false');
  }

  function sourceTreeChildren(kindKey) { return document.querySelectorAll('.source-check[data-kind-key="' + kindKey + '"]'); }
  function sourceTreeGroup(groupKey) { return document.querySelectorAll('.source-check[data-group-key="' + groupKey + '"]'); }
  function syncTreeParent(parent, children) {
    var list = Array.prototype.slice.call(children || []), checked = list.filter(function (box) { return box.checked; }).length;
    parent.checked = list.length > 0 && checked === list.length;
    parent.indeterminate = checked > 0 && checked < list.length;
  }
  function syncSourceTreeParents() {
    document.querySelectorAll('.source-kind-check').forEach(function (parent) { syncTreeParent(parent, sourceTreeChildren(parent.dataset.kindKey)); });
    document.querySelectorAll('.source-group-check').forEach(function (parent) { syncTreeParent(parent, sourceTreeGroup(parent.dataset.groupKey)); });
    updateSourceSelectionButton();
  }
  function setSourceTreeChildren(selector, checked) {
    document.querySelectorAll(selector).forEach(function (box) { box.checked = checked; });
    syncSourceTreeParents();
  }
  function bindSourceTree() {
    document.querySelectorAll('.tree-toggle').forEach(function (button) {
      button.addEventListener('click', function () {
        var target = document.getElementById(button.dataset.target), collapsed = target.classList.toggle('is-collapsed');
        button.textContent = collapsed ? '▸' : '▾'; button.setAttribute('aria-expanded', String(!collapsed));
      });
    });
    document.querySelectorAll('.source-group-check').forEach(function (box) { box.addEventListener('change', function () { setSourceTreeChildren('.source-check[data-group-key="' + box.dataset.groupKey + '"]', box.checked); }); });
    document.querySelectorAll('.source-kind-check').forEach(function (box) { box.addEventListener('change', function () { setSourceTreeChildren('.source-check[data-kind-key="' + box.dataset.kindKey + '"]', box.checked); }); });
    document.querySelectorAll('.source-check').forEach(function (box) { box.addEventListener('change', syncSourceTreeParents); });
    syncSourceTreeParents();
  }

  function toggleAllSources() {
    var boxes = document.querySelectorAll('.source-check');
    if (!boxes.length) return;
    var all = Array.prototype.every.call(boxes, function (box) { return box.checked; });
    boxes.forEach(function (box) { box.checked = !all; });
    syncSourceTreeParents();
  }

  function sourceHtml(source, table, treeContext) {
    if (table) return '<tr><td><code>' + esc(source.source_id) + '</code></td><td>' + esc(source.name) + '</td><td>' + esc(source.kind) + '</td><td>' + (source.enabled ? '<span style="color:#059669">是</span>' : '否') + '</td><td class="muted">' + esc(source.url || 'fixture://offline') + '</td><td><button class="btn secondary btn-test" data-id="' + esc(source.source_id) + '" type="button">测试</button></td></tr>';
    treeContext = treeContext || {};
    return '<label class="source-item"><input class="source-check" data-group-key="' + esc(treeContext.groupKey || '') + '" data-kind-key="' + esc(treeContext.kindKey || '') + '" type="checkbox" value="' + esc(source.source_id) + '"' + (source.enabled ? ' checked' : '') + '><span class="dot ' + (source.enabled ? 'on' : '') + '"></span><span><b>' + esc(source.name || source.source_id) + '</b><small>' + esc(source.kind) + ' · ' + esc(source.url || 'fixture://offline') + '</small></span><span class="muted">' + (source.enabled ? '已保存' : '未启用') + '</span></label>';
  }

  function sourceTreeHtml(sources) {
    var groups = {};
    (sources || []).forEach(function (source) {
      var groupKey = sourceProfileKey(source), kindKey = groupKey + '__' + sourceKindKey(source);
      groups[groupKey] = groups[groupKey] || { sources: [], kinds: {} }; groups[groupKey].sources.push(source);
      groups[groupKey].kinds[kindKey] = groups[groupKey].kinds[kindKey] || []; groups[groupKey].kinds[kindKey].push(source);
    });
    return Object.keys(groups).sort(function (a, b) { return sourceProfiles[a].order - sourceProfiles[b].order; }).map(function (groupKey, groupIndex) {
      var group = groups[groupKey], groupTarget = 'tree-group-' + groupIndex, kindHtml = Object.keys(group.kinds).sort().map(function (kindKey, kindIndex) {
        var kindTarget = 'tree-kind-' + groupIndex + '-' + kindIndex, kind = kindKey.split('__')[1], children = group.kinds[kindKey];
        return '<section class="source-tree-kind"><div class="tree-node tree-kind"><button class="tree-toggle" data-target="' + kindTarget + '" aria-expanded="true" type="button">▾</button><label><input class="source-kind-check" data-kind-key="' + esc(kindKey) + '" type="checkbox"><span>' + esc(sourceKinds[kind] || kind) + '</span></label><span class="tree-count">' + children.length + '</span></div><div class="tree-leaves" id="' + kindTarget + '">' + children.map(function (source) { return sourceHtml(source, false, { groupKey: groupKey, kindKey: kindKey }); }).join('') + '</div></section>';
      }).join('');
      return '<section class="source-tree-group"><div class="tree-node tree-root"><button class="tree-toggle" data-target="' + groupTarget + '" aria-expanded="true" type="button">▾</button><label><input class="source-group-check" data-group-key="' + esc(groupKey) + '" type="checkbox"><span>' + esc(sourceProfiles[groupKey].label) + '</span></label><span class="tree-count">' + group.sources.length + '</span></div><div class="tree-children" id="' + groupTarget + '">' + kindHtml + '</div></section>';
    }).join('');
  }

  function bindSourceButtons(root) { root.querySelectorAll('.btn-test').forEach(function (button) { button.addEventListener('click', function () { testSource(button.dataset.id); }); }); }

  async function loadSources() {
    try {
      var data = await request('/api/v1/information-sources'); state.sources = (data && data.sources) || [];
      $('sources-body').innerHTML = state.sources.length ? '<div class="source-tree">' + sourceTreeHtml(state.sources) + '</div>' : '<div class="muted">暂无来源</div>';
      $('sources-table-body').innerHTML = state.sources.length ? state.sources.map(function (x) { return sourceHtml(x, true); }).join('') : '<tr><td colspan="6" class="muted">暂无来源</td></tr>';
      bindSourceButtons($('sources-table-body')); bindSourceTree(); updateKpis();
    } catch (e) { $('sources-body').innerHTML = '<div style="color:#dc2626">' + esc(e.message || e) + '</div>'; }
  }

  async function saveSourceSelection() {
    var button = $('btn-save-source-selection'), status = $('source-selection-status'), selected = {};
    document.querySelectorAll('.source-check').forEach(function (box) { selected[box.value] = box.checked; });
    button.disabled = true; status.className = 'source-selection-status'; status.textContent = '正在保存来源选择…';
    try {
      await Promise.all(state.sources.map(function (source) { return request('/api/v1/information-sources/' + encodeURIComponent(source.source_id), { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: Boolean(selected[source.source_id]) }) }); }));
      state.sources.forEach(function (source) { source.enabled = Boolean(selected[source.source_id]); });
      status.className = 'source-selection-status ok'; status.textContent = '已保存 ' + Object.keys(selected).filter(function (id) { return selected[id]; }).length + ' 个来源；下次刷新和运行会沿用。';
    } catch (e) { status.className = 'source-selection-status error'; status.textContent = '保存失败：' + (e.message || e); }
    finally { button.disabled = false; }
  }

  async function testSource(id) {
    try { var result = await request('/api/v1/information-sources/' + encodeURIComponent(id) + '/test', { method: 'POST' }); $('inspector-log').textContent = id + '\n' + JSON.stringify(result, null, 2); } catch (e) { $('inspector-log').textContent = id + '\nERROR ' + (e.message || e); }
  }

  async function addFixture() {
    await request('/api/v1/information-sources', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kind: 'fixture', name: 'New Fixture Source', enabled: true, options: { items: [{ title: 'Fixture research signal', url: 'https://example.com/fixture', content: 'offline fixture content' }] } }) });
    await loadSources();
  }

  function sourceFormStatus(message, kind) { var el = $('source-form-status'); if (!el) return; el.textContent = message; el.className = 'form-status' + (kind ? ' ' + kind : ''); }
  function syncSourcePreview() {
    var name = $('source-name').value.trim() || '未命名来源', kind = $('source-kind').value, profile = $('source-profile').value;
    $('source-preview-name').textContent = name + ' · ' + kind;
    var ai = (profile === 'dufu' || profile === 'openweights') ? '不进入 AI 60 秒' : '进入 AI 60 秒证据流';
    var world = (profile === 'ai60' || profile === 'openweights') ? '不进入独夫之心' : '进入独夫之心故事板';
    $('preview-ai60-title').textContent = name + ' · 60 秒证据卡'; $('preview-ai60-copy').textContent = ai + '：Scout/Checker 会将内容压缩为事实卡、为什么重要、产业映射和风险反证，并接入 60 秒时间带。';
    $('preview-dufu-title').textContent = name + ' · 世界趋势议题板'; $('preview-dufu-copy').textContent = world + '：采集、清洗、分析和 Red Team 会将内容组织为时间线、关键驱动、数据趋势和三情景故事板。';
  }
  function syncSourceKind() {
    var kind = $('source-kind').value, fixture = kind === 'fixture';
    $('source-url').required = !fixture; $('source-url').disabled = fixture; $('source-url-note').textContent = fixture ? 'Fixture 不需要 URL；内容来自条目 JSON。' : '联网来源请填写公开地址，服务端会执行 SSRF/主机安全校验。';
    $('source-fixture-items').closest('label').style.display = fixture ? 'grid' : 'none'; $('source-fixture-note').style.display = fixture ? 'block' : 'none';
    sourceFormStatus(fixture ? 'Fixture 模式无需外部 Key，可离线验证。' : '联网来源将在保存后可进行健康检查。'); syncSourcePreview();
  }
  function parseJsonField(id, fallback) {
    var raw = $(id).value.trim(); if (!raw) return fallback;
    try { return JSON.parse(raw); } catch (e) { throw new Error($(id).previousElementSibling ? $(id).previousElementSibling.textContent + ' JSON 格式错误' : id + ' JSON 格式错误'); }
  }
  async function createSource(event) {
    event.preventDefault(); var button = $('btn-submit-source'); button.disabled = true; sourceFormStatus('正在保存信息源…');
    try {
      var kind = $('source-kind').value, options = parseJsonField('source-options', {});
      if (!options || Array.isArray(options) || typeof options !== 'object') throw new Error('options 必须是 JSON 对象');
      if (kind === 'fixture') { var items = parseJsonField('source-fixture-items', []); if (!Array.isArray(items)) throw new Error('Fixture 条目必须是 JSON 数组'); options.items = items; }
      var secret = $('source-secret-env').value.trim(), profile = $('source-profile').value;
      var targetTeams = profile === 'ai60' ? ['ai_news_60s'] : profile === 'dufu' ? ['dufu_world_intel'] : profile === 'openweights' ? ['open_weights'] : profile === 'all' ? ['ai_news_60s', 'dufu_world_intel', 'open_weights'] : ['ai_news_60s', 'dufu_world_intel'];
      options.collection_profile = profile; options.target_teams = targetTeams;
      options.output_contracts = {
        ai_news_60s: ['headline', 'bullets', 'why_it_matters', 'related_companies', 'risks_and_counterpoints', 'citations'],
        dufu_world_intel: ['what_happened', 'timeline', 'drivers', 'data_trends', 'counterpoints', 'scenarios', 'market_transmission', 'citations'],
        open_weights: ['what_happened', 'timeline', 'drivers', 'data_trends', 'counterpoints', 'scenarios', 'license_watch', 'admission_impact', 'citations']
      };
      var payload = { kind: kind, name: $('source-name').value.trim(), url: $('source-url').value.trim(), enabled: $('source-enabled').checked, options: options, language: $('source-language').value.trim(), region: $('source-region').value.trim() };
      if (secret) { if (!/^env:[A-Za-z_][A-Za-z0-9_]*$/.test(secret)) throw new Error('Token 环境变量必须使用 env:VAR_NAME 格式'); payload.secret_refs = { token: secret }; }
      var created = await request('/api/v1/information-sources', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      sourceFormStatus('已添加：' + (created.name || created.source_id) + '。来源列表已刷新。', 'ok'); await loadSources(); await loadSchedules(); switchTab('add-source');
    } catch (e) { sourceFormStatus(e.message || String(e), 'error'); } finally { button.disabled = false; }
  }
  function resetSourceForm() { $('source-form').reset(); $('source-options').value = '{}'; $('source-fixture-items').value = '[{"title":"Fixture research signal","url":"https://example.com/fixture","content":"offline fixture content","published_at":"2026-08-01T00:00:00Z"}]'; syncSourceKind(); }

  function directoryMessage(text, role) { var root = $('directory-chat-messages'); if (!root) return; var node = document.createElement('div'); node.className = 'chat-message ' + (role || 'assistant'); node.textContent = text; root.appendChild(node); root.scrollTop = root.scrollHeight; }

  function resetDirectoryChat() {
    var root = $('directory-chat-messages');
    if (root) {
      root.innerHTML = '<div class="chat-message assistant">贴一个 GitHub RSS 列表、OPML 或目录页，我会先解析、去重并校验，再让你确认批量添加。</div>';
    }
    if ($('directory-chat-input')) $('directory-chat-input').value = '';
    if ($('directory-preview')) {
      $('directory-preview').hidden = true;
      $('directory-preview').innerHTML = '';
    }
    if ($('btn-directory-select-all')) $('btn-directory-select-all').hidden = true;
    if ($('btn-directory-commit')) $('btn-directory-commit').hidden = true;
    state.directory = { url: '', candidates: [] };
  }

  function renderDirectoryPreview(data) {
    var root = $('directory-preview');
    if (!root) return;
    var candidates = (data && Array.isArray(data.candidates)) ? data.candidates : [];
    state.directory.candidates = candidates;
    state.directory.url = (data && data.directory_url) || '';
    root.hidden = false;
    root.innerHTML = '<div class="form-note" style="margin-bottom:6px">解析到 ' + candidates.length + ' 条候选 RSS；已勾选的条目才会写入来源库。</div>' +
      (candidates.length ? candidates.map(function (item, index) {
        var status = item.status === 'ok' ? '可用' : item.status === 'failed' ? '失败' : '待校验';
        return '<label class="directory-row"><input class="directory-check" type="checkbox" data-index="' + index + '" ' + (item.status !== 'failed' ? 'checked' : '') + '><span><b>' + esc(item.name) + '</b><small>' + esc(item.url) + '</small></span><span class="directory-status ' + (item.status === 'failed' ? 'failed' : '') + '">' + status + '</span></label>';
      }).join('') : '<div class="muted">没有解析到可导入的 RSS 链接。</div>');
    if ($('btn-directory-select-all')) $('btn-directory-select-all').hidden = !candidates.length;
    if ($('btn-directory-commit')) $('btn-directory-commit').hidden = !candidates.length;
  }

  async function parseDirectoryChat(event) {
    event.preventDefault();
    var inputEl = $('directory-chat-input');
    var text = (inputEl && inputEl.value ? inputEl.value : '').trim();
    var match = text.match(/https?:\/\/[^\s]+/i);
    if (!match) {
      directoryMessage('请在消息中提供一个 http(s) URL，我才能抓取并解析目录。', 'assistant');
      return;
    }
    var url = match[0].replace(/[),.;]+$/, '');
    directoryMessage(text, 'user');
    directoryMessage('正在抓取目录、解析 RSS 链接并执行安全校验…', 'assistant');
    try {
      var data = await request('/api/v1/information-sources/import-directory/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url, max_items: 200, check_health: $('directory-check-health') ? $('directory-check-health').checked : true })
      });
      if (!data) {
        var lastErr = (client()._lastError && client()._lastError.message) || client()._lastViewError || '网络请求异常或无法抓取目标目录';
        throw new Error(lastErr);
      }
      renderDirectoryPreview(data);
      if (data.candidates && data.candidates.length) {
        directoryMessage('解析完成：成功提取 ' + data.candidates.length + ' 条候选 RSS。请在下方预览列表中勾选需要的项，然后点击【确认添加选中 RSS】将其入库。', 'assistant');
      } else {
        directoryMessage('解析完成，但未能从该页面提取到可用的 RSS / OPML 链接。', 'assistant');
      }
    } catch (e) {
      var errText = e.message || String(e);
      directoryMessage('解析失败：' + errText + '。（若需重试，可修改链接或点击右上角【开启新对话】）', 'assistant');
    }
  }

  function selectAllDirectory() {
    var boxes = document.querySelectorAll('.directory-check');
    var all = Array.prototype.every.call(boxes, function (box) { return box.checked; });
    boxes.forEach(function (box) { box.checked = !all; });
  }

  async function commitDirectory() {
    var items = Array.prototype.slice.call(document.querySelectorAll('.directory-check:checked')).map(function (box) {
      return state.directory.candidates[Number(box.dataset.index)];
    }).filter(Boolean);
    if (!items.length) {
      directoryMessage('请至少选择一条 RSS。', 'assistant');
      return;
    }
    var button = $('btn-directory-commit');
    if (button) button.disabled = true;
    try {
      var result = await request('/api/v1/information-sources/import-directory/commit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          directory_url: state.directory.url,
          profile: $('directory-profile') ? $('directory-profile').value : 'both',
          items: items
        })
      });
      if (!result) {
        var lastErr = (client()._lastError && client()._lastError.message) || '批量添加请求失败';
        throw new Error(lastErr);
      }
      directoryMessage('已成功添加 ' + result.count + ' 条 RSS 来源！跳过 ' + ((result.skipped || []).length) + ' 条重复项。已自动刷新信息源列表并接入采集流水线。', 'assistant');
      await loadSources();
      await loadSchedules();
    } catch (e) {
      directoryMessage('批量添加失败：' + (e.message || e), 'assistant');
    } finally {
      if (button) button.disabled = false;
    }
  }

  async function healthAll() {
    var log = $('health-log'); log.textContent = '并发检测中…'; var lines = [];
    await Promise.all(state.sources.map(async function (source) { try { var result = await request('/api/v1/information-sources/' + encodeURIComponent(source.source_id) + '/test', { method: 'POST' }); lines.push(source.source_id + ' [' + source.kind + ']: ' + (result.ok ? 'OK' : 'FAIL') + ' — ' + (result.message || '')); } catch (e) { lines.push(source.source_id + ': ERROR ' + (e.message || e)); } }));
    log.textContent = lines.sort().join('\n') || '无来源'; $('kpi-health').textContent = lines.filter(function (x) { return x.indexOf(': OK') >= 0; }).length;
  }

  function trace(status, result) {
    var steps = result && result.steps ? result.steps : [];
    var traceRoot = $('queue-trace'); if (!traceRoot) return; traceRoot.innerHTML = steps.map(function (step, i) { return '<div class="trace-step"><span class="num">' + (i + 1) + '</span><div><b>' + esc(step.step || 'agent step') + '</b><small>' + esc(JSON.stringify(step)) + '</small></div><span class="status-pill">' + (step.ok === false ? '需复核' : '完成') + '</span></div>'; }).join('') || '<div class="trace-step"><span class="num">•</span><div><b>' + esc(status) + '</b><small>等待 Agent 返回步骤</small></div><span class="status-pill">运行中</span></div>';
  }

  async function pollInformationRun(runId, teamId, onEvent) {
    var after = 0;
    var deadline = Date.now() + 180000;
    while (Date.now() < deadline) {
      var ev = await request('/api/v1/information-runs/' + encodeURIComponent(runId) + '/events?after_seq=' + after);
      if (ev && ev.events && ev.events.length) {
        after = ev.last_seq || after;
        if (onEvent) onEvent(ev.events);
        var steps = ev.events.map(function (e) {
          return { step: (e.agent || '') + ':' + (e.phase || e.status), ok: e.status !== 'failed', message: e.message };
        });
        trace('running', { steps: steps });
      }
      var run = await request('/api/v1/information-runs/' + encodeURIComponent(runId));
      if (!run) {
        await new Promise(function (r) { setTimeout(r, 600); });
        continue;
      }
      if (run.status === 'completed' || run.status === 'degraded') {
        return run.result && Object.keys(run.result).length ? Object.assign({}, run.result, {
          run_status: run.status,
          information_run_id: run.run_id,
          cards: run.cards || [],
          steps: (run.result && run.result.steps) || []
        }) : run;
      }
      if (run.status === 'failed' || run.status === 'cancelled') {
        throw new Error(run.error || ('run ' + run.status));
      }
      setText(teamMeta[teamId].note, ' 后台 ' + (run.status || 'queued') + '…');
      await new Promise(function (r) { setTimeout(r, 500); });
    }
    throw new Error('运行超时：后台仍在执行，可稍后刷新查看文档');
  }

  async function runTeam(teamId) {
    switchTab(teamId === 'ai_news_60s' ? 'ai60' : 'world');
    setText('inspector-log', '启动 ' + teamId + '…');
    trace('running');
    var meta = teamMeta[teamId];
    if (teamState[teamId].running) return;
    teamState[teamId].running = true;
    resetBriefForRun(teamId);
    setAgentProgress(teamId, 0, 'running');
    $(meta.start).disabled = true;
    var sourceIds = Array.prototype.slice.call(document.querySelectorAll('.source-check:checked')).map(function (x) { return x.value; });
    var startedAt = Date.now();
    startLiveProgress(teamId, sourceIds.length, startedAt);
    try {
      var accepted = await request('/api/v1/information-sources/teams/' + encodeURIComponent(teamId) + '/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_ids: sourceIds })
      });
      if (!accepted) throw new Error((client()._lastError && client()._lastError.message) || 'enqueue failed');
      var result = accepted;
      if (accepted.async || accepted.accepted || accepted.status === 'queued') {
        setText('inspector-log', '已入队 run_id=' + (accepted.run_id || '—') + '，后台执行中…');
        result = await pollInformationRun(accepted.run_id, teamId);
      }
      stopLiveProgress(teamId);
      setText('inspector-log', JSON.stringify(result, null, 2));
      $('inspector-log').textContent = teamId + ' · ' + new Date().toLocaleString() + '\n' + JSON.stringify(result, null, 2);
      trace('completed', result);
      await animateTeamProgress(teamId, result);
      await loadLatestDocs();
      await loadHistory();
    } catch (e) {
      stopLiveProgress(teamId);
      teamState[teamId].running = false;
      setAgentProgress(teamId, 0, 'idle');
      setText(meta.note, ' failed / retry');
      setText('inspector-log', 'ERROR ' + (e.message || e));
    } finally {
      $(meta.start).disabled = false;
    }
  }

  function renderDoc(doc, frameId) {
    var frame = $(frameId); if (!frame) return;
    var key = doc ? [doc.document_id || '', doc.version || '', doc.as_of || ''].join(':') : 'empty';
    // Polling may observe the same document repeatedly. Do not reset srcdoc:
    // resetting it destroys the reader's scroll position and interrupts reading.
    if (frame.dataset.docKey === key) return;
    frame.dataset.docKey = key;
    frame.srcdoc = doc && doc.html ? doc.html : '<div style="font:14px system-ui;padding:30px;color:#64748b">暂无报告，请先运行对应团队。</div>';
  }
  function reportReaderUrl(channel, doc) {
    var base = '/report-viewer.html?channel=' + encodeURIComponent(channel);
    if (!doc || !doc.document_id || !doc.version) return base;
    return base + '&document_id=' + encodeURIComponent(doc.document_id) + '&version=' + encodeURIComponent(String(doc.version));
  }
  function openReport(channel, doc) {
    var url = reportReaderUrl(channel, doc || state.latest[channel]);
    var opened = window.open(url, '_blank');
    if (opened) { opened.opener = null; opened.focus(); } else { window.location.assign(url); }
  }
  function reportReaderLink(channel, doc, label) {
    return '<a class="btn ghost report-open" data-open="' + esc(channel) + '" href="' + esc(reportReaderUrl(channel, doc)) + '" target="_blank" rel="noopener noreferrer" aria-label="在新标签打开完整动态 HTML 报告" style="margin-top:8px">' + esc(label || '查看完整动态 HTML →') + '</a>';
  }
  function claimText(value, fallback) {
    if (value && typeof value === 'object') value = value.text || value.title || value.detail || value.summary || fallback;
    var text = plainSummary(value || fallback);
    if (/^https?:\/\/\S+$/i.test(text)) return '来源仅提供链接，暂无可读标题或摘要，不能形成判断。';
    return text;
  }
  function listClaims(items, fallback, limit) {
    var rows = Array.isArray(items) ? items : [];
    rows = rows.slice(0, limit || 3).map(function (item) { return claimText(item, fallback); }).filter(Boolean);
    return rows.length ? '<ul>' + rows.map(function (x) { return '<li class="brief-expandable" tabindex="0" role="button" aria-expanded="false" title="点击展开完整结论">' + esc(x) + '</li>'; }).join('') + '</ul>' : '<div class="brief-empty">' + esc(fallback) + '</div>';
  }
  function insightItems(channel, doc) {
    var r = doc && doc.report || {}, a = r.analysis || {};
    if (channel === 'ai_news_60s') {
      var topics = (a.topic_clusters || []).slice(0, 3).map(function (x) { return (x.name || '主题') + '：' + Math.round(Number(x.share || 0) * 100) + '%，' + (x.count || 0) + ' 条证据'; });
      var signals = (a.top_signals || []).slice(0, 3).map(function (x) { return (x.title || '信号') + '（' + (x.score || '—') + '分）'; });
      var impacts = (a.business_implications || r.why_it_matters || []).slice(0, 3).map(function (x) { return claimText(x.detail || x, '待确认影响'); });
      var counters = (a.open_questions || r.risks_and_counterpoints || []).slice(0, 3).map(function (x) { return claimText(x, '待验证问题'); });
      return { headline: r.headline || doc.title || 'AI 情报研判', focus: (r.bullets || []).slice(0, 4).map(function (x) { return claimText(x, '待确认信号'); }), core: topics.length ? topics : ['暂无足够主题证据'], hot: signals.length ? signals : ['暂无高分信号'], insight: impacts.length ? impacts : ['暂无可确认的业务影响推断'], counter: counters.length ? counters : ['暂无反证摘要'], sourceCount: a.source_count || (r.citations || []).length, domains: a.source_diversity || 0, score: a.evidence_score, cutoff: r.data_cutoff || doc.as_of };
    }
    var drivers = (r.drivers || a.drivers || []).slice(0, 3).map(function (x) { return claimText(x, '待确认驱动'); });
    var trends = (r.data_trends || a.data_trends || []).slice(0, 3).map(function (x) { return claimText(x, '待确认趋势'); });
    var scenarios = (r.scenarios || []).slice(0, 3).map(function (x) { return (x.name || '情景') + '：' + claimText(x.summary, '待生成'); });
    var transmission = (r.market_transmission || []).slice(0, 3).map(function (x) { return claimText(x, '待确认传导'); });
    var countersWorld = (r.views_and_counterpoints || []).slice(0, 3).map(function (x) { return claimText(x, '待确认反证'); });
    return { headline: claimText(r.what_happened, doc.title || '世界趋势研判'), focus: [claimText(r.what_happened, '暂无事件摘要')].concat(drivers.slice(0, 3)), core: drivers.length ? drivers : ['暂无关键驱动'], hot: trends.length ? trends : ['暂无数据趋势'], insight: transmission.length ? transmission : (scenarios.length ? scenarios : ['暂无可确认传导']), counter: countersWorld.length ? countersWorld : ['暂无反证摘要'], sourceCount: a.source_count || (r.citations || []).length, domains: a.source_diversity || 0, score: a.evidence_score, cutoff: r.data_cutoff || doc.as_of };
  }
  function insightListHtml(items, emptyText) {
    if (!items || !items.length) return '<div class="brief-empty">' + esc(emptyText || '暂无') + '</div>';
    return '<ul>' + items.slice(0, 4).map(function (it) {
      var body = typeof it === 'string' ? it : (it.body || it.title || '');
      var title = typeof it === 'string' ? '' : (it.title || '');
      var domains = typeof it === 'string' ? '' : ((it.source_domains || []).join(', '));
      var single = typeof it === 'object' && it.kind === 'inference' && (it.source_domains || []).length < 2;
      return '<li class="brief-expandable" tabindex="0" role="button" aria-expanded="false" title="点击展开完整结论"><strong>' + esc(title || body.slice(0, 24) || '要点') + '</strong> ' + esc(body) +
        (domains || single ? '<small style="display:block;opacity:.75;margin-top:3px">' + esc(domains) + (single ? ' · 单一来源推断' : '') + '</small>' : '') +
        '</li>';
    }).join('') + '</ul>';
  }

  /** Paint both home strip and dark executive panel from the same brief contract. */
  function applyBrief(brief, channel) {
    channel = channel || (brief && brief.channel) || 'ai_news_60s';
    if ($('brief-strip')) $('brief-strip').classList.remove('is-running');
    var channelLabel = channel === 'dufu_world_intel' ? '世界趋势' : 'AI 60 秒';

    // Light strip (always present in P13 layout)
    if ($('brief-headline')) {
      if (!brief) {
        if ($('in-focus-text')) $('in-focus-text').textContent = '运行团队后显示核心结论';
        $('brief-headline').textContent = '—';
        if ($('brief-bullets')) $('brief-bullets').innerHTML = '';
        if ($('brief-hot')) $('brief-hot').innerHTML = '<div class="muted">—</div>';
        if ($('brief-trend')) $('brief-trend').innerHTML = '<div class="muted">—</div>';
        if ($('brief-insights')) $('brief-insights').innerHTML = '<div class="muted">—</div>';
        if ($('brief-limits')) $('brief-limits').textContent = '';
      } else {
        var focus = (brief.focus_items && brief.focus_items[0] && brief.focus_items[0].body) || brief.headline || '—';
        if ($('in-focus-text')) $('in-focus-text').textContent = focus;
        $('brief-headline').textContent = brief.headline || '—';
        if ($('brief-bullets')) {
          $('brief-bullets').innerHTML = (brief.bullets || []).slice(0, 4).map(function (b) {
            return '<li class="brief-expandable" tabindex="0" role="button" aria-expanded="false" title="点击展开完整结论">' + esc(b) + '</li>';
          }).join('');
        }
        if ($('brief-hot')) $('brief-hot').innerHTML = insightListHtml(brief.hot_analysis, '暂无热门分析');
        if ($('brief-trend')) $('brief-trend').innerHTML = insightListHtml(brief.trending_news, '暂无趋势新闻');
        if ($('brief-insights')) $('brief-insights').innerHTML = insightListHtml(brief.distinctive_insights, '暂无独到见解');
        if ($('brief-limits')) {
          $('brief-limits').textContent = (brief.evidence_limits || []).join(' · ') || (brief.disclaimer || '');
        }
      }
    }

    // Dark executive panel
    var root = $('executive-brief');
    if (!root) return;
    if (!brief) {
      root.innerHTML = '<div class="brief-head"><div><div class="brief-kicker">IN FOCUS · EVIDENCE FIRST</div><h2 class="brief-title">等待本轮研究结论</h2><div class="brief-meta">启动团队或等待定时任务完成后，这里会显示结论、信号、影响和反证。</div></div><span class="brief-badge">研究/模拟</span></div><div class="brief-grid"><article class="brief-card"><h3>核心结论</h3><div class="brief-empty">暂无报告。</div></article><article class="brief-card"><h3>热门分析</h3><div class="brief-empty">等待主题聚类。</div></article><article class="brief-card insight"><h3>独到见解</h3><div class="brief-empty">等待跨来源推断与反证。</div></article><article class="brief-card"><h3>趋势新闻</h3><div class="brief-empty">等待引用标题。</div></article></div>';
      return;
    }
    var score = brief.evidence_score == null ? '—' : brief.evidence_score;
    var status = (brief.source_count || (brief.evidence_ids || []).length) ? '已形成结论' : '证据不足';
    var counters = (brief.distinctive_insights || []).filter(function (x) { return x.kind === 'counter'; });
    var insights = (brief.distinctive_insights || []).filter(function (x) { return x.kind !== 'counter'; });
    root.innerHTML =
      '<div class="brief-head"><div><div class="brief-kicker">IN FOCUS · ' + esc(channelLabel) + '</div>' +
      '<h2 class="brief-title">' + esc(brief.headline || '—') + '</h2>' +
      '<div class="brief-meta">' + esc(brief.source_count || 0) + ' 条证据 · ' + esc(brief.source_diversity || (brief.focus_items && brief.focus_items[0] && brief.focus_items[0].source_domains || []).length || 0) +
      ' 个来源域 · 综合分 ' + esc(score) + ' · 截止 ' + esc(brief.as_of || '—') +
      ' · ' + esc(brief.disclaimer || '研究/分析用途，仅供内部治理参考') + '</div></div>' +
      '<span class="brief-badge">' + esc(status) + '</span></div>' +
      '<div class="brief-focus" aria-label="本轮重点信号">' +
      ((brief.focus_items || []).length
        ? (brief.focus_items || []).slice(0, 4).map(function (item, i) {
          return '<div class="focus-chip"><b>重点 ' + (i + 1) + '</b><span>' + esc(item.body || item.title || '') + '</span></div>';
        }).join('')
        : '<div class="brief-empty">暂无重点信号</div>') +
      '</div>' +
      '<div class="brief-grid">' +
      '<article class="brief-card"><h3>核心结论 · 要点</h3>' + listClaims(brief.bullets, '暂无可确认结论') + '<small>结论来自本轮来源，不代表预测。</small></article>' +
      '<article class="brief-card"><h3>热门分析 · 趋势与影响</h3>' + insightListHtml(brief.hot_analysis, '暂无趋势分析') + '<small>按主题/信号支持度整理。</small></article>' +
      '<article class="brief-card insight"><h3>独到见解</h3>' + insightListHtml(insights, '暂无可确认推断') + '<small>推断需结合反证与来源。</small></article>' +
      '<article class="brief-card"><h3>趋势新闻 · 反证</h3>' + insightListHtml((brief.trending_news || []).slice(0, 2).concat(counters), '暂无') + '<small>研究/分析用途，仅供内部治理参考。</small></article>' +
      '</div>';
  }

  function resetBriefForRun(channel) {
    var strip = $('brief-strip');
    if (strip) strip.classList.add('is-running');
    if ($('in-focus-text')) $('in-focus-text').textContent = 'Agent 正在重新分析本轮来源…';
    if ($('brief-headline')) $('brief-headline').textContent = '本轮结论生成中';
    if ($('brief-bullets')) $('brief-bullets').innerHTML = '<li class="brief-expandable">采集与核验进行中</li><li class="brief-expandable">等待主题、信号和反证完成</li>';
    if ($('brief-hot')) $('brief-hot').innerHTML = '<div class="muted">正在计算热门分析…</div>';
    if ($('brief-trend')) $('brief-trend').innerHTML = '<div class="muted">正在整理趋势新闻…</div>';
    if ($('brief-insights')) $('brief-insights').innerHTML = '<div class="muted">正在形成独到见解…</div>';
    if ($('brief-limits')) $('brief-limits').textContent = '本轮旧结论已清除；完成后将替换为新结论。';
  }

  function renderExecutiveBrief(channel, doc) {
    // Prefer server contract; fall back to client insightItems only if needed
    if (doc && doc.executive_summary) {
      applyBrief(doc.executive_summary, channel);
      return;
    }
    if (!doc || !doc.report) {
      applyBrief(null, channel);
      return;
    }
    var x = insightItems(channel, doc);
    applyBrief({
      channel: channel,
      headline: x.headline,
      bullets: x.core && x.core.length ? x.core : x.focus,
      focus_items: (x.focus || []).map(function (b) { return { kind: 'fact', title: 'In Focus', body: b, source_domains: [] }; }),
      hot_analysis: (x.hot || []).map(function (b) { return { kind: 'analysis', title: '热门分析', body: b, source_domains: [] }; }),
      trending_news: (x.focus || []).map(function (b) { return { kind: 'fact', title: b.slice(0, 24), body: b, source_domains: [] }; }),
      distinctive_insights: (x.insight || []).map(function (b) { return { kind: 'analysis', title: '见解', body: b, source_domains: [] }; }).concat(
        (x.counter || []).map(function (b) { return { kind: 'counter', title: '反证', body: b, source_domains: [] }; })
      ),
      evidence_limits: ['研究/分析用途，仅供内部治理参考'],
      as_of: x.cutoff,
      source_count: x.sourceCount,
      source_diversity: x.domains,
      evidence_score: x.score,
      disclaimer: '研究/分析用途，仅供内部治理参考'
    }, channel);
  }

  function renderLatestSummary(channel, doc) {
    if (!doc) return '<div class="muted">暂无 ' + esc(channel) + ' 报告</div>';
    var head = (doc.executive_summary && doc.executive_summary.headline) || (insightItems(channel, doc).headline) || doc.title || channel;
    var meta = doc.executive_summary
      ? ((doc.executive_summary.source_count || 0) + ' 条证据 · v' + (doc.version || '—') + ' · ' + (doc.as_of || '—'))
      : ((insightItems(channel, doc).sourceCount || 0) + ' 条证据 · v' + (doc.version || '—') + ' · ' + (doc.as_of || '—'));
    return '<div style="font-size:12px;font-weight:800">' + esc(head) + '</div><div class="muted" style="margin-top:5px">' + esc(meta) + '</div>' + reportReaderLink(channel, doc);
  }

  async function loadBriefs(preferredChannel) {
    try {
      var data = await request('/api/v1/information-documents/latest-summary');
      var sum = (data && data.summaries) || {};
      state.briefs = sum;
      var ch = preferredChannel || activeBriefChannel();
      var preferred = sum[ch] || sum.ai_news_60s || sum.dufu_world_intel || null;
      applyBrief(preferred, preferred && preferred.channel || ch);
    } catch (e) { /* soft */ }
  }

  function activeBriefChannel() {
    var selected = document.querySelector('.workbench-primary-nav .tab.active');
    return selected && selected.dataset.tab === 'world' ? 'dufu_world_intel' : 'ai_news_60s';
  }

  function plainSummary(value, limit) {
    var text = String(value == null ? '' : value).replace(/<\s*script[^>]*>[\s\S]*?<\s*\/\s*script\s*>/gi, ' ').replace(/<[^>]*>/g, ' ').replace(/&nbsp;|&#160;/gi, ' ').replace(/&amp;/gi, '&').replace(/&lt;/gi, '<').replace(/&gt;/gi, '>').replace(/\s+/g, ' ').trim();
    limit = limit || 260;
    return text.length > limit ? text.slice(0, limit) + '…' : text;
  }
  function reportLine(value, fallback) { if (Array.isArray(value)) value = value[0]; if (value && typeof value === 'object') value = value.text || value.title || value.name; return plainSummary(value || fallback || '等待报告发布。'); }
  function hydrateBoxes(teamId, doc) {
    if (!doc || !doc.report || teamState[teamId].running) return;
    var r = doc.report, values;
    if (teamId === 'ai_news_60s') {
      var a = r.analysis || {}, clusters = (a.topic_clusters || []).slice(0, 3).map(function (x) { return plainSummary((x.name || '主题') + ' ' + Math.round(Number(x.share || 0) * 100) + '%', 50); }).join(' · '),
        evidence = a.source_count ? '证据 ' + a.source_count + ' 条 · ' + (a.source_diversity || 0) + ' 个来源域 · 综合分 ' + (a.evidence_score || '—') : reportLine(r.bullets, '等待证据综合。'),
        judgment = clusters ? '主题：' + clusters + ' · 信号：' + (a.signal_strength || '待定') : reportLine(r.why_it_matters, '等待判断路径。'),
        impact = (a.business_implications || []).slice(0, 2).map(function (x) { return plainSummary((x.stage || '影响') + '：' + (x.detail || ''), 100); }).join('；') || (Array.isArray(r.related_companies) ? r.related_companies.join(' · ') : reportLine(r.related_companies, '等待业务影响。')),
        questions = (a.open_questions || []).slice(0, 2).map(function (x) { return plainSummary(x, 100); }).join('；') || reportLine(r.risks_and_counterpoints, '等待反证。'),
        published = (a.reasoning_steps || []).length ? '已完成 ' + a.reasoning_steps.length + ' 个研判阶段' : '动态 HTML 已发布';
      values = [r.headline, evidence, judgment, impact, questions, published + ' · ' + (doc.evidence_urls || []).length + ' 条引用 · v' + (doc.version || '—')];
    } else {
      values = [reportLine(r.what_happened, '等待事件事实。'), reportLine(r.timeline, '等待时间线。'), reportLine(r.drivers, '等待关键驱动。'), reportLine(r.data_trends, '等待数据趋势。'), reportLine(r.counterpoints, '等待反证。'), reportLine(r.scenarios, '等待三情景树。'), reportLine(r.market_transmission, '等待市场传导。'), (doc.evidence_urls || []).length + ' 条来源 · 截止 ' + (doc.as_of || '—')];
    }
    var root = $(teamMeta[teamId].grid); if (!root) return; values.forEach(function (value, index) { var box = root.querySelector('[data-box-index="' + index + '"]'); if (!box) return; var p = box.querySelector('p'); if (p) p.textContent = value; box.classList.remove('filling'); box.classList.add('filled'); var label = box.querySelector('.box-status'); if (label) label.textContent = '已填充'; });
  }
  async function loadLatestDocs() {
    try {
      var ai = await request('/api/v1/information-documents/latest/ai_news_60s');
      state.latest.ai_news_60s = ai;
      renderDoc(ai, 'frame-ai60');
      hydrateBoxes('ai_news_60s', ai);
      if (ai && ai.executive_summary) applyBrief(ai.executive_summary);
    } catch (e) { renderDoc(null, 'frame-ai60'); }
    try {
      var world = await request('/api/v1/information-documents/latest/dufu_world_intel');
      state.latest.dufu_world_intel = world;
      renderDoc(world, 'frame-world');
      hydrateBoxes('dufu_world_intel', world);
    } catch (e2) { renderDoc(null, 'frame-world'); }
    var selected = document.querySelector('.workbench-primary-nav .tab.active');
    var channel = selected && selected.dataset.tab === 'world' ? 'dufu_world_intel' : 'ai_news_60s';
    if (typeof renderExecutiveBrief === 'function') renderExecutiveBrief(channel, state.latest[channel]);
    $('latest-summary').innerHTML = renderLatestSummary('ai_news_60s', state.latest.ai_news_60s) +
      '<hr style="border:0;border-top:1px solid #edf1f5;margin:12px 0">' +
      renderLatestSummary('dufu_world_intel', state.latest.dufu_world_intel);
    await loadBriefs();
  }

  async function loadOpenWeights() {
    var root = $('openweights-grid');
    if (root) root.innerHTML = '<div class="muted" style="padding:24px;grid-column:1/-1">正在加载开放权重模型知识库…</div>';
    try {
      var res = await request('/api/v1/model-clearance/licenses');
      state.openweights = (res && res.models) || [];
      populateVendorFilter();
      renderOpenWeights();
    } catch (e) {
      if (root) root.innerHTML = '<div style="padding:20px;color:#dc2626;grid-column:1/-1">加载开放权重模型库失败：' + esc(e.message || e) + '</div>';
    }
  }

  function populateVendorFilter() {
    var sel = $('ow-filter-vendor');
    if (!sel) return;
    var current = sel.value;
    var list = state.openweights || [];
    var vendorSet = {};
    list.forEach(function (m) { if (m.vendor) vendorSet[m.vendor] = true; });
    var vendors = Object.keys(vendorSet).sort();
    sel.innerHTML = '<option value="">全部厂商/机构</option>' + vendors.map(function (v) {
      return '<option value="' + esc(v) + '"' + (v === current ? ' selected' : '') + '>' + esc(v) + '</option>';
    }).join('');
  }

  function renderOpenWeights() {
    var root = $('openweights-grid');
    if (!root) return;
    var search = ($('ow-filter-search') ? $('ow-filter-search').value : '').trim().toLowerCase();
    var licFilter = $('ow-filter-license') ? $('ow-filter-license').value : '';
    var vendorFilter = $('ow-filter-vendor') ? $('ow-filter-vendor').value : '';

    var all = state.openweights || [];
    var total = all.length;
    var commercial = all.filter(function (m) { return m.license_class === 'commercial_ok'; }).length;
    var conditional = all.filter(function (m) { return m.license_class === 'conditional'; }).length;
    var restricted = all.filter(function (m) { return m.license_class === 'restricted'; }).length;

    if ($('ow-kpi-total')) $('ow-kpi-total').textContent = total || '—';
    if ($('ow-kpi-commercial')) $('ow-kpi-commercial').textContent = commercial;
    if ($('ow-kpi-conditional')) $('ow-kpi-conditional').textContent = conditional;
    if ($('ow-kpi-restricted')) $('ow-kpi-restricted').textContent = restricted;

    var filtered = all.filter(function (m) {
      if (licFilter && m.license_class !== licFilter) return false;
      if (vendorFilter && m.vendor !== vendorFilter) return false;
      if (search) {
        var str = ((m.display_name || '') + ' ' + (m.model_id || '') + ' ' + (m.vendor || '') + ' ' + (m.license_id || '')).toLowerCase();
        if (str.indexOf(search) === -1) return false;
      }
      return true;
    });

    if (!filtered.length) {
      root.innerHTML = '<div class="muted" style="padding:24px;grid-column:1/-1">未找到匹配的开放权重模型。</div>';
      return;
    }

    root.innerHTML = filtered.map(function (m) {
      var licCls = m.license_class || 'conditional';
      var conditions = Array.isArray(m.license_conditions) ? m.license_conditions : [];
      var paramsText = m.params_b ? m.params_b + 'B 参数' : 'MoE / 多模态';
      var clearanceUrl = '/ai-model-entry-clearance.html?model_id=' + encodeURIComponent(m.model_id);

      return '<article class="ow-card">' +
        '<div class="ow-card-head">' +
          '<div>' +
            '<h3 class="ow-card-title">' + esc(m.display_name || m.model_id) + '</h3>' +
            '<div class="ow-card-meta">' + esc(m.vendor || '开源社区') + ' · ' + esc(m.vendor_country || 'Global') + ' · <code>' + esc(m.model_id) + '</code></div>' +
          '</div>' +
          '<span class="ow-badge ' + licCls + '">' + esc(m.license_id || licCls) + '</span>' +
        '</div>' +
        '<div style="font-size:11px;color:#475569;display:flex;gap:12px;flex-wrap:wrap">' +
          '<span>规模：<b>' + esc(paramsText) + '</b></span>' +
          '<span>格式：<b>' + esc(m.weights_format || 'safetensors') + '</b></span>' +
          (m.open_weights_signatory ? '<span style="color:#0f766e;font-weight:700">✓ Open Weights Letter 签署方</span>' : '') +
        '</div>' +
        (conditions.length ? '<div class="ow-tags">' + conditions.map(function (c) { return '<span class="ow-tag">' + esc(c) + '</span>'; }).join('') + '</div>' : '') +
        '<div class="ow-actions">' +
          '<a href="' + esc(clearanceUrl) + '" class="btn" style="background:#0f766e;color:#fff">🛡️ 发起准入评审</a>' +
          (m.license_url ? '<a href="' + esc(m.license_url) + '" target="_blank" rel="noopener noreferrer" class="btn ghost" style="padding:4px 6px">📄 许可证</a>' : '') +
          (m.weights_url ? '<a href="' + esc(m.weights_url) + '" target="_blank" rel="noopener noreferrer" class="btn ghost" style="padding:4px 6px">📦 权重库</a>' : '') +
        '</div>' +
      '</article>';
    }).join('');
  }

  async function loadHistory() { var channel = $('docs-channel').value; try { var data = await request('/api/v1/information-documents?limit=30' + (channel ? '&channel=' + encodeURIComponent(channel) : '')); var rows = data.documents || []; $('kpi-docs').textContent = rows.length; $('docs-body').innerHTML = rows.length ? rows.map(function (d) { return '<tr class="doc-row" data-id="' + esc(d.document_id) + '"><td>' + esc(d.channel) + '</td><td>v' + esc(d.version) + '</td><td>' + esc(d.title) + '</td><td>' + esc(d.as_of) + '</td><td><code>' + esc(d.run_id) + '</code></td><td>' + reportReaderLink(d.channel, d, '打开 ↗') + '</td></tr>'; }).join('') : '<tr><td colspan="6" class="muted">无历史文档</td></tr>'; $('docs-body').querySelectorAll('.doc-row').forEach(function (row) { row.addEventListener('click', function (event) { if (event.target.closest('.report-open')) return; var doc = rows.find(function (x) { return x.document_id === row.dataset.id; }); $('doc-preview').innerHTML = doc && doc.html ? '<iframe class="doc" sandbox title="历史报告" srcdoc="' + esc(doc.html) + '"></iframe>' : ''; }); }); } catch (e) { $('docs-body').innerHTML = '<tr><td colspan="6" style="color:#dc2626">' + esc(e.message || e) + '</td></tr>'; } }

  function scheduleHtml(item) { var status = item.last_status === 'success' ? '完成' : item.last_status === 'failed' ? '失败' : item.enabled ? '等待' : '暂停'; return '<div class="schedule-item"><strong>' + esc(item.name) + '</strong><div class="schedule-meta">' + esc(item.team_id) + ' · 每 ' + esc(item.interval_minutes) + ' 分钟 · ' + status + '<br>下次：' + esc(item.next_run_at || '—') + '</div><div class="schedule-actions"><button class="btn ghost schedule-run" data-id="' + esc(item.schedule_id) + '" type="button">立即运行</button><button class="btn ghost schedule-toggle" data-id="' + esc(item.schedule_id) + '" data-enabled="' + (!item.enabled) + '" type="button">' + (item.enabled ? '暂停' : '启用') + '</button><button class="btn ghost schedule-delete" data-id="' + esc(item.schedule_id) + '" type="button">删除</button></div></div>'; }
  async function loadSchedules() {
    try {
      var data = await request('/api/v1/information-schedules');
      state.schedules = (data && data.schedules) || [];
      $('schedule-list').innerHTML = state.schedules.length ? state.schedules.map(scheduleHtml).join('') : '<div class="muted">暂无定时任务</div>';
      updateKpis();
      $('schedule-list').querySelectorAll('.schedule-run').forEach(function (b) {
        b.addEventListener('click', async function () {
          var r = await request('/api/v1/information-schedules/' + b.dataset.id + '/run', { method: 'POST' });
          if (!r && client()._lastError) {
            alert('运行失败: ' + (client()._lastError.message || ''));
          }
          await loadSchedules();
          await loadLatestDocs();
        });
      });
      $('schedule-list').querySelectorAll('.schedule-toggle').forEach(function (b) {
        b.addEventListener('click', async function () {
          await request('/api/v1/information-schedules/' + b.dataset.id, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: b.dataset.enabled === 'true' })
          });
          await loadSchedules();
        });
      });
      $('schedule-list').querySelectorAll('.schedule-delete').forEach(function (b) {
        b.addEventListener('click', async function () {
          if (!confirm('确定删除此定时任务？')) return;
          await request('/api/v1/information-schedules/' + b.dataset.id, { method: 'DELETE' });
          await loadSchedules();
        });
      });
    } catch (e) {
      $('schedule-list').innerHTML = '<div style="color:#dc2626">' + esc(e.message || e) + '</div>';
    }
  }

  async function createSchedule(event) {
    event.preventDefault();
    var btn = $('btn-create-schedule');
    if (btn) btn.disabled = true;
    try {
      var nameVal = $('schedule-name') ? $('schedule-name').value.trim() : '';
      var teamVal = $('schedule-team') ? $('schedule-team').value : 'ai_news_60s';
      var intervalVal = Number($('schedule-interval') ? $('schedule-interval').value : 30) || 30;
      var immediateVal = $('schedule-immediate') ? $('schedule-immediate').checked : false;
      var sourceIds = Array.prototype.slice.call(document.querySelectorAll('.source-check:checked')).map(function (x) { return x.value; });

      var res = await request('/api/v1/information-schedules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: nameVal,
          team_id: teamVal,
          interval_minutes: intervalVal,
          run_immediately: immediateVal,
          source_ids: sourceIds
        })
      });
      if (!res) {
        var err = (client()._lastError && client()._lastError.message) || '添加定时任务失败';
        throw new Error(err);
      }
      if ($('schedule-immediate')) $('schedule-immediate').checked = false;
      await loadSchedules();
    } catch (e) {
      alert('添加定时任务失败：' + (e.message || e));
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  if ($('btn-refresh-openweights')) $('btn-refresh-openweights').addEventListener('click', loadOpenWeights);
  if ($('ow-filter-search')) $('ow-filter-search').addEventListener('input', renderOpenWeights);
  if ($('ow-filter-license')) $('ow-filter-license').addEventListener('change', renderOpenWeights);
  if ($('ow-filter-vendor')) $('ow-filter-vendor').addEventListener('change', renderOpenWeights);

  $('btn-refresh-sources').addEventListener('click', loadSources); $('btn-save-source-selection').addEventListener('click', saveSourceSelection); $('btn-select-all-sources').addEventListener('click', toggleAllSources); $('btn-add-fixture').addEventListener('click', addFixture); $('btn-health').addEventListener('click', healthAll); $('btn-run-ai60').addEventListener('click', function () { runTeam('ai_news_60s'); }); $('btn-run-dufu').addEventListener('click', function () { runTeam('dufu_world_intel'); }); $('btn-start-ai60').addEventListener('click', function () { runTeam('ai_news_60s'); }); $('btn-start-dufu').addEventListener('click', function () { runTeam('dufu_world_intel'); }); $('btn-docs').addEventListener('click', loadHistory); $('btn-latest').addEventListener('click', loadLatestDocs); $('btn-refresh-schedules').addEventListener('click', loadSchedules); $('schedule-form').addEventListener('submit', createSchedule); $('source-kind').addEventListener('change', syncSourceKind); $('source-profile').addEventListener('change', syncSourcePreview); $('source-name').addEventListener('input', syncSourcePreview); $('source-form').addEventListener('submit', createSource); $('btn-reset-source').addEventListener('click', resetSourceForm); $('directory-chat-form').addEventListener('submit', parseDirectoryChat); if ($('btn-directory-reset')) $('btn-directory-reset').addEventListener('click', resetDirectoryChat); document.querySelectorAll('.dir-preset-btn').forEach(function (btn) { btn.addEventListener('click', function () { if ($('directory-chat-input')) { $('directory-chat-input').value = btn.dataset.url || ''; $('directory-chat-form').dispatchEvent(new Event('submit')); } }); }); $('btn-directory-select-all').addEventListener('click', selectAllDirectory); $('btn-directory-commit').addEventListener('click', commitDirectory); document.querySelectorAll('.preview-tab').forEach(function (tab) { tab.addEventListener('click', function () { document.querySelectorAll('.preview-tab').forEach(function (x) { x.classList.toggle('active', x === tab); }); document.querySelectorAll('.preview-panel').forEach(function (panel) { panel.classList.toggle('active', panel.id === 'preview-' + tab.dataset.preview); }); }); });
  syncSourceKind();
  renderInfoBoxes('ai_news_60s'); renderInfoBoxes('dufu_world_intel'); renderInfoBoxes('open_weights');
  renderAgentRow('ai_news_60s'); renderAgentRow('dufu_world_intel'); renderAgentRow('open_weights');
  // Focus the primary information-source workspace on first paint; utility views
  // remain reachable from the right-side collection navigation.
  var initialTab = (typeof window !== 'undefined' && window.location && window.location.search) ? (new URLSearchParams(window.location.search)).get('tab') || 'ai60' : 'ai60';
  switchTab(initialTab);
  loadTeamAgents('ai_news_60s'); loadTeamAgents('dufu_world_intel'); loadTeamAgents('open_weights'); loadSources(); loadSchedules(); loadLatestDocs(); loadBriefs();
  // Reports are scheduled at a 30-minute cadence; a 20-second poll made the
  // iframe jump while users were reading a long report.
  window.setInterval(function () {
    if (!teamState.ai_news_60s.running && !teamState.dufu_world_intel.running && !teamState.open_weights.running) {
      loadSchedules();
      loadLatestDocs();
      loadBriefs();
    }
  }, 30 * 60 * 1000);
})();
