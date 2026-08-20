import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import vm from 'node:vm';

function loadScript(rel) {
  const code = readFileSync(path.join(process.cwd(), rel), 'utf8');
  const sandbox = { window: {}, console, globalThis: {} };
  sandbox.globalThis = sandbox;
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox);
  return sandbox;
}

describe('Clearance Cockpit Wiring & De-financialization (P10 / TA01–TA09)', () => {
  it('ai-model-entry-clearance.html contains proper clearance form inputs and zero legacy IDs', () => {
    const html = readFileSync(
      path.join(process.cwd(), 'src/frontend/ai-model-entry-clearance.html'),
      'utf8',
    );
    expect(html).toContain('id="model_id"');
    expect(html).toContain('id="revision"');
    expect(html).toContain('id="weights_uri"');
    expect(html).toContain('id="as_of"');
    expect(html).toContain('id="target_qpm"');
    expect(html).toContain('id="review_rounds"');
    expect(html).toContain('id="redteam_rounds"');
    expect(html).toContain('id="use_case"');

    // No legacy ticker/trade_date/cash/initial_cash in HTML element IDs
    expect(html).not.toMatch(/id="ticker"/);
    expect(html).not.toMatch(/id="trade_date"/);
    expect(html).not.toMatch(/id="cash"/);
  });

  it('ai-model-entry-clearance.js contains zero investment-simulations calls and targets model-clearance APIs', () => {
    const js = readFileSync(
      path.join(process.cwd(), 'src/frontend/js/ai-model-entry-clearance.js'),
      'utf8',
    );
    expect(js).not.toContain('investment-simulations');
    expect(js).toContain('/api/v1/model-clearance/applications');
    expect(js).toContain('/api/v1/model-clearance/registry');
    expect(js).toContain('/submit');
  });

  it('engine-state.js validates real model IDs and rejects invalid/mutable revisions', () => {
    const s = loadScript('src/frontend/js/engine-state.js');
    const ES = s.window.EngineState || s.EngineState;

    // Default valid form
    const validForm = {
      model_id: 'meta-llama/Llama-3.1-8B-Instruct',
      revision: 'v1.0',
      as_of: '2026-08-20',
      target_qpm: 1000,
    };
    expect(ES.validateEngineForm(validForm)).toEqual([]);

    // Rejects mutable main/latest
    const mutableForm = {
      model_id: 'meta-llama/Llama-3.1-8B-Instruct',
      revision: 'main',
      as_of: '2026-08-20',
    };
    const errors = ES.validateEngineForm(mutableForm);
    expect(errors.some((e) => e.includes('main/latest'))).toBe(true);

    // Rejects empty model_id
    expect(ES.validateEngineForm({ model_id: '', as_of: '2026-08-20' }).length).toBeGreaterThan(0);
  });

  it('engine-judgment.js exposes dimensionsFromVerdicts and maps gate verdicts accurately', () => {
    const s = loadScript('src/frontend/js/engine-judgment.js');
    const EJ = s.window.EngineJudgment || s.EngineJudgment;

    expect(typeof EJ.dimensionsFromVerdicts).toBe('function');

    const sampleApp = {
      application_id: 'app-test123',
      status: 'approved_with_conditions',
      identity: {
        model_id: 'meta-llama/Llama-3.1-8B-Instruct',
        revision: 'v1.0',
      },
      evidence: [
        { evidence_id: 'ev1', gate: 'G1', check_id: 'G1-PROV-03', collector: 'hash-manifest', payload: { _status: 'ok' } },
        { evidence_id: 'ev2', gate: 'G2', check_id: 'G2-BOM-02', collector: 'format-scan', payload: { safe_only: true } },
        { evidence_id: 'ev3', gate: 'G3', check_id: 'G3-LIC-02', collector: 'license-eval', payload: { _status: 'ok' } },
      ],
      verdicts: [
        { gate: 'G1', verdict: 'pass', severity: 'none', failed_checks: [], evidence_refs: ['ev1'], decided_at: '2026-08-20T00:00:00Z' },
        { gate: 'G2', verdict: 'pass', severity: 'none', failed_checks: [], evidence_refs: ['ev2'], decided_at: '2026-08-20T00:00:00Z' },
        { gate: 'G3', verdict: 'pass', severity: 'none', failed_checks: [], evidence_refs: ['ev3'], decided_at: '2026-08-20T00:00:00Z' },
      ],
    };

    const dims = EJ.dimensionsFromVerdicts(sampleApp, '2026-08-20');
    expect(dims.length).toBe(EJ.DIMENSION_KEYS.length);

    const g1Dim = dims.find((d) => d.key === 'artifact_integrity');
    expect(g1Dim.direction).toBe('pass');
    expect(g1Dim.gate).toBe('G1');
    expect(g1Dim.score).toBeGreaterThan(0.75);

    const overall = EJ.overallFromDimensions(dims, '2026-08-20');
    expect(overall.blocked).toBe(false);
  });

  it('dimensionsFromVerdicts flags failed blocker gates as conflict/fail', () => {
    const s = loadScript('src/frontend/js/engine-judgment.js');
    const EJ = s.window.EngineJudgment || s.EngineJudgment;

    const blockedApp = {
      application_id: 'app-blocked123',
      status: 'rejected',
      identity: {
        model_id: 'mistralai/Mistral-Large-Instruct-2407',
        revision: 'v1.0',
      },
      evidence: [],
      verdicts: [
        { gate: 'G1', verdict: 'pass', severity: 'none', failed_checks: [], evidence_refs: [] },
        { gate: 'G2', verdict: 'pass', severity: 'none', failed_checks: [], evidence_refs: [] },
        { gate: 'G3', verdict: 'fail', severity: 'blocker', failed_checks: ['G3-LIC-02'], evidence_refs: [] },
      ],
    };

    const dims = EJ.dimensionsFromVerdicts(blockedApp, '2026-08-20');
    const g3Dim = dims.find((d) => d.key === 'license_compliance');
    expect(g3Dim.direction).toBe('fail');
    expect(g3Dim.rationale).toContain('G3-LIC-02');

    const overall = EJ.overallFromDimensions(dims, '2026-08-20');
    expect(overall.blocked).toBe(true);
    expect(overall.label).toContain('阻断');
  });
});
