/**
 * AgentsGroup2026 — Tasks & Workflow Views
 * Manages concurrent task display, workflow pipeline rendering,
 * task terminals (Claude Code sessions), and task lifecycle.
 * Extracted from agent-team-config.js for modularity.
 * Depends on: utils.js, api.js, agent-team-config.js (parent scope)
 */
(function(){
'use strict';
const csrfFetch = window._agFetch || fetch;
const PRIO_LBL={0:'🔴 紧急',1:'🟠 高',2:'🔵 普通',3:'⚪ 低'};
const TST_CLS={pending:'st-idle',running:'st-working',completed:'st-reporting',failed:'st-error',cancelled:'st-blocked'};
const TST_LBL={pending:'待执行',running:'执行中',completed:'已完成',failed:'失败',cancelled:'已取消'};

const WF_ICONS={completed:'✓',active:'●',pending:'○',skipped:'—',failed:'✗'};

async function listTasks(limit = 200, offset = 0){
  if(window.api&&typeof window.api.list==='function'){
    const payload=await window.api.list(`${A}/teams/${tid}/tasks`,limit,offset);
    return Array.isArray(payload?.items)?payload.items:[];
  }
  const payload=await api(`${A}/teams/${tid}/tasks`);
  return Array.isArray(payload)?payload:Array.isArray(payload?.items)?payload.items:[];
}

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
      const tasks=await listTasks();
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
  fetch(`${A}/claude-sessions/${sid}`).then(r=>{if(!r.ok)throw new Error('gone');return r.json()}).then(d=>{
    if(d.output&&d.output.length){
      // XC-6.2: 检测旧 CLI 引擎会话头并标注
      const _OLD_CLI_MARKERS=['正在启动 Claude Code CLI','Claude Code →','DeepSeek 凭据未找到，回退到 Claude CLI','⏳ 正在启动 Claude Code CLI'];
      let oldEngineDetected=false;
      d.output.forEach(line=>{
        const div=document.createElement('div');
        div.className='tl';
        const trimmed=line.replace(/\n$/,'');
        // 检测旧引擎标记
        if(_OLD_CLI_MARKERS.some(m=>trimmed.includes(m))){
          oldEngineDetected=true;
          div.style.color='oklch(0.56 0.05 70)';
          div.style.fontStyle='italic';
          div.textContent=trimmed+'  ⚠ (历史会话·旧引擎)';
        }else{
          div.textContent=trimmed;
        }
        body.appendChild(div);
      });
      if(oldEngineDetected){
        const warn=document.createElement('div');
        warn.className='tl';
        warn.style.cssText='color:oklch(0.56 0.05 70);font-size:10px;padding:4px 0;border-top:1px dashed';
        warn.textContent='⚠ 以上日志来自旧 CLI 引擎——重启后端后新任务将走配置模型 provider';
        body.appendChild(warn);
      }
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
  toast('正在调用配置模型...');
  const r=await api(`${A}/teams/${tid}/tasks/${taskId}/workflow/run-step`,{method:'POST'});
  if(r&&r.session_id){
    toast('步骤已启动');
    loadTasks();
    setTimeout(()=>connectAllTaskTerminals(),500);
  }else{toast(r?r.status||'失败':'启动失败')}
}

function stopTaskTerm(sid){
  csrfFetch(`${A}/claude-sessions/${sid}/stop`,{method:'POST'});
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

async function loadTasks(){hideViewLoading("view-tasks");
  const[tasks,stats]=await Promise.all([listTasks(),api(`${A}/tasks/stats`)]);
  const tb=el('tasks-tb'),st=el('task-stats');
  if(stats){const s=stats.by_status||{};st.innerHTML=`<span class="chip" style="background:rgba(53,200,255,0.1)">并发: ${stats.max_concurrency}</span><span class="chip">${stats.total||0} 总</span>${s.running?`<span class="chip" style="background:rgba(53,200,255,0.15);color:var(--cyan-s)">${s.running} 运行中</span>`:''}${s.completed?`<span class="chip" style="background:rgba(152,245,167,0.15);color:var(--lime)">${s.completed} 完成</span>`:''}`}
  if(!tasks||!tasks.length){tb.innerHTML='<tr><td colspan="7" style="color:var(--dim)">暂无任务 — 点击「提交任务」开始并发执行</td></tr>';return}
  tb.innerHTML=tasks.map(t=>{
    let actions='';
    const hasWf=t.metadata&&t.metadata.workflow&&t.metadata.workflow.length>0;
    const wfAllDone=hasWf&&t.metadata.workflow.every(s=>s.status==='completed'||s.status==='skipped');
    const delBtn=`<button class="btn btn-sm" style="padding:2px 8px;font-size:11px;color:oklch(0.55 0.005 110)" onclick="taskAction('${t.task_id}','delete')" title="删除任务">🗑</button>`;
    // XG-11: pending 起即可进物竞（沙箱竞标，不替代「开始」）
    const ecoBtn=` <button class="btn btn-sm" style="padding:2px 8px;font-size:11px;background:rgba(167,139,250,0.12);color:var(--purple)" onclick="sendTaskToEcoField('${t.task_id}')" title="带本团队+任务进入办公室物竞试验田">🧬 物竞</button>`;
    if(t.status==='pending') actions=`<button class="btn btn-sm" style="padding:2px 8px;font-size:11px;background:rgba(53,200,255,0.1);color:var(--cyan-s)" onclick="taskAction('${t.task_id}','start')">▶ 开始</button>${ecoBtn} <button class="btn btn-sm" style="padding:2px 8px;font-size:11px" onclick="taskAction('${t.task_id}','cancel')">取消</button> ${delBtn}`;
    else if(t.status==='running'){
      const cancelBtn=`<button class="btn btn-sm" style="padding:2px 8px;font-size:11px" onclick="taskAction('${t.task_id}','cancel')">⏹ 取消</button>`;
      // T3.2: Step-level retry/skip/terminate for stuck running tasks
      let stepBtns='';
      if(hasWf&&!wfAllDone){
        const activeIdx=t.metadata.workflow.findIndex(s=>s.status==='active');
        if(activeIdx>=0){
          stepBtns=` <button class="btn btn-sm" style="padding:2px 8px;font-size:10px;background:rgba(53,200,255,0.08)" onclick="retryStep('${t.task_id}',${activeIdx})" title="重试当前步骤">🔄</button>`+
                   ` <button class="btn btn-sm" style="padding:2px 8px;font-size:10px;background:rgba(245,158,11,0.08)" onclick="skipStep('${t.task_id}',${activeIdx})" title="跳过当前步骤">⏭</button>`;
        }
        actions=`<span style="font-size:11px;color:var(--dim)">流程进行中</span>${stepBtns} <button class="btn btn-sm" style="padding:2px 8px;font-size:11px;background:rgba(224,27,36,0.1);color:var(--red)" onclick="taskAction('${t.task_id}','fail')">✗ 失败</button> ${cancelBtn}`;
      } else {
        actions=`<button class="btn btn-sm" style="padding:2px 8px;font-size:11px;background:rgba(152,245,167,0.15);color:var(--lime)" onclick="taskAction('${t.task_id}','complete')">✓ 完成</button> <button class="btn btn-sm" style="padding:2px 8px;font-size:11px;background:rgba(224,27,36,0.1);color:var(--red)" onclick="taskAction('${t.task_id}','fail')">✗ 失败</button> ${cancelBtn} ${delBtn}`;
      }
    }
    else if(t.status==='completed') actions=`<span style="color:var(--lime)">✓</span>${ecoBtn} <button class="btn btn-sm" style="padding:2px 8px;font-size:11px;background:rgba(53,200,255,0.08);color:var(--cyan-s)" onclick="rerunTask('${t.task_id}')" title="重跑任务">🔄 重跑</button> ${delBtn}`;
    else if(t.status==='cancelled'||t.status==='failed') actions=`${ecoBtn} <button class="btn btn-sm" style="padding:2px 8px;font-size:11px;background:rgba(53,200,255,0.08);color:var(--cyan-s)" onclick="rerunTask('${t.task_id}')" title="重跑任务">🔄 重跑</button> ${delBtn}`;
    else actions=ecoBtn||'—';
    // running 行也挂物竞（可边跑边做孪生对照）
    if(t.status==='running') actions=actions+ecoBtn;
    const src=t.metadata&&t.metadata.cross_team?`<span class="chip" style="font-size:9px;background:rgba(245,158,11,0.1);color:oklch(0.56 0.05 70)">跨团队 ← ${t.metadata.source_agent||t.metadata.source_team||''}</span>`:'';
    const wfHtml=renderWorkflow(t);
    const wfProgress=t.metadata&&t.metadata.workflow?(() => {const w=t.metadata.workflow;const done=w.filter(s=>s.status==='completed').length;return `<span style="font-size:10px;color:var(--dim);margin-left:6px">${done}/${w.length}</span>`})():'';
    // T3.1: Stuck highlight + runtime info
    const stuckBadge=t.stuck?`<span class="chip" style="font-size:9px;background:rgba(224,27,36,0.12);color:var(--red);margin-left:4px">⚠ 可能卡死</span>`:'';
    const runtimeInfo=t.elapsed_sec!=null&&t.status==='running'?`<span style="font-size:10px;color:var(--dim);margin-left:4px">⏱${Math.round(t.elapsed_sec/60)}m${t.current_step?' · '+t.current_step:''}${t.last_activity_sec!=null?' · 活动'+Math.round(t.last_activity_sec)+'s前':''}</span>`:'';
    // T5.5: Collaboration info
    const collabInfo=t.metadata&&t.metadata.collaboration?`<span class="chip" style="font-size:9px;background:rgba(152,245,167,0.1);color:var(--lime);margin-left:4px">🤝 协作${t.metadata.collaboration.message_count?' · '+t.metadata.collaboration.message_count+'条':''}</span>`:'';
    const stuckRow=t.stuck?' style="background:rgba(224,27,36,0.04)"':'';
    // XC-4.1: 工作区按钮
    const wsBtn=hasWf?` <button class="btn btn-sm" style="padding:2px 8px;font-size:10px;background:rgba(168,85,247,0.08);color:var(--purple)" onclick="openWorkspace('${t.task_id}')" title="查看工作区产物">📁 工作区</button>`:'';
    return `<tr${stuckRow}><td style="font-family:'IBM Plex Mono',monospace;font-size:11px">${escapeHtml(t.task_id)}</td><td style="min-width:280px"><b>${escapeHtml(t.title)}</b>${src}${stuckBadge}${collabInfo}${wfProgress}${runtimeInfo}${t.description?`<br><span style="color:var(--dim);font-size:11px">${escapeHtml(t.description?.slice(0,80)||'')}</span>`:''}${wfHtml}</td><td>${t.agent_id||'<span style="color:var(--dim)">自动</span>'}</td><td>${PRIO_LBL[t.priority]||t.priority}</td><td>${t.dependencies&&t.dependencies.length?t.dependencies.map(d=>'<span class="chip" style="font-size:10px">'+d+'</span>').join(''):'—'}</td><td><span class="st ${TST_CLS[t.status]||''}">${TST_LBL[t.status]||t.status}</span></td><td style="white-space:nowrap">${actions}${wsBtn}</td></tr>`;
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
    if(!confirm('确定要永久删除此任务吗？此操作不可撤销。')) return;
    const resp=await csrfFetch(`${A}/teams/${tid}/tasks/${id}/remove`,{method:'DELETE'});
    const body=await resp.json().catch(()=>null);
    const alreadyMissing=resp.status===404 && ((body&&body.detail)||'').toLowerCase().indexOf('task not found')>=0;
    if(resp.ok||alreadyMissing){
      toast(alreadyMissing?'✅ 任务已不存在（视为已删除）':'✅ 已永久删除');
      loadTasks();
    }else{
      toast('❌ 删除失败: '+((body&&body.detail)||`HTTP ${resp.status}`),'error');
    }
  }
  else if(action==='cancel'){
    if(!confirm('确定要取消此任务吗？')) return;
    toast('⏳ 正在取消...');
    await api(`${A}/teams/${tid}/tasks/${id}/stop`,{method:'POST'}).catch(()=>{});
    const r=await api(`${A}/teams/${tid}/tasks/${id}`,{method:'DELETE'}); // 只标记 cancelled
    if(r){toast('✅ 已取消');loadTasks()}else{toast('❌ 取消失败','error')}
  }
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
    const resp=await csrfFetch(`${A}/teams/${tid}/tasks/${id}/start`,{method:'POST'});
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
  else{await csrfFetch(`${A}/teams/${tid}/tasks/${id}/${action}`,{method:'POST'});toast(action==='complete'?'任务已完成':'任务已标记失败')}
  loadTasks()
}

// ── Create team ──
el('btn-ct').onclick=async()=>{const n=el('ct-name').value.trim();if(!n){toast('请输入名称');return}el('btn-ct').disabled=true;el('btn-ct').textContent='创建中...';try{const r=await api(`${A}/teams`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n,description:el('ct-desc').value.trim()})});if(r&&r.team_id){toast('✅ 团队创建成功');closeModal('modal-create-team');el('ct-name').value='';el('ct-desc').value='';tid=r.team_id;loadTeams()}else{toast('❌ 创建失败，请检查后端日志')}}finally{el('btn-ct').disabled=false;el('btn-ct').textContent='创建'}};

// ── Delete team ──（与批量删除统一逻辑：优先 checkbox，兜底 tid）
window.deleteTeam=async function(){
  // 优先走批量删除（与「删除选中团队」按钮一致）
  if (typeof deleteSelectedTeams === 'function') {
    var cbs = document.querySelectorAll('.ov-team-cb:checked');
    if (cbs.length) { deleteSelectedTeams(); return; }
  }
  // 兜底：没勾选时删下拉选中的团队
  if(!tid||(typeof isPlatformScope==='function'&&isPlatformScope())){
    toast('请先勾选团队对比矩阵中的复选框，或在左上角下拉列表中选择要删除的团队');
    return;
  }
  const teams=await api(`${A}/teams`);
  const t=teams.find(x=>x.team_id===tid);
  const name=t?t.name:tid;
  showConfirm('⚠️ 确定要删除团队「' + name + '」吗？此操作不可撤销，团队下的所有模型、智能体、任务都会被删除。', async () => {
    const r=await api(`${A}/teams/${tid}`,{method:'DELETE'});
    if(r){toast('✅ 团队「' + name + '」已删除');tid=(typeof ALL_TEAMS!=='undefined')?ALL_TEAMS:'';_teamsListCache=null;loadTeams()}else{toast('❌ 删除失败，请检查后端日志')}
  });
};
// ── 批量删除选中团队 ──
window.deleteSelectedTeams=async function(){
  const cbs=document.querySelectorAll('.ov-team-cb:checked');
  if(!cbs.length){toast('请先在团队对比矩阵中勾选复选框');return}
  const ids=Array.from(cbs).map(c=>c.value);
  showConfirm(`⚠️ 确定要删除选中的 ${ids.length} 个团队吗？此操作不可撤销，团队下的所有模型、智能体、任务都会被删除。`, async () => {
    let ok=0,fail=0;
    for(const id of ids){
      const r=await api(`${A}/teams/${id}`,{method:'DELETE'});
      if(r)ok++;else fail++;
    }
    toast(`✅ 已删除 ${ok} 个团队${fail?`，${fail} 个失败`:''}`);
    tid=(typeof ALL_TEAMS!=='undefined')?ALL_TEAMS:'';_teamsListCache=null;loadTeams();
  });
};
// ── Add model ──
el('btn-am').onclick=async()=>{const n=el('am-name').value.trim();if(!n){toast('请输入模型名');return}const r=await api(`${A}/teams/${tid}/models`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider:el('am-prov').value,name:n,max_tokens:+el('am-tok').value,temperature:+el('am-temp').value,api_key:el('am-key').value,api_base_url:el('am-url').value,is_default:el('am-def').value==='true'})});if(r){toast('添加成功');closeModal('modal-add-model');el('am-name').value='';el('am-key').value='';el('am-url').value='';loadModels()}else toast('失败')};
// ── Submit task ──
el('btn-tk').onclick=async()=>{if(!tid){toast('请先选择一个团队');return}const t=el('tk-title').value.trim();if(!t){toast('请输入标题');return}el('btn-tk').disabled=true;el('btn-tk').textContent='提交中...';try{const deps=el('tk-deps').value.trim();const execMode=(el('tk-exec-mode')||{}).value||'linear';const r=await api(`${A}/teams/${tid}/tasks`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:t,description:el('tk-desc').value.trim(),agent_id:el('tk-agent').value||'',priority:+el('tk-prio').value,dependencies:deps?deps.split(',').map(s=>s.trim()).filter(Boolean):[],execution_mode:execMode})});if(r){toast(`✅ 任务 ${r.task_id||''} 已提交`);closeModal('modal-add-task');el('tk-title').value='';el('tk-desc').value='';el('tk-deps').value='';loadTasks()}else{toast('❌ 提交失败，请检查后端日志')}}finally{el('btn-tk').disabled=false;el('btn-tk').textContent='提交'}};
// ── Batch submit ──
el('btn-bt').onclick=async()=>{if(!tid){toast('请先选择一个团队');return}try{const j=JSON.parse(el('bt-json').value);if(!Array.isArray(j)||!j.length){toast('需要非空 JSON 数组');return}for(const t of j){if(!t.title){toast('每个任务必须有 title 字段');return}}el('btn-bt').disabled=true;el('btn-bt').textContent='提交中...';const r=await api(`${A}/teams/${tid}/tasks/batch`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tasks:j})});if(r){toast(`✅ ${Array.isArray(r)?r.length:j.length} 个任务已提交`);closeModal('modal-batch-task');el('bt-json').value='';loadTasks()}else{toast('❌ 批量提交失败，请检查后端日志')}}catch(e){toast('JSON 格式错误: '+e.message)}finally{el('btn-bt').disabled=false;el('btn-bt').textContent='批量提交'}};
// ── Close modals ──
document.querySelectorAll('.modal-overlay').forEach(o=>{o.addEventListener('mousedown',e=>{if(e.target===o)o.classList.remove('open')});const mc=o.querySelector('.modal');if(mc)mc.addEventListener('mousedown',e=>e.stopPropagation())});

