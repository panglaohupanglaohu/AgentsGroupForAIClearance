import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const html = readFileSync(
  path.join(process.cwd(), 'src/frontend/data-intelligence.html'),
  'utf8',
);
const js = readFileSync(
  path.join(process.cwd(), 'src/frontend/js/data-intelligence.js'),
  'utf8',
);

describe('Data Intelligence conclusion brief (P13)', () => {
  it('exposes one retained dark executive-brief panel on first paint', () => {
    expect(html).toContain('id="executive-brief"');
    expect(html).not.toContain('id="brief-strip"');
    expect(html).toContain('IN FOCUS · EVIDENCE FIRST');
    expect(html).toContain('aria-live="polite"');
    expect(html).toMatch(/研究\/分析|治理参考|内部治理/);
  });

  it('loads latest-summary API and paints the executive panel', () => {
    expect(js).toContain('/api/v1/information-documents/latest-summary');
    expect(js).toContain('loadBriefs');
    expect(js).toContain('applyBrief');
    expect(js).toContain('executive_summary');
    expect(js).toContain('单一来源推断');
    expect(js).toContain('renderExecutiveBrief');
    expect(js).toContain('executive-brief');
    expect(js).toContain('activeBriefChannel');
    // Prefer server contract over client-only rewrite
    expect(js).toContain('doc.executive_summary');
  });

  it('shows which skills and tools own each delivery box', () => {
    expect(js).toContain('box-capabilities');
    expect(js).toContain('agent.skills');
    expect(js).toContain('agent.tools');
    expect(js).toContain('技能：');
    expect(js).toContain('工具：');
  });

  it('exposes dedicated open-weights intelligence tab and license integration', () => {
    expect(html).toContain('data-tab="openweights"');
    expect(html).toContain('id="panel-openweights"');
    expect(html).toContain('id="openweights-grid"');
    expect(js).toContain('/api/v1/model-clearance/licenses');
    expect(js).toContain('loadOpenWeights');
    expect(js).toContain('renderOpenWeights');
    expect(js).toContain('发起准入评审');
  });

  it('puts open weights first and loads it by default', () => {
    const primaryNav = html.match(/<div class="workbench-primary-nav"[\s\S]*?<\/div>/)?.[0] || '';
    expect(primaryNav.indexOf('data-tab="openweights"')).toBeLessThan(primaryNav.indexOf('data-tab="ai60"'));
    expect(primaryNav).toMatch(/class="tab primary active" data-tab="openweights"/);
    expect(js).toContain("get('tab') || 'openweights'");
  });

  it('provides concrete research and investigation execution buttons across panels and cards', () => {
    // Top hero action for open_weights
    expect(html).toContain('id="btn-run-openweights"');
    expect(html).toContain('运行开放权重调研');

    // Panel action and team control for open_weights
    expect(html).toContain('id="btn-start-ow"');
    expect(html).toContain('id="btn-exec-ow-team"');
    expect(html).toContain('id="ow-agent-row"');
    expect(html).toContain('id="ow-box-grid"');
    expect(html).toContain('id="frame-openweights"');

    // Model cards offer per-model investigation action
    expect(js).toContain('btn-investigate-model');
    expect(js).toContain('执行模型调研');
    expect(js).toContain('investigateModel');
    expect(js).toContain("runTeam('open_weights'");
  });
});
