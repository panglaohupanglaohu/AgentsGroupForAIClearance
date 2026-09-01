import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const html = readFileSync(
  path.join(process.cwd(), 'src/frontend/ai-model-entry-clearance.html'),
  'utf8',
);

describe('Clearance rig layout (P11)', () => {
  it('clips page-level horizontal overflow and zeros grid min-width', () => {
    expect(html).toMatch(/overflow-x:\s*clip/);
    expect(html).toMatch(/\.grid\s*>\s*\*\s*\{[^}]*min-width:\s*0/);
    expect(html).toMatch(/minmax\(0,\s*1fr\)/);
    expect(html).toContain('engine-main');
  });

  it('keeps the parts rail scrollable so a long contributor list cannot blow out the page', () => {
    expect(html).toMatch(/\.parts-rail[\s\S]*overflow:\s*auto/);
    expect(html).toMatch(/\.parts-rail[\s\S]*max-height/);
  });

  it('exposes the composable rig contracts and primary controls', () => {
    [
      'btn-engine-start',
      'gate-lanes',
      'parts-teams',
      'parts-documents',
      'parts-sources',
      'model_id',
    ].forEach((id) => expect(html).toContain(`id="${id}"`));

    // 零件由 /contributors 动态渲染，拖拽契约在 JS 里
    const js = readFileSync(
      path.join(process.cwd(), 'src/frontend/js/ai-model-entry-clearance.js'),
      'utf8',
    );
    expect(js).toContain('draggable="true"');
    expect(js).toContain('/api/v1/model-clearance/contributors');
    expect(js).toContain('dragstart');
    expect(js).toContain('drop');
  });

  it('lays the 9 gates out as one horizontal scrollable pipeline', () => {
    expect(html).toMatch(/\.lanes \{[^}]*display:flex/);
    expect(html).toMatch(/\.lanes \{[^}]*overflow-x:\s*auto/);
    // 泳道定宽才能横排，不能被压扁
    expect(html).toMatch(/\.lane \{[^}]*flex:0 0 /);
    // 泳道之间有箭头，体现门禁执行顺序
    expect(html).toMatch(/\.lane:not\(:last-child\)::after/);
  });

  it('displays step numbers, responsible agents and execution status on each gate lane', () => {
    const js = readFileSync(
      path.join(process.cwd(), 'src/frontend/js/ai-model-entry-clearance.js'),
      'utf8',
    );
    expect(js).toContain('lane-step');
    expect(js).toContain('步骤 #');
    expect(js).toContain('lane-agent');
    expect(js).toContain('lane-agent-name');
    expect(js).toContain('lane-agent-id');
    expect(js).toContain('lane-exec');
    expect(js).toContain('updateGateLanesStatus');
    expect(html).toContain('.lane-agent');
    expect(html).toContain('.lane-step');
  });

  it('gives the pipeline its own full-width grid row', () => {
    expect(html).toContain('grid-template-areas:"rig rig" "main config" "main rail"');
    expect(html).toContain('#clearance-evidence { grid-area:rig; }');
  });

  it('keeps drag-and-drop resilient: delegation, dragenter, and a payload fallback', () => {
    const js = readFileSync(
      path.join(process.cwd(), 'src/frontend/js/ai-model-entry-clearance.js'),
      'utf8',
    );
    // 委托绑定在不变的祖先上，零件/泳道重渲染后监听器不会丢
    expect(js).toMatch(/rig\.addEventListener\('dragstart'/);
    expect(js).toMatch(/rig\.addEventListener\('drop'/);
    // Firefox 等浏览器要求 dragenter 也 preventDefault 才允许放置
    expect(js).toMatch(/rig\.addEventListener\('dragenter'/);
    // dataTransfer 在部分浏览器 drop 时取不到值，必须有兜底
    expect(js).toContain('return draggedPart;');
    // 拖拽失败时仍有点选放入的通路
    expect(js).toContain("rig.classList.add('has-picked')");
    expect(html).toContain('.has-picked .lane');
  });

  it('pins grid column widths so scrollbars cannot oscillate the layout', () => {
    // 默认 grid 列取 max-content，长文本会撑宽列、催生横向滚动条并与纵向滚动条互相触发
    expect(html).toMatch(/\.parts-list \{[^}]*grid-template-columns:minmax\(0,1fr\)/);
    expect(html).toMatch(/\.lane-drop \{[^}]*grid-template-columns:minmax\(0,1fr\)/);
    expect(html).toMatch(/\.part \{[^}]*min-width:0/);
  });

  it('wraps the parts rail instead of the pipeline on narrow viewports', () => {
    expect(html).toMatch(/@media \(max-width: 600px\)[\s\S]*\.parts-rail \{ max-height:none; flex-wrap:wrap; \}/);
  });
});
