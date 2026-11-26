const test = require('node:test');
const assert = require('node:assert/strict');
const m = require('../../static/js/messages.js');

// Every error code the Django backend can send (statements/validators, processing, reports).
const BACKEND_CODES = ['missing_file', 'empty_file', 'file_too_large', 'unsupported_type', 'content_mismatch',
  'duplicate_upload', 'pdf_unreadable', 'pdf_encrypted', 'pdf_no_text', 'csv_unreadable', 'csv_no_header',
  'no_transactions', 'multiple_currencies', 'not_allowed', 'expired', 'internal_error'];
const CLIENT_CODES = ['session_expired', 'network_error', 'multiple_files'];

test('every backend and client error code has human wording', () => {
  for (const code of [...BACKEND_CODES, ...CLIENT_CODES]) {
    assert.ok(m.codes.includes(code), `missing wording for ${code}`);
    const { title, message } = m.describe(code, { maxLabel: '10 MB' });
    assert.ok(title.length > 3 && message.length > 10, code);
  }
});

test('messages never leak internals', () => {
  for (const code of m.codes) {
    const { title, message } = m.describe(code, {});
    assert.doesNotMatch(`${title} ${message}`, /traceback|exception|django|python|sqlite|stack|undefined|\{max\}|_/i, code);
  }
});

test('unreadable PDF message mentions selectable text (the spec example)', () => {
  assert.match(m.describe('pdf_no_text').message, /selectable text/);
});

test('too large message includes the limit when known, and no placeholder when not', () => {
  assert.match(m.describe('file_too_large', { maxLabel: '10 MB' }).message, /10 MB/);
  assert.doesNotMatch(m.describe('file_too_large', {}).message, /\{max\}/);
});

test('unknown codes fall back to a generic, safe message', () => {
  assert.equal(m.describe('something_new').title, m.describe('internal_error').title);
});

test('wording never suggests guessing the purpose of transactions', () => {
  for (const code of m.codes) assert.doesNotMatch(m.describe(code).message, /categor|lifestyle|why you spent/i);
});
