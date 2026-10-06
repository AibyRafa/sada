/**
 * SADA — "Paste a link" control on the audio step.
 * Downloads the clip behind the link and hands it to the same handler as a chosen
 * file, so validation, waveform, player and spectrogram need no special case.
 */

import { api } from './api.js';
import { SadaError, isAbortError } from './errors.js';
import { h, announce } from './ui.js';
import { t } from './i18n.js';

/**
 * @param {{form: HTMLFormElement, input: HTMLInputElement, submit: HTMLButtonElement,
 *          cancel: HTMLButtonElement, hint: HTMLElement,
 *          onFile: (file: File) => void, onError: (error: SadaError) => void, onClear: () => void,
 *          getToken: () => number, isBusy: () => boolean}} options
 *   getToken  changes whenever the chosen file changes; a download that finishes after that is discarded
 */
export function bindLinkInput({ form, input, submit, cancel, hint, onFile, onError, onClear, getToken, isBusy }) {
  hint.textContent = t(api.mode === 'live' ? 'link.hintLive' : 'link.hintMock');

  const idleLabel = Array.from(submit.childNodes).map((node) => node.cloneNode(true));
  let controller = null;

  function setLoading(on) {
    form.toggleAttribute('aria-busy', on);
    input.readOnly = on;
    // aria-disabled (not disabled) keeps keyboard focus on the button while it works.
    submit.setAttribute('aria-disabled', String(on));
    submit.replaceChildren(...(on ? [h('span', { class: 'spinner', 'aria-hidden': 'true' }), t('link.loading')] : idleLabel.map((node) => node.cloneNode(true))));
    cancel.hidden = !on;
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (controller || isBusy()) return;
    onClear();

    if (!input.value.trim()) {
      onError(new SadaError('invalid_link'));
      input.focus();
      return;
    }

    const token = getToken();
    controller = new AbortController();
    setLoading(true);
    announce(t('link.announceLoading'));
    try {
      const file = await api.fetchAudioFromLink(input.value, { signal: controller.signal });
      if (getToken() !== token) return; // another file was chosen or removed meanwhile
      input.value = '';
      onFile(file);
    } catch (error) {
      if (isAbortError(error)) {
        announce(t('link.cancelled'));
        return;
      }
      if (getToken() !== token) return;
      onError(error instanceof SadaError ? error : new SadaError('link_unreachable'));
      input.focus();
    } finally {
      controller = null;
      setLoading(false);
    }
  });

  cancel.addEventListener('click', () => controller?.abort());
}
