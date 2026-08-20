/**
 * Engine Live Cockpit — single source of truth (T802).
 * Browser global: window.EngineState
 */
(function (global) {
  'use strict';

  function createEngineState() {
    return {
      runId: null,
      status: 'idle', // idle|queued|running|completed|failed|cancelled
      phase: 'assembly',
      progress: 0,
      currentNode: null,
      assembly: { modules: [], snapshotHash: null, warnings: [] },
      events: [],
      insights: {
        context: null,
        judgment: null,
        plan: null,
        valuePath: null,
        risk: null,
        portfolio: null,
      },
      lastSeq: 0,
      connection: 'idle', // idle|polling|live|reconnecting|error
      error: null,
      graphShape: [],
      formErrors: [],
    };
  }

  function validateEngineForm(form) {
    var errors = [];
    form = form || {};
    var modelId = (form.model_id || form.ticker || '').trim();
    if (!modelId || !/^[A-Za-z0-9._\/-]{1,128}$/.test(modelId)) {
      errors.push('请填写合法 model_id（如 meta-llama/Llama-3.1-8B-Instruct）');
    }
    var rev = (form.revision !== undefined ? form.revision : 'v1.0').trim();
    if (!rev || rev === 'main' || rev === 'latest') {
      errors.push('必须锁定不可变 revision，禁止 main/latest');
    }
    var asOf = (form.as_of || form.trade_date || '').trim();
    if (!asOf) {
      errors.push('请选择证据截止日期 as_of');
    }
    var qpm = form.target_qpm != null ? form.target_qpm : form.initial_cash;
    if (qpm !== undefined && qpm !== '' && !(Number(qpm) >= 1)) {
      errors.push('预估并发量至少为 1');
    }
    return errors;
  }

  /**
   * Derive primary CTA from form + run status (T801).
   */
  function deriveStartState(form, run) {
    var errors = validateEngineForm(form || {});
    if (errors.length) {
      return { label: '检查配置', action: 'validate', disabled: false, errors: errors };
    }
    if (!run || !run.run_id) {
      return { label: '创建并启动准入评审', action: 'create_start', disabled: false, errors: [] };
    }
    var st = run.status || 'idle';
    if (st === 'queued' || st === 'draft' || st === 'submitted') {
      return { label: '提交准入评审', action: 'start', disabled: false, errors: [] };
    }
    if (st === 'running' || st === 'gating' || st === 'adjudicating') {
      return { label: '门禁评审执行中', action: 'none', disabled: true, errors: [] };
    }
    if (st === 'completed' || st === 'approved' || st === 'approved_with_conditions' || st === 'registered') {
      return { label: '重新评估', action: 'rerun', disabled: false, errors: [] };
    }
    if (st === 'failed' || st === 'rejected' || st === 'cancelled' || st === 'revoked') {
      return { label: '重新提交申请', action: 'retry', disabled: false, errors: [] };
    }
    return { label: '创建并启动准入评审', action: 'create_start', disabled: false, errors: [] };
  }

  function modulesFromDraft(sources) {
    return (sources || []).map(function (s, i) {
      return {
        module_id: s.sourceId || s.module_id || s.id,
        kind: s.kind || 'source',
        name: s.name || s.sourceId || '',
        enabled: s.enabled !== false,
        priority: s.priority || i + 1,
        config: s.config || {},
      };
    });
  }

  global.EngineState = {
    create: createEngineState,
    validateEngineForm: validateEngineForm,
    deriveStartState: deriveStartState,
    modulesFromDraft: modulesFromDraft,
  };
})(typeof window !== 'undefined' ? window : globalThis);
