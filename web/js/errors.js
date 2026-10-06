/**
 * SADA — Error model shared by the API layer and the UI.
 * Every user-facing failure maps to one of these codes; the copy for each
 * (what happened / why / what to do next) lives in i18n.js under `errors`.
 */

export const ERROR_CODES = Object.freeze([
  'invalid_file',
  'unsupported_format',
  'file_too_large',
  'file_too_short',
  'file_too_long',
  'backend_unavailable',
  'processing_failure',
  'unsupported_speaker',
  'speakers_unavailable',
  'invalid_link',
  'link_unreachable',
  'link_not_audio',
]);

export class SadaError extends Error {
  /**
   * @param {string} code    one of ERROR_CODES (unknown codes fall back to processing_failure)
   * @param {object} details interpolation values for the message (file name, size…)
   * @param {{cause?: unknown}} [options]
   */
  constructor(code, details = {}, options = {}) {
    super(code);
    this.name = 'SadaError';
    this.code = ERROR_CODES.includes(code) ? code : 'processing_failure';
    this.details = details;
    if (options.cause) this.cause = options.cause;
  }
}

export function abortError() {
  return new DOMException('The operation was aborted.', 'AbortError');
}

export function isAbortError(error) {
  return error?.name === 'AbortError';
}
