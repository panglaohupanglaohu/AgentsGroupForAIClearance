/**
 * AI Model Entry Clearance — 准入控制台控制器。
 *
 * 门禁目录、许可用途分级与治理角色全部来自 /api/v1/model-clearance/standard，
 * 页面不硬编码标准内容；申请提交 §7/§8/§10 部署上下文供后端门禁求值。
 */
(function () {
  'use strict';

  var ES = window.EngineState;
  var ER = window.EngineReducer;
  var EJ = window.EngineJudgment;
  var engineState = ES.create();
  var pollTimer = null;
  var standard = null;
  var contributors = null;
  var contributions = [];   // [{gate, kind, ref_id, label}]
  var selectedPart = null;  // 点选零件后点泳道挂入（键盘/触屏通路）
  var draggedPart = null;   // dataTransfer 在部分浏览器 drop 时取不到值，用它兜底
  var judgmentState = { dimensions: [], overall: null, group: 'summary', as_of: '' };

  function api() { return window.api; }
  function $(id) { return document.getElementById(id); }
  function esc(s) { return ER.esc(s); }
  function safeText(s) { return ER.safeText(s); }
  function checked(id) { var el = $(id); return el ? !!el.checked : false; }
  function val(id, fallback) { var el = $(id); return el ? el.value : (fallback || ''); }

  function today() { return new Date().toISOString().slice(0, 10); }

  /** §7/§8/§10 部署上下文；键名与后端 DeploymentContext 字段一致。 */
  function readDeployment() {
    return {
      hosting_environment: val('hosting_environment', 'lenovo_controlled'),
      hosting_region: val('hosting_region', 'ROW'),
      access_mode: val('access_mode', 'self_hosted_weights'),
      provider_hosted_in_prc: checked('provider_hosted_in_prc'),
      data_egress_to_prc: checked('data_egress_to_prc'),
      outbound_egress_controlled: checked('outbound_egress_controlled'),
      workload_segregated: checked('workload_segregated'),
      monitoring_and_audit_logging: checked('monitoring_and_audit_logging'),
      tool_access_allowlisted: checked('tool_access_allowlisted'),
      least_privilege_enforced: checked('least_privilege_enforced'),
      human_approval_for_consequential: checked('human_approval_for_consequential'),
      generated_code_treated_untrusted: checked('generated_code_treated_untrusted'),
      intended_use: val('intended_use').trim(),
      privacy_assessed: checked('privacy_assessed'),
      ip_licensing_reviewed: checked('ip_licensing_reviewed'),
      human_oversight_defined: checked('human_oversight_defined'),
      incident_response_defined: checked('incident_response_defined'),
      rollback_capability: checked('rollback_capability'),
      suspension_revocation_capable: checked('suspension_revocation_capable'),
      alternative_model_path: checked('alternative_model_path'),
      named_owner: val('named_owner').trim(),
      permitted_use: val('permitted_use', 'internal_row'),
      additional_assessment_complete: checked('additional_assessment_complete'),
    };
  }

  function readForm() {
    return {
      model_id: val('model_id').trim(),
      revision: val('revision').trim(),
      weights_uri: val('weights_uri').trim(),
      expected_signer_identity: val('expected_signer').trim() || null,
      as_of: val('as_of'),
      deployment: readDeployment(),
    };
  }

  /** 标准明确要求的申请侧必填项；缺失时后端会判 needs_info，这里提前提示。 */
  function standardErrors(form) {
    var errors = [];
    var d = form.deployment;
    if (!d.intended_use) errors.push('§7.3 要求记录预期用途 intended_use');
    if (!d.named_owner) errors.push('§8/§11 要求指定具名负责人 named_owner');
    if (d.permitted_use !== 'internal_row' && !d.additional_assessment_complete) {
      errors.push('§10 该许可用途分级需完成附加产品与用例评估');
    }
    return errors;
  }

  function isFastTrackIntake() {
    return !!(incoming && incoming.source === 'data-intelligence');
  }

  function blockingStandardErrors(form) {
    return [];
  }

  function validationForm(form) {
    return Object.assign({}, form, {
      revision: form.revision && !/^(main|latest|master|head)$/i.test(form.revision)
        ? form.revision
        : 'pending-evidence',
    });
  }

  function deriveReviewStartState(form) {
    return ES.deriveStartState(validationForm(form), runView());
  }

  function runView() {
    if (!engineState.runId) return null;
    return { run_id: engineState.runId, status: engineState.status };
  }

  // ── 标准目录（门禁 / 许可用途 / 治理角色） ─────────────────
  async function loadStandard() {
    try {
      standard = await api().request('/api/v1/model-clearance/standard');
    } catch (e) {
      var box = $('gate-lanes');
      if (box) box.innerHTML = '<div class="empty">无法读取准入标准: ' + esc(e.message || e) + '</div>';
      return;
    }
    renderGateLanes();
    renderGovernanceRoles();
    renderPermittedUseOptions();
  }

  // ── 弹性组装：情报零件 → 门禁泳道 ─────────────────────────
  async function loadContributors() {
    try {
      contributors = await api().request('/api/v1/model-clearance/contributors');
    } catch (e) {
      ['parts-teams', 'parts-documents', 'parts-sources', 'parts-runs'].forEach(function (id) {
        var box = $(id);
        if (box) box.innerHTML = '<div class="empty">' + esc(e.message || e) + '</div>';
      });
      return;
    }
    renderParts();
  }

  function partHtml(kind, refId, label, note, stale) {
    return (
      '<div class="part' + (stale ? ' is-stale' : '') + '" draggable="true" role="button" tabindex="0"' +
      ' data-kind="' + esc(kind) + '" data-ref="' + esc(refId) + '" data-label="' + esc(label) + '">' +
      '<span class="part-kind">' + esc(kind.toUpperCase()) + '</span>' +
      '<b>' + esc(label) + '</b><small>' + esc(note) + '</small></div>'
    );
  }

  function renderParts() {
    if (!contributors) return;

    var teams = contributors.teams || [];
    $('parts-teams').innerHTML = teams.length
      ? teams
          .map(function (t) {
            var note = t.has_analysis
              ? '最新分析 ' + (t.latest_as_of || '—') + ' · ' + (t.latest_title || '')
              : '尚无已发布分析，挂入后按缺证记录';
            return (
              partHtml('team', t.ref_id, t.label, note, !t.has_analysis) +
              '<button type="button" class="run-part js-run-team" data-team="' + esc(t.ref_id) + '">' +
              (t.has_analysis ? '↻ 重新采集' : '▶ 跑一次采集') + '</button>'
            );
          })
          .join('')
      : '<div class="empty">无情报团队</div>';

    var runs = contributors.runs || [];
    $('parts-runs').innerHTML = runs.length
      ? runs
          .map(function (r) {
            var note = (r.status || '') + ' · ' + (r.source_count || 0) + ' 个信息源';
            return partHtml('run', r.ref_id, r.label, note, r.status !== 'completed');
          })
          .join('')
      : '<div class="empty">尚无采集运行</div>';

    var docs = contributors.documents || [];
    $('parts-documents').innerHTML = docs.length
      ? docs
          .map(function (d) {
            return partHtml('document', d.ref_id, d.label, d.channel + ' · v' + d.version + ' · ' + (d.as_of || '—'), false);
          })
          .join('')
      : '<div class="empty">无已发布文档</div>';

    var srcs = contributors.sources || [];
    $('parts-sources').innerHTML = srcs.length
      ? srcs
          .map(function (s) {
            return partHtml('source', s.ref_id, s.label, (s.source_kind || '') + ' · ' + (s.enabled ? '启用' : '停用'), !s.enabled);
          })
          .join('')
      : '<div class="empty">无信息源</div>';

    bindRig();
  }

  // 零件与泳道都会重渲染，统一用委托绑定在不变的祖先上，避免重渲染后监听器丢失。
  function bindRig() {
    var rig = $('clearance-evidence');
    if (!rig || rig.dataset.rigBound === '1') return;
    rig.dataset.rigBound = '1';

    rig.addEventListener('dragstart', function (ev) {
      var el = ev.target.closest && ev.target.closest('.part');
      if (!el) return;
      draggedPart = readPart(el);
      el.classList.add('dragging');
      if (ev.dataTransfer) {
        ev.dataTransfer.effectAllowed = 'copy';
        try {
          ev.dataTransfer.setData('text/plain', JSON.stringify(draggedPart));
        } catch (e) { /* 兜底靠 draggedPart */ }
      }
    });

    rig.addEventListener('dragend', function (ev) {
      var el = ev.target.closest && ev.target.closest('.part');
      if (el) el.classList.remove('dragging');
      draggedPart = null;
      rig.querySelectorAll('.lane.over').forEach(function (l) { l.classList.remove('over'); });
    });

    function laneFrom(ev) {
      return ev.target.closest ? ev.target.closest('.lane') : null;
    }

    function allowDrop(ev) {
      var lane = laneFrom(ev);
      if (!lane) return;
      ev.preventDefault();
      if (ev.dataTransfer) ev.dataTransfer.dropEffect = 'copy';
      lane.classList.add('over');
    }
    rig.addEventListener('dragenter', allowDrop);
    rig.addEventListener('dragover', allowDrop);

    rig.addEventListener('dragleave', function (ev) {
      var lane = laneFrom(ev);
      if (lane && !lane.contains(ev.relatedTarget)) lane.classList.remove('over');
    });

    rig.addEventListener('drop', function (ev) {
      var lane = laneFrom(ev);
      if (!lane) return;
      ev.preventDefault();
      lane.classList.remove('over');
      addContribution(lane.getAttribute('data-gate'), payloadFrom(ev));
    });

    rig.addEventListener('click', function (ev) {
      var chipBtn = ev.target.closest('.js-drop-contrib');
      if (chipBtn) {
        removeContribution(parseInt(chipBtn.getAttribute('data-i'), 10));
        return;
      }
      if (ev.target.closest('.js-run-team')) return; // 由全局 click 处理

      var part = ev.target.closest('.part');
      if (part) {
        selectedPart = readPart(part);
        rig.querySelectorAll('.part').forEach(function (p) {
          p.classList.toggle('is-picked', p === part);
          p.setAttribute('aria-pressed', p === part ? 'true' : 'false');
        });
        rig.classList.add('has-picked');
        return;
      }

      var lane = ev.target.closest('.lane');
      if (lane && selectedPart) addContribution(lane.getAttribute('data-gate'), selectedPart);
    });

    rig.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Enter' && ev.key !== ' ') return;
      var hit = ev.target.closest('.part') || ev.target.closest('.lane');
      if (!hit) return;
      ev.preventDefault();
      hit.click();
    });
  }

  /** drop 载荷：优先 dataTransfer，取不到就用拖拽起始时存的零件。 */
  function payloadFrom(ev) {
    var raw = '';
    try {
      raw = ev.dataTransfer ? ev.dataTransfer.getData('text/plain') : '';
    } catch (e) { /* 某些浏览器限制读取 */ }
    if (raw) {
      try {
        return JSON.parse(raw);
      } catch (e) { /* 非本页拖入的内容 */ }
    }
    return draggedPart;
  }

  function readPart(el) {
    return {
      kind: el.getAttribute('data-kind'),
      ref_id: el.getAttribute('data-ref'),
      label: el.getAttribute('data-label'),
    };
  }

  var DEFAULT_GATE_AGENTS = {
    G0: { id: 'mc_infra', role: '基础设施架构师' },
    G1: { id: 'mc_supply', role: '供应链与制品完整性工程师' },
    G2: { id: 'mc_supply', role: '供应链与制品完整性工程师' },
    G3: { id: 'mc_security', role: 'AI模型安全审核人' },
    G4: { id: 'mc_redteam', role: '红队与威胁情报分析师' },
    G5: { id: 'mc_infra', role: '基础设施架构师' },
    G6: { id: 'mc_security', role: 'AI模型安全审核人' },
    G7: { id: 'mc_legal', role: 'AI模型法务审核人' },
    G8: { id: 'mc_operations', role: '持续保障与运营负责人' }
  };

  var currentApplication = null;

  function renderGateLanes() {
    var box = $('gate-lanes');
    if (!box || !standard) return;
    var gates = standard.gates || [];
    box.innerHTML = gates
      .map(function (g, idx) {
        var agentInfo = DEFAULT_GATE_AGENTS[g.gate] || { id: g.agent_id || 'mc_agent', role: g.owner_role || '审核人' };
        var agentId = g.agent_id || agentInfo.id;
        var agentRole = g.owner_role || agentInfo.role;
        var stepNum = idx + 1;
        return (
          '<div class="lane' + (g.hard_block ? ' is-hard-block' : '') + '" data-gate="' + esc(g.gate) + '">' +
          '<div class="lane-top">' +
            '<span class="lane-step">步骤 #' + stepNum + '</span>' +
            '<span class="lane-status-tag pending" data-status-gate="' + esc(g.gate) + '">待执行</span>' +
          '</div>' +
          '<div class="lane-head"><span class="lane-id">' + esc(g.gate) + '</span>' +
          '<span class="lane-section">§' + esc(g.section) + '</span>' +
          (g.hard_block ? '<span class="lane-flag">HARD BLOCK</span>' : '') +
          '</div><b>' + esc(g.name) + '</b>' +
          '<div class="lane-agent" title="负责本门禁取证与审核的智能体">' +
            '<span class="lane-agent-icon">🤖</span>' +
            '<span class="lane-agent-name">' + esc(agentRole) + '</span>' +
            '<code class="lane-agent-id">' + esc(agentId) + '</code>' +
          '</div>' +
          '<div class="lane-exec" data-exec-gate="' + esc(g.gate) + '">' + esc(agentId) + ' 待命</div>' +
          '<div class="lane-drop" data-gate="' + esc(g.gate) + '"></div></div>'
        );
      })
      .join('');
    bindRig();
    renderContributionChips();
    updateGateLanesStatus();
    updateStandardCount();
    refreshLaneOverflow();
  }

  function updateGateLanesStatus() {
    var box = $('gate-lanes');
    if (!box || !standard) return;
    var gates = standard.gates || [];
    var app = currentApplication;
    var verdicts = (app && app.verdicts) || [];
    var verdictByGate = {};
    verdicts.forEach(function (v) { verdictByGate[v.gate] = v; });

    var evidencesByGate = {};
    ((app && app.evidence) || []).forEach(function (e) {
      if (!e.advisory) evidencesByGate[e.gate] = (evidencesByGate[e.gate] || 0) + 1;
    });

    var isRunning = engineState && (engineState.status === 'running' || engineState.status === 'gating' || engineState.status === 'submitted');
    var runningGate = null;
    if (isRunning) {
      for (var i = 0; i < gates.length; i++) {
        var gId = gates[i].gate;
        if (!verdictByGate[gId]) {
          runningGate = gId;
          break;
        }
      }
    }

    gates.forEach(function (g) {
      var gateEl = box.querySelector('.lane[data-gate="' + g.gate + '"]');
      if (!gateEl) return;
      var tagEl = gateEl.querySelector('[data-status-gate="' + g.gate + '"]');
      var execEl = gateEl.querySelector('[data-exec-gate="' + g.gate + '"]');
      var v = verdictByGate[g.gate];
      var agentInfo = DEFAULT_GATE_AGENTS[g.gate] || { id: g.agent_id || 'mc_agent', role: g.owner_role || '审核人' };
      var agentId = g.agent_id || agentInfo.id;

      gateEl.classList.remove('is-running', 'is-pass', 'is-fail', 'is-needs_info');

      if (v) {
        var evCount = evidencesByGate[g.gate] || 0;
        if (v.verdict === 'pass') {
          gateEl.classList.add('is-pass');
          if (tagEl) { tagEl.className = 'lane-status-tag pass'; tagEl.textContent = '通过 ✓'; }
          if (execEl) {
            execEl.className = 'lane-exec pass';
            execEl.textContent = agentId + ' 取证完成 (' + evCount + '项)';
          }
        } else if (v.verdict === 'needs_info') {
          gateEl.classList.add('is-needs_info');
          if (tagEl) { tagEl.className = 'lane-status-tag needs_info'; tagEl.textContent = '待补证 ?'; }
          if (execEl) {
            execEl.className = 'lane-exec needs_info';
            execEl.textContent = agentId + ' 待补: ' + (v.failed_checks || []).join(', ');
          }
        } else {
          gateEl.classList.add('is-fail');
          if (tagEl) { tagEl.className = 'lane-status-tag fail'; tagEl.textContent = '未通过 ✗'; }
          if (execEl) {
            execEl.className = 'lane-exec fail';
            execEl.textContent = agentId + ' 阻断: ' + (v.failed_checks || []).join(', ');
          }
        }
      } else if (isRunning && g.gate === runningGate) {
        gateEl.classList.add('is-running');
        if (tagEl) { tagEl.className = 'lane-status-tag running'; tagEl.textContent = '执行中...'; }
        if (execEl) {
          execEl.className = 'lane-exec running';
          execEl.textContent = '🤖 ' + agentId + ' 正在审核...';
        }
      } else if (isRunning) {
        if (tagEl) { tagEl.className = 'lane-status-tag pending'; tagEl.textContent = '等待中'; }
        if (execEl) { execEl.className = 'lane-exec'; execEl.textContent = '等待前序门禁'; }
      } else if (app && (app.status === 'completed' || app.status === 'approved' || app.status === 'approved_with_conditions' || app.status === 'rejected')) {
        if (tagEl) { tagEl.className = 'lane-status-tag pending'; tagEl.textContent = '未执行'; }
        if (execEl) { execEl.className = 'lane-exec'; execEl.textContent = '前序门禁阻断，已跳过'; }
      } else {
        if (tagEl) { tagEl.className = 'lane-status-tag pending'; tagEl.textContent = '待执行'; }
        if (execEl) { execEl.className = 'lane-exec'; execEl.textContent = agentId + ' 待命'; }
      }
    });
  }

  function refreshLaneOverflow() {
    var lanes = $('gate-lanes');
    var hint = $('lanes-hint');
    if (!lanes) return;
    var over = lanes.scrollWidth > lanes.clientWidth + 1;
    lanes.classList.toggle('is-overflowing', over);
    if (hint) hint.hidden = !over;
  }

  function addContribution(gate, part) {
    if (!gate || !part || !part.ref_id) return;
    var dup = contributions.some(function (c) {
      return c.gate === gate && c.kind === part.kind && c.ref_id === part.ref_id;
    });
    if (dup) return;
    contributions.push({ gate: gate, kind: part.kind, ref_id: part.ref_id, label: part.label || part.ref_id });
    renderContributionChips();
    updateStandardCount();
    renderFromState();
  }

  function removeContribution(index) {
    contributions.splice(index, 1);
    renderContributionChips();
    updateStandardCount();
    renderFromState();
  }

  function renderContributionChips() {
    document.querySelectorAll('.lane-drop').forEach(function (slot) {
      var gate = slot.getAttribute('data-gate');
      var rows = contributions
        .map(function (c, i) { return { c: c, i: i }; })
        .filter(function (x) { return x.c.gate === gate; });
      slot.innerHTML = rows.length
        ? rows
            .map(function (x) {
              return (
                '<div class="chip"><span title="' + esc(x.c.kind + ' · ' + x.c.ref_id) + '">' +
                esc(x.c.label) + '</span>' +
                '<button type="button" class="js-drop-contrib" data-i="' + x.i + '" aria-label="移除参考情报">移除</button></div>'
              );
            })
            .join('')
        : '<div class="lane-empty">拖入情报零件</div>';
    });
  }

  function updateStandardCount() {
    var count = $('standard-count');
    if (!count || !standard) return;
    var gates = (standard.gates || []).length;
    count.textContent = gates + ' 道门禁 · 已挂 ' + contributions.length + ' 个情报来源';
  }

  function renderGovernanceRoles() {
    var box = $('standard-roles');
    if (!box || !standard) return;
    box.innerHTML = (standard.governance_roles || [])
      .map(function (r) {
        return '<div class="role-card"><b>' + esc(r.label_zh || r.role) + ' · ' + esc(r.role) + '</b>' + esc(r.desc || '') + '</div>';
      })
      .join('');
  }

  function renderPermittedUseOptions() {
    var sel = $('permitted_use');
    if (!sel || !standard) return;
    var tiers = standard.permitted_use_tiers || [];
    sel.innerHTML = tiers
      .map(function (t) {
        return '<option value="' + esc(t.value) + '">§' + esc(t.section) + ' ' + esc(t.label_zh) + '</option>';
      })
      .join('');
    updatePermittedUseNote();
  }

  function currentTier() {
    if (!standard) return null;
    var v = val('permitted_use');
    var tiers = standard.permitted_use_tiers || [];
    for (var i = 0; i < tiers.length; i++) {
      if (tiers[i].value === v) return tiers[i];
    }
    return null;
  }

  function updatePermittedUseNote() {
    var note = $('permitted_use_note');
    var tier = currentTier();
    if (!note) return;
    if (!tier) {
      note.textContent = '选择分级后显示该分级要求的附加评估条目。';
      return;
    }
    if (!tier.requires_additional_assessment) {
      note.textContent = tier.note || '该分级为基线保障范围，无需附加评估。';
      return;
    }
    note.textContent =
      (tier.note || '') + ' 附加评估条目：' + (tier.additional_criteria || []).join('、');
  }

  // ── §9 保障记录：按标准要求装配完整审核报告 ─────────────────
  var reportRecord = null;
  var reportKey = '';

  var OUTCOME_ZH = {
    approved: '批准 / Approved',
    approved_with_conditions: '有条件批准 / Approved with Conditions',
    restricted: '受限 / Restricted',
    not_approved: '不批准 / Not Approved'
  };
  var VERDICT_ZH = { pass: '通过', fail: '未通过', needs_info: '待补证', not_assessed: '未评估' };

  function block(title, sub, body) {
    return (
      '<div class="report-block"><h3>' + esc(title) +
      (sub ? '<em>' + esc(sub) + '</em>' : '') + '</h3>' +
      '<div class="report-block-body">' + body + '</div></div>'
    );
  }

  function kvGrid(pairs) {
    return '<div class="report-kv">' + pairs.map(function (p) {
      return '<div><b>' + esc(p[0]) + '</b>：' + esc(p[1] === '' || p[1] == null ? '—' : String(p[1])) + '</div>';
    }).join('') + '</div>';
  }

  function bulletList(items, empty) {
    if (!items || !items.length) return '<div class="report-note">' + esc(empty) + '</div>';
    return '<ul class="report-list">' + items.map(function (t) {
      return '<li>' + esc(t) + '</li>';
    }).join('') + '</ul>';
  }

  function renderArtifact(rec) {
    var a = rec.artifact_assessed;
    var body = kvGrid([
      ['模型标识', a.model_id],
      ['版本 / Revision', a.revision],
      ['根摘要 Digest', a.root_digest],
      ['权重来源 URI', a.weights_uri],
      ['预期签名主体', a.expected_signer_identity],
      ['申请单号', rec.application.application_id]
    ]);
    if (a.custody_chain.length) {
      body += '<table class="report-table"><thead><tr><th>保管步骤</th><th>输入摘要</th><th>输出摘要</th><th>执行方</th><th>时间</th></tr></thead><tbody>' +
        a.custody_chain.map(function (s) {
          return '<tr><td>' + esc(s.step_type) + '</td><td>' + esc((s.input_digest || '').slice(0, 16)) +
            '…</td><td>' + esc((s.output_digest || '').slice(0, 16)) + '…</td><td>' + esc(s.performed_by) +
            '</td><td>' + esc(s.performed_at) + '</td></tr>';
        }).join('') + '</tbody></table>';
    } else {
      body += '<div class="report-note">未登记保管链步骤（§6.1 血缘信息以扫描器证据为准）。</div>';
    }
    return block('1. 受评的模型制品与版本', '§9 · §6.1', body);
  }

  function renderEvidence(rec) {
    var e = rec.evidence_reviewed;
    var rows = e.decisive.map(function (it) {
      return '<tr><td>' + esc(it.gate) + ' §' + esc(it.section) + '</td><td>' + esc(it.check_id) +
        '</td><td>' + esc(it.collector) + '@' + esc(it.collector_version) + '</td><td>' +
        esc(it.collected_at) + '</td><td><code>' + esc((it.digest || '').slice(0, 12)) + '…</code></td><td>' +
        esc(it.status) + '</td></tr>';
    }).join('');
    var body = '<div class="report-note">裁决性证据 ' + e.decisive_count + ' 份 · 参考情报 ' + e.advisory_count + ' 份。' + esc(e.note) + '</div>';
    body += rows
      ? '<table class="report-table"><thead><tr><th>门禁</th><th>检查项</th><th>采集器</th><th>采集时间</th><th>摘要</th><th>状态</th></tr></thead><tbody>' + rows + '</tbody></table>'
      : '<div class="report-note">尚无裁决性证据。</div>';
    return block('2. 已复核的证据', '§9', body);
  }

  function advisoryBlock(adv) {
    if (!adv) return '';
    if (adv.error) {
      return '<div class="adv adv-error">分析未生成：' + esc(adv.error) + '</div>';
    }
    if (!adv.analysis && !adv.recommendation) return '';
    return (
      '<div class="adv">' +
      (adv.analysis ? '<p><b>分析</b>' + esc(adv.analysis) + '</p>' : '') +
      (adv.recommendation ? '<p><b>建议</b>' + esc(adv.recommendation) + '</p>' : '') +
      (adv.risk_if_ignored ? '<p><b>不处理的风险</b>' + esc(adv.risk_if_ignored) + '</p>' : '') +
      '<span class="adv-sig">参考性分析 · 由 ' + esc(adv.generated_by) + ' 生成，不参与判定</span>' +
      '</div>'
    );
  }

  function renderMethodology(rec) {
    var body = rec.methodology_and_results.map(function (m) {
      var checks = m.checks.map(function (c) {
        return '<li><span class="report-pill ' + esc(c.result) + '">' + esc(VERDICT_ZH[c.result] || c.result) +
          '</span> ' + esc(c.check_id) + (c.blocker ? ' <span class="report-pill blocker">Blocker</span>' : '') +
          ' — ' + esc(c.requirement) + advisoryBlock(c.advisory) + '</li>';
      }).join('');
      return (
        '<details class="report-gate ' + esc(m.verdict) + '"><summary>' +
        '<b>' + esc(m.gate) + ' §' + esc(m.section) + ' ' + esc(m.name) + '</b>' +
        '<span class="report-pill ' + esc(m.verdict) + '">' + esc(VERDICT_ZH[m.verdict] || m.verdict) + '</span>' +
        (m.hard_block ? '<span class="report-pill blocker">硬红线</span>' : '') +
        '<span class="report-pill">' + (m.checks_total - m.checks_failed) + '/' + m.checks_total + ' 检查项通过</span>' +
        '<span class="report-pill">责任职能：' + esc(m.owner_role) + '</span>' +
        '</summary><div class="report-gate-detail">' +
        '<div><b>标准要求覆盖点</b></div>' + bulletList(m.standard_criteria, '标准未列举细项') +
        '<div><b>测试方法（采集器）</b></div>' + bulletList(m.collectors, '本门未运行采集器') +
        '<div><b>检查项结果</b></div><ul class="report-list">' + checks + '</ul>' +
        '<div class="report-note">判定方：' + esc(m.decided_by || '—') + ' · 判定时间：' + esc(m.decided_at || '—') +
        ' · 引用证据 ' + m.evidence_refs.length + ' 份</div>' +
        '</div></details>'
      );
    }).join('');
    return block('3. 测试方法与结果', '§9 · §6/§7/§8 逐门', body);
  }

  function renderComparative(rec) {
    var adv = rec.evidence_reviewed.advisory;
    if (!adv.length) {
      return block('4. 对比测试与外部情报', '§9（适当时）',
        '<div class="report-note">本次评审未引入外部采集与分析情报。</div>');
    }
    var body = adv.map(function (it) {
      var an = it.analysis || {};
      var steps = (an.reasoning_steps || []).map(function (s) {
        return (s.stage || '') + '（' + (s.status || '') + '）' + (s.detail ? '：' + s.detail : '');
      });
      return (
        '<details class="report-gate"><summary><b>' + esc(it.label || it.check_id) + '</b>' +
        '<span class="report-pill">' + esc(it.gate) + ' §' + esc(it.section) + '</span>' +
        '<span class="report-pill">' + esc(it.kind || 'source') + '</span>' +
        '<span class="report-pill ' + (it.status === 'ok' ? 'pass' : 'needs_info') + '">' + esc(it.status) + '</span>' +
        '</summary><div class="report-gate-detail">' +
        kvGrid([['证据分', an.evidence_score], ['信号强度', an.signal_strength]]) +
        '<div style="margin-top:6px"><b>推理链摘要</b></div>' + bulletList(steps, '该来源未记录推理步骤') +
        '<div><b>待解问题</b></div>' + bulletList(an.open_questions, '无') +
        '</div></details>'
      );
    }).join('');
    return block('4. 对比测试与外部情报', '§9（适当时）· 仅作风险信号',
      body + '<div class="report-note">' + esc(rec.evidence_reviewed.note) + '</div>');
  }

  function renderFindings(rec) {
    var f = rec.findings_and_mitigations;
    if (!f.length) {
      return block('5. 重大发现与缓解措施', '§9', '<div class="report-note">未产生未通过项或复核发现。</div>');
    }
    var body = '<table class="report-table"><thead><tr><th>门禁</th><th>检查项</th><th>发现</th><th>严重性</th><th>来源</th><th>缓解措施</th></tr></thead><tbody>' +
      f.map(function (it) {
        return '<tr><td>' + esc(it.gate) + ' §' + esc(it.section) + '</td><td>' + esc(it.check_id) +
          (it.blocker ? ' <span class="report-pill blocker">Blocker</span>' : '') +
          '</td><td>' + esc(it.finding) + '</td><td>' + esc(it.severity) + '</td><td>' + esc(it.source) +
          '</td><td>' + esc(it.mitigation) + '</td></tr>';
      }).join('') + '</tbody></table>';
    return block('5. 重大发现与缓解措施', '§9', body);
  }

  function renderConditions(rec) {
    var c = rec.conditions_and_restrictions;
    var body = '<div><b>条件</b></div>' + bulletList(c.conditions, '无附加条件') +
      '<div><b>例外与偏离（§12）</b></div>' + bulletList(c.exceptions, '未登记例外；例外须经治理流程正式记录并风险接受') +
      kvGrid([
        ['运行时档位', c.runtime_profile],
        ['适用范围', (c.scope || []).join(' / ')],
        ['有效期至', c.expires_at]
      ]);
    return block('7. 条件、限制与例外', '§9 · §12', body);
  }

  function renderDecision(rec) {
    var d = rec.decision;
    if (!d) {
      return block('8. 最终保障裁决', '§9', '<div class="report-note">尚未产生裁决。</div>');
    }
    var body = '<div class="report-decision"><span class="verdict ' + esc(d.verdict) + '">' +
      esc(OUTCOME_ZH[d.verdict] || d.verdict) + '</span>' +
      (d.hard_block ? '<span class="report-pill blocker">§3 硬红线命中</span>' : '') +
      '<span class="report-pill">裁决时间 ' + esc(d.decided_at) + '</span></div>' +
      '<div class="report-note">' + esc(d.reason) + '</div>';
    var u = rec.permitted_use;
    body += kvGrid([
      ['申请用途', u.label_zh + '（§' + u.section + '）'],
      ['需附加评估', u.requires_additional_assessment ? '是' : '否'],
      ['附加评估已完成', u.additional_assessment_complete ? '是' : '否'],
      ['用途要求满足', u.satisfied ? '满足' : '未满足']
    ]);
    if (u.requires_additional_assessment) {
      body += '<div style="margin-top:6px"><b>§' + esc(u.section) + ' 附加评估条目</b></div>' +
        bulletList(u.additional_criteria, '标准未列举');
    }
    body += '<div class="report-note">' + esc(u.note) + '</div>';
    var g = rec.governance;
    body += '<div style="margin-top:8px"><b>§11 治理归属</b></div>' +
      kvGrid([['申请人', g.applicant], ['具名负责人 Own', g.own]]) +
      '<div class="report-note">Evaluate 职能分工：' +
      esc(g.evaluate.map(function (x) { return x.gate + ' ' + x.owner_role; }).join(' · ')) + '</div>';
    return block('8. 最终保障裁决与许可用途', '§9 · §10 · §11', body);
  }

  function paintReport(rec) {
    var root = $('reports');
    if (!root) return;
    var buttons = [$('btn-export-report'), $('btn-open-report'), $('btn-advise-blockers')];
    function setDisabled(flag) {
      buttons.forEach(function (b) { if (b) b.disabled = flag; });
    }
    if (!rec || !rec.assessed) {
      root.innerHTML = '<div class="report-empty">尚未产生门禁裁决。启动评审后，这里按 ' +
        esc(rec ? rec.standard.name : 'Open-Weight Model Assurance Standard') + ' §9 生成完整保障记录。</div>';
      setDisabled(true);
      return;
    }
    setDisabled(false);
    var a = rec.artifact_assessed;
    var e = rec.evidence_reviewed;
    var failed = rec.methodology_and_results.filter(function (m) { return m.verdict === 'fail'; }).length;
    root.innerHTML =
      '<div class="report-summary">' +
      '<div class="report-summary-card"><strong>受评对象</strong><span>' + esc(a.model_id) + ' @ ' + esc(a.revision) + '</span></div>' +
      '<div class="report-summary-card"><strong>保障裁决</strong><span>' +
      esc(rec.decision ? (OUTCOME_ZH[rec.decision.verdict] || rec.decision.verdict) : rec.application.status) + '</span></div>' +
      '<div class="report-summary-card"><strong>取证规模</strong><span>' +
      rec.methodology_and_results.length + ' 道门禁 · ' + failed + ' 道未通过 · ' +
      e.decisive_count + ' 份裁决性证据 · ' + e.advisory_count + ' 份参考情报</span></div>' +
      '</div>' +
      '<div class="report-note">依据 ' + esc(rec.standard.name) + ' v' + esc(rec.standard.version) +
      ' §9 装配 · 生成于 ' + esc(rec.generated_at) + '</div>' +
      renderArtifact(rec) + renderEvidence(rec) + renderMethodology(rec) + renderComparative(rec) +
      renderFindings(rec) +
      block('6. 残余风险', '§5 · §9', bulletList(rec.residual_risks, '未记录无法完全控制或独立验证的残余风险')) +
      renderConditions(rec) + renderDecision(rec);
  }

  async function renderReportIndex(app) {
    if (!$('reports')) return;
    if (!app || !(app.verdicts || []).length) {
      reportRecord = null;
      paintReport(null);
      return;
    }
    // 轮询期间只在申请真正变化时重取报告，避免每 500ms 打一次后端。
    var key = app.application_id + '|' + app.updated_at + '|' + app.status;
    if (key === reportKey && reportRecord) return;
    try {
      reportRecord = await api().request(
        '/api/v1/model-clearance/applications/' + encodeURIComponent(app.application_id) + '/assurance-record'
      );
      reportKey = key;
      paintReport(reportRecord);
    } catch (err) {
      console.warn(err);
    }
  }

  // ── 从开放权重资源页带入待评审模型 ─────────────────────────
  var incoming = null;

  function readIncoming() {
    var q = new URLSearchParams(window.location.search);
    var modelId = (q.get('model_id') || '').trim();
    if (!modelId) return null;
    return {
      model_id: modelId.slice(0, 128),
      revision: (q.get('revision') || '').trim().slice(0, 64),
      weights_uri: (q.get('weights_uri') || '').trim().slice(0, 256),
      source: q.get('source') === 'data-intelligence' ? 'data-intelligence' : '',
    };
  }

  function applyIncoming() {
    if (!incoming) return;
    if ($('model_id')) $('model_id').value = incoming.model_id;
    // 不可变版本未知时保持未知，由 G1 标为 needs_info，禁止伪造 v1.0。
    if ($('revision')) {
      $('revision').value = incoming.revision && !/^(main|latest|master|head)$/i.test(incoming.revision)
        ? incoming.revision
        : '';
    }
    if ($('weights_uri')) $('weights_uri').value = incoming.weights_uri || '';
    if (isFastTrackIntake() && $('extended-application-fields')) {
      $('extended-application-fields').hidden = true;
    }
  }

  function renderIntakeNotice(errors, reviewGaps) {
    var box = $('intake-notice');
    if (!box || !incoming) return;
    box.hidden = false;
    reviewGaps = reviewGaps || [];
    if (isFastTrackIntake() && !errors.length) {
      box.className = 'intake-notice ready';
      box.innerHTML = '<b>模型评审快速入口</b><code>' + esc(incoming.model_id) +
        '</code> 已带入现有模型事实，可直接运行模型门禁。申请人、用途、负责人和部署信息不会伪造，也不阻断本次模型评审。' +
        (reviewGaps.length
          ? '<p>未提供的工作流信息将保留为未知，不作为模型证据。</p>'
          : '') +
        '<button type="button" class="btn btn-sm" data-intake-start>直接运行模型评审</button>' +
        '<button type="button" class="btn secondary btn-sm" data-intake-edit aria-expanded="false">查看可选部署信息</button>';
      return;
    }
    if (!errors.length) {
      box.className = 'intake-notice ready';
      box.innerHTML = '<b>已带入待评审模型</b><code>' + esc(incoming.model_id) +
        '</code> 申请信息齐备，可直接启动 9 道门禁评审。' +
        '<button type="button" class="btn btn-sm" data-intake-start>启动准入评审</button>';
      return;
    }
    box.className = 'intake-notice';
    box.innerHTML = '<b>已带入待评审模型</b><code>' + esc(incoming.model_id) +
      '</code> 评审尚未启动，标准要求以下申请项先补齐：<ul>' +
      errors.map(function (e) { return '<li>' + esc(e) + '</li>'; }).join('') + '</ul>';
  }

  function syncPrimaryButton() {
    var form = readForm();
    var d = deriveReviewStartState(form);
    var extra = blockingStandardErrors(form);
    renderIntakeNotice(
      (d.action === 'validate' ? (d.errors || []) : []).concat(extra),
      isFastTrackIntake() ? standardErrors(form) : []
    );
    if (extra.length && d.action !== 'validate') {
      d = { label: '补齐标准必填项', action: 'validate', disabled: false, errors: extra };
    } else if (extra.length) {
      d.errors = (d.errors || []).concat(extra);
    }
    var btn = $('btn-engine-start');
    if (btn) {
      btn.textContent = d.label;
      btn.disabled = !!d.disabled;
      btn.dataset.action = d.action;
    }
    var pipelineBtn = $('btn-pipeline-start');
    if (pipelineBtn) {
      pipelineBtn.textContent = d.label;
      pipelineBtn.disabled = !!d.disabled;
      pipelineBtn.dataset.action = d.action;
    }
    var hint = $('engine-start-hint');
    if (hint) {
      if (d.errors && d.errors.length) {
        hint.textContent = d.errors.join('；');
        hint.className = 'stat warning-hint';
      } else {
        hint.textContent = '可直接运行模型门禁；未知技术事实会标记待补证，不会用默认值冒充证据。';
        hint.className = 'stat muted';
      }
    }
    var pipelineHint = $('pipeline-start-hint');
    if (pipelineHint) {
      pipelineHint.textContent = d.action === 'retry' || d.action === 'rerun'
        ? '基于当前模型事实创建新运行，旧记录保留'
        : (d.errors && d.errors.length ? d.errors.join('；') : '直接从流水线启动当前模型审核');
      pipelineHint.className = d.errors && d.errors.length ? 'stat warning-hint' : 'stat muted';
    }
    if ($('btn-start')) {
      $('btn-start').disabled =
        !engineState.runId || engineState.status === 'running' || engineState.status === 'completed';
    }
    if ($('btn-cancel')) {
      $('btn-cancel').disabled = engineState.status !== 'running' && engineState.status !== 'queued';
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

  function renderJudgmentPanel() {
    if (!EJ) return;
    if (!judgmentState.dimensions.length) {
      judgmentState.as_of = val('as_of') || today();
      judgmentState.dimensions = EJ.emptyDimensions(judgmentState.as_of);
      judgmentState.overall = EJ.overallFromDimensions(judgmentState.dimensions, judgmentState.as_of);
    }
    EJ.render(document, judgmentState);
  }

  function renderFromState() {
    var s = engineState;
    var phase = s.phase || 'assembly';
    var route = ER.routeKey(phase);
    var routeOrder = ['context', 'judgment', 'plan', 'risk', 'portfolio'];
    var routeIndex = routeOrder.indexOf(route);
    if (routeIndex < 0) routeIndex = 0;

    var phaseLabels = {
      assembly: '待提交',
      context: '§3/§6.1 登记与制品',
      analysis: '§6.2/§6.3 供应链与行为',
      planning: '§6.4/§7.1 红队与部署',
      risk: '§7.2/§7.3 权限与法务',
      portfolio: '§8/§9 保障与裁决',
      reflection: '准入审计',
    };

    if ($('engine-phase')) $('engine-phase').textContent = phaseLabels[phase] || s.status || '待启动';
    if ($('engine-progress')) $('engine-progress').textContent = (s.progress || 0) + '%';
    if ($('engine-progress-bar')) $('engine-progress-bar').style.width = (s.progress || 0) + '%';
    if ($('engine-hud')) {
      $('engine-hud').classList.toggle('live', s.status === 'running');
      $('engine-hud').classList.toggle('reconnect', s.connection === 'reconnecting');
    }
    if ($('engine-conn')) {
      var connMap = { idle: '未连接', polling: '轮询', live: 'SSE', reconnecting: '重连中', error: '连接错误' };
      $('engine-conn').textContent = connMap[s.connection] || s.connection;
    }

    document.querySelectorAll('.route-stop').forEach(function (stop) {
      var key = stop.getAttribute('data-route');
      var idx = routeOrder.indexOf(key);
      stop.classList.toggle('active', key === route);
      stop.classList.toggle('done', idx >= 0 && idx < routeIndex);
    });

    var c = s.insights.context;
    var contextText = c
      ? c.summary
      : contributions.length
        ? '已组装 ' + contributions.length + ' 个情报来源，跨 ' +
          new Set(contributions.map(function (x) { return x.gate; })).size +
          ' 道门禁；提交后作为参考情报随裁决留痕。'
        : '尚未组装情报来源；可把智能体团队的采集分析拖入任意门禁泳道。';
    setInsight('context-card', contextText, null, route === 'context');
    var j = s.insights.judgment;
    setInsight(
      'judgment-card',
      j
        ? j.claim +
            (j.confidence != null ? ' · 置信 ' + Math.round(j.confidence * 100) + '%' : '') +
            (j.direction ? ' · ' + j.direction : '')
        : '等待 AI-BOM、CVE 与行为评估结论。',
      null,
      route === 'judgment'
    );
    var p = s.insights.plan;
    setInsight('plan-card', p ? p.objective || '' : '等待威胁情报、红队发现项与部署数据流核验。', null, route === 'plan');
    var r = s.insights.risk;
    setInsight(
      'risk-card',
      r ? r.gate + '：' + r.reason : '等待工具权限边界与许可证/用例法务判定。',
      r ? 'warning' : null,
      route === 'risk'
    );
    var pf = s.insights.portfolio;
    setInsight(
      'portfolio-card',
      pf ? pf.summary + (pf.disclaimer ? ' · ' + pf.disclaimer : '') : '待审，等待 Clearance Board 裁决。',
      'positive',
      route === 'portfolio'
    );
    var tier = currentTier();
    setInsight(
      'revenue-card',
      tier
        ? '§' + tier.section + ' ' + tier.label_zh +
            (tier.requires_additional_assessment
              ? checked('additional_assessment_complete')
                ? ' · 附加评估已完成'
                : ' · 附加评估未完成，将判为受限'
              : ' · 基线保障范围内')
        : '尚未确定许可用途分级与附加评估状态。',
      tier && tier.requires_additional_assessment && !checked('additional_assessment_complete') ? 'warning' : null,
      false
    );

    if (EJ && (route === 'judgment' || s.status === 'running' || s.status === 'completed')) {
      judgmentState.as_of = val('as_of') || judgmentState.as_of || today();
      if (!judgmentState.dimensions.length) {
        judgmentState.dimensions = EJ.emptyDimensions(judgmentState.as_of);
      }
      s.events.forEach(function (ev) {
        if (!ev || !ev.structured) return;
        (ev.structured.judgment_dimensions || []).forEach(function (d) {
          judgmentState.dimensions = EJ.mergeEventDimension(judgmentState.dimensions, d);
        });
        if (ev.structured.dimension) {
          judgmentState.dimensions = EJ.mergeEventDimension(judgmentState.dimensions, ev.structured.dimension);
        }
      });
      judgmentState.overall = EJ.overallFromDimensions(judgmentState.dimensions, judgmentState.as_of);
      renderJudgmentPanel();
    }

    var box = $('timeline');
    if (box) {
      if (!s.events.length) {
        box.innerHTML = '<div class="empty">创建并启动申请后显示节点进度</div>';
      } else {
        box.innerHTML = s.events
          .slice()
          .sort(function (a, b) { return (a.seq || 0) - (b.seq || 0); })
          .map(function (e) {
            return (
              '<div class="event" data-seq="' + esc(e.seq) + '"><div class="meta">#' + esc(e.seq) +
              ' · ' + esc(e.phase) + ' · ' + esc(e.participant) + ' · ' + esc(e.status) +
              '</div><div>' + esc(safeText(e.content)) + '</div></div>'
            );
          })
          .join('');
        box.scrollTop = box.scrollHeight;
      }
    }

    updateGateLanesStatus();
    syncPrimaryButton();
  }

  function applyApp(app) {
    if (!app) return;
    currentApplication = app;
    engineState.runId = app.application_id || app.run_id;
    engineState.status = app.status || engineState.status;
    if (app.error) engineState.error = app.error;
    if (app.status === 'completed' || app.status === 'approved' || app.status === 'approved_with_conditions') {
      engineState.progress = 100;
    }
    updateGateLanesStatus();
  }

  function ingestEvents(list) {
    engineState = ER.reduceMany(engineState, list || []);
  }

  // ── Networking ────────────────────────────────────────────
  async function loadRuntimeHealth() {
    try {
      var h = await api().request('/api/v1/model-clearance/registry');
      var list = (h && h.registry) || [];
      $('runtime-health').textContent = JSON.stringify(
        {
          status: 'ok',
          clearance_engine: 'online',
          active_models: list.filter(function (x) { return x.status === 'active'; }).length,
          revoked_models: list.filter(function (x) { return x.status === 'revoked'; }).length,
          total_registry_entries: list.length,
          timestamp: new Date().toISOString(),
        },
        null,
        2
      );
    } catch (e) {
      $('runtime-health').textContent = e.message || String(e);
    }
  }

  async function createApplication(autoStart) {
    var form = readForm();
    var errors = ES.validateEngineForm(validationForm(form)).concat(blockingStandardErrors(form));
    if (errors.length) {
      engineState.formErrors = errors;
      syncPrimaryButton();
      alert(errors.join('\n'));
      return null;
    }

    var app = await api().request('/api/v1/model-clearance/applications', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model_id: form.model_id,
        applicant: '',
        revision: form.revision,
        weights_uri: form.weights_uri,
        expected_signer_identity: form.expected_signer_identity,
        deployment: {},
        review_scope: 'model',
        contributions: contributions,
        auto_submit: !!autoStart,
      }),
    });

    // api.request 失败时返回 null；不拦住就会把控制台清成空白，评审人看不到任何原因。
    if (!app || !app.application_id) {
      var reason = (api()._lastError || {}).message || '服务未返回申请单';
      engineState.formErrors = ['创建准入申请失败：' + reason];
      syncPrimaryButton();
      renderFromState();
      alert('创建准入申请失败：' + reason);
      return null;
    }

    engineState = ES.create();
    applyApp(app);
    engineState.lastSeq = 0;
    engineState.events = [];
    judgmentState.dimensions = [];
    try {
      localStorage.setItem('sa_clearance_app_id', app.application_id);
    } catch (e) { /* ignore */ }
    renderFromState();
    if (app.status === 'running' || app.status === 'gating' || autoStart) beginLiveJourney();
    return app;
  }

  async function submitApplication() {
    if (!engineState.runId) return;
    var res = await api().request(
      '/api/v1/model-clearance/applications/' + encodeURIComponent(engineState.runId) + '/submit',
      { method: 'POST' }
    );
    if (!res) {
      var reason = (api()._lastError || {}).message || '服务未返回结果';
      alert('提交准入评审失败：' + reason);
      return;
    }
    applyApp(res);
    renderFromState();
    beginLiveJourney();
  }

  async function retryApplication() {
    if (!engineState.runId) return null;
    var app = await api().request(
      '/api/v1/model-clearance/applications/' + encodeURIComponent(engineState.runId) + '/retry',
      { method: 'POST' }
    );
    if (!app || !app.application_id) {
      var reason = (api()._lastError || {}).message || '服务未返回新的审核运行';
      alert('重新审核失败：' + reason);
      return null;
    }
    engineState = ES.create();
    applyApp(app);
    engineState.lastSeq = 0;
    engineState.events = [];
    judgmentState.dimensions = [];
    try {
      localStorage.setItem('sa_clearance_app_id', app.application_id);
    } catch (e) { /* ignore */ }
    renderFromState();
    beginLiveJourney();
    return app;
  }

  async function cancelApplication() {
    if (!engineState.runId) return;
    stopLiveJourney();
    engineState.status = 'cancelled';
    renderFromState();
  }

  async function onPrimaryStart() {
    var form = readForm();
    var d = deriveReviewStartState(form);
    var extra = blockingStandardErrors(form);
    if (d.action === 'validate' || extra.length) {
      alert((d.errors || []).concat(extra).join('\n') || '请检查配置');
      return;
    }
    if (d.action === 'create_start') {
      await createApplication(true);
      return;
    }
    if (d.action === 'rerun' || d.action === 'retry') {
      await retryApplication();
      return;
    }
    if (d.action === 'start') await submitApplication();
  }

  function stopLiveJourney() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    if (engineState.connection === 'live' || engineState.connection === 'polling') {
      engineState.connection = 'idle';
    }
  }

  function beginLiveJourney() {
    stopLiveJourney();
    engineState.connection = 'polling';
    pollTimer = setInterval(poll, 500);
    poll();
  }

  var TERMINAL = ['approved', 'approved_with_conditions', 'restricted', 'rejected', 'registered',
                  'revoked', 'completed', 'failed', 'cancelled', 'need_info'];

  function refreshJudgment(app) {
    if (!EJ || !app) return;
    if ((app.verdicts && app.verdicts.length) || app.status !== 'draft') {
      judgmentState.dimensions = EJ.dimensionsFromVerdicts(app, judgmentState.as_of);
      judgmentState.overall = EJ.overallFromDimensions(judgmentState.dimensions, judgmentState.as_of);
      renderJudgmentPanel();
    }
  }

  async function poll() {
    if (!engineState.runId) return;
    var base = '/api/v1/model-clearance/applications/' + encodeURIComponent(engineState.runId);
    try {
      var app = await api().request(base);
      var evData = await api().request(base + '/events');
      if (app) {
        applyApp(app);
        refreshJudgment(app);
        renderReportIndex(app);
      }
      if (evData && evData.events) ingestEvents(evData.events);
      renderPortfolio();
      if (app && TERMINAL.indexOf(app.status) >= 0) {
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

  function renderPortfolio() {
    var el = $('portfolio');
    if (!el) return;
    api()
      .request('/api/v1/model-clearance/registry')
      .then(function (res) {
        var list = (res && res.registry) || [];
        if (!list.length) {
          el.innerHTML = '<div class="empty">空状态：尚无准入条目</div>';
          return;
        }
        el.innerHTML =
          '<div style="font-size:12px">' +
          list
            .map(function (item) {
              var badgeCls = item.status === 'active' ? 'status-ok' : 'status-bad';
              return (
                '<div class="stat" style="border-bottom:1px solid #e2e8f0;padding:8px 0">' +
                '<div style="display:flex;justify-content:space-between;align-items:center">' +
                '<strong>' + esc(item.model_id) + '</strong>' +
                '<span class="' + badgeCls + '" style="font-size:11px">' + esc(item.status) + '</span></div>' +
                '<div style="margin-top:3px;font-size:11px;color:#64748b">' +
                'Profile: <b>' + esc(item.runtime_profile || 'standard') + '</b>' +
                '<br>§11 负责人: ' + esc(item.service_owner || '未登记') +
                '<br>Digest: <code>' + esc((item.locked_digest || '').slice(0, 16)) + '…</code></div>' +
                (item.conditions && item.conditions.length
                  ? '<div style="margin-top:2px;font-size:11px;color:#b45309">§9 条件: ' + esc(item.conditions.join('; ')) + '</div>'
                  : '') +
                '<div style="margin-top:6px;display:flex;gap:6px">' +
                '<button type="button" class="btn js-kill" data-entry="' + esc(item.entry_id) + '" style="padding:2px 6px;font-size:10px">暂停/吊销</button>' +
                '<button type="button" class="btn js-rollback" data-entry="' + esc(item.entry_id) + '" style="padding:2px 6px;font-size:10px">回滚</button>' +
                '</div></div>'
              );
            })
            .join('') +
          '</div>';
      })
      .catch(function () {
        el.innerHTML = '<div class="empty">空状态：尚无准入条目</div>';
      });
  }

  async function restore() {
    try {
      var id = localStorage.getItem('sa_clearance_app_id');
      if (!id) return;
      var base = '/api/v1/model-clearance/applications/' + encodeURIComponent(id);
      var app = await api().request(base);
      var evData = await api().request(base + '/events');
      applyApp(app);
      if (Array.isArray(app.contributions) && app.contributions.length) {
        contributions = app.contributions.map(function (c) {
          return { gate: c.gate, kind: c.kind, ref_id: c.ref_id, label: c.label || c.ref_id };
        });
        renderContributionChips();
        updateStandardCount();
      }
      engineState.lastSeq = 0;
      engineState.events = [];
      if (evData && evData.events) ingestEvents(evData.events);
      refreshJudgment(app);
      renderReportIndex(app);
      renderPortfolio();
      renderFromState();
      if (app && (app.status === 'running' || app.status === 'gating' || app.status === 'submitted')) {
        beginLiveJourney();
      }
    } catch (e) { /* ignore */ }
  }

  // ── Wire UI ───────────────────────────────────────────────
  if ($('as_of') && !$('as_of').value) $('as_of').value = today();

  function downloadBlob(blob, filename) {
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  if ($('btn-advise-blockers')) {
    $('btn-advise-blockers').addEventListener('click', function () {
      if (!reportRecord) return;
      var btn = this;
      var label = btn.textContent;
      btn.disabled = true;
      btn.textContent = '分析中…';
      api()
        .send('/api/v1/model-clearance/applications/' +
          encodeURIComponent(reportRecord.application.application_id) + '/blocker-advisories', 'POST')
        .then(function (res) {
          if (!res) throw new Error((api()._lastError || {}).message || '生成失败');
          reportKey = '';  // 强制下一轮重取报告
          return renderReportIndex({
            application_id: reportRecord.application.application_id,
            updated_at: new Date().toISOString(),
            status: reportRecord.application.status,
            verdicts: reportRecord.methodology_and_results
          });
        })
        .catch(function (e) { alert(e.message || e); })
        .then(function () { btn.disabled = false; btn.textContent = label; });
    });
  }

  if ($('btn-open-report')) {
    $('btn-open-report').addEventListener('click', function () {
      if (!reportRecord || !window.AssuranceReportDoc) return;
      var html = window.AssuranceReportDoc.build(reportRecord);
      // 必须在点击事件里同步 open，异步或 blob URL 会被弹窗拦截。
      var w = window.open('', '_blank');
      if (!w) {
        downloadBlob(
          new Blob([html], { type: 'text/html;charset=utf-8' }),
          'assurance-record-' + (reportRecord.application.application_id || 'draft') + '.html'
        );
        return;
      }
      w.document.open();
      w.document.write(html);
      w.document.close();
    });
  }

  if ($('btn-export-report')) {
    $('btn-export-report').addEventListener('click', function () {
      if (!reportRecord) return;
      downloadBlob(
        new Blob([JSON.stringify(reportRecord, null, 2)], { type: 'application/json' }),
        'assurance-record-' + (reportRecord.application.application_id || 'draft') + '.json'
      );
    });
  }

  if ($('intake-notice')) {
    $('intake-notice').addEventListener('click', function (ev) {
      var edit = ev.target.closest('[data-intake-edit]');
      if (edit) {
        var fields = $('extended-application-fields');
        if (fields) {
          fields.hidden = !fields.hidden;
          edit.setAttribute('aria-expanded', fields.hidden ? 'false' : 'true');
          edit.textContent = fields.hidden ? '查看可选部署信息' : '收起可选部署信息';
        }
        return;
      }
      if (!ev.target.closest('[data-intake-start]')) return;
      onPrimaryStart()
        .then(function () {
          // 启动后把视图带到时间线，否则评审在屏幕外跑完，用户看不到过程。
          var t = $('clearance-timeline');
          if (t) t.scrollIntoView({ block: 'start' });
        })
        .catch(function (e) { alert(e.message || e); });
    });
  }

  if ($('btn-engine-start')) {
    $('btn-engine-start').addEventListener('click', function () {
      onPrimaryStart().catch(function (e) { alert(e.message || e); });
    });
  }
  if ($('btn-pipeline-start')) {
    $('btn-pipeline-start').addEventListener('click', function () {
      onPrimaryStart().catch(function (e) { alert(e.message || e); });
    });
  }
  if ($('btn-create')) {
    $('btn-create').addEventListener('click', function () {
      createApplication(false).catch(function (e) { alert(e.message || e); });
    });
  }
  if ($('btn-start')) {
    $('btn-start').addEventListener('click', function () {
      submitApplication().catch(function (e) { alert(e.message || e); });
    });
  }
  if ($('btn-cancel')) {
    $('btn-cancel').addEventListener('click', function () {
      cancelApplication().catch(function (e) { alert(e.message || e); });
    });
  }
  document.querySelectorAll('[data-model]').forEach(function (button) {
    button.addEventListener('click', function () {
      if ($('model_id')) $('model_id').value = button.dataset.model;
      syncPrimaryButton();
    });
  });

  // 表单任一字段变化都要重算主 CTA 与 §10 提示。
  var configRoot = $('clearance-application');
  if (configRoot) {
    ['input', 'change'].forEach(function (evt) {
      configRoot.addEventListener(evt, function (ev) {
        if (ev.target && ev.target.id === 'permitted_use') updatePermittedUseNote();
        syncPrimaryButton();
        renderFromState();
      });
    });
  }

  if (window.EngineSidebar && typeof window.EngineSidebar.init === 'function') {
    window.EngineSidebar.init({ badges: {} });
  }

  document.addEventListener('click', function (ev) {
    var t = ev.target;
    if (!t || !t.closest) return;
    var tab = t.closest('.judgment-tab');
    if (tab && tab.getAttribute('data-group')) {
      judgmentState.group = tab.getAttribute('data-group');
      renderJudgmentPanel();
      return;
    }
    var kill = t.closest('.js-kill');
    if (kill) return triggerKillSwitch(kill.getAttribute('data-entry'));
    var rb = t.closest('.js-rollback');
    if (rb) return triggerRollback(rb.getAttribute('data-entry'));
    var run = t.closest('.js-run-team');
    if (run) runInformationTeam(run);
  });

  function runInformationTeam(btn) {
    var teamId = btn.getAttribute('data-team');
    if (!teamId || btn.disabled) return;
    btn.disabled = true;
    var original = btn.textContent;
    btn.textContent = '采集中…';
    api()
      .request('/api/v1/information-sources/teams/' + encodeURIComponent(teamId) + '/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ team_id: teamId }),
      })
      .then(function () {
        // 采集是后台任务，完成后才会出现新文档；这里只刷新一次列表
        btn.textContent = '已排队，稍后刷新';
        return loadContributors();
      })
      .catch(function (err) {
        btn.textContent = original;
        btn.disabled = false;
        alert('触发采集失败: ' + (err.message || err));
      });
  }

  function triggerKillSwitch(entryId) {
    if (!entryId) return;
    if (!confirm('§11 revoke：确定暂停/吊销准入条目 [' + entryId + '] 吗？')) return;
    api()
      .request('/api/v1/model-clearance/registry/' + encodeURIComponent(entryId) + '/kill-switch', {
        method: 'POST',
        body: JSON.stringify({ operator: 'lenovo-secops-admin', reason: 'Console manual revoke' }),
      })
      .then(function () {
        alert('已暂停/吊销该条目。');
        renderPortfolio();
      })
      .catch(function (err) { alert('操作失败: ' + (err.message || err)); });
  }

  function triggerRollback(entryId) {
    if (!entryId) return;
    var targetDigest = prompt('请输入要回滚的目标锁定权重 SHA-256 Digest:');
    if (!targetDigest || !targetDigest.trim()) return;
    api()
      .request('/api/v1/model-clearance/registry/' + encodeURIComponent(entryId) + '/rollback', {
        method: 'POST',
        body: JSON.stringify({ target_digest: targetDigest.trim(), operator: 'lenovo-infra-ops', reason: 'Console manual rollback' }),
      })
      .then(function () {
        alert('已完成基线回滚。');
        renderPortfolio();
      })
      .catch(function (err) { alert('回滚失败: ' + (err.message || err)); });
  }

  window.addEventListener('resize', refreshLaneOverflow);

  incoming = readIncoming();
  applyIncoming();

  loadStandard().then(function () {
    syncPrimaryButton();
    renderFromState();
  });
  loadContributors();
  loadRuntimeHealth();
  renderPortfolio();
  renderFromState();
  renderJudgmentPanel();
  // 带着待评审模型进来时不恢复上一份申请，否则页面显示的是另一个模型的评审过程。
  if (incoming) {
    syncPrimaryButton();
    var card = $('clearance-application');
    if (card) card.scrollIntoView({ block: 'center' });
  } else {
    restore();
  }
})();
