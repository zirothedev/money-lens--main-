const test = require('node:test');
const assert = require('node:assert/strict');
const v = require('../../static/js/validation.js');

const file = (name, size) => ({ name, size });
const MAX = 10 * 1024 * 1024;

test('accepts a PDF and a CSV, reports the type', () => {
  assert.deepEqual(v.validateFile(file('September_2026.pdf', 2400000), { maxBytes: MAX }), { ok: true, type: 'PDF' });
  assert.deepEqual(v.validateFile(file('statement.csv', 1200), { maxBytes: MAX }), { ok: true, type: 'CSV' });
});

test('extension check is case-insensitive and uses the last dot', () => {
  assert.equal(v.validateFile(file('STATEMENT.PDF', 10), {}).ok, true);
  assert.equal(v.validateFile(file('my.statement.v2.csv', 10), {}).ok, true);
  assert.equal(v.validateFile(file('statement.pdf.exe', 10), {}).code, 'unsupported_type');
});

test('rejects unsupported types', () => {
  for (const n of ['notes.txt', 'photo.png', 'sheet.xlsx', 'noextension', '.pdf.', '']) {
    assert.deepEqual(v.validateFile(file(n, 10), {}), { ok: false, code: 'unsupported_type' }, n);
  }
});

test('rejects missing and empty files', () => {
  assert.equal(v.validateFile(null, {}).code, 'missing_file');
  assert.equal(v.validateFile(file('a.pdf', 0), {}).code, 'empty_file');
});

test('rejects files over the limit but allows exactly the limit', () => {
  assert.equal(v.validateFile(file('a.csv', MAX + 1), { maxBytes: MAX }).code, 'file_too_large');
  assert.equal(v.validateFile(file('a.csv', MAX), { maxBytes: MAX }).ok, true);
});

test('formatBytes', () => {
  assert.equal(v.formatBytes(500), '500 B');
  assert.equal(v.formatBytes(2048), '2.0 KB');
  assert.equal(v.formatBytes(150 * 1024), '150 KB');
  assert.equal(v.formatBytes(2.4 * 1024 * 1024), '2.4 MB');
});
