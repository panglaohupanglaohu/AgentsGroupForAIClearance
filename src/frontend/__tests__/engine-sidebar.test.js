import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import vm from 'node:vm';

const PRESERVED = [
  'sector',
  'ticker',
  'trade_date',
  'cash',
  'debate',
  'risk',
  'mode',
  'btn-create',
  'btn-start',
  'btn-cancel',
  'btn-engine-start',
  'run-id',
  'run-status',
  'source-drop',
  'source-selected',
  'dynamic-dashboard',
  'timeline',
  'portfolio',
  'runtime-health',
];

const ANCHORS = [
  'clearance-overview',
  'clearance-application',
  'clearance-evidence',
  'clearance-posture',
  'clearance-board',
  'clearance-registry',
  'clearance-timeline',
  'clearance-health',
];

function loadSidebarScript() {
  const code = readFileSync(
    path.join(process.cwd(), 'src/frontend/js/engine-sidebar.js'),
    'utf8',
  );
  const store = {};
  const sandbox = {
    console,
    window: {},
    globalThis: {},
    localStorage: {
      getItem(k) {
        return store[k] || null;
      },
      setItem(k, v) {
        store[k] = String(v);
      },
      removeItem(k) {
        delete store[k];
      },
    },
  };
  sandbox.globalThis = sandbox;
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox);
  return { api: sandbox.window.EngineSidebar || sandbox.EngineSidebar, store };
}

describe('Engine research sidebar (P10)', () => {
  it('html keeps control contracts and adds research nav anchors', () => {
    const html = readFileSync(
      path.join(process.cwd(), 'src/frontend/ai-model-entry-clearance.html'),
      'utf8',
    );
    for (const id of PRESERVED) {
      expect(html).toContain(`id="${id}"`);
    }
    for (const id of ANCHORS) {
      expect(html).toContain(`id="${id}"`);
    }
    expect(html).toContain('aria-label="准入控制台导航"');
    expect(html).toContain('engine-sidebar.js');
    expect(html).toContain('id="engine-sidebar"');
    expect(html).toContain('id="btn-engine-start"');
    expect(html).toContain('创建并启动 Engine');
  });

  it('sidebar module exposes items, storage key, and badge fallback', () => {
    const { api } = loadSidebarScript();
    expect(api.STORAGE_KEY).toBe('sa_engine_sidebar_v1');
    expect(api.ITEMS.length).toBeGreaterThanOrEqual(6);
    expect(api.ITEMS.some((x) => x.id === 'application')).toBe(true);
    expect(api.ITEMS.some((x) => x.id === 'registry')).toBe(true);
    expect(api.badgeText(null)).toBe('—');
    expect(api.badgeText(3)).toBe('3');
  });

  it('persists collapsed / active UI state only', () => {
    const { api, store } = loadSidebarScript();
    const state = api.defaultState();
    state.collapsed = true;
    state.active = 'application';
    state.expandedMore = true;
    api.saveState(state);
    const raw = JSON.parse(store[api.STORAGE_KEY]);
    expect(raw.collapsed).toBe(true);
    expect(raw.active).toBe('application');
    expect(raw.expandedMore).toBe(true);
    expect(raw).not.toHaveProperty('apiKey');
    expect(raw).not.toHaveProperty('reportHtml');
  });

  it('maps sidebar targets to stable engine anchors', () => {
    const { api } = loadSidebarScript();
    const targets = api.ITEMS.map((x) => x.target);
    expect(targets).toContain('clearance-application');
    expect(targets).toContain('clearance-posture');
    expect(targets).toContain('clearance-registry');
    expect(targets).toContain('clearance-board');
  });
});