// ══════════════════════════════════
//  OPENCLAW IMPORT
// ══════════════════════════════════



// Export to global scope for HTML onclick access
window.loadTasks = loadTasks;
window.cancelAllTasks = async function(){
  const choice=prompt('选择要清理的任务类型:\n  r = 仅运行中\n  p = 仅待执行\n  a = 全部(含失败/已完成/已取消)\n  f = 仅失败\n  d = 仅已完成\n  输入后确认:');
  if(!choice) return;
  const ch=choice.trim().toLowerCase();
  const targets=[];
  if(ch==='r') targets.push('running');
  else if(ch==='p') targets.push('pending');
  else if(ch==='a') targets.push('running','pending','failed','completed','cancelled');
  else if(ch==='f') targets.push('failed');
  else if(ch==='d') targets.push('completed');
  else {toast('无效选择，请输入 r/p/a/f/d');return}

  const tasks=await listTasks();
  if(!tasks||!tasks.length){toast('暂无任务');return}
  const matched=tasks.filter(t=>targets.includes(t.status));
  if(!matched.length){toast(`没有 ${targets.join('/')} 状态的任务`);return}
  if(!confirm(`确定要清理 ${matched.length} 个任务 (${targets.join(',')})？`)) return;

  let count=0;
  for(const t of matched){
    if(t.status==='running') await api(`${A}/teams/${tid}/tasks/${t.task_id}/stop`,{method:'POST'}).catch(()=>{});
    const resp=await csrfFetch(`${A}/teams/${tid}/tasks/${t.task_id}/remove`,{method:'DELETE'});
    if(!resp.ok&&resp.status!==404){
      const body=await resp.json().catch(()=>null);
      toast('❌ 清理失败: '+((body&&body.detail)||`HTTP ${resp.status}`),'error');
      return;
    }
    count++;
  }
  toast(`已清理 ${count} 个任务`);loadTasks();
};
window.rerunTask = async function(taskId){
  if(!confirm('确定要重跑此任务？将重置失败/跳过的步骤并重新执行。')) return;
  toast('⏳ 正在重跑...');
  try{
    const resp=await csrfFetch(`${A}/teams/${tid}/tasks/${taskId}/rerun`,{method:'POST'});
    const body=await resp.json().catch(()=>null);
    if(!resp.ok){
      toast('❌ 重跑失败: '+((body&&body.detail)||`HTTP ${resp.status}`),'error');
      return;
    }
    toast('✅ 任务已重跑');
    loadTasks();
    setTimeout(()=>connectAllTaskTerminals(),500);
  }catch(e){
    toast('❌ 重跑失败: '+e.message,'error');
  }
};
/** XG-11: 团队任务 → 物竞试验田（带 team_id + task_id） */
window.sendTaskToEcoField = async function(taskId){
  if(!tid){toast('请先选择团队');return;}
  if(!taskId){toast('无任务 ID');return;}
  let task=null;
  try{
    const tasks=await listTasks();
    task=(tasks||[]).find(x=>x.task_id===taskId)||null;
  }catch(e){/* ignore */}
  let teamName=tid;
  try{
    const tm=await api(`${A}/teams/${tid}`);
    if(tm&&tm.name) teamName=tm.name;
  }catch(e){/* ignore */}
  try{
    sessionStorage.setItem('eco_bound_team',JSON.stringify({id:tid,name:teamName}));
    if(task) sessionStorage.setItem('eco_bound_task',JSON.stringify(task));
    // 若任务带 plan 元数据，尽量附带 plan 壳（无 steps 时孪生会走 from-tasks）
    if(task&&task.metadata&&task.metadata.plan_id){
      const meta=task.metadata;
      sessionStorage.setItem('eco_bound_plan_meta',JSON.stringify({
        plan_id:meta.plan_id||'',
        plaza_id:meta.plaza_id||'',
        discussion_id:meta.discussion_id||'',
        team_id:tid,
        task_id:taskId,
      }));
    }
  }catch(e){/* ignore */}
  const url=`/Agent-digital-twin.html?office3d=1&team_id=${encodeURIComponent(tid)}&team_name=${encodeURIComponent(teamName)}&task_id=${encodeURIComponent(taskId)}`+
    (task&&task.metadata&&task.metadata.plan_id?`&plan_id=${encodeURIComponent(task.metadata.plan_id)}`:'');
  window.open(url,'_blank');
  toast('已打开物竞试验田（团队+任务已绑定）');
};
window.taskAction = taskAction;
window.startClaudeForTask = startClaudeForTask;
window.toggleTaskTerm = toggleTaskTerm;
window.connectTaskTerminal = connectTaskTerminal;
window.connectAllTaskTerminals = connectAllTaskTerminals;
window.expandTaskTerm = expandTaskTerm;
window.stepClick = stepClick;
window.advanceWorkflow = advanceWorkflow;
// T3.2: Step-level retry / skip
window.retryStep = async function(taskId, idx){
  await api(`${A}/teams/${tid}/tasks/${taskId}/workflow/${idx}/status`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:'active'})});
  await api(`${A}/teams/${tid}/tasks/${taskId}/workflow/run-step`,{method:'POST'});
  toast('🔄 已重试');loadTasks();
};
window.skipStep = async function(taskId, idx){
  if(!confirm('确定跳过当前步骤？')) return;
  await api(`${A}/teams/${tid}/tasks/${taskId}/workflow/${idx}/status`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:'skipped'})});
  toast('⏭ 已跳过');loadTasks();
};

