/**
 * Investment Engine research sidebar (P10).
 * UI-only: localStorage sa_engine_sidebar_v1; does not alter simulation state machine.
 */
(function (global) {
  'use strict';

  var STORAGE_KEY = 'sa_engine_sidebar_v1';

  var ITEMS = [
    { id: 'overview', label: '首页', target: 'engine-overview', group: 'primary', icon: '⌂' },
    { id: 'analysis', label: '分析', target: 'engine-config', group: 'primary', icon: '◫' },
    { id: 'news', label: '信息流', target: 'engine-context', group: 'primary', icon: '☰', badge: 'docs_ai' },
    { id: 'performance', label: '市场表现', target: 'engine-dashboard', group: 'primary', icon: '↗' },
    { id: 'authors', label: '我的 Agent', target: 'engine-assembly', group: 'primary', icon: '◎', badge: 'modules_team' },
    { id: 'research', label: '研究组', target: 'engine-assembly', group: 'research', icon: '▤', badge: 'sources_selected' },
    { id: 'timeline', label: '运行时间线', target: 'engine-timeline', group: 'secondary', icon: '≡' },
    { id: 'health', label: '运行时健康', target: 'engine-health', group: 'secondary', icon: '♥' },
    { id: 'portfolio', label: '纸面组合', target: 'engine-portfolio', group: 'primary', icon: '◈' },
  ];

  function defaultState() {
    return {
      collapsed: false,
      expandedMore: false,
      active: 'overview',
      drawerOpen: false,
      badges: {},
    };
  }

  function loadState() {
    var base = defaultState();
    try {
      var raw = global.localStorage && global.localStorage.getItem(STORAGE_KEY);
      if (!raw) return base;
      var parsed = JSON.parse(raw);
      if (parsed && typeof parsed === 'object') {
        if (typeof parsed.collapsed === 'boolean') base.collapsed = parsed.collapsed;
        if (typeof parsed.expandedMore === 'boolean') base.expandedMore = parsed.expandedMore;
        if (typeof parsed.active === 'string') base.active = parsed.active;
      }
    } catch (e) {
      /* ignore */
    }
    return base;
  }

  function saveState(state) {
    try {
      if (!global.localStorage) return;
      global.localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          collapsed: !!state.collapsed,
          expandedMore: !!state.expandedMore,
          active: state.active || 'overview',
        })
      );
    } catch (e) {
      /* ignore */
    }
  }

  function badgeText(value) {
    if (value === null || value === undefined || value === '') return '—';
    if (typeof value === 'number' && !isFinite(value)) return '—';
    return String(value);
  }

  function focusTarget(targetId) {
    var el = global.document && global.document.getElementById(targetId);
    if (!el) return;
    if (typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    if (typeof el.focus === 'function') {
      try {
        el.setAttribute('tabindex', '-1');
        el.focus({ preventScroll: true });
      } catch (e) {
        /* ignore */
      }
    }
  }

  function renderNav(state) {
    var doc = global.document;
    if (!doc) return;

    var list = doc.getElementById('engine-sidebar-list');
    if (!list) return;

    var showSecondary = !!state.expandedMore;
    var html = '';
    var lastGroup = '';

    ITEMS.forEach(function (item) {
      if (item.group === 'secondary' && !showSecondary) return;
      if (item.group === 'research' && lastGroup === 'primary') {
        html += '<li class="engine-sidebar-sep" role="separator" aria-hidden="true"></li>';
      }
      if (item.group === 'secondary' && lastGroup !== 'secondary') {
        html += '<li class="engine-sidebar-sep" role="separator" aria-hidden="true"></li>';
      }
      lastGroup = item.group;

      var isActive = state.active === item.id;
      var badge = item.badge ? badgeText(state.badges[item.badge]) : '';
      var badgeHtml = item.badge
        ? '<span class="engine-sidebar-badge" data-badge="' +
          item.badge +
          '">' +
          badge +
          '</span>'
        : '';

      html +=
        '<li>' +
        '<button type="button" class="engine-sidebar-item' +
        (isActive ? ' is-active' : '') +
        '" data-sidebar-id="' +
        item.id +
        '" data-target="' +
        item.target +
        '"' +
        (isActive ? ' aria-current="page"' : '') +
        '>' +
        '<span class="engine-sidebar-icon" aria-hidden="true">' +
        item.icon +
        '</span>' +
        '<span class="engine-sidebar-label">' +
        item.label +
        '</span>' +
        badgeHtml +
        '</button></li>';
    });

    list.innerHTML = html;
  }

  function applyChrome(state) {
    var doc = global.document;
    if (!doc) return;
    var shell = doc.getElementById('engine-shell');
    var nav = doc.getElementById('engine-sidebar');
    var toggle = doc.getElementById('engine-sidebar-toggle');
    var more = doc.getElementById('engine-sidebar-more');
    var drawerBtn = doc.getElementById('engine-sidebar-open');
    var overlay = doc.getElementById('engine-sidebar-overlay');

    if (shell) {
      shell.classList.toggle('sidebar-collapsed', !!state.collapsed);
      shell.classList.toggle('sidebar-drawer-open', !!state.drawerOpen);
    }
    if (nav) {
      nav.setAttribute('aria-expanded', state.collapsed ? 'false' : 'true');
      nav.classList.toggle('is-collapsed', !!state.collapsed);
      nav.classList.toggle('is-drawer-open', !!state.drawerOpen);
    }
    if (toggle) {
      toggle.setAttribute('aria-expanded', state.collapsed ? 'false' : 'true');
      toggle.setAttribute(
        'aria-label',
        state.collapsed ? '展开研究导航' : '折叠研究导航'
      );
      toggle.textContent = state.collapsed ? '»' : '«';
    }
    if (more) {
      more.setAttribute('aria-expanded', state.expandedMore ? 'true' : 'false');
      more.textContent = state.expandedMore ? '显示更少' : '显示更多';
    }
    if (drawerBtn) {
      drawerBtn.setAttribute('aria-expanded', state.drawerOpen ? 'true' : 'false');
    }
    if (overlay) {
      overlay.hidden = !state.drawerOpen;
      overlay.setAttribute('aria-hidden', state.drawerOpen ? 'false' : 'true');
    }
  }

  function selectItem(state, id) {
    var item = null;
    for (var i = 0; i < ITEMS.length; i++) {
      if (ITEMS[i].id === id) {
        item = ITEMS[i];
        break;
      }
    }
    if (!item) return state;
    state.active = id;
    state.drawerOpen = false;
    saveState(state);
    renderNav(state);
    applyChrome(state);
    focusTarget(item.target);
    return state;
  }

  function setBadges(state, badges) {
    state.badges = badges || {};
    renderNav(state);
    return state;
  }

  function init(options) {
    options = options || {};
    var state = loadState();
    if (options.badges) state.badges = options.badges;

    var doc = global.document;
    renderNav(state);
    applyChrome(state);

    if (!doc) {
      return {
        state: state,
        selectItem: function (id) {
          return selectItem(state, id);
        },
        setBadges: function (b) {
          return setBadges(state, b);
        },
        getState: function () {
          return state;
        },
      };
    }

    doc.addEventListener('click', function (ev) {
      var t = ev.target;
      if (!t || !t.closest) return;
      var itemBtn = t.closest('[data-sidebar-id]');
      if (itemBtn && itemBtn.getAttribute('data-sidebar-id')) {
        selectItem(state, itemBtn.getAttribute('data-sidebar-id'));
        return;
      }
      if (t.closest('#engine-sidebar-toggle')) {
        state.collapsed = !state.collapsed;
        saveState(state);
        applyChrome(state);
        return;
      }
      if (t.closest('#engine-sidebar-more')) {
        state.expandedMore = !state.expandedMore;
        saveState(state);
        renderNav(state);
        applyChrome(state);
        return;
      }
      if (t.closest('#engine-sidebar-open')) {
        state.drawerOpen = !state.drawerOpen;
        applyChrome(state);
        return;
      }
      if (t.closest('#engine-sidebar-overlay') || t.closest('#engine-sidebar-close')) {
        state.drawerOpen = false;
        applyChrome(state);
      }
    });

    doc.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape' && state.drawerOpen) {
        state.drawerOpen = false;
        applyChrome(state);
      }
    });

    return {
      state: state,
      selectItem: function (id) {
        return selectItem(state, id);
      },
      setBadges: function (b) {
        return setBadges(state, b);
      },
      getState: function () {
        return state;
      },
      ITEMS: ITEMS,
      STORAGE_KEY: STORAGE_KEY,
    };
  }

  global.EngineSidebar = {
    init: init,
    loadState: loadState,
    saveState: saveState,
    ITEMS: ITEMS,
    STORAGE_KEY: STORAGE_KEY,
    badgeText: badgeText,
    defaultState: defaultState,
  };
})(typeof window !== 'undefined' ? window : globalThis);
