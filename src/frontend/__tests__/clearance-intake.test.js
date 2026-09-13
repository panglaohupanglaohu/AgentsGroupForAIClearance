import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const root = process.cwd();
const read = (p) => readFileSync(path.join(root, p), 'utf8');

describe('clearance intake from the open-weights catalogue', () => {
  const sender = read('src/frontend/js/open-weights-models.js');
  const dataIntelligence = read('src/frontend/js/data-intelligence.js');
  const console_ = read('src/frontend/js/ai-model-entry-clearance.js');
  const html = read('src/frontend/ai-model-entry-clearance.html');

  it('sends artifact facts the registry already knows', () => {
    expect(sender).toContain('function buildClearanceHref');
    expect(sender).toContain('revision=');
    expect(sender).toContain('weights_uri=');
    // 两个入口都必须走同一个构造函数，否则卡片和弹窗会带不一样的参数
    expect(sender).not.toContain("'/ai-model-entry-clearance.html?model_id='");
    expect((sender.match(/=\s*buildClearanceHref\(m\)/g) || []).length).toBe(2);
  });

  it('reads the incoming model from the query string', () => {
    expect(console_).toContain('new URLSearchParams(window.location.search)');
    expect(console_).toContain("q.get('model_id')");
    expect(console_).toContain('function applyIncoming');
  });

  it('marks data-intelligence links as evidence-backed fast-track intake', () => {
    expect(dataIntelligence).toContain('source=data-intelligence');
    expect(dataIntelligence).toContain('revision=');
    expect(dataIntelligence).toContain('weights_uri=');
    expect(console_).toContain('function isFastTrackIntake');
    expect(console_).toContain("incoming.source === 'data-intelligence'");
  });

  it('does not block evidence-backed intake on governance details that gates can assess as missing', () => {
    expect(console_).toContain('function blockingStandardErrors');
    expect(console_).toMatch(/function blockingStandardErrors[\s\S]*?return \[\]/);
    expect(console_).toMatch(/async function createApplication[\s\S]*?blockingStandardErrors\(form\)/);
    expect(console_).toMatch(/async function onPrimaryStart[\s\S]*?blockingStandardErrors\(form\)/);
    expect(console_).toContain("applicant: ''");
    expect(console_).toContain("review_scope: 'model'");
    expect(console_).toContain('deployment: {}');
    expect(html).not.toMatch(/intended_use\).*必填/);
    expect(html).not.toMatch(/named_owner\).*必填/);
  });

  it('refuses to prefill a floating revision tag', () => {
    // 标准 §6.1 / G1-PROV-02 禁止 main/latest
    expect(console_).toMatch(/main\|latest\|master\|head/i);
  });

  it('does not restore an unrelated previous application when a model is carried in', () => {
    expect(console_).toMatch(/if \(incoming\) \{[\s\S]*?\} else \{\s*restore\(\);/);
  });

  it('renders an intake notice that lists what still blocks the review', () => {
    expect(html).toContain('id="intake-notice"');
    expect(console_).toContain('function renderIntakeNotice');
    expect(console_).toContain('评审尚未启动');
  });

  it('puts a run button where the reviewer is, not off-screen at the page top', () => {
    // #btn-engine-start 在页头，带入模型时视图停在下方表单，够不着
    expect(console_).toContain('data-intake-start');
    expect(console_).toContain('启动准入评审');
    expect(html).toContain('.intake-notice .btn');
    expect(html).toContain('id="btn-pipeline-start"');
    expect(console_).toContain("$('btn-pipeline-start').addEventListener");
  });

  it('retries the stored model snapshot instead of rebuilding from applicant fields', () => {
    expect(console_).toContain("encodeURIComponent(engineState.runId) + '/retry'");
    expect(console_).toMatch(/d\.action === 'rerun' \|\| d\.action === 'retry'[\s\S]*?retryApplication\(\)/);
  });

  it('labels intelligence chips as removable references, not failed models', () => {
    expect(console_).toContain('aria-label="移除参考情报"');
    expect(console_).toContain('>移除</button>');
  });

  it('collapses optional deployment details for fast-track intake but keeps them editable', () => {
    expect(html).toContain('id="extended-application-fields"');
    expect(console_).toContain('data-intake-edit');
    expect(console_).toContain('不会伪造');
  });

  it('scrolls to the timeline after starting so the run is visible', () => {
    expect(console_).toMatch(/data-intake-start[\s\S]*?clearance-timeline/);
  });

  it('wins the button text colour back from the taste-light theme', () => {
    // html.taste-light .btn 特异度 (0,2,1) 会把文字压成 #4B5568，深底上只剩 2.38:1
    expect(html).toContain('html.taste-light .btn { color:#fff; }');
    expect(html).toMatch(/html\.taste-light \.btn:disabled/);
  });
});
