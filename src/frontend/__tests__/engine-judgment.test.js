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

describe('Clearance gate matrix (§3/§6/§7/§8)', () => {
  it('exposes one dimension per standard gate G0-G8 and phase-aligned group tabs', () => {
    const J = loadJudgment();
    expect(J.DIMENSION_KEYS).toEqual(['G0', 'G1', 'G2', 'G3', 'G4', 'G5', 'G6', 'G7', 'G8']);
    expect(J.GATE_OF.G1).toBe('G1');
    expect(J.LABELS.G7).toContain('§7.3');
    expect(Object.keys(J.GROUPS)).toEqual([
      'summary',
      'context',
      'analysis',
      'planning',
      'risk',
      'portfolio',
    ]);
    // §3 硬红线与§6.1/§6.2/§7 均为 Blocker
    expect(J.BLOCKER_KEYS.G0).toBe(true);
    expect(J.BLOCKER_KEYS.G7).toBe(true);
    expect(J.BLOCKER_KEYS.G3).toBeUndefined();
  });

  it('starts fail-closed: no evidence means missing rows, never fabricated scores', () => {
    const J = loadJudgment();
    const dims = J.emptyDimensions('2026-07-01');
    expect(dims.length).toBe(9);
    expect(dims.every((d) => d.score === null && d.state === 'missing')).toBe(true);

    const overall = J.overallFromDimensions(dims, '2026-07-01');
    expect(overall.score).toBe(null);
    expect(overall.coverage).toBe(0);
    expect(overall.label).toBe('证据不足');
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
    let dims = J.DIMENSION_KEYS.map((key) => ({
      key,
      gate: key,
      score: 0.95,
      label: J.LABELS[key],
      direction: 'pass',
      confidence: 0.95,
      as_of: '2026-07-01',
      evidence_count: 1,
      source_domains: [],
      rationale: 'ok',
      state: 'ok',
      progress: 'done',
    }));
    dims = J.mergeEventDimension(dims, {
      key: 'G7',
      score: 0.1,
      direction: 'fail',
      state: 'conflict',
      rationale: 'restricted license',
      confidence: 0.9,
    });
    const overall = J.overallFromDimensions(dims, '2026-07-01');
    expect(overall.blocked).toBe(true);
    expect(overall.label).toContain('阻断');
    expect(overall.risks.join(' ')).toContain('用例、数据与法务');
  });

  it('merges event dimension payloads', () => {
    const J = loadJudgment();
    let dims = J.emptyDimensions('2026-07-01');
    dims = J.mergeEventDimension(dims, {
      key: 'G5',
      score: 0.9,
      direction: 'pass',
      state: 'ok',
      rationale: 'event update',
      evidence_count: 3,
      confidence: 0.8,
      as_of: '2026-07-01',
    });
    const m = dims.find((d) => d.key === 'G5');
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
