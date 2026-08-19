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
    expect(html).toMatch(/研究\/模拟|非投资建议/);
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
});
