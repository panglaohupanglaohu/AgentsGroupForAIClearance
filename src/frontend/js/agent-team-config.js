const A='/api/v1/agent-config',AT='/api/v1/agent-teams';
let tid='',aid='',atab='ag-status',wzD={},wzS=1;
let _offline=false;
let _teamsListCache=null;
let _teamsListCacheAt=0;
const TEAMS_LIST_CACHE_MS=60000;

function toast(m,type){
  const e=document.getElementById('toast');
  e.className='toast'+(type?' toast-'+type:'');
  e.textContent=m;e.classList.add('show');
  const dur=type==='error'?5000:2500;
  setTimeout(()=>e.classList.remove('show'),dur);
}
function openModal(id){
  const m=document.getElementById(id);m.classList.add('open');
  m.setAttribute('role','dialog');m.setAttribute('aria-modal','true');
  // Focus trap
  const focusable=m.querySelectorAll('button,input,select,textarea,[tabindex]:not([tabindex="-1"])');
  if(focusable.length)focusable[0].focus();
  m._focusTrap=e=>{
    if(e.key==='Escape'){closeModal(id);return}
    if(e.key!=='Tab')return;
    const first=focusable[0],last=focusable[focusable.length-1];
    if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}
    else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}
  };
  m.addEventListener('keydown',m._focusTrap);
}
function closeModal(id){
  const m=document.getElementById(id);m.classList.remove('open');
  m.removeAttribute('aria-modal');
  if(m._focusTrap){m.removeEventListener('keydown',m._focusTrap);delete m._focusTrap}
}

// Connection status banner
function showOfflineBanner(){
  if(document.getElementById('offline-banner'))return;
  const b=document.createElement('div');
  b.id='offline-banner';
  b.style.cssText='position:fixed;top:0;left:0;right:0;z-index:1000;background:var(--shu);color:var(--shironeri);padding:8px 16px;font-size:13px;text-align:center;display:flex;justify-content:center;align-items:center;gap:12px';
  b.innerHTML='⚠ 后端连接失败 <button style="background:var(--shironeri);color:var(--shu);border:none;padding:4px 12px;cursor:pointer;font-size:12px;font-weight:600" onclick="retryConnection()">重试</button>';
  document.body.prepend(b);
}
function hideOfflineBanner(){
  const b=document.getElementById('offline-banner');if(b)b.remove();
  _offline=false;
}
async function retryConnection(){
  const r=await fetch(`${A}/teams`).catch(()=>null);
  if(r&&r.ok){hideOfflineBanner();loadTeams();toast('连接已恢复','success')}
  else toast('仍然无法连接','error')
}

// IMPORTANT: use `const api = async function` — NOT `async function api`.
// Top-level function declarations become window.api and clobber api.js shared client
// (window.api.request / CSRF). That forced the bare-fetch fallback and noisy 500 logs.
const api = async function(p,o){
  // Prefer shared client from api.js (CSRF + 403 retry + unified errors)
  const client = (typeof window!=='undefined' && window.api && typeof window.api.request==='function')
    ? window.api : null;
  if(client){
    try{
      const data = await client.request(p, o || {});
      if(_offline){hideOfflineBanner()}
      if(data === null && client._lastError){
        api._lastError = Object.assign({}, client._lastError);
        return null;
      }
      api._lastError = null;
      return data;
    }catch(e){
      console.error(`API error: ${p}`, e);
      if(e.name==='TypeError'||(e.message&&e.message.includes('fetch'))){
        _offline=true;
        showOfflineBanner();
      }
      api._lastError={status:0,message:e.message,url:p,network:true};
      return null;
    }
  }
  // 兜底：无 window.api 时用原生 fetch（仍可能经 window.fetch 包装）
  try{
    const r=await fetch(p,o);
    if(_offline){hideOfflineBanner()}
    if(!r.ok){
      let msg='';
      try{const d=await r.json();msg=d.detail||d.message||d.error||''}catch{}
      console.warn(`API ${r.status}: ${p}`,msg);
      api._lastError={status:r.status,message:msg,url:p};
      return null;
    }
    api._lastError=null;
    return await r.json();
  }catch(e){
    console.error(`API error: ${p}`,e);
    if(e.name==='TypeError'||e.message?.includes('fetch')){
      _offline=true;
      showOfflineBanner();
    }
    api._lastError={status:0,message:e.message,url:p,network:true};
    return null;
  }
};
api._lastError=null;

function _sleep(ms){return new Promise(r=>setTimeout(r,ms))}

async function getTeamsList(force=false){
  const now=Date.now();
  if(!force&&_teamsListCache&&(now-_teamsListCacheAt)<TEAMS_LIST_CACHE_MS){
    return _teamsListCache;
  }
  // Retry on transient 5xx / proxy blips (Vite→8080 during backend --reload)
  let raw=null;
  let lastErr=null;
  for(let attempt=0; attempt<3; attempt++){
    raw=await api(`${A}/teams`);
    if(raw!=null) break;
    lastErr=api._lastError;
    const st=lastErr&&lastErr.status;
    if(st && st>=500 && st<600 && attempt<2){
      await _sleep(250*(attempt+1));
      continue;
    }
    break;
  }
  // Accept plain array or pagination envelope {items,total,...}
  const teams=Array.isArray(raw)?raw:Array.isArray(raw?.items)?raw.items:[];
  if(teams.length){
    _teamsListCache=teams;
    _teamsListCacheAt=now;
    return teams;
  }
  // Keep last good cache if this request failed / empty (e.g. transient 500)
  if(_teamsListCache&&_teamsListCache.length) return _teamsListCache;
  if(lastErr&&lastErr.status){
    console.warn('getTeamsList failed', lastErr.status, lastErr.message||'');
  }
  return teams;
}

function stL(s){return{idle:'待命中',working:'工作中',reporting:'汇报中',blocked:'阻塞',error:'异常'}[s]||s||'未知'}
function el(id){return document.getElementById(id)}
function escapeHtml(v){return String(v??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;')}

// ── 作用域：平台级 vs 团队级 ──
// tid === ALL_TEAMS 表示「未选择具体团队」，此时只呈现平台视角。
const ALL_TEAMS='__all__';
function isPlatformScope(){return tid===ALL_TEAMS||!tid}
/** 团队级视图在平台作用域下不可用，统一降级回仪表盘。 */
const TEAM_SCOPED_VIEWS=['models','tools','skills','tasks','agent','wizard'];

function currentTeamName(){
  const t=(_teamsListCache||[]).find(x=>x&&x.team_id===tid);
  return t?.name||tid||'—';
}

function renderScopeChrome(view){
  const chip=el('scope-chip');
  const platform=isPlatformScope();
  if(chip){
    const teamScoped=!platform&&TEAM_SCOPED_VIEWS.includes(view);
    const overviewTeam=!platform&&view==='overview';
    if(teamScoped||overviewTeam){
      chip.dataset.scope='team';
      chip.textContent=`团队 · ${currentTeamName()}`;
    }else{
      chip.dataset.scope='platform';
      chip.textContent='平台 · 全部团队';
    }
  }
  const nameEl=el('sb-scope-team-name');
  if(nameEl)nameEl.textContent=platform?'未选择':currentTeamName();
  document.querySelectorAll('.sb-nav a[data-scope="team"]').forEach(a=>{
    a.classList.toggle('scope-muted',platform);
    a.title=platform?'需先选择一个团队':'';
  });
}

// ── Teams ──
async function loadTeams(){
  const d=await getTeamsList(true);const s=el('team-select');
  if(!d||!d.length){
    const err=api._lastError;
    const hint=err?(err.status?`HTTP ${err.status}`:'网络错误')+(err.message?`: ${err.message}`:''):'无数据';
    s.innerHTML=`<option>无团队（${escapeHtml(hint)}）</option>`;
    if(err&&err.status>=500){
      toast(`加载团队失败 ${hint} — 后端可能正在重启，点「重试」`,'error');
      showOfflineBanner();
    }
    return;
  }
  // 深链 team_id（物竞反馈台 → 关系 tab）
  try{
    const qp=new URLSearchParams(window.location.search);
    const qTeam=qp.get('team_id')||qp.get('team');
    if(qTeam&&d.some(t=>t.team_id===qTeam))tid=qTeam;
  }catch(e){/* ignore */}
  s.innerHTML=`<option value="${ALL_TEAMS}">▣ 全部团队 · 平台总览</option>`
    +d.map(t=>`<option value="${escapeHtml(t.team_id)}">${escapeHtml(t.name)}</option>`).join('');
  if(!tid)tid=ALL_TEAMS;
  s.value=tid;loadView();
}
el('team-select').onchange=e=>{
  tid=e.target.value;
  if(typeof toggleTopologyEditMode==='function') toggleTopologyEditMode(false);
  // 平台作用域下团队级视图无意义，回落到仪表盘
  const active=document.querySelector('.sb-nav a.active');
  if(isPlatformScope()&&active&&TEAM_SCOPED_VIEWS.includes(active.dataset.view)){
    switchView('overview');
    return;
  }
  loadView();
};

// ── View switch ──
function switchView(v,extra){
  // 平台作用域拦截：团队级视图必须先选团队
  if(isPlatformScope()&&TEAM_SCOPED_VIEWS.includes(v)){
    toast('请先在左上角选择一个团队','error');
    v='overview';
    extra=undefined;
  }
  document.querySelectorAll('.main-inner').forEach(e=>e.classList.add('hidden'));
  document.querySelectorAll('.sb-nav a').forEach(a=>a.classList.toggle('active',a.dataset.view===v));
  document.querySelectorAll('.sb-agent').forEach(a=>a.classList.remove('active'));
  const t=el('main-title'),b=el('main-badge');
  if(v==='overview'){
    el('view-overview').classList.remove('hidden');
    if(isPlatformScope()){t.textContent='平台总览';b.textContent='';}
    else{t.textContent='团队概览';b.textContent=tid;}
    loadOverview();
  }
  else if(v==='models'){el('view-models').classList.remove('hidden');t.textContent='模型池';b.textContent='';loadModels()}
  else if(v==='tools'){el('view-tools').classList.remove('hidden');t.textContent='工具管理';b.textContent='';loadTools()}
  else if(v==='skills'){el('view-skills').classList.remove('hidden');t.textContent='技能管理';b.textContent='';loadSkills()}
  else if(v==='tasks'){el('view-tasks').classList.remove('hidden');t.textContent='并发任务';b.textContent='';loadTasks()}
  else if(v==='llm'){el('view-llm').classList.remove('hidden');t.textContent='LLM 配置';b.textContent='';loadLLMStatus();loadTTSConfig()}
  else if(v==='sessions'){el('view-agent').classList.remove('hidden');el('agent-tabs').style.display='none';el('agent-content').style.display='none';el('view-sessions').classList.remove('hidden');t.textContent='会话存档';b.textContent='';loadPersistedSessions()}
  else if(v==='runtime'){el('view-agent').classList.remove('hidden');el('agent-tabs').style.display='none';el('agent-content').style.display='none';el('view-runtime').classList.remove('hidden');t.textContent='PortRuntime';b.textContent='claw-code-parity';el('rt-results').classList.add('hidden')}
  else if(v==='registry'){el('view-agent').classList.remove('hidden');el('agent-tabs').style.display='none';el('agent-content').style.display='none';el('view-registry').classList.remove('hidden');t.textContent='自主 Token 工厂';b.textContent='Token Factory';loadTokenFactory();_startTfPoll()}
  else if(v==='agent'){el('view-agent').classList.remove('hidden');el('agent-tabs').style.display='';el('agent-content').style.display='';loadAgent(extra)}
  else if(v==='wizard'){el('view-wizard').classList.remove('hidden');t.textContent='新建智能体';b.textContent=''}
  renderScopeChrome(v);
}
function loadView(){
  // ── Darwin rule: bridge-task-dispatch deep-link support ──
  // ── XF-7.11: 物竞反馈 → team_id + agent_id + atab=ag-relations ──
  const params = new URLSearchParams(window.location.search);
  const view = params.get('view');
  const qAgent = params.get('agent_id') || params.get('aid') || '';
  const qAtab = params.get('atab') || params.get('tab') || '';
  if(qAtab)atab=qAtab;
  if(qAgent)aid=qAgent;
  let nextView=view && document.querySelector(`[data-view="${view}"]`) ? view : 'overview';
  if(qAgent&&(!view||view==='agent'))nextView='agent';
  if(nextView!=='overview'&&!isPlatformScope())loadSbAgents();
  if(nextView==='agent'){
    // 激活对应 tab UI
    if(qAtab){
      document.querySelectorAll('#agent-tabs .tab').forEach(x=>{
        x.classList.toggle('active',x.dataset.at===qAtab);
      });
    }
    switchView('agent',qAgent||aid||undefined);
  }else{
    switchView(nextView);
  }
}

// ── Sidebar agents ──
function renderSbAgents(team){
  const c=el('sb-agents');
  if(isPlatformScope()){c.innerHTML='<div style="padding:12px;color:var(--dim);font-size:12px">未选择团队</div>';return}
  if(!team||!team.agents){c.innerHTML='<div style="padding:12px;color:var(--dim);font-size:12px">暂无成员</div>';return}
  const aa=Array.isArray(team.agents)?team.agents:Object.values(team.agents);
  c.innerHTML=aa.map(a=>`<div class="sb-agent${a.agent_id===aid?' active':''}" onclick="selectAgent('${a.agent_id}')"><span class="dot ${a.state||'idle'}"></span><span style="overflow:hidden;text-overflow:ellipsis">${escapeHtml(a.name||a.agent_id)}</span></div>`).join('');
}

async function loadSbAgents(){
  if(isPlatformScope()){renderSbAgents(null);return}
  const d=await api(`${A}/teams/${tid}`);
  renderSbAgents(d);
}
function selectAgent(id){aid=id;switchView('agent',id)}
window.selectAgent=selectAgent;
/** 列表「编辑」：进入 Agent 设置 Tab */
function editAgentFromList(id){
  aid=id;
  atab='ag-settings';
  document.querySelectorAll('#agent-tabs .tab').forEach(x=>{
    x.classList.toggle('active',x.dataset.at==='ag-settings');
  });
  switchView('agent',id);
}
window.editAgentFromList=editAgentFromList;
/** 列表「删除」：可传 agent_id，不必先进入详情 */
async function deleteAgentFromList(id,name){
  const agentId=String(id||'').trim();
  if(!agentId){toast('缺少 agent_id');return}
  if(!confirm(`确定删除智能体「${name||agentId}」？此操作不可撤销。`))return;
  let r=null;
  const url=`${A}/teams/${tid}/agents/${encodeURIComponent(agentId)}`;
  if(window.api&&typeof window.api.del==='function'){
    r=await window.api.del(url);
  }else{
    r=await api(url,{method:'DELETE'});
  }
  if(r&&(r.deleted||r.status==='deleted'||r.agent_id||r.deleted===agentId)){
    toast('已删除');
    if(aid===agentId)aid='';
    loadSbAgents();
    if(document.querySelector('#view-overview:not(.hidden)'))loadOverview();
    else switchView('overview');
  }else{
    const err=(window.api&&window.api._lastError)||api._lastError||{};
    // DELETE 有时返回空 body 但 200 — 再按 status 判断
    if(err.status===0||!err.status){
      // 再刷列表确认是否已消失
      toast('已提交删除');
      if(aid===agentId)aid='';
      loadSbAgents();
      if(document.querySelector('#view-overview:not(.hidden)'))loadOverview();
    }else{
      toast('删除失败：'+(err.message||'未知错误'));
    }
  }
}
window.deleteAgentFromList=deleteAgentFromList;

// ── Overview ──
let _ovTimer=null;

// ── 团队成员协作环状图 & 拓扑设计系统 ──────────────────────────────
const _TOPO_PRESETS = {
  dev: {
    key: 'dev',
    name: '全流程研发协作环',
    badge: '💻 研发全流水线',
    steps: [
      { key: 'pm_decompose', label: 'PM需求分解', role: 'project_manager', icon: '📋' },
      { key: 'research', label: '技术研究分析', role: 'researcher', icon: '🔬' },
      { key: 'architecture', label: '系统架构设计', role: 'architect', icon: '📐' },
      { key: 'develop', label: '核心代码开发', role: 'developer', icon: '💻' },
      { key: 'test', label: '质量测试验证', role: 'qa_engineer', icon: '🧪' },
      { key: 'deploy', label: '部署构建上线', role: 'devops', icon: '🚀' },
      { key: 'document', label: '项目文档更新', role: 'documentation', icon: '📝' },
    ]
  },
  xops: {
    key: 'xops',
    name: 'xOPs 云运维与SRE运营环',
    badge: '☁️ xOPs 运营环',
    steps: [
      { key: 'ops_triage', label: '事件响应与调度', role: 'incident_commander', icon: '🚨' },
      { key: 'sre_design', label: 'SRE方案设计', role: 'platform_sre_architect', icon: '🛡️' },
      { key: 'automation_exec', label: '自动化作业实施', role: 'automation_platform_engineer', icon: '⚙️' },
      { key: 'cloud_delivery', label: '多云服务落地', role: 'cloud_service_owner', icon: '🌐' },
      { key: 'security_audit', label: '安全合规审计', role: 'security_compliance_engineer', icon: '🔒' },
      { key: 'finops_review', label: 'FinOps成本复盘', role: 'finops_analyst', icon: '💰' },
      { key: 'sop_postmortem', label: '运营归档与SOP', role: 'domestic_cloud_service_owner', icon: '📚' },
    ]
  },
  energy: {
    key: 'energy',
    name: '绿色能效与达尔文演化环',
    badge: '⚡ 能效治理环',
    steps: [
      { key: 'anomaly_sensing', label: '异常功耗感知', role: 'anomaly_detector', icon: '📡' },
      { key: 'thermal_analysis', label: '热力分布分析', role: 'thermal_engineer', icon: '🌡️' },
      { key: 'pue_opt', label: 'PUE能效调优', role: 'energy_optimizer', icon: '⚡' },
      { key: 'evolution_verify', label: '达尔文演化验证', role: 'evolution_engineer', icon: '🧬' },
      { key: 'policy_audit', label: '政策合规审计', role: 'policy_analyst', icon: '📜' },
      { key: 'forecast_archive', label: '负荷预测与归档', role: 'forecast_analyst', icon: '📈' },
    ]
  }
};

const _ROLE_FALLBACK_CANDIDATES = {
  project_manager: ['project_manager', 'cloud_ops_finops_owner', '运维Leader', 'incident_commander', 'leader', 'owner', 'manager', 'pm', '负责人', '指挥官'],
  researcher: ['researcher', 'finops_analyst', 'anomaly_detector', '巡检监控员', '成本优化成员', 'analyst', 'sentinel', 'watchdog', '分析', '巡检', '研究'],
  architect: ['architect', 'platform_sre_architect', '上云架构师', 'sre', '架构'],
  developer: ['developer', 'automation_platform_engineer', '运维操作员', 'engineer', 'automation', 'operator', '开发', '工程师', '操作'],
  qa_engineer: ['qa_engineer', 'security_compliance_engineer', 'tester', 'qa', 'security', 'compliance', 'verifier', '安全', '合规', '测试'],
  devops: ['devops', 'aws_service_owner', 'azure_service_owner', 'aliyun_service_owner', 'gcp_service_owner', 'domestic_cloud_service_owner', 'deployer', '运维操作员', '运维', '部署'],
  documentation: ['documentation', 'domestic_cloud_service_owner', 'doc_writer', '文档', 'writer', 'doc'],

  incident_commander: ['incident_commander', 'cloud_ops_finops_owner', '运维Leader', 'operations_lead', 'leader', '指挥官', '值班', '调度', '负责人'],
  platform_sre_architect: ['platform_sre_architect', '上云架构师', 'cloud_architect', 'architect', 'sre', '架构'],
  automation_platform_engineer: ['automation_platform_engineer', '运维操作员', 'operations_operator', 'developer', 'automation', '自动化', '操作', '平台', '工程师'],
  cloud_service_owner: ['aws_service_owner', 'azure_service_owner', 'aliyun_service_owner', 'gcp_service_owner', 'domestic_cloud_service_owner', '北美AI项目运维员', 'devops', '云服务', '实施', '运维'],
  security_compliance_engineer: ['security_compliance_engineer', 'regional_compliance', 'qa_engineer', 'tester', 'security', 'compliance', '安全', '合规', '风控'],
  finops_analyst: ['finops_analyst', 'cost_optimizer', '成本优化成员', 'cloud-finops', 'finops', '成本', '财务', '分析'],
  domestic_cloud_service_owner: ['domestic_cloud_service_owner', 'cloud_ops_finops_owner', 'doc_writer', 'documentation', 'ccoe', '云卓越中心治理', '文档', '归档', '复盘', 'SOP'],

  anomaly_detector: ['anomaly_detector', 'anomaly_watchdog', '巡检监控员', 'monitoring', 'watchdog', '巡检', '异常'],
  thermal_engineer: ['thermal_engineer', 'thermal_sentinel', 'sentinel', '热力', '温控'],
  energy_optimizer: ['energy_optimizer', 'pue_optimizer', 'optimizer', '能效', 'pue'],
  evolution_engineer: ['evolution_engineer', 'darwin_ratchet', 'ratchet', '演化', '棘轮'],
  policy_analyst: ['policy_analyst', 'policy_engine', '合规', '政策', '审计'],
  forecast_analyst: ['forecast_analyst', 'forecast_planner', 'planner', '预测', '调度'],
};

const _AGENT_ACCENT_COLORS = ['#22d3ee', '#34d399', '#a78bfa', '#fbbf24', '#f472b6', '#60a5fa', '#f97316', '#38bdf8', '#4ade80', '#e879f9', '#fb7185'];

let _isEditingTopology = false;
let _selectedSourceAgentId = null;
let _currentTeamDetail = null;
let _customTopologyLinks = [];
let _customTopologyUndoStack = [];
let _customTopologyRedoStack = [];

function _pushTopologyUndo(){
  _customTopologyUndoStack.push(JSON.parse(JSON.stringify(_customTopologyLinks)));
  _customTopologyRedoStack = [];
  _updateUndoRedoBtnState();
}

function _updateUndoRedoBtnState(){
  const btnUndo = el('btn-undo-topo');
  const btnRedo = el('btn-redo-topo');
  if(btnUndo){
    const canUndo = _customTopologyUndoStack.length > 0;
    btnUndo.disabled = !canUndo;
    btnUndo.style.opacity = canUndo ? '1' : '0.45';
    btnUndo.style.cursor = canUndo ? 'pointer' : 'not-allowed';
  }
  if(btnRedo){
    const canRedo = _customTopologyRedoStack.length > 0;
    btnRedo.disabled = !canRedo;
    btnRedo.style.opacity = canRedo ? '1' : '0.45';
    btnRedo.style.cursor = canRedo ? 'pointer' : 'not-allowed';
  }
}

function _inferTeamDomain(team, teamId){
  const tId = (team?.team_id || teamId || '').toLowerCase();
  const tName = (team?.name || '').toLowerCase();
  const combined = `${tId} ${tName}`;
  if (['energy', 'pue', 'thermal', '节能', '能效'].some(k => combined.includes(k))) return 'energy';
  if (['ops', 'cloud', 'aws', 'sre', '运维', '云平台', 'finops'].some(k => combined.includes(k))) return 'xops';
  const agents = Array.isArray(team?.agents) ? team.agents : Object.values(team?.agents || {});
  const opsMarkers = ['cloud_ops', 'sre', 'finops', 'incident', 'aws_', 'azure_', 'aliyun_', 'gcp_', 'domestic_cloud', '运维', '巡检', '上云'];
  for(const a of agents){
    const r = (a.role || '').toLowerCase();
    if(opsMarkers.some(m => r.includes(m))) return 'xops';
  }
  const energyMarkers = ['energy', 'pue', 'thermal', 'ratchet'];
  for(const a of agents){
    const r = (a.role || '').toLowerCase();
    if(energyMarkers.some(m => r.includes(m))) return 'energy';
  }
  return 'dev';
}

function _findAgentForRole(roleNeeded, agentsList, defaultAgentId=''){
  if(!agentsList || !agentsList.length) return defaultAgentId;
  for(const a of agentsList){
    if(a.role === roleNeeded && a.agent_id) return a.agent_id;
  }
  const candidates = _ROLE_FALLBACK_CANDIDATES[roleNeeded] || [roleNeeded];
  for(const cand of candidates){
    for(const a of agentsList){
      const aRole = (a.role || '').toLowerCase();
      const aName = (a.name || '').toLowerCase();
      if(!a.agent_id) continue;
      if(aRole.includes(cand.toLowerCase()) || aName.includes(cand.toLowerCase())){
        return a.agent_id;
      }
    }
  }
  return defaultAgentId || agentsList[0]?.agent_id || '';
}

/** 渲染成员环状拓扑图 */
function renderTeamTopology(teamDetail){
  _currentTeamDetail = teamDetail;
  const svg = el('topo-ring-svg');
  const sel = el('topo-mode-sel');
  const badge = el('topo-badge');
  const stepsBar = el('topo-steps-bar');
  if(!svg || !teamDetail) return;

  const rawAgents = teamDetail.agents;
  const agents = Array.isArray(rawAgents) ? rawAgents : Object.values(rawAgents || {});
  const totalAgents = agents.length;
  const inferredDomain = _inferTeamDomain(teamDetail, tid);
  const autoPreset = _TOPO_PRESETS[inferredDomain] || _TOPO_PRESETS.dev;
  const mode = _isEditingTopology ? 'custom' : (teamDetail.workflow_mode || 'auto');

  // 1. 同步下拉选择框第一项（自适应文本）与当前选定值
  if(sel){
    const optAuto = sel.querySelector('option[value="auto"]');
    if(optAuto){
      optAuto.textContent = `✨ 智能自适应（匹配：${autoPreset.name}）`;
    }
    const targetMode = _isEditingTopology ? 'custom' : (teamDetail.workflow_mode || 'auto');
    if(sel.value !== targetMode && document.activeElement !== sel){
      sel.value = targetMode;
    }
  }

  // 仅在非编辑状态或 _customTopologyLinks 未初始化时从 metadata 同步
  if(!_isEditingTopology){
    if(Array.isArray(teamDetail.metadata?.custom_topology)){
      _customTopologyLinks = [...teamDetail.metadata.custom_topology];
    } else {
      _customTopologyLinks = [];
    }
  }

  if(totalAgents === 0){
    svg.innerHTML = `<text x="380" y="220" text-anchor="middle" fill="var(--dim)" font-size="14">团队暂无成员，请点击左侧「＋ 新建智能体」添加成员</text>`;
    if(stepsBar) stepsBar.innerHTML = '<span style="color:var(--dim);font-size:12px">暂无协作步骤</span>';
    return;
  }

  // 2. 环状坐标计算 (中心 380, 220，半径根据成员数自适应)
  const cx = 380, cy = 220;
  const R = totalAgents <= 4 ? 130 : totalAgents <= 7 ? 145 : 155;
  const nodeCoords = {};
  agents.forEach((a, i) => {
    const angle = (2 * Math.PI * i / totalAgents) - (Math.PI / 2);
    nodeCoords[a.agent_id] = {
      x: cx + R * Math.cos(angle),
      y: cy + R * Math.sin(angle),
      angle: angle,
      agent: a,
      color: _AGENT_ACCENT_COLORS[i % _AGENT_ACCENT_COLORS.length]
    };
  });

  // 3. 计算当前拓扑模式下的步骤和连线
  let links = [];
  let flowSteps = [];
  let currentBadgeText = autoPreset.badge;

  if(_isEditingTopology || mode === 'custom'){
    currentBadgeText = '✏️ 自定义连线 (编辑中)';
    links = [..._customTopologyLinks];
    flowSteps = links.map((lnk, idx) => {
      const srcA = agents.find(a => a.agent_id === lnk.source);
      const tgtA = agents.find(a => a.agent_id === lnk.target);
      return {
        key: `custom_step_${idx + 1}`,
        label: `${srcA?.name || '起点'} ➔ ${tgtA?.name || '目标'}`,
        icon: '🔗',
        agent_id: lnk.source,
        target_id: lnk.target
      };
    });
    if(!flowSteps.length){
      flowSteps = [{ key: 'custom_empty', label: '请点击任意成员作为起点开始连线', icon: '✏️', agent_id: '' }];
    }
  } else if(mode === 'single'){
    currentBadgeText = '👤 单步独立模式';
    flowSteps = [{ key: 'execute', label: '单步独立执行', icon: '👤', agent_id: agents[0]?.agent_id || '' }];
  } else if(mode === 'star'){
    currentBadgeText = '⭐ 星型中枢模式';
    const hubId = _findAgentForRole('incident_commander', agents) || agents[0]?.agent_id;
    agents.forEach(a => {
      if(a.agent_id !== hubId){
        links.push({ source: hubId, target: a.agent_id, label: '调度/汇聚' });
      }
    });
    const hubAgent = agents.find(a => a.agent_id === hubId);
    flowSteps = [
      { key: 'star_hub', label: `${hubAgent?.name || '中枢'}·总控分发`, icon: '⭐', agent_id: hubId },
      ...agents.filter(a => a.agent_id !== hubId).map(a => ({ key: `star_${a.agent_id}`, label: `${a.name}·专项协同`, icon: '🔹', agent_id: a.agent_id })),
      { key: 'star_agg', label: `${hubAgent?.name || '中枢'}·汇总验收`, icon: '🏁', agent_id: hubId }
    ];
  } else if(mode === 'mesh'){
    currentBadgeText = '🕸️ 全网状自由协同';
    for(let i = 0; i < agents.length; i++){
      for(let j = i + 1; j < agents.length; j++){
        links.push({ source: agents[i].agent_id, target: agents[j].agent_id, label: '对等通信' });
      }
    }
    flowSteps = agents.map((a, idx) => ({ key: `mesh_${a.agent_id}`, label: `${a.name}·对等协同`, icon: '🔄', agent_id: a.agent_id }));
  } else {
    // 领域预设环 (xops / dev / energy / auto)
    const effectivePresetKey = (mode === 'auto' || mode === 'full') ? inferredDomain : mode;
    const preset = _TOPO_PRESETS[effectivePresetKey] || _TOPO_PRESETS.dev;
    currentBadgeText = preset.badge;

    flowSteps = preset.steps.map(s => {
      const aid = _findAgentForRole(s.role, agents);
      const ag = agents.find(a => a.agent_id === aid);
      return {
        ...s,
        agent_id: aid,
        agent_name: ag?.name || '待指定'
      };
    });

    // 顺序建立首尾或链式连线
    for(let i = 0; i < flowSteps.length - 1; i++){
      const srcId = flowSteps[i].agent_id;
      const tgtId = flowSteps[i + 1].agent_id;
      if(srcId && tgtId && srcId !== tgtId){
        links.push({ source: srcId, target: tgtId, label: `S${i+1}➔S${i+2}` });
      }
    }
    // 闭环连接（最后一步连回第一步，形成生命周期持续演进闭环）
    if(flowSteps.length > 2){
      const lastId = flowSteps[flowSteps.length - 1].agent_id;
      const firstId = flowSteps[0].agent_id;
      if(lastId && firstId && lastId !== firstId){
        links.push({ source: lastId, target: firstId, label: '闭环反馈' });
      }
    }
  }

  if(badge) badge.textContent = currentBadgeText;

  // 4. 构建 SVG 视图
  let svgContent = `
    <defs>
      <!-- 箭头标记 -->
      <marker id="topo-arrow" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#22d3ee" />
      </marker>
      <marker id="topo-arrow-amber" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#fbbf24" />
      </marker>
      <marker id="topo-arrow-active" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M 0 1 L 9 5 L 0 9 z" fill="#38bdf8" />
      </marker>
      <!-- 发光滤镜 -->
      <filter id="topo-glow" x="-20%" y="-20%" width="140%" height="140%">
        <feGaussianBlur stdDeviation="3" result="blur" />
        <feComposite in="SourceGraphic" in2="blur" operator="over" />
      </filter>
    </defs>

    <!-- 背景科技同心圆环 -->
    <circle cx="${cx}" cy="${cy}" r="${R}" fill="none" stroke="var(--line)" stroke-width="1.5" stroke-dasharray="4 6" opacity="0.6" />
    <circle cx="${cx}" cy="${cy}" r="${R + 32}" fill="none" stroke="var(--line)" stroke-width="1" stroke-dasharray="2 10" opacity="0.3" />
    <circle cx="${cx}" cy="${cy}" r="${R * 0.45}" fill="none" stroke="var(--line)" stroke-width="1" opacity="0.4" />

    <!-- 中心徽章 -->
    <g class="topo-center-badge" style="cursor:pointer" onclick="toggleTopologyEditMode()" title="${_isEditingTopology ? '点击完成编辑' : '点击继续编辑连线'}">
      <circle cx="${cx}" cy="${cy}" r="54" fill="var(--panel2)" stroke="${_isEditingTopology ? '#fbbf24' : '#22d3ee'}" stroke-width="1.8" opacity="0.95" />
      <text x="${cx}" y="${cy - 16}" text-anchor="middle" font-size="20">${_isEditingTopology ? '✏️' : '🤖'}</text>
      <text x="${cx}" y="${cy + 6}" text-anchor="middle" fill="var(--text)" font-size="12" font-weight="700">${escapeHtml(teamDetail.name || tid).slice(0, 10)}</text>
      <text x="${cx}" y="${cy + 22}" text-anchor="middle" fill="${_isEditingTopology ? '#fbbf24' : '#22d3ee'}" font-size="10" font-family="var(--font-mono)">${_isEditingTopology ? '✏️ 编辑中' : `${links.length} 协作链路`}</text>
      <text x="${cx}" y="${cy + 34}" text-anchor="middle" fill="var(--muted)" font-size="9">${_isEditingTopology ? '点击完成编辑' : '点击继续编辑'}</text>
    </g>
  `;

  // 5. 渲染连线 (二次贝塞尔曲线，平滑弯向圆心)
  svgContent += `<g class="topo-links-group">`;
  links.forEach((lnk, idx) => {
    const s = nodeCoords[lnk.source];
    const t = nodeCoords[lnk.target];
    if(!s || !t) return;

    // 控制点稍微拉向中心
    const bend = 0.45;
    const qx = (s.x + t.x) * 0.5 * (1 - bend) + cx * bend;
    const qy = (s.y + t.y) * 0.5 * (1 - bend) + cy * bend;

    const isCustom = _isEditingTopology || (mode === 'custom');
    const strokeColor = isCustom ? '#fbbf24' : '#22d3ee';
    const markerId = isCustom ? 'topo-arrow-amber' : 'topo-arrow';

    svgContent += `
      <g class="topo-link-item" style="cursor:${_isEditingTopology ? 'pointer' : 'default'}" onclick="handleTopoLinkClick('${escapeHtml(lnk.source)}', '${escapeHtml(lnk.target)}')">
        <!-- 拓宽鼠标拾取区域 -->
        <path d="M ${s.x} ${s.y} Q ${qx} ${qy} ${t.x} ${t.y}" fill="none" stroke="transparent" stroke-width="18" />
        <!-- 实体连线 -->
        <path class="topo-link-path" d="M ${s.x} ${s.y} Q ${qx} ${qy} ${t.x} ${t.y}" fill="none" stroke="${strokeColor}" stroke-width="${isCustom ? '2.4' : '2'}" opacity="0.85" marker-end="url(#${markerId})">
          <title>协作交接：${escapeHtml(s.agent.name || s.agent.agent_id)} ➔ ${escapeHtml(t.agent.name || t.agent.agent_id)}${_isEditingTopology ? '（点击删除此连线）' : ''}</title>
        </path>
      </g>
    `;
  });
  svgContent += `</g>`;

  // 6. 渲染成员节点
  svgContent += `<g class="topo-nodes-group">`;
  agents.forEach((a, i) => {
    const node = nodeCoords[a.agent_id];
    if(!node) return;
    const isSelectedSource = (_selectedSourceAgentId === a.agent_id);
    const nodeColor = node.color;
    const name = a.name || a.agent_id || `Agent-${i+1}`;
    const role = a.role || '成员';
    const initial = name.slice(0, 1).toUpperCase();

    // 标签位置与对齐
    const cosA = Math.cos(node.angle);
    const sinA = Math.sin(node.angle);
    let labelX = node.x + (cosA > 0.2 ? 24 : cosA < -0.2 ? -24 : 0);
    let labelY = node.y + (sinA > 0.5 ? 26 : sinA < -0.5 ? -20 : 4);
    let textAnchor = cosA > 0.2 ? 'start' : cosA < -0.2 ? 'end' : 'middle';

    svgContent += `
      <g class="topo-node-item" style="cursor:pointer" onclick="handleTopoNodeClick('${escapeHtml(a.agent_id)}')" transform="translate(0,0)">
        <!-- 选中态扩散光环 -->
        ${isSelectedSource ? `
          <circle cx="${node.x}" cy="${node.y}" r="28" fill="none" stroke="#fbbf24" stroke-width="2.5" opacity="0.95" stroke-dasharray="4 2">
            <animateTransform attributeName="transform" type="rotate" from="0 ${node.x} ${node.y}" to="360 ${node.x} ${node.y}" dur="3s" repeatCount="indefinite"/>
          </circle>
          <circle cx="${node.x}" cy="${node.y}" r="34" fill="rgba(251,191,36,0.2)" />
        ` : ''}

        <!-- 节点主圆 -->
        <circle cx="${node.x}" cy="${node.y}" r="18" fill="var(--panel2)" stroke="${isSelectedSource ? '#fbbf24' : nodeColor}" stroke-width="${isSelectedSource ? '3' : '2'}" filter="url(#topo-glow)" />
        
        <!-- 成员首字 / 头像 -->
        <text x="${node.x}" y="${node.y + 5}" text-anchor="middle" fill="${isSelectedSource ? '#fbbf24' : nodeColor}" font-size="12" font-weight="800" font-family="var(--font-mono)">${escapeHtml(initial)}</text>
        
        <!-- 状态小圆点 -->
        <circle cx="${node.x + 13}" cy="${node.y - 13}" r="4" fill="${a.state === 'working' ? 'var(--cyan)' : a.state === 'error' ? 'var(--red)' : 'var(--lime)'}" stroke="var(--bg)" stroke-width="1.5" />

        <!-- 姓名与角色标签 -->
        <g transform="translate(${labelX}, ${labelY})">
          <text x="0" y="0" text-anchor="${textAnchor}" fill="${isSelectedSource ? '#fbbf24' : 'var(--text)'}" font-size="11" font-weight="700">${escapeHtml(name)}</text>
          <text x="0" y="12" text-anchor="${textAnchor}" fill="var(--muted)" font-size="9.5">${escapeHtml(role.length > 14 ? role.slice(0, 13) + '…' : role)}</text>
        </g>
        
        <title>${escapeHtml(name)} (${escapeHtml(role)})\n状态: ${stL(a.state || 'idle')}${_isEditingTopology ? '\n点击可连接/解除协作关系' : '\n点击可查看成员详情'}</title>
      </g>
    `;
  });
  svgContent += `</g>`;

  svg.innerHTML = svgContent;

  // 7. 渲染底部时序胶囊条
  if(stepsBar){
    stepsBar.innerHTML = flowSteps.map((st, idx) => {
      const ag = agents.find(a => a.agent_id === st.agent_id);
      const isCur = (_selectedSourceAgentId === st.agent_id);
      return `
        <div class="chip" style="padding:4px 10px;font-size:11px;display:flex;align-items:center;gap:6px;background:${isCur ? 'rgba(251,191,36,0.15)' : 'var(--panel2)'};border:1px solid ${isCur ? 'var(--amber)' : 'var(--line)'};cursor:pointer" onclick="handleTopoNodeClick('${escapeHtml(st.agent_id)}')">
          <span style="font-family:var(--font-mono);color:var(--cyan);font-weight:700">${idx + 1}</span>
          <span>${st.icon || '🔹'} <b>${escapeHtml(st.label || '')}</b></span>
          <span style="color:var(--muted)">(${escapeHtml(ag?.name || '自动指派')})</span>
        </div>
      `;
    }).join('<span style="color:var(--dim);font-size:11px">➔</span>');
  }
}

/** 切换编辑模式 */
function toggleTopologyEditMode(forceState){
  const willEdit = (forceState !== undefined) ? Boolean(forceState) : !_isEditingTopology;
  _isEditingTopology = willEdit;
  _selectedSourceAgentId = null;

  const btnEdit = el('btn-edit-topo');
  const btnQuick = el('btn-quick-edit-topo');
  const btnSave = el('btn-save-topo');
  const btnUndo = el('btn-undo-topo');
  const btnRedo = el('btn-redo-topo');
  const btnLoop = el('btn-autoloop-topo');
  const btnClear = el('btn-clear-topo');
  const hintBox = el('topo-edit-hint');
  const hintText = el('topo-hint-text');
  const sel = el('topo-mode-sel');

  if(_isEditingTopology){
    if(btnEdit){ btnEdit.textContent = '✓ 完成编辑'; btnEdit.className = 'btn btn-sm btn-ghost'; }
    if(btnQuick){ btnQuick.textContent = '💾 保存连线拓扑'; btnQuick.className = 'btn btn-sm btn-pink'; btnQuick.onclick = () => saveCustomTopology(); }
    btnSave?.classList.remove('hidden');
    btnUndo?.classList.remove('hidden');
    btnRedo?.classList.remove('hidden');
    btnLoop?.classList.remove('hidden');
    btnClear?.classList.remove('hidden');
    hintBox?.classList.remove('hidden');
    if(sel) sel.value = 'custom';
    if(hintText){
      hintText.innerHTML = `💡 <b>连线编辑中：</b> 点击起点成员，再点击目标成员建立协作连线（支持随时点击「↩ 回退」与「↪ 下一步」）`;
    }
    // 进入编辑模式时，保留团队已有的自定义连线
    if(Array.isArray(_currentTeamDetail?.metadata?.custom_topology)){
      _customTopologyLinks = [..._currentTeamDetail.metadata.custom_topology];
    } else {
      _customTopologyLinks = [];
    }
    _customTopologyUndoStack = [];
    _customTopologyRedoStack = [];
    _updateUndoRedoBtnState();
    toast('已进入自定义连线模式：点击起点成员，再点击目标成员开始连线', 'info');
  } else {
    if(btnEdit){ btnEdit.textContent = '✏️ 连线编辑'; btnEdit.className = 'btn btn-sm btn-pink'; }
    if(btnQuick){ btnQuick.textContent = '✏️ 连线编辑 / 继续画线'; btnQuick.className = 'btn btn-sm btn-pink'; btnQuick.onclick = () => toggleTopologyEditMode(true); }
    btnSave?.classList.add('hidden');
    btnUndo?.classList.add('hidden');
    btnRedo?.classList.add('hidden');
    btnLoop?.classList.add('hidden');
    btnClear?.classList.add('hidden');
    hintBox?.classList.add('hidden');
  }

  if(_currentTeamDetail){
    _currentTeamDetail.workflow_mode = _isEditingTopology ? 'custom' : (sel?.value || 'auto');
    if(_currentTeamDetail.metadata){
      _currentTeamDetail.metadata.custom_topology = _customTopologyLinks;
    }
    renderTeamTopology(_currentTeamDetail);
  }
}
window.toggleTopologyEditMode = toggleTopologyEditMode;

/** 回退上一步操作 (Undo) */
function undoTopologyStep(){
  if(!_customTopologyUndoStack.length){
    toast('没有可回退的操作', 'info');
    return;
  }
  _customTopologyRedoStack.push(JSON.parse(JSON.stringify(_customTopologyLinks)));
  _customTopologyLinks = _customTopologyUndoStack.pop() || [];
  if(_currentTeamDetail){
    _currentTeamDetail.metadata = _currentTeamDetail.metadata || {};
    _currentTeamDetail.metadata.custom_topology = [..._customTopologyLinks];
    _currentTeamDetail.workflow_mode = 'custom';
  }
  if(_customTopologyLinks.length){
    _selectedSourceAgentId = _customTopologyLinks[_customTopologyLinks.length - 1].target;
  } else {
    _selectedSourceAgentId = null;
  }
  const hintText = el('topo-hint-text');
  if(hintText){
    hintText.innerHTML = `↩️ <b>已回退上一步：</b> 当前剩余 ${_customTopologyLinks.length} 条连线，可继续点击成员连线或点击「💾 保存」`;
  }
  _updateUndoRedoBtnState();
  toast('已回退上一步连线', 'info');
  renderTeamTopology(_currentTeamDetail);
}
window.undoTopologyStep = undoTopologyStep;

/** 重做/下一步操作 (Redo) */
function redoTopologyStep(){
  if(!_customTopologyRedoStack.length){
    toast('没有可前进/下一步的操作', 'info');
    return;
  }
  _customTopologyUndoStack.push(JSON.parse(JSON.stringify(_customTopologyLinks)));
  _customTopologyLinks = _customTopologyRedoStack.pop() || [];
  if(_currentTeamDetail){
    _currentTeamDetail.metadata = _currentTeamDetail.metadata || {};
    _currentTeamDetail.metadata.custom_topology = [..._customTopologyLinks];
    _currentTeamDetail.workflow_mode = 'custom';
  }
  if(_customTopologyLinks.length){
    _selectedSourceAgentId = _customTopologyLinks[_customTopologyLinks.length - 1].target;
  }
  const hintText = el('topo-hint-text');
  if(hintText){
    hintText.innerHTML = `↪️ <b>已前进到下一步：</b> 当前已有 ${_customTopologyLinks.length} 条连线`;
  }
  _updateUndoRedoBtnState();
  toast('已恢复下一步连线', 'info');
  renderTeamTopology(_currentTeamDetail);
}
window.redoTopologyStep = redoTopologyStep;

/** 点击成员节点交互 */
function handleTopoNodeClick(agentId){
  if(!agentId) return;
  if(!_isEditingTopology){
    // 非编辑模式下点击任意成员：自动进入连线编辑模式，并以该成员作为起点！
    toggleTopologyEditMode(true);
    _selectedSourceAgentId = agentId;
    const agents = Array.isArray(_currentTeamDetail?.agents) ? _currentTeamDetail.agents : Object.values(_currentTeamDetail?.agents || {});
    const agent = agents.find(a => a.agent_id === agentId);
    const hintText = el('topo-hint-text');
    if(hintText){
      hintText.innerHTML = `👉 已选起点 <b>${escapeHtml(agent?.name || agentId)}</b>，请点击目标成员建立协作连线`;
    }
    toast(`已进入连线编辑，起点：${agent?.name || agentId}，请点击目标成员连线`, 'info');
    renderTeamTopology(_currentTeamDetail);
    return;
  }

  const agents = Array.isArray(_currentTeamDetail?.agents) ? _currentTeamDetail.agents : Object.values(_currentTeamDetail?.agents || {});
  const agent = agents.find(a => a.agent_id === agentId);
  const hintText = el('topo-hint-text');

  if(_selectedSourceAgentId === null){
    _selectedSourceAgentId = agentId;
    if(hintText){
      hintText.innerHTML = `👉 已选起点 <b>${escapeHtml(agent?.name || agentId)}</b>，请点击目标成员建立/取消协作连线`;
    }
    renderTeamTopology(_currentTeamDetail);
  } else if(_selectedSourceAgentId === agentId){
    // 再次点击自己 -> 取消选择
    _selectedSourceAgentId = null;
    if(hintText){
      hintText.innerHTML = `💡 <b>连线编辑中：</b> 点击起点成员，再点击目标成员建立协作连线（点击已有连线可删除）`;
    }
    renderTeamTopology(_currentTeamDetail);
  } else {
    // 记录回退快照
    _pushTopologyUndo();

    // 建立或移除 A -> B 连线
    const srcId = _selectedSourceAgentId;
    const tgtId = agentId;
    const srcAgent = agents.find(a => a.agent_id === srcId);
    const tgtAgent = agents.find(a => a.agent_id === tgtId);

    const existIdx = _customTopologyLinks.findIndex(l => l.source === srcId && l.target === tgtId);
    if(existIdx >= 0){
      _customTopologyLinks.splice(existIdx, 1);
      toast(`已移除连线：${srcAgent?.name || srcId} ⤬ ${tgtAgent?.name || tgtId}`, 'info');
    } else {
      _customTopologyLinks.push({ source: srcId, target: tgtId, label: '协作交接' });
      toast(`已建立连线：${srcAgent?.name || srcId} ➔ ${tgtAgent?.name || tgtId}`, 'success');
    }

    // 同步到内存对象，防止被覆盖
    if(_currentTeamDetail){
      _currentTeamDetail.metadata = _currentTeamDetail.metadata || {};
      _currentTeamDetail.metadata.custom_topology = [..._customTopologyLinks];
      _currentTeamDetail.workflow_mode = 'custom';
    }

    // 链式推进：将目标成员作为下一个潜在起点
    _selectedSourceAgentId = tgtId;
    if(hintText){
      hintText.innerHTML = `👉 已连至 <b>${escapeHtml(tgtAgent?.name || tgtId)}</b>，可继续点击下一个目标成员，或点击「💾 保存拓扑」`;
    }
    _updateUndoRedoBtnState();
    renderTeamTopology(_currentTeamDetail);
  }
}
window.handleTopoNodeClick = handleTopoNodeClick;

/** 点击连线直接删除 */
function handleTopoLinkClick(srcId, tgtId){
  if(!_isEditingTopology) return;
  const existIdx = _customTopologyLinks.findIndex(l => l.source === srcId && l.target === tgtId);
  if(existIdx >= 0){
    _pushTopologyUndo();
    _customTopologyLinks.splice(existIdx, 1);
    if(_currentTeamDetail){
      _currentTeamDetail.metadata = _currentTeamDetail.metadata || {};
      _currentTeamDetail.metadata.custom_topology = [..._customTopologyLinks];
    }
    _updateUndoRedoBtnState();
    toast('已删除协作连线', 'info');
    renderTeamTopology(_currentTeamDetail);
  }
}
window.handleTopoLinkClick = handleTopoLinkClick;

/** 自动首尾成环 */
function autoLoopTopology(){
  const agents = Array.isArray(_currentTeamDetail?.agents) ? _currentTeamDetail.agents : Object.values(_currentTeamDetail?.agents || {});
  if(agents.length < 2){
    toast('成员不足 2 人，无法成环', 'warning');
    return;
  }
  _pushTopologyUndo();
  _customTopologyLinks = [];
  for(let i = 0; i < agents.length; i++){
    const nextIdx = (i + 1) % agents.length;
    _customTopologyLinks.push({
      source: agents[i].agent_id,
      target: agents[nextIdx].agent_id,
      label: '顺序协作'
    });
  }
  if(_currentTeamDetail){
    _currentTeamDetail.metadata = _currentTeamDetail.metadata || {};
    _currentTeamDetail.metadata.custom_topology = [..._customTopologyLinks];
  }
  _updateUndoRedoBtnState();
  toast(`已自动将 ${agents.length} 名成员连成闭环`, 'success');
  renderTeamTopology(_currentTeamDetail);
}
window.autoLoopTopology = autoLoopTopology;

/** 清空连线 */
function clearTopologyLinks(){
  _pushTopologyUndo();
  _customTopologyLinks = [];
  _selectedSourceAgentId = null;
  if(_currentTeamDetail){
    _currentTeamDetail.metadata = _currentTeamDetail.metadata || {};
    _currentTeamDetail.metadata.custom_topology = [];
  }
  _updateUndoRedoBtnState();
  toast('已清空所有连线', 'info');
  renderTeamTopology(_currentTeamDetail);
}
window.clearTopologyLinks = clearTopologyLinks;

/** 保存自定义拓扑配置 */
async function saveCustomTopology(){
  if(!tid) return;
  const r = await api(`${A}/teams/${tid}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      workflow_mode: 'custom',
      metadata: { custom_topology: _customTopologyLinks }
    })
  });
  if(r && r.workflow_mode === 'custom'){
    if(_currentTeamDetail){
      _currentTeamDetail.workflow_mode = 'custom';
      _currentTeamDetail.metadata = _currentTeamDetail.metadata || {};
      _currentTeamDetail.metadata.custom_topology = [..._customTopologyLinks];
    }
    toast('💾 自定义协作拓扑已成功保存！后续派发任务将按此顺序流转', 'success');
    toggleTopologyEditMode(false);
  } else {
    toast('保存自定义拓扑失败', 'error');
  }
}
window.saveCustomTopology = saveCustomTopology;

// 下拉菜单切换拓扑模式
async function handleTopoModeSelectChange(sel){
  const val = sel?.value || 'auto';
  if(val === 'custom'){
    toggleTopologyEditMode(true);
  } else {
    if(_isEditingTopology) toggleTopologyEditMode(false);
    const r = await api(`${A}/teams/${tid}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workflow_mode: val })
    });
    if(r){
      toast(`已切换拓扑模式：${sel?.options[sel.selectedIndex]?.text || val}`, 'success');
      if(_currentTeamDetail){
        _currentTeamDetail.workflow_mode = val;
        renderTeamTopology(_currentTeamDetail);
      }
    } else {
      toast('切换拓扑模式失败', 'error');
    }
  }
}
window.handleTopoModeSelectChange = handleTopoModeSelectChange;

