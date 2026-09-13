import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

function read(relPath) {
  return readFileSync(path.join(process.cwd(), relPath), 'utf8');
}

function buildGetNextUrl(search) {
  const source = read('src/frontend/login.html');
  const match = source.match(/function getNextUrl\(\) \{[\s\S]*?return next;\r?\n\s*\}/);
  if (!match) throw new Error('getNextUrl not found in login.html');
  const windowObj = { location: { search } };
  return new Function('window', 'URLSearchParams', `${match[0]}; return getNextUrl;`)(windowObj, URLSearchParams);
}

describe('login.html auth flow guards', () => {
  it('allows root-relative next targets and rejects external redirects', () => {
    expect(buildGetNextUrl('?next=/system-evolution.html?panel=items')()).toBe('/system-evolution.html?panel=items');
    expect(buildGetNextUrl('?next=//evil.example/login')()).toBe('/agent-team-config.html');
    expect(buildGetNextUrl('?next=https://evil.example/login')()).toBe('/agent-team-config.html');
    expect(buildGetNextUrl('')()).toBe('/agent-team-config.html');
  });

  it('primes csrf token on both login and register success paths', () => {
    const source = read('src/frontend/login.html');
    const matches = source.match(/window\.api\.setCsrfToken\(data\.csrf_token\);/g) || [];
    expect(matches).toHaveLength(2);
  });

  it('keeps auth bootstrap on the sanitized redirect path', () => {
    const source = read('src/frontend/login.html');
    expect(source).toContain("window.location.href = getNextUrl();");
    expect(source).toContain("window.api.request('/api/v1/auth/me').then(function (data) {");
    expect(source).toContain("localStorage.setItem('ag-user', data.username);");
  });

  it('offers no guest entry, which authenticated nothing and made writes fail with 401', () => {
    const source = read('src/frontend/login.html');
    expect(source).not.toContain('guestLogin');
    expect(source).not.toContain("'ag-user', 'guest'");
  });
});
