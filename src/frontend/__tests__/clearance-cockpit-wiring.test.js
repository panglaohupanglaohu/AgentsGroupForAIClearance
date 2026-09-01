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
  it('ai-model-entry-clearance.html carries the standard-mandated application fields', () => {
    const html = readFileSync(
      path.join(process.cwd(), 'src/frontend/ai-model-entry-clearance.html'),
      'utf8',
    );
    // §6.1 制品标识
    expect(html).toContain('id="model_id"');
    expect(html).toContain('id="revision"');
    expect(html).toContain('id="weights_uri"');
    expect(html).toContain('id="expected_signer"');
    expect(html).toContain('id="as_of"');
    // §10 许可用途分级
    expect(html).toContain('id="permitted_use"');
    expect(html).toContain('id="additional_assessment_complete"');
    // §7.1 部署与数据流
    expect(html).toContain('id="hosting_environment"');
    expect(html).toContain('id="data_egress_to_prc"');
    // §7.2 模型权限
    expect(html).toContain('id="tool_access_allowlisted"');
    // §7.3 用例与法务 / §8 归属
    expect(html).toContain('id="intended_use"');
    expect(html).toContain('id="named_owner"');

    // 投研页遗留的装配台与金融字段已清除
    expect(html).not.toMatch(/id="ticker"/);
    expect(html).not.toMatch(/id="trade_date"/);
    expect(html).not.toMatch(/id="target_qpm"/);
    expect(html).not.toMatch(/id="source-drop"/);
    expect(html).not.toMatch(/id="module-library"/);
  });

  it('ai-model-entry-clearance.js contains zero investment-simulations calls and targets model-clearance APIs', () => {
    const js = readFileSync(
      path.join(process.cwd(), 'src/frontend/js/ai-model-entry-clearance.js'),
      'utf8',
    );
    expect(js).not.toContain('investment-simulations');
    expect(js).toContain('/api/v1/model-clearance/applications');
    expect(js).toContain('/api/v1/model-clearance/registry');
    expect(js).toContain('/api/v1/model-clearance/standard');
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
        { evidence_id: 'ev3', gate: 'G7', check_id: 'G7-LIC-02', collector: 'license-eval', payload: { _status: 'ok' } },
      ],
      verdicts: EJ.DIMENSION_KEYS.map((gate) => ({
        gate,
        verdict: 'pass',
        severity: 'none',
        failed_checks: [],
        evidence_refs: [],
        decided_at: '2026-08-20T00:00:00Z',
      })),
    };

    const dims = EJ.dimensionsFromVerdicts(sampleApp, '2026-08-20');
    expect(dims.length).toBe(EJ.DIMENSION_KEYS.length);

    const g1Dim = dims.find((d) => d.key === 'G1');
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
      verdicts: EJ.DIMENSION_KEYS.map((gate) =>
        gate === 'G7'
          ? { gate, verdict: 'fail', severity: 'blocker', failed_checks: ['G7-LIC-02'], evidence_refs: [] }
          : { gate, verdict: 'pass', severity: 'none', failed_checks: [], evidence_refs: [] },
      ),
    };

    const dims = EJ.dimensionsFromVerdicts(blockedApp, '2026-08-20');
    const legalDim = dims.find((d) => d.key === 'G7');
    expect(legalDim.direction).toBe('fail');
    expect(legalDim.state).toBe('conflict');
    expect(legalDim.rationale).toContain('G7-LIC-02');

    const overall = EJ.overallFromDimensions(dims, '2026-08-20');
    expect(overall.blocked).toBe(true);
    expect(overall.label).toContain('阻断');
  });
});
