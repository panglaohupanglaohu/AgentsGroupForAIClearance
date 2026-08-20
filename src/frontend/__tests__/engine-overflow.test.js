import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const html = readFileSync(
  path.join(process.cwd(), 'src/frontend/ai-model-entry-clearance.html'),
  'utf8',
);

describe('Engine assembly overflow (P11)', () => {
  it('clips page-level horizontal overflow and zeros grid min-width', () => {
    expect(html).toMatch(/overflow-x:\s*clip/);
    expect(html).toMatch(/\.grid\s*>\s*\*\s*\{[^}]*min-width:\s*0/);
    expect(html).toMatch(/minmax\(0,\s*1fr\)/);
    expect(html).toContain('engine-main');
  });

  it('keeps internal scroll regions for parts bank and road modules', () => {
    expect(html).toMatch(/\.parts-bank[\s\S]*overflow-x:\s*auto/);
    expect(html).toContain('id="road-modules-scroll"');
    expect(html).toContain('data-road-core="ingress"');
    expect(html).toContain('data-road-core="research"');
    expect(html).toContain('data-road-core="portfolio"');
    expect(html).toContain('parts-scroll-hint');
  });

  it('preserves drag contracts and primary engine controls', () => {
    [
      'btn-engine-start',
      'source-drop',
      'source-selected',
      'source-library',
      'module-library',
      'use_case',
      'model_id',
    ].forEach((id) => expect(html).toContain(`id="${id}"`));
    expect(html).toContain('draggable="true"');
  });
});
