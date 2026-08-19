/**
 * AgentsGroup2026 — Shared Global Navigation (compat shim)
 *
 * Prefer nav.js. This file keeps the same PAGE labels/hrefs for legacy
 * pages and tests that load global-nav.js directly.
 * If nav.js already ran (window.AG_NAV), reuse it; otherwise inject into .global-nav.
 */
(function () {
  'use strict';

  // Same canonical set as nav.js — keep labels in lockstep
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

  var script = document.querySelector('script[src*="global-nav.js"][data-page], script[data-page]');
  var currentId = script ? (script.getAttribute('data-page') || '') : '';

  function buildNavHTML() {
    var html = '';
    for (var i = 0; i < PAGES.length; i++) {
      var p = PAGES[i];
      if (p.id === currentId) {
        html += '<span class="cur" aria-current="page">' + p.label + '</span>';
      } else {
        html += '<a href="' + p.href + '">' + p.label + '</a>';
      }
    }
    var user = null;
    try { user = localStorage.getItem('ag-user'); } catch (e) { /* ignore */ }
    if (user && user !== 'guest') {
      html += '<span class="nav-user" style="margin-left:auto;display:flex;align-items:center;gap:6px;font-size:12px;color:var(--sumi-3,#666)">';
      html += '<span>' + user + '</span>';
      html += '<button type="button" onclick="window._agLogout()" style="font-size:11px;padding:2px 8px;cursor:pointer;background:none;border:1px solid var(--groove,#ddd);color:inherit;border-radius:3px">登出</button>';
      html += '</span>';
    }
    return html;
  }

  function injectNav() {
    if (window.AG_NAV && typeof window.AG_NAV.injectNav === 'function') {
      // nav.js already owns topbar + global-nav
      window.AG_NAV.injectNav();
      return;
    }
    var navs = document.querySelectorAll('.global-nav');
    var navHTML = buildNavHTML();
    for (var i = 0; i < navs.length; i++) {
      navs[i].innerHTML = navHTML;
    }
  }

  if (!window._agLogout) {
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
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', injectNav);
  } else {
    injectNav();
  }

  window.AG_GLOBAL_NAV = { PAGES: PAGES, buildNavHTML: buildNavHTML, injectNav: injectNav };
})();
