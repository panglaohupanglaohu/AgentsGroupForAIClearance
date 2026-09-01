/**
 * office-boot.js — 办公室场景接线 (P7-1)
 * 激活: URL 带 ?office3d=1（feature flag，默认关闭，旧场景零影响）。
 * 接管策略: 重载 window._dt3dBuildRoom；rest-area(枯山水·Owner 隐藏款) 仍委托旧实现，原样保留。
 * 数据源: OfficeState 单一 store；输入 = 位置轮询 + handleTrialEvent 钩子 + transitionTrialStatus 钩子。
 */
import { createStore, collabStats, setBreakTimeScale } from './office-state.js';
import { createOfficeScene } from './office-scene.js';
import { validateVoiceConfig } from './voice-config-validator.js';

const FLAG_ON = new URLSearchParams(location.search).get('office3d') === '1';

function bootOffice() {
  const container = document.getElementById('env-3d-container');
  const legacyCanvas = document.getElementById('env-3d-canvas');
  if (!container || !legacyCanvas) return;

  // 立即隐藏旧场景画布，避免两个 WebGL 上下文同时渲染
  legacyCanvas.style.display = 'none';

  // 自有画布，与旧场景画布互斥显示（切枯山水时还原旧画布）
  const canvas = document.createElement('canvas');
  canvas.id = 'office-3d-canvas';
  canvas.style.cssText = 'width:100%;height:100%;display:block';
  container.appendChild(canvas);

  const store = createStore();
  const sceneApi = createOfficeScene(canvas, container);
  store.subscribe((state) => { sceneApi.applyState(state); renderPanel(state); });

  // ── 覆盖层: SIMULATION 徽标 + 协作热度面板（协作能力考察的读数） ──
  const badge = document.createElement('div');
  badge.textContent = 'SIMULATION · 孪生镜像';
  badge.style.cssText = 'position:absolute;top:10px;right:12px;padding:4px 10px;border:1px solid #4d9de0;color:#2b6cb0;background:rgba(230,240,255,.85);font:600 11px/1.6 sans-serif;border-radius:4px;letter-spacing:1px;display:none;pointer-events:none;z-index:5';
  const panel = document.createElement('div');
  panel.style.cssText = 'position:absolute;top:10px;left:12px;min-width:150px;padding:8px 10px;background:rgba(255,255,255,.88);border:1px solid #e2e5e9;border-radius:6px;font:11px/1.7 sans-serif;color:#3b4048;z-index:5';
  if (getComputedStyle(container).position === 'static') container.style.position = 'relative';
  container.appendChild(badge);
  container.appendChild(panel);

  // XB-6.1 生境实时信息：写入 #env-3d-habitat（与操作提示同一左下角卡片），禁止再叠一层蓝底浮层
  function habitatSlot() {
    return document.getElementById('env-3d-habitat')
      || document.getElementById('office-habitat-hud');
  }

  function renderPanel(state) {
    badge.style.display = state.mirror ? 'block' : 'none';
    const stats = collabStats(state, 5);
    panel.innerHTML = '<b style="font-size:11px">协作热度 TOP5</b>' + (stats.length
      ? stats.map((s) => '<div>' + esc(s.pair) + ' <b>×' + s.count + '</b></div>').join('')
      : '<div style="color:#9aa1ab">演练开始后显示 Agent 协作</div>');
    // 生境 / 任务考卷 HUD → 单卡片内区块
    // XF-5：任务型用办公室语言（本步技能/考卷进度）；随机生境仍用简洁环境读数，禁止裸 hex 图腾
    const habitatHud = habitatSlot();
    const env = state.ecoEnv || null;
    // 同步任务 HUD（右上角）
    try {
      if (env && window.ecoTaskHudOnEnv) window.ecoTaskHudOnEnv(env);
    } catch (eTask) { /* ignore */ }
    if (habitatHud && env && (env.demand || env.niche_title || env.step != null)) {
      habitatHud.style.display = 'block';
      const taskExam = !!(window.__ECO_TASK_EXAM__ || (window.ecoTaskHudIsActive && window.ecoTaskHudIsActive()));
      let demandLab = env.demand || '—';
      if (taskExam && env.demand && window._ecoSkillLabel) {
        try {
          const lab = window._ecoSkillLabel(env.demand);
          if (lab && lab !== env.demand) demandLab = lab;
          else if (/^[0-9a-f]{6,}$/i.test(String(env.demand))) demandLab = '技能·' + String(env.demand).slice(0, 8);
        } catch (eL) { /* ignore */ }
      } else if (env.demand && /^[0-9a-f]{6,}$/i.test(String(env.demand))) {
        demandLab = '技能·' + String(env.demand).slice(0, 8);
      }
      if (taskExam) {
        habitatHud.innerHTML = '<b style="color:#c4b5fd;font-size:11px">📋 考卷进度（任务型）</b>'
          + '<div style="margin-top:4px">本步所需：<b style="color:#67e8f9">' + esc(demandLab) + '</b></div>'
          + (env.niche_title ? '<div style="color:#94a3b8;font-size:10px">步骤：' + esc(env.niche_title) + '</div>' : '')
          + '<div style="color:#94a3b8;font-size:10px">存活 ' + (env.living != null ? env.living : '—')
          + (env.deaths ? ' · 本帧离场 ' + env.deaths : '')
          + (env.predated ? ' · 突发 ' + env.predated : '')
          + (env.step != null ? ' · tick ' + env.step : '')
          + '</div>'
          + '<div style="font-size:9px;color:#64748b;margin-top:2px">统一业务考卷过滤 skill/协作是否适合（非觅食图腾）</div>';
      } else {
        habitatHud.innerHTML = '<b style="color:#22d3ee;font-size:11px">🌍 生境读数</b>'
          + '<div style="margin-top:4px">当前过滤：<b style="color:#f59e0b">' + esc(demandLab) + '</b></div>'
          + (env.niche_title ? '<div style="color:#94a3b8;font-size:10px">步骤：' + esc(env.niche_title) + '</div>' : '')
          + '<div style="color:#94a3b8;font-size:10px">存活 ' + (env.living != null ? env.living : '—')
          + (env.deaths ? ' · 本帧死亡 ' + env.deaths : '')
          + (env.predated ? ' · 捕食 ' + env.predated : '')
          + (env.step != null ? ' · tick ' + env.step : '')
          + '</div>'
          + '<div style="font-size:9px;color:#64748b;margin-top:2px">随机生境 · 挂任务后显示考卷 HUD</div>';
      }
    } else if (!env) {
      // 保持上次显示，除非显式清空 ecoEnv
    }
  }
  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  renderPanel(store.getState());

  // ── 接管 _dt3dBuildRoom：枯山水(rest-area) 委托旧实现，其余房间进办公室 ──
  const legacyBuildRoom = window._dt3dBuildRoom;
  window._dt3dBuildRoom = function (roomId) {
    if (roomId === 'rest-area' && typeof legacyBuildRoom === 'function') {
      canvas.style.display = 'none'; panel.style.display = 'none'; badge.style.display = 'none';
      const h = habitatSlot(); if (h) { h.style.display = 'none'; h.innerHTML = ''; }
      legacyCanvas.style.display = 'block';
      return legacyBuildRoom(roomId);            // 枯山水原样
    }
    legacyCanvas.style.display = 'none';
    canvas.style.display = 'block'; panel.style.display = 'block';
    const info = document.getElementById('env-3d-info');
    if (info) info.textContent = '▣ 数字办公室 — 全部任务在此进行孪生';
    syncPositions();
  };

  // ── 输入 1: 位置/团队 轮询（window.S 由 secs-core 维护，只读） ──
  // 尊重左栏团队选择: 只显示选中团队的成员；成员级筛选经 OfficeAPI.setRoster 覆盖。
  let memberFilter = null;   // Set<agentId> | null（null = 不做成员级过滤）
  let lastRosterKey = '';
  let lastSkillKey = '';     // 技能名解析完成后触发一次 roster 重建

  // 技能 ID → 可读名称 缓存: teamId -> {skillId: name}
  // agent.skills 里混有 snake_case ID（如 task_decomposition）和 hex ID（如 9897f3f7），
  // hex ID 需查团队技能目录才能得到中文名（如 "数据修复与功能修复解耦"）。
  const _skillNames = {};
  async function _loadSkillNames(teamId) {
    if (_skillNames[teamId]) return;
    _skillNames[teamId] = {};   // 先占位防止重复请求
    try {
      const r = await fetch('/api/v1/agent-config/teams/' + encodeURIComponent(teamId));
      const d = await r.json();
      const m = {};
      if (d && d.skills && typeof d.skills === 'object') {
        Object.entries(d.skills).forEach(([sid, sd]) => {
          m[sid] = (sd && (sd.name || sd.slug)) || sid;
        });
      }
      _skillNames[teamId] = m;
      lastSkillKey = '';   // 触发下次 syncPositions 重建 roster
    } catch (e) { /* 非致命，用原始 ID */ }
  }
  function _resolveSkill(teamId, skillId) {
    const m = _skillNames[teamId];
    if (m && m[skillId]) return m[skillId];
    // snake_case → 可读
    return String(skillId).replace(/_/g, ' ');
  }

  function syncPositions() {
    try {
      // 物竞天择 v2: 生境回放期间种群由 eco-console/eco-replay 全权驱动（含回放中出生的后代），
      // 暂停团队轮询，避免 team_reset 把后代/死亡状态冲掉。
      if (window.__ECO_REPLAY_ACTIVE__) return;
      const S = window.S || {};
      const positions = S.positions || {};
      const selected = Array.isArray(S.selectedTeams) ? S.selectedTeams.filter(Boolean) : [];
      const teams = (S.teams || []).filter(
        (t) => !selected.length || selected.includes(t.team_id || t.id)
      );
      // 异步加载团队技能目录（首次）
      teams.forEach((t) => {
        const tid = t.team_id || t.id || '';
        if (tid && !_skillNames[tid]) _loadSkillNames(tid);
      });
      let roster = [];
      teams.forEach((t) => (t.agents || []).forEach((a) => {
        const tid = t.team_id || t.id || '';
        // 技能来源: agent.skills（含 hex ID → 查目录解析）+ personality.expertise_areas
        const rawSkills = a.skills || [];
        const expertise = (a.personality && a.personality.expertise_areas) || [];
        const skills = Array.from(new Set([
          ...rawSkills.map(s => _resolveSkill(tid, s)),
          ...expertise.map(e => _resolveSkill(tid, e)),
        ]));
        const entry = { id: a.agent_id || a.id, name: a.name, role: a.role, team: tid, skills };
        // 宠物团队特殊标记
        if (tid === 'pet_squad') {
          entry._isCat = a.agent_id === 'xiaohu_cat' || a.id === 'xiaohu_cat';
          entry._isMouse = a.agent_id === 'squeak_mouse' || a.id === 'squeak_mouse';
        }
        roster.push(entry);
      }));
      if (memberFilter) roster = roster.filter((a) => memberFilter.has(a.id));
      // 演练时只显示所选团队的正式成员——不并入「增援」等临时注入的 agent。
      if (roster.length) {
        const key = roster.map((a) => a.id).sort().join(',');   // 顺序无关: 成员集不变不触发重置
        // 技能名解析完成后也需重建（hex ID → 中文名）
        const skillKey = roster.map(a => a.id + ':' + a.skills.join(',')).join('|');
        if (key !== lastRosterKey || skillKey !== lastSkillKey) {          // 花名册变化才整体重置（含移除未选团队成员）
          lastRosterKey = key;
          lastSkillKey = skillKey;
          store.dispatch({ type: 'team_reset', agents: roster });
        }
        const ids = new Set(roster.map((a) => a.id));
        for (const [agentId, room] of Object.entries(positions)) {
          if (ids.has(agentId)) store.dispatch({ type: 'position', agentId, room });
        }
      }
      syncScenarioStages();       // M2-5: 选中场景 → 阶段分区带
    } catch (e) { /* 只读同步失败不致命 */ }
  }
  // M2-5: 从当前选中场景 spec 的 world.rooms[].stage 派发业务阶段映射（幂等，变化才派发）
  let lastStageKey = '';
  function syncScenarioStages() {
    const rooms = (window._sx && _sx.scenarioSpec && _sx.scenarioSpec.world && _sx.scenarioSpec.world.rooms) || [];
    const stages = {};
    rooms.forEach((r) => { if (r && r.room_id != null) stages[r.name || r.room_id] = Number(r.stage || 0); });
    const key = Object.entries(stages).map(([k, v]) => k + ':' + v).sort().join(',');
    if (key === lastStageKey) return;
    lastStageKey = key;
    store.dispatch({ type: 'stages_sync', stages });
  }
  setInterval(syncPositions, 2000);

  // ── 猫气泡 = 演练解说员（优先级: 种子技能注入 > 运行中的仿真参数 > 当前演练任务） ──
  const MODE_LABEL = { what_if: 'What-if', multi_branch: '并行', parallel: '并行', evolutionary: '演化' };
  let seedNote = null;          // {text, until} 种子技能注入的置顶提示（45s）
  function catContextNote() {
    if (seedNote && Date.now() < seedNote.until) return seedNote.text;
    const sx = window._sx || {};
    if (sx.simRunning) {
      const modeEl = document.querySelector('input[name="secs-mode"]:checked');
      const mode = MODE_LABEL[(modeEl && modeEl.value) || (window._DTS && window._DTS.selectedMode)] || 'What-if';
      const steps = (document.getElementById('secs-steps') || {}).value || sx.maxSteps || 150;
      const speed = (document.getElementById('secs-speed-slider') || {}).value || 10;
      return `🐈 仿真参数\n模式 ${mode} · 步数 ${steps} · 加速 ${speed}x`;
    }
    // 任务来源链: SECS 任务选择(_selectedTaskGoal) > 场景名 > 任务下拉 > 导演台输入框 > 场景id
    const selOpt = (el) => (el && el.selectedIndex > 0
      ? el.options[el.selectedIndex].textContent.trim() : '');
    const task = (window._selectedTaskGoal && window._selectedTaskGoal.name)
      || (sx.scenarioSpec && sx.scenarioSpec.name)
      || selOpt(document.getElementById('secs-task-select'))
      || ((document.getElementById('dp-task-name') || {}).value || '').trim()
      || (sx.scenarioId ? String(sx.scenarioId) : '');
    return task ? `🐈 演练任务\n${task}` : '';
  }
  setInterval(() => {
    store.dispatch({ type: 'cat_say', text: catContextNote() });
  }, 2000);
  // 种子技能注入 → 气泡置顶显示注入的技能名（沙箱进料 · 💉 注入按钮）
  document.addEventListener('click', (e) => {
    const btn = e.target && e.target.closest && e.target.closest('#btn-inject-skill');
    if (!btn) return;
    const sel = document.getElementById('skill-inject-select');
    const name = sel && sel.selectedIndex > 0
      ? sel.options[sel.selectedIndex].textContent.trim() : '';
    if (name) {
      seedNote = { text: `🐈 种子技能已注入\n💉 ${name}`, until: Date.now() + 45e3 };
      store.dispatch({ type: 'cat_say', text: seedNote.text });
    }
  }, true);

  // 混沌加入/离开即时反映到办公室（不等 2s 轮询）
  for (const fn of ['_dt2dChaosJoin', '_dt2dChaosLeave', '_dt2dChaosReset']) {
    const orig = window[fn];
    if (typeof orig === 'function') {
      window[fn] = function (...args) {
        const r = orig.apply(this, args);
        try { syncPositions(); } catch (e) { /* 非致命 */ }
        return r;
      };
    }
  }
  setInterval(() => store.dispatch({ type: 'tick', dt: 1 }), 1000);

  // ── 作息调度（错峰 + 排队） ──
  // 频率: 咖啡≈30min / 马桶≈1h / 跑步机≈30min。停留与排队由 store 的设施占位模型管理
  //（咖啡 1min、跑步机 5min、马桶 5min，容量 1，FIFO）。
  // 错峰算法: 团队内相位均匀分布——同队第 i 个成员(共 N 人)的首次到点
  //   due = now + mean × (i+0.5)/N × jitter(0.9~1.1)
  // 之后 due += mean × (0.8~1.2)。再加团队并发闸: 同队已有人在该设施(占用或排队)则顺延，
  // 保证「一个团队不会集体去咖啡机」。
  // ?breakspeed=60 → 时间加速 60 倍（演示/调试排队行为）: 频率与停留时长同比缩短
  const SPEED = Math.max(1, Number(new URLSearchParams(location.search).get('breakspeed')) || 1);
  setBreakTimeScale(SPEED);
  const BREAK_MEAN = {
    coffee: 1800e3 / SPEED, toilet: 3600e3 / SPEED, treadmill: 1800e3 / SPEED,
  };
  const nextBreakAt = {};   // agentId -> {facility: dueTs}
  let staggerKey = '';
  function initStagger(state) {
    const byTeam = {};
    for (const a of Object.values(state.agents)) {
      (byTeam[a.team || '_'] = byTeam[a.team || '_'] || []).push(a.id);
    }
    const now = Date.now();
    for (const members of Object.values(byTeam)) {
      members.sort();
      members.forEach((id, i) => {
        nextBreakAt[id] = {};
        for (const [fac, mean] of Object.entries(BREAK_MEAN)) {
          nextBreakAt[id][fac] = now + mean * ((i + 0.5) / members.length) * (0.9 + Math.random() * 0.2);
        }
      });
    }
  }
  function teammateBusyAt(state, agent, facility) {
    const f = state.facilities[facility];
    if (!f) return false;
    const ids = [f.occupant, ...f.queue].filter(Boolean);
    return ids.some((id) => id !== agent.id && (state.agents[id] || {}).team === agent.team);
  }
  setInterval(() => store.dispatch({ type: 'break_tick', now: Date.now() }),
    Math.max(1000, 5e3 / SPEED));
  setInterval(() => {
    // 物竞天择 v2.3: 生境演练/回放期间冻结作息调度，并重置错峰计时——
    // 否则演练结束的一瞬间，攒了一整场的咖啡/马桶/跑步机"欠账"会同时放行，
    // 全员涌向设施，看起来像"Agent 纷纷退场"（用户 2026-07-11 反馈）。
    if (window.__ECO_REPLAY_ACTIVE__) { staggerKey = ''; return; }
    const state = store.getState();
    const rosterKey = Object.keys(state.agents).sort().join(',');
    if (rosterKey !== staggerKey) { staggerKey = rosterKey; initStagger(state); }
    if (state.mirror || state.meeting.active) return;   // 孪生演练/开会时不摸鱼
    const now = Date.now();
    for (const agent of Object.values(state.agents)) {
      // v2.4: eco 种群（演练生物）— 不参与作息调度（演练后留在工位观察数据）
      if (agent.noBreaks) continue;
      if (!nextBreakAt[agent.id] || agent.activity !== 'working') continue;
      for (const fac of Object.keys(BREAK_MEAN)) {
        if (now < nextBreakAt[agent.id][fac]) continue;
        if (teammateBusyAt(state, agent, fac)) {
          // 团队并发闸: 同队有人在此设施 → 顺延一个错峰间隔
          nextBreakAt[agent.id][fac] = now + BREAK_MEAN[fac] * 0.15 * (0.8 + Math.random() * 0.4);
          continue;
        }
        nextBreakAt[agent.id][fac] = now + BREAK_MEAN[fac] * (0.8 + Math.random() * 0.4);
        store.dispatch({ type: 'break_request', agentId: agent.id, facility: fac, now });
        break;   // 一次只去一个地方
      }
    }
  }, Math.max(1000, 20e3 / SPEED));

  // ── 输入 2: 孪生事件钩子（step / 讨论 / 状态机），不改旧函数行为 ──
  // 孪生副本 → 真身对齐: SSE 的 agent_actions 以 twin_id 为键，
  // 用事件携带的 twin_agents 映射回真身 agent_id，办公室里的人才对得上号。
  // 两条演练通道共用: 试炼导演台(handleTrialEvent) + SECS 面板 SSE(secs-core 调 ingestStep)。
  function ingestStep(ev) {
    try {
      const raw = ev.agent_actions || (ev.data && ev.data.agent_actions) || {};
      const twinMap = ev.twin_agents || (ev.data && ev.data.twin_agents) || {};
      // 只驱动当前花名册内的 agent：仿真自带的外部/临时 agent（不在所选团队）忽略，
      // 否则 step reducer 会为其新建 figure → 自动运行时「弹出一堆 agent」。
      const known = store.getState().agents;
      const mapped = {};
      for (const [k, v] of Object.entries(raw)) {
        const realId = twinMap[k] || k;
        if (!known[realId]) continue;
        const act = typeof v === 'string' ? { action: v } : { ...(v || {}) };
        if (act.target) act.target = twinMap[act.target] || act.target;
        if (act.to) act.to = twinMap[act.to] || act.to;
        mapped[realId] = act;
      }
      store.dispatch({ type: 'step', agentActions: mapped });
      // 评分波动追踪 → 猫评价
      if (typeof ev.global_reward === 'number') trackReward(ev.global_reward);
    } catch (e) { /* 观测层不阻塞业务 */ }
  }
  const legacyHandle = window.handleTrialEvent;
  window.handleTrialEvent = function (ev) {
    if (ev && ev.type === 'step') ingestStep(ev);
    if (typeof legacyHandle === 'function') return legacyHandle(ev);
  };
  const legacyTransition = window.transitionTrialStatus;
  if (typeof legacyTransition === 'function') {
    window.transitionTrialStatus = function (from, to) {
      const ok = legacyTransition(from, to);
      if (ok) store.dispatch({ type: 'trial_status', status: to });
      return ok;
    };
  }

  // ── 对外 API（后续 P7-3 Plaza 白板接线 / 面板联动使用） ──
  // 宠物语音：从 pet_config 加载，支持 browser / edge-tts / gpt-sovits 三种引擎
  let _catTtsTimer = null;
  let _petVoiceConfig = null;   // 缓存当前会说话宠物的 voice 配置
  let _catAudioEl = null;       // 后端 TTS 播放器（须先于 stopCatAudio 声明）
  // 猫静音（3D 窗口按键）：localStorage 持久化，默认开声
  const _CAT_MUTE_LS = 'ag-office-cat-muted';
  let _catMuted = false;
  try { _catMuted = localStorage.getItem(_CAT_MUTE_LS) === '1'; } catch (e) { _catMuted = false; }
  let _catMuteBtn = null;

  function stopCatAudio() {
    try {
      if (window.speechSynthesis) speechSynthesis.cancel();
    } catch (e) { /* ignore */ }
    if (_catTtsTimer) { clearTimeout(_catTtsTimer); _catTtsTimer = null; }
    if (_catAudioEl) {
      try { _catAudioEl.pause(); _catAudioEl.src = ''; } catch (e2) { /* ignore */ }
      _catAudioEl = null;
    }
  }

  function setCatMuted(muted, { persist = true } = {}) {
    _catMuted = !!muted;
    if (persist) {
      try { localStorage.setItem(_CAT_MUTE_LS, _catMuted ? '1' : '0'); } catch (e) { /* ignore */ }
    }
    if (_catMuted) stopCatAudio();
    if (_catMuteBtn) {
      _catMuteBtn.textContent = _catMuted ? '🐱 🔇' : '🐱 🔊';
      _catMuteBtn.title = _catMuted
        ? '猫语音已静音 — 点击恢复播报'
        : '猫语音开启 — 点击静音小虎解说/对话';
      _catMuteBtn.setAttribute('aria-pressed', _catMuted ? 'true' : 'false');
      _catMuteBtn.style.opacity = _catMuted ? '0.72' : '1';
      _catMuteBtn.style.borderColor = _catMuted ? 'rgba(245,158,11,.55)' : 'rgba(232,160,32,.55)';
    }
    return _catMuted;
  }

  function toggleCatMute() {
    return setCatMuted(!_catMuted);
  }

  function mountCatMuteButton() {
    if (_catMuteBtn && _catMuteBtn.isConnected) return _catMuteBtn;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.id = 'office-cat-mute-btn';
    btn.setAttribute('aria-label', '猫语音静音');
    // 贴在 3D 窗口右下角、旧版切换按钮上方，不挡任务 HUD
    btn.style.cssText = [
      'position:absolute', 'bottom:48px', 'right:12px', 'z-index:22',
      'padding:6px 10px', 'border-radius:8px',
      'border:1px solid rgba(232,160,32,.55)',
      'background:rgba(15,14,13,0.82)', 'color:#f8fafc',
      'font:600 12px/1.2 sans-serif', 'cursor:pointer',
      'backdrop-filter:blur(8px)', 'box-shadow:0 2px 12px rgba(0,0,0,.28)',
      'pointer-events:auto', 'user-select:none',
    ].join(';');
    btn.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      toggleCatMute();
    };
    if (getComputedStyle(container).position === 'static') container.style.position = 'relative';
    container.appendChild(btn);
    _catMuteBtn = btn;
    setCatMuted(_catMuted, { persist: false }); // 同步 UI，不重写 LS
    return btn;
  }

  // ── 宠物隐藏按钮（吱吱/小虎）：与猫静音按钮同款风格，localStorage 持久化 ──
  const _PETS_HIDDEN_LS = 'ag-office-pets-hidden';
  let _petsHidden = false;
  try { _petsHidden = localStorage.getItem(_PETS_HIDDEN_LS) === '1'; } catch (e) { _petsHidden = false; }
  let _petsHideBtn = null;

  function setPetsVisible(visible, { persist = true } = {}) {
    _petsHidden = !visible;
    if (persist) {
      try { localStorage.setItem(_PETS_HIDDEN_LS, _petsHidden ? '1' : '0'); } catch (e) { /* ignore */ }
    }
    if (_petsHidden) stopCatAudio();
    sceneApi.setPetsVisible(visible);
    if (_petsHideBtn) {
      _petsHideBtn.textContent = _petsHidden ? '🐱 🐭 已隐藏' : '🐱 🐭';
      _petsHideBtn.title = _petsHidden
        ? '吱吱与小虎已隐藏 — 点击恢复显示'
        : '隐藏吱吱与小虎';
      _petsHideBtn.setAttribute('aria-pressed', _petsHidden ? 'true' : 'false');
      _petsHideBtn.style.opacity = _petsHidden ? '0.72' : '1';
      _petsHideBtn.style.borderColor = _petsHidden ? 'rgba(245,158,11,.55)' : 'rgba(232,160,32,.55)';
    }
    return visible;
  }

  function togglePetsVisibility() {
    return setPetsVisible(_petsHidden); // 传"当前是否隐藏"，取反即得到新状态
  }

  function mountPetsVisibilityButton() {
    if (_petsHideBtn && _petsHideBtn.isConnected) return _petsHideBtn;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.id = 'office-pets-toggle-btn';
    btn.setAttribute('aria-label', '隐藏吱吱与小虎');
    // 贴在猫静音按钮上方，不挡任务 HUD 与旧版切换按钮
    btn.style.cssText = [
      'position:absolute', 'bottom:88px', 'right:12px', 'z-index:22',
      'padding:6px 10px', 'border-radius:8px',
      'border:1px solid rgba(232,160,32,.55)',
      'background:rgba(15,14,13,0.82)', 'color:#f8fafc',
      'font:600 12px/1.2 sans-serif', 'cursor:pointer',
      'backdrop-filter:blur(8px)', 'box-shadow:0 2px 12px rgba(0,0,0,.28)',
      'pointer-events:auto', 'user-select:none',
    ].join(';');
    btn.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      togglePetsVisibility();
    };
    if (getComputedStyle(container).position === 'static') container.style.position = 'relative';
    container.appendChild(btn);
    _petsHideBtn = btn;
    setPetsVisible(!_petsHidden, { persist: false }); // 同步 UI 与场景，不重写 LS
    return btn;
  }

  // 预加载 voices（Chrome 异步加载，首次 getVoices() 返回空）
  if (window.speechSynthesis) {
    speechSynthesis.getVoices();
    speechSynthesis.onvoiceschanged = () => { speechSynthesis.getVoices(); };
  }
  // 加载会说话宠物的语音配置（取第一个 speak.provider=llm 的宠物）
  (async function loadPetVoice() {
    try {
      const doFetch = (typeof window._af === 'function') ? window._af : (window._agFetch || fetch);
      const r = await doFetch('/api/v1/pet-ecosystem/config');
      if (!r.ok) return;
      const data = await r.json();
      const speaker = (data.pets || []).find(p => p.speak && p.speak.provider === 'llm');
      if (speaker && speaker.voice) _petVoiceConfig = speaker.voice;
    } catch (e) { console.warn('[catSpeak] voice config load failed', e); }
  })();

  function catSpeak(text, voiceCfg) {
    if (_catMuted || _petsHidden) {
      console.log('[catSpeak] muted or pets hidden, skip');
      return;
    }
    const vc = voiceCfg || _petVoiceConfig;
    const v = validateVoiceConfig(vc);
    if (!v.ok) { console.error('[catSpeak]', v.error); return; }
    const provider = vc.provider;
    console.log('[catSpeak] called:', text ? text.slice(0, 30) : '(empty)', 'provider:', provider);
    const raw = String(text || '');
    const cleanText = (vc.strip_punctuation !== false)
      ? raw.replace(/[.,!?;:'"()\[\]{}。，！？；：""''（）【】《》—…\-]/g, ' ').replace(/\s+/g, ' ').trim()
      : raw.trim();
    if (!cleanText) return;

    if (provider === 'edge-tts' || provider === 'gpt-sovits') {
      _catSpeakBackend(cleanText, vc, provider);
      return;
    }
    // 浏览器内置语音 — validateVoiceConfig 已保证字段齐全
    if (!window.speechSynthesis) { console.warn('[catSpeak] speechSynthesis unavailable'); return; }
    speechSynthesis.cancel();
    // Chrome bug: cancel() 是异步的，立即 speak() 会导致旧语音不被取消而重复播放
    const utt = new SpeechSynthesisUtterance(cleanText);
    utt.lang = vc.lang;
    utt.rate = vc.rate;
    utt.pitch = vc.pitch;
    utt.volume = vc.volume;
    const voices = speechSynthesis.getVoices();
    const fv = voices.find(v => v.name === vc.preferred_voice);
    if (!fv) {
      console.error(`[catSpeak] preferred_voice "${vc.preferred_voice}" not found in browser voices — 请在 /pet-config.html 页面重新选择`);
      return;
    }
    utt.voice = fv;
    utt.onstart = () => { console.log('[catSpeak] started'); };
    utt.onend = () => { console.log('[catSpeak] ended'); if (_catTtsTimer) { clearTimeout(_catTtsTimer); _catTtsTimer = null; } };
    utt.onerror = (e) => { console.warn('[catSpeak] error:', e.error || e); if (_catTtsTimer) { clearTimeout(_catTtsTimer); _catTtsTimer = null; } };
    if (_catTtsTimer) clearTimeout(_catTtsTimer);
    _catTtsTimer = setTimeout(() => { console.warn('[catSpeak] timeout, force resume'); _catTtsTimer = null; }, vc.timeout_sec * 1000);
    // 延迟 150ms 再 speak，确保 cancel() 完成后再播新语音
    setTimeout(() => { speechSynthesis.resume(); speechSynthesis.speak(utt); }, 150);
  }

  // 后端 TTS（edge-tts / gpt-sovits）→ 取音频播放
  async function _catSpeakBackend(text, vc, provider) {
    if (_catMuted) return;
    try {
      if (provider === 'edge-tts' && !vc.edge_voice) {
        console.error('[catSpeak] voice.edge_voice missing for edge-tts — 请在 /pet-config.html 页面选择 Edge 神经语音');
        return;
      }
      const doFetch = (typeof window._af === 'function') ? window._af : (window._agFetch || fetch);
      const body = { text, agent_name: '小虎' };
      if (provider === 'edge-tts') {
        body.voice = vc.edge_voice;
        if (vc.edge_rate) body.rate = vc.edge_rate;
        if (vc.edge_pitch) body.pitch = vc.edge_pitch;
      }
      if (provider === 'gpt-sovits' && vc.speed_factor !== undefined) body.speed_factor = vc.speed_factor;
      const r = await doFetch('/api/v1/tts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.detail || 'HTTP ' + r.status); }
      if (_catMuted) return; // 请求返回期间可能已静音
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      if (_catAudioEl) { _catAudioEl.pause(); }
      _catAudioEl = new Audio(url);
      _catAudioEl.onended = () => URL.revokeObjectURL(url);
      _catAudioEl.onerror = (e) => { console.warn('[catSpeak] audio error', e); URL.revokeObjectURL(url); };
      if (_catMuted) {
        URL.revokeObjectURL(url);
        _catAudioEl = null;
        return;
      }
      await _catAudioEl.play();
      console.log('[catSpeak] backend played, engine:', r.headers.get('X-TTS-Engine'));
    } catch (e) {
      if (_catMuted) return;
      console.warn('[catSpeak] backend TTS failed, fallback to browser:', e.message);
      // 回退到浏览器语音
      catSpeak(text, { ...vc, provider: 'browser' });
    }
  }

  // 猫对话框 — 窄条输入框，回答只在气泡显示
  let catDialogEl = null;
  function showCatDialog() {
    if (catDialogEl) { catDialogEl.remove(); catDialogEl = null; return; }
    catDialogEl = document.createElement('div');
    catDialogEl.style.cssText = 'position:absolute;bottom:20px;left:50%;transform:translateX(-50%);display:flex;align-items:center;gap:6px;background:rgba(255,255,255,0.95);border:1.5px solid #e8a020;border-radius:22px;padding:4px 4px 4px 12px;z-index:10;box-shadow:0 4px 20px rgba(0,0,0,0.12);font-family:sans-serif';
    catDialogEl.innerHTML = `<span style="font-size:14px">🐱</span><input id="cat-dialog-input" type="text" placeholder="问小虎…" style="width:180px;border:none;outline:none;font-size:12px;color:#3b4048;background:transparent"><button id="cat-dialog-send" style="padding:5px 14px;background:#e8a020;color:white;border:none;border-radius:18px;font-size:11px;cursor:pointer;font-weight:600">问</button>`;
    container.appendChild(catDialogEl);
    const input = catDialogEl.querySelector('#cat-dialog-input');
    const sendBtn = catDialogEl.querySelector('#cat-dialog-send');
    async function askCat() {
      const q = input.value.trim();
      if (!q) return;
      input.value = '';
      // 走 cat speak: 调后端 /llm/cat-speak，用 LLM 以 Metal Gear 中 Mei Ling 的台词回答
      sceneApi.showCatBubble('🐱 喵…（思索中）');
      let reply = '喵~ 硕鼠硕鼠，无食我黍！';
      try {
        const doFetch = (typeof window._af === 'function') ? window._af : (window._agFetch || fetch);
        const r = await doFetch('/api/v1/agent-config/llm/cat-speak', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ context: q }),
        });
        const d = await r.json();
        if (d && d.reply) reply = d.reply;
      } catch (e) {
        console.warn('[cat-dialog] cat-speak failed:', e);
      }
      // bug-050: 降级文案净化（与 PetEcosystem.sanitizeCatReply 同规则）
      try {
        const { PetEcosystem } = await import('./pet-ecosystem.js');
        reply = PetEcosystem.sanitizeCatReply(reply, '');
      } catch (e) { /* 净化失败时保持原文 */ }
      sceneApi.showCatBubble('🐱 ' + reply);
      catSpeak(reply);
    }
    sendBtn.onclick = askCat;
    input.onkeydown = (e) => { if (e.key === 'Enter') askCat(); };
    // 点击对话框外部 → 收起
    setTimeout(() => input.focus(), 50);
    const _outsideHandler = (e) => {
      if (catDialogEl && !catDialogEl.contains(e.target)) {
        catDialogEl.remove(); catDialogEl = null;
        document.removeEventListener('pointerdown', _outsideHandler, true);
      }
    };
    // 延迟绑定，避免当前点击事件立即触发
    setTimeout(() => document.addEventListener('pointerdown', _outsideHandler, true), 100);
  }

  // 评分波动追踪
  let _lastReward = null;
  function trackReward(reward) {
    if (typeof reward !== 'number') return;
    if (_lastReward !== null) {
      sceneApi.onRewardUpdate(reward, _lastReward);
    }
    _lastReward = reward;
  }

  window.OfficeAPI = {
    dispatch: store.dispatch,
    getState: store.getState,
    ingestStep,
    collabStats: (n) => collabStats(store.getState(), n),
    setRoster(agentIds) {
      memberFilter = agentIds && agentIds.length ? new Set(agentIds) : null;
      lastRosterKey = '';
      syncPositions();
    },
    syncWorkflow(edges) { store.dispatch({ type: 'workflow_sync', edges: edges || [] }); },
    syncStages(map) { store.dispatch({ type: 'stages_sync', stages: map || {} }); },
    meeting(active, speakerId, boardLine, participantIds) {
      window.OfficeAPI._speakerId = speakerId || null;
      store.dispatch({ type: 'discussion', active, speakerId, boardLine, participantIds });
    },
    onCatClick: showCatDialog,
    onCatComment: (comment, voiceCfg) => { catSpeak(comment, voiceCfg); },
    isCatMuted: () => _catMuted,
    setCatMuted,
    toggleCatMute,
    setPetsVisible,
    isPetsHidden: () => _petsHidden,
    stopCatAudio,
    trackReward,
    _speakerId: null,
  };

  mountCatMuteButton();
  mountPetsVisibilityButton();

  // 初次进入即渲染办公室
  window._dt3dBuildRoom(window._currentRoomId && window._currentRoomId !== 'rest-area'
    ? window._currentRoomId : 'workshop');
}

