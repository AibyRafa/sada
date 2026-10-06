/**
 * SADA — API service layer.
 *
 * The UI only ever talks to `api` below. It is backed by either:
 *   - mockApi  (js/mock-api.js) — in-browser demo, default
 *   - liveApi  (this file)      — FastAPI backend
 * Both return raw contract-shaped JSON, which is validated and normalised here,
 * so switching to FastAPI requires no UI change.
 *
 * Contract (see README):
 *   GET  /api/v1/speakers  → [{ id, name, role?, reference_count?, official_source? }]
 *   POST /api/v1/verify    multipart: audio, speaker_id → verification result
 */

import { CONFIG } from './config.js';
import { ERROR_CODES, SadaError, abortError } from './errors.js';
import { ANALYSIS_STAGES, RESULT_STATUSES } from './state.js';
import { t } from './i18n.js';
import { mockApi } from './mock-api.js';
import { parseLink, downloadLinkedAudio } from './link.js';

/* ---- HTTP (XHR for upload progress + abort + timeout) -------------------- */

function endpoint(name) {
  return `${CONFIG.apiBaseUrl.replace(/\/+$/, '')}${CONFIG.endpoints[name]}`;
}

function httpRequest({ method, url, body = null, signal, timeoutMs = 30_000, onUploadProgress, onUploadDone }) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError());
      return;
    }
    const xhr = new XMLHttpRequest();
    const onAbort = () => xhr.abort();
    const cleanup = () => signal?.removeEventListener('abort', onAbort);

    xhr.open(method, url);
    xhr.timeout = timeoutMs;
    xhr.setRequestHeader('Accept', 'application/json');

    if (body && xhr.upload) {
      if (onUploadProgress) {
        xhr.upload.addEventListener('progress', (event) => {
          if (event.lengthComputable) onUploadProgress(event.loaded / event.total);
        });
      }
      if (onUploadDone) xhr.upload.addEventListener('load', onUploadDone);
    }

    xhr.addEventListener('load', () => {
      cleanup();
      let parsed = null;
      try {
        parsed = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        parsed = null;
      }
      resolve({ status: xhr.status, body: parsed });
    });
    xhr.addEventListener('error', () => {
      cleanup();
      reject(new SadaError('backend_unavailable'));
    });
    xhr.addEventListener('timeout', () => {
      cleanup();
      reject(new SadaError('processing_failure', { reason: 'timeout' }));
    });
    xhr.addEventListener('abort', () => {
      cleanup();
      reject(abortError());
    });

    signal?.addEventListener('abort', onAbort, { once: true });
    xhr.send(body);
  });
}

function errorFromResponse(status, body) {
  const code = body?.error?.code ?? body?.detail?.code ?? body?.code;
  if (typeof code === 'string' && ERROR_CODES.includes(code)) return new SadaError(code, { status });
  if (status === 413) return new SadaError('file_too_large', { status });
  if (status === 415) return new SadaError('unsupported_format', { status });
  if (status === 502 || status === 503 || status === 504) return new SadaError('backend_unavailable', { status });
  return new SadaError('processing_failure', { status });
}

/** Backend failure for the link endpoint: its own code when valid, else a link problem for 4xx. */
async function linkErrorFromResponse(response, link) {
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  const error = errorFromResponse(response.status, body);
  if (error.code === 'processing_failure' && response.status >= 400 && response.status < 500) {
    return new SadaError('link_unreachable', { name: link.host, status: response.status });
  }
  error.details = { name: link.host, ...error.details };
  return error;
}

/* ---- Live FastAPI client ------------------------------------------------- */