// DOM 兜底绑定
try {
  const selEl = el('topo-mode-sel');
  if(selEl) {
    selEl.onchange = () => handleTopoModeSelectChange(selEl);
  }
} catch(e) {}

async function loadOverview(){
  if(_ovTimer)clearInterval(_ovTimer);
  if(isPlatformScope())return loadPlatformOverview();
  const [teamsList,ov]=await Promise.all([
    getTeamsList(),
    api(`${AT}/overview?team_id=${encodeURIComponent(tid)}`)
  ]);
  const curTm=ov?.current_team||null;
  const sc=el('ov-stats');
  _setOverviewSections(false);
  const _teamIcons={'build_system':'🏗️','energy_first_principle':'⚡','ai_coding':'💻','d083a568':'☁️'};
  const allTeams=teamsList||[];
  if(ov){
    const sh=ov.scheduler||{};
    const ev=ov.evolution||{};
    const evs=ev.stats||{};
    const taskSummary=curTm?.tasks||{};
    const curMeta=allTeams.find(t=>t&&t.team_id===tid)||{};
    const agentsArr=curTm?.agents?(Array.isArray(curTm.agents)?curTm.agents:Object.values(curTm.agents)):[];
    const working=agentsArr.filter(a=>a&&a.state==='working').length;
    // 团队作用域只呈现本团队指标；跨团队汇总在「全部团队」平台视图
    sc.innerHTML=`
      <div class="stat-card" data-scope="team"><div class="label">🤖 成员</div><div class="value">${curMeta.agent_count??agentsArr.length??0}</div><div class="sub">${working} 个工作中</div></div>
      <div class="stat-card" data-scope="team"><div class="label">📦 模型</div><div class="value">${curMeta.model_count??0}</div><div class="sub">本团队模型槽</div></div>
      <div class="stat-card" data-scope="team"><div class="label">📋 任务</div><div class="value">${taskSummary.total||0}</div><div class="sub">${Object.entries(taskSummary.by_status||{}).map(([k,v])=>`${k}: ${v}`).join(' · ')||'无任务'}</div></div>
      <div class="stat-card"><div class="label">📊 调度器</div><div class="value" style="font-size:16px;color:${sh.running?'var(--lime)':'var(--red)'}">${sh.running?'运行中':'已停止'}</div><div class="sub">平台级 · Tick ${sh.tick_count??0}</div></div>
      <div class="stat-card"><div class="label">🔄 自我演进</div><div class="value">${ev?.evolution_items_count??'-'}</div><div class="sub">平台级 · 已验证 ${evs?.total_verified??0}</div></div>`;
    const curTmMeta=curMeta;
    const teamTitle=(curTm&&curTm.name)||(curTmMeta&&curTmMeta.name)||tid;
    const teamIcon=_teamIcons[tid]||'🤖';
    renderSbAgents(curTm);
    el('ov-team-title').textContent=`${teamIcon} ${teamTitle}`;
    
    // 渲染成员环状拓扑图与协作流
    api(`${A}/teams/${tid}`).then(fullTeam => {
      renderTeamTopology(fullTeam || curTm);
    }).catch(() => {
      renderTeamTopology(curTm);
    });
    const tbody=el('ov-team-agents');tbody.innerHTML='';
    if(curTm&&curTm.agents){
      const aa=Array.isArray(curTm.agents)?curTm.agents:Object.values(curTm.agents);
      aa.forEach(a=>{
        const id=escapeHtml(a.agent_id||'');
        const nm=escapeHtml(a.name||a.agent_id||'');
        tbody.innerHTML+=`<tr>
          <td><b>${nm}</b></td>
          <td style="color:var(--muted)">${escapeHtml(a.role||'-')}</td>
          <td><span class="st st-${a.state||'idle'}">${stL(a.state)}</span></td>
          <td>${(a.skills||[]).slice(0,3).map(s=>'<span class="chip">'+escapeHtml(s)+'</span>').join('')}</td>
          <td style="white-space:nowrap">
            <button class="btn btn-sm btn-ghost" onclick="selectAgent('${id}')" title="查看">查看</button>
            <button class="btn btn-sm btn-ghost" onclick="editAgentFromList('${id}')" title="编辑">✏️ 编辑</button>
            <button class="btn btn-sm btn-ghost" onclick="deleteAgentFromList('${id}','${nm.replace(/'/g,'&#39;')}')" title="删除" style="color:var(--pink)">🗑️ 删除</button>
          </td>
        </tr>`;
      });
    }
    if(!tbody.innerHTML)tbody.innerHTML='<tr><td colspan="5" style="color:var(--dim)">暂无</td></tr>';
    _ovTimer=setInterval(()=>{
      if(document.hidden||!document.querySelector('#view-overview:not(.hidden)')){
        clearInterval(_ovTimer);
        _ovTimer=null;
        return;
      }
      loadOverview();
    },10000);
    loadEvolution(ov?.evolution?.compliance_rating||null);
  }
}

/** 仪表盘区块按作用域切换：平台态只留对比矩阵，团队态留拓扑/成员/预算/痕迹。 */
function _setOverviewSections(platform){
  const show=(id,on)=>{const e=el(id);if(e)e.classList.toggle('hidden',!on)};
  show('ov-platform-section',platform);
  ['ov-topology-section','ov-team-section','budget-section','trace-section','evo-section']
    .forEach(id=>show(id,!platform));
}

/** 平台总览：跨团队对比矩阵 + 平台设施状态。 */
async function loadPlatformOverview(){
  _setOverviewSections(true);
  const [teams,ov]=await Promise.all([getTeamsList(),api(`${AT}/overview`)]);
  const allTeams=(teams||[]).filter(Boolean);
  const sh=ov?.scheduler||{};
  const ev=ov?.evolution||{};
  const totalAgents=allTeams.reduce((n,t)=>n+(Number(t?.agent_count)||0),0);
  const totalModels=allTeams.reduce((n,t)=>n+(Number(t?.model_count)||0),0);

  el('ov-stats').innerHTML=`
    <div class="stat-card"><div class="label">🏢 团队</div><div class="value">${allTeams.length}</div><div class="sub">平台内已注册</div></div>
    <div class="stat-card"><div class="label">🤖 智能体</div><div class="value">${totalAgents}</div><div class="sub">全部团队合计</div></div>
    <div class="stat-card"><div class="label">📦 模型槽</div><div class="value">${totalModels}</div><div class="sub">全部团队合计</div></div>
    <div class="stat-card"><div class="label">📊 调度器</div><div class="value" style="font-size:16px;color:${sh.running?'var(--lime)':'var(--red)'}">${sh.running?'运行中':'已停止'}</div><div class="sub">Tick ${sh.tick_count??0} · 运行 ${Math.round((sh.uptime_seconds||0)/60)}m</div></div>
    <div class="stat-card"><div class="label">🔄 自我演进</div><div class="value">${ev?.evolution_items_count??'-'}</div><div class="sub">规则 ${ev?.audit_rules_count??0}</div></div>`;

  const icons={'build_system':'🏗️','energy_first_principle':'⚡','ai_coding':'💻','d083a568':'☁️'};
  const tb=el('ov-team-matrix');
  if(!allTeams.length){
    tb.innerHTML='<tr><td colspan="8" style="color:var(--dim);text-align:center;padding:24px">暂无团队 — 可「＋ 新建团队」或「⬇ 导入外部团队」</td></tr>';
  }else{
    const rows=await Promise.all(allTeams.map(async t=>{
      const d=await api(`${A}/teams/${encodeURIComponent(t.team_id)}`);
      const tk=d?.tasks||{};
      const by=tk.by_status||{};
      return{t,running:by.running||0,total:tk.total||0};
    }));
    tb.innerHTML=rows.map(({t,running,total})=>{
      const ic=icons[t.team_id]||'🤖';
      const id=escapeHtml(t.team_id);
      return`<tr class="ov-matrix-row" onclick="focusTeam('${id}')">
        <td><input type="checkbox" class="ov-team-cb" value="${id}" onclick="event.stopPropagation()" style="width:auto;margin:0;cursor:pointer" title="勾选后可批量删除"></td>
        <td><b>${ic} ${escapeHtml(t.name||t.team_id)}</b></td>
        <td>${t.agent_count??0}</td>
        <td>${t.model_count??0}</td>
        <td>${running?`<span class="st st-working">${running}</span>`:'<span style="color:var(--dim)">0</span>'}</td>
        <td>${total}</td>
        <td style="color:var(--muted)">${escapeHtml((t.description||'').slice(0,40))||'—'}</td>
        <td style="white-space:nowrap"><button class="btn btn-sm btn-ghost" onclick="event.stopPropagation();focusTeam('${id}')">进入 →</button></td>
      </tr>`;
    }).join('');
  }
  _ovTimer=setInterval(()=>{
    if(document.hidden||!document.querySelector('#view-overview:not(.hidden)')||!isPlatformScope()){
      clearInterval(_ovTimer);_ovTimer=null;return;
    }
    loadPlatformOverview();
  },15000);
}

/** 从平台矩阵进入某团队作用域。 */
function focusTeam(id){
  tid=id;
  const s=el('team-select');if(s)s.value=id;
  if(typeof toggleTopologyEditMode==='function')toggleTopologyEditMode(false);
  switchView('overview');
  loadSbAgents();
}
window.focusTeam=focusTeam;

// ── 导入外部智能体团队 ──
let _itMode='json';

function setImportTeamMode(m){
  _itMode=m;
  el('it-mode-json').classList.toggle('selected',m==='json');
  el('it-mode-openclaw').classList.toggle('selected',m==='openclaw');
  el('it-mode-json').style.borderColor=m==='json'?'var(--shu)':'var(--line)';
  el('it-mode-openclaw').style.borderColor=m==='openclaw'?'var(--shu)':'var(--line)';
  el('it-openclaw-fields').style.display=m==='openclaw'?'block':'none';
}
window.setImportTeamMode=setImportTeamMode;

function openImportTeamModal(){
  ['it-name','it-desc','it-url','it-token','it-agents'].forEach(id=>{const e=el(id);if(e)e.value=''});
  const f=el('it-file');if(f)f.value='';
  const p=el('it-preview');if(p){p.style.display='none';p.innerHTML=''}
  setImportTeamMode('json');
  openModal('modal-import-team');
}
window.openImportTeamModal=openImportTeamModal;

/** 解析用户输入：接受完整团队包或纯成员数组。 */
function _parseTeamBundle(raw){
  const data=JSON.parse(raw);
  if(Array.isArray(data))return{agents:data,models:[]};
  if(data&&typeof data==='object'){
    if(!Array.isArray(data.agents))throw new Error('缺少 agents 数组');
    return{name:data.name,description:data.description,agents:data.agents,models:Array.isArray(data.models)?data.models:[]};
  }
  throw new Error('格式无法识别');
}

function loadImportTeamFile(input){
  const file=input.files&&input.files[0];
  if(!file)return;
  if(file.size>2*1024*1024){toast('文件过大（上限 2MB）','error');input.value='';return}
  const rd=new FileReader();
  rd.onload=()=>{
    try{
      const b=_parseTeamBundle(String(rd.result));
      el('it-agents').value=JSON.stringify(b.agents,null,2);
      if(b.name&&!el('it-name').value)el('it-name').value=b.name;
      if(b.description&&!el('it-desc').value)el('it-desc').value=b.description;
      const p=el('it-preview');
      p.style.display='block';
      p.innerHTML=`✅ 已解析：<b>${b.agents.length}</b> 个成员 · <b>${(b.models||[]).length}</b> 个模型`;
    }catch(e){
      toast('JSON 解析失败: '+e.message,'error');
      input.value='';
    }
  };
  rd.readAsText(file);
}
window.loadImportTeamFile=loadImportTeamFile;

