/**
 * AgentsGroup2026 — New Agent Creation Wizard
 * Multi-step wizard for creating new agents with personality,
 * skills, tools, and permissions configuration.
 * Extracted from agent-team-config.js for modularity.
 * Depends on: utils.js, api.js, agent-team-config.js (parent scope)
 */
(function(){
'use strict';
const csrfFetch = window._agFetch || fetch;
const TMPLS=[{id:'custom',ab:'自定义',nm:'自定义'},{id:'coordinator',ab:'PM',nm:'项目经理'},{id:'researcher',ab:'RS',nm:'研究员'},{id:'developer',ab:'DV',nm:'开发者'},{id:'analyst',ab:'AN',nm:'分析师'},{id:'navigator',ab:'NV',nm:'导航员'},{id:'engineer',ab:'EN',nm:'工程师'}];
async function listApi(path, limit = 200, offset = 0){
  if(window.api&&typeof window.api.list==='function'){
    const payload=await window.api.list(path,limit,offset);
    return Array.isArray(payload?.items)?payload.items:[];
  }
  const payload=await api(path);
  return Array.isArray(payload)?payload:(Array.isArray(payload?.items)?payload.items:[]);
}

function openWizard(){if(typeof isPlatformScope==='function'&&isPlatformScope()){toast('请先在左上角选择一个团队','error');return}wzD={template_type:'custom',name:'',role:'',description:'',system_prompt:'',model_id:'',team_id:tid,personality:{tone:'professional',language:'zh-CN',expertise_areas:[],response_style:'concise',creativity:0.5},skill_ids:[],tool_ids:[],permissions:[],channels:[],visibility:'public',default_access:'use'};wzS=1;switchView('wizard');renderWz()}

function renderWz(){
  document.querySelectorAll('#wz-steps .wz-step').forEach(s=>{const n=+s.dataset.step;s.classList.remove('active','done');if(n===wzS)s.classList.add('active');else if(n<wzS)s.classList.add('done')});
  const c=el('wz-content'),w=wzD;
  if(wzS===1){
    c.innerHTML=`<h3 style="margin-bottom:20px">基础信息与模型选择</h3><p class="form-label" style="margin-bottom:10px">选择模板（可选）</p><div class="tmpl-grid">${TMPLS.map(t=>`<div class="tmpl-card${w.template_type===t.id?' selected':''}" onclick="selTmpl('${t.id}')"><div class="abbr">${t.ab}</div><div class="desc">${t.nm}</div></div>`).join('')}</div><div style="display:flex;gap:12px;margin-bottom:16px"><p style="color:var(--muted);font-size:12px;cursor:pointer" onclick="toast('JSON 导入功能开发中')">↑ 从 JSON 导入</p><p style="color:var(--pink);font-size:12px;cursor:pointer;font-weight:600" onclick="openModal('modal-import-openclaw')">🔗 连接 OpenClaw Agent</p></div><div class="form-group"><label class="form-label">名称 <span class="req">*</span></label><input class="fi" id="wz-name" value="${w.name}" placeholder="例：小智"></div><div class="form-group"><label class="form-label">👤 角色</label><input class="fi" id="wz-role" value="${w.role}" placeholder="描述它的角色定位"></div><div class="form-group"><label class="form-label">描述</label><textarea class="fi" id="wz-desc">${w.description}</textarea></div><div class="form-group"><label class="form-label">所属团队 <span class="req">*</span></label><select class="fi" id="wz-team"></select></div><div class="form-group"><label class="form-label">主模型 <span class="req">*</span></label><select class="fi" id="wz-model"><option value="">选择模型...</option></select></div><div class="wz-actions"><button class="btn" onclick="switchView('overview')">取消</button><button class="btn btn-pink" onclick="wzNext()">下一步 →</button></div>`;
    listApi(`${A}/teams`,200,0).then(ts=>{const s=el('wz-team');if(ts)ts.forEach(t=>{const o=document.createElement('option');o.value=t.team_id;o.textContent=t.name;if(t.team_id===(w.team_id||tid))o.selected=true;s.appendChild(o)})});
    listApi(`${A}/teams/${w.team_id||tid}/models`,200,0).then(ms=>{const s=el('wz-model');if(ms)ms.forEach(m=>{const o=document.createElement('option');o.value=m.model_id;o.textContent=`${m.name} (${m.provider})`;if(m.model_id===w.model_id)o.selected=true;s.appendChild(o)})});
  } else if(wzS===2){
    c.innerHTML=`<h3 style="margin-bottom:20px">人格设定</h3><div class="form-group"><label class="form-label">语言风格</label><select class="fi" id="wz-tone"><option value="professional"${w.personality.tone==='professional'?' selected':''}>专业</option><option value="friendly"${w.personality.tone==='friendly'?' selected':''}>友好</option><option value="directive"${w.personality.tone==='directive'?' selected':''}>指令式</option><option value="casual"${w.personality.tone==='casual'?' selected':''}>随意</option></select></div><div class="form-group"><label class="form-label">语言</label><select class="fi" id="wz-lang"><option value="zh-CN"${w.personality.language==='zh-CN'?' selected':''}>中文</option><option value="en"${w.personality.language==='en'?' selected':''}>English</option></select></div><div class="form-group"><label class="form-label">回复风格</label><select class="fi" id="wz-style"><option value="concise"${w.personality.response_style==='concise'?' selected':''}>简洁</option><option value="detailed"${w.personality.response_style==='detailed'?' selected':''}>详细</option><option value="structured"${w.personality.response_style==='structured'?' selected':''}>结构化</option></select></div><div class="form-group"><label class="form-label">创造力 (${w.personality.creativity})</label><input type="range" id="wz-creat" min="0" max="1" step="0.1" value="${w.personality.creativity}" oninput="this.previousElementSibling.textContent='创造力 ('+parseFloat(this.value).toFixed(1)+')'"></div><div class="form-group"><label class="form-label">专长领域</label><div>${(w.personality.expertise_areas||[]).map(e=>`<span class="chip">${e} <span class="x" onclick="rmExp('${e}')">×</span></span>`).join('')}<span class="chip chip-add" onclick="addExp()">＋ 添加</span></div></div><div class="form-group"><label class="form-label">系统提示词</label><textarea class="fi" id="wz-prompt" rows="4" placeholder="定义核心行为...">${w.system_prompt||''}</textarea></div><div class="wz-actions"><button class="btn" onclick="wzBack()">← 上一步</button><button class="btn btn-pink" onclick="wzNext()">下一步 →</button></div>`;
  } else if(wzS===3){
    listApi(`${A}/skills`,200,0).then(sk=>{
      const cats={};(sk||[]).forEach(s=>{const c=s.category||'general';if(!cats[c])cats[c]=[];cats[c].push(s)});
      let html='<h3 style="margin-bottom:20px">技能配置</h3><p style="color:var(--muted);font-size:13px;margin-bottom:16px">选择此 Agent 应具备的技能 <span style="color:var(--pink)">('+w.skill_ids.length+' 已选)</span></p>';
      Object.keys(cats).sort().forEach(cat=>{html+=`<div class="sb-section" style="margin-top:14px;margin-bottom:8px">${cat.toUpperCase()}</div>`;cats[cat].forEach(s=>{const on=w.skill_ids.includes(s.skill_id);html+=`<div class="ws-item" style="cursor:pointer" onclick="togWzSk('${s.skill_id}')"><span class="fname"><span style="font-size:16px">${on?'☑':'☐'}</span> ${s.icon||'⚡'} ${s.name}</span><span style="color:var(--dim);font-size:12px">${s.category||''}</span></div>`})});
      html+=`<div class="wz-actions"><button class="btn" onclick="wzBack()">← 上一步</button><button class="btn btn-pink" onclick="wzNext()">下一步 →</button></div>`;
      c.innerHTML=html});
  } else if(wzS===4){
    listApi(`${A}/tools`,200,0).then(tk=>{
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
    CH_PLATFORMS.forEach(p=>{const on=!!chMap[p.id];html+=`<div class="ws-item" style="cursor:pointer;padding:16px;margin-bottom:8px" onclick="togWzChan('${p.id}','${p.name}')"><span class="fname"><span style="font-size:22px">${p.icon}</span><div><div style="font-weight:600">${p.name}</div><div style="font-size:12px;color:var(--muted)">${p.desc}</div></div></span><span style="font-size:14px;color:${on?'var(--pink)':'var(--dim)'}">${on?'▼':'▶'}</span></div>`;if(on){html+=`<div style="padding:4px 16px 12px;margin-top:-8px;margin-bottom:8px;border:1px solid var(--line);border-top:none;border-radius:0 0 8px 8px;background:rgba(232,240,250,0.5)"><div style="display:grid;grid-template-columns:1fr 1fr;gap:10px"><label style="display:flex;align-items:center;gap:6px;font-size:13px"><input type="checkbox" role="switch" ${chMap[p.id].subscribe?'checked':''} onchange="updChanSub('${p.id}',this.checked)"> 订阅</label><label style="display:flex;align-items:center;gap:6px;font-size:13px"><input type="checkbox" role="switch" ${chMap[p.id].publish?'checked':''} onchange="updChanPub('${p.id}',this.checked)"> 发布</label></div></div>`}});
    html+=`<p style="color:var(--muted);font-size:12px;text-align:center;margin-top:16px">跳过此步骤后，数字员工仍可通过 Web 端进行对话</p>`;
    html+=`<div style="background:var(--panel2);border:1px solid var(--line);border-radius:0;padding:14px;margin-top:20px;font-size:13px;color:var(--muted)">${w.name||'未命名'} · 模型: ${w.model_id||'未选择'}</div>`;
    html+=`<div class="wz-actions"><button class="btn" onclick="wzBack()">← 上一步</button><button class="btn btn-pink" onclick="wzFinish()">🚀 完成创建</button></div>`;
    c.innerHTML=html;
  }
}

const TMPL_DEFAULTS={
  coordinator:{role:'项目协调与任务分配',personality:{tone:'directive',response_style:'structured',expertise_areas:['项目管理','任务拆解','进度跟踪']},skill_ids:['task_decomposition','progress_tracking','blocker_resolution']},
  researcher:{role:'深度研究与知识发现',personality:{tone:'professional',response_style:'detailed',expertise_areas:['文献检索','数据分析','知识整理'],creativity:0.7},skill_ids:['web_research','data_analysis','cross_session_recall'],tool_ids:['web_search','extract_content','memory_read']},
  developer:{role:'代码开发与技术实现',personality:{tone:'professional',response_style:'concise',expertise_areas:['编程','调试','架构设计']},skill_ids:['code_implementation','debugging','refactoring'],tool_ids:['run_shell','read_file','write_file']},
  analyst:{role:'数据分析与洞察挖掘',personality:{tone:'professional',response_style:'structured',expertise_areas:['数据可视化','统计分析','趋势预测'],creativity:0.6},skill_ids:['data_analysis','competitive_analysis','requirements_analysis'],tool_ids:['run_python','read_file','web_search']},
  navigator:{role:'航线规划与海况分析',personality:{tone:'directive',response_style:'concise',expertise_areas:['航海','气象','避碰']},skill_ids:['web_research','requirements_analysis','progress_tracking'],tool_ids:['web_search','extract_content','read_file']},
  engineer:{role:'机舱监控与设备维护',personality:{tone:'professional',response_style:'structured',expertise_areas:['轮机','传感器','预测维护']},skill_ids:['debugging','data_analysis','build_automation'],tool_ids:['run_shell','read_file','write_file']}
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
    await csrfFetch(`${A}/teams/${wtid}/agents/${nid}`,{method:'DELETE'}).catch(()=>{});
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

// Export to global scope for HTML onclick access
window.openWizard = openWizard;
window.selTmpl = selTmpl;
window.wzBack = wzBack;
window.wzNext = wzNext;
window.setWzVis = setWzVis;
window.setWzAccess = setWzAccess;
window.updChanSub = updChanSub;
window.updChanPub = updChanPub;
window.togWzChan = togWzChan;
window.saveWzData = saveWzData;
window.togWzTk = togWzTk;
window.addExp = addExp;
window.rmExp = rmExp;
window.togWzSk = togWzSk;
window.addPerm = addPerm;
window.rmPerm = rmPerm;
window.wzFinish = wzFinish;

})();
