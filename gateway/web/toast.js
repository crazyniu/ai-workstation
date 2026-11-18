'use strict';

const toast = (() => {
  document.body.insertAdjacentHTML('beforeend', `<div id="desktop-toast" class="desktop-toast" popover="manual" hidden>
    <svg class="toast-icon" viewBox="0 0 24 24" aria-hidden="true"><path class="toast-success" d="m5 12 4 4L19 6"/><g class="toast-error"><circle cx="12" cy="12" r="9"/><path d="M12 7v6m0 4h.01"/></g></svg>
    <p id="toast-message" class="toast-message" role="status" aria-live="polite" aria-atomic="true"></p>
    <button type="button" id="toast-close" class="toast-close" aria-label="关闭提示"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 7 10 10M17 7 7 17"/></svg></button>
  </div>`);
  const panel = document.getElementById('desktop-toast');
  const text = document.getElementById('toast-message');
  let timer, remaining, started;

  function close() {
    clearTimeout(timer);
    timer = null;
    panel.hidePopover?.();
    panel.hidden = true;
  }

  function syncLayer() {
    if (panel.hidden) return;
    const parent = document.activeElement?.closest('dialog:modal')
      || [...document.querySelectorAll('dialog:modal')].at(-1) || document.body;
    if (panel.parentElement !== parent) {
      panel.hidePopover?.();
      parent.append(panel);
    }
    if (panel.showPopover && !panel.matches(':popover-open')) panel.showPopover();
  }

  function resume() {
    clearTimeout(timer);
    timer = null;
    if (panel.hidden || panel.matches(':hover') || panel.contains(document.activeElement)) return;
    started = performance.now();
    timer = setTimeout(close, remaining);
  }

  function pause() {
    if (timer == null) return;
    clearTimeout(timer);
    timer = null;
    remaining = Math.max(0, remaining - (performance.now() - started));
  }

  document.getElementById('toast-close').onclick = close;
  panel.addEventListener('mouseenter', pause);
  panel.addEventListener('mouseleave', resume);
  panel.addEventListener('focusin', pause);
  panel.addEventListener('focusout', () => queueMicrotask(resume));
  panel.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.stopPropagation(); close(); }
  });
  new MutationObserver(syncLayer).observe(document.body, {subtree: true, attributes: true, attributeFilter: ['open']});

  return (message, error = false) => {
    if (!message) return;
    panel.classList.toggle('error', error);
    text.setAttribute('role', error ? 'alert' : 'status');
    text.setAttribute('aria-live', error ? 'assertive' : 'polite');
    panel.hidden = false;
    syncLayer();
    text.textContent = message;
    remaining = Math.max(error ? 8000 : 4200, Math.min(12000, message.length * 160));
    resume();
  };
})();
