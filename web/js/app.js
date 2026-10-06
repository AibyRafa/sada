/**
 * SADA — Verification page controller (verify.html).
 * Flow: upload → attributed speaker → pre-check → analysis → result | error.
 */

import { CONFIG } from './config.js';
import { t, tPlural } from './i18n.js';
import { api } from './api.js';
import { SadaError, isAbortError } from './errors.js';
import { STATUS, ANALYSIS_STAGES, getState, setState, subscribe, setupStatus } from './state.js';
import { createAudioSession, createPlayer, computeEnvelope, drawWaveform } from './audio.js';
import { createAnalysisView } from './analysis.js';
import { bindLinkInput } from './link-input.js';
import { renderResult } from './result.js';
import {
  h,
  icon,
  ltr,
  announce,
  errorAlertContent,
  errorCopy,
  formatBytes,
  formatDuration,
  formatDurationHuman,
  supportedFormatsLabel,
  prefersReducedMotion,
  wait,
  observeResize,
} from './ui.js';

const byId = (id) => document.getElementById(id);

const dom = {
  stepper: byId('stepper'),
  stepAudio: byId('step-audio'),
  stepSpeaker: byId('step-speaker'),
  dropzone: byId('dropzone'),
  fileInput: byId('file-input'),
  dropzoneHint: byId('dropzone-hint'),
  fileLoading: byId('file-loading'),
  fileError: byId('file-error'),
  linkForm: byId('link-form'),
  linkInput: byId('link-input'),
  linkSubmit: byId('link-submit'),
  linkCancel: byId('link-cancel'),
  linkHint: byId('link-hint'),
  fileCard: byId('file-card'),
  fileName: byId('file-name'),
  fileDetails: byId('file-details'),
  fileReplace: byId('file-replace'),
  fileRemove: byId('file-remove'),
  waveform: byId('waveform-canvas'),
  waveformFallback: byId('waveform-fallback'),
  setupPlayer: byId('setup-player'),
  speakerList: byId('speaker-list'),
  speakerError: byId('speaker-error'),
  speakerNote: byId('speaker-note'),
  sumFile: byId('sum-file'),
  sumSpeaker: byId('sum-speaker'),
  sumDuration: byId('sum-duration'),
  analyzeBtn: byId('analyze-btn'),
  analyzeHint: byId('analyze-hint'),
  privacyMode: byId('privacy-mode-note'),
  stageList: byId('stage-list'),
  elapsed: byId('elapsed'),
  processingNote: byId('processing-note'),
  processingFile: byId('processing-file'),
  processingSpeaker: byId('processing-speaker'),
  cancelBtn: byId('cancel-btn'),
  resultRoot: byId('result-root'),
  errorTitle: byId('error-title'),
  errorDetail: byId('error-detail'),
  errorWhy: byId('error-why'),
  errorNext: byId('error-next'),
  errorActions: byId('error-actions'),
  audio: byId('sada-audio'),
  demoSlot: byId('demo-slot'),
};

const session = createAudioSession(dom.audio);
const analysisView = createAnalysisView({ list: dom.stageList, elapsed: dom.elapsed, note: dom.processingNote });

let speakers = [];
let loadToken = 0;
let abortController = null;
let envelope = null;
let setupPlayer = null;

init();

