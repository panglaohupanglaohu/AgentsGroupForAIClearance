import { readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const BANNED = [
  /投资建议/,
  /股票/,
  /纸面组合/,
  /投资引擎/,
  /StockAgents/i,
];

const SCAN_TARGETS = [
  'src/frontend/ai-model-entry-clearance.html',
  'src/frontend/data-intelligence.html',
  'src/frontend/js/ai-model-entry-clearance.js',
  'src/frontend/js/data-intelligence.js',
  'src/frontend/js/engine-sidebar.js',
  'src/frontend/js/engine-state.js',
  'src/frontend/js/engine-reducer.js',
  'src/frontend/js/engine-judgment.js',
];

describe('Terminology Guard (T007)', () => {
  it('clearance and data intelligence frontend files contain no banned investment terminology', () => {
    for (const rel of SCAN_TARGETS) {
      const fullPath = path.join(process.cwd(), rel);
      const text = readFileSync(fullPath, 'utf8');
      for (const pattern of BANNED) {
        expect(text, `${rel} should not contain ${pattern}`).not.toMatch(pattern);
      }
    }
  });
});