async function submitImportTeam(){
  const name=el('it-name').value.trim();
  if(!name){toast('团队名称不能为空','error');return}
  const rawAgents=el('it-agents').value.trim();
  if(!rawAgents){toast('请提供成员清单','error');return}
  let bundle;
  try{bundle=_parseTeamBundle(rawAgents)}
  catch(e){toast('成员清单解析失败: '+e.message,'error');return}
  if(!bundle.agents.length){toast('团队至少需要一个成员','error');return}

  const url=el('it-url').value.trim();
  if(_itMode==='openclaw'&&!url){toast('请输入 OpenClaw Gateway URL','error');return}

  const btn=el('btn-import-team');
  btn.disabled=true;btn.textContent='导入中…';
  try{
    const payload={
      name,
      description:el('it-desc').value.trim(),
      source:_itMode,
      openclaw_url:_itMode==='openclaw'?url:'',
      openclaw_token:_itMode==='openclaw'?el('it-token').value:'',
      agents:bundle.agents.map(a=>({
        name:String(a.name||'').trim(),
        role:String(a.role||''),
        description:String(a.description||''),
        model_id:String(a.model_id||a.model||''),
        system_prompt:String(a.system_prompt||''),
        tools:Array.isArray(a.tools)?a.tools.map(String):[],
        skills:Array.isArray(a.skills)?a.skills.map(String):[],
        openclaw_agent_id:String(a.openclaw_agent_id||a.agent_id||''),
      })),
      models:(bundle.models||[]).map(m=>({
        provider:String(m.provider||'anthropic'),
        name:String(m.name||''),
        max_tokens:Number(m.max_tokens)||8192,
        temperature:Number(m.temperature)??0.7,
        api_base_url:String(m.api_base_url||''),
      })).filter(m=>m.name),
    };
    if(payload.agents.some(a=>!a.name)){toast('存在没有 name 的成员','error');return}

    const res=await api(`${A}/teams/import`,{method:'POST',body:JSON.stringify(payload)});
    if(!res||!res.report){
      const err=api._lastError;
      toast('导入失败'+(err?.message?`: ${err.message}`:''),'error');
      return;
    }
    const r=res.report;
    closeModal('modal-import-team');
    toast(`已导入「${r.name}」· ${r.agents_imported} 成员 / ${r.models_imported} 模型`,'success');
    if(r.renamed)toast(`存在同名团队，已重命名为「${r.name}」`);
    (r.warnings||[]).forEach(w=>toast(w));
    _teamsListCache=null;
    await loadTeams();
    focusTeam(r.team_id);
  }finally{
    btn.disabled=false;btn.textContent='导入团队';
  }
}
window.submitImportTeam=submitImportTeam;

// ── System Evolution (自我演进) ──
const EVP='/api/v1/agent-teams/evolution';
const EVO_ITEMS_PAGE_SIZE=50;
let evoVisibleCount=EVO_ITEMS_PAGE_SIZE;
let evoCachedItems=[];

async function loadEvolution(prefetchedCompliance=null){
  const statusFilter=el('evo-filter')?.value||'';
  const itemsUrl=statusFilter?`${EVP}/items?status=${statusFilter}`:`${EVP}/items`;
  const rs=el('evo-rules'),is=el('evo-items'),sc=el('evo-stats'),cc=el('evo-compliance');
  const needsDetailedData=Boolean(rs||is||sc);
  const complianceReq=prefetchedCompliance?Promise.resolve(prefetchedCompliance):api(`${EVP}/compliance-rating`);
  const [rules,items,summary,compliance]=needsDetailedData
    ? await Promise.all([
        api(`${EVP}/rules`),
        api(itemsUrl),
        api(`${EVP}/summary`),
        complianceReq
      ])
    : [null,null,null,await complianceReq];

  // Compliance Rating Card
  if(compliance&&cc){
    const grade=compliance.grade||'?';
    const score=compliance.score??0;
    const gradeColor={A:'var(--lime)',B:'var(--koke)',C:'var(--amber)',D:'var(--kitsune)',E:'var(--red)'}[grade]||'var(--muted)';
    cc.innerHTML=`<div class="stat-card" style="grid-column:span 2"><div style="display:flex;align-items:center;gap:20px"><div style="position:relative;width:64px;height:64px"><svg viewBox="0 0 36 36" style="width:64px;height:64px;transform:rotate(-90deg)"><circle cx="18" cy="18" r="16" fill="none" stroke="var(--groove)" stroke-width="3"/><circle cx="18" cy="18" r="16" fill="none" stroke="${gradeColor}" stroke-width="3" stroke-dasharray="${score} ${100-score}" stroke-linecap="round"/></svg><div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:900;color:${gradeColor};font-family:var(--font-mono)">${grade}</div></div><div><div class="label">合规评级</div><div class="value" style="font-size:18px;color:${gradeColor}">${score}/100</div><div class="sub">${compliance.description||'系统合规状态'}</div></div></div></div>`;
  }

  // Stats
  if(summary&&sc){
    const bs=summary.by_status||{};const bd=summary.by_domain||{};
    sc.innerHTML=`<div class="stat-card"><div class="label">📋 规则</div><div class="value">${summary.audit_rules_count||0}</div><div class="sub">验证函数 ${summary.verify_tests_registered||0}</div></div><div class="stat-card"><div class="label">🔍 演进项</div><div class="value">${summary.total_items||0}</div><div class="sub">${Object.entries(bs).map(([k,v])=>evoStL(k)+': '+v).join(' · ')||'无'}</div></div><div class="stat-card"><div class="label">📚 域分布</div><div class="value" style="font-size:13px">${Object.entries(bd).map(([k,v])=>k+' '+v).join(' · ')||'-'}</div></div>`;
  }

  if(!needsDetailedData){
    return;
  }

  // Active Zones
  loadEvoZones();

  // Rules — filter by selected team
  const isEnergy=(tid==='energy_first_principle');
  const filteredRules=(rules||[]).filter(r=>isEnergy?r.domain==='Datacenter':r.domain!=='Datacenter');
  if(rs&&filteredRules.length){
    rs.innerHTML=`<div style="font-size:13px;font-weight:600;margin-bottom:8px;color:var(--muted)">审查规则 (${filteredRules.length})</div><div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:8px">${filteredRules.map(r=>`<div style="padding:10px 14px;background:var(--panel2);border:1px solid var(--line);border-radius:0"><div style="display:flex;justify-content:space-between;align-items:center"><b style="font-size:12px">${escapeHtml(r.id)}</b><span class="chip" style="font-size:10px">${escapeHtml(r.domain)}</span></div><div style="font-size:12px;margin-top:4px;color:var(--text)">${escapeHtml(r.title)}</div><div style="font-size:11px;color:var(--dim);margin-top:2px">${escapeHtml(r.reference||'')}</div><div style="font-size:11px;margin-top:2px"><span style="color:${r.severity==='critical'?'var(--red)':r.severity==='high'?'var(--amber)':'var(--muted)'}">${escapeHtml(r.severity)}</span> · ${escapeHtml(r.target_channel)}</div></div>`).join('')}</div>`;
  } else if(rs) { rs.innerHTML='<div style="color:var(--dim);font-size:12px">暂无审查规则</div>'; }

  // Items with action buttons
  evoCachedItems=items||[];
  evoVisibleCount=EVO_ITEMS_PAGE_SIZE;
  renderEvolutionItems();
}

function renderEvolutionItems(){
  const is=el('evo-items');
  if(!is)return;
  if(!evoCachedItems.length){
    is.innerHTML='<div style="color:var(--dim);font-size:12px;padding:8px">暂无演进条目 — 点击「审查」或「运行演进周期」开始</div>';
    return;
  }
  const shown=evoCachedItems.slice(0,evoVisibleCount);
  const remaining=Math.max(0,evoCachedItems.length-shown.length);
  is.innerHTML=`<div style="font-size:13px;font-weight:600;margin-bottom:8px;color:var(--muted)">演进条目 (${evoCachedItems.length}${remaining>0?' · 显示前'+shown.length+'条':''})</div><table class="tbl"><thead><tr><th>ID</th><th>标题</th><th>域</th><th>严重度</th><th>状态</th><th>目标</th><th>操作</th></tr></thead><tbody>${shown.map(i=>`<tr><td style="font-family:var(--font-mono);font-size:11px">${escapeHtml(i.id?.slice(0,8)||'')}</td><td><b>${escapeHtml(i.title)}</b></td><td><span class="chip" style="font-size:10px">${escapeHtml(i.audit_domain||'')}</span></td><td style="color:${i.severity==='critical'?'var(--red)':i.severity==='high'?'var(--amber)':'var(--muted)'}">${escapeHtml(i.severity||'')}</td><td>${evoStBadge(i.status)}</td><td style="font-size:12px">${escapeHtml(i.target_channel||'')}</td><td style="white-space:nowrap">${evoItemActions(i)}</td></tr>`).join('')}</tbody></table>${remaining>0?`<button class="btn btn-sm" style="margin-top:8px" onclick="evoLoadMore()">加载更多 (${remaining} 剩余)</button>`:''}`;
}

function evoLoadMore(){
  evoVisibleCount+=EVO_ITEMS_PAGE_SIZE;
  renderEvolutionItems();
}

function evoItemActions(item){
  const s=item.status;
  if(s==='discovered')return `<button class="btn btn-sm" style="padding:2px 8px;font-size:11px" onclick="evoMarkProgress('${item.id}')">开始</button>`;
  if(s==='in_progress')return `<button class="btn btn-sm" style="padding:2px 8px;font-size:11px" onclick="evoMarkComplete('${item.id}')">完成</button>`;
  if(s==='verify_pending')return `<span style="font-size:11px;color:var(--amber)">待验证</span>`;
  if(s==='verified')return `<span style="font-size:11px;color:var(--lime)">✓</span>`;
  if(s==='failed')return `<span style="font-size:11px;color:var(--red)">✗</span>`;
  return '—';
}

async function evoMarkProgress(itemId){
  const r=await api(`${EVP}/items/${itemId}/progress`,{method:'POST'});
  if(r){toast('已标记为进行中');loadEvolution()}else toast('操作失败')
}
async function evoMarkComplete(itemId){
  const r=await api(`${EVP}/items/${itemId}/complete`,{method:'POST'});
  if(r){toast('已标记完成，等待验证');loadEvolution()}else toast('操作失败')
}

async function loadEvoZones(){
  const zc=el('evo-zones');if(!zc)return;
  const zones=await api(`${EVP}/zones/active`);
  if(!zones||!zones.length){zc.innerHTML='';return}
  zc.innerHTML=`<div style="font-size:13px;font-weight:600;margin-bottom:8px;color:var(--muted)">活跃合规区域</div><div style="display:flex;gap:8px;flex-wrap:wrap">${zones.map(z=>`<div class="chip" style="padding:6px 12px"><b>${escapeHtml(z.name||z.zone_id||'')}</b>${z.standards?` · ${z.standards.length} 标准`:''}</div>`).join('')}</div>`;
}

function evoStL(s){return{discovered:'发现',dispatched:'已派发',in_progress:'进行中',verify_pending:'待验证',verified:'已验证',failed:'失败',closed:'已关闭'}[s]||s}
function evoStBadge(s){const c={discovered:'var(--cyan)',dispatched:'var(--amber)',in_progress:'var(--cyan-s)',verify_pending:'var(--pink)',verified:'var(--lime)',failed:'var(--red)',closed:'var(--dim)'}[s]||'var(--muted)';return `<span style="color:${c};font-weight:600;font-size:12px">${evoStL(s)}</span>`}

async function runEvoAudit(){
  toast('正在运行审查...');
  const r=await api(`${EVP}/audit`,{method:'POST'});
  if(r){toast(`审查完成: ${r.passed||0} 通过, ${r.failed||0} 未通过`);loadEvolution()}else toast('审查失败')
}

// Evolution Cycle Stepper — visual 4-step progress
async function runEvoCycleStepper(){
  const stepper=el('evo-stepper');const log=el('evo-stepper-log');
  stepper.classList.remove('hidden');
  const steps=['audit','dispatch','verify','close'];
  const stepNames=['审查','派发','验证','关闭'];
  // Reset all dots
  steps.forEach(s=>{const d=el('es-'+s);d.className='wf-dot'});
  ['es-c1','es-c2','es-c3'].forEach(id=>{const c=el(id);if(c)c.className='wf-connector'});
  log.innerHTML='';

  for(let i=0;i<steps.length;i++){
    const dotEl=el('es-'+steps[i]);
    dotEl.classList.add('wf-active');
    log.innerHTML+=`<div>⏳ ${stepNames[i]}...</div>`;
    const r=await api(`${EVP}/${steps[i]}`,{method:'POST'});
    dotEl.classList.remove('wf-active');
    if(r){
      dotEl.classList.add('wf-completed');
      const count=r.count||r.passed||r.dispatched||(r.closed||[]).length||0;
      log.innerHTML+=`<div style="color:var(--lime)">✓ ${stepNames[i]}完成 (${count})</div>`;
    }else{
      dotEl.classList.add('wf-failed');
      log.innerHTML+=`<div style="color:var(--red)">✗ ${stepNames[i]}失败</div>`;
      break;
    }
    // Mark connector as done
    if(i<3){const c=el('es-c'+(i+1));if(c)c.classList.add('wf-done')}
  }
  toast('演进周期完成');
  loadEvolution();
}

// Keep backward compat
async function runEvoCycle(){runEvoCycleStepper()}

// ── LLM Config ──
async function loadLLMStatus(){
  const st=await api(`${A}/llm/status`);
  const prov=await api(`${A}/llm/provider`);
  const card=el('llm-status-card');
  if(!st||!prov){card.innerHTML='<p style="color:var(--pink)">⚠️ 无法获取 LLM 状态，请确认后端已启动</p>';return}
  const keyStatus=prov.has_api_key?'<span style="color:var(--lime)">✅ 已配置</span>':'<span style="color:var(--pink)">❌ 未配置</span>';
  card.innerHTML=`
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px">
      <div class="stat-card"><div class="label">提供商</div><div class="value">${escapeHtml(prov.provider)}</div></div>
      <div class="stat-card"><div class="label">模型</div><div class="value" style="font-size:14px">${escapeHtml(prov.model)}</div></div>
      <div class="stat-card"><div class="label">API Key</div><div class="value" style="font-size:14px">${keyStatus}</div><div class="sub">${prov.api_key_preview||''}</div></div>
      <div class="stat-card"><div class="label">Base URL</div><div class="value" style="font-size:11px;word-break:break-all">${escapeHtml(prov.base_url)}</div></div>
      <div class="stat-card"><div class="label">总调用</div><div class="value">${st.total_calls??0}</div></div>
      <div class="stat-card"><div class="label">总 Tokens</div><div class="value">${(st.total_tokens||0).toLocaleString()}</div></div>
      <div class="stat-card"><div class="label">活跃会话</div><div class="value">${st.active_sessions??0}</div></div>
      <div class="stat-card"><div class="label">错误数</div><div class="value" style="color:${(st.errors||0)>0?'var(--pink)':'var(--lime)'}">${st.errors??0}</div></div>
    </div>`;
  // Fill form with current values
  el('llm-provider').value=prov.provider||'deepseek';
  el('llm-model').value=prov.model||'';
  el('llm-url').value=prov.base_url||'';
  el('llm-tokens').value=prov.max_tokens||4096;
  el('llm-temp').value=prov.temperature||0.7;
  // Load sessions
  const sessions=await api(`${A}/llm/sessions`);
  const sc=el('llm-sessions');
  if(!sessions||!sessions.length){sc.innerHTML='<p style="color:var(--dim)">暂无活跃会话</p>';return}
  sc.innerHTML='<table class="tbl"><thead><tr><th>会话 ID</th><th>Agent</th><th>轮次</th><th>消息数</th><th>Tokens</th><th>创建时间</th></tr></thead><tbody>'+sessions.map(s=>`<tr><td>${escapeHtml(s.session_id)}</td><td>${escapeHtml(s.agent_id||'-')}</td><td>${s.turn_count}</td><td>${s.message_count}</td><td>${(s.usage?.total_tokens||0).toLocaleString()}</td><td>${s.created_at?.split('T')[0]||'-'}</td></tr>`).join('')+'</tbody></table>';
}
async function saveLLMConfig(){
  const body={provider:el('llm-provider').value,model:el('llm-model').value,api_key:el('llm-key').value,api_base_url:el('llm-url').value,max_tokens:parseInt(el('llm-tokens').value)||4096,temperature:parseFloat(el('llm-temp').value)||0.7};
  const r=await api(`${A}/llm/provider`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r){toast('LLM 配置已保存');el('llm-key').value='';loadLLMStatus()}else toast('保存失败')
}
async function testLLM(){
  const rc=el('llm-test-result');rc.classList.remove('hidden');
  el('llm-test-content').innerHTML='<p style="color:var(--dim)">正在测试<strong>全局默认</strong> LLM 连接（非单条模型编辑）...</p>';
  const r=await api(`${A}/llm/test`,{method:'POST'});
  if(!r){el('llm-test-content').innerHTML='<p style="color:var(--pink)">请求失败，请检查后端</p>';return}
  const meta=`<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px;margin-top:8px">
    <div><b>实际模型:</b> ${escapeHtml(r.model||r.requested_model||'—')}</div>
    <div><b>提供商:</b> ${escapeHtml(r.provider||'—')}</div>
    <div style="grid-column:1/-1"><b>Base URL:</b> <code style="word-break:break-all">${escapeHtml(r.base_url||'—')}</code></div>
    <div><b>延迟:</b> ${r.latency_ms!=null?Number(r.latency_ms).toFixed(0)+'ms':'—'}</div>
    <div><b>范围:</b> 全局默认 (scope=${escapeHtml(r.scope||'global')})</div>
  </div>`;
  if(r.success){
    el('llm-test-content').innerHTML=`<div style="color:var(--lime);margin-bottom:8px">✅ 连接成功！</div>${meta}<div style="margin-top:12px;padding:12px;background:rgba(232,240,250,0.7);border-radius:0;font-size:13px;color:var(--text)">${escapeHtml(r.response)}</div>`;
  } else {
    el('llm-test-content').innerHTML=`<div style="color:var(--pink);margin-bottom:8px">❌ 连接失败</div>
      ${meta}
      <div style="margin-top:10px;padding:12px;background:rgba(224,27,36,0.06);border-radius:0;font-size:12px;color:var(--red);word-break:break-all">${escapeHtml(r.error||'未知错误')}</div>
      ${r.response?`<div style="margin-top:10px;padding:12px;background:rgba(232,240,250,0.7);border-radius:0;font-size:13px;color:var(--text)">${escapeHtml(r.response)}</div>`:''}
      <div style="margin-top:12px;color:var(--muted);font-size:12px;line-height:1.55">💡 ${escapeHtml(r.tip||'本按钮测的是全局默认模型。若你刚在某条模型里改了 Key/URL，请打开该模型编辑弹窗点「测试连接」，并确认「模型名称」是上游真实 id（例如 qwen27b-…），而不是 deepseek-v4-flash。')}</div>`;
  }
}

// ── Models ──
let _editModelId='';
async function loadModels(){
  const [d,gm] = await Promise.all([
    api(`${A}/teams/${tid}/models`),
    api(`${A}/llm/global-model`)
  ]);
  const tb=el('models-tb');
  // 全局模型信息
  const gmMeta = (gm && gm.enabled && gm.current) ? gm.current : null;
  const gmTeamId = gmMeta ? gmMeta.team_id : '';
  const gmModelId = gmMeta ? gmMeta.model_id : '';
  const gmName = gmMeta ? (gmMeta.name || gmModelId) : '';
  // 判断全局模型是否属于当前团队
  const gmInThisTeam = gmMeta && gmTeamId === tid;

  // 顶部 banner：明确「全局已启用 / 未启用」
  const banner = el('global-model-banner');
  if (banner) {
    if (gmMeta) {
      const where = gmInThisTeam ? '本团队' : `团队 ${escapeHtml(gmTeamId)}`;
      banner.innerHTML =
        `<span style="color:var(--lime,#26a269);font-weight:600">✅ 全局 LLM 已启用</span>` +
        ` · 模型 <b>${escapeHtml(gmName)}</b>（${where} · id=${escapeHtml(gmModelId)}）` +
        ` · <span style="color:var(--muted)">演练/广场/萃取/任务等全部只走此连接；model_route 与团队槽不再生效</span>` +
        ` · <button class="btn btn-sm" style="padding:2px 8px;font-size:11px;margin-left:6px" onclick="clearGlobalDefault()">取消全局</button>`;
      banner.style.background = 'rgba(38,162,105,0.08)';
      banner.style.borderColor = 'rgba(38,162,105,0.35)';
    } else {
      banner.innerHTML =
        `<span style="color:var(--amber,#f59e0b);font-weight:600">⚠️ 未设置全局 LLM</span>` +
        ` · 请在下表点 <b>🌐 全局默认</b> 提升一个已保存密钥的模型；` +
        `启用后演练/广场/任务等只使用该连接。`;
      banner.style.background = 'rgba(245,158,11,0.06)';
      banner.style.borderColor = 'var(--line)';
    }
  }

  let rows = (d||[]).map(m=>{
    const mid=m.model_id;
    const isGlobal = gmInThisTeam && gmModelId === mid;
    const defaultBadge = isGlobal
      ? '<span style="color:var(--cyan-s,#22d3ee)">🌐 全局默认</span>'
      : m.is_default
        ? '<span style="color:var(--lime)">✓ 团队默认</span>'
        : `<button class="btn btn-sm" style="padding:2px 8px;font-size:11px" onclick="setModelDefault('${mid}')">设为默认</button>`;
    const globalBtn = isGlobal
      ? `<button class="btn btn-sm" style="padding:2px 8px;font-size:11px;color:var(--amber,#f59e0b)" onclick="clearGlobalDefault()" title="取消全局默认">🌐 取消全局</button>`
      : `<button class="btn btn-sm" style="padding:2px 8px;font-size:11px;color:var(--cyan-s,#22d3ee)" onclick="setModelGlobalDefault('${mid}')" title="提升为全局默认 provider">🌐 全局默认</button>`;
    return `<tr><td><b>${escapeHtml(mid)}</b></td><td>${escapeHtml(m.name)}</td><td>${escapeHtml(m.provider)}</td><td>${m.max_tokens.toLocaleString()}</td><td>${m.temperature}</td><td>${defaultBadge}</td><td style="display:flex;gap:6px">${globalBtn}<button class="btn btn-sm" style="padding:2px 8px;font-size:11px" onclick="openEditModel('${mid}')">编辑</button><button class="btn btn-danger btn-sm" onclick="delModel('${mid}')">删除</button></td></tr>`;
  });

  // 如果全局模型属于其他团队，追加一行展示
  if (gmMeta && !gmInThisTeam) {
    rows.push(
      `<tr style="background:rgba(34,211,238,0.04)"><td><b style="color:var(--cyan-s,#22d3ee)">${escapeHtml(gmModelId)}</b> <span style="font-size:9px;color:var(--dim)">(${escapeHtml(gmTeamId)})</span></td><td>${escapeHtml(gmName)}</td><td colspan="2" style="color:var(--dim)">— 来自其他团队 —</td><td>—</td><td><span style="color:var(--cyan-s,#22d3ee)">🌐 全局默认</span></td><td><button class="btn btn-sm" style="padding:2px 8px;font-size:11px;color:var(--amber,#f59e0b)" onclick="clearGlobalDefault()" title="取消全局默认">🌐 取消全局</button></td></tr>`
    );
  }

  if(!rows.length){
    tb.innerHTML='<tr><td colspan="7" style="color:var(--dim)">暂无模型 — 点击右上角「+ 添加模型」</td></tr>';
    return;
  }
  tb.innerHTML = rows.join('');
}
async function delModel(mid){if(!confirm('删除此模型？'))return;await fetch(`${A}/teams/${tid}/models/${mid}`,{method:'DELETE'});toast('已删除');loadModels()}
async function setModelDefault(mid){
  const r=await api(`${A}/teams/${tid}/models/${mid}/default`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({})});
  if(r){toast(`模型 ${mid} 已设为默认，所有智能体已同步`);loadModels();loadSbAgents();if(aid)loadAgent()}else toast('设置失败')
}
async function setModelGlobalDefault(mid){
  if(!confirm('将此模型（连同服务端已存密钥）提升为【全局 LLM】？\n\n启用后：演练 / 广场 / 萃取 / 任务 / tool_loop 等全部只走此连接；\nmodel_route、团队模型槽、其它 override 均不再生效。'))return;
  const r=await api(`${A}/teams/${tid}/models/${mid}/set-global-default`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})});
  if(r&&r.promoted){toast(`🌐 全局 LLM 已启用: ${r.provider}/${r.model}（key 尾号 ${r.api_key_tail}）`);loadModels()}
  else{const d=window.api?._lastError?.message||'';toast('提升失败'+(d?'：'+d:''))}
}
window.setModelGlobalDefault=setModelGlobalDefault;
async function clearGlobalDefault(){
  if(!confirm('取消全局默认模型？\n取消后各团队将回退到自己的默认模型。'))return;
  const r=await api(`${A}/llm/global-model`,{method:'DELETE'});
  if(r&&!r.enabled){toast('已取消全局默认模型');loadModels()}
  else{toast('取消失败')}
}
window.clearGlobalDefault=clearGlobalDefault;
async function openEditModel(mid){
  _editModelId=mid;
  const models=await api(`${A}/teams/${tid}/models`);
  const m=(models||[]).find(x=>x.model_id===mid);if(!m){toast('模型未找到');return}
  el('em-prov').value=m.provider||'deepseek';
  el('em-name').value=m.name||'';
  el('em-tok').value=m.max_tokens||8192;
  el('em-temp').value=m.temperature??0.7;
  // 密钥回填优先级: env: 引用(后端存的) > 浏览器记住的明文 key
  const remembered=_rememberedKey(tid,mid);
  if(m.api_key && String(m.api_key).startsWith('env:')){
    el('em-key').value=m.api_key;
    if(el('em-remember'))el('em-remember').checked=false;
  }else if(remembered){
    el('em-key').value=remembered;
    if(el('em-remember'))el('em-remember').checked=true;
  }else{
    el('em-key').value='';
    if(el('em-remember'))el('em-remember').checked=false;
  }
  el('em-url').value=m.api_base_url||'';
  el('em-def').value=m.is_default?'true':'false';
  el('em-title').textContent=`✏️ 编辑模型 — ${mid}`;
  el('em-test-result').classList.add('hidden');
  updateEmUrlHint();
  openModal('modal-edit-model');
}

// ── 「记住密钥」浏览器持久化（localStorage 按 team+model 存取）──
// bug-034/038 修复的真正落地：勾选框把明文 key 存到本浏览器，重启后端后
// openEditModel 自动回填并勾选；test/save 用 _effectiveKey 取「输入框→记住的key」。
function _rememberKeyStorageKey(teamId,modelId){return `ag_model_key:${teamId}:${modelId}`}
function _rememberedKey(teamId,modelId){
  try{return localStorage.getItem(_rememberKeyStorageKey(teamId,modelId))||''}catch(e){return ''}
}
function _setRememberedKey(teamId,modelId,key){
  try{
    if(key)localStorage.setItem(_rememberKeyStorageKey(teamId,modelId),key);
    else localStorage.removeItem(_rememberKeyStorageKey(teamId,modelId));
  }catch(e){/* 隐私模式/禁用 localStorage 时静默降级 */}
}
// 有效密钥: 输入框非空则用输入框; 否则回退到记住的 key(即使字段留空也能测/存)
function _effectiveKey(teamId,modelId){
  const typed=(el('em-key')&&el('em-key').value||'').trim();
  if(typed)return typed;
  return _rememberedKey(teamId,modelId);
}
// 按当前勾选框状态同步 localStorage: 勾选写入, 取消清除
function _syncRememberKey(teamId,modelId){
  const remember=el('em-remember')&&el('em-remember').checked;
  const typed=(el('em-key')&&el('em-key').value||'').trim();
  // 只记明文 key; env: 引用无需记(后端已存), 留空且已记过则保留原记忆
  if(remember && typed && !typed.startsWith('env:')){
    _setRememberedKey(teamId,modelId,typed);
  }else if(!remember){
    _setRememberedKey(teamId,modelId,'');
  }
}
const _providerDefaultUrls={deepseek:'https://api.deepseek.com',openai:'https://api.openai.com/v1',anthropic:'https://api.anthropic.com/v1',github:'https://models.inference.ai.azure.com',qwen:'https://dashscope.aliyuncs.com/compatible-mode/v1',openrouter:'https://openrouter.ai/api/v1',local:'http://127.0.0.1:11434/v1'};
function updateEmUrlHint(){
  const prov=el('em-prov').value;
  const defaultUrl=_providerDefaultUrls[prov]||'';
  const urlInput=el('em-url');
  urlInput.placeholder=defaultUrl||'输入自定义 Base URL';
  const hint=el('em-url-hint');
  if(hint){
    if(urlInput.value){hint.textContent=`自定义 URL（默认: ${defaultUrl}）`}
    else{hint.textContent=`当前使用默认: ${defaultUrl}`}
  }
}
async function submitEditModel(){
  if(!_editModelId)return;
  // 先按勾选框同步浏览器记忆，再用有效密钥(输入框→记住的key)提交
  _syncRememberKey(tid,_editModelId);
  const body={provider:el('em-prov').value,name:el('em-name').value.trim(),max_tokens:parseInt(el('em-tok').value)||8192,temperature:parseFloat(el('em-temp').value)||0.7,is_default:el('em-def').value==='true',api_key:_effectiveKey(tid,_editModelId),api_base_url:el('em-url').value};
  if(!body.name){toast('模型名称不能为空');return}
  const r=await api(`${A}/teams/${tid}/models/${_editModelId}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r){toast('模型已更新');closeModal('modal-edit-model');loadModels();if(body.is_default){loadSbAgents();if(aid)loadAgent()}}else toast('更新失败')
}
async function testModelInEdit(){
  const rb=el('em-test-result');rb.classList.remove('hidden');
  rb.style.background='rgba(232,240,250,0.7)';rb.style.color='var(--muted)';
  const modelName=(el('em-name').value||'').trim();
  const baseUrl=(el('em-url').value||'').trim();
  if(!modelName){
    rb.style.background='rgba(224,27,36,0.06)';rb.style.color='var(--red)';
    rb.innerHTML='❌ 模型名称为空 — 请填写上游真实模型 ID（例如 <code>qwen27b-abliterated-Fable-MTP</code>），不要留空或沿用 deepseek-v4-flash';
    return;
  }
  rb.innerHTML=`⏳ 正在测试 <b>${escapeHtml(modelName)}</b> @ <code style="font-size:11px">${escapeHtml(baseUrl||'(默认 base)')}</code> …`;
  const btn=el('em-test-btn');btn.disabled=true;
  // 测试前先按勾选框同步记忆，并用有效密钥(输入框→记住的key)发请求，留空也能用已记密钥测
  _syncRememberKey(tid,_editModelId);
  const body={provider:el('em-prov').value,name:modelName,api_key:_effectiveKey(tid,_editModelId),api_base_url:baseUrl,max_tokens:parseInt(el('em-tok').value)||8192,temperature:parseFloat(el('em-temp').value)||0.7,team_id:tid,model_id:_editModelId};
  const r=await api(`${A}/llm/test-model`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  btn.disabled=false;
  if(!r){rb.style.background='rgba(224,27,36,0.06)';rb.style.color='var(--red)';rb.innerHTML='❌ 请求失败，请检查后端是否运行';return}
  const sentModel=r.sent_model||r.model||modelName;
  const reqModel=r.requested_model||modelName;
  const routeWarn=(sentModel&&reqModel&&sentModel!==reqModel)
    ?`<div style="margin-top:4px;color:var(--warn,#A67C1A);font-size:11px">⚠ 编辑框「${escapeHtml(reqModel)}」与实际上游 model「${escapeHtml(sentModel)}」不一致（可能被 Token 治理路由改写）</div>`
    :'';
  const meta=`<div style="margin-top:6px;font-size:11px;color:var(--muted);line-height:1.5">编辑框 model=<code>${escapeHtml(reqModel)}</code> · 实际上游 model=<code>${escapeHtml(sentModel)}</code> · base=<code style="word-break:break-all">${escapeHtml(r.base_url||baseUrl||'—')}</code></div>${routeWarn}`;
  if(r.success){
    rb.style.background='rgba(38,162,105,0.08)';rb.style.color='var(--lime)';
    rb.innerHTML=`✅ 连接成功 — 模型: ${escapeHtml(sentModel)} · 延迟: ${Number(r.latency_ms||0).toFixed(0)}ms${meta}<div style="margin-top:8px;padding:10px;background:rgba(232,240,250,0.6);border-radius:6px;color:var(--text);font-size:12px">${escapeHtml(r.response)}</div>`;
    // Auto-save after successful test（body.api_key 已是 _effectiveKey 结果）
    if(_editModelId){
      const sb={provider:el('em-prov').value,name:modelName,max_tokens:parseInt(el('em-tok').value)||8192,temperature:parseFloat(el('em-temp').value)||0.7,is_default:el('em-def').value==='true',api_key:body.api_key,api_base_url:baseUrl};
      const sr=await api(`${A}/teams/${tid}/models/${_editModelId}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(sb)});
      if(sr){
        let saveNote='💾 配置已自动保存';
        if(sr.global_override_refreshed){
          saveNote+=' · 已同步到全局默认（广场/萃取将使用此连接）';
        }else{
          saveNote+=' · 若议事广场仍报 LLM 不可用，请点「设为全局默认」再试';
        }
        rb.innerHTML+=`<div style="margin-top:8px;color:var(--lime);font-size:12px">${saveNote}</div>`;
        loadModels();if(sb.is_default){loadSbAgents();if(aid)loadAgent()}
      }
    }
  } else {
    rb.style.background='rgba(224,27,36,0.06)';rb.style.color='var(--red)';
    rb.innerHTML=`❌ 连接失败${meta}<div style="margin-top:6px;font-size:12px;word-break:break-all">${escapeHtml(r.error||'未知错误')}</div><div style="margin-top:8px;color:var(--muted);font-size:11px;line-height:1.55">💡 ${escapeHtml(r.tip||'请确认：模型名称=上游 id；Base URL 与 Key 属于同一分组；Key 已开通该模型。')}</div>`;
  }
}

