/* Accessible modal: focus trap, Escape, backdrop click, scroll lock, focus restore. */
(function (root) {
  'use strict';
  root.MoneyLens = root.MoneyLens || {};

  var FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])';

  function createModal(modalEl) {
    var panel = modalEl.querySelector('[role="dialog"]');
    var backdrop = modalEl.querySelector('[data-modal-backdrop]');
    var opener = null;
    var locked = false;     // true while processing: the request can't be cancelled safely
    var onClose = null;

    function visibleFocusables() {
      return Array.prototype.filter.call(panel.querySelectorAll(FOCUSABLE), function (el) {
        return el.offsetParent !== null || el === document.activeElement;
      });
    }

    function onKeydown(event) {
      if (event.key === 'Escape' && !locked) { event.stopPropagation(); close(); return; }
      if (event.key !== 'Tab') return;
      var items = visibleFocusables();
      if (!items.length) { event.preventDefault(); panel.focus(); return; }
      var first = items[0], last = items[items.length - 1];
      if (event.shiftKey && (document.activeElement === first || document.activeElement === panel)) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }

    function open(trigger) {
      opener = trigger || document.activeElement;
      modalEl.hidden = false;
      document.documentElement.classList.add('is-modal-open');
      document.addEventListener('keydown', onKeydown, true);
      panel.focus();
    }

    function close() {
      if (locked || modalEl.hidden) return;
      modalEl.hidden = true;
      document.documentElement.classList.remove('is-modal-open');
      document.removeEventListener('keydown', onKeydown, true);
      if (opener && typeof opener.focus === 'function') opener.focus();
      if (onClose) onClose();
    }

    backdrop.addEventListener('click', function () { close(); });
    modalEl.addEventListener('click', function (event) {
      if (event.target.closest('[data-modal-close]')) close();
    });

    return {
      open: open,
      close: close,
      lock: function (value) { locked = !!value; var btn = modalEl.querySelector('.modal__close'); if (btn) btn.hidden = locked; },
      isOpen: function () { return !modalEl.hidden; },
      onClose: function (fn) { onClose = fn; }
    };
  }

  root.MoneyLens.createModal = createModal;
})(typeof self !== 'undefined' ? self : this);
