const test = require('node:test');
const assert = require('node:assert/strict');
const { classify } = require('../../static/js/api.js');

test('success returns the body', () => {
  assert.deepEqual(classify({ status: 201, body: { id: 'abc' } }), { ok: true, data: { id: 'abc' } });
  assert.equal(classify({ status: 200, body: { report_id: 'r' } }).ok, true);
});

test('backend error codes pass through with the body', () => {
  const r = classify({ status: 422, body: { error: 'no_transactions', message: 'x' } });
  assert.equal(r.ok, false);
  assert.equal(r.code, 'no_transactions');
  assert.equal(r.status, 422);
});

test('413 and 400 upload errors keep their codes', () => {
  assert.equal(classify({ status: 413, body: { error: 'file_too_large' } }).code, 'file_too_large');
  assert.equal(classify({ status: 400, body: { error: 'unsupported_type' } }).code, 'unsupported_type');
});

test('duplicate upload keeps the existing job so the flow can continue', () => {
  const r = classify({ status: 409, body: { error: 'duplicate_upload', job: { id: 'job1' } } });
  assert.equal(r.code, 'duplicate_upload');
  assert.equal(r.data.job.id, 'job1');
});

test('redirect to login, 401 and 403 all mean the session expired', () => {
  assert.equal(classify({ status: 200, body: null, redirectedToLogin: true }).code, 'session_expired');
  assert.equal(classify({ status: 401, body: null }).code, 'session_expired');
  assert.equal(classify({ status: 403, body: null }).code, 'session_expired');
});

test('network failure', () => {
  assert.equal(classify({ networkError: true }).code, 'network_error');
});

test('non-JSON or unexpected responses become a safe internal error', () => {
  assert.equal(classify({ status: 500, body: null }).code, 'internal_error');
  assert.equal(classify({ status: 200, body: null }).code, 'internal_error');
  assert.equal(classify({ status: 502, body: 'Bad gateway' }).code, 'internal_error');
});
