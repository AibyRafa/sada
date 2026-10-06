/**
 * SADA — Back-to-top button, shared by every page.
 *
 * A classic, self-contained script on purpose (no imports, inline icon, fixed Arabic label):
 * the landing page is static and also works when opened straight from disk (file://), where the
 * browser blocks module scripts and the external icon sprite. Appears once the page has been
 * scrolled past the first part of the screen.
 */
(function () {
  'use strict';

  var SHOW_AFTER_PX = 300;
  var LABEL = 'العودة إلى أعلى الصفحة';
  var SVG_NS = 'http://www.w3.org/2000/svg';

  function reducedMotion() {
    return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  function arrowIcon() {
    var svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('class', 'icon');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    svg.setAttribute('stroke-width', '1.75');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    ['M12 19V5', 'm5 12 7-7 7 7'].forEach(function (d) {
      var path = document.createElementNS(SVG_NS, 'path');
      path.setAttribute('d', d);
      svg.appendChild(path);
    });
    return svg;
  }

  function init() {
    if (document.querySelector('.to-top')) return;

    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'to-top';
    button.setAttribute('aria-label', LABEL);
    button.title = LABEL;
    button.appendChild(arrowIcon());
    button.addEventListener('click', function (event) {
      window.scrollTo({ top: 0, behavior: reducedMotion() ? 'auto' : 'smooth' });
      // Keyboard and screen-reader users: the button is about to hide, so put focus back at the page start.
      if (event.detail === 0) {
        var skip = document.querySelector('.skip-link');
        if (skip) skip.focus({ preventScroll: true });
      }
    });
    document.body.appendChild(button);

    var queued = false;
    function update() {
      queued = false;
      button.classList.toggle('is-visible', window.scrollY > SHOW_AFTER_PX);
    }
    function schedule() {
      if (queued) return;
      queued = true;
      window.requestAnimationFrame(update);
    }

    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule);
    update();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