function init() {
  document.documentElement.dataset.apiMode = api.mode;

  const { limits, formats } = CONFIG;
  dom.fileInput.accept = [...formats.supported.map((ext) => `.${ext}`), 'audio/*', 'video/*'].join(',');
  dom.dropzoneHint.textContent = t('upload.hint', {
    formats: supportedFormatsLabel(),
    maxSize: formatBytes(limits.maxFileBytes),
    minDuration: formatDurationHuman(limits.minDurationSec),
    maxDuration: formatDurationHuman(limits.maxDurationSec),
  });
  if (api.mode === 'mock') {
    dom.privacyMode.textContent = t('precheck.privacyMock');
    dom.privacyMode.hidden = false;
  }

  bindUpload();
  bindLinkInput({
    form: dom.linkForm,
    input: dom.linkInput,
    submit: dom.linkSubmit,
    cancel: dom.linkCancel,
    hint: dom.linkHint,
    onFile: (file) => handleFiles([file]),
    onError: (error) => showAlert(dom.fileError, error),
    onClear: () => hideAlert(dom.fileError),
    getToken: () => loadToken,
    isBusy: () => getState().status === STATUS.PROCESSING,
  });
  dom.analyzeBtn.addEventListener('click', runAnalysis);
  dom.cancelBtn.addEventListener('click', () => abortController?.abort());
  initDemoControls();

  setupPlayer = createPlayer(dom.setupPlayer, dom.audio, session);
  session.onFrame(redrawWaveform);
  observeResize(dom.waveform, redrawWaveform);

  // Release the clip when leaving the page; reset cleanly if restored from the back/forward cache.
  window.addEventListener('pagehide', () => {
    abortController?.abort();
    session.clear();
  });
  window.addEventListener('pageshow', (event) => {
    if (!event.persisted) return;
    dom.resultRoot.cleanup?.();
    dom.resultRoot.replaceChildren();
    removeFile({ focus: false, quiet: true });
    showView('setup');
  });

  subscribe(render);
  render(getState());
  loadSpeakers();
}

/* ---- Rendering of the setup state ---------------------------------------- */

function render(state) {
  renderStepper(state);
  renderPrecheck(state);
  dom.stepAudio.classList.toggle('is-complete', Boolean(state.file));
  dom.stepSpeaker.classList.toggle('is-complete', Boolean(state.speaker));
}

function renderStepper(state) {
  const hasFile = Boolean(state.file);
  const hasSpeaker = Boolean(state.speaker);
  let current = 3;
  if (state.status === STATUS.COMPLETED) current = 4;
  else if (state.status !== STATUS.PROCESSING && state.status !== STATUS.ERROR) {
    if (!hasFile) current = 1;
    else if (!hasSpeaker) current = 2;
  }
  const complete = { 1: hasFile, 2: hasSpeaker, 3: state.status === STATUS.COMPLETED, 4: false };

  dom.stepper.querySelectorAll('[data-step]').forEach((item) => {
    const step = Number(item.dataset.step);
    const name = step === current ? 'current' : complete[step] ? 'complete' : 'upcoming';
    item.dataset.state = name;
    if (name === 'current') item.setAttribute('aria-current', 'step');
    else item.removeAttribute('aria-current');
    const status = item.querySelector('.stepper__status');
    if (status) status.textContent = name === 'upcoming' ? '' : t(`stepper.${name}`);
  });
}

function setSummary(el, value, emptyText) {
  const text = value ?? emptyText;
  if (el.textContent !== text) el.textContent = text;
  el.classList.toggle('is-empty', value == null);
}

function renderPrecheck(state) {
  setSummary(dom.sumFile, state.fileMeta?.name ?? null, t('precheck.noFile'));
  setSummary(dom.sumSpeaker, state.speaker?.name ?? null, t('precheck.noSpeaker'));
  setSummary(dom.sumDuration, state.fileMeta ? formatDuration(state.fileMeta.duration) : null, '—');
  if (state.fileMeta) dom.sumFile.title = state.fileMeta.name;
  else dom.sumFile.removeAttribute('title');

  dom.analyzeBtn.disabled = !(state.file && state.speaker) || state.status === STATUS.PROCESSING;

  let hint = 'precheck.hintReady';
  if (!state.file && !state.speaker) hint = 'precheck.hintNone';
  else if (!state.file) hint = 'precheck.hintNoFile';
  else if (!state.speaker) hint = 'precheck.hintNoSpeaker';
  const text = t(hint);
  if (dom.analyzeHint.textContent !== text) dom.analyzeHint.textContent = text;
}

