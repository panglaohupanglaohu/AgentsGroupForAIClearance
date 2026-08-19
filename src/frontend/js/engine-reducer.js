/**
 * Event → cockpit insights reducer (T832) + safe text helpers (T833).
 */
(function (global) {
  'use strict';

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function safeText(s) {
    // Never treat as HTML — strip tags if any slipped through
    return String(s == null ? '' : s).replace(/<[^>]*>/g, '');
  }

  function phaseFor(event) {
    var p = (event && event.phase) || 'context';
    if (p === 'decision') return 'portfolio';
    if (p === 'debate') return 'plan';
    return p;
  }

  function routeKey(phase) {
    var map = {
      assembly: 'context',
      context: 'context',
      analysis: 'judgment',
      judgment: 'judgment',
      debate: 'plan',
      planning: 'plan',
      plan: 'plan',
      trading: 'risk',
      risk: 'risk',
      portfolio: 'portfolio',
      reflection: 'portfolio',
      budget: 'risk',
    };
    return map[phase] || 'context';
  }

  function progressFrom(events, graphShape) {
    var completed = (events || []).filter(function (e) {
      return e.status === 'completed';
    }).length;
    var total = Math.max(1, ((graphShape && graphShape.length) || 12) * 2 + 4);
    return Math.min(100, Math.round((completed / total) * 100));
  }

  function normalizeClaim(event) {
    var s = (event && event.structured) || {};
    return {
      claim: safeText(s.claim || event.content || ''),
      direction: s.direction || 'neutral',
      confidence: typeof s.confidence === 'number' ? s.confidence : null,
      drivers: s.drivers || [],
      counterpoints: s.counterpoints || [],
      evidence_ids: s.evidence_ids || event.evidence || [],
      label: s.label || 'analysis',
      ts: event.ts,
      node: event.node,
    };
  }

  function normalizePlan(event) {
    var s = (event && event.structured) || {};
    if (s.base_case || s.bull_case || s.bear_case) {
      return {
        objective: safeText(s.objective || event.content || ''),
        base_case: s.base_case || {},
        bull_case: s.bull_case || {},
        bear_case: s.bear_case || {},
        invalidations: s.invalidations || [],
        label: s.label || 'simulation',
        ts: event.ts,
      };
    }
    return {
      objective: safeText(event.content || ''),
      base_case: {},
      bull_case: {},
      bear_case: {},
      invalidations: [],
      label: 'simulation',
      ts: event.ts,
    };
  }

  function normalizeValuePath(event) {
    var s = (event && event.structured) || {};
    return {
      action: s.action || '',
      allocation: s.allocation,
      value_path: s.value_path || [],
      notes: s.notes || [],
      label: 'simulation',
      summary: safeText(event.content || ''),
      ts: event.ts,
    };
  }

  function normalizeRisk(event) {
    var s = (event && event.structured) || {};
    return {
      gate: s.gate || 'approved',
      reason: safeText(s.reason || event.content || ''),
      size_multiplier: s.size_multiplier,
      evidence_ids: s.evidence_ids || event.evidence || [],
      label: s.label || 'analysis',
      ts: event.ts,
    };
  }

  function normalizePortfolio(event) {
    var s = (event && event.structured) || {};
    return {
      decision: s.decision || {},
      order_lifecycle: s.order_lifecycle || [],
      portfolio: s.portfolio || null,
      summary: safeText(event.content || ''),
      disclaimer: s.disclaimer || '仅供内部治理参考，不构成法律或采购建议。',
      label: 'simulation',
      ts: event.ts,
    };
  }

  function reduceJourney(state, event) {
    if (!event || typeof event.seq !== 'number') return state;
    // Dedup by seq
    if (state.events.some(function (e) { return e.seq === event.seq; })) {
      return state;
    }
    var next = {
      runId: state.runId,
      status: state.status,
      phase: state.phase,
      progress: state.progress,
      currentNode: state.currentNode,
      assembly: state.assembly,
      events: state.events.slice(),
      insights: {
        context: state.insights.context,
        judgment: state.insights.judgment,
        plan: state.insights.plan,
        valuePath: state.insights.valuePath,
        risk: state.insights.risk,
        portfolio: state.insights.portfolio,
      },
      lastSeq: state.lastSeq,
      connection: state.connection,
      error: state.error,
      graphShape: state.graphShape,
      formErrors: state.formErrors,
    };
    next.events.push(event);
    next.events.sort(function (a, b) { return (a.seq || 0) - (b.seq || 0); });
    next.lastSeq = Math.max(next.lastSeq || 0, event.seq || 0);
    next.phase = phaseFor(event);
    next.currentNode = event.node || next.currentNode;
    next.progress = progressFrom(next.events, next.graphShape);

    var ph = event.phase;
    if (ph === 'context') {
      next.insights.context = {
        summary: safeText(event.content || ''),
        evidence_ids: event.evidence || (event.structured && event.structured.evidence_ids) || [],
        structured: event.structured || {},
        ts: event.ts,
      };
    }
    if (ph === 'analysis') {
      next.insights.judgment = normalizeClaim(event);
    }
    if (ph === 'debate' || ph === 'planning') {
      next.insights.plan = normalizePlan(event);
    }
    if (ph === 'trading') {
      next.insights.valuePath = normalizeValuePath(event);
    }
    if (ph === 'risk' || ph === 'budget') {
      next.insights.risk = normalizeRisk(event);
    }
    if (ph === 'portfolio' || ph === 'decision' || ph === 'reflection') {
      next.insights.portfolio = normalizePortfolio(event);
    }
    if (event.status === 'failed') {
      next.error = safeText(event.content || '节点失败');
    }
    return next;
  }

  function reduceMany(state, events) {
    var s = state;
    (events || []).forEach(function (ev) {
      s = reduceJourney(s, ev);
    });
    return s;
  }

  global.EngineReducer = {
    esc: esc,
    safeText: safeText,
    phaseFor: phaseFor,
    routeKey: routeKey,
    progressFrom: progressFrom,
    reduceJourney: reduceJourney,
    reduceMany: reduceMany,
    normalizeClaim: normalizeClaim,
    normalizePlan: normalizePlan,
    normalizeValuePath: normalizeValuePath,
    normalizeRisk: normalizeRisk,
    normalizePortfolio: normalizePortfolio,
  };
})(typeof window !== 'undefined' ? window : globalThis);
