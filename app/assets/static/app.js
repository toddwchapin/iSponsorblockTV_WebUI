// Global UI behaviors. Loaded on every page via base.html.
(function () {
  'use strict';

  /**
   * Status-badge announcer (audit §3 + §6).
   *
   * The badge polls /status/badge every 5s and swaps via outerHTML. With
   * aria-live on the wrapper, screen readers re-announce "Running" every
   * 5 seconds — noisy. So the wrapper is aria-live="off" and we route
   * meaningful transitions to a hidden aria-live announcer instead.
   */
  let lastBadgeText = null;

  document.addEventListener('htmx:afterSwap', function (evt) {
    const target = evt.detail && evt.detail.target;
    if (!target || target.id !== 'status-badge') return;

    const text = (target.textContent || '').trim();
    const announcer = document.getElementById('status-announcer');
    if (!announcer) {
      lastBadgeText = text;
      return;
    }
    if (lastBadgeText !== null && text !== lastBadgeText) {
      announcer.textContent = 'Service status: ' + text;
    }
    lastBadgeText = text;
  });
})();
