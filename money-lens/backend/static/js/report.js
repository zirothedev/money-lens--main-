/* Report dashboard: bar widths, expand/collapse, transaction search + filter + "show more". */
(function () {
  'use strict';
  var PAGE_SIZE = 25;

  /* ---- bars ---- */
  var fills = document.querySelectorAll('.bar__fill[data-percent]');
  requestAnimationFrame(function () {
    Array.prototype.forEach.call(fills, function (el) { el.style.width = el.dataset.percent + '%'; });
  });

  /* ---- expandable details (recipients + unidentified) ---- */
  function setExpanded(button, panel, expanded) {
    button.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    panel.hidden = !expanded;
    var label = button.querySelector('[data-toggle-label]');
    if (label) label.textContent = expanded ? 'Hide transactions' : 'View transactions';
  }
  function wire(button) {
    var panel = document.getElementById(button.getAttribute('aria-controls'));
    if (!panel) return;
    setExpanded(button, panel, false);   // collapsed only once JS is running (no-JS shows everything)
    button.addEventListener('click', function () {
      setExpanded(button, panel, button.getAttribute('aria-expanded') !== 'true');
    });
  }
  Array.prototype.forEach.call(document.querySelectorAll('[data-toggle], [data-toggle-unidentified]'), wire);

  /* ---- transactions ---- */
  var root = document.querySelector('[data-transactions]');
  if (!root) return;
  var rows = Array.prototype.slice.call(root.querySelectorAll('[data-tx-row]'));
  var searchInput = root.querySelector('[data-tx-search]');
  var filterButtons = root.querySelectorAll('[data-tx-filter]');
  var emptyMsg = root.querySelector('[data-tx-empty]');
  var moreBtn = root.querySelector('[data-tx-more]');
  var countEl = root.querySelector('[data-tx-count]');
  var tableWrap = root.querySelector('.table-wrap');
  var state = { query: '', direction: 'all', limit: PAGE_SIZE };

  function matches(row) {
    if (state.direction !== 'all' && row.dataset.direction !== state.direction) return false;
    return !state.query || row.dataset.search.indexOf(state.query) !== -1;
  }

  function render() {
    var matching = rows.filter(matches);
    rows.forEach(function (row) { row.hidden = true; });
    matching.slice(0, state.limit).forEach(function (row) { row.hidden = false; });
    var shown = Math.min(matching.length, state.limit);
    emptyMsg.hidden = matching.length > 0;
    tableWrap.hidden = matching.length === 0;
    moreBtn.hidden = matching.length <= state.limit;
    moreBtn.textContent = 'Show more (' + (matching.length - shown) + ' remaining)';
    countEl.textContent = matching.length
      ? 'Showing ' + shown + ' of ' + matching.length + ' transaction' + (matching.length === 1 ? '' : 's')
      : '';
  }

  searchInput.addEventListener('input', function () {
    state.query = searchInput.value.trim().toLowerCase();
    state.limit = PAGE_SIZE;
    render();
  });
  Array.prototype.forEach.call(filterButtons, function (btn) {
    btn.addEventListener('click', function () {
      state.direction = btn.dataset.txFilter;
      state.limit = PAGE_SIZE;
      Array.prototype.forEach.call(filterButtons, function (b) {
        var active = b === btn;
        b.classList.toggle('is-active', active);
        b.setAttribute('aria-pressed', active ? 'true' : 'false');
      });
      render();
    });
  });
  moreBtn.addEventListener('click', function () { state.limit += PAGE_SIZE; render(); });
  render();
})();