function showView(name, focusTarget) {
  document.querySelectorAll('[data-view]').forEach((view) => {
    view.hidden = view.dataset.view !== name;
  });
  window.scrollTo({ top: 0, behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
  const target = typeof focusTarget === 'string' ? byId(focusTarget) : focusTarget;
  target?.focus({ preventScroll: true });
}

/* ---- Alerts -------------------------------------------------------------- */

function showAlert(container, error, actions = []) {
  container.replaceChildren(...errorAlertContent(error, actions).filter(Boolean));
  container.hidden = false;
  const copy = errorCopy(error);
  announce(`${copy.title}. ${copy.detail ?? ''}`);
}

function hideAlert(container) {
  container.hidden = true;
  container.replaceChildren();
}

/* ---- Step 1: audio file -------------------------------------------------- */

function bindUpload() {
  dom.fileInput.addEventListener('change', () => {
    if (dom.fileInput.files?.length) handleFiles(dom.fileInput.files);
    dom.fileInput.value = '';
  });

  const hasFiles = (event) => Array.from(event.dataTransfer?.types ?? []).includes('Files');
  let dragDepth = 0;
  const setDragging = (on) => {
    dom.dropzone.classList.toggle('is-dragover', on);
    dom.stepAudio.classList.toggle('is-dragover', on);
  };

  dom.stepAudio.addEventListener('dragenter', (event) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    dragDepth += 1;
    setDragging(true);
  });
  dom.stepAudio.addEventListener('dragover', (event) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
  });
  dom.stepAudio.addEventListener('dragleave', () => {
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) setDragging(false);
  });
  dom.stepAudio.addEventListener('drop', (event) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    dragDepth = 0;
    setDragging(false);
    handleFiles(event.dataTransfer.files);
  });
  // Files dropped elsewhere must not navigate away from the page.
  window.addEventListener('dragover', (event) => event.preventDefault());
  window.addEventListener('drop', (event) => event.preventDefault());

  dom.fileReplace.addEventListener('click', () => dom.fileInput.click());
  dom.fileRemove.addEventListener('click', () => removeFile());
  dom.waveform.addEventListener('click', (event) => {
    const rect = dom.waveform.getBoundingClientRect();
    const duration = session.duration;
    if (Number.isFinite(duration) && rect.width) session.seek(((event.clientX - rect.left) / rect.width) * duration);
  });
}

async function handleFiles(fileList) {
  const file = fileList[0];
  if (!file || getState().status === STATUS.PROCESSING) return;
  if (fileList.length > 1) announce(t('upload.multiple'));

  const token = ++loadToken;
  hideAlert(dom.fileError);
  dom.fileLoading.hidden = false;
  dom.stepAudio.setAttribute('aria-busy', 'true');

  try {
    const meta = await session.load(file);
    if (token !== loadToken) return;
    envelope = session.decoded ? computeEnvelope(session.decoded.samples) : null;
    setState({
      file,
      fileMeta: meta,
      result: null,
      error: null,
      status: setupStatus({ file, speaker: getState().speaker }),
    });
    showFileCard(meta);
    announce(t('upload.selected', { name: meta.name, duration: formatDuration(meta.duration) }));
  } catch (error) {
    if (token !== loadToken) return;
    showAlert(dom.fileError, error instanceof SadaError ? error : new SadaError('invalid_file', { name: file.name }));
  } finally {
    if (token === loadToken) {
      dom.fileLoading.hidden = true;
      dom.stepAudio.removeAttribute('aria-busy');
    }
  }
}

function showFileCard(meta) {
  dom.fileName.textContent = meta.name;
  dom.fileName.title = meta.name;
  // Each part is direction-isolated so Latin format names and times keep their order in RTL.
  dom.fileDetails.replaceChildren(
    ltr(meta.ext.toUpperCase()),
    ' · ',
    h('bdi', { text: formatBytes(meta.size) }),
    ' · ',
    ltr(formatDuration(meta.duration)),
  );
  dom.dropzone.hidden = true;
  dom.fileCard.hidden = false;
  dom.waveform.hidden = !envelope;
  dom.waveformFallback.hidden = Boolean(envelope);
  setupPlayer.sync();
  requestAnimationFrame(redrawWaveform);
}