const liveApi = {
  mode: 'live',
  demo: null,

  async getSpeakers({ signal } = {}) {
    try {
      const { status, body } = await httpRequest({ method: 'GET', url: endpoint('speakers'), signal });
      if (status < 200 || status >= 300) throw errorFromResponse(status, body);
      return Array.isArray(body) ? body : body?.speakers;
    } catch (error) {
      if (error?.code === 'backend_unavailable') throw new SadaError('speakers_unavailable');
      throw error;
    }
  },

  /** The backend downloads the link and returns the audio bytes (see README: POST /api/v1/fetch-audio). */
  async fetchAudioFromLink(link, { signal } = {}) {
    return downloadLinkedAudio(
      link,
      (requestSignal) =>
        fetch(endpoint('fetchAudio'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'audio/*, application/octet-stream, application/json' },
          body: JSON.stringify({ url: link.href }),
          signal: requestSignal,
        }),
      {
        signal,
        networkErrorCode: 'backend_unavailable',
        onHttpError: (response) => linkErrorFromResponse(response, link),
      },
    );
  },

  async verifyAudio(file, speakerId, { signal, onStage, onUploadProgress } = {}) {
    const form = new FormData();
    form.append('audio', file, file.name);
    form.append('speaker_id', speakerId);

    onStage?.('upload', 'active');
    const { status, body } = await httpRequest({
      method: 'POST',
      url: endpoint('verify'),
      body: form,
      signal,
      timeoutMs: CONFIG.requestTimeoutMs,
      onUploadProgress,
      onUploadDone: () => {
        // The backend runs its stages in one request; show them as "on the server"
        // rather than inventing per-stage timing.
        onStage?.('upload', 'done');
        ANALYSIS_STAGES.forEach((id) => onStage?.(id, 'server'));
      },
    });
    if (status < 200 || status >= 300) throw errorFromResponse(status, body);
    return body;
  },
};

/* ---- Normalisation (shared by mock and live) ----------------------------- */

const isObject = (value) => value != null && typeof value === 'object' && !Array.isArray(value);
const text = (value) => (typeof value === 'string' && value.trim() ? value.trim() : null);
const textList = (value) => (Array.isArray(value) ? value.map(text).filter(Boolean) : []);
const positive = (value) => (Number.isFinite(value) && value > 0 ? value : null);
const count = (value) => (Number.isInteger(value) && value >= 0 ? value : null);

/** Values must be on the 0–1 scale of the contract; anything else is hidden. */
function unit(value) {
  if (!Number.isFinite(value)) return null;
  if (value < 0 || value > 1) {
    console.warn('[SADA] Ignoring out-of-range score (expected 0–1):', value);
    return null;
  }
  return value;
}

/** Only http(s) or same-site relative links are ever rendered. */
export function safeUrl(value) {
  if (typeof value !== 'string' || !value.trim()) return null;
  try {
    const url = new URL(value, window.location.href);
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null;
  } catch {
    return null;
  }
}

function normalizeOfficialSource(raw) {
  if (!isObject(raw)) return null;
  const label = text(raw.label);
  const url = safeUrl(raw.url);
  return label || url ? { label, url } : null;
}

function normalizeSpeakers(list) {
  if (!Array.isArray(list)) throw new SadaError('speakers_unavailable');
  return list
    .filter((item) => isObject(item) && (typeof item.id === 'string' || Number.isFinite(item.id)) && text(item.name))
    .map((item) => ({
      id: String(item.id),
      name: text(item.name),
      role: text(item.role),
      referenceCount: count(item.reference_count),
      officialSource: normalizeOfficialSource(item.official_source),
    }));
}

const KNOWN_INDICATORS = ['pitch_stability', 'high_frequency_energy', 'pause_regularity'];

function normalizeIndicators(acoustic) {
  return Object.entries(acoustic)
    .filter(([key, value]) => key !== 'score' && typeof value === 'number')
    .map(([key, value]) => ({ key, value: unit(value) }))
    .filter((item) => item.value != null)
    .sort((a, b) => {
      const ia = KNOWN_INDICATORS.indexOf(a.key);
      const ib = KNOWN_INDICATORS.indexOf(b.key);
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    });
}

function normalizeSegments(raw) {
  if (!Array.isArray(raw)) return null;
  return raw
    .filter(isObject)
    .map((segment) => {
      const start = Number(segment.start);
      const end = Number(segment.end);
      if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start) return null;
      return { start, end, reason: text(segment.reason) ?? text(segment.label) ?? t('segments.defaultReason') };
    })
    .filter(Boolean)
    .sort((a, b) => a.start - b.start);
}

