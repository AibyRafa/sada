/**
 * SADA — Verification state.
 * A single, explicit state object; UI modules subscribe and re-render.
 *
 *   status:  idle → file_selected → ready → processing → completed | error
 *   result.status: likely_authentic | inconclusive | likely_synthetic
 */

export const STATUS = Object.freeze({
  IDLE: 'idle',
  FILE_SELECTED: 'file_selected',
  READY: 'ready',
  PROCESSING: 'processing',
  COMPLETED: 'completed',
  ERROR: 'error',
});

export const RESULT_STATUS = Object.freeze({
  AUTHENTIC: 'likely_authentic',
  INCONCLUSIVE: 'inconclusive',
  SYNTHETIC: 'likely_synthetic',
});

export const RESULT_STATUSES = Object.freeze(Object.values(RESULT_STATUS));

/** Server-side pipeline stages, in order (mirrors the proposal's workflow). */
export const ANALYSIS_STAGES = Object.freeze(['preprocess', 'voiceprint', 'acoustic', 'splice', 'fusion', 'report']);

const verificationState = {
  file: null,
  fileMeta: null,
  speaker: null,
  status: STATUS.IDLE,
  result: null,
  error: null,
};

const listeners = new Set();

/** Returns a shallow copy; mutate only through setState(). */
export function getState() {
  return { ...verificationState };
}

export function setState(patch) {
  Object.assign(verificationState, patch);
  const snapshot = getState();
  listeners.forEach((listener) => listener(snapshot));
}

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Status implied by the setup inputs alone (used outside processing/result). */
export function setupStatus({ file, speaker }) {
  if (!file) return STATUS.IDLE;
  return speaker ? STATUS.READY : STATUS.FILE_SELECTED;
}