function redrawWaveform() {
  if (!envelope || dom.waveform.hidden || dom.waveform.offsetParent === null) return;
  const duration = session.duration;
  const progress = Number.isFinite(duration) && duration > 0 ? dom.audio.currentTime / duration : 0;
  drawWaveform(dom.waveform, envelope, progress);
}

function removeFile({ focus = true, quiet = false } = {}) {
  loadToken += 1;
  session.clear();
  envelope = null;
  hideAlert(dom.fileError);
  dom.fileCard.hidden = true;
  dom.fileLoading.hidden = true;
  dom.dropzone.hidden = false;
  setState({
    file: null,
    fileMeta: null,
    result: null,
    error: null,
    status: setupStatus({ file: null, speaker: getState().speaker }),
  });
  if (focus) dom.fileInput.focus();
  if (!quiet) announce(t('upload.removed'));
}

/* ---- Step 2: attributed speaker ------------------------------------------ */

async function loadSpeakers() {
  hideAlert(dom.speakerError);
  dom.speakerList.setAttribute('aria-busy', 'true');
  dom.speakerList.replaceChildren(
    ...Array.from({ length: 3 }, () => h('div', { class: 'skeleton', 'aria-hidden': 'true' })),
    h('span', { class: 'visually-hidden', text: t('speakers.loading') }),
  );

  try {
    speakers = await api.getSpeakers();
    renderSpeakers();
    applySpeakerPrefill();
  } catch (error) {
    console.error('[SADA] could not load speakers', error);
    dom.speakerList.replaceChildren();
    const retry = h(
      'button',
      { type: 'button', class: 'btn btn--secondary btn--sm', onClick: loadSpeakers },
      icon('replace'),
      t('speakers.retry'),
    );
    showAlert(dom.speakerError, new SadaError('speakers_unavailable'), [retry]);
  } finally {
    dom.speakerList.setAttribute('aria-busy', 'false');
  }
}

function renderSpeakers() {
  const selectedId = getState().speaker?.id;
  dom.speakerList.replaceChildren(
    ...speakers.map((speaker, index) => {
      const inputId = `speaker-option-${index}`;
      // The number of reference recordings is not shown to users (it is in reports/ and README).
      const meta = [speaker.role]
        .filter(Boolean)
        .join(' · ');
      const input = h('input', {
        type: 'radio',
        name: 'speaker',
        id: inputId,
        value: speaker.id,
        class: 'speaker-option__input',
        checked: speaker.id === selectedId,
      });
      input.addEventListener('change', () => {
        if (input.checked) selectSpeaker(speaker.id);
      });
      return h(
        'label',
        {
          class: `speaker-option${speaker.id === selectedId ? ' is-selected' : ''}`,
          for: inputId,
          dataset: { speakerId: speaker.id },
        },
        input,
        h('span', { class: 'speaker-option__avatar', 'aria-hidden': 'true' }, icon('user')),
        h(
          'span',
          { class: 'speaker-option__body' },
          h('span', { class: 'speaker-option__name', text: speaker.name }),
          meta ? h('span', { class: 'speaker-option__meta', text: meta }) : null,
        ),
        h('span', { class: 'speaker-option__check', 'aria-hidden': 'true' }, icon('check')),
      );
    }),
  );
  if (api.mode === 'mock') {
    dom.speakerNote.replaceChildren(icon('info'), h('span', { text: t('speakers.demoNote') }));
    dom.speakerNote.hidden = false;
  }
}

function selectSpeaker(id) {
  const speaker = speakers.find((item) => item.id === id);
  if (!speaker) {
    showAlert(dom.speakerError, new SadaError('unsupported_speaker'));
    return;
  }
  hideAlert(dom.speakerError);
  setState({ speaker, result: null, error: null, status: setupStatus({ file: getState().file, speaker }) });
  syncSpeakerSelection();
}

