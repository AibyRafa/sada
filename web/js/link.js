/**
 * SADA — Audio from a pasted link.
 *
 * Shared by the mock client (the browser downloads the link itself) and the live
 * client (the backend downloads it and streams the audio back). Either way the
 * result is a File, so the clip enters the same flow as a chosen file: the same
 * validation, waveform, player and spectrogram.
 */

import { CONFIG } from './config.js';
import { SadaError, abortError, isAbortError } from './errors.js';
import { getExtension } from './audio.js';

/* ---- Link parsing -------------------------------------------------------- */

/**
 * Accepts an http(s) address (a missing scheme is read as https). Rejects anything
 * else, including addresses that embed credentials.
 * @returns {{href: string, host: string, pathname: string}}
 */
export function parseLink(input) {
  const raw = typeof input === 'string' ? input.trim() : '';
  if (!raw || /\s/.test(raw)) throw new SadaError('invalid_link');

  let url;
  try {
    url = new URL(raw.includes('://') ? raw : `https://${raw}`);
  } catch {
    throw new SadaError('invalid_link');
  }
  const web = url.protocol === 'https:' || url.protocol === 'http:';
  if (!web || !url.hostname || url.username || url.password) throw new SadaError('invalid_link');
  return { href: url.href, host: url.hostname, pathname: url.pathname };
}

/* ---- Response → File ----------------------------------------------------- */

const MIME_EXTENSIONS = {
  'audio/mpeg': 'mp3',
  'audio/mp3': 'mp3',
  'audio/wav': 'wav',
  'audio/x-wav': 'wav',
  'audio/wave': 'wav',
  'audio/vnd.wave': 'wav',
  'audio/mp4': 'm4a',
  'audio/x-m4a': 'm4a',
  'audio/m4a': 'm4a',
  'audio/aac': 'aac',
  'audio/aacp': 'aac',
  'audio/ogg': 'ogg',
  'application/ogg': 'ogg',
  'audio/opus': 'opus',
  'audio/flac': 'flac',
  'audio/x-flac': 'flac',
};

// Same family of types audio.js accepts, plus the generic binary types servers often send.
const AUDIO_LIKE = /^(audio\/.+|video\/ogg|video\/mp4|application\/ogg|application\/octet-stream|binary\/octet-stream)$/;

const FALLBACK_NAME = 'link-audio';
const MAX_STEM_LENGTH = 100;

function decodeSafe(value) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function nameFromDisposition(header) {
  if (!header) return null;
  const extended = /filename\*\s*=\s*utf-8''([^;]+)/i.exec(header);
  if (extended) return decodeSafe(extended[1].trim());
  const plain = /filename\s*=\s*"?([^";]+)"?/i.exec(header);
  return plain ? plain[1].trim() : null;
}

/** Last path segment only; control characters and separators are dropped. */
function cleanName(name) {
  if (!name) return null;
  const base = String(name).split(/[\\/]/).pop().replace(/[\u0000-\u001f\u007f]/g, '').trim();
  return base || null;
}

function fileNameFor(link, response, mime) {
  const raw =
    cleanName(nameFromDisposition(response.headers.get('content-disposition')))
    ?? cleanName(decodeSafe(link.pathname.split('/').filter(Boolean).pop() ?? ''));
  const ext = raw ? getExtension(raw) : '';
  if (CONFIG.formats.supported.includes(ext)) {
    const stem = raw.slice(0, -(ext.length + 1));
    return `${stem.slice(0, MAX_STEM_LENGTH)}.${ext}`;
  }
  // The name does not say what the file is: trust the declared audio type instead.
  const mimeExt = MIME_EXTENSIONS[mime];
  if (mimeExt) {
    const stem = (raw ?? FALLBACK_NAME).replace(/\.[a-z0-9]{1,5}$/i, '') || FALLBACK_NAME;
    return `${stem.slice(0, MAX_STEM_LENGTH)}.${mimeExt}`;
  }
  return raw ?? FALLBACK_NAME;
}

/** Reads the body with a hard size cap, so an oversized download is stopped early. */
async function readBounded(response, link, signal) {
  const max = CONFIG.limits.maxFileBytes;
  const tooLarge = (size) => new SadaError('file_too_large', { name: link.host, size });

  const declared = Number(response.headers.get('content-length'));
  if (Number.isFinite(declared) && declared > max) throw tooLarge(declared);

  if (!response.body?.getReader) {
    const blob = await response.blob();
    if (blob.size > max) throw tooLarge(blob.size);
    return [blob];
  }

  const reader = response.body.getReader();
  const chunks = [];
  let total = 0;
  const onAbort = () => reader.cancel().catch(() => {});
  signal?.addEventListener('abort', onAbort, { once: true });
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > max) {
        reader.cancel().catch(() => {});
        throw tooLarge(total);
      }
      chunks.push(value);
    }
  } finally {
    signal?.removeEventListener('abort', onAbort);
  }
  return chunks;
}

async function fileFromResponse(response, link, signal) {
  const mime = (response.headers.get('content-type') ?? '').split(';')[0].trim().toLowerCase();
  // A web page, JSON, an image… is not a clip. An unknown or missing type is left to the file checks.
  if (mime && !AUDIO_LIKE.test(mime)) throw new SadaError('link_not_audio', { name: link.host });

  const chunks = await readBounded(response, link, signal);
  const name = fileNameFor(link, response, mime);
  return new File(chunks, name, { type: mime.startsWith('audio/') ? mime : '' });
}

/* ---- Request guard ------------------------------------------------------- */

function withTimeout(outer, ms) {
  const controller = new AbortController();
  let timedOut = false;
  const onAbort = () => controller.abort();
  if (outer?.aborted) controller.abort();
  else outer?.addEventListener('abort', onAbort, { once: true });
  const timer = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, ms);
  return {
    signal: controller.signal,
    timedOut: () => timedOut,
    cleanup() {
      window.clearTimeout(timer);
      outer?.removeEventListener('abort', onAbort);
    },
  };
}

/**
 * Runs `request(signal)` (a fetch returning a Response) and turns the audio it
 * returns into a File. Every failure leaves as a SadaError, or as an AbortError
 * when the person cancelled.
 *
 * @param {{href: string, host: string, pathname: string}} link
 * @param {(signal: AbortSignal) => Promise<Response>} request
 * @param {{signal?: AbortSignal,
 *          onHttpError?: (response: Response) => Promise<SadaError>,
 *          networkErrorCode?: string}} [options]
 *   onHttpError          maps a non-2xx response to an error (default: link_unreachable)
 *   networkErrorCode     code when the request itself fails (default: link_unreachable)
 */
export async function downloadLinkedAudio(link, request, { signal, onHttpError, networkErrorCode = 'link_unreachable' } = {}) {
  const guard = withTimeout(signal, CONFIG.requestTimeoutMs);
  try {
    const response = await request(guard.signal);
    if (!response.ok) {
      throw onHttpError
        ? await onHttpError(response)
        : new SadaError('link_unreachable', { name: link.host, status: response.status });
    }
    return await fileFromResponse(response, link, guard.signal);
  } catch (error) {
    if (guard.timedOut()) throw new SadaError('link_unreachable', { name: link.host, reason: 'timeout' });
    if (isAbortError(error)) throw abortError();
    if (error instanceof SadaError) throw error;
    throw new SadaError(networkErrorCode, { name: link.host }, { cause: error });
  } finally {
    guard.cleanup();
  }
}
