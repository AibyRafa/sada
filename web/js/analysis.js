/**
 * SADA — Analysis progress view.
 * Shows the real pipeline stages (from the proposal's workflow). In mock mode
 * the timing is simulated and labelled; in live mode only the upload progress
 * is measured and server stages are shown as running on the server.
 */

import { t } from './i18n.js';
import { h, icon, formatDuration } from './ui.js';

export function createAnalysisView({ list, elapsed, note }) {
  const items = new Map();
  let timer = 0;
  let startedAt = 0;

  function render(stageIds, mode) {
    items.clear();
    list.replaceChildren(
      ...stageIds.map((id) => {
        const copy = t(`stages.${id}`);
        const state = h('span', { class: 'stage__state', text: t('stageState.pending') });
        const item = h(
          'li',
          { class: 'stage', dataset: { state: 'pending', stage: id } },
          h('span', { class: 'stage__marker' }, icon('check')),
          h(
            'div',
            { class: 'stage__body' },
            h('p', { class: 'stage__title', text: copy.title }),
            h('p', { class: 'stage__detail', text: copy.detail }),
          ),
          state,
        );
        items.set(id, { item, state });
        return item;
      }),
    );
    note.replaceChildren(icon('info'), h('span', { text: t(mode === 'mock' ? 'processing.noteMock' : 'processing.noteLive') }));
  }

  /** state: pending | active | server | done; label overrides the state text (e.g. "42%"). */
  function set(id, state, label) {
    const entry = items.get(id);
    if (!entry) return;
    entry.item.dataset.state = state;
    if (state === 'active' || state === 'server') entry.item.setAttribute('aria-current', 'step');
    else entry.item.removeAttribute('aria-current');
    entry.state.textContent = label ?? t(`stageState.${state}`);
  }

  function completeAll() {
    items.forEach((_, id) => set(id, 'done'));
  }

  function tick() {
    elapsed.textContent = formatDuration((performance.now() - startedAt) / 1000);
  }

  function startTimer() {
    stopTimer();
    startedAt = performance.now();
    tick();
    timer = window.setInterval(tick, 500);
  }

  function stopTimer() {
    window.clearInterval(timer);
    timer = 0;
  }

  return { render, set, completeAll, startTimer, stopTimer };
}
