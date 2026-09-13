/**
 * AgentsGroup2026 — Shared API Client
 * Unified fetch wrapper with error handling, offline detection,
 * and pagination support. Load before page-specific scripts.
 * Exposes window.api with .request(), .get(), .post(), .put(), .del(), .list()
 */
(function () {
  'use strict';

  var nativeFetch = window.fetch ? window.fetch.bind(window) : null;
  var api = window.api = {};

  // Last error for debugging
  api._lastError = null;

  // Offline state (consumed by page-specific UI)
  api._offline = false;
  api._onOffline = null;  // callback when offline status changes
  api._onError = null;    // callback(msg) for 4xx/5xx

  // CSRF token (fetched from endpoint and cached)
  api._csrfToken = null;
  api._csrfPromise = null;
  api._csrfHeaderName = 'X-CSRF-Token';
  api._requestIdHeaderName = 'X-Request-ID';
  api._lastRequestId = '';

  api.setCsrfToken = function (token) {
    api._csrfToken = token || '';
    api._csrfPromise = api._csrfToken ? Promise.resolve(api._csrfToken) : null;
    return api._csrfToken;
  };

  api.clearCsrfToken = function () {
    api._csrfToken = null;
    api._csrfPromise = null;
  };

  api.getLastRequestId = function () {
    return api._lastRequestId || '';
  };

  api._authRedirecting = false;

  api.decorateErrorMessage = function (message, requestId) {
    var text = String(message || '');
    var id = requestId || api.getLastRequestId() || (api._lastError && api._lastError.request_id) || '';
    if (!id || text.indexOf('请求ID:') !== -1) return text;
    return text + ' · 请求ID: ' + id;
  };

  function withCredentials(opts) {
    opts = opts || {};
    if (!opts.credentials) opts.credentials = 'same-origin';
    return opts;
  }

  function isStateChanging(method) {
    method = (method || 'GET').toUpperCase();
    return method === 'POST' || method === 'PUT' || method === 'DELETE' || method === 'PATCH';
  }

  function getRequestUrl(input) {
    if (typeof input === 'string') return input;
    if (input && typeof input.url === 'string') return input.url;
    return '';
  }

  function _resolveTarget(input) {
    var url = getRequestUrl(input);
    if (!url) return { csrfAware: false, sameOrigin: false };
    try {
      var resolved = new URL(url, window.location.origin);
      var current = new URL(window.location.origin);
      var sameOrigin = resolved.origin === current.origin;
      var csrfAware = sameOrigin || (
        resolved.protocol === current.protocol &&
        resolved.hostname === current.hostname
      );
      return { csrfAware: csrfAware, sameOrigin: sameOrigin };
    } catch (e) {
      return { csrfAware: false, sameOrigin: false };
    }
  }

  function hasHeader(headers, name) {
    if (!headers || typeof headers.has !== 'function') return false;
    return headers.has(name) || headers.has(name.toLowerCase());
  }

  function isAuthEndpointPath(pathname) {
    return pathname.indexOf('/api/v1/auth/') === 0;
  }

  // Read-only endpoints are auth-exempt, so a page can look fully loaded while the
  // session is already gone. Say so before navigating, otherwise the bounce back to
  // login reads as "the button did nothing".
  function showSessionExpiredNotice() {
    if (!document.body) return;
    var el = document.createElement('div');
    el.setAttribute('role', 'alert');
    el.textContent = '登录已失效，正在跳转到登录页…';
    el.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:99999;padding:12px 16px;' +
      'background:#b91c1c;color:#fff;font-size:14px;text-align:center';
    document.body.appendChild(el);
  }

  function redirectToLogin() {
    if (api._authRedirecting) return;
    if (window.location.pathname === '/login.html') return;
    api._authRedirecting = true;
    var next = window.location.pathname + window.location.search + window.location.hash;
    var target = '/login.html?next=' + encodeURIComponent(next);
    showSessionExpiredNotice();
    window.setTimeout(function () { window.location.href = target; }, 1200);
  }

  function maybeHandleUnauthorizedResponse(response, input) {
    if (!response || response.status !== 401) return;
    var url = getRequestUrl(input);
    if (!url) return;
    try {
      var resolved = new URL(url, window.location.origin);
      if (resolved.pathname.indexOf('/api/v1/') !== 0) return;
      if (isAuthEndpointPath(resolved.pathname)) return;
      redirectToLogin();
    } catch (e) {
      /* ignore malformed URLs */
    }
  }

  function nextRequestId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
      return window.crypto.randomUUID();
    }
    return 'ag-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
  }

  function getRequestIdFromPrepared(input, opts) {
    if (typeof Request !== 'undefined' && input instanceof Request) {
      return input.headers.get(api._requestIdHeaderName) || '';
    }
    if (opts && opts.headers && typeof opts.headers.get === 'function') {
      return opts.headers.get(api._requestIdHeaderName) || '';
    }
    return '';
  }

  function isCsrfFailurePayload(payload) {
    if (!payload) return false;
    var detail = payload.detail || payload.message || '';
    return typeof detail === 'string' && /csrf token invalid or expired/i.test(detail);
  }

  async function isCsrfFailureResponse(response) {
    if (!response || response.status !== 403 || typeof response.clone !== 'function') return false;
    try {
      var payload = await response.clone().json();
      return isCsrfFailurePayload(payload);
    } catch (e) {
      try {
        var text = await response.clone().text();
        return /csrf token invalid or expired/i.test(text || '');
      } catch (ignored) {
        return false;
      }
    }
  }

  async function prepareRequest(input, opts) {
    var target = _resolveTarget(input);
    if (!target.csrfAware) {
      return [input, opts];
    }

    var requestLike = (typeof Request !== 'undefined') && input instanceof Request;
    var method = (opts && opts.method) || (requestLike ? input.method : 'GET');
    var headers = new Headers((opts && opts.headers) || (requestLike ? input.headers : undefined) || undefined);

    if (isStateChanging(method)) {
      await api.fetchCsrfToken();
      if (api._csrfToken && !hasHeader(headers, api._csrfHeaderName)) {
        headers.set(api._csrfHeaderName, api._csrfToken);
      }
    }
    if (!hasHeader(headers, api._requestIdHeaderName)) {
      headers.set(api._requestIdHeaderName, nextRequestId());
    }

    var finalOpts = {};
    if (opts) {
      Object.keys(opts).forEach(function (key) {
        if (key !== 'headers') finalOpts[key] = opts[key];
      });
    }
    finalOpts.headers = headers;
    if (!finalOpts.credentials) {
      finalOpts.credentials = (requestLike && input.credentials) || (target.sameOrigin ? 'same-origin' : 'include');
    }

    if (requestLike) {
      return [new Request(input, finalOpts), undefined];
    }
    return [input, finalOpts];
  }

  async function fetchWithCsrfRetry(input, opts) {
    var retryInput = (typeof Request !== 'undefined' && input instanceof Request) ? input.clone() : input;
    var prepared = await prepareRequest(input, opts);
    var requestId = getRequestIdFromPrepared(prepared[0], prepared[1]);
    var response = await nativeFetch(prepared[0], prepared[1]);
    maybeHandleUnauthorizedResponse(response, prepared[0]);
    if (!(await isCsrfFailureResponse(response))) {
      return { response: response, requestId: requestId };
    }

    api.clearCsrfToken();
    await api.fetchCsrfToken();
    var retryPrepared = await prepareRequest(retryInput, opts);
    var retryRequestId = getRequestIdFromPrepared(retryPrepared[0], retryPrepared[1]) || requestId;
    var retryResponse = await nativeFetch(retryPrepared[0], retryPrepared[1]);
    maybeHandleUnauthorizedResponse(retryResponse, retryPrepared[0]);
    return { response: retryResponse, requestId: retryRequestId };
  }

  /**
   * Fetch a fresh CSRF token from the server and cache it.
   */
  api.fetchCsrfToken = function () {
    if (api._csrfToken) return Promise.resolve(api._csrfToken);
    if (api._csrfPromise) return api._csrfPromise;
    api._csrfPromise = nativeFetch('/api/v1/auth/csrf-token', withCredentials())
      .then(function (r) { return r.json(); })
      .then(function (d) {
        return api.setCsrfToken(d.csrf_token || '');
      })
      .catch(function () {
        api._csrfPromise = null;
        return '';
      });
    return api._csrfPromise;
  };
  /**
   * Main request function.
   * @param {string} url  - Full or relative URL
   * @param {object} [opts] - fetch options (method, headers, body)
   * @returns {object|null} - Parsed JSON response, or null on error
   */
  api.request = async function (url, opts) {
    try {
      var result = await fetchWithCsrfRetry(url, opts);
      var outgoingRequestId = result.requestId;
      var r = result.response;
      api._lastRequestId = r.headers && r.headers.get ? (r.headers.get(api._requestIdHeaderName) || outgoingRequestId) : outgoingRequestId;
      if (api._offline) {
        api._offline = false;
        if (api._onOffline) api._onOffline(false);
      }
      if (!r.ok) {
        var msg = '';
        try {
          var d = await r.json();
          var det = d.detail;
          if (det && typeof det === 'object') {
            // FastAPI HTTPException(detail={"error":..., "issues":[...]}) → readable string
            msg = det.error || det.message || '';
            if (det.issues && det.issues.length) {
              msg = (msg ? msg + '：' : '') + (Array.isArray(det.issues) ? det.issues.join('；') : det.issues);
            }
            if (!msg) msg = JSON.stringify(det);
          } else {
            msg = det || d.message || '';
          }
        } catch (e) { /* ignore parse errors */ }
        console.warn('API ' + r.status + ': ' + url, msg);
        api._lastError = { status: r.status, message: msg, url: url, request_id: api._lastRequestId || outgoingRequestId };
        if (api._onError) api._onError(msg || 'HTTP ' + r.status);
        api._lastViewError = msg || 'HTTP ' + r.status;
        return null;
      }
      api._lastError = null;
      return await r.json();
    } catch (e) {
      console.error('API error: ' + url, e);
      api._lastRequestId = api._lastRequestId || outgoingRequestId || '';
      if (e.name === 'TypeError' || (e.message && e.message.indexOf('fetch') !== -1)) {
        api._offline = true;
        if (api._onOffline) api._onOffline(true);
      }
      api._lastError = { status: 0, message: e.message, url: url, network: true, request_id: api._lastRequestId || outgoingRequestId || '' };
      if (api._onError) api._onError(e.message);
      api._lastViewError = e.message;
      return null;
    }
  };

  /**
   * Shorthand for GET requests
   */
  api.get = function (url) {
    return api.request(url);
  };

  /**
   * Shorthand for POST/PUT/DELETE with JSON body
   * Automatically includes CSRF token for state-changing requests.
   */
  api.send = async function (url, method, body) {
    var opts = {
      method: method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (body !== undefined) opts.body = JSON.stringify(body);
    return api.request(url, opts);
  };

  /**
   * POST shorthand
   */
  api.post = function (url, body) {
    return api.send(url, 'POST', body);
  };

  /**
   * PUT shorthand
   */
  api.put = function (url, body) {
    return api.send(url, 'PUT', body);
  };

  /**
   * DELETE shorthand
   */
  api.del = function (url) {
    var opts = { method: 'DELETE' };
    if (api._csrfToken) {
      opts.headers = opts.headers || {};
      opts.headers[api._csrfHeaderName] = api._csrfToken;
    }
    return api.request(url, opts);
  };

  api.logout = async function () {
    var result = await api.post('/api/v1/auth/logout');
    api.clearCsrfToken();
    return result;
  };

  /**
   * Pagination wrapper — adds limit/offset/query params to a list GET
   * Returns { items, total, limit, offset, has_more }
   */
  api.list = function (baseUrl, limit, offset) {
    limit = limit || 50;
    offset = offset || 0;
    var sep = baseUrl.indexOf('?') >= 0 ? '&' : '?';
    return api.request(baseUrl + sep + 'limit=' + limit + '&offset=' + offset);
  };

  // Global CSRF-aware fetch wrapper for direct fetch() calls in other scripts.
  // Usage: replace fetch(url, opts) with window._agFetch(url, opts) for state-changing requests.
  window._agFetch = async function (url, opts) {
    var result = await fetchWithCsrfRetry(url, opts);
    return result.response;
  };

  if (nativeFetch) {
    // 全局 fetch 包装：状态变更请求走 CSRF 注入 + 403 重试（与 api.request 一致）
    window.fetch = async function (input, opts) {
      var method = (opts && opts.method) ||
        ((typeof Request !== 'undefined' && input instanceof Request) ? input.method : 'GET') ||
        'GET';
      if (isStateChanging(method)) {
        var result = await fetchWithCsrfRetry(input, opts || {});
        return result.response;
      }
      var prepared = await prepareRequest(input, opts);
      return nativeFetch(prepared[0], prepared[1]);
    };
  }

  // Pre-fetch at load time
  api.fetchCsrfToken();
})();
