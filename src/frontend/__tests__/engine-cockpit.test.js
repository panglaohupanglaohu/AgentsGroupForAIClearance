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

describe('Engine Live Cockpit (T801/T802/T832/T861)', () => {
  it('ai-model-entry-clearance.html exposes primary start button on first paint', () => {
    const html = readFileSync(
      path.join(process.cwd(), 'src/frontend/ai-model-entry-clearance.html'),
      'utf8',
    );
    expect(html).toContain('id="btn-engine-start"');
    expect(html).toContain('创建并启动准入评审');
    expect(html).toContain('engine-state.js');
    expect(html).toContain('engine-reducer.js');
    expect(html).toContain('仅供内部治理参考');
  });

  it('keeps the rig wide and stacks controls/results on the right rail', () => {
    const html = readFileSync(
      path.join(process.cwd(), 'src/frontend/ai-model-entry-clearance.html'),
      'utf8',
    );
    expect(html).toContain('grid-template-areas:"rig rig" "main config" "main rail"');
    expect(html).toContain('#engine-config { grid-area:config; }');
    expect(html).toContain('.grid > aside:not(#engine-config) { grid-area:rail;');
    expect(html).toContain('max-width:none');
    expect(html).toContain('id="reports" class="report-index"');
    expect(html).toContain('id="gate-lanes"');
    expect(html).toContain('id="parts-teams"');
    // 组装状态必须驱动主 CTA 与上下文卡片
    expect(
      readFileSync(path.join(process.cwd(), 'src/frontend/js/ai-model-entry-clearance.js'), 'utf8'),
    ).toContain('contributions.length');
  });

  it('deriveStartState covers five run statuses', () => {
    const s = loadScript('src/frontend/js/engine-state.js');
    const form = { model_id: 'meta-llama/Llama-3.1-8B-Instruct', revision: 'v1.0', as_of: '2026-07-01', target_qpm: 10000 };
    const ES = s.window.EngineState || s.EngineState;
    expect(ES.deriveStartState(form, null).action).toBe('create_start');
    expect(ES.deriveStartState(form, { run_id: 'r1', status: 'queued' }).label).toContain('准入');
    expect(ES.deriveStartState(form, { run_id: 'r1', status: 'running' }).disabled).toBe(true);
    expect(ES.deriveStartState(form, { run_id: 'r1', status: 'completed' }).action).toBe('rerun');
    expect(ES.deriveStartState(form, { run_id: 'r1', status: 'failed' }).action).toBe('retry');
    expect(ES.validateEngineForm({ model_id: '', as_of: '', target_qpm: 1 }).length).toBeGreaterThan(0);
    expect(ES.validateEngineForm({ model_id: 'meta-llama/Llama-3.1-8B-Instruct', revision: 'main', as_of: '2026-08-20' })).toContain('必须锁定不可变 revision，禁止 main/latest');
    expect(ES.validateEngineForm(form).length).toBe(0);
  });

  it('reducer dedups seq and maps structured phases', () => {
    const s = loadScript('src/frontend/js/engine-reducer.js');
    const ES = loadScript('src/frontend/js/engine-state.js');
    const ER = s.window.EngineReducer || s.EngineReducer;
    const create = (ES.window.EngineState || ES.EngineState).create;
    let state = create();
    const ev = {
      seq: 1,
      phase: 'analysis',
      node: 'market_analyst',
      participant: 'Market',
      status: 'completed',
      content: 'ok <script>alert(1)</script>',
      structured: {
        claim: '偏多',
        direction: 'bullish',
        confidence: 0.6,
        label: 'analysis',
      },
      evidence: ['e1'],
      ts: 't',
    };
    state = ER.reduceJourney(state, ev);
    state = ER.reduceJourney(state, ev); // duplicate
    expect(state.events.length).toBe(1);
    expect(state.insights.judgment.claim).toBe('偏多');
    expect(state.insights.judgment.claim).not.toContain('<script>');
    expect(ER.safeText('<b>x</b>')).toBe('x');

    state = ER.reduceJourney(state, {
      seq: 2,
      phase: 'planning',
      node: 'research_manager',
      participant: 'RM',
      status: 'completed',
      content: 'plan',
      structured: {
        objective: '模拟目标',
        base_case: { action: 'HOLD' },
        bull_case: { action: 'BUY' },
        bear_case: { action: 'REDUCE' },
      },
    });
    expect(state.insights.plan.bull_case.action).toBe('BUY');
  });

  it('modulesFromDraft maps draft assembly modules', () => {
    const s = loadScript('src/frontend/js/engine-state.js');
    const ES = s.window.EngineState || s.EngineState;
    const mods = ES.modulesFromDraft([
      { sourceId: 'team:ai_news_60s', kind: 'team', name: 'AI', priority: 1 },
    ]);
    expect(mods[0].module_id).toBe('team:ai_news_60s');
    expect(mods[0].kind).toBe('team');
  });
});
