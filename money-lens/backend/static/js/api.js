/* Talks to the existing Django endpoints. Never invents new ones. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else { root.MoneyLens = root.MoneyLens || {}; root.MoneyLens.api = factory(root); }
})(typeof self !== 'undefined' ? self : this, function (root) {
  'use strict';

  /**
   * Turn a raw response description into {ok, data} or {ok:false, code, data}.
   * Pure function so it can be tested without a browser.
   */
  function classify(res) {
    if (res.networkError) return { ok: false, code: 'network_error' };
    if (res.redirectedToLogin || res.status === 401 || res.status === 403) return { ok: false, code: 'session_expired' };
    var body = res.body && typeof res.body === 'object' ? res.body : null;
    if (res.status >= 200 && res.status < 300 && body) return { ok: true, data: body };
    if (body && body.error) return { ok: false, code: String(body.error), data: body, status: res.status };
    return { ok: false, code: 'internal_error', status: res.status };
  }

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;
    var m = /(?:^|;\s*)csrftoken=([^;]+)/.exec(document.cookie);
    return m ? decodeURIComponent(m[1]) : '';
  }

  function send(url, options, loginUrl) {
    var headers = { 'X-CSRFToken': csrfToken(), 'Accept': 'application/json' };
    return fetch(url, Object.assign({ method: 'POST', credentials: 'same-origin', headers: headers }, options))
      .then(function (response) {
        var redirectedToLogin = response.redirected && loginUrl && new URL(response.url).pathname.indexOf(loginUrl) === 0;
        var type = response.headers.get('content-type') || '';
        var parse = type.indexOf('application/json') !== -1 ? response.json().catch(function () { return null; }) : Promise.resolve(null);
        return parse.then(function (body) {
          return classify({ status: response.status, body: body, redirectedToLogin: redirectedToLogin });
        });
      })
      .catch(function () { return classify({ networkError: true }); });
  }

  function uploadStatement(url, file, loginUrl) {
    var form = new FormData();
    form.append('statement', file);
    return send(url, { body: form }, loginUrl);
  }

  function processStatement(url, loginUrl) {
    return send(url, {}, loginUrl);
  }

  return { classify: classify, uploadStatement: uploadStatement, processStatement: processStatement };
});
