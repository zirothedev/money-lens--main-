/* Upload flow: choose file -> upload -> process -> ready/error.
   Uses the existing synchronous backend:  POST upload/  ->  POST <job>/process/  ->  report id. */
(function () {
  'use strict';
  var ML = window.MoneyLens;
  var modalEl = document.getElementById('upload-modal');
  if (!modalEl || !ML || !ML.createModal) return;

  var panel = modalEl.querySelector('[role="dialog"]');
  var cfg = {
    uploadUrl: panel.dataset.uploadUrl,
    processUrl: panel.dataset.processUrl,
    reportUrl: panel.dataset.reportUrl,
    loginUrl: panel.dataset.loginUrl,
    maxBytes: parseInt(panel.dataset.maxBytes, 10) || 0,
    maxLabel: panel.dataset.maxLabel || ''
  };
  var ZERO_UUID = '00000000-0000-0000-0000-000000000000';
  var STEP_INTERVAL_MS = 1100;   // pacing of the checklist while the server works
  var STEP_FINISH_MS = 140;      // quick catch-up once the server has answered
  var REDIRECT_DELAY_MS = 2200;

  var modal = ML.createModal(modalEl);
  var states = {};
  Array.prototype.forEach.call(modalEl.querySelectorAll('[data-state]'), function (el) { states[el.dataset.state] = el; });
  var q = function (sel) { return modalEl.querySelector(sel); };

  var input = q('[data-file-input]');
  var dropzone = q('[data-dropzone]');
  var fileCard = q('[data-file-card]');
  var fileError = q('[data-file-error]');
  var analyze = q('[data-analyze]');
  var steps = Array.prototype.slice.call(modalEl.querySelectorAll('[data-step]'));
  var announcer = q('[data-progress-announcer]');

  var selectedFile = null;
  var busy = false;
  var redirectTimer = null;
  var stepTimer = null;

  /* ---------- state handling ---------- */
  function show(name) {
    Object.keys(states).forEach(function (key) { states[key].hidden = key !== name; });
    modal.lock(name === 'processing');
  }

  function focusIn(el) { if (el) { el.setAttribute('tabindex', '-1'); el.focus(); } }

  function resetSelection() {
    selectedFile = null;
    input.value = '';
    fileCard.hidden = true;
    analyze.disabled = true;
    clearFileError();
  }

  function showFileError(code) {
    var info = ML.messages.describe(code, { maxLabel: cfg.maxLabel });
    fileError.textContent = info.title + '. ' + info.message;
    fileError.hidden = false;
  }
  function clearFileError() { fileError.hidden = true; fileError.textContent = ''; }

  /* ---------- file selection ---------- */
  function chooseFile(file) {
    clearFileError();
    var result = ML.validation.validateFile(file, { maxBytes: cfg.maxBytes });
    if (!result.ok) {
      selectedFile = null; fileCard.hidden = true; analyze.disabled = true; input.value = '';
      showFileError(result.code);
      return;
    }
    selectedFile = file;
    q('[data-file-name]').textContent = file.name;
    q('[data-file-name]').title = file.name;
    q('[data-file-size]').textContent = ML.validation.formatBytes(file.size);
    q('[data-file-type]').textContent = result.type;
    fileCard.hidden = false;
    analyze.disabled = false;
  }

  input.addEventListener('change', function () { chooseFile(input.files && input.files[0]); });
  q('[data-file-remove]').addEventListener('click', function () { resetSelection(); input.focus(); });

  ['dragenter', 'dragover'].forEach(function (type) {
    dropzone.addEventListener(type, function (e) { e.preventDefault(); dropzone.classList.add('is-dragover'); });
  });
  ['dragleave', 'drop'].forEach(function (type) {
    dropzone.addEventListener(type, function (e) { e.preventDefault(); dropzone.classList.remove('is-dragover'); });
  });
  dropzone.addEventListener('drop', function (e) {
    var files = e.dataTransfer && e.dataTransfer.files;
    if (!files || !files.length) return;
    if (files.length > 1) { resetSelection(); showFileError('multiple_files'); return; }
    chooseFile(files[0]);
  });
  // Dropping outside the zone should not make the browser navigate to the file.
  ['dragover', 'drop'].forEach(function (type) {
    modalEl.addEventListener(type, function (e) { if (!dropzone.contains(e.target)) e.preventDefault(); });
  });

  /* ---------- processing checklist ---------- */
  function setStep(index) {
    steps.forEach(function (step, i) {
      step.classList.toggle('is-done', i < index);
      step.classList.toggle('is-current', i === index);
    });
    if (announcer && steps[index]) announcer.textContent = steps[index].textContent.trim();
  }

  function startPacing(fromIndex) {
    var current = fromIndex;
    setStep(current);
    // Keep the last step ("Preparing your report") current until the server really answers.
    stepTimer = setInterval(function () {
      if (current < steps.length - 2) { current += 1; setStep(current); }
    }, STEP_INTERVAL_MS);
    return function () { return current; };
  }

  function finishSteps(done) {
    clearInterval(stepTimer);
    var index = steps.findIndex(function (s) { return s.classList.contains('is-current'); });
    if (index < 0) index = 0;
    (function next() {
      index += 1;
      steps.forEach(function (step, i) { step.classList.toggle('is-done', i < index); step.classList.toggle('is-current', i === index && i < steps.length); });
      if (index < steps.length) setTimeout(next, STEP_FINISH_MS); else setTimeout(done, 350);
    })();
  }

  /* ---------- the flow ---------- */
  function start() {
    if (busy || !selectedFile) return;
    busy = true;
    analyze.disabled = true;
    show('processing');
    setStep(0);
    var processingTitle = q('#processing-title');

    ML.api.uploadStatement(cfg.uploadUrl, selectedFile, cfg.loginUrl).then(function (res) {
      if (res.ok) return res.data.id;
      if (res.code === 'duplicate_upload' && res.data && res.data.job) return res.data.job.id; // continue the job already waiting
      throw res;
    }).then(function (jobId) {
      startPacing(1);   // step 1 ("Reading your statement") is really done: the file has arrived
      return ML.api.processStatement(cfg.processUrl.replace(ZERO_UUID, jobId), cfg.loginUrl);
    }).then(function (res) {
      if (!res.ok) throw res;
      var url = cfg.reportUrl.replace(ZERO_UUID, res.data.report_id);
      finishSteps(function () { showReady(url); });
    }).catch(function (res) {
      clearInterval(stepTimer);
      busy = false;
      handleFailure(res && res.code ? res.code : 'internal_error', res);
    });
    if (processingTitle) processingTitle.focus && processingTitle.setAttribute('tabindex', '-1');
  }

  function showReady(url) {
    busy = false;
    show('ready');
    var link = q('[data-view-report]');
    link.href = url;
    focusIn(q('[data-ready-title]'));
    redirectTimer = setTimeout(function () { window.location.assign(url); }, REDIRECT_DELAY_MS);
  }

  function handleFailure(code, res) {
    var stage = res && res.stage;
    var info = ML.messages.describe(code, { maxLabel: cfg.maxLabel });
    // Problems with the file itself go back to the chooser with an inline message.
    var inlineCodes = ['missing_file', 'empty_file', 'file_too_large', 'unsupported_type', 'content_mismatch', 'network_error'];
    if (inlineCodes.indexOf(code) !== -1) {
      show('select');
      if (code === 'network_error') { analyze.disabled = !selectedFile; } else { resetSelection(); }
      showFileError(code);
      return;
    }
    q('[data-error-title]').textContent = info.title;
    q('[data-error-message]').textContent = info.message;
    var session = code === 'session_expired';
    q('[data-error-login]').hidden = !session;
    q('[data-error-retry]').hidden = session;
    show('error');
    focusIn(q('[data-error-title]'));
  }

  analyze.addEventListener('click', start);
  q('[data-error-retry]').addEventListener('click', function () {
    resetSelection(); show('select'); input.focus();
  });

  /* ---------- opening / closing ---------- */
  function openModal(trigger) {
    clearTimeout(redirectTimer);
    resetSelection();
    show('select');
    modal.open(trigger);
  }
  modal.onClose(function () { clearTimeout(redirectTimer); });

  Array.prototype.forEach.call(document.querySelectorAll('[data-open-upload]'), function (btn) {
    btn.addEventListener('click', function () { openModal(btn); });
  });

  // "New statement" / "Upload Statement" links elsewhere point at /?upload=1
  var params = new URLSearchParams(window.location.search);
  if (params.get('upload') === '1') {
    params.delete('upload');
    var clean = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
    window.history.replaceState({}, '', clean);
    openModal(document.querySelector('[data-open-upload]'));
  }
})();