/* ---- Splice / edit detection (`splice_analysis`) -------------------------- */

const SPLICE_INDICATORS = ['cut_continuity', 'sequence_naturalness', 'voice_consistency'];
const SPLICE_TYPES = ['cut', 'unnatural_sequence', 'voice_swap'];

/** A cut is an instant. When a finding carries `time` instead of a range, this many seconds
 *  either side are marked and played, so the listener hears the join in context. */
const SPLICE_POINT_PADDING_SEC = 1;

const finiteNumber = (value) => (typeof value === 'number' && Number.isFinite(value) ? value : null);

/** → null when the backend sent no usable list (unknown); [] only when it explicitly found nothing. */
function normalizeSpliceFindings(raw) {
  if (!Array.isArray(raw)) return null;
  const findings = raw
    .filter(isObject)
    .map((item) => {
      const start = finiteNumber(item.start);
      const end = finiteNumber(item.end);
      const time = finiteNumber(item.time);
      let from;
      let to;
      if (start != null && end != null) {
        from = start;
        to = end;
      } else if (time != null && time >= 0) {
        from = Math.max(0, time - SPLICE_POINT_PADDING_SEC);
        to = time + SPLICE_POINT_PADDING_SEC;
      } else {
        return null;
      }
      if (from < 0 || to <= from) return null;
      const kind = SPLICE_TYPES.includes(item.type) ? item.type : 'other';
      return {
        start: from,
        end: to,
        reason: text(item.reason) ?? t(`splice.types.${kind}`),
        kind,
        confidence: unit(item.confidence),
      };
    })
    .filter(Boolean)
    .sort((a, b) => a.start - b.start);
  // A non-empty list in which every entry was invalid is "unknown", not "nothing found".
  return raw.length > 0 && findings.length === 0 ? null : findings;
}

/** Returns null when the response carries nothing usable, so the card is hidden rather than filled in. */
function normalizeSplice(raw) {
  if (!isObject(raw)) return null;
  const indicators = SPLICE_INDICATORS
    .map((key) => ({ key, value: unit(raw[key]) }))
    .filter((item) => item.value != null);
  const splice = {
    score: unit(raw.score),
    indicators,
    findings: normalizeSpliceFindings(raw.findings),
    anomalies: textList(raw.anomalies),
  };
  const empty = splice.score == null && !indicators.length && splice.findings == null && !splice.anomalies.length;
  return empty ? null : splice;
}

/** Splice findings are shown on the spectrogram and in the segment list next to `flagged_segments`. */
function mergeSpliceSegments(segments, splice) {
  if (!splice?.findings?.length) return segments;
  return [...(segments ?? []), ...splice.findings].sort((a, b) => a.start - b.start);
}

const IMAGE_MIME = /^image\/(png|jpeg|webp)$/;
const BASE64 = /^[A-Za-z0-9+/=\s]+$/;
const MAX_MATRIX_CELLS = 2_000_000;

function normalizeSpectrogram(raw) {
  if (!isObject(raw)) return null;
  const maxHz = positive(raw.frequency_max_hz);
  const scale = raw.frequency_scale === 'linear' ? 'linear' : 'mel';

  const imageUrl = safeUrl(raw.image_url);
  if (imageUrl) return { kind: 'image', src: imageUrl, maxHz, scale };

  if (typeof raw.image_base64 === 'string' && BASE64.test(raw.image_base64)) {
    const mime = IMAGE_MIME.test(raw.mime_type) ? raw.mime_type : 'image/png';
    return { kind: 'image', src: `data:${mime};base64,${raw.image_base64.replace(/\s/g, '')}`, maxHz, scale };
  }

  const matrix = raw.data;
  if (
    Array.isArray(matrix) && matrix.length > 1 && Array.isArray(matrix[0]) && matrix[0].length > 1
    && matrix.length * matrix[0].length <= MAX_MATRIX_CELLS
    && matrix.every((column) => Array.isArray(column) && column.length === matrix[0].length)
  ) {
    return { kind: 'matrix', data: matrix, maxHz: maxHz ?? 8000, scale };
  }
  return null;
}