// ── Tools (Clawith-style) ──
let _tcToolId='';
async function loadTools(){
  const[all,team]=await Promise.all([api(`${A}/tools`),api(`${A}/teams/${tid}/tools`)]);
  const en=new Set((team||[]).filter(t=>t.enabled!==false).map(t=>t.tool_id||t.id));const box=el('tools-cards');
  if(!all||!all.length){box.innerHTML='<p style="color:var(--dim)">暂无工具</p>';return}
  const cats={};all.forEach(t=>{const c=(t.category||'general').toUpperCase();if(!cats[c])cats[c]=[];cats[c].push(t)});
  let html='';Object.keys(cats).sort().forEach(cat=>{
    html+=`<div class="sb-section" style="margin-top:16px;margin-bottom:10px">${cat}</div>`;
    cats[cat].forEach(t=>{const on=en.has(t.tool_id);const hasCfg=t.config_schema&&Object.keys(t.config_schema).length;
      html+=`<div data-tool-name="${t.name}" style="display:flex;align-items:center;padding:14px 18px;background:var(--panel2,#21272D);border:1px solid var(--line);border-radius:0;margin-bottom:6px;gap:12px"><span style="font-size:22px;width:36px;text-align:center">${t.icon||'🔧'}</span><div style="flex:1;min-width:0"><div style="display:flex;align-items:center;gap:8px;margin-bottom:2px"><b style="font-size:13px;color:var(--text)">${t.name}</b><span class="chip" style="font-size:10px;padding:1px 6px">${t.source||'Built-in'}</span>${t.is_default?'<span class="chip" style="background:rgba(38,162,105,0.1);color:var(--lime);font-size:10px;padding:1px 6px">Default</span>':''}</div><div style="color:var(--muted);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${t.description||''}</div></div><div style="display:flex;align-items:center;gap:8px"><button class="btn btn-sm btn-ghost" onclick="testToolExec('${t.name}')" title="测试执行">▶</button>${hasCfg?`<button class="btn btn-sm btn-ghost" onclick="openToolConfig('${t.tool_id}')">配置</button>`:''}<button class="btn btn-sm btn-ghost" onclick="openEditTool('${t.tool_id}')" title="编辑">✏️</button><button class="btn btn-sm btn-ghost" onclick="deleteTool('${t.tool_id}','${t.name}')" title="删除" style="color:var(--pink)">🗑️</button><label style="position:relative;display:inline-block;width:44px;height:24px;cursor:pointer"><input type="checkbox" ${on?'checked':''} onchange="togTool('${t.tool_id}',this.checked)" style="opacity:0;width:0;height:0"><span style="position:absolute;inset:0;background:${on?'var(--pink)':'var(--dim)'};border-radius:0;transition:.3s"></span><span style="position:absolute;top:2px;left:${on?'22px':'2px'};width:20px;height:20px;background:oklch(0.96 0.003 110);border-radius:50%;transition:.3s"></span></label></div></div>`})});
  box.innerHTML=html;
}
async function togTool(id,en){
  const r=await api(`${A}/teams/${tid}/tools/${id}/${en?'enable':'disable'}`,{method:'POST'});
  if(r){toast(en?'已启用':'已禁用')}else{toast(en?'启用失败':'禁用失败 — 请刷新重试')}
  loadTools()
}
async function testToolExec(toolName){
  toast(`正在执行 ${toolName}...`);
  const args={};
  if(toolName==='web_search')args.query='AgentsGroup2026 maritime system';
  else if(toolName==='engine_status')args.engine_id='main';
  else if(toolName==='ais_query')args.mmsi='';
  else if(toolName==='weather_fetch'){args.lat=31.2;args.lon=121.5}
  else if(toolName==='cargo_status')args.hold_id='all';
  else if(toolName==='list_directory')args.path='.';
  else if(toolName==='run_python')args.code='print("Hello from AgentsGroup2026!")';
  else if(toolName==='colregs_check'){args.own_vessel={};args.target_vessel={}}
  else if(toolName==='route_calculate'){args.origin={lat:31.2,lon:121.5};args.destination={lat:22.3,lon:114.2}}
  const r=await api(`${A}/tools/${toolName}/execute`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({arguments:args})}).catch(()=>null);
  if(r&&r.success){toast(`✅ ${toolName} 执行成功`);alert(`工具: ${toolName}\n\n${r.output||'(无输出)'}`)}
  else if(r){toast(`❌ ${toolName} 执行失败`);alert(`工具: ${toolName}\n\n错误: ${r.error||'未知错误'}`)}
  else toast('执行请求失败')
}
function openToolConfig(toolId){_tcToolId=toolId;api(`${A}/tools`).then(all=>{const t=(all||[]).find(x=>x.tool_id===toolId);if(!t){toast('工具未找到');return}el('tc-title').textContent=`${t.icon||'🔧'} ${t.name} 配置`;const sch=t.config_schema||{};const cfg=t.config||{};let html='';Object.keys(sch).forEach(k=>{const s=sch[k];const v=cfg[k]??s.default??'';html+=`<div class="form-group"><label class="form-label">${k} <span style="color:var(--dim);font-size:11px">${s.description||''}</span></label>${s.type==='boolean'?`<select class="fi" id="tc-${k}"><option value="true"${v?'selected':''}>是</option><option value="false"${!v?' selected':''}>否</option></select>`:`<input class="fi" id="tc-${k}" value="${Array.isArray(v)?v.join(', '):v}" placeholder="${s.default||''}">`}</div>`});if(!html)html='<p style="color:var(--dim)">此工具暂无可配置项</p>';el('tc-form').innerHTML=html;openModal('modal-tool-config')})}
async function saveToolConfig(){
  if(!_tcToolId){toast('无工具选中');return}
  const inputs=el('tc-form').querySelectorAll('[id^="tc-"]');
  const config={};inputs.forEach(inp=>{const k=inp.id.replace('tc-','');config[k]=inp.tagName==='SELECT'?inp.value==='true':inp.value});
  const r=await api(`${A}/tools/${_tcToolId}/config`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({config})});
  if(r){toast('配置已保存');closeModal('modal-tool-config')}else toast('保存失败')
}

// ── Tool Edit / Delete ──
async function openEditTool(toolId){
  const all=await api(`${A}/tools`);const t=(all||[]).find(x=>x.tool_id===toolId);
  if(!t){toast('工具未找到');return}
  const html=`<div class="modal-overlay open" id="modal-edit-tool" onclick="if(event.target===this)this.remove()"><div class="modal"><h3>✏️ 编辑工具: ${escapeHtml(t.name)}</h3><div class="form-group"><label class="form-label">名称</label><input class="fi" id="et-name" value="${escapeHtml(t.name)}"></div><div class="form-group"><label class="form-label">描述</label><textarea class="fi" id="et-desc" rows="3">${escapeHtml(t.description||'')}</textarea></div><div class="form-group"><label class="form-label">图标</label><input class="fi" id="et-icon" value="${t.icon||'🔧'}" style="width:60px"></div><div class="form-group"><label class="form-label">需要审批</label><select class="fi" id="et-approval"><option value="false"${!t.requires_approval?' selected':''}>否</option><option value="true"${t.requires_approval?' selected':''}>是</option></select></div><div class="modal-actions"><button class="btn" onclick="document.getElementById('modal-edit-tool').remove()">取消</button><button class="btn btn-pink" onclick="submitEditTool('${toolId}')">保存</button></div></div></div>`;
  document.body.insertAdjacentHTML('beforeend',html);
}
async function submitEditTool(toolId){
  const data={name:el('et-name').value.trim(),description:el('et-desc').value.trim(),icon:el('et-icon').value.trim(),requires_approval:el('et-approval').value==='true'};
  const r=await api(`${A}/teams/${tid}/tools/${toolId}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  if(r){toast('✅ 工具已更新');const m=document.getElementById('modal-edit-tool');if(m)m.remove();loadTools()}else toast('更新失败')
}
async function deleteTool(toolId,toolName){
  if(!confirm(`确认删除工具「${toolName}」？此操作不可撤销。`))return;
  const r=await api(`${A}/teams/${tid}/tools/${toolId}`,{method:'DELETE'});
  if(r){toast('✅ 工具已删除');loadTools()}else toast('删除失败')
}

// ── Skill Edit / Delete ──
async function openEditSkill(skillId){
  const all=await api(`${A}/skills`);const s=(all||[]).find(x=>x.skill_id===skillId);
  if(!s){toast('技能未找到');return}
  // Fetch full instructions
  let instructions='';
  if(s.has_instructions){const r=await api(`${A}/skills/${skillId}/instructions`);if(r)instructions=r.instructions||''}
  const html=`<div class="modal-overlay open" id="modal-edit-skill" onclick="if(event.target===this)this.remove()"><div class="modal"><h3>✏️ 编辑技能: ${escapeHtml(s.name)}</h3><div class="form-group"><label class="form-label">名称</label><input class="fi" id="es-name" value="${escapeHtml(s.name)}"></div><div class="form-group"><label class="form-label">描述</label><textarea class="fi" id="es-desc" rows="3">${escapeHtml(s.description||'')}</textarea></div><div class="form-group"><label class="form-label">图标</label><input class="fi" id="es-icon" value="${s.icon||'⚡'}" style="width:60px"></div><div class="form-group"><label class="form-label">类别</label><select class="fi" id="es-cat"><option value="general"${s.category==='general'?' selected':''}>通用</option><option value="maritime"${s.category==='maritime'?' selected':''}>海事</option><option value="coding"${s.category==='coding'?' selected':''}>编程</option><option value="analysis"${s.category==='analysis'?' selected':''}>分析</option><option value="research"${s.category==='research'?' selected':''}>研究</option><option value="communication"${s.category==='communication'?' selected':''}>沟通</option></select></div><div class="form-group"><label class="form-label">Slug</label><input class="fi" id="es-slug" value="${escapeHtml(s.slug||'')}"></div><div class="form-group"><label class="form-label">指令 (Instructions)</label><textarea class="fi" id="es-instructions" rows="6" style="font-family:monospace;font-size:12px">${escapeHtml(instructions)}</textarea></div><div class="modal-actions"><button class="btn" onclick="document.getElementById('modal-edit-skill').remove()">取消</button><button class="btn btn-pink" onclick="submitEditSkill('${skillId}')">保存</button></div></div></div>`;
  document.body.insertAdjacentHTML('beforeend',html);
}
async function submitEditSkill(skillId){
  const data={name:el('es-name').value.trim(),description:el('es-desc').value.trim(),icon:el('es-icon').value.trim(),category:el('es-cat').value,slug:el('es-slug').value.trim(),instructions:el('es-instructions').value};
  const r=await api(`${A}/teams/${tid}/skills/${skillId}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  if(r){toast('✅ 技能已更新');const m=document.getElementById('modal-edit-skill');if(m)m.remove();loadSkills()}else toast('更新失败')
}
async function deleteSkill(skillId,skillName){
  // tools-skills.js 后加载会覆盖为带防连点版本；此处作兜底
  const rawId=String(skillId||'').trim();
  if(!rawId){toast('缺少 skill_id');return}
  if(!confirm(`确认删除技能「${skillName||rawId}」？此操作不可撤销。`))return;
  const sid=encodeURIComponent(rawId);
  let r=null;
  if(window.api&&typeof window.api.del==='function'){
    r=await window.api.del(`${A}/teams/${tid}/skills/${sid}`);
  }else{
    r=await api(`${A}/teams/${tid}/skills/${sid}`,{method:'DELETE'});
  }
  const err=(window.api&&window.api._lastError)||api._lastError||{};
  const ok=r&&(r.status==='deleted'||r.status==='already_deleted'||r.skill_id);
  const gone=err.status===404;
  if(ok||gone){
    toast(gone||(r&&r.status==='already_deleted')?'技能已不存在，已刷新列表':'✅ 技能已删除');
    loadSkills();
  }else{
    toast('删除失败：'+(err.message||(r&&r.detail)||'未知错误')+(err.status===403?'（可硬刷新后重试）':''));
    try{loadSkills()}catch(_){}
  }
}

// ── Skills (Clawith-style) ──
async function loadSkills(){
  const[all,team]=await Promise.all([api(`${A}/skills`),api(`${A}/teams/${tid}/skills`)]);
  const en=new Set((team||[]).map(s=>s.skill_id||s.id));const box=el('skills-cards');
  if(!all||!all.length){box.innerHTML='<p style="color:var(--dim)">暂无技能</p>';return}
  const cats={};all.forEach(s=>{const c=(s.category||'general').toUpperCase();if(!cats[c])cats[c]=[];cats[c].push(s)});
  let html='<div style="display:flex;gap:8px;margin-bottom:16px"><button class="btn btn-sm btn-pink" onclick="openGenerateSkillModal()">⚡ 生成技能</button><button class="btn btn-sm" onclick="importSkillFromFile()">📥 导入技能</button><button class="btn btn-sm" onclick="exportSkillsMD()">📤 导出全部</button></div>';
  Object.keys(cats).sort().forEach(cat=>{
    html+=`<div class="sb-section" style="margin-top:16px;margin-bottom:10px">${cat}</div>`;
    cats[cat].forEach(s=>{const on=en.has(s.skill_id);const hasCfg=s.config_schema&&Object.keys(s.config_schema).length;
      html+=`<div style="display:flex;align-items:center;padding:14px 18px;background:var(--panel2,#21272D);border:1px solid var(--line);border-radius:0;margin-bottom:6px;gap:12px"><span style="font-size:22px;width:36px;text-align:center">${s.icon||'⚡'}</span><div style="flex:1;min-width:0"><div style="display:flex;align-items:center;gap:8px;margin-bottom:2px"><b style="font-size:13px;color:var(--text)">${s.name}</b><span class="chip" style="font-size:10px;padding:1px 6px">${s.source||'Built-in'}</span>${s.is_default?'<span class="chip" style="background:rgba(38,162,105,0.1);color:var(--lime);font-size:10px;padding:1px 6px">Default</span>':''}${s.slug?`<span class="chip" style="font-size:10px;padding:1px 6px">${s.slug}</span>`:''}</div><div style="color:var(--muted);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${s.description||''}</div></div><div style="display:flex;align-items:center;gap:8px">${hasCfg?`<button class="btn btn-sm btn-ghost" onclick="openSkillConfig('${s.name}')" title="配置" style="color:var(--pink)">⚙️</button>`:''}<button class="btn btn-sm btn-ghost" onclick="testSkillExec('${s.name}')" title="测试执行">▶</button>${s.has_instructions?`<button class="btn btn-sm btn-ghost" onclick="viewSkillInstructions('${s.skill_id}')" title="查看指令">📖</button>`:''}<button class="btn btn-sm btn-ghost" onclick="openEditSkill('${s.skill_id}')" title="编辑">✏️</button><button class="btn btn-sm btn-ghost" onclick="deleteSkill('${s.skill_id}','${s.name}')" title="删除" style="color:var(--pink)">🗑️</button><button class="btn btn-sm btn-ghost" onclick="viewSkillPortability('${s.skill_id}')" title="可移植性">🏷</button><button class="btn btn-sm btn-ghost" onclick="viewSkillFolder('${s.skill_id}')" title="文件结构">📁</button><label style="position:relative;display:inline-block;width:44px;height:24px;cursor:pointer"><input type="checkbox" ${on?'checked':''} onchange="togSkill('${s.skill_id}',this.checked)" style="opacity:0;width:0;height:0"><span style="position:absolute;inset:0;background:${on?'var(--pink)':'var(--dim)'};border-radius:0;transition:.3s"></span><span style="position:absolute;top:2px;left:${on?'22px':'2px'};width:20px;height:20px;background:oklch(0.96 0.003 110);border-radius:50%;transition:.3s"></span></label></div></div>`})});
  box.innerHTML=html;
}
async function togSkill(id,en){await api(`${A}/teams/${tid}/skills/${id}/${en?'enable':'disable'}`,{method:'POST'});toast(en?'已启用':'已禁用');loadSkills()}
function openGenerateSkillModal(){
  const html=`<div class="modal-overlay open" id="modal-gen-skill" onclick="if(event.target===this)this.remove()"><div class="modal"><h3>⚡ 生成新技能</h3><div class="form-group"><label class="form-label">技能名称 <span class="req">*</span></label><input class="fi" id="gs-name" placeholder="例: maritime_weather_analysis"></div><div class="form-group"><label class="form-label">描述</label><textarea class="fi" id="gs-desc" placeholder="技能用途描述"></textarea></div><div class="form-group"><label class="form-label">类别</label><select class="fi" id="gs-cat"><option value="general">通用</option><option value="maritime">海事</option><option value="coding">编程</option><option value="analysis">分析</option></select></div><div class="form-group"><label class="form-label">触发词 (逗号分隔)</label><input class="fi" id="gs-triggers" placeholder="天气分析, 气象, weather"></div><div class="modal-actions"><button class="btn" onclick="document.getElementById('modal-gen-skill').remove()">取消</button><button class="btn btn-pink" onclick="submitGenerateSkill()">生成</button></div></div></div>`;
  document.body.insertAdjacentHTML('beforeend',html);
}
async function submitGenerateSkill(){
  const name=el('gs-name').value.trim();if(!name){toast('请输入技能名称');return}
  const r=await api(`${A}/skills`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,description:el('gs-desc').value.trim(),category:el('gs-cat').value,triggers:(el('gs-triggers').value||'').split(',').map(s=>s.trim()).filter(Boolean)})});
  if(r){toast('✅ 技能已生成');const m=document.getElementById('modal-gen-skill');if(m)m.remove();loadSkills()}else{toast('❌ 生成失败，请检查后端')}
}
function importSkillFromFile(){
  const inp=document.createElement('input');inp.type='file';inp.accept='.json,.md';
  inp.onchange=async(e)=>{const f=e.target.files[0];if(!f)return;const text=await f.text();
    try{
      let data;
      if(f.name.endsWith('.json')){data=JSON.parse(text)}
      else{data={name:f.name.replace(/\.(md|json)$/,''),instructions:text,category:'general'}}
      const r=await api(`${A}/skills`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
      if(r){toast('✅ 技能导入成功');loadSkills()}else{toast('❌ 导入失败')}
    }catch(err){toast('文件解析失败: '+err.message)}
  };inp.click();
}
async function viewSkillInstructions(skillId){
  const r=await api(`${A}/skills/${skillId}/instructions`);
  if(!r){toast('获取失败');return}
  const inst=r.instructions||'暂无指令内容';
  const tools=(r.required_tools||[]).join(', ')||'无';
  alert(`技能: ${r.name}\n\n所需工具: ${tools}\n\n--- 指令内容 ---\n\n${inst}`);
}
async function viewSkillPortability(skillId){
  const r=await api(`${A}/skills/${skillId}/portability`);
  if(!r){toast('获取失败');return}
  const tcolors={1:'var(--lime)',2:'var(--amber)',3:'var(--pink)'};
  const tdesc={1:'纯 Prompt — 可在任何 LLM 平台使用',2:'CLI/API 依赖 — 需要对应运行环境',3:'平台原生 — 仅在 AgentsGroup2026 上运行'};
  toast(`${skillId}: Tier ${r.tier} (${r.label})`);
  alert(`技能: ${skillId}\n\n可移植性等级: Tier ${r.tier}\n标签: ${r.label}\n\n${tdesc[r.tier]||'未知等级'}`);
}
async function viewSkillFolder(skillId){
  const r=await api(`${A}/skills/${skillId}/folder`);
  if(!r){toast('获取失败');return}
  const files=(r.files||[]).map(f=>`  📄 ${f.name||f} (${f.size||'?'} B)`).join('\n')||'  (无文件)';
  alert(`技能文件结构: ${skillId}\n\n📁 ${r.folder_name||skillId}/\n${files}`);
}

// ── Skill Config Modal ──
async function openSkillConfig(skillName){
  const r=await api(`${A}/skills/${skillName}/config-schema`);
  if(!r||!r.config_schema){toast('该技能无可配置项');return}
  const schema=r.config_schema;const cfg=r.config||{};
  let html=`<div class="card" style="max-width:560px;margin:0 auto"><div class="section-title">⚙️ ${skillName} 配置</div>`;
  Object.entries(schema).forEach(([key,def])=>{
    const val=cfg[key]!==undefined?cfg[key]:def.default;
    const desc=def.description||key;
    html+=`<div class="form-group"><label class="form-label">${desc}</label>`;
    if(def.enum){
      html+=`<select class="fi" id="sc-${key}">`;
      def.enum.forEach(opt=>{html+=`<option value="${opt}"${val===opt?' selected':''}>${opt}</option>`});
      html+='</select>';
    } else if(def.type==='boolean'){
      html+=`<select class="fi" id="sc-${key}"><option value="true"${val?'selected':''}>是</option><option value="false"${!val?'selected':''}>否</option></select>`;
    } else if(def.type==='integer'||def.type==='number'){
      html+=`<input class="fi" type="number" id="sc-${key}" value="${val||0}">`;
    } else {
      html+=`<input class="fi" type="text" id="sc-${key}" value="${escapeHtml(String(val||''))}" placeholder="${def.default||''}">`;
    }
    html+='</div>';
  });
  html+=`<div style="display:flex;gap:10px;margin-top:16px"><button class="btn btn-pink" onclick="saveSkillConfig('${skillName}')">保存配置</button><button class="btn" onclick="switchView('skills')">取消</button></div></div>`;
  // Show in main area
  const main=el('view-skills');
  main.querySelector('.main-scroll').innerHTML=html;
  window._skillConfigSchema=schema;window._skillConfigName=skillName;
}
async function saveSkillConfig(skillName){
  const schema=window._skillConfigSchema||{};const cfg={};
  Object.entries(schema).forEach(([key,def])=>{
    const e=el('sc-'+key);if(!e)return;
    if(def.type==='boolean')cfg[key]=e.value==='true';
    else if(def.type==='integer')cfg[key]=parseInt(e.value)||0;
    else if(def.type==='number')cfg[key]=parseFloat(e.value)||0;
    else cfg[key]=e.value;
  });
  const r=await api(`${A}/skills/${skillName}/config`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)});
  if(r){toast(`${skillName} 配置已保存`);loadSkills()}else toast('保存失败');
}
async function testSkillExec(skillName){
  const prompt=window.prompt(`输入测试提示词 (${skillName}):`);
  if(!prompt)return;
  toast('正在执行...');
  const agentId=aid||'build_developer';const teamId=tid||'build_system';
  const r=await api(`${A}/teams/${teamId}/agents/${agentId}/skills/${skillName}/execute`,{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({prompt,task_id:'',config_overrides:{}})
  });
  if(r){
    if(r.session_id && r.status==='streaming'){
      // Open terminal panel and stream output
      openClaudeTerm(r.session_id);
    } else {
      const status=r.status||'unknown';
      let msg=`技能: ${skillName}\n状态: ${status}`;
      if(r.output)msg+=`\n\n输出:\n${r.output.slice(0,500)}`;
      if(r.error)msg+=`\n\n错误: ${r.error}`;
      if(r.subtasks)msg+=`\n\n子任务: ${r.count} 个`;
      alert(msg);
      toast(`${skillName} 执行: ${status}`);
    }
  } else toast('执行失败');
}

// ── Claude Code Terminal ──
let _ctEventSource=null;
let _ctSessionId='';
let _ctElapsedTimer=null;

function openClaudeTerm(sessionId){
  _ctSessionId=sessionId;
  const overlay=el('claude-term-overlay');
  const body=el('ct-body');
  const statusEl=el('ct-status');
  const linesEl=el('ct-lines');
  const sessionEl=el('ct-session-id');
  const stopBtn=el('ct-stop');
  body.innerHTML='';
  sessionEl.textContent=sessionId;
  statusEl.textContent='● running';
  statusEl.style.color='oklch(0.52 0.04 160)';
  stopBtn.style.display='';
  linesEl.textContent='0 lines';
  overlay.classList.add('open');
  let lineCount=0;
  const startTime=Date.now();

  // Elapsed timer
  clearInterval(_ctElapsedTimer);
  _ctElapsedTimer=setInterval(()=>{
    const s=Math.floor((Date.now()-startTime)/1000);
    el('ct-elapsed').textContent=`${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`;
  },1000);

  // Connect SSE
  if(_ctEventSource){_ctEventSource.close();_ctEventSource=null}
  const es=new EventSource(`${A}/claude-sessions/${sessionId}/stream`);
  _ctEventSource=es;

  es.onmessage=(e)=>{
    lineCount++;
    const line=document.createElement('div');
    line.className='ct-line';
    const text=e.data;
    if(text.startsWith('❌'))line.classList.add('ct-err');
    else if(text.startsWith('✅')||text.includes('passed'))line.classList.add('ct-success');
    line.textContent=text;
    body.appendChild(line);
    body.scrollTop=body.scrollHeight;
    linesEl.textContent=`${lineCount} lines`;
  };

  es.addEventListener('done',(e)=>{
    try{
      const d=JSON.parse(e.data);
      statusEl.textContent=d.status==='completed'?'✓ completed':'✗ '+d.status;
      statusEl.style.color=d.status==='completed'?'oklch(0.52 0.04 160)':'oklch(0.48 0.07 22)';
      stopBtn.style.display='none';
      clearInterval(_ctElapsedTimer);
      const endLine=document.createElement('div');
      endLine.className='ct-line '+(d.status==='completed'?'ct-success':'ct-err');
      endLine.textContent=`\n[${d.status}] exit code: ${d.exit_code}`;
      body.appendChild(endLine);
      body.scrollTop=body.scrollHeight;
    }catch(ex){}
    es.close();
    _ctEventSource=null;
  });

  es.onerror=()=>{
    statusEl.textContent='⚠ connection lost';
    statusEl.style.color='oklch(0.56 0.05 70)';
    clearInterval(_ctElapsedTimer);
    es.close();
    _ctEventSource=null;
  };
}

function closeClaudeTerm(){
  el('claude-term-overlay').classList.remove('open');
  if(_ctEventSource){_ctEventSource.close();_ctEventSource=null}
  clearInterval(_ctElapsedTimer);
}

async function stopClaudeSession(){
  if(!_ctSessionId)return;
  await fetch(`${A}/claude-sessions/${_ctSessionId}/stop`,{method:'POST'});
  toast('已停止');
}

// ══════════════════════════════════
//  AGENT DETAIL (Clawith tabs)
// ══════════════════════════════════
// NOTE: use `const loadAgent = …` (not `async function loadAgent`).
// A function declaration would become window.loadAgent and fight agent-detail.js.
// agent-detail (loaded after this file) exports window.__detailLoadAgent + window.loadAgent.
async function _waitDetailLoadAgent(maxMs){
  if(typeof window.__detailLoadAgent==='function') return window.__detailLoadAgent;
  const deadline=Date.now()+(maxMs||3000);
  while(Date.now()<deadline){
    await _sleep(25);
    if(typeof window.__detailLoadAgent==='function') return window.__detailLoadAgent;
  }
  return typeof window.__detailLoadAgent==='function' ? window.__detailLoadAgent : null;
}

const loadAgent = async function(id){
  // Prefer full implementation from agent-detail.js (ag-memory / employee / …)
  const detailLoad = await _waitDetailLoadAgent(atab==='ag-memory'?4000:1500);
  if(detailLoad){
    return detailLoad(id);
  }
  if(id){aid=id;_chatSid=''}const d=await api(`${A}/teams/${tid}/agents/${aid}`);
  if(!d){el('agent-content').innerHTML='<p style="color:var(--dim);padding:40px">加载失败</p>';return}
  el('main-title').textContent=d.name||d.agent_id;el('main-badge').textContent=d.role||d.template_type||'';
  document.querySelectorAll('.sb-agent').forEach(e=>e.classList.toggle('active',e.onclick&&e.onclick.toString().includes(aid)));
  renderATab(d);
};
// Expose for inline handlers; agent-detail overwrites with richer impl when ready
window.loadAgent = loadAgent;

// Only one tab-click handler here; agent-detail also registers — both call loadAgent which
// resolves to the same detail impl after ready. Deduplicate by data flag.
if(!window.__agentTabsBound){
  window.__agentTabsBound=true;
  document.querySelectorAll('#agent-tabs .tab').forEach(t=>t.addEventListener('click',()=>{
    document.querySelectorAll('#agent-tabs .tab').forEach(x=>x.classList.remove('active'));
    t.classList.add('active');
    atab=t.dataset.at;
    loadAgent();
  }));
}

