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
    if (!form.ticker || !/^[A-Za-z0-9.]{1,12}$/.test(form.ticker)) {
      errors.push('请填写合法 Ticker（字母/数字，最长 12）');
    }
    if (!form.trade_date) {
      errors.push('请选择交易日期 / as_of 截止');
    }
    if (!(Number(form.initial_cash) >= 1000)) {
      errors.push('初始资金至少 1000');
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
      return { label: '创建并启动 Engine', action: 'create_start', disabled: false, errors: [] };
    }
    var st = run.status || 'idle';
    if (st === 'queued') {
      return { label: '继续启动', action: 'start', disabled: false, errors: [] };
    }
    if (st === 'running') {
      return { label: 'Engine 行驶中', action: 'none', disabled: true, errors: [] };
    }
    if (st === 'completed') {
      return { label: '重新运行', action: 'rerun', disabled: false, errors: [] };
    }
    if (st === 'failed' || st === 'cancelled') {
      return { label: '重试 Engine', action: 'retry', disabled: false, errors: [] };
    }
    return { label: '创建并启动 Engine', action: 'create_start', disabled: false, errors: [] };
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
