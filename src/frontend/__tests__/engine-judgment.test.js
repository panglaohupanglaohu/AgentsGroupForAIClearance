import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import vm from 'node:vm';

function loadJudgment() {
  const code = readFileSync(
    path.join(process.cwd(), 'src/frontend/js/engine-judgment.js'),
    'utf8',
  );
  const sandbox = { console, window: {}, globalThis: {} };
  sandbox.globalThis = sandbox;
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox);
  return sandbox.window.EngineJudgment || sandbox.EngineJudgment;
}

describe('Clearance multi-dim gate matrix (P12)', () => {
  it('exposes 11 gate dimensions and gate group tabs', () => {
    const J = loadJudgment();
    expect(J.DIMENSION_KEYS).toHaveLength(11);
    expect(J.DIMENSION_KEYS).toContain('license_compliance');
    expect(J.DIMENSION_KEYS).toContain('operational_control');
    expect(Object.keys(J.GROUPS).length).toBeGreaterThanOrEqual(4);
    expect(J.GATE_OF.artifact_integrity).toBe('G1');
    expect(J.GATE_OF.operational_control).toBe('G6');
  });

  it('builds fixture matrix without inventing certainty on missing dims', () => {
    const J = loadJudgment();
    const dims = J.buildFixtureDimensions({
      model_id: 'Qwen/Qwen2.5-7B-Instruct',
      as_of: '2026-07-01',
    });
    expect(dims.length).toBe(11);
    const overall = J.overallFromDimensions(dims, '2026-07-01');
    expect(overall.coverage).toBeGreaterThan(0);
    expect(overall.label).toMatch(/模拟/);
  });

  it('maps scores to clearance verdicts instead of market direction', () => {
    const J = loadJudgment();
    expect(J.directionFromScore(0.9)).toBe('pass');
    expect(J.directionFromScore(0.6)).toBe('needs_info');
    expect(J.directionFromScore(0.3)).toBe('fail');
    expect(J.dirLabel('fail')).toContain('阻断');
  });

  it('blocks overall verdict when a blocker gate fails, ignoring the average', () => {
    const J = loadJudgment();
    let dims = J.buildFixtureDimensions({
      model_id: 'mistralai/Mistral-Large-Instruct-2407',
      as_of: '2026-07-01',
    });
    dims = J.mergeEventDimension(dims, {
      key: 'license_compliance',
      score: 0.1,
      direction: 'fail',
      state: 'conflict',
      rationale: 'restricted license',
      confidence: 0.9,
    });
    const overall = J.overallFromDimensions(dims, '2026-07-01');
    expect(overall.blocked).toBe(true);
    expect(overall.label).toContain('阻断');
    expect(overall.risks.join(' ')).toContain('许可证合规');
  });

  it('merges event dimension payloads', () => {
    const J = loadJudgment();
    let dims = J.buildFixtureDimensions({
      model_id: 'deepseek-ai/DeepSeek-R1',
      as_of: '2026-07-01',
    });
    dims = J.mergeEventDimension(dims, {
      key: 'resource_fit',
      score: 0.9,
      direction: 'pass',
      state: 'ok',
      rationale: 'event update',
      evidence_count: 3,
      confidence: 0.8,
      as_of: '2026-07-01',
      label: '资源与算力适配',
    });
    const m = dims.find((d) => d.key === 'resource_fit');
    expect(m.score).toBe(0.9);
    expect(m.rationale).toBe('event update');
  });

  it('html wires judgment panel and engine-judgment.js', () => {
    const html = readFileSync(
      path.join(process.cwd(), 'src/frontend/ai-model-entry-clearance.html'),
      'utf8',
    );
    expect(html).toContain('engine-judgment.js');
    expect(html).toContain('id="judgment-dimensions-panel"');
    expect(html).toContain('id="judgment-matrix-body"');
    expect(html).toContain('仅供内部治理参考');
    expect(html).toContain('id="judgment-card"');
    expect(html).toContain('clearance_verdict');
    expect(html).toContain('id="judgment-pass-signals"');
  });
});