function renderATab(d){
  const c=el('agent-content'),p=d.personality||{},m=d.metadata||{},cr=d.created_at?d.created_at.split('T')[0]:'?';
  if(atab==='ag-status'){
    // Fetch real metrics from the new endpoint
    Promise.all([
      api(`${A}/teams/${tid}/agents/${aid}/metrics`),
      api(`${A}/teams/${tid}/agents/${aid}/activity`)
    ]).then(([mt,act])=>{
      mt=mt||{};act=act||{};
      c.innerHTML=`<div class="card-grid"><div class="stat-card"><div class="label">📋 状态</div><div class="value" style="font-size:16px"><span class="st st-${d.state||'idle'}">● ${stL(d.state)}</span></div><div class="sub"><button class="btn btn-sm" style="margin-top:6px;padding:3px 10px;font-size:11px" onclick="startStop('${d.state}')">${d.state==='working'?'⏹ 停止':'▶ 启动'}</button></div></div><div class="stat-card"><div class="label">📊 今日 Token</div><div class="value">${(mt.today_tokens||0).toLocaleString()}</div></div><div class="stat-card"><div class="label">📈 本月 Token</div><div class="value">${((mt.month_tokens||0)/1000).toFixed(1)}K</div></div><div class="stat-card"><div class="label">🤖 今日 LLM 调用</div><div class="value">${mt.today_llm_calls||0}</div><div class="sub">消息: ${mt.messages_sent||0}</div></div><div class="stat-card"><div class="label">🔄 总 Token</div><div class="value">${((mt.total_tokens||0)/1000).toFixed(1)}K</div></div><div class="stat-card"><div class="label">✅ 任务完成</div><div class="value">${mt.tasks_completed||0}</div><div class="sub">失败: ${mt.tasks_failed||0}</div></div><div class="stat-card"><div class="label">🔧 工具调用</div><div class="value">${mt.tools_invoked||0}</div></div><div class="stat-card"><div class="label">🔴 24h 活动</div><div class="value">${act.total_actions||0}</div></div></div><div style="display:grid;grid-template-columns:1fr 1fr;gap:16px"><div class="card"><div class="section-title">📁 Agent 档案</div><div class="detail-row"><span class="lbl">👤 角色</span><span class="val">${d.role||d.description||'-'}</span></div><div class="detail-row"><span class="lbl">📅 创建时间</span><span class="val">${cr}</span></div><div class="detail-row"><span class="lbl">👤 创建者</span><span class="val">@system</span></div><div class="detail-row"><span class="lbl">🔴 最后活跃</span><span class="val">${mt.last_active?mt.last_active.split('T')[0]:'从未'}</span></div><div class="detail-row"><span class="lbl">💬 会话数</span><span class="val">${mt.sessions_created||0}</span></div><div class="detail-row"><span class="lbl">🧠 是否 Hermes</span><span class="val">${d.is_hermes_agent?'<span style="color:var(--lime)">✓</span>':'—'}</span></div></div><div class="card"><div class="section-title">🧠 模型配置</div><div class="detail-row"><span class="lbl">🟠 模型</span><span class="val">${d.model_id||'未配置'}</span></div><div class="detail-row"><span class="lbl">📁 模板</span><span class="val">${d.template_type||'-'}</span></div><div class="detail-row"><span class="lbl">🔧 工具数</span><span class="val">${(d.tools||[]).length}</span></div><div class="detail-row"><span class="lbl">⚡ 技能数</span><span class="val">${(d.skills||[]).length}</span></div><div class="detail-row"><span class="lbl">📡 通道数</span><span class="val">${(d.channels||[]).length}</span></div></div></div><div class="section" style="margin-top:20px"><div class="section-title">📊 近期活动</div>${act.recent_logs&&act.recent_logs.length?act.recent_logs.slice(-8).reverse().map(l=>`<div class="focus-item" style="padding:10px 14px"><div class="title" style="font-size:13px"><span class="chip" style="font-size:10px">${l.action}</span> ${l.detail||''}</div><div class="meta">${l.timestamp?l.timestamp.replace('T',' ').slice(0,19):''}</div></div>`).join(''):'<p style="color:var(--dim);font-size:13px">暂无活动记录 — 发送消息或启动 Agent 后将显示</p>'}</div>`;
    });
  } else if(atab==='ag-aware'){
    const tr=m.traits||[],bd=m.behavior_boundaries||[];
    c.innerHTML=`<div class="section"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px"><div class="section-title" style="margin:0">关注点</div><span style="color:var(--dim);font-size:12px">${(d.skills||[]).length+tr.length} active</span></div><p style="color:var(--muted);font-size:12px;margin-bottom:14px">Agent 当前正在关注的任务</p>${(d.skills||[]).map(s=>`<div class="focus-item"><div class="title"><span class="dot" style="width:8px;height:8px;background:var(--pink)"></span>${s}</div><div class="meta">skill · active</div></div>`).join('')}${tr.map(t=>`<div class="focus-item"><div class="title"><span class="dot" style="width:8px;height:8px;background:var(--amber)"></span>${t}</div><div class="meta">trait · personality</div></div>`).join('')}${bd.map(b=>`<div class="focus-item"><div class="title"><span class="dot" style="width:8px;height:8px;background:var(--dim)"></span>${b}</div><div class="meta">boundary · constraint</div></div>`).join('')}${!(d.skills||[]).length&&!tr.length&&!bd.length?'<p style="color:var(--dim)">暂无关注项</p>':''}</div>`;
  } else if(atab==='ag-soul'){
    const soul=`# Soul — ${d.name||d.agent_id}\n\n## Identity\n- **名称**: ${d.name||d.agent_id}\n- **角色**: ${d.role||d.description||'-'}\n- **创建时间**: ${cr}\n\n## Personality\n- ${p.tone||'professional'}\n- ${p.response_style||'concise'}\n- 创造力: ${p.creativity??0.5}\n- 语言: ${p.language||'zh-CN'}\n- 专长: ${(p.expertise_areas||[]).join(', ')||'无'}\n\n## Boundaries\n${(m.behavior_boundaries||[]).map(b=>'- '+b).join('\n')||'- 无限制'}`;
    // Load saved soul or generate default
    api(`${A}/teams/${tid}/agents/${aid}/soul`).then(sd=>{
      const savedSoul=(sd&&sd.content)?sd.content:soul;
      // Load memory files
      api(`${A}/teams/${tid}/agents/${aid}/memory`).then(mf=>{
        const files=mf||[];
        c.innerHTML=`<div class="section"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px"><div><div class="section-title" style="margin:0">🧬 Soul.md — 人格定义</div><p style="color:var(--muted);font-size:12px;margin-top:2px">核心身份、人格和行为边界</p></div><div><button class="btn btn-sm" id="soul-edit-btn" onclick="toggleSoulEdit()">编辑</button><button class="btn btn-pink btn-sm hidden" id="soul-save-btn" onclick="saveSoul()">保存</button></div></div><div class="soul-block" id="soul-view">${savedSoul}</div><textarea class="fi hidden" id="soul-editor" rows="16" style="font-family:'IBM Plex Mono',monospace;font-size:13px;line-height:1.7;min-height:300px">${savedSoul}</textarea></div><div class="section"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px"><div class="section-title" style="margin:0">🧠 记忆文件</div><button class="btn btn-sm" onclick="addMemoryFile()">＋ 新建</button></div><p style="color:var(--muted);font-size:12px;margin-bottom:12px">通过对话和经验积累的持久记忆</p><div id="memory-list">${files.length?files.map(f=>`<div class="memory-item" style="cursor:pointer" onclick="openMemoryFile('${f.filename}')"><span>📄 ${f.filename}</span><span style="display:flex;align-items:center;gap:8px"><span style="color:var(--dim);font-size:12px">${f.size_display||f.size+' B'}</span><span style="cursor:pointer;color:var(--dim);font-size:14px" onclick="event.stopPropagation();delMemoryFile('${f.filename}')" title="删除">×</span></span></div>`).join(''):'<p style="color:var(--dim);font-size:13px">暂无记忆文件，点击「新建」开始积累</p>'}</div></div><div class="section hidden" id="mem-editor-section"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px"><div class="section-title" style="margin:0" id="mem-editor-title">📝 编辑文件</div><div style="display:flex;gap:8px"><button class="btn btn-pink btn-sm" onclick="saveMemoryFile()">保存</button><button class="btn btn-sm" onclick="closeMemEditor()">关闭</button></div></div><textarea class="fi" id="mem-editor" rows="12" style="font-family:'IBM Plex Mono',monospace;font-size:13px;line-height:1.7"></textarea></div><div class="section"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px"><div class="section-title" style="margin:0">关注点</div><span style="color:var(--dim);font-size:12px">${(d.skills||[]).length+(m.traits||[]).length} active</span></div><p style="color:var(--muted);font-size:12px;margin-bottom:14px">技能、性格特质与行为边界</p>${(d.skills||[]).map(s=>`<div class="focus-item"><div class="title"><span class="dot" style="width:8px;height:8px;background:var(--pink)"></span>${s}</div><div class="meta">skill · active</div></div>`).join('')}${(m.traits||[]).map(t=>`<div class="focus-item"><div class="title"><span class="dot" style="width:8px;height:8px;background:var(--amber)"></span>${t}</div><div class="meta">trait · personality</div></div>`).join('')}${(m.behavior_boundaries||[]).map(b=>`<div class="focus-item"><div class="title"><span class="dot" style="width:8px;height:8px;background:var(--dim)"></span>${b}</div><div class="meta">boundary · constraint</div></div>`).join('')}${!(d.skills||[]).length&&!(m.traits||[]).length&&!(m.behavior_boundaries||[]).length?'<p style="color:var(--dim)">暂无关注项</p>':''}</div>`;
      });
    });
  } else if(atab==='ag-memory'){
    // Prefer agent-detail panel; poll briefly if script order races deep-link
    c.innerHTML='<div class="section"><div class="section-title">🧠 记忆绑定</div><p style="color:var(--dim);font-size:12px">加载中…</p></div>';
    (async()=>{
      for(let i=0;i<80;i++){
        if(typeof window.renderAgentMemoryBind==='function'){
          try{ await window.renderAgentMemoryBind(d); return; }catch(e){
            c.innerHTML=`<div class="section"><p style="color:var(--red)">记忆面板错误: ${escapeHtml(e.message||e)}</p></div>`;
            return;
          }
        }
        await _sleep(40);
      }
      c.innerHTML=`<div class="section"><div class="section-title">🧠 记忆绑定</div>
        <p style="color:var(--muted);font-size:13px;margin:8px 0 12px">记忆面板脚本尚未就绪。可打开站级中枢，或稍后重试。</p>
        <a class="btn btn-pink btn-sm" href="/agent-memory.html?team_id=${encodeURIComponent(tid||'')}&agent_id=${encodeURIComponent(aid||'')}&seg=agents">打开 Agent记忆中枢</a>
        <button class="btn btn-sm" style="margin-left:8px" onclick="loadAgent()">重试</button>
      </div>`;
    })();
  } else if(atab==='ag-tools'){
    api(`${A}/tools`).then(all=>{
      const bound=new Set(d.tools||[]);
      const cats={};(all||[]).forEach(t=>{const c=(t.category||'general').toUpperCase();if(!cats[c])cats[c]=[];cats[c].push(t)});
      let html=`<div class="section"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px"><div class="section-title" style="margin:0">🔧 已绑定工具</div><span style="color:var(--dim);font-size:12px">${bound.size} / ${(all||[]).length} 已启用</span></div>`;
      Object.keys(cats).sort().forEach(cat=>{
        html+=`<div class="sb-section" style="margin-top:12px;margin-bottom:8px;font-size:11px;color:var(--dim);letter-spacing:1px">${cat}</div>`;
        cats[cat].forEach(t=>{const on=bound.has(t.tool_id)||bound.has(t.name);
          html+=`<div class="ws-item" style="padding:10px 14px"><span class="fname" style="gap:10px"><span style="font-size:18px">${t.icon||'🔧'}</span> <b>${t.name}</b> <span style="color:var(--dim);font-size:11px">${t.category||''}</span></span><span style="display:flex;align-items:center;gap:8px"><span style="color:var(--dim);font-size:12px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${t.description||''}</span><button class="btn btn-sm btn-ghost" onclick="testToolExec('${t.name}')" title="测试执行">▶</button><button class="btn btn-sm btn-ghost" onclick="openEditTool('${t.tool_id}')" title="编辑">✏️</button><button class="btn btn-sm btn-ghost" onclick="deleteTool('${t.tool_id}','${t.name}')" title="删除" style="color:var(--pink)">🗑️</button><button class="btn btn-sm${on?' btn-danger':''}" onclick="togAgentTool('${t.tool_id}',${!on})">${on?'解绑':'绑定'}</button></span></div>`})});
      html+=`</div>`;
      c.innerHTML=html;
    });
  } else if(atab==='ag-skills'){
    api(`${A}/skills`).then(all=>{
      const bound=new Set(d.skills||[]);
      const cats={};(all||[]).forEach(s=>{const c=(s.category||'general').toUpperCase();if(!cats[c])cats[c]=[];cats[c].push(s)});
      let html=`<div class="section"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px"><div class="section-title" style="margin:0">⚡ 已配置技能</div><span style="color:var(--dim);font-size:12px">${bound.size} / ${(all||[]).length} 已启用</span></div>`;
      Object.keys(cats).sort().forEach(cat=>{
        html+=`<div class="sb-section" style="margin-top:12px;margin-bottom:8px;font-size:11px;color:var(--dim);letter-spacing:1px">${cat}</div>`;
        cats[cat].forEach(s=>{const on=bound.has(s.skill_id)||bound.has(s.name);
          html+=`<div class="ws-item" style="padding:10px 14px"><span class="fname" style="gap:10px"><span style="font-size:18px">${s.icon||'⚡'}</span> <b>${s.name}</b> <span style="color:var(--dim);font-size:11px">${s.category||''}</span></span><span style="display:flex;align-items:center;gap:8px"><span style="color:var(--dim);font-size:12px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${s.description||''}</span>${s.has_instructions?`<button class="btn btn-sm btn-ghost" onclick="viewSkillInstructions('${s.skill_id}')" title="查看指令">📖</button>`:''}<button class="btn btn-sm btn-ghost" onclick="openEditSkill('${s.skill_id}')" title="编辑">✏️</button><button class="btn btn-sm btn-ghost" onclick="deleteSkill('${s.skill_id}','${s.name}')" title="删除" style="color:var(--pink)">🗑️</button><button class="btn btn-sm${on?' btn-danger':''}" onclick="togAgentSkill('${s.skill_id}',${!on})">${on?'解绑':'绑定'}</button></span></div>`})});
      html+=`</div>`;
      c.innerHTML=html;
    });
  } else if(atab==='ag-relations'){
    // 真关系边 = RelationshipStore（agent-employee API）；同伴列表仅作参考
    const AE='/api/v1/agent-employee';
    Promise.all([
      api(`${A}/teams/${tid}/agents/${aid}/relationships`).catch(()=>null),
      api(`${AE}/teams/${tid}/relationships?agent_id=${encodeURIComponent(aid)}`).catch(()=>null),
    ]).then(([rel,storeRel])=>{
      const chans=JSON.parse(JSON.stringify(d.channels||[]));
      window._relChannelDraft={teamId:tid,agentId:aid,channels:chans};
      const edges=(storeRel&&storeRel.relationships)||[];
      // XF-7.13 空关系 CTA
      const twinUrl=`/Agent-digital-twin.html?office3d=1&team_id=${encodeURIComponent(tid||'')}`;
      const edgeHtml=edges.length?edges.map(r=>{
        const other=r.source_agent_id===aid?r.target_id:r.source_agent_id;
        const dir=r.source_agent_id===aid?'→':'←';
        const eco=(r.note&&String(r.note).includes('eco'))||(r.created_by&&String(r.created_by).includes('eco'));
        return `<div class="ws-item"><span class="fname">🔗 ${escapeHtml(dir)} ${escapeHtml(other||'?')}</span>`
          +`<span class="chip">${escapeHtml(r.rel_type||'collaborator')}</span>`
          +(eco?'<span class="chip" style="background:rgba(34,211,238,.12);color:var(--cyan)">物竞</span>':'')
          +(r.note?`<span style="color:var(--dim);font-size:11px;max-width:220px;overflow:hidden;text-overflow:ellipsis">${escapeHtml(r.note)}</span>`:'')
          +`</div>`;
      }).join(''):(
        `<div style="padding:12px 14px;border:1px dashed var(--line);margin-bottom:8px">`
        +`<div style="font-size:13px;font-weight:600;margin-bottom:6px">暂无门禁关系边</div>`
        +`<p style="color:var(--dim);font-size:12px;margin:0 0 10px;line-height:1.45">同队编制与通道共总线已是协作关系；点对点门禁边可从物竞 ③ 建议确认写回，或在数字员工页人工添加。</p>`
        +`<div style="display:flex;flex-wrap:wrap;gap:8px">`
        +`<a class="btn btn-sm btn-pink" href="${twinUrl}" style="text-decoration:none">🧬 物竞 ③ 生成建议</a>`
        +`<a class="btn btn-sm" href="/agent-team-config.html?team_id=${encodeURIComponent(tid||'')}&view=agent&agent_id=${encodeURIComponent(aid||'')}&atab=ag-relations" style="text-decoration:none">刷新本页</a>`
        +`</div></div>`
      );
      const peerHtml=rel&&rel.relationships&&rel.relationships.length
        ?`<div style="margin-top:8px;font-size:11px;color:var(--dim)">协作通讯录（同队/通道/门禁）：${rel.relationships.map(r=>escapeHtml(r.name||r.target||'?')).join(' · ')}</div>`
        :'';
      const chRows=chans.length?chans.map((ch,i)=>{
        const eco=ch.source==='eco_drill'||(ch.note&&String(ch.note).indexOf('eco:')===0);
        return `<div class="ws-item" style="flex-wrap:wrap;gap:8px" data-ch-i="${i}">
          <span class="fname">📡 <input class="fi" style="width:140px;padding:4px 8px;font-size:12px" value="${escapeHtml(ch.channel_name||ch.channel||'')}" onchange="updRelChanName(${i},this.value)" placeholder="通道名"></span>
          <label style="font-size:12px;display:flex;align-items:center;gap:4px"><input type="checkbox" ${ch.subscribe?'checked':''} onchange="updRelChanField(${i},'subscribe',this.checked)"> 订阅</label>
          <label style="font-size:12px;display:flex;align-items:center;gap:4px"><input type="checkbox" ${ch.publish?'checked':''} onchange="updRelChanField(${i},'publish',this.checked)"> 发布</label>
          <label style="font-size:12px;display:flex;align-items:center;gap:4px">P <input type="number" style="width:48px" value="${ch.priority??0}" onchange="updRelChanField(${i},'priority',+this.value)"></label>
          ${eco?'<span class="chip" style="background:rgba(34,211,238,.12);color:var(--cyan)">物竞</span>':''}
          <button class="btn btn-sm btn-ghost" style="color:var(--pink)" onclick="rmRelChan(${i})">删除</button>
        </div>`;
      }).join(''):'<p style="color:var(--dim)">暂无通道 — 可添加团队总线</p>';
      c.innerHTML=`<div class="section"><div class="section-title">🔗 关系边 <span style="font-weight:400;color:var(--dim);font-size:11px">通信门禁 · RelationshipStore</span></div>${edgeHtml}${peerHtml}</div>
        <div class="section"><div class="section-title" style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
          <span>📡 通道绑定 <span style="font-weight:400;color:var(--dim);font-size:11px">subscribe/publish 运行时生效</span></span>
          <span style="display:flex;gap:6px;flex-wrap:wrap">
            <button class="btn btn-sm" onclick="addRelChan()">＋ 添加</button>
            <button class="btn btn-sm btn-pink" onclick="saveRelChannels()">💾 保存通道</button>
            <button class="btn btn-sm" onclick="testRelChanPublish()" title="向首个可发布通道发测试消息">🧪 测发布</button>
            <button class="btn btn-sm" onclick="testRelChanInbox()">📥 收件箱</button>
          </span>
        </div>
        <div id="rel-chan-list">${chRows}</div>
        <p id="rel-chan-status" style="font-size:12px;color:var(--dim);margin-top:8px"></p>
        </div>`;
    });
  } else if(atab==='ag-workspace'){
    var wsPath='';
    function renderWs(p){
      wsPath=p||'';
      api(`${A}/teams/${tid}/agents/${aid}/workspace?path=${encodeURIComponent(wsPath)}`).then(ws=>{
        if(ws.type==='file'){
          c.innerHTML=`<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px"><div class="section-title" style="margin:0">📄 ${escapeHtml(ws.name)}</div><div style="display:flex;gap:8px"><button class="btn btn-sm" onclick="renderWs('${wsPath.split('/').slice(0,-1).join('/')}')">← 返回</button><button class="btn btn-danger btn-sm" onclick="wsDelete('${wsPath}')">🗑 删除</button></div></div><textarea id="ws-edit" style="width:100%;min-height:300px;background:var(--card);color:var(--fg);border:1px solid var(--border);border-radius:0;padding:12px;font-family:monospace;font-size:13px;resize:vertical">${escapeHtml(ws.content||'')}</textarea><div style="margin-top:12px;display:flex;gap:8px"><button class="btn btn-pink" onclick="wsSave('${wsPath}')">💾 保存</button><button class="btn" onclick="wsIngestFile('${wsPath}')">📥 送入知识库</button></div>`;
          return;
        }
        var items=(ws.items||[]).map(it=>{
          var icon=it.type==='folder'?'📁':'📄';
          var newPath=wsPath?wsPath+'/'+it.name:it.name;
          return `<div class="ws-item" style="cursor:pointer" onclick="renderWs('${newPath}')"><span class="fname">${icon} ${escapeHtml(it.name)}</span><span style="color:var(--dim);font-size:12px">${it.size_display||''}</span></div>`;
        }).join('')||'<p style="color:var(--dim)">空文件夹</p>';
        var breadcrumb=wsPath?`<span style="cursor:pointer;color:var(--pink)" onclick="renderWs('')">workspace</span> / ${wsPath.split('/').map((p,i,a)=>`<span style="cursor:pointer;color:var(--pink)" onclick="renderWs('${a.slice(0,i+1).join('/')}')">${p}</span>`).join(' / ')}`:'workspace';
        c.innerHTML=`<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px"><div class="section-title" style="margin:0">📁 ${breadcrumb}</div><div style="display:flex;gap:8px"><button class="btn btn-sm" onclick="wsCreateFolder()">📁 新建文件夹</button><button class="btn btn-pink btn-sm" onclick="wsCreateFile()">＋ 新建文件</button><button class="btn btn-sm" onclick="wsIngestAll()">📥 全部送入知识库</button></div></div>${items}`;
      }).catch(()=>{
        c.innerHTML=`<p style="color:var(--dim)">加载工作区失败</p>`;
      });
    }
    window.wsSave=function(fp){
      var content=document.getElementById('ws-edit').value;
      fetch(`${A}/teams/${tid}/agents/${aid}/workspace/${fp}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({content})}).then(r=>r.json()).then(()=>{showToast('已保存');renderWs(fp)});
    };
    window.wsDelete=function(fp){
      if(!confirm('确认删除 '+fp+'?'))return;
      fetch(`${A}/teams/${tid}/agents/${aid}/workspace/${fp}`,{method:'DELETE'}).then(r=>r.json()).then(()=>{showToast('已删除');renderWs(fp.split('/').slice(0,-1).join('/'))});
    };
    window.wsCreateFolder=function(){
      var name=prompt('文件夹名称');if(!name)return;
      fetch(`${A}/teams/${tid}/agents/${aid}/workspace?path=${encodeURIComponent(wsPath)}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,type:'folder'})}).then(r=>r.json()).then(()=>{showToast('已创建');renderWs(wsPath)});
    };
    window.wsCreateFile=function(){
      var name=prompt('文件名称 (例如 report.md)');if(!name)return;
      fetch(`${A}/teams/${tid}/agents/${aid}/workspace?path=${encodeURIComponent(wsPath)}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,type:'file',content:''})}).then(r=>r.json()).then(()=>{showToast('已创建');renderWs(wsPath)});
    };
    window.wsIngestAll=function(){
      fetch(`${A}/teams/${tid}/agents/${aid}/workspace/ingest-to-kb?path=${encodeURIComponent(wsPath)}`,{method:'POST'}).then(r=>r.json()).then(r=>{showToast('已送入知识库: '+r.files+' 个文件')});
    };
    window.wsIngestFile=function(fp){
      fetch(`${A}/teams/${tid}/agents/${aid}/workspace/ingest-to-kb?path=${encodeURIComponent(fp)}`,{method:'POST'}).then(r=>r.json()).then(r=>{showToast('已送入知识库')});
    };
    renderWs('');
  } else if(atab==='ag-chat'){
    if(_chatSid){loadChatView(c);return}
    api(`${A}/teams/${tid}/agents/${aid}/sessions`).then(ss=>{c.innerHTML=`<div class="section"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px"><div class="section-title" style="margin:0">💬 对话</div><button class="btn btn-pink btn-sm" onclick="newSession()">＋ 新建会话</button></div>${ss&&ss.length?ss.map(s=>`<div class="ws-item" style="cursor:pointer" onclick="openChatSession('${s.session_id||s.id}')"><span class="fname">💬 ${s.session_id||s.id}</span><span style="color:var(--dim);font-size:12px">${s.created_at||''}</span></div>`).join(''):'<p style="color:var(--dim)">暂无会话，点击上方按钮开始对话</p>'}</div>`});
  } else if(atab==='ag-logs'){
    api(`${A}/teams/${tid}/agents/${aid}/logs?limit=100`).then(lg=>{
      const logs=(lg&&lg.logs)||[];
      c.innerHTML=`<div class="section"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px"><div class="section-title" style="margin:0">📋 工作日志</div><span style="color:var(--dim);font-size:12px">${logs.length} 条记录</span></div>${logs.length?logs.slice().reverse().map(l=>`<div class="focus-item" style="padding:10px 14px"><div class="title" style="font-size:13px"><span class="chip" style="font-size:10px">${l.action||'log'}</span> ${escapeHtml(l.detail||'')}</div><div class="meta">${l.timestamp?l.timestamp.replace('T',' ').slice(0,19):''}</div></div>`).join(''):'<p style="color:var(--dim)">暂无日志 — 与 Agent 交互后日志将自动生成</p>'}</div>`});
  } else if(atab==='ag-settings'){
    c.innerHTML=`<div class="card" style="max-width:600px"><div class="section-title">⚙️ 设置</div><div class="form-group"><label class="form-label">名称</label><input class="fi" value="${d.name||''}" id="set-name"></div><div class="form-group"><label class="form-label">角色</label><input class="fi" value="${d.role||''}" id="set-role"></div><div class="form-group"><label class="form-label">描述</label><textarea class="fi" id="set-desc">${d.description||''}</textarea></div><div class="form-group"><label class="form-label">系统提示词</label><textarea class="fi" id="set-prompt" rows="4">${d.system_prompt||''}</textarea></div><div class="form-group"><label class="form-label">模型 ID</label><input class="fi" value="${d.model_id||''}" id="set-model"></div><div id="agent-test-result" class="hidden" style="margin-top:12px;padding:14px;border-radius:0;border:1px solid var(--line);font-size:13px"></div><div style="display:flex;gap:10px;margin-top:20px"><button class="btn btn-pink" onclick="saveAgent()">保存</button><button class="btn" onclick="testAgentLLM()">🧪 测试连接</button><button class="btn btn-danger" onclick="delAgent()">删除</button></div></div>`;
  }
}
async function newSession(){const r=await api(`${A}/teams/${tid}/agents/${aid}/sessions`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})});if(r){toast('会话已创建');_chatSid=r.session_id||r.id;loadAgent()}else{toast('已创建');loadAgent()}}
let _chatSid='';
function openChatSession(sid){_chatSid=sid;loadAgent()}
function closeChatSession(){_chatSid='';loadAgent()}
function loadChatView(c){
  const sid=_chatSid;
  api(`${A}/teams/${tid}/agents/${aid}/sessions/${sid}/messages`).then(resp=>{
    const msgs=resp&&resp.messages?resp.messages:resp||[];
    let html=`<div style="display:flex;align-items:center;gap:12px;margin-bottom:16px"><button class="btn btn-sm" onclick="closeChatSession()">← 返回</button><div class="section-title" style="margin:0">💬 会话 ${sid.slice(0,8)}</div></div>`;
    html+=`<div id="chat-msgs" style="display:flex;flex-direction:column;gap:10px;margin-bottom:20px;min-height:200px">`;
    if(msgs&&msgs.length){msgs.forEach(m=>{const isU=m.role==='user';html+=`<div style="display:flex;${isU?'justify-content:flex-end':''}"><div style="max-width:80%;padding:12px 16px;border-radius:${isU?'12px 12px 4px 12px':'12px 12px 12px 4px'};background:${isU?'var(--chat-user)':'var(--chat-agent)'};border:1px solid ${isU?'var(--chat-user-border)':'var(--chat-agent-border)'};font-size:13px;line-height:1.7;color:var(--chat-text)"><div style="font-size:11px;color:${isU?'var(--pink)':'var(--cyan)'};margin-bottom:4px">${isU?'👤 你':'🤖 Agent'} · ${(m.timestamp||m.created_at||'').slice(11,19)}</div><div style="white-space:pre-wrap;color:var(--text)">${(m.content||'').replace(/</g,'&lt;')}</div></div></div>`})}else{html+=`<p style="color:var(--dim);text-align:center;padding:40px 0">开始对话吧 👋</p>`}
    html+=`</div>`;
    html+=`<div style="display:flex;gap:10px;position:sticky;bottom:0;background:linear-gradient(to top,var(--bg) 80%,transparent);padding:12px 0"><input class="fi" id="chat-input" placeholder="输入消息..." style="flex:1" onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendChatMsg()}"><button class="btn btn-pink" onclick="sendChatMsg()">发送</button></div>`;
    c.innerHTML=html;
    const ci=el('chat-input');if(ci)ci.focus();
    const cm=el('chat-msgs');if(cm)cm.scrollTop=cm.scrollHeight;
  }).catch(()=>{
    c.innerHTML=`<div style="display:flex;align-items:center;gap:12px;margin-bottom:16px"><button class="btn btn-sm" onclick="closeChatSession()">← 返回</button><div class="section-title" style="margin:0">💬 会话 ${sid.slice(0,8)}</div></div><div style="display:flex;flex-direction:column;gap:10px;margin-bottom:20px;min-height:200px"><p style="color:var(--dim);text-align:center;padding:40px 0">开始对话吧 👋</p></div><div style="display:flex;gap:10px;position:sticky;bottom:0;background:linear-gradient(to top,var(--bg) 80%,transparent);padding:12px 0"><input class="fi" id="chat-input" placeholder="输入消息..." style="flex:1" onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendChatMsg()}"><button class="btn btn-pink" onclick="sendChatMsg()">发送</button></div>`;
    const ci=el('chat-input');if(ci)ci.focus();
  });
}
async function sendChatMsg(){const inp=el('chat-input');if(!inp)return;const msg=inp.value.trim();if(!msg)return;inp.value='';inp.disabled=true;
  const r=await api(`${A}/teams/${tid}/agents/${aid}/sessions/${_chatSid}/messages`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role:'user',content:msg})}).catch(()=>null);
  inp.disabled=false;if(r){loadAgent();if(r.task_id){toast(`📋 任务已创建: ${r.task_id}`)}}else{toast('发送失败');inp.value=msg}}
