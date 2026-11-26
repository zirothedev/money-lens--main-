/* Quick, friendly client-side checks. The server remains the authority on what is valid. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else { root.MoneyLens = root.MoneyLens || {}; root.MoneyLens.validation = factory(); }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var ALLOWED = ['pdf', 'csv'];

  function extensionOf(name) {
    var match = /\.([^.\\/]+)$/.exec(String(name || ''));
    return match ? match[1].toLowerCase() : '';
  }

  function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(bytes < 10240 ? 1 : 0) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  }

  /** @returns {{ok: true, type: string} | {ok: false, code: string}} */
  function validateFile(file, options) {
    if (!file) return { ok: false, code: 'missing_file' };
    if (file.size === 0) return { ok: false, code: 'empty_file' };
    var ext = extensionOf(file.name);
    if (ALLOWED.indexOf(ext) === -1) return { ok: false, code: 'unsupported_type' };
    if (options && options.maxBytes && file.size > options.maxBytes) return { ok: false, code: 'file_too_large' };
    return { ok: true, type: ext.toUpperCase() };
  }

  return { ALLOWED: ALLOWED, extensionOf: extensionOf, formatBytes: formatBytes, validateFile: validateFile };
});
