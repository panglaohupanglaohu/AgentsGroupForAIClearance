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

describe('Engine multi-dim judgment (P12)', () => {
  it('exposes 11 dimensions and group tabs', () => {
    const J = loadJudgment();
    expect(J.DIMENSION_KEYS).toHaveLength(11);
    expect(J.DIMENSION_KEYS).toContain('valuation');
    expect(J.DIMENSION_KEYS).toContain('event_impact');
    expect(Object.keys(J.GROUPS).length).toBeGreaterThanOrEqual(4);
  });

  it('builds fixture matrix without inventing certainty on missing dims', () => {
    const J = loadJudgment();
    const dims = J.buildFixtureDimensions({ ticker: 'NVDA', as_of: '2026-07-01' });
    expect(dims.length).toBe(11);
    const overall = J.overallFromDimensions(dims, '2026-07-01');
    expect(overall.coverage).toBeGreaterThan(0);
    expect(overall.label).toMatch(/模拟/);
  });

  it('merges event dimension payloads', () => {
    const J = loadJudgment();
    let dims = J.buildFixtureDimensions({ ticker: 'AMD', as_of: '2026-07-01' });
    dims = J.mergeEventDimension(dims, {
      key: 'momentum',
      score: 0.9,
      direction: 'up',
      state: 'ok',
      rationale: 'event update',
      evidence_count: 3,
      confidence: 0.8,
      as_of: '2026-07-01',
      label: '动量',
    });
    const m = dims.find((d) => d.key === 'momentum');
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
    expect(html).toContain('研究/模拟，非投资建议');
    expect(html).toContain('id="judgment-card"');
  });
});