const SOURCE_TYPES = ['reference_recording', 'methodology', 'official_source', 'traceability'];

function normalizeSources(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter(isObject)
    .map((source) => ({
      type: SOURCE_TYPES.includes(source.type) ? source.type : 'other',
      title: text(source.title),
      description: text(source.description),
      url: safeUrl(source.url),
    }))
    .filter((source) => source.title);
}

/**
 * Validates a backend (or mock) response and maps it to the UI model.
 * Unknown verdicts are rejected — the UI never shows a status it can't explain.
 */
export function normalizeResult(raw, { isMock = false } = {}) {
  if (!isObject(raw)) throw new SadaError('processing_failure', { reason: 'empty_response' });
  if (!RESULT_STATUSES.includes(raw.status)) {
    throw new SadaError('processing_failure', { reason: 'unknown_status' });
  }

  const voiceprint = isObject(raw.voiceprint) ? raw.voiceprint : {};
  const acoustic = isObject(raw.acoustic_analysis) ? raw.acoustic_analysis : {};
  const meta = isObject(raw.meta) ? raw.meta : {};
  const models = isObject(meta.models) ? meta.models : {};
  const splice = normalizeSplice(raw.splice_analysis);

  return {
    status: raw.status,
    confidence: unit(raw.confidence),
    decisionThreshold: unit(raw.decision_threshold),
    speaker: isObject(raw.speaker) ? { id: text(String(raw.speaker.id ?? '')), name: text(raw.speaker.name) } : null,
    voiceprint: {
      match: unit(voiceprint.match),
      flag: text(voiceprint.flag),
      referencesCompared: count(voiceprint.references_compared),
    },
    acoustic: {
      score: unit(acoustic.score),
      indicators: normalizeIndicators(acoustic),
      anomalies: textList(acoustic.anomalies),
    },
    splice,
    flaggedSegments: mergeSpliceSegments(normalizeSegments(raw.flagged_segments), splice),
    spectrogram: normalizeSpectrogram(raw.spectrogram),
    recommendation: text(raw.recommendation),
    observations: textList(raw.observations),
    limitations: textList(raw.limitations),
    sources: normalizeSources(raw.sources),
    officialSource: normalizeOfficialSource(raw.official_source),
    meta: {
      isMock: isMock || meta.mode === 'mock',
      analysisId: text(meta.analysis_id),
      analyzedAt: text(meta.analyzed_at),
      speakerEncoder: text(models.speaker_encoder),
      artifactClassifier: text(models.artifact_classifier),
      spliceDetector: text(models.splice_detector),
      referenceSet: text(meta.reference_set),
      processingMs: positive(meta.processing_ms),
      duration: positive(raw.duration),
    },
  };
}

/* ---- Public facade ------------------------------------------------------- */

const backend = CONFIG.apiMode === 'live' ? liveApi : mockApi;

export const api = Object.freeze({
  /** 'mock' | 'live' */
  mode: backend.mode,

  /** Demo controls (mock only); null when talking to the real backend. */
  demo: backend.demo ?? null,

  async getSpeakers(options) {
    return normalizeSpeakers(await backend.getSpeakers(options));
  },

  /**
   * Downloads the audio behind a pasted link as a File, so it enters the same flow as a chosen file.
   * @param {string} input   what the person pasted
   * @param {{signal?: AbortSignal}} [options]
   */
  async fetchAudioFromLink(input, options = {}) {
    return backend.fetchAudioFromLink(parseLink(input), options);
  },

  /**
   * @param {File} file
   * @param {string} speakerId
   * @param {{signal?: AbortSignal, onStage?: (id: string, state: string) => void,
   *          onUploadProgress?: (ratio: number) => void}} [options]
   */
  async verifyAudio(file, speakerId, options = {}) {
    const raw = await backend.verifyAudio(file, speakerId, options);
    return normalizeResult(raw, { isMock: backend.mode === 'mock' });
  },
});