function clearSpeaker() {
  setState({ speaker: null, status: setupStatus({ file: getState().file, speaker: null }) });
  syncSpeakerSelection();
}

function syncSpeakerSelection() {
  const selectedId = getState().speaker?.id ?? null;
  dom.speakerList.querySelectorAll('.speaker-option').forEach((option) => {
    const selected = option.dataset.speakerId === selectedId;
    option.classList.toggle('is-selected', selected);
    const input = option.querySelector('input');
    if (input) input.checked = selected;
  });
}

function applySpeakerPrefill() {
  const id = CONFIG.prefill.speaker;
  if (!id) return;
  if (speakers.some((item) => item.id === id)) selectSpeaker(id);
  else showAlert(dom.speakerError, new SadaError('unsupported_speaker'));
}

function focusSpeakers() {
  const input = dom.speakerList.querySelector('input:checked') ?? dom.speakerList.querySelector('input');
  input?.focus();
}

/* ---- Analysis ------------------------------------------------------------ */

async function runAnalysis() {
  const { file, speaker } = getState();
  if (!file || !speaker || abortController) return;

  abortController = new AbortController();
  dom.audio.pause();
  setState({ status: STATUS.PROCESSING, result: null, error: null });

  analysisView.render(api.mode === 'live' ? ['upload', ...ANALYSIS_STAGES] : [...ANALYSIS_STAGES], api.mode);
  dom.processingFile.textContent = file.name;
  dom.processingSpeaker.textContent = speaker.name;
  showView('processing', 'processing-title');
  analysisView.startTimer();
  announce(t('processing.started'));

  try {
    const result = await api.verifyAudio(file, speaker.id, {
      signal: abortController.signal,
      onStage: (id, stageState) => analysisView.set(id, stageState),
      onUploadProgress: (ratio) => analysisView.set('upload', 'active', `${Math.round(ratio * 100)}%`),
    });
    analysisView.completeAll();
    analysisView.stopTimer();
    await wait(prefersReducedMotion() ? 0 : 450);
    setState({ status: STATUS.COMPLETED, result });
    showResult(result);
  } catch (error) {
    analysisView.stopTimer();
    if (isAbortError(error)) {
      setState({ status: setupStatus(getState()) });
      showView('setup', dom.analyzeBtn);
      announce(t('processing.cancelled'));
      return;
    }
    console.error('[SADA] verification failed', error);
    const sadaError = error instanceof SadaError ? error : new SadaError('processing_failure', {}, { cause: error });
    setState({ status: STATUS.ERROR, error: sadaError });
    showError(sadaError);
  } finally {
    abortController = null;
  }
}

function showResult(result) {
  const { fileMeta, speaker } = getState();
  renderResult(dom.resultRoot, result, {
    fileMeta,
    speaker,
    session,
    audio: dom.audio,
    onRestart: restart,
    onEdit: backToSetup,
  });
  showView('result', 'result-title');
  announce(t('result.announce', { status: t(`result.status.${result.status}.title`) }));
}

function restart() {
  dom.resultRoot.cleanup?.();
  dom.resultRoot.replaceChildren();
  removeFile({ focus: false, quiet: true });
  showView('setup', dom.fileInput);
}

function backToSetup() {
  dom.resultRoot.cleanup?.();
  dom.audio.pause();
  setState({ status: setupStatus(getState()), result: null, error: null });
  showView('setup', 'setup-title');
}

const FILE_ERRORS = ['invalid_file', 'unsupported_format', 'file_too_large', 'file_too_short', 'file_too_long'];

