import { readFileSync } from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { describe, expect, it } from 'vitest';

function loadDoc() {
  const code = readFileSync(
    path.join(process.cwd(), 'src/frontend/js/assurance-report-doc.js'),
    'utf8',
  );
  const sandbox = { console, window: {}, globalThis: {} };
  sandbox.globalThis = sandbox;
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox);
  return sandbox.window.AssuranceReportDoc;
}

function record(overrides = {}) {
  return {
    standard: { name: 'Open-Weight Model Assurance Standard', version: '0.1' },
    generated_at: '2026-08-31T09:00:00+00:00',
    assessed: true,
    application: {
      application_id: 'app-1',
      applicant: 'tester',
      status: 'rejected',
      decided: true,
      need_info_count: 0,
      created_at: '',
      updated_at: '',
    },
    artifact_assessed: {
      model_id: 'acme/open-7b',
      revision: 'v1.2',
      root_digest: 'a'.repeat(64),
      weights_uri: '',
      expected_signer_identity: null,
      custody_chain: [],
    },
    evidence_reviewed: {
      decisive: [{
        evidence_id: 'ev1', gate: 'G1', section: '6.1', check_id: 'G1-PROV-02',
        collector: 'manifest-scanner', collector_version: '1.0.0',
        collected_at: '2026-08-31T09:00:00+00:00', digest: 'b'.repeat(64), status: 'ok',
      }],
      advisory: [],
      decisive_count: 1,
      advisory_count: 0,
      note: '参考情报仅作风险信号。',
    },
    methodology_and_results: ['G0', 'G1', 'G2', 'G3', 'G4', 'G5', 'G6', 'G7', 'G8'].map((gate, i) => ({
      gate,
      section: String(i),
      name: '门禁' + gate,
      name_en: 'Gate ' + gate,
      owner_role: '审核人',
      hard_block: gate === 'G0',
      summary: '',
      standard_criteria: ['要点一'],
      collectors: ['scanner@1.0.0'],
      checks: [{ check_id: gate + '-01', requirement: '要求', blocker: true, result: 'pass' }],
      checks_total: 1,
      checks_failed: 0,
      verdict: 'pass',
      severity: 'none',
      decided_by: 'policy',
      decided_at: '2026-08-31T09:00:00+00:00',
      evidence_refs: ['ev1'],
    })),
    findings_and_mitigations: [],
    residual_risks: [],
    conditions_and_restrictions: {
      conditions: [], runtime_profile: 'standard', scope: ['internal'], expires_at: '', exceptions: [],
    },
    permitted_use: {
      value: 'internal_row', section: '10.1', label_zh: '内部 ROW 使用', note: '',
      requires_additional_assessment: false, additional_assessment_complete: false,
      additional_criteria: [], satisfied: true,
    },
    governance: {
      roles: [], evaluate: [{ gate: 'G0', section: '3', owner_role: '架构师' }],
      own: '未登记', applicant: 'tester',
    },
    decision: {
      verdict: 'approved', reason: '所有门禁与复核均已满足', conditions: [],
      runtime_profile: 'standard', scope: ['internal'], permitted_use: 'internal_row',
      residual_risks: [], hard_block: false, expires_at: '', decided_at: '2026-08-31T09:00:00+00:00',
    },
    deployment_context: {},
    ...overrides,
  };
}

describe('assurance report document', () => {
  const D = loadDoc();

  it('produces a self-contained document with no external requests', () => {
    const html = D.build(record());
    expect(html.startsWith('<!doctype html>')).toBe(true);
    // 交付物必须能离线打开：任何外链都会让归档环境里的文档降级。
    expect(html).not.toMatch(/<link\b/i);
    expect(html).not.toMatch(/<script\b/i);
    expect(html).not.toMatch(/https?:\/\//);
  });

  it('carries every §9 section plus permitted use and governance', () => {
    const html = D.build(record());
    for (const heading of [
      '受评的模型制品与版本',
      '已复核的证据',
      '测试方法与结果',
      '对比测试与外部情报',
      '重大发现与缓解措施',
      '残余风险',
      '条件、限制与例外',
      '最终保障裁决',
      '许可用途',
      '角色与治理',
    ]) {
      expect(html).toContain(heading);
    }
  });

  it('renders one strip cell per gate', () => {
    const html = D.build(record());
    expect((html.match(/class="strip-cell/g) || []).length).toBe(9);
  });

  it('escapes untrusted text so external labels cannot inject markup', () => {
    const rec = record();
    rec.evidence_reviewed.advisory = [{
      evidence_id: 'adv', gate: 'G7', section: '7.3', check_id: 'G7-ADVISORY',
      collector: 'x', collector_version: '1', collected_at: '', digest: '', status: 'ok',
      label: '<img src=x onerror=alert(1)>', kind: 'run', analysis: {},
    }];
    rec.evidence_reviewed.advisory_count = 1;
    const html = D.build(rec);
    expect(html).not.toContain('<img src=x');
    expect(html).toContain('&lt;img src=x onerror=alert(1)&gt;');
  });

  it('never implies a decision when the review has not run', () => {
    const rec = record({ decision: null });
    const html = D.build(rec);
    expect(html).toContain('尚未产生保障裁决');
    expect(html).not.toContain('Approved · 批准');
  });

  it('renders blocker analysis and recommendation with an advisory disclaimer', () => {
    const rec = record();
    rec.methodology_and_results[0].checks[0].advisory = {
      gate: 'G0', check_id: 'G0-01', result: 'pass',
      analysis: '当前部署形态未命中任何禁止项',
      recommendation: '维持 ROW 自托管，变更托管方前重跑 G0',
      risk_if_ignored: '误改托管地会直接触发硬红线',
      generated_by: 'deepseek/deepseek-v4-pro',
      generated_at: '2026-08-31T10:00:00+00:00',
      advisor_version: '1.0.0', error: '', advisory: true,
    };
    const html = D.build(rec);
    expect(html).toContain('当前部署形态未命中任何禁止项');
    expect(html).toContain('维持 ROW 自托管，变更托管方前重跑 G0');
    // 参考性必须写在文档里，读报告的人不能把它当判定依据
    expect(html).toContain('不参与门禁规则求值');
    expect(html).toContain('deepseek/deepseek-v4-pro');
  });

  it('surfaces advisory generation failure instead of hiding it', () => {
    const rec = record();
    rec.methodology_and_results[0].checks[0].advisory = {
      gate: 'G0', check_id: 'G0-01', result: 'pass',
      analysis: '', recommendation: '', risk_if_ignored: '',
      generated_by: 'unavailable', generated_at: '', advisor_version: '1.0.0',
      error: 'upstream 502', advisory: true,
    };
    const html = D.build(rec);
    expect(html).toContain('分析未生成：upstream 502');
  });
});