// XC-4.1: 工作区浏览器
window.openWorkspace = async function(taskId){
  let overlay=document.getElementById('ws-overlay');
  if(!overlay){
    overlay=document.createElement('div');
    overlay.id='ws-overlay';
    overlay.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:9999;display:flex;align-items:center;justify-content:center';
    overlay.innerHTML=`<div style="background:var(--bg,#1a1a2e);border-radius:12px;width:80%;max-width:900px;max-height:80vh;display:flex;flex-direction:column;overflow:hidden">
      <div style="display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid var(--border,#333)">
        <span style="font-weight:600;color:var(--purple,#a855f7)">📁 任务工作区 — <span id="ws-task-id"></span></span>
        <button onclick="document.getElementById('ws-overlay').remove()" style="background:none;border:none;color:var(--dim);cursor:pointer;font-size:18px">✕</button>
      </div>
      <div id="ws-breadcrumb" style="padding:6px 16px;font-size:11px;color:var(--dim);border-bottom:1px solid var(--border,#333)"></div>
      <div id="ws-content" style="flex:1;overflow:auto;padding:12px 16px;font-size:12px;font-family:'IBM Plex Mono',monospace"></div>
    </div>`;
    document.body.appendChild(overlay);
  }
  document.getElementById('ws-task-id').textContent=taskId;
  await browseWorkspace(taskId,'');
};