function addToggleButton() {
  // 页面内切换入口: 不用手改 URL 就能进办公室视图
  const host = document.getElementById('env-3d-container');
  if (!host) return;
  const btn = document.createElement('button');
  btn.textContent = FLAG_ON ? '↩ 旧版房间视图' : '▣ 办公室视图';
  btn.title = '切换数字办公室 3D（Marvis 风格）';
  btn.style.cssText = 'position:absolute;bottom:10px;right:12px;z-index:20;padding:5px 12px;'
    + 'border:1px solid #cfd4da;border-radius:6px;background:rgba(255,255,255,.95);'
    + 'color:#3b4048;font:600 11px sans-serif;cursor:pointer';
  btn.onclick = () => {
    const url = new URL(location.href);
    if (FLAG_ON) url.searchParams.delete('office3d');
    else url.searchParams.set('office3d', '1');
    location.href = url.toString();
  };
  if (getComputedStyle(host).position === 'static') host.style.position = 'relative';
  host.appendChild(btn);
}

function start() {
  addToggleButton();
  // 物竞天择 v2 XT-3.1: 办公室视图 = 自然选择试验田。
  // 该旗标使右侧演练菜单整体切换为生境控制台（rp-eco），优先级高于 team.runtime。
  window.__ECO_FIELD__ = FLAG_ON;
  if (FLAG_ON) {
    document.body.classList.add('office-mode');
    try {
      bootOffice();
    } catch (e) {
      console.error('[office-boot] bootOffice failed:', e);
      // 显示错误提示，方便排查
      const div = document.createElement('div');
      div.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:#fff;color:#c00;padding:20px;border-radius:8px;border:2px solid #c00;z-index:9999;font-family:monospace;font-size:13px;max-width:80vw';
      div.textContent = '数字办公室加载失败: ' + (e && e.message || e);
      document.body.appendChild(div);
    }
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', start);
} else {
  start();
}
