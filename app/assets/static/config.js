// Config page — save/start button state machine.
// Loaded as a deferred module-level script from config.html.
(function () {
  'use strict';

  const RESTART_LABEL  = 'Save and restart service';
  const START_LABEL    = 'Start service';
  const SAVING_LABEL   = 'Saving and restarting…';
  const STARTING_LABEL = 'Starting…';
  const POLL_DEADLINE_MS = 10000;
  const MIN_VISIBLE_MS   = 1500;
  const POLL_INTERVAL_MS = 1000;

  const form = document.getElementById('config-form');
  const btn  = document.getElementById('save-btn');
  if (!form || !btn) return;

  let busyStart = 0;
  let pollAbort = false;

  function idleLabel() {
    return btn.dataset.mode === 'start' ? START_LABEL : RESTART_LABEL;
  }
  function busyLabel() {
    return btn.dataset.mode === 'start' ? STARTING_LABEL : SAVING_LABEL;
  }

  function setBusy(state) {
    if (state) {
      btn.setAttribute('aria-busy', 'true');
      btn.disabled = true;
      btn.textContent = busyLabel();
    } else {
      btn.removeAttribute('aria-busy');
      // After a successful save the service should be running; switch to
      // restart mode and re-arm the dirty gate, unless this is the
      // no-detection legacy fallback (always enabled).
      btn.dataset.mode = 'restart';
      btn.textContent = idleLabel();
      if (btn.dataset.noDirtyGate === '1') {
        btn.disabled = false;
      } else {
        btn.disabled = true;
        armDirtyTracker();
      }
    }
  }

  function enableForDirty() { btn.disabled = false; }
  function armDirtyTracker() {
    if (btn.dataset.noDirtyGate === '1') return;
    form.addEventListener('input',  enableForDirty, { once: true });
    form.addEventListener('change', enableForDirty, { once: true });
  }
  armDirtyTracker();

  function renderToast(cls, msg) {
    const el = document.getElementById('toast');
    if (!el) return;
    el.className = 'toast ' + cls;
    el.textContent = msg;
  }

  function finishBusy() {
    pollAbort = true;
    const elapsed = Date.now() - busyStart;
    const wait = Math.max(0, MIN_VISIBLE_MS - elapsed);
    setTimeout(() => setBusy(false), wait);
  }

  form.addEventListener('htmx:beforeRequest', function () {
    busyStart = Date.now();
    pollAbort = false;
    setBusy(true);
  });

  form.addEventListener('htmx:afterRequest', function (evt) {
    const xhr = evt.detail && evt.detail.xhr;
    if (!xhr || xhr.status < 200 || xhr.status >= 300) {
      finishBusy();
      return;
    }
    pollStatusUntilSettled();
  });

  // Network-level failure (WebUI dropped, DNS, etc.). HTTP errors go
  // through afterRequest with the toast partial.
  form.addEventListener('htmx:sendError', function () {
    pollHealthzUntilBack();
  });

  function pollStatusUntilSettled() {
    const start = busyStart;
    function tick() {
      if (pollAbort) return;
      fetch('/status', { cache: 'no-store' })
        .then(r => r.ok ? r.json() : null)
        .then(s => {
          const elapsed = Date.now() - start;
          if (s && s.running === true) { finishBusy(); return; }
          if (s && s.method === 'none') { finishBusy(); return; }
          if (elapsed >= POLL_DEADLINE_MS) {
            renderToast('err',
              'Service status unknown after 10s — open the Logs page to investigate.');
            finishBusy();
            return;
          }
          setTimeout(tick, POLL_INTERVAL_MS);
        })
        .catch(() => {
          if (Date.now() - start >= POLL_DEADLINE_MS) { finishBusy(); return; }
          setTimeout(tick, POLL_INTERVAL_MS);
        });
    }
    tick();
  }

  function pollHealthzUntilBack() {
    renderToast('ok', 'Restart in progress, status unknown — checking…');
    const start = busyStart || Date.now();
    function tick() {
      if (pollAbort) return;
      fetch('/healthz', { cache: 'no-store' })
        .then(r => {
          if (r && r.ok) {
            renderToast('ok',
              'WebUI is back. Verify iSponsorBlockTV with: systemctl status iSponsorBlockTV');
            finishBusy();
            return;
          }
          schedule();
        })
        .catch(schedule);
    }
    function schedule() {
      if (Date.now() - start >= POLL_DEADLINE_MS) {
        renderToast('err',
          'Status unknown after 10s. Check: systemctl status iSponsorBlockTV');
        finishBusy();
        return;
      }
      setTimeout(tick, POLL_INTERVAL_MS);
    }
    tick();
  }
})();
