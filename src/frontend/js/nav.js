/**
 * AgentsGroup2026 — Unified site navigation (single source of truth)
 *
 * Injects the same page set into:
 *   - .topbar-ws__nav   (primary horizontal topbar)
 *   - .global-nav       (legacy flat nav)
 *   - [data-ag-site-nav] (optional hooks, e.g. cost shell)
 *
 * Usage:
 *   <script src="/js/nav.js" data-page="plaza"></script>
 * data-page should match a PAGE id; if omitted, path is auto-detected.
 *
 * Always overwrites target nav containers so hardcoded HTML cannot drift.
 * Also wires .topbar-ws__user-* and window._agLogout.
 */
(function () {
  'use strict';

  /** Canonical site map — labels and hrefs must stay identical on every page. */
  var PAGES = [
    { id: 'agents',        label: '智能体团队', href: '/agent-team-config.html' },
    { id: 'plaza',         label: '议事广场',   href: '/plaza.html' },
    { id: 'skill-extract', label: '技能萃取',   href: '/skill-extract.html' },
    { id: 'memory',        label: 'Agent记忆',  href: '/agent-memory.html' },
    { id: 'digital-twin',  label: '数字孪生',   href: '/Agent-digital-twin.html?office3d=1' },
    { id: 'cost',          label: 'Token节省',  href: '/cost-dashboard.html' },
    { id: 'pet',           label: '生态配置',   href: '/pet-config.html' },
    { id: 'data-intelligence', label: '数据采集/分析', href: '/data-intelligence.html' },
    { id: 'model-clearance',   label: 'AI 模型准入',   href: '/ai-model-entry-clearance.html' }
  ];

  /** Path → page id (secondary pages map to nearest primary). */
  var PATH_MAP = [
    { re: /agent-team-config/i, id: 'agents' },
    { re: /plaza\.html/i, id: 'plaza' },
    { re: /skill-extract|extraction-pipeline/i, id: 'skill-extract' },
    { re: /agent-memory/i, id: 'memory' },
    { re: /Agent-digital-twin|digital-twin-cli|sandbox-twin/i, id: 'digital-twin' },
    { re: /cost-dashboard|datacenter-ratchet/i, id: 'cost' },
    { re: /pet-config/i, id: 'pet' },
    { re: /data-intelligence/i, id: 'data-intelligence' },
    { re: /ai-model-entry-clearance|model-clearance|open-weights-models/i, id: 'model-clearance' },
    { re: /system-evolution/i, id: 'agents' },
    { re: /tasks\.html/i, id: 'agents' }
  ];

  function detectPageIdFromPath() {
    var path = '';
    try {
      path = (window.location && window.location.pathname) || '';
    } catch (e) { /* ignore */ }
    for (var i = 0; i < PATH_MAP.length; i++) {
      if (PATH_MAP[i].re.test(path)) return PATH_MAP[i].id;
    }
    return '';
  }

  function currentPageId() {
    var scripts = document.querySelectorAll('script[src*="nav.js"][data-page], script[data-page]');
    var fromScript = '';
    for (var i = 0; i < scripts.length; i++) {
      var src = scripts[i].getAttribute('src') || '';
      var page = scripts[i].getAttribute('data-page') || '';
      if (page && (src.indexOf('nav.js') >= 0 || scripts[i].src && String(scripts[i].src).indexOf('nav.js') >= 0)) {
        fromScript = page;
        break;
      }
      if (!fromScript && page && !src) fromScript = page;
    }
    // Prefer explicit data-page on nav.js; fall back to any data-page then path
    if (!fromScript) {
      var s = document.querySelector('script[src*="nav.js"]');
      if (s) fromScript = s.getAttribute('data-page') || '';
    }
    if (!fromScript) {
      var any = document.querySelector('script[data-page]');
      if (any) fromScript = any.getAttribute('data-page') || '';
    }
    return fromScript || detectPageIdFromPath();
  }

  function buildNavHTML(currentId) {
    var html = '';
    for (var i = 0; i < PAGES.length; i++) {
      var p = PAGES[i];
      if (p.id === currentId) {
        html += '<span class="cur" aria-current="page" data-nav-id="' + p.id + '">' + p.label + '</span>';
      } else {
        html += '<a href="' + p.href + '" data-nav-id="' + p.id + '">' + p.label + '</a>';
      }
    }
    return html;
  }

  function injectNav() {
    var currentId = currentPageId();
    var html = buildNavHTML(currentId);
    var targets = document.querySelectorAll('.topbar-ws__nav, .global-nav, [data-ag-site-nav]');
    for (var i = 0; i < targets.length; i++) {
      targets[i].innerHTML = html;
    }
    syncUserChip();
  }

  function syncUserChip() {
    var user = null;
    try { user = localStorage.getItem('ag-user'); } catch (e) { /* ignore */ }
    var name = (user && user !== 'guest') ? user : 'guest';
    var initial = name ? name.charAt(0).toUpperCase() : 'U';
    var nameEls = document.querySelectorAll('.topbar-ws__user-name, #topbar-user');
    var avatarEls = document.querySelectorAll('.topbar-ws__user-avatar, #topbar-avatar');
    for (var i = 0; i < nameEls.length; i++) nameEls[i].textContent = name;
    for (var j = 0; j < avatarEls.length; j++) avatarEls[j].textContent = initial;
  }

  window._agLogout = function () {
    if (window.api && window.api.logout) {
      window.api.logout().then(function () {
        try { localStorage.removeItem('ag-user'); } catch (e) { /* ignore */ }
        window.location.href = '/login.html';
      });
    } else {
      try { localStorage.removeItem('ag-user'); } catch (e) { /* ignore */ }
      window.location.href = '/login.html';
    }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', injectNav);
  } else {
    injectNav();
  }

  window.AG_NAV = {
    PAGES: PAGES,
    buildNavHTML: buildNavHTML,
    injectNav: injectNav,
    currentPageId: currentPageId,
    detectPageIdFromPath: detectPageIdFromPath
  };
})();
