/**
 * SADA — Frontend configuration.
 * Every environment-dependent value lives here so UI modules never hard-code them.
 *
 * API mode resolution (first match wins):
 *   1. URL parameter      ?mode=mock | ?mode=live
 *   2. <meta name="sada-api-mode" content="mock|live"> in verify.html
 *   3. default            "mock"
 *
 * No secrets belong in this file — it is shipped to every browser.
 */

const params = new URLSearchParams(window.location.search);

function readMeta(name) {
  const el = document.querySelector(`meta[name="${name}"]`);
  return el ? el.getAttribute('content').trim() : '';
}

function resolveApiMode() {
  const fromUrl = params.get('mode');
  if (fromUrl === 'mock' || fromUrl === 'live') return fromUrl;
  const fromMeta = readMeta('sada-api-mode');
  return fromMeta === 'live' ? 'live' : 'mock';
}

export const CONFIG = Object.freeze({
  locale: 'ar',

  /** 'mock' runs fully in the browser; 'live' calls the FastAPI backend. */
  apiMode: resolveApiMode(),

  /** Empty string = same origin (FastAPI serving these static files). */
  apiBaseUrl: readMeta('sada-api-base'),

  endpoints: Object.freeze({
    verify: '/api/v1/verify',
    speakers: '/api/v1/speakers',
    fetchAudio: '/api/v1/fetch-audio',
  }),

  requestTimeoutMs: 120_000,

  /**
   * ASSUMPTION: the proposal does not specify upload limits.
   * These are conservative defaults; keep them in sync with the backend.
   */
  limits: Object.freeze({
    maxFileBytes: 50 * 1024 * 1024,
    minDurationSec: 3,
    maxDurationSec: 600,
  }),

  /**
   * ASSUMPTION: formats commonly used when sharing clips (incl. messaging-app
   * voice notes). Decoding on the server is expected to support all of them.
   */
  formats: Object.freeze({
    supported: Object.freeze(['mp3', 'wav', 'm4a', 'aac', 'ogg', 'opus', 'flac', 'mp4', 'mov', 'webm']),
    // Video files: only their sound is analysed (on the server); the picture is ignored.
    video: Object.freeze(['mp4', 'mov', 'webm']),
    knownUnsupportedAudio: Object.freeze([
      'wma', 'amr', 'aiff', 'aif', 'aifc', 'caf', '3gp', 'ra', 'mid', 'midi', 'ac3', 'ape', 'mka',
    ]),
  }),

  /** Client-side visualisation only (waveform + local spectrogram). */
  visual: Object.freeze({
    analysisSampleRate: 32_000,
    spectrogramMaxHz: 16_000,
  }),

  /** Optional deep links, e.g. verify.html?speaker=ref_a&scenario=inconclusive */
  prefill: Object.freeze({
    speaker: params.get('speaker'),
  }),

  demo: Object.freeze({
    scenario: params.get('scenario'),
    simulate: params.get('simulate'),
  }),
});