window.browseWorkspace = async function(taskId, subpath){
  const content=document.getElementById('ws-content');
  const crumb=document.getElementById('ws-breadcrumb');
  if(!content) return;
  content.innerHTML='<span style="color:var(--dim)">加载中...</span>';
  try{
    const r=await api(`${A}/teams/${tid}/tasks/${taskId}/workspace?subpath=${encodeURIComponent(subpath)}`);
    // 面包屑
    const parts=subpath?subpath.split('/').filter(Boolean):[];
    let bc='<span style="cursor:pointer;color:var(--cyan)" onclick="browseWorkspace(\''+taskId+'\',\'\')">📁 根</span>';
    let cur='';
    parts.forEach(p=>{cur=cur?cur+'/'+p:p;bc+=' / <span style="cursor:pointer;color:var(--cyan)" onclick="browseWorkspace(\''+taskId+'\',\''+cur+'\')">'+escapeHtml(p)+'</span>';});
    crumb.innerHTML=bc;

    if(r.type==='file'){
      content.innerHTML='<pre style="white-space:pre-wrap;word-break:break-all;color:var(--text,#e0e0e0)">'+escapeHtml(r.content||'(empty)')+'</pre>';
    }else if(r.type==='dir'){
      const entries=r.entries||[];
      if(!entries.length){content.innerHTML='<span style="color:var(--dim)">（空目录）</span>';return}
      content.innerHTML=entries.map(e=>{
        if(e.type==='dir'){
          return '<div style="padding:3px 6px;cursor:pointer;color:var(--cyan)" onclick="browseWorkspace(\''+taskId+'\',\''+e.path+'\')">📁 '+escapeHtml(e.name)+'/</div>';
        }
        const sizeStr=e.size>1024?(e.size/1024).toFixed(1)+'KB':e.size+'B';
        return '<div style="padding:3px 6px;cursor:pointer" onclick="browseWorkspace(\''+taskId+'\',\''+e.path+'\')">📄 '+escapeHtml(e.name)+' <span style="color:var(--dim);font-size:10px">'+sizeStr+'</span></div>';
      }).join('');
    }else{
      content.innerHTML='<span style="color:var(--dim)">（工作区尚未创建——任务执行后会自动生成）</span>';
    }
  }catch(e){
    content.innerHTML='<span style="color:var(--red)">加载失败: '+escapeHtml(String(e))+'</span>';
  }
};
})();