function showError(error) {
  const copy = errorCopy(error);
  dom.errorTitle.textContent = copy.title;
  dom.errorDetail.textContent = copy.detail ?? '';
  dom.errorWhy.textContent = copy.why;
  dom.errorNext.textContent = copy.next;

  const button = (label, onClick, { primary = false, iconName = null } = {}) =>
    h(
      'button',
      { type: 'button', class: `btn ${primary ? 'btn--primary' : 'btn--secondary'}`, onClick },
      iconName ? icon(iconName) : null,
      label,
    );

  let actions;
  if (error.code === 'unsupported_speaker') {
    actions = [
      button(t('errorActions.chooseSpeaker'), () => {
        clearSpeaker();
        backToSetup();
        focusSpeakers();
      }, { primary: true }),
    ];
  } else if (FILE_ERRORS.includes(error.code)) {
    actions = [
      button(t('errorActions.chooseFile'), () => {
        backToSetup();
        dom.fileReplace.focus();
      }, { primary: true, iconName: 'upload' }),
    ];
  } else {
    actions = [
      button(t('errorActions.retry'), runAnalysis, { primary: true, iconName: 'replace' }),
      button(t('errorActions.back'), backToSetup),
    ];
  }
  dom.errorActions.replaceChildren(...actions);
  showView('error', 'error-title');
}

/* ---- Demo controls (mock mode only) -------------------------------------- */

function initDemoControls() {
  const demo = api.demo;
  if (!demo) return;

  const value = h('span', { class: 'demo-pill__value' });
  const pill = h(
    'button',
    { type: 'button', class: 'demo-pill', 'aria-expanded': 'false', 'aria-controls': 'demo-panel' },
    icon('flask'),
    h('span', { class: 'demo-pill__label', text: t('demo.pill') }),
    h('span', { class: 'demo-pill__label--short', 'aria-hidden': 'true', text: t('demo.pillShort') }),
    value,
  );

  const settings = demo.getSettings();
  const option = (group, key, label, hint) => {
    const input = h('input', { type: 'radio', name: `demo-${group}`, value: key, checked: settings[group] === key });
    input.addEventListener('change', () => {
      if (!input.checked) return;
      demo.setSettings({ [group]: key });
      updatePill();
    });
    return h('label', { class: 'demo-option' }, input, h('span', {}, label, hint ? h('small', { text: hint }) : null));
  };

  const panel = h(
    'div',
    { id: 'demo-panel', class: 'demo-panel', role: 'dialog', 'aria-labelledby': 'demo-panel-title', hidden: true },
    h(
      'div',
      { class: 'demo-panel__head' },
      h('h2', { class: 'demo-panel__title', id: 'demo-panel-title', text: t('demo.title') }),
      h('button', { type: 'button', class: 'btn btn--ghost btn--sm', 'aria-label': t('common.close'), onClick: () => toggle(false) }, icon('close')),
    ),
    h('p', { class: 'demo-panel__text', text: t('demo.text') }),
    h(
      'fieldset',
      {},
      h('legend', { text: t('demo.scenarioLegend') }),
      demo.scenarios.map((key) =>
        option('scenario', key, t(`demo.scenarios.${key}.label`), key === 'auto' ? t('demo.scenarios.auto.hint') : null),
      ),
    ),
    h(
      'fieldset',
      {},
      h('legend', { text: t('demo.errorLegend') }),
      demo.errors.map((key) => option('error', key, t(`demo.errors.${key}.label`))),
    ),
  );

  function updatePill() {
    const current = demo.getSettings();
    value.textContent = current.error !== 'none'
      ? t('demo.short.error', { label: t(`demo.errors.${current.error}.label`) })
      : t(`demo.short.${current.scenario}`);
  }

  function toggle(open, { returnFocus = true } = {}) {
    panel.hidden = !open;
    pill.setAttribute('aria-expanded', String(open));
    if (open) panel.querySelector('input:checked')?.focus();
    else if (returnFocus) pill.focus();
  }

  pill.addEventListener('click', () => toggle(panel.hidden));
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !panel.hidden) toggle(false);
  });
  document.addEventListener('pointerdown', (event) => {
    if (!panel.hidden && !panel.contains(event.target) && !pill.contains(event.target)) {
      toggle(false, { returnFocus: false });
    }
  });

  dom.demoSlot.replaceChildren(pill, panel);
  updatePill();
}