async function saveAgent(){const b={name:el('set-name').value.trim(),role:el('set-role').value.trim(),description:el('set-desc').value.trim(),system_prompt:el('set-prompt').value.trim(),model_id:el('set-model').value.trim()};const r=await api(`${A}/teams/${tid}/agents/${aid}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});if(r){toast('已保存');loadSbAgents();loadAgent()}else toast('失败')}
async function testAgentLLM(){
  const rc=document.getElementById('agent-test-result');
  if(!rc)return;
  rc.classList.remove('hidden');
  rc.innerHTML='<p style="color:var(--dim)">正在测试 Agent LLM 连接...</p>';
  try{
    const r=await api(`${A}/llm/test`,{method:'POST'});
    if(!r){rc.innerHTML='<p style="color:var(--pink)">请求失败，请检查后端</p>';return}
    if(r.success){
      rc.style.borderColor='var(--lime,oklch(0.52 0.04 160))';
      rc.innerHTML=`<div style="color:var(--lime,oklch(0.52 0.04 160));margin-bottom:6px">✅ 连接成功</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:12px"><div><b>模型:</b> ${escapeHtml(r.model)}</div><div><b>提供商:</b> ${escapeHtml(r.provider)}</div><div><b>延迟:</b> ${r.latency_ms?r.latency_ms.toFixed(0):'?'}ms</div></div><div style="margin-top:8px;padding:10px;background:rgba(232,240,250,0.7);border-radius:6px;font-size:12px;color:var(--text)">${escapeHtml(r.response||'')}</div>`;
      // Auto-update model_id to the actual connected model
      const mi=document.getElementById('set-model');
      if(mi && r.model && mi.value!==r.model){
        mi.value=r.model;
        const b={name:el('set-name').value.trim(),role:el('set-role').value.trim(),description:el('set-desc').value.trim(),system_prompt:el('set-prompt').value.trim(),model_id:r.model};
        api(`${A}/teams/${tid}/agents/${aid}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}).then(()=>{toast('模型已自动更新为 '+r.model);loadSbAgents()});
      }
    } else {
      rc.style.borderColor='var(--pink,oklch(0.48 0.07 22))';
      rc.innerHTML=`<div style="color:var(--pink,oklch(0.48 0.07 22));margin-bottom:6px">❌ 连接失败</div><div style="padding:10px;background:rgba(224,27,36,0.06);border-radius:6px;font-size:12px;word-break:break-all">${escapeHtml(r.error||'未知错误')}</div><div style="margin-top:8px;font-size:11px;color:var(--muted)">💡 请在「模型池」或「LLM 配置」中填入正确的 API Key</div>`;
    }
  }catch(e){rc.innerHTML=`<p style="color:var(--pink)">请求异常: ${escapeHtml(e.message)}</p>`}
}
async function delAgent(){
  // 详情页删除：复用列表删除（CSRF 安全）
  if(!aid){toast('未选中智能体');return}
  const nameEl=document.getElementById('set-name');
  const name=nameEl?nameEl.value:(aid);
  await deleteAgentFromList(aid,name);
}
async function startStop(cur){const act=cur==='working'?'stop':'start';const r=await api(`${A}/teams/${tid}/agents/${aid}/${act}`,{method:'POST'});if(r){toast(act==='start'?'Agent 已启动':'Agent 已停止');loadSbAgents();loadAgent()}else toast('操作失败')}

// ══════════════════════════════════
//  SOUL.MD & MEMORY FILES
// ══════════════════════════════════
let _memFn='';
function toggleSoulEdit(){const v=el('soul-view'),e=el('soul-editor'),eb=el('soul-edit-btn'),sb=el('soul-save-btn');if(e.classList.contains('hidden')){e.classList.remove('hidden');v.classList.add('hidden');eb.classList.add('hidden');sb.classList.remove('hidden');e.focus()}else{e.classList.add('hidden');v.classList.remove('hidden');eb.classList.remove('hidden');sb.classList.add('hidden')}}
async function saveSoul(){const c=el('soul-editor').value;const r=await api(`${A}/teams/${tid}/agents/${aid}/soul`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:c})});if(r){toast('Soul.md 已保存');el('soul-view').textContent=c;toggleSoulEdit()}else toast('保存失败')}
async function addMemoryFile(){const n=prompt('输入文件名 (例: learning_log.md):');if(!n||!n.trim())return;const fn=n.trim();const r=await api(`${A}/teams/${tid}/agents/${aid}/memory/${encodeURIComponent(fn)}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:`# ${fn}\n\n创建于 ${new Date().toISOString().split('T')[0]}\n`})});if(r){toast(`${fn} 已创建`);loadAgent()}else toast('创建失败')}
async function openMemoryFile(fn){_memFn=fn;const r=await api(`${A}/teams/${tid}/agents/${aid}/memory/${encodeURIComponent(fn)}`);if(!r){toast('无法打开');return}const sec=el('mem-editor-section');sec.classList.remove('hidden');el('mem-editor-title').textContent=`📝 ${fn}`;el('mem-editor').value=r.content||'';el('mem-editor').focus()}
async function saveMemoryFile(){if(!_memFn)return;const c=el('mem-editor').value;const r=await api(`${A}/teams/${tid}/agents/${aid}/memory/${encodeURIComponent(_memFn)}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:c})});if(r){toast(`${_memFn} 已保存`);loadAgent()}else toast('保存失败')}
function closeMemEditor(){el('mem-editor-section').classList.add('hidden');_memFn=''}
// Ensure overlay click also resets memory editor state
document.addEventListener('click',e=>{if(e.target.classList.contains('modal-overlay')&&_memFn){closeMemEditor()}})
async function delMemoryFile(fn){if(!confirm(`删除记忆文件 "${fn}"？`))return;await fetch(`${A}/teams/${tid}/agents/${aid}/memory/${encodeURIComponent(fn)}`,{method:'DELETE'});toast(`${fn} 已删除`);loadAgent()}

// ══════════════════════════════════
//  AGENT TOOL / SKILL BIND
// ══════════════════════════════════
async function togAgentTool(toolId,bind){
  const d=await api(`${A}/teams/${tid}/agents/${aid}`);if(!d)return;
  let cur=new Set(d.tools||[]);if(bind)cur.add(toolId);else cur.delete(toolId);
  await api(`${A}/teams/${tid}/agents/${aid}/tools`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({tool_ids:[...cur]})});
  toast(bind?`已绑定 ${toolId}`:`已解绑 ${toolId}`);loadAgent();
}
async function togAgentSkill(skillId,bind){
  const d=await api(`${A}/teams/${tid}/agents/${aid}`);if(!d)return;
  let cur=new Set(d.skills||[]);if(bind)cur.add(skillId);else cur.delete(skillId);
  await api(`${A}/teams/${tid}/agents/${aid}/skills`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({skill_ids:[...cur]})});
  toast(bind?`已绑定 ${skillId}`:`已解绑 ${skillId}`);loadAgent();
}

// ══════════════════════════════════
//  5-STEP WIZARD
// ══════════════════════════════════
const TMPLS=[{id:'custom',ab:'自定义',nm:'自定义'},{id:'coordinator',ab:'PM',nm:'项目经理'},{id:'researcher',ab:'RS',nm:'研究员'},{id:'developer',ab:'DV',nm:'开发者'},{id:'analyst',ab:'AN',nm:'分析师'},{id:'navigator',ab:'NV',nm:'导航员'},{id:'engineer',ab:'EN',nm:'工程师'}];

function openWizard(){if(isPlatformScope()){toast('请先在左上角选择一个团队','error');return}wzD={template_type:'custom',name:'',role:'',description:'',system_prompt:'',model_id:'',team_id:tid,personality:{tone:'professional',language:'zh-CN',expertise_areas:[],response_style:'concise',creativity:0.5},skill_ids:[],tool_ids:[],permissions:[],channels:[],visibility:'public',default_access:'use'};wzS=1;switchView('wizard');renderWz()}

function renderWz(){
  document.querySelectorAll('#wz-steps .wz-step').forEach(s=>{const n=+s.dataset.step;s.classList.remove('active','done');if(n===wzS)s.classList.add('active');else if(n<wzS)s.classList.add('done')});
  const c=el('wz-content'),w=wzD;
  if(wzS===1){
    c.innerHTML=`<h3 style="margin-bottom:20px">基础信息与模型选择</h3><p class="form-label" style="margin-bottom:10px">选择模板（可选）</p><div class="tmpl-grid">${TMPLS.map(t=>`<div class="tmpl-card${w.template_type===t.id?' selected':''}" onclick="selTmpl('${t.id}')"><div class="abbr">${t.ab}</div><div class="desc">${t.nm}</div></div>`).join('')}</div><div style="display:flex;gap:12px;margin-bottom:16px"><p style="color:var(--muted);font-size:12px;cursor:pointer" onclick="toast('JSON 导入功能开发中')">↑ 从 JSON 导入</p><p style="color:var(--pink);font-size:12px;cursor:pointer;font-weight:600" onclick="openModal('modal-import-openclaw')">🔗 连接 OpenClaw Agent</p></div><div class="form-group"><label class="form-label">名称 <span class="req">*</span></label><input class="fi" id="wz-name" value="${w.name}" placeholder="例：小智"></div><div class="form-group"><label class="form-label">👤 角色</label><input class="fi" id="wz-role" value="${w.role}" placeholder="描述它的角色定位"></div><div class="form-group"><label class="form-label">描述</label><textarea class="fi" id="wz-desc">${w.description}</textarea></div><div class="form-group"><label class="form-label">所属团队 <span class="req">*</span></label><select class="fi" id="wz-team"></select></div><div class="form-group"><label class="form-label">主模型 <span class="req">*</span></label><select class="fi" id="wz-model"><option value="">选择模型...</option></select></div><div class="wz-actions"><button class="btn" onclick="switchView('overview')">取消</button><button class="btn btn-pink" onclick="wzNext()">下一步 →</button></div>`;
    api(`${A}/teams`).then(ts=>{const s=el('wz-team');if(ts)ts.forEach(t=>{const o=document.createElement('option');o.value=t.team_id;o.textContent=t.name;if(t.team_id===(w.team_id||tid))o.selected=true;s.appendChild(o)})});
    api(`${A}/teams/${w.team_id||tid}/models`).then(ms=>{const s=el('wz-model');if(ms)ms.forEach(m=>{const o=document.createElement('option');o.value=m.model_id;o.textContent=`${m.name} (${m.provider})`;if(m.model_id===w.model_id)o.selected=true;s.appendChild(o)})});
  } else if(wzS===2){
    c.innerHTML=`<h3 style="margin-bottom:20px">人格设定</h3><div class="form-group"><label class="form-label">语言风格</label><select class="fi" id="wz-tone"><option value="professional"${w.personality.tone==='professional'?' selected':''}>专业</option><option value="friendly"${w.personality.tone==='friendly'?' selected':''}>友好</option><option value="directive"${w.personality.tone==='directive'?' selected':''}>指令式</option><option value="casual"${w.personality.tone==='casual'?' selected':''}>随意</option></select></div><div class="form-group"><label class="form-label">语言</label><select class="fi" id="wz-lang"><option value="zh-CN"${w.personality.language==='zh-CN'?' selected':''}>中文</option><option value="en"${w.personality.language==='en'?' selected':''}>English</option></select></div><div class="form-group"><label class="form-label">回复风格</label><select class="fi" id="wz-style"><option value="concise"${w.personality.response_style==='concise'?' selected':''}>简洁</option><option value="detailed"${w.personality.response_style==='detailed'?' selected':''}>详细</option><option value="structured"${w.personality.response_style==='structured'?' selected':''}>结构化</option></select></div><div class="form-group"><label class="form-label">创造力 (${w.personality.creativity})</label><input type="range" id="wz-creat" min="0" max="1" step="0.1" value="${w.personality.creativity}"></div><div class="form-group"><label class="form-label">专长领域</label><div>${(w.personality.expertise_areas||[]).map(e=>`<span class="chip">${e} <span class="x" onclick="rmExp('${e}')">×</span></span>`).join('')}<span class="chip chip-add" onclick="addExp()">＋ 添加</span></div></div><div class="form-group"><label class="form-label">系统提示词</label><textarea class="fi" id="wz-prompt" rows="4" placeholder="定义核心行为...">${w.system_prompt||''}</textarea></div><div class="wz-actions"><button class="btn" onclick="wzBack()">← 上一步</button><button class="btn btn-pink" onclick="wzNext()">下一步 →</button></div>`;
  } else if(wzS===3){
    api(`${A}/skills`).then(sk=>{
      const cats={};(sk||[]).forEach(s=>{const c=s.category||'general';if(!cats[c])cats[c]=[];cats[c].push(s)});
      let html='<h3 style="margin-bottom:20px">技能配置</h3><p style="color:var(--muted);font-size:13px;margin-bottom:16px">选择此 Agent 应具备的技能 <span style="color:var(--pink)">('+w.skill_ids.length+' 已选)</span></p>';
      Object.keys(cats).sort().forEach(cat=>{html+=`<div class="sb-section" style="margin-top:14px;margin-bottom:8px">${cat.toUpperCase()}</div>`;cats[cat].forEach(s=>{const on=w.skill_ids.includes(s.skill_id);html+=`<div class="ws-item" style="cursor:pointer" onclick="togWzSk('${s.skill_id}')"><span class="fname"><span style="font-size:16px">${on?'☑':'☐'}</span> ${s.icon||'⚡'} ${s.name}</span><span style="color:var(--dim);font-size:12px">${s.category||''}</span></div>`})});
      html+=`<div class="wz-actions"><button class="btn" onclick="wzBack()">← 上一步</button><button class="btn btn-pink" onclick="wzNext()">下一步 →</button></div>`;
      c.innerHTML=html});
  } else if(wzS===4){
    api(`${A}/tools`).then(tk=>{
      const cats={};(tk||[]).forEach(t=>{const c=t.category||'general';if(!cats[c])cats[c]=[];cats[c].push(t)});
      let html='<h3 style="margin-bottom:20px">工具绑定</h3><p style="color:var(--muted);font-size:13px;margin-bottom:16px">选择要绑定的工具 <span style="color:var(--pink)">('+w.tool_ids.length+' 已选)</span></p>';
      Object.keys(cats).sort().forEach(cat=>{html+=`<div class="sb-section" style="margin-top:14px;margin-bottom:8px">${cat.toUpperCase()}</div>`;cats[cat].forEach(t=>{const on=w.tool_ids.includes(t.tool_id);html+=`<div class="ws-item" style="cursor:pointer" onclick="togWzTk('${t.tool_id}')"><span class="fname"><span style="font-size:16px">${on?'☑':'☐'}</span> ${t.icon||'🔧'} ${t.name}</span><span style="display:flex;align-items:center;gap:8px"><span style="color:var(--dim);font-size:12px">${t.category||''}</span>${t.is_default?'<span class="chip" style="background:rgba(152,245,167,0.12);color:var(--lime);font-size:10px">Default</span>':''}</span></div>`})});
      html+=`<div class="wz-actions"><button class="btn" onclick="wzBack()">← 上一步</button><button class="btn btn-pink" onclick="wzNext()">下一步 →</button></div>`;
      c.innerHTML=html});
  } else if(wzS===5){
    c.innerHTML=`<h3 style="margin-bottom:20px">权限设置</h3><div class="section"><div class="section-title">可见范围</div><div style="display:flex;flex-direction:column;gap:10px;margin-bottom:24px"><div class="tmpl-card${w.visibility==='public'?' selected':''}" onclick="setWzVis('public')" style="text-align:left;padding:16px;display:flex;align-items:center;gap:12px"><span style="color:var(--pink);font-size:20px">${w.visibility==='public'?'●':'○'}</span><div><div style="font-weight:600">全公司可见</div><div style="font-size:12px;color:var(--muted)">所有人都可以使用此数字员工</div></div></div><div class="tmpl-card${w.visibility==='private'?' selected':''}" onclick="setWzVis('private')" style="text-align:left;padding:16px;display:flex;align-items:center;gap:12px"><span style="color:var(--dim);font-size:20px">${w.visibility==='private'?'●':'○'}</span><div><div style="font-weight:600">仅自己</div><div style="font-size:12px;color:var(--muted)">仅创建者本人可使用</div></div></div></div></div><div class="section"><div class="section-title">默认访问级别</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:24px"><div class="tmpl-card${w.default_access==='use'?' selected':''}" onclick="setWzAccess('use')" style="text-align:left;padding:16px"><div style="display:flex;align-items:center;gap:8px"><span style="color:var(--pink);font-size:16px">${w.default_access==='use'?'●':'○'}</span><span style="font-size:18px">⚙️</span><div style="font-weight:600">使用</div></div><div style="font-size:12px;color:var(--muted);margin-top:6px">可以使用任务、聊天、工具、技能、工作区</div></div><div class="tmpl-card${w.default_access==='admin'?' selected':''}" onclick="setWzAccess('admin')" style="text-align:left;padding:16px"><div style="display:flex;align-items:center;gap:8px"><span style="color:var(--dim);font-size:16px">${w.default_access==='admin'?'●':'○'}</span><span style="font-size:18px">⚙️</span><div style="font-weight:600">管理</div></div><div style="font-size:12px;color:var(--muted);margin-top:6px">完全访问权限，包括设置、心智、关系</div></div></div></div><div class="section"><div class="section-title">细粒度权限 <span style="font-size:12px;color:var(--muted);font-weight:400">（可选）</span></div><div id="wz-perms">${(w.permissions||[]).map((p,i)=>`<div class="ws-item"><span class="fname">${p.resource} — ${p.access_level}</span><button class="btn btn-danger btn-sm" style="padding:2px 8px" onclick="rmPerm(${i})">×</button></div>`).join('')}</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px"><input class="fi" id="wz-pr" placeholder="资源名"><select class="fi" id="wz-pl"><option value="read">只读</option><option value="write">读写</option><option value="admin">管理</option></select></div><button class="btn btn-sm" style="margin-top:8px" onclick="addPerm()">＋ 添加</button></div><div class="wz-actions"><button class="btn" onclick="wzBack()">← 上一步</button><button class="btn btn-pink" onclick="wzNext()">下一步 →</button></div>`;
  } else if(wzS===6){
    const CH_PLATFORMS=[{id:'slack',icon:'💬',name:'Slack',desc:'Slack Bot'},{id:'discord',icon:'🎮',name:'Discord',desc:'Gateway / Webhook'},{id:'teams',icon:'🟦',name:'Microsoft Teams',desc:'Teams Bot'},{id:'feishu',icon:'💙',name:'飞书机器人',desc:'Feishu / Lark'},{id:'wecom',icon:'💚',name:'企业微信',desc:'WebSocket / Webhook'},{id:'dingtalk',icon:'🔵',name:'钉钉',desc:'Stream Mode'},{id:'atlassian',icon:'🔺',name:'Atlassian',desc:'Jira / Confluence / Compass (Rovo MCP)'},{id:'agentbay',icon:'☁️',name:'AgentBay',desc:'Browser & Code Execution (阿里云)'}];
    const chMap={};(w.channels||[]).forEach(ch=>chMap[ch.channel_name]=ch);
    let html=`<h3 style="margin-bottom:20px">通道配置</h3><p style="color:var(--muted);font-size:13px;margin-bottom:20px">连接消息平台，使你的智能体能够通过不同的渠道进行通信。</p>`;
    CH_PLATFORMS.forEach(p=>{const on=!!chMap[p.id];html+=`<div class="ws-item" style="cursor:pointer;padding:16px;margin-bottom:8px" onclick="togWzChan('${p.id}','${p.name}')"><span class="fname"><span style="font-size:22px">${p.icon}</span><div><div style="font-weight:600">${p.name}</div><div style="font-size:12px;color:var(--muted)">${p.desc}</div></div></span><span style="font-size:14px;color:${on?'var(--pink)':'var(--dim)'}">${on?'▼':'▶'}</span></div>`;if(on){html+=`<div style="padding:4px 16px 12px;margin-top:-8px;margin-bottom:8px;border:1px solid var(--line);border-top:none;border-radius:0 0 8px 8px;background:rgba(232,240,250,0.5)"><div style="display:grid;grid-template-columns:1fr 1fr;gap:10px"><label style="display:flex;align-items:center;gap:6px;font-size:13px"><input type="checkbox" ${chMap[p.id].subscribe?'checked':''} onchange="updChanSub('${p.id}',this.checked)"> 订阅</label><label style="display:flex;align-items:center;gap:6px;font-size:13px"><input type="checkbox" ${chMap[p.id].publish?'checked':''} onchange="updChanPub('${p.id}',this.checked)"> 发布</label></div></div>`}});
    html+=`<p style="color:var(--muted);font-size:12px;text-align:center;margin-top:16px">跳过此步骤后，数字员工仍可通过 Web 端进行对话</p>`;
    html+=`<div style="background:var(--panel2);border:1px solid var(--line);border-radius:0;padding:14px;margin-top:20px;font-size:13px;color:var(--muted)">${w.name||'未命名'} · 模型: ${w.model_id||'未选择'}</div>`;
    html+=`<div class="wz-actions"><button class="btn" onclick="wzBack()">← 上一步</button><button class="btn btn-pink" onclick="wzFinish()">🚀 完成创建</button></div>`;
    c.innerHTML=html;
  }
}

const TMPL_DEFAULTS={
  coordinator:{role:'项目协调与任务分配',personality:{tone:'directive',response_style:'structured',expertise_areas:['项目管理','任务拆解','进度跟踪']},skill_ids:['task_decomposition','progress_tracking','team_coordination']},
  researcher:{role:'深度研究与知识发现',personality:{tone:'professional',response_style:'detailed',expertise_areas:['文献检索','数据分析','知识整理'],creativity:0.7},skill_ids:['deep_research','data_analysis','knowledge_synthesis']},
  developer:{role:'代码开发与技术实现',personality:{tone:'professional',response_style:'concise',expertise_areas:['编程','调试','架构设计']},skill_ids:['code_generation','debugging','code_review'],tool_ids:['run_python','web_search','file_editor']},
  analyst:{role:'数据分析与洞察挖掘',personality:{tone:'professional',response_style:'structured',expertise_areas:['数据可视化','统计分析','趋势预测'],creativity:0.6},skill_ids:['data_analysis','visualization','report_generation']},
  navigator:{role:'航线规划与海况分析',personality:{tone:'directive',response_style:'concise',expertise_areas:['航海','气象','避碰']},skill_ids:['route_planning','weather_analysis','collision_avoidance'],tool_ids:['weather_fetch','ais_query']},
  engineer:{role:'机舱监控与设备维护',personality:{tone:'professional',response_style:'structured',expertise_areas:['轮机','传感器','预测维护']},skill_ids:['engine_diagnostics','predictive_maintenance'],tool_ids:['engine_status','sensor_data']}
};
function selTmpl(id){
  wzD.template_type=id;
  const def=TMPL_DEFAULTS[id];
  if(def){
    if(def.role&&!wzD.role)wzD.role=def.role;
    if(def.personality)Object.assign(wzD.personality,def.personality);
    if(def.skill_ids)wzD.skill_ids=[...new Set([...wzD.skill_ids,...def.skill_ids])];
    if(def.tool_ids)wzD.tool_ids=[...new Set([...wzD.tool_ids,...def.tool_ids])];
  }
  renderWz();
}
function wzBack(){if(wzS>1){saveWzData();wzS--;renderWz()}}
function wzNext(){
  saveWzData();
  // Validate step 1 required fields
  if(wzS===1){
    if(!wzD.name){toast('请填写 Agent 名称','error');el('wz-name')?.focus();return}
    if(!wzD.role){toast('请填写角色','error');el('wz-role')?.focus();return}
  }
  // Validate step 2 creativity range
  if(wzS===2){
    const c=wzD.personality.creativity;
    if(c<0||c>2){toast('创造力参数范围: 0-2','error');return}
  }
  if(wzS<6){wzS++;renderWz()}
}
function setWzVis(v){wzD.visibility=v;renderWz()}
function setWzAccess(v){wzD.default_access=v;renderWz()}
function togWzChan(id,name){const i=wzD.channels.findIndex(c=>c.channel_name===id);if(i>=0)wzD.channels.splice(i,1);else wzD.channels.push({channel_name:id,subscribe:true,publish:true,priority:0});renderWz()}
function updChanSub(id,v){const ch=wzD.channels.find(c=>c.channel_name===id);if(ch)ch.subscribe=v}
function updChanPub(id,v){const ch=wzD.channels.find(c=>c.channel_name===id);if(ch)ch.publish=v}
function saveWzData(){if(wzS===1){wzD.name=el('wz-name')?.value?.trim()||'';wzD.role=el('wz-role')?.value?.trim()||'';wzD.description=el('wz-desc')?.value?.trim()||'';wzD.model_id=el('wz-model')?.value||'';wzD.team_id=el('wz-team')?.value||tid}else if(wzS===2){wzD.personality.tone=el('wz-tone')?.value||'professional';wzD.personality.language=el('wz-lang')?.value||'zh-CN';wzD.personality.response_style=el('wz-style')?.value||'concise';wzD.personality.creativity=parseFloat(el('wz-creat')?.value||0.5);wzD.system_prompt=el('wz-prompt')?.value?.trim()||''}}
function togWzTk(tkid){const i=wzD.tool_ids.indexOf(tkid);if(i>=0)wzD.tool_ids.splice(i,1);else wzD.tool_ids.push(tkid);renderWz()}
function addExp(){const v=prompt('输入专长领域:');if(v?.trim()){wzD.personality.expertise_areas.push(v.trim());renderWz()}}
function rmExp(e){wzD.personality.expertise_areas=wzD.personality.expertise_areas.filter(x=>x!==e);renderWz()}
function togWzSk(sid){const i=wzD.skill_ids.indexOf(sid);if(i>=0)wzD.skill_ids.splice(i,1);else wzD.skill_ids.push(sid);renderWz()}
function addPerm(){const r=el('wz-pr').value.trim();if(!r){toast('请输入资源名');return}wzD.permissions.push({resource:r,access_level:el('wz-pl').value,channels:[]});renderWz()}
function rmPerm(i){wzD.permissions.splice(i,1);renderWz()}

async function wzFinish(){
  saveWzData();if(!wzD.name){toast('请输入名称');wzS=1;renderWz();return}
  const wtid=wzD.team_id||tid;
  // Disable finish button to prevent double-submit
  const finBtn=document.querySelector('.wz-actions .btn-pink');
  if(finBtn){finBtn.disabled=true;finBtn.classList.add('loading')}
  const r1=await api(`${A}/teams/${wtid}/agents`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:wzD.name,role:wzD.role,description:wzD.description,template_type:wzD.template_type,model_id:wzD.model_id,system_prompt:wzD.system_prompt})});
  if(!r1){toast('创建失败');if(finBtn){finBtn.disabled=false;finBtn.classList.remove('loading')}return}
  const nid=r1.agent_id;
  // Transaction: if any sub-step fails, rollback by deleting agent
  let failed=false;
  const steps=[
    ()=>api(`${A}/teams/${wtid}/agents/${nid}/personality`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(wzD.personality)}),
    ()=>wzD.skill_ids.length?api(`${A}/teams/${wtid}/agents/${nid}/skills`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({skill_ids:wzD.skill_ids})}):true,
    ()=>wzD.tool_ids.length?api(`${A}/teams/${wtid}/agents/${nid}/tools`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({tool_ids:wzD.tool_ids})}):true,
    ()=>wzD.permissions.length?api(`${A}/teams/${wtid}/agents/${nid}/permissions`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({permissions:wzD.permissions})}):true,
    ()=>wzD.channels.length?api(`${A}/teams/${wtid}/agents/${nid}/channels`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({channels:wzD.channels})}):true,
    ()=>(wzD.visibility||wzD.default_access)?api(`${A}/teams/${wtid}/agents/${nid}/visibility`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({visibility:wzD.visibility||'public',default_access:wzD.default_access||'use'})}):true
  ];
  for(const step of steps){
    const r=await step();
    if(r===null){failed=true;break}
  }
  if(failed){
    // Rollback: delete partially-created agent
    await fetch(`${A}/teams/${wtid}/agents/${nid}`,{method:'DELETE'}).catch(()=>{});
    toast('配置步骤失败，已回滚创建');
    if(finBtn){finBtn.disabled=false;finBtn.classList.remove('loading')}
    return;
  }
  if(finBtn){finBtn.disabled=false;finBtn.classList.remove('loading')}
  toast(`"${wzD.name}" 创建成功！`);tid=wtid;aid=nid;loadTeams();
}

// ══════════════════════════════════
//  CONCURRENT TASKS
// ══════════════════════════════════
const PRIO_LBL={0:'🔴 紧急',1:'🟠 高',2:'🔵 普通',3:'⚪ 低'};
const TST_CLS={pending:'st-idle',running:'st-working',completed:'st-reporting',failed:'st-error',cancelled:'st-blocked'};
const TST_LBL={pending:'待执行',running:'执行中',completed:'已完成',failed:'失败',cancelled:'已取消'};

const WF_ICONS={completed:'✓',active:'●',pending:'○',skipped:'—',failed:'✗'};

function renderWorkflow(task){
  const wf=task.metadata&&task.metadata.workflow;
  if(!wf||!wf.length) return '';
  const activeIdx=wf.findIndex(s=>s.status==='active');
  let html='<div class="wf-pipeline">';
  wf.forEach((step,i)=>{
    const cls='wf-dot'+(step.status==='completed'?' wf-completed':step.status==='active'?' wf-active':step.status==='failed'?' wf-failed':step.status==='skipped'?' wf-skipped':'');
    const icon=WF_ICONS[step.status]||(step.status==='failed'?'✗':'○');
    const agentName=step.agent_id?step.agent_id.replace(/^build_/,'').replace(/^ship_/,''):'?';
    const tip=step.label+' — '+agentName;
    if(i>0){
      const connCls='wf-connector'+(step.status==='completed'||wf[i-1].status==='completed'?' wf-done':'');
      html+=`<div class="${connCls}"></div>`;
    }
    const labelColor=step.status==='active'?'var(--cyan-s)':step.status==='completed'?'var(--lime)':step.status==='failed'?'var(--red)':'var(--dim)';
    html+=`<div class="wf-step-wrap"><div class="wf-step" onclick="stepClick('${task.task_id}',${i},'${step.status}')"><div class="wf-tip">${escapeHtml(tip)}</div><div class="${cls}">${icon}</div></div><div class="wf-label">${escapeHtml(step.label)}<br><span style="font-size:9px;color:${labelColor}">${escapeHtml(agentName)}</span></div></div>`;
  });

  // Advance button
  if(activeIdx>=0 && activeIdx+1<wf.length){
    const next=wf[activeIdx+1];
    const nextAgent=next.agent_id?next.agent_id.replace(/^build_/,''):'?';
    html+=`<button class="wf-advance-btn" onclick="advanceWorkflow('${task.task_id}')" title="推进到: ${escapeHtml(next.label)} (${escapeHtml(nextAgent)})">→ ${escapeHtml(nextAgent)} ▸</button>`;
  } else if(activeIdx>=0){
    html+=`<button class="wf-advance-btn" onclick="advanceWorkflow('${task.task_id}')" title="完成最后一步">✓ 完成 ▸</button>`;
  }
  html+='</div>';

  // Show Claude Code terminals for ALL steps that have a session_id
  const stepsWithSession = wf.filter(s => s.session_id);
  // Also show start button for active step without session
  const activeStep = wf.find(s => s.status === 'active');

  if(stepsWithSession.length > 0 || (activeStep && !activeStep.session_id)){
    html += '<div class="wf-terminals">';

    // Render a terminal panel for each step that has a session
    stepsWithSession.forEach(step => {
      const sid = step.session_id;
      const stepKey = step.key;
      const termId = `${task.task_id}_${stepKey}`;
      const agentName = step.agent_id ? step.agent_id.replace(/^build_/, '') : '?';
      const isActive = step.status === 'active';
      const isDone = step.status === 'completed';
      const statusCls = isActive ? 'running' : isDone ? 'done' : 'err';
      const openCls = isActive ? ' open' : '';  // Auto-open active step terminal

      html += `<div class="task-term" id="tt-${termId}">`;
      html += `<div class="task-term-header" onclick="toggleTaskTerm('${termId}')">`;
      html += `<div class="task-term-title">`;
      html += `<span class="tt-dot ${statusCls}" id="tt-dot-${termId}"></span>`;
      html += `<span class="tt-step-label">${escapeHtml(step.label)}</span>`;
      html += ` — ${escapeHtml(agentName)}`;
      html += `<span id="tt-sid-${termId}" style="color:oklch(0.72 0.006 110);font-size:10px;margin-left:6px">${escapeHtml(sid)}</span>`;
      html += `</div>`;
      html += `<div class="task-term-actions">`;
      html += `<span id="tt-st-${termId}" style="font-size:10px;color:${isActive?'oklch(0.52 0.04 160)':isDone?'oklch(0.52 0.04 160)':'oklch(0.48 0.07 22)'}">${isActive?'● running':isDone?'✓ done':'✗ ended'}</span>`;
      html += `<span id="tt-el-${termId}" style="font-size:10px;color:oklch(0.72 0.006 110)"></span>`;
      if(isActive) html += `<button onclick="event.stopPropagation();stopTaskTerm('${sid}')">⏹</button>`;
      html += `<button onclick="event.stopPropagation();expandTaskTerm('${termId}')">⛶</button>`;
      html += `</div></div>`;
      html += `<div class="task-term-body${openCls}" id="tt-body-${termId}"></div>`;
      html += `</div>`;
    });

    // Start button for active step without session
    if(activeStep && !activeStep.session_id){
      const agentName = activeStep.agent_id ? activeStep.agent_id.replace(/^build_/, '') : '?';
      html += `<div style="margin-top:6px"><button class="wf-advance-btn" onclick="startClaudeForTask('${task.task_id}')" style="background:rgba(88,166,255,0.08);border-color:rgba(88,166,255,0.3)">▶ 启动 Claude Code (${escapeHtml(activeStep.label)} — ${escapeHtml(agentName)})</button></div>`;
    }

    html += '</div>';
  }

  return html;
}

async function advanceWorkflow(taskId){
  const r=await api(`${A}/teams/${tid}/tasks/${taskId}/workflow/advance`,{method:'POST'});
  if(r){
    toast(r.all_completed?'工作流已全部完成':'已推进到下一步 — Claude Code 已自动启动');
    loadTasks();
    // Auto-connect inline terminals after re-render
    setTimeout(()=>connectAllTaskTerminals(),500);
  }else{toast('推进失败')}
}

// ── Workflow auto-refresh: polls active workflows for status changes ──
let _wfPollTimer=null;
let _lastWfSnapshot='';

function startWorkflowPoll(){
  if(_wfPollTimer) return;
  _wfPollTimer=setInterval(async()=>{
    try{
      const tasks=await api(`${A}/teams/${tid}/tasks`);
      if(!tasks||!tasks.length)return;
      // Build snapshot of all workflow step statuses
      let snap='';
      let hasActive=false;
      tasks.forEach(t=>{
        const wf=t.metadata&&t.metadata.workflow;
        if(!wf)return;
        wf.forEach(s=>{
          snap+=s.status;
          if(s.status==='active') hasActive=true;
        });
      });
      // If snapshot changed, re-render
      if(snap!==_lastWfSnapshot){
        _lastWfSnapshot=snap;
        loadTasks();
        setTimeout(()=>connectAllTaskTerminals(),600);
      }
      // G11 fix: Stop polling only when all tasks are terminal (completed/failed/cancelled),
      // not just when no step is currently "active" (race between steps)
      if(!hasActive){
        let allTerminal = true;
        tasks.forEach(t => {
          const st = t.status || '';
          if (!['completed','failed','cancelled'].includes(st)) allTerminal = false;
        });
        if(allTerminal){
          clearInterval(_wfPollTimer);
          _wfPollTimer=null;
        }
      }
    }catch(e){}
  }, 4000); // Poll every 4 seconds
}

// Start polling whenever tasks are loaded
const _origLoadTasks = typeof loadTasks==='function' ? loadTasks : null;

// ── Inline Task Terminals (per-step) ──
const _taskTermSources={};  // termId -> EventSource

function toggleTaskTerm(termId){
  const body=document.getElementById('tt-body-'+termId);
  if(!body)return;
  const wasOpen=body.classList.contains('open');
  body.classList.toggle('open');
  if(!wasOpen) connectTaskTerminal(termId);
}

function connectTaskTerminal(termId){
  if(_taskTermSources[termId])return; // already connected
  const sidEl=document.getElementById('tt-sid-'+termId);
  if(!sidEl)return;
  const sid=sidEl.textContent.trim();
  if(!sid)return;
  const body=document.getElementById('tt-body-'+termId);
  const dotEl=document.getElementById('tt-dot-'+termId);
  const stEl=document.getElementById('tt-st-'+termId);
  const elEl=document.getElementById('tt-el-'+termId);
  if(!body)return;

  // First fetch existing output
  fetch(`${A}/claude-sessions/${sid}`).then(r=>r.json()).then(d=>{
    if(d.output&&d.output.length){
      d.output.forEach(line=>{
        const div=document.createElement('div');
        div.className='tl';
        div.textContent=line.replace(/\n$/,'');
        body.appendChild(div);
      });
      body.scrollTop=body.scrollHeight;
    }
    if(dotEl)dotEl.className='tt-dot '+(d.status==='running'?'running':d.status==='completed'?'done':'err');
    if(stEl){stEl.textContent=d.status==='running'?'● running':d.status==='completed'?'✓ done':'✗ '+d.status;stEl.style.color=d.status==='running'?'oklch(0.52 0.04 160)':d.status==='completed'?'oklch(0.52 0.04 160)':'oklch(0.48 0.07 22)'}
    if(d.status!=='running')return; // no need to stream
    // Connect SSE for live updates
    const es=new EventSource(`${A}/claude-sessions/${sid}/stream`);
    _taskTermSources[termId]=es;
    let lineCount=d.output?d.output.length:0;
    const startT=Date.now();
    const timer=setInterval(()=>{if(elEl){const s=Math.floor((Date.now()-startT)/1000);elEl.textContent=`${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`}},1000);
    es.onmessage=(e)=>{
      lineCount++;
      const div=document.createElement('div');
      div.className='tl';
      if(e.data.startsWith('❌'))div.classList.add('tl-err');
      else if(e.data.startsWith('✅')||e.data.includes('passed'))div.classList.add('tl-ok');
      div.textContent=e.data;
      body.appendChild(div);
      body.scrollTop=body.scrollHeight;
    };
    es.addEventListener('done',(e)=>{
      try{const d=JSON.parse(e.data);if(dotEl)dotEl.className='tt-dot '+(d.status==='completed'?'done':'err');if(stEl){stEl.textContent=d.status==='completed'?'✓ done':'✗ '+d.status;stEl.style.color=d.status==='completed'?'oklch(0.52 0.04 160)':'oklch(0.48 0.07 22)'}}catch(ex){}
      clearInterval(timer);es.close();delete _taskTermSources[termId];
    });
    es.onerror=()=>{clearInterval(timer);es.close();delete _taskTermSources[termId];if(stEl){stEl.textContent='⚠ lost';stEl.style.color='oklch(0.56 0.05 70)'}};
  }).catch(()=>{});
}

function connectAllTaskTerminals(){
  document.querySelectorAll('.task-term').forEach(el=>{
    const id=el.id.replace('tt-','');
    const body=document.getElementById('tt-body-'+id);
    if(body&&body.classList.contains('open'))connectTaskTerminal(id);
  });
}

async function startClaudeForTask(taskId){
  toast('正在启动 Claude Code...');
  const r=await api(`${A}/teams/${tid}/tasks/${taskId}/workflow/run-claude`,{method:'POST'});
  if(r&&r.session_id){
    toast('Claude Code 已启动');
    loadTasks();
    setTimeout(()=>connectAllTaskTerminals(),500);
  }else{toast(r?r.status||'失败':'启动失败')}
}

function stopTaskTerm(sid){
  fetch(`${A}/claude-sessions/${sid}/stop`,{method:'POST'});
  toast('已停止');
}

function expandTaskTerm(termId){
  // Open in the full terminal overlay
  const sidEl=document.getElementById('tt-sid-'+termId);
  if(!sidEl)return;
  const sid=sidEl.textContent.trim();
  if(sid) openClaudeTerm(sid);
}

async function stepClick(taskId,stepIndex,currentStatus){
  // Click on a step: toggle completed/pending, or activate
  let newStatus;
  if(currentStatus==='completed') newStatus='pending';
  else if(currentStatus==='pending') newStatus='completed';
  else if(currentStatus==='active') newStatus='completed';
  else newStatus='pending';
  const r=await api(`${A}/teams/${tid}/tasks/${taskId}/workflow/${stepIndex}/status`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:newStatus})});
  if(r){loadTasks()}else{toast('更新失败')}
}

async function loadTasks(){
  const[tasks,stats]=await Promise.all([api(`${A}/teams/${tid}/tasks`),api(`${A}/tasks/stats`)]);
  const tb=el('tasks-tb'),st=el('task-stats');
  if(stats){const s=stats.by_status||{};st.innerHTML=`<span class="chip" style="background:rgba(53,200,255,0.1)">并发: ${stats.max_concurrency}</span><span class="chip">${stats.total||0} 总</span>${s.running?`<span class="chip" style="background:rgba(53,200,255,0.15);color:var(--cyan-s)">${s.running} 运行中</span>`:''}${s.completed?`<span class="chip" style="background:rgba(152,245,167,0.15);color:var(--lime)">${s.completed} 完成</span>`:''}`}
  if(!tasks||!tasks.length){tb.innerHTML='<tr><td colspan="7" style="color:var(--dim)">暂无任务 — 点击「提交任务」开始并发执行</td></tr>';return}
  tb.innerHTML=tasks.map(t=>{
    let actions='';
    const hasWf=t.metadata&&t.metadata.workflow&&t.metadata.workflow.length>0;
    const wfAllDone=hasWf&&t.metadata.workflow.every(s=>s.status==='completed'||s.status==='skipped');
    const delBtn=`<button class="btn btn-sm" style="padding:2px 8px;font-size:11px;color:oklch(0.55 0.005 110)" onclick="taskAction('${t.task_id}','delete')" title="删除任务">🗑</button>`;
    const ecoBtn=` <button class="btn btn-sm" style="padding:2px 8px;font-size:11px;background:rgba(167,139,250,0.12);color:var(--purple)" onclick="sendTaskToEcoField('${t.task_id}')" title="带本团队+任务进入办公室物竞试验田">🧬 物竞</button>`;
    if(t.status==='pending') actions=`<button class="btn btn-sm" style="padding:2px 8px;font-size:11px;background:rgba(53,200,255,0.1);color:var(--cyan-s)" onclick="taskAction('${t.task_id}','start')">▶ 开始</button>${ecoBtn} <button class="btn btn-danger btn-sm" onclick="taskAction('${t.task_id}','cancel')">取消</button> ${delBtn}`;
    else if(t.status==='running'){
      if(hasWf&&!wfAllDone){
        // Workflow in progress — only show fail button, no manual complete
        actions=`<span style="font-size:11px;color:var(--dim)">流程进行中</span> <button class="btn btn-sm" style="padding:2px 8px;font-size:11px;background:rgba(224,27,36,0.1);color:var(--red)" onclick="taskAction('${t.task_id}','fail')">✗ 失败</button>${ecoBtn}`;
      } else {
        actions=`<button class="btn btn-sm" style="padding:2px 8px;font-size:11px;background:rgba(152,245,167,0.15);color:var(--lime)" onclick="taskAction('${t.task_id}','complete')">✓ 完成</button> <button class="btn btn-sm" style="padding:2px 8px;font-size:11px;background:rgba(224,27,36,0.1);color:var(--red)" onclick="taskAction('${t.task_id}','fail')">✗ 失败</button>${ecoBtn}`;
      }
    }
    else if(t.status==='completed') actions=`<span style="color:var(--lime)">✓</span>${ecoBtn} ${delBtn}`;
    else if(t.status==='cancelled'||t.status==='failed') actions=`${ecoBtn} ${delBtn}`;
    else actions=ecoBtn;
    const src=t.metadata&&t.metadata.cross_team?`<span class="chip" style="font-size:9px;background:rgba(245,158,11,0.1);color:oklch(0.56 0.05 70)">跨团队 ← ${t.metadata.source_agent||t.metadata.source_team||''}</span>`:'';
    const wfHtml=renderWorkflow(t);
    const wfProgress=t.metadata&&t.metadata.workflow?(() => {const w=t.metadata.workflow;const done=w.filter(s=>s.status==='completed').length;return `<span style="font-size:10px;color:var(--dim);margin-left:6px">${done}/${w.length}</span>`})():'';
    return `<tr><td style="font-family:'IBM Plex Mono',monospace;font-size:11px">${escapeHtml(t.task_id)}</td><td style="min-width:280px"><b>${escapeHtml(t.title)}</b>${src}${wfProgress}${t.description?`<br><span style="color:var(--dim);font-size:11px">${escapeHtml(t.description.slice(0,80))}</span>`:''}${wfHtml}</td><td>${t.agent_id||'<span style="color:var(--dim)">自动</span>'}</td><td>${PRIO_LBL[t.priority]||t.priority}</td><td>${t.dependencies&&t.dependencies.length?t.dependencies.map(d=>'<span class="chip" style="font-size:10px">'+d+'</span>').join(''):'—'}</td><td><span class="st ${TST_CLS[t.status]||''}">${TST_LBL[t.status]||t.status}</span></td><td style="white-space:nowrap">${actions}</td></tr>`;
  }).join('');
  // populate agent select in modal
  const tm=await api(`${A}/teams/${tid}`);const sel=el('tk-agent');if(tm&&tm.agents){const aa=Array.isArray(tm.agents)?tm.agents:Object.values(tm.agents);sel.innerHTML='<option value="">自动分配</option>'+aa.map(a=>`<option value="${a.agent_id}">${a.name||a.agent_id}</option>`).join('')}
  // Start workflow auto-polling if any active steps exist
  if(tasks&&tasks.some(t=>t.metadata&&t.metadata.workflow&&t.metadata.workflow.some(s=>s.status==='active'))){
    startWorkflowPoll();
  }
}
async function taskAction(id,action){
  if(action==='delete'){
    if(!confirm('确定要永久删除此任务吗？')) return;
    await fetch(`${A}/teams/${tid}/tasks/${id}/remove`,{method:'DELETE'});toast('任务已删除');
  }
  else if(action==='cancel'){await fetch(`${A}/teams/${tid}/tasks/${id}`,{method:'DELETE'});toast('已取消')}
  else if(action==='start'){
    // Pre-execution environment check — advisory only. Backend is the source of truth.
    toast('⏳ 正在检查执行环境...');
    try{
      const h=await fetch('/api/v1/token-factory/health');
      if(!h.ok){
        toast(`⚠️ 未找到执行环境健康接口 (HTTP ${h.status})，直接尝试启动任务`);
      } else {
      const hd=await h.json();
      const providers=(hd&&hd.providers)||{};
      const ollama=(hd.providers&&hd.providers.ollama_local)||{};
      const deepseek=providers.deepseek||{};
      const claudeCode=providers.claude_code||{};
      const readyViaClaude=!!claudeCode.ok;
      const readyViaDeepSeek=!!deepseek.reachable;
      const readyViaOllama=!!ollama.reachable;
      const envReady=!!hd.ready||readyViaClaude||readyViaDeepSeek||readyViaOllama;
      if(!envReady){
        const go=confirm('⚠️ 执行环境未就绪！\n\n未检测到可用的执行链路。\n\nDeepSeek: '+(deepseek.reachable?'在线':'离线 ('+(deepseek.error||'未知错误')+')')+'\nClaude Code: '+(claudeCode.ok?'就绪':'未就绪')+'\nOllama: '+(ollama.reachable?'在线':'离线 ('+(ollama.error||'未知错误')+')')+'\n\n请先确保 DeepSeek / Claude Code 或 Ollama 至少有一条链路可用。\n\n是否仍然强制启动任务？');
        if(!go){toast('❌ 任务未启动 — 请先确保 Token 工厂就绪');return}
      } else {
        const readyLabel=readyViaClaude
          ? `Claude Code → DeepSeek ${claudeCode.latency_ms||deepseek.latency_ms||'--'}ms`
          : readyViaDeepSeek
            ? `DeepSeek ${deepseek.latency_ms||'--'}ms`
            : `Ollama ${ollama.latency_ms||'--'}ms`;
        toast(`✅ 执行环境就绪 — ${readyLabel}`);
      }
      }
    }catch(e){
      toast('⚠️ 执行环境检查失败，直接尝试启动任务: '+e.message);
    }
    const resp=await fetch(`${A}/teams/${tid}/tasks/${id}/start`,{method:'POST'});
    const body=await resp.json().catch(()=>null);
    if(!resp.ok){
      toast('❌ 启动失败: '+((body&&body.detail)||`HTTP ${resp.status}`));
      return;
    }
    if(body&&body.metadata&&body.metadata.token_factory_error){
      toast('⚠️ '+body.metadata.token_factory_error);
    }else{
      toast('任务已开始');
    }
  }
  else{await fetch(`${A}/teams/${tid}/tasks/${id}/${action}`,{method:'POST'});toast(action==='complete'?'任务已完成':'任务已标记失败')}
  loadTasks()
}

// ── Create team ──
el('btn-ct').onclick=async()=>{const n=el('ct-name').value.trim();if(!n){toast('请输入名称');return}el('btn-ct').disabled=true;el('btn-ct').textContent='创建中...';try{const r=await api(`${A}/teams`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n,description:el('ct-desc').value.trim()})});if(r&&r.team_id){toast('✅ 团队创建成功');closeModal('modal-create-team');el('ct-name').value='';el('ct-desc').value='';tid=r.team_id;loadTeams()}else{toast('❌ 创建失败，请检查后端日志')}}finally{el('btn-ct').disabled=false;el('btn-ct').textContent='创建'}};
// ── Add model ──
el('btn-am').onclick=async()=>{const n=el('am-name').value.trim();if(!n){toast('请输入模型名');return}const r=await api(`${A}/teams/${tid}/models`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider:el('am-prov').value,name:n,max_tokens:+el('am-tok').value,temperature:+el('am-temp').value,api_key:el('am-key').value,api_base_url:el('am-url').value,is_default:el('am-def').value==='true'})});if(r){toast('添加成功');closeModal('modal-add-model');el('am-name').value='';el('am-key').value='';el('am-url').value='';loadModels()}else toast('失败')};
// ── Submit task ──
el('btn-tk').onclick=async()=>{if(!tid){toast('请先选择一个团队');return}const t=el('tk-title').value.trim();if(!t){toast('请输入标题');return}el('btn-tk').disabled=true;el('btn-tk').textContent='提交中...';try{const deps=el('tk-deps').value.trim();const r=await api(`${A}/teams/${tid}/tasks`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:t,description:el('tk-desc').value.trim(),agent_id:el('tk-agent').value||'',priority:+el('tk-prio').value,dependencies:deps?deps.split(',').map(s=>s.trim()).filter(Boolean):[]})});if(r){toast(`✅ 任务 ${r.task_id||''} 已提交`);closeModal('modal-add-task');el('tk-title').value='';el('tk-desc').value='';el('tk-deps').value='';loadTasks()}else{toast('❌ 提交失败，请检查后端日志')}}finally{el('btn-tk').disabled=false;el('btn-tk').textContent='提交'}};
// ── Batch submit ──
el('btn-bt').onclick=async()=>{if(!tid){toast('请先选择一个团队');return}try{const j=JSON.parse(el('bt-json').value);if(!Array.isArray(j)||!j.length){toast('需要非空 JSON 数组');return}for(const t of j){if(!t.title){toast('每个任务必须有 title 字段');return}}el('btn-bt').disabled=true;el('btn-bt').textContent='提交中...';const r=await api(`${A}/teams/${tid}/tasks/batch`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tasks:j})});if(r){toast(`✅ ${Array.isArray(r)?r.length:j.length} 个任务已提交`);closeModal('modal-batch-task');el('bt-json').value='';loadTasks()}else{toast('❌ 批量提交失败，请检查后端日志')}}catch(e){toast('JSON 格式错误: '+e.message)}finally{el('btn-bt').disabled=false;el('btn-bt').textContent='批量提交'}};
// ── Close modals ──
document.querySelectorAll('.modal-overlay').forEach(o=>{o.addEventListener('mousedown',e=>{if(e.target===o)o.classList.remove('open')});const mc=o.querySelector('.modal');if(mc)mc.addEventListener('mousedown',e=>e.stopPropagation())});

// ══════════════════════════════════
//  OPENCLAW IMPORT
// ══════════════════════════════════
let _ocMode='openclaw',_ocVis='public';
function setOcMode(m){_ocMode=m;el('oc-mode-platform').classList.toggle('selected',m==='platform');el('oc-mode-openclaw').classList.toggle('selected',m==='openclaw');el('oc-form').style.display=m==='openclaw'?'block':'none';if(m==='platform'){closeModal('modal-import-openclaw');openWizard()}}
function setOcVis(v){_ocVis=v;el('oc-vis-public').classList.toggle('selected',v==='public');el('oc-vis-private').classList.toggle('selected',v==='private')}

el('btn-oc').onclick=async()=>{const n=el('oc-name').value.trim();if(!n){toast('智能体名称不能为空');return}const gw=el('oc-url').value.trim();if(!gw){toast('请输入 OpenClaw Gateway URL');return}const tk=el('oc-token').value.trim();if(!tk){toast('请输入 API Token');return}const t=el('oc-team').value||tid;const r=await api(`${A}/teams/${t}/agents/import-openclaw`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n,role:el('oc-role').value.trim(),openclaw_url:gw,openclaw_token:tk,visibility:_ocVis})});if(r){toast(`${n} 已连接！`);closeModal('modal-import-openclaw');el('oc-name').value='';el('oc-role').value='';el('oc-url').value='';el('oc-token').value='';tid=t;aid=r.agent_id;loadTeams()}else toast('连接失败')};

// populate OC team select when modal opens
const _origOpen=openModal;
openModal=function(id){_origOpen(id);if(id==='modal-import-openclaw'){api(`${A}/teams`).then(ts=>{const s=el('oc-team');s.innerHTML='';(ts||[]).forEach(t=>{const o=document.createElement('option');o.value=t.team_id;o.textContent=t.name;if(t.team_id===tid)o.selected=true;s.appendChild(o)})})}};

// ══════════════════════════════════
//  SESSION PERSISTENCE (claw-code-parity)
// ══════════════════════════════════
function showToolSearch(){el('tools-search-bar').classList.remove('hidden');el('tools-search-input').focus()}
function filterToolCards(q){
  const cards=el('tools-cards').querySelectorAll('[data-tool-name]');
  cards.forEach(c=>{const n=c.dataset.toolName||'';c.style.display=(!q||n.toLowerCase().includes(q.toLowerCase()))?'':'none'});
}
async function loadPersistedSessions(){
  const d=await api(`${A}/sessions/persisted`);
  const ls=el('ss-list'),ct=el('ss-count');
  if(!d||!d.sessions||!d.sessions.length){
    ls.innerHTML='<div style="padding:20px;text-align:center;color:var(--dim)"><div style="font-size:32px;margin-bottom:8px">📂</div><div style="font-size:14px;margin-bottom:6px">暂无已保存的会话</div><div style="font-size:12px">在 Agent 聊天中与智能体对话后，会话将自动出现在此处。<br>您也可以通过 API 调用 <code>POST /sessions/{id}/persist</code> 手动保存。</div></div>';
    ct.textContent='0 个会话';return;
  }
  ct.textContent=`${d.count} 个会话`;
  ls.innerHTML=d.sessions.map(sid=>`<div class="ws-item" style="cursor:pointer" data-sid="${escapeHtml(sid)}"><span class="fname"><span style="font-size:16px">💬</span> ${escapeHtml(sid)}</span><span style="display:flex;gap:8px"><button class="btn btn-sm" data-action="load" title="加载到活跃会话">📂 加载</button><button class="btn btn-sm btn-ghost" data-action="preview" title="预览">👁</button></span></div>`).join('');
  // Event delegation for session actions (XSS-safe)
  ls.onclick=function(e){
    const item=e.target.closest('[data-sid]');if(!item)return;
    const sid=item.dataset.sid;
    const btn=e.target.closest('[data-action]');
    if(btn){
      if(btn.dataset.action==='load')persistSessionToActive(sid);
      else if(btn.dataset.action==='preview')previewPersistedSession(sid);
    }else{loadPersistedSession(sid)}
  };
}
async function loadPersistedSession(sid){
  const d=await api(`${A}/sessions/persisted/${sid}/load`,{method:'POST'});
  if(d){toast(`会话 ${sid.slice(0,8)} 已加载到内存`)}else{toast('加载失败')}
}
function persistSessionToActive(sid){loadPersistedSession(sid)}
async function previewPersistedSession(sid){
  const d=await api(`${A}/sessions/persisted/${sid}/load`,{method:'POST'});
  if(!d){toast('无法加载会话');return}
  const msgs=(d.messages||[]).slice(-20);
  let html=`<div class="modal-overlay open" id="modal-preview-session" onclick="if(event.target===this)this.remove()"><div class="modal" style="width:640px;max-height:85vh"><h3>💬 会话预览</h3><div style="margin-bottom:12px;font-size:12px;color:var(--muted)"><b>会话 ID</b>: ${escapeHtml(sid)}<br><b>消息数</b>: ${d.message_count||msgs.length} · <b>创建</b>: ${d.created_at||'?'}</div><div style="max-height:50vh;overflow-y:auto;border:1px solid var(--line);border-radius:0;padding:12px">`;
  if(msgs.length){msgs.forEach(m=>{const isUser=m.role==='user';html+=`<div style="margin-bottom:10px;padding:10px 14px;background:${isUser?'var(--chat-user)':'var(--chat-agent)'};border:1px solid ${isUser?'var(--chat-user-border)':'var(--chat-agent-border)'};border-radius:0"><div style="font-size:11px;font-weight:600;color:var(--muted);margin-bottom:4px">${escapeHtml(m.role||'?')}</div><div style="font-size:13px;white-space:pre-wrap;word-break:break-word">${escapeHtml((m.content||'').slice(0,500))}</div></div>`})}
  else{html+='<p style="color:var(--dim)">无消息记录</p>'}
  html+=`</div><div class="modal-actions"><button class="btn" onclick="document.getElementById('modal-preview-session').remove()">关闭</button><button class="btn btn-pink" onclick="loadPersistedSession('${escapeHtml(sid)}');document.getElementById('modal-preview-session').remove()">📂 加载到活跃会话</button></div></div></div>`;
  document.body.insertAdjacentHTML('beforeend',html);
}
async function searchPersistedSessions(){
  const q=el('ss-query').value.trim();
  if(!q){toast('请输入搜索关键词');return}
  const d=await api(`${A}/sessions/search`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q,max_results:20})});
  const rc=el('ss-search-results');
  if(!d||!d.results||!d.results.length){
    rc.innerHTML='<p style="color:var(--dim)">未找到匹配结果</p>';return;
  }
  rc.innerHTML=`<p style="color:var(--muted);font-size:12px;margin-bottom:8px">找到 ${d.count} 个结果</p>`+
    d.results.map(r=>`<div class="focus-item" style="padding:10px 14px;cursor:pointer" onclick="loadPersistedSession('${escapeHtml(r.session_id||r.id||'')}')"><div class="title"><span class="chip" style="font-size:10px">${escapeHtml(r.session_id||r.id||'').slice(0,8)}</span> ${escapeHtml((r.snippet||r.content||'').slice(0,120))}</div><div class="meta">${r.score?`相关度: ${(r.score*100).toFixed(0)}%`:''}</div></div>`).join('');
}

// ══════════════════════════════════
//  PORT RUNTIME (claw-code-parity)
// ══════════════════════════════════
function _rtParams(){
  return{
    prompt:el('rt-prompt').value.trim(),
    limit:parseInt(el('rt-limit').value)||5,
    deny_tools:(el('rt-deny').value||'').split(',').map(s=>s.trim()).filter(Boolean),
    deny_prefixes:(el('rt-deny-pfx').value||'').split(',').map(s=>s.trim()).filter(Boolean)
  };
}
async function doRoutePrompt(){
  const p=_rtParams();if(!p.prompt){toast('请输入 Prompt');return}
  toast('正在路由匹配...');
  const d=await api(`${A}/runtime/route`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)});
  const rc=el('rt-results'),rcc=el('rt-results-content');rc.classList.remove('hidden');
  if(!d){rcc.innerHTML='<p style="color:var(--pink)">路由失败 — 后端 PortRuntime 服务可能未就绪，请检查后端日志</p>';return}
  if(!d.matches||!d.matches.length){rcc.innerHTML='<p style="color:var(--dim)">未匹配到工具/命令 — 尝试更具体的 Prompt</p>';return}
  rcc.innerHTML=`<p style="color:var(--muted);font-size:12px;margin-bottom:12px">匹配到 ${d.count||d.matches.length} 个工具/命令</p><table class="tbl"><thead><tr><th>类型</th><th>名称</th><th>来源</th><th>得分</th></tr></thead><tbody>${d.matches.map(m=>`<tr><td><span class="chip" style="font-size:10px;background:${m.kind==='tool'?'rgba(38,162,105,0.1);color:var(--lime)':'rgba(26,95,180,0.1);color:var(--cyan)'}">${m.kind}</span></td><td><b>${escapeHtml(m.name)}</b></td><td style="color:var(--muted)">${escapeHtml(m.source_hint||'-')}</td><td style="font-family:'IBM Plex Mono',monospace">${(m.score||0).toFixed(2)}</td></tr>`).join('')}</tbody></table>`;
}
async function doBootstrapSession(){
  const p=_rtParams();if(!p.prompt){toast('请输入 Prompt');return}
  toast('正在引导会话...');
  const d=await api(`${A}/runtime/bootstrap`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)});
  const rc=el('rt-results'),rcc=el('rt-results-content');rc.classList.remove('hidden');
  if(!d){rcc.innerHTML='<p style="color:var(--pink)">引导失败 — 后端 PortRuntime 服务可能未就绪，请检查后端日志</p>';return}
  let html=`<div class="card-grid">
    <div class="stat-card"><div class="label">🎯 匹配数</div><div class="value">${(d.matches||[]).length}</div></div>
    <div class="stat-card"><div class="label">🔧 工具结果</div><div class="value">${(d.tool_results||[]).length}</div></div>
    <div class="stat-card"><div class="label">⚙️ 命令结果</div><div class="value">${(d.command_results||[]).length}</div></div>
    <div class="stat-card"><div class="label">🚫 权限拒绝</div><div class="value" style="color:${(d.denials||[]).length?'var(--red)':'var(--lime)'}">${(d.denials||[]).length}</div></div>
  </div>`;
  if(d.matches&&d.matches.length){html+=`<div class="section" style="margin-top:16px"><div class="section-title">路由匹配</div>${d.matches.map(m=>`<div class="ws-item"><span class="fname"><span class="chip" style="font-size:10px">${m.kind}</span> ${m.name}</span><span style="font-family:'IBM Plex Mono',monospace;color:var(--dim)">${m.score.toFixed(2)}</span></div>`).join('')}</div>`;}
  if(d.tool_results&&d.tool_results.length){html+=`<div class="section" style="margin-top:16px"><div class="section-title">🔧 工具执行结果</div>${d.tool_results.map(r=>`<div class="focus-item"><div class="title"><span class="chip">${r.name}</span> ${r.handled?'✅':'❌'}</div><div style="margin-top:8px;padding:10px;background:rgba(232,240,250,0.7);border-radius:6px;font-size:12px;font-family:'IBM Plex Mono',monospace;max-height:120px;overflow-y:auto;white-space:pre-wrap">${escapeHtml(r.output||'(无输出)')}</div></div>`).join('')}</div>`;}
  if(d.denials&&d.denials.length){html+=`<div class="section" style="margin-top:16px"><div class="section-title" style="color:var(--red)">🚫 权限拒绝</div>${d.denials.map(dn=>`<div class="ws-item" style="border-color:rgba(224,27,36,0.2)"><span class="fname" style="color:var(--red)">${dn.tool_name}</span><span style="color:var(--muted)">${dn.reason}</span></div>`).join('')}</div>`;}
  if(d.history&&d.history.length){html+=`<div class="section" style="margin-top:16px"><div class="section-title">📜 执行历史</div>${d.history.slice(-8).map(h=>`<div class="focus-item" style="padding:8px 14px"><div class="title" style="font-size:12px"><span class="chip" style="font-size:10px">${h.kind||h.type||'event'}</span> ${escapeHtml(h.summary||h.detail||'')}</div><div class="meta">${h.ts||h.timestamp||''}</div></div>`).join('')}</div>`;}
  rcc.innerHTML=html;
}
async function doRouteAndChat(){
  const p=_rtParams();if(!p.prompt){toast('请输入 Prompt');return}
  toast('路由+对话...');
  const d=await api(`${A}/runtime/route-and-chat`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)});
  const rc=el('rt-results'),rcc=el('rt-results-content');rc.classList.remove('hidden');
  if(!d){rcc.innerHTML='<p style="color:var(--pink)">请求失败 — 请先在「LLM 配置」中配置提供商和 API Key</p>';return}
  rcc.innerHTML=`<div class="card-grid">
    <div class="stat-card"><div class="label">🎯 路由匹配</div><div class="value">${d.matched_count||d.matches?.length||0}</div></div>
    <div class="stat-card"><div class="label">📊 Tokens</div><div class="value">${(d.usage?.total_tokens||0).toLocaleString()}</div></div>
  </div>
  <div class="section" style="margin-top:16px"><div class="section-title">💬 LLM 回复</div><div style="padding:16px;background:rgba(232,240,250,0.7);border-radius:0;font-size:13px;line-height:1.7;white-space:pre-wrap">${escapeHtml(d.response||d.content||d.answer||'(无回复)')}</div></div>`;
}
async function doAssemblePool(){
  const body={
    simple_mode:el('tp-simple').checked,
    include_mcp:el('tp-mcp').checked,
    deny_tools:(el('tp-deny').value||'').split(',').map(s=>s.trim()).filter(Boolean),
    deny_prefixes:(el('tp-deny-pfx').value||'').split(',').map(s=>s.trim()).filter(Boolean)
  };
  const d=await api(`${A}/tool-pool`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const rc=el('tp-results');
  if(!d){rc.innerHTML='<p style="color:var(--pink)">装配失败 — 后端 Tool Pool 服务未就绪</p>';return}
  rc.innerHTML=`<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px"><span class="chip" style="background:rgba(38,162,105,0.1);color:var(--lime)">共 ${d.count} 个工具</span>${d.simple_mode?'<span class="chip" style="background:rgba(255,207,112,0.15);color:var(--amber)">简单模式</span>':''}${d.include_mcp?'<span class="chip">含 MCP</span>':''}</div>
  <div style="display:flex;gap:6px;flex-wrap:wrap">${(d.tools||[]).map(t=>`<span class="chip" style="font-size:11px">${escapeHtml(t)}</span>`).join('')}</div>`;
}

// ══════════════════════════════════
//  TOKEN FACTORY — 自主 Token 工厂
// ══════════════════════════════════
const TF='/api/v1/token-factory';
let _tfPollTimer=null;
function _startTfPoll(){if(_tfPollTimer)clearInterval(_tfPollTimer);_tfPollTimer=setInterval(()=>{if(document.querySelector('#view-registry:not(.hidden)'))loadTokenFactory();else{clearInterval(_tfPollTimer);_tfPollTimer=null}},5000)}
async function loadTokenFactory(){
  try{
    const r=await fetch(`${TF}/health`);
    if(!r.ok){el('tf-health').innerHTML=`<p style="color:oklch(0.48 0.07 22)">API 错误: HTTP ${r.status}</p>`;return}
    const d=await r.json();
    if(!d){el('tf-health').innerHTML='<p style="color:var(--dim)">Token Factory 返回空数据</p>';return}
  // Health overview
  const ready=d.ready;
  const providers=d.providers||{};
  const ollama=providers.ollama_local||{};
  const deepseek=providers.deepseek||{};
  const cc=providers.claude_code||{};
  const tunnel=d.tunnel||{};
  let html='<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px">';
  html+=`<div style="text-align:center;padding:14px;background:rgba(0,0,0,.1);border-radius:0"><div style="font-size:24px;margin-bottom:4px">${ready?'🟢':'🔴'}</div><div style="font-size:11px;color:var(--muted)">整体状态</div><div style="font-weight:600;font-size:13px">${ready?'就绪':'不可用'}</div></div>`;
  html+=`<div style="text-align:center;padding:14px;background:rgba(0,0,0,.1);border-radius:0"><div style="font-size:24px;margin-bottom:4px">${ollama.reachable?'🦙':'⬛'}</div><div style="font-size:11px;color:var(--muted)">Ollama</div><div style="font-weight:600;font-size:13px;color:${ollama.reachable?'var(--lime)':'var(--dim)'}">${ollama.reachable?ollama.latency_ms+'ms':'离线'}</div></div>`;
  html+=`<div style="text-align:center;padding:14px;background:rgba(0,0,0,.1);border-radius:0"><div style="font-size:24px;margin-bottom:4px">${cc.ok?'☁️':'⬛'}</div><div style="font-size:11px;color:var(--muted)">Claude via DeepSeek</div><div style="font-weight:600;font-size:13px;color:${cc.ok?'var(--lime)':'var(--dim)'}">${cc.ok?'就绪':(deepseek.reachable?deepseek.latency_ms+'ms':(deepseek.error||'离线'))}</div></div>`;
  html+=`<div style="text-align:center;padding:14px;background:rgba(0,0,0,.1);border-radius:0"><div style="font-size:24px;margin-bottom:4px">${tunnel.state==='running'?'🔗':'🔌'}</div><div style="font-size:11px;color:var(--muted)">SSH 隧道</div><div style="font-weight:600;font-size:13px;color:${tunnel.state==='running'?'var(--lime)':'var(--dim)'}">${tunnel.state==='running'?'PID '+tunnel.pid:'停止'}</div></div>`;
  html+='</div>';
  if(d.ollama_models&&d.ollama_models.length){
    html+=`<div style="margin-top:14px;font-size:12px;color:var(--muted)">可用模型: <span style="color:var(--lime);font-family:'IBM Plex Mono',monospace">${d.ollama_models.join(', ')}</span></div>`;
  }
  el('tf-health').innerHTML=html;
  // Tunnel
  el('tf-tunnel-state').innerHTML=`<span style="color:${tunnel.state==='running'?'oklch(0.52 0.04 160)':'oklch(0.48 0.07 22)'}">${tunnel.state==='running'?'● 运行中':'○ 停止'}</span>${tunnel.pid?' — PID '+tunnel.pid:''}`;
  el('tf-tunnel-port').textContent=tunnel.config?.local_port||'11434';
  el('tf-tunnel-host').textContent=tunnel.config?.remote_host||'—';
  // Ollama models
  if(ollama.reachable&&ollama.models&&ollama.models.length){
    el('tf-ollama-models').innerHTML=ollama.models.map(m=>`<span style="display:inline-block;padding:3px 10px;margin:2px 4px;background:rgba(110,231,183,.12);border:1px solid rgba(110,231,183,.3);border-radius:4px;color:oklch(0.52 0.04 160)">${escapeHtml(m)}</span>`).join('');
  }else{
    el('tf-ollama-models').innerHTML='<span style="color:var(--dim)">未检测到模型</span>';
  }
  // DeepSeek — show Claude Code via DeepSeek result
  if(cc.ok){
    let h='<span style="color:oklch(0.52 0.04 160);font-weight:600">● 就绪</span> <span style="color:var(--muted);font-size:11px">— Claude Code 已通过 DeepSeek 返回响应 ('+cc.latency_ms+'ms)</span>';
    if(cc.reply){h+='<div style="margin-top:8px;padding:8px 12px;background:rgba(110,231,183,.08);border:1px solid rgba(110,231,183,.2);border-radius:6px;white-space:pre-wrap;color:oklch(0.18 0.008 110);font-size:12px;max-height:120px;overflow-y:auto">'+escapeHtml(cc.reply).slice(0,500)+'</div>'}
    el('tf-deepseek-status').innerHTML=h;
  }else if(deepseek.reachable){
    el('tf-deepseek-status').innerHTML='<span style="color:oklch(0.52 0.04 160)">● 在线</span> <span style="color:var(--muted);font-size:11px">— 点击 ⚡确保就绪 测试 Claude Code 链路</span>';
  }else{
    el('tf-deepseek-status').innerHTML='<span style="color:oklch(0.48 0.07 22)">○ '+(cc.error||deepseek.error||'离线')+'</span>';
  }
  }catch(e){el('tf-health').innerHTML=`<p style="color:oklch(0.48 0.07 22)">加载失败: ${e.message}</p>`;console.error('TokenFactory load error:',e)}
}
async function tfEnsureReady(){
  toast('正在确保推理服务就绪...');
  const d=await api(`${TF}/ensure-ready`,{method:'POST'});
  if(d&&d.ready){toast('✅ Token Factory 就绪')}else{toast('⚠️ 部分服务不可用')}
  loadTokenFactory();
}
async function tfTunnelStart(){
  toast('正在启动 SSH 隧道...');
  el('tf-tunnel-state').innerHTML='<span style="color:oklch(0.56 0.05 70)">⏳ 启动中...</span>';
  try{
    const ctrl=new AbortController();
    const tmr=setTimeout(()=>ctrl.abort(),15000);
    const r=await fetch(`${TF}/tunnel/start`,{method:'POST',signal:ctrl.signal});
    clearTimeout(tmr);
    const d=await r.json();
    if(d&&d.ok){
      toast('✅ 隧道已启动');
      el('tf-tunnel-state').innerHTML=`<span style="color:oklch(0.52 0.04 160)">● 运行中</span> — PID ${d.pid||'?'} — ${d.state}`;
    }else{
      toast('⚠️ 隧道启动失败');
      el('tf-tunnel-state').innerHTML=`<span style="color:oklch(0.48 0.07 22)">✕ 启动失败</span> — ${d.state||d.error||'未知错误'}`;
    }
  }catch(e){
    const msg=e.name==='AbortError'?'请求超时(15s)':e.message;
    toast('❌ 请求失败: '+msg);
    el('tf-tunnel-state').innerHTML=`<span style="color:oklch(0.48 0.07 22)">✕ ${msg}</span>`;
  }
  loadTokenFactory();
  setTimeout(loadTokenFactory,3000);
}
async function tfTunnelStop(){
  el('tf-tunnel-state').innerHTML='<span style="color:oklch(0.56 0.05 70)">⏳ 停止中...</span>';
  try{
    const ctrl=new AbortController();
    const tmr=setTimeout(()=>ctrl.abort(),10000);
    const r=await fetch(`${TF}/tunnel/stop`,{method:'POST',signal:ctrl.signal});
    clearTimeout(tmr);
    const d=await r.json();
    toast('隧道已停止');
    el('tf-tunnel-state').innerHTML=`<span style="color:oklch(0.55 0.005 110)">○ 已停止</span> — ${d.state||'stopped'}`;
  }catch(e){
    const msg=e.name==='AbortError'?'请求超时(10s)':e.message;
    toast('❌ 请求失败: '+msg);
    el('tf-tunnel-state').innerHTML=`<span style="color:oklch(0.48 0.07 22)">✕ ${msg}</span>`;
  }
  loadTokenFactory();
  setTimeout(loadTokenFactory,2000);
}
async function tfTestClaude(){
  const statusEl=el('tf-claude-test-status');
  const resultEl=el('tf-claude-test-result');
  statusEl.innerHTML='<span style="color:oklch(0.56 0.05 70)">⏳ 运行 claude -p "hi" ...</span>';
  resultEl.style.display='block';
  resultEl.innerHTML='<span style="color:oklch(0.56 0.05 70)">⏳ 正在通过 CLI 调用 Claude Code... (提示词: "hi")</span>';
  toast('正在测试 Claude Code CLI...');
  const ctrl=new AbortController();const tmr=setTimeout(()=>ctrl.abort(),15000);
  try{
    const r=await fetch(`${TF}/probe/claude`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:'hi'}),signal:ctrl.signal});
    clearTimeout(tmr);
    const d=await r.json();
    let html='';
    if(d.ok){
      statusEl.innerHTML='<span style="color:oklch(0.52 0.04 160)">✅ 测试通过</span>';
      html+=`<div style="color:oklch(0.52 0.04 160);font-weight:600;margin-bottom:8px">✅ Claude Code CLI 正常</div>`;
      html+=`<div><b>模型</b>: ${escapeHtml(d.model)}</div>`;
      html+=`<div><b>延迟</b>: ${d.latency_ms} ms</div>`;
      html+=`<div style="margin-top:8px;padding:10px 12px;background:rgba(110,231,183,.08);border:1px solid rgba(110,231,183,.2);border-radius:6px"><b>模型回复</b>:<div style="margin-top:4px;white-space:pre-wrap;color:oklch(0.18 0.008 110)">${escapeHtml(d.reply||'(空)')}</div></div>`;
      toast(`✅ Claude Code 测试通过 — ${d.latency_ms}ms`);
    }else{
      statusEl.innerHTML='<span style="color:oklch(0.48 0.07 22)">❌ 测试失败</span>';
      html+=`<div style="color:oklch(0.48 0.07 22);font-weight:600;margin-bottom:8px">❌ Claude Code CLI 异常</div>`;
      html+=`<div><b>模型</b>: ${escapeHtml(d.model)}</div>`;
      if(d.latency_ms) html+=`<div><b>延迟</b>: ${d.latency_ms} ms</div>`;
      if(d.error) html+=`<div style="margin-top:8px;padding:10px 12px;background:oklch(0.48 0.07 22 / .08);border:1px solid oklch(0.48 0.07 22 / .2);border-radius:6px;color:oklch(0.48 0.07 22)"><b>错误</b>: ${escapeHtml(d.error)}</div>`;
      toast('⚠️ Claude Code 测试失败');
    }
    resultEl.innerHTML=html;
  }catch(e){
    clearTimeout(tmr);
    const msg=e.name==='AbortError'?'请求超时(15s)，请检查服务状态':e.message;
    statusEl.innerHTML='<span style="color:oklch(0.48 0.07 22)">❌ 请求异常</span>';
    resultEl.innerHTML=`<div style="color:oklch(0.48 0.07 22)">❌ 请求失败: ${escapeHtml(msg)}</div>`;
    toast('❌ 测试请求失败: '+msg);
  }
}
async function tfTestClaudeReady(){
  const stEl=el('tf-claude-ready-status');
  const dsEl=el('tf-deepseek-status');
  stEl.innerHTML='<span style="color:oklch(0.56 0.05 70)">⏳ 正在测试 Claude Code → DeepSeek 链路...</span>';
  dsEl.innerHTML='<span style="color:oklch(0.56 0.05 70)">⏳ 运行 claude -p "hi" ，请稍候...</span>';
  toast('正在测试 Claude → DeepSeek 就绪...');
  const ctrl=new AbortController();const tmr=setTimeout(()=>ctrl.abort(),15000);
  try{
    const r=await fetch(`${TF}/probe/claude`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:'hi'}),signal:ctrl.signal});
    clearTimeout(tmr);
    const d=await r.json();
    if(d.ok){
      stEl.innerHTML='<span style="color:oklch(0.52 0.04 160)">✅ Claude 就绪</span>';
      let h='<span style="color:oklch(0.52 0.04 160);font-weight:600">● 就绪</span> <span style="color:var(--muted);font-size:11px">— Claude Code 已通过 DeepSeek 返回响应 ('+d.latency_ms+'ms)</span>';
      if(d.reply){h+='<div style="margin-top:8px;padding:8px 12px;background:rgba(110,231,183,.08);border:1px solid rgba(110,231,183,.2);border-radius:6px;white-space:pre-wrap;color:oklch(0.18 0.008 110);font-size:12px;max-height:120px;overflow-y:auto">'+escapeHtml(d.reply).slice(0,500)+'</div>'}
      dsEl.innerHTML=h;
      toast('✅ Claude via DeepSeek 就绪 — '+d.latency_ms+'ms');
    }else{
      stEl.innerHTML='<span style="color:oklch(0.48 0.07 22)">❌ 未就绪</span>';
      dsEl.innerHTML='<span style="color:oklch(0.48 0.07 22)">○ '+(d.error||'连接失败')+'</span>';
      toast('⚠️ Claude 未就绪: '+(d.error||''));
    }
  }catch(e){
    clearTimeout(tmr);
    const msg=e.name==='AbortError'?'请求超时(15s)，请检查服务状态':e.message;
    stEl.innerHTML='<span style="color:oklch(0.48 0.07 22)">❌ 请求异常</span>';
    dsEl.innerHTML='<span style="color:oklch(0.48 0.07 22)">○ '+escapeHtml(msg)+'</span>';
    toast('❌ 测试失败: '+msg);
  }finally{
    loadTokenFactory();
  }
}
async function tfProbeOllama(){
  toast('正在探测 Ollama...');
  const modelsEl=el('tf-ollama-models');
  modelsEl.innerHTML='<span style="color:oklch(0.56 0.05 70)">⏳ 探测中 http://127.0.0.1:11434 ...</span>';
  const ctrl=new AbortController();const tmr=setTimeout(()=>ctrl.abort(),15000);
  try{
    const r=await fetch(`${TF}/probe/ollama`,{signal:ctrl.signal});
    clearTimeout(tmr);
    const d=await r.json();
    let html='';
    if(d.reachable){
      const root=d.root||{};
      const tags=d.api_tags||{};
      html+=`<div style="margin-bottom:8px"><span style="color:oklch(0.52 0.04 160);font-weight:600">✅ Ollama 可达</span> — <code>${d.url}</code></div>`;
      html+=`<div style="font-size:12px;padding:8px 12px;background:rgba(0,0,0,.2);border-radius:6px;margin-bottom:6px">`;
      html+=`<div><b>GET /</b> → HTTP ${root.status} (${root.latency_ms}ms)</div>`;
      html+=`<div style="color:var(--muted);font-family:'IBM Plex Mono',monospace;font-size:11px;margin:4px 0">${escapeHtml((root.body||'').trim())}</div>`;
      html+=`<div style="margin-top:6px"><b>GET /api/tags</b> → HTTP ${tags.status} (${tags.latency_ms}ms) — ${tags.model_count} 个模型</div>`;
      if(tags.models&&tags.models.length){
        html+=`<div style="margin-top:4px">`+tags.models.map(m=>`<span style="display:inline-block;padding:2px 8px;margin:2px 3px;background:rgba(110,231,183,.12);border:1px solid rgba(110,231,183,.3);border-radius:4px;color:oklch(0.52 0.04 160);font-size:11px">${escapeHtml(m)}</span>`).join('')+'</div>';
      }
      html+=`</div>`;
      toast(`✅ Ollama 在线 — ${tags.model_count} 个模型, ${root.latency_ms}ms`);
    }else{
      html+=`<div style="color:oklch(0.48 0.07 22)">❌ Ollama 不可达 — <code>${d.url}</code></div>`;
      if(d.error) html+=`<div style="font-size:12px;color:oklch(0.48 0.07 22);margin-top:4px;padding:8px 12px;background:oklch(0.48 0.07 22 / .08);border-radius:6px;font-family:'IBM Plex Mono',monospace">${escapeHtml(d.error)}</div>`;
      toast('⚠️ Ollama 不可达: '+(d.error||''));
    }
    modelsEl.innerHTML=html;
  }catch(e){
    clearTimeout(tmr);
    const msg=e.name==='AbortError'?'请求超时(15s)，请检查 Ollama 服务':e.message;
    modelsEl.innerHTML=`<span style="color:oklch(0.48 0.07 22)">❌ 探测请求失败: ${escapeHtml(msg)}</span>`;
    toast('❌ 探测失败: '+msg);
  }
  setTimeout(loadTokenFactory,3000);
}

loadTeams();

// ═══ Phase 3: Performance Optimization ═══

document.addEventListener('visibilitychange',()=>{
  if(!document.hidden){
    const v=document.querySelector('.main-inner:not(.hidden)');
    if(v&&v.id==='view-overview')loadOverview();
  }
});

// Debounce utility
function debounce(fn,ms=300){let t;return(...a)=>{clearTimeout(t);t=setTimeout(()=>fn(...a),ms)}}

// SSE cleanup on page unload
window.addEventListener('beforeunload',()=>{
  if(_ovTimer){clearInterval(_ovTimer);_ovTimer=null}
});

// ═══ Phase 4: Interaction Experience ═══

// Enhanced toast with types
const _origToast=toast;
function toastTyped(msg,type='info'){
  const e=document.getElementById('toast');
  e.className='toast';
  if(type)e.classList.add('toast-'+type);
  e.textContent=msg;
  e.classList.add('show');
  setTimeout(()=>{e.classList.remove('show');e.className='toast'},3000);
}

// Keyboard navigation
document.addEventListener('keydown',e=>{
  // Escape closes modals
  if(e.key==='Escape'){
    document.querySelectorAll('.modal-overlay.open').forEach(m=>m.classList.remove('open'));
    document.querySelectorAll('.claude-term-overlay.open').forEach(m=>m.classList.remove('open'));
  }
  // Ctrl+K: focus search (if exists)
  if((e.ctrlKey||e.metaKey)&&e.key==='k'){
    const s=document.querySelector('.main-inner:not(.hidden) input[type="search"],input.fi[placeholder*="搜索"]');
    if(s){e.preventDefault();s.focus()}
  }
});

// Mobile sidebar toggle
(function(){
  const sidebar=document.querySelector('.sidebar');
  if(!sidebar)return;
  // ARIA roles
  sidebar.setAttribute('role','navigation');
  sidebar.setAttribute('aria-label','Agent 导航侧栏');
  sidebar.querySelectorAll('.sb-nav').forEach(n=>n.setAttribute('role','list'));
  sidebar.querySelectorAll('.sb-nav a').forEach(a=>a.setAttribute('role','listitem'));
  // Collapse memory
  const collapsed=localStorage.getItem('atc-sidebar-collapsed')==='1';
  if(collapsed)sidebar.classList.add('collapsed');
  // Add hamburger button for mobile
  const topbar=document.querySelector('.topbar-left');
  if(topbar){
    const btn=document.createElement('button');
    btn.className='btn btn-ghost sidebar-toggle';
    btn.innerHTML='☰';
    btn.setAttribute('aria-label','打开导航');
    btn.style.cssText='display:none;font-size:18px;padding:4px 8px';
    btn.onclick=()=>sidebar.classList.toggle('open');
    topbar.insertBefore(btn,topbar.firstChild);
    // Show on mobile
    const mq=window.matchMedia('(max-width:768px)');
    function check(e){btn.style.display=e.matches?'inline-flex':'none';if(!e.matches)sidebar.classList.remove('open')}
    mq.addEventListener('change',check);
    check(mq);
    // Desktop collapse toggle
    const colBtn=document.createElement('button');
    colBtn.className='btn btn-ghost';
    colBtn.style.cssText='position:absolute;bottom:8px;right:8px;font-size:14px;padding:4px 8px;opacity:0.5';
    colBtn.innerHTML='«';colBtn.title='折叠侧栏';
    colBtn.setAttribute('aria-label','折叠侧栏');
    colBtn.onclick=()=>{
      sidebar.classList.toggle('collapsed');
      const c=sidebar.classList.contains('collapsed');
      localStorage.setItem('atc-sidebar-collapsed',c?'1':'0');
      colBtn.innerHTML=c?'»':'«';
      colBtn.title=c?'展开侧栏':'折叠侧栏';
    };
    if(collapsed)colBtn.innerHTML='»';
    sidebar.style.position='relative';
    sidebar.appendChild(colBtn);
  }
  // Close sidebar on nav click (mobile)
  sidebar.querySelectorAll('.sb-nav a,.sb-agent').forEach(a=>{
    a.addEventListener('click',()=>{if(window.innerWidth<=768)sidebar.classList.remove('open')});
  });
})();

// ═══ Phase 5: Feature Enhancements ═══

// 5a. Search/filter for tools
(function(){
  const box=document.getElementById('tools-cards');
  if(!box)return;
  const parent=box.parentElement;
  const search=document.createElement('input');
  search.type='search';
  search.className='fi';
  search.placeholder='搜索工具名称或描述...';
  search.style.cssText='margin-bottom:12px;max-width:320px';
  parent.insertBefore(search,box);
  search.addEventListener('input',debounce(e=>{
    const q=e.target.value.toLowerCase();
    box.querySelectorAll('[data-tool-name]').forEach(card=>{
      const name=(card.dataset.toolName||'').toLowerCase();
      const desc=(card.textContent||'').toLowerCase();
      card.style.display=(name.includes(q)||desc.includes(q))?'':'none';
    });
  },200));
})();

// 5b. Team config export/import
async function exportTeamConfig(){
  if(!tid){toast('请先选择团队');return}
  const[info,models,tools,skills]=await Promise.all([
    api(`${A}/teams/${tid}`),
    api(`${A}/teams/${tid}/models`),
    api(`${A}/teams/${tid}/tools`),
    api(`${A}/teams/${tid}/skills`)
  ]);
  const cfg={team:info,models,tools,skills,exported_at:new Date().toISOString()};
  const blob=new Blob([JSON.stringify(cfg,null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');
  a.href=url;a.download=`team-${tid}-config.json`;
  document.body.appendChild(a);a.click();
  document.body.removeChild(a);URL.revokeObjectURL(url);
  toast('配置已导出');
}

async function importTeamConfig(){
  const input=document.createElement('input');
  input.type='file';input.accept='.json';
  input.onchange=async e=>{
    const file=e.target.files[0];if(!file)return;
    try{
      const text=await file.text();
      const cfg=JSON.parse(text);
      if(!cfg.team){toast('无效的配置文件');return}
      // Import models
      if(cfg.models&&Array.isArray(cfg.models)){
        for(const m of cfg.models){
          await api(`${A}/teams/${tid}/models`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(m)});
        }
      }
      toast(`已导入配置 (${cfg.models?.length||0} 模型)`);
      loadView();
    }catch(err){toast('导入失败: '+err.message)}
  };
  input.click();
}

// 5c. Batch operations for tools
async function batchEnableTools(enable){
  const box=document.getElementById('tools-cards');
  const checks=box.querySelectorAll('input[type="checkbox"]');
  let count=0;
  for(const chk of checks){
    if(chk.checked!==enable){
      const card=chk.closest('[data-tool-name]');
      if(card&&card.style.display!=='none'){
        chk.checked=enable;
        chk.dispatchEvent(new Event('change'));
        count++;
      }
    }
  }
  if(count===0)toast('无需变更');
}

// 5d. Real-time status polling for agent detail
let _agentPollTimer=null;
function startAgentPoll(agentId){
  stopAgentPoll();
  if(!agentId)return;
  _agentPollTimer=setInterval(async()=>{
    if(document.hidden)return;
    const st=await api(`${A}/teams/${tid}/agents/${agentId}/status`);
    if(st){
      const dotEl=document.querySelector(`.sb-agent[data-aid="${agentId}"] .dot`);
      if(dotEl)dotEl.className='dot '+(st.status||'idle');
    }
  },10000);
}
function stopAgentPoll(){if(_agentPollTimer){clearInterval(_agentPollTimer);_agentPollTimer=null}}

// Add export/import buttons to topbar
(function(){
  const topRight=document.querySelector('.topbar-right');
  if(!topRight)return;
  const expBtn=document.createElement('button');
  expBtn.className='btn btn-sm';
  expBtn.innerHTML='📤 导出';
  expBtn.onclick=exportTeamConfig;
  const impBtn=document.createElement('button');
  impBtn.className='btn btn-sm';
  impBtn.innerHTML='📥 导入';
  impBtn.onclick=importTeamConfig;
  const createBtn = topRight.querySelector('button[onclick*="create-team"]');
  topRight.insertBefore(expBtn, createBtn);
  topRight.insertBefore(impBtn, createBtn);
})();

// ── TTS Configuration ──
const TTSAPI='/api/v1';
async function loadTTSConfig(){
  const cfg=await api(`${TTSAPI}/tts/config`);
  if(!cfg)return;
  el('tts-engine').value=cfg.engine||'gpt-sovits';
  el('tts-api-url').value=cfg.api_url||'http://127.0.0.1:9880';
  el('tts-ref-audio').value=cfg.ref_audio_path||'';
  el('tts-prompt-text').value=cfg.prompt_text||'';
  el('tts-lang').value=cfg.text_lang||'zh';
  el('tts-speed').value=cfg.speed_factor||1.0;
  // Check service status
  checkTTSStatus();
}
async function checkTTSStatus(){
  const badge=el('tts-status-badge');
  try{
    const r=await fetch(`${TTSAPI}/tts/status`);
    const d=await r.json();
    if(d.online){badge.textContent='🟢 在线';badge.style.background='rgba(152,245,167,0.15)';badge.style.color='var(--lime)'}
    else{badge.textContent='🔴 离线';badge.style.background='rgba(224,27,36,0.1)';badge.style.color='var(--pink)'}
  }catch(e){badge.textContent='🔴 离线';badge.style.background='rgba(224,27,36,0.1)';badge.style.color='var(--pink)'}
}
async function saveTTSConfig(){
  const body={engine:el('tts-engine').value,api_url:el('tts-api-url').value,ref_audio_path:el('tts-ref-audio').value,prompt_text:el('tts-prompt-text').value,text_lang:el('tts-lang').value,speed_factor:parseFloat(el('tts-speed').value)||1.0};
  const r=await api(`${TTSAPI}/tts/config`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r){toast('TTS 配置已保存');checkTTSStatus()}else toast('保存失败','error')
}
async function testTTSConnection(){
  const res=el('tts-test-result');
  res.textContent='正在测试 TTS 服务...';res.style.color='var(--dim)';
  try{
    const r=await fetch(`${TTSAPI}/tts/status`);
    const d=await r.json();
    if(d.online){res.innerHTML='<span style="color:var(--lime)">✅ GPT-SoVITS 服务在线，可正常使用</span>';checkTTSStatus()}
    else{res.innerHTML='<span style="color:var(--pink)">❌ 服务离线 — 请点击「▶ 启动服务」</span>';checkTTSStatus()}
  }catch(e){res.innerHTML='<span style="color:var(--pink)">❌ 无法连接: '+escapeHtml(e.message)+'</span>'}
}
async function startTTSService(){
  const res=el('tts-test-result');
  res.textContent='正在启动 GPT-SoVITS 服务...';res.style.color='var(--dim)';
  try{
    const r=await api(`${TTSAPI}/tts/start`,{method:'POST'});
    if(r&&r.status==='started'){res.innerHTML='<span style="color:var(--lime)">✅ GPT-SoVITS 服务已启动 (PID: '+r.pid+')</span>';setTimeout(checkTTSStatus,3000)}
    else if(r&&r.status==='already_running'){res.innerHTML='<span style="color:var(--lime)">ℹ️ 服务已在运行中 (PID: '+r.pid+')</span>';checkTTSStatus()}
    else{res.innerHTML='<span style="color:var(--pink)">❌ 启动失败: '+(r?.error||'未知错误')+'</span>'}
  }catch(e){res.innerHTML='<span style="color:var(--pink)">❌ 启动请求失败: '+escapeHtml(e.message)+'</span>'}
}



/* ── 关系 tab：通道绑定可编辑 + 运行时测通 ── */
function _relChanStatus(msg){const el=document.getElementById('rel-chan-status');if(el)el.textContent=msg||'';}
function _relDraft(){return window._relChannelDraft||{teamId:'',agentId:'',channels:[]};}
function updRelChanName(i,v){const d=_relDraft();if(d.channels[i]){d.channels[i].channel_name=v;d.channels[i].channel=v;}}
function updRelChanField(i,k,v){const d=_relDraft();if(d.channels[i])d.channels[i][k]=v;}
function rmRelChan(i){const d=_relDraft();d.channels.splice(i,1);loadAgent(d.agentId||aid);}
function addRelChan(){const d=_relDraft();const bus=(d.teamId||tid||'team').replace(/[^a-zA-Z0-9_-]/g,'_')+'_bus';d.channels.push({channel_name:bus,channel:bus,subscribe:true,publish:true,priority:0});
  // 就地刷新列表，不丢未保存编辑
  const list=document.getElementById('rel-chan-list');
  if(list){
    const i=d.channels.length-1;const ch=d.channels[i];
    const div=document.createElement('div');div.className='ws-item';div.style.cssText='flex-wrap:wrap;gap:8px';
    div.innerHTML=`<span class="fname">📡 <input class="fi" style="width:140px;padding:4px 8px;font-size:12px" value="${escapeHtml(ch.channel_name||'')}" onchange="updRelChanName(${i},this.value)"></span>
      <label style="font-size:12px;display:flex;align-items:center;gap:4px"><input type="checkbox" checked onchange="updRelChanField(${i},'subscribe',this.checked)"> 订阅</label>
      <label style="font-size:12px;display:flex;align-items:center;gap:4px"><input type="checkbox" checked onchange="updRelChanField(${i},'publish',this.checked)"> 发布</label>
      <label style="font-size:12px;display:flex;align-items:center;gap:4px">P <input type="number" style="width:48px" value="0" onchange="updRelChanField(${i},'priority',+this.value)"></label>
      <button class="btn btn-sm btn-ghost" style="color:var(--pink)" onclick="rmRelChan(${i})">删除</button>`;
    list.appendChild(div);_relChanStatus('已添加，记得保存');
  } else loadAgent(d.agentId||aid);
}
function saveRelChannels(){const d=_relDraft();if(!d.teamId||!d.agentId){_relChanStatus('⚠ 无 agent');return;}
  const channels=(d.channels||[]).filter(c=>c&&(c.channel_name||c.channel)).map(c=>({channel_name:c.channel_name||c.channel,subscribe:!!c.subscribe,publish:!!c.publish,priority:c.priority||0}));
  api(`${A}/teams/${d.teamId}/agents/${d.agentId}/channels`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({channels})}).then(r=>{
    if(r&&(r.agent_id||r.channels)){ _relChanStatus('✅ 通道已保存（已持久化；publish/subscribe 运行时生效）'); loadAgent(d.agentId||aid); }
    else _relChanStatus('⚠ 保存失败'+(api._lastError?': '+api._lastError.message:''));
  }).catch(e=>_relChanStatus('⚠ '+(e.message||e)));}
function testRelChanPublish(){const d=_relDraft();const pub=(d.channels||[]).find(c=>c.publish);if(!pub){_relChanStatus('⚠ 无 publish=true 的通道');return;}
  const name=pub.channel_name||pub.channel;api(`${A}/teams/${d.teamId}/agents/${d.agentId}/channels/publish`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({channel_name:name,content:'test from team-config '+new Date().toISOString()})}).then(r=>{
    if(r&&r.ok)_relChanStatus('✅ 已发布到 '+name+' msg='+(r.message&&r.message.msg_id));else _relChanStatus('⚠ '+(r&&r.detail||r&&r.error||'publish failed'));
  }).catch(e=>_relChanStatus('⚠ '+(e.message||e)));}
function testRelChanInbox(){const d=_relDraft();api(`${A}/teams/${d.teamId}/agents/${d.agentId}/channels/inbox`).then(r=>{
  if(r&&r.ok)_relChanStatus('📥 收件箱 '+(r.count||0)+' 条'+(r.messages&&r.messages.length?': '+r.messages.slice(-3).map(m=>(m.from||'?')+':'+(m.content||'').slice(0,24)).join(' | '):''));
  else _relChanStatus('⚠ inbox failed');
}).catch(e=>_relChanStatus('⚠ '+(e.message||e)));}
