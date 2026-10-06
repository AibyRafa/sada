/**
 * SADA — Audio handling in the browser.
 * File validation, metadata, decoding for visualisation, waveform drawing,
 * and a small accessible player. Nothing here performs authenticity analysis;
 * decoded samples are used only to draw the clip.
 */

import { CONFIG } from './config.js';
import { SadaError } from './errors.js';
import { t } from './i18n.js';
import { h, icon, fitCanvas, formatDuration } from './ui.js';

/* ---- Validation ---------------------------------------------------------- */

export function getExtension(name = '') {
  const match = /\.([a-z0-9]+)$/i.exec(name.trim());
  return match ? match[1].toLowerCase() : '';
}

// MIME types browsers report for the supported formats (or empty / generic).
const ACCEPTABLE_MIME = /^(audio\/.+|video\/(ogg|mp4|quicktime|webm)|application\/ogg|application\/octet-stream)$/i;

/** Synchronous checks that need no decoding. Throws SadaError. */
export function checkFileBasics(file) {
  const ext = getExtension(file.name);
  const type = (file.type || '').toLowerCase();
  const details = { name: file.name, ext: ext ? ext.toUpperCase() : '—', size: file.size };
  const { supported, knownUnsupportedAudio } = CONFIG.formats;

  if (!file.size) throw new SadaError('invalid_file', details);
  if (!supported.includes(ext)) {
    const looksLikeAudio = type.startsWith('audio/') || knownUnsupportedAudio.includes(ext);
    throw new SadaError(looksLikeAudio ? 'unsupported_format' : 'invalid_file', details);
  }
  if (type && !ACCEPTABLE_MIME.test(type)) throw new SadaError('invalid_file', details);
  if (file.size > CONFIG.limits.maxFileBytes) throw new SadaError('file_too_large', details);
  return { ext };
}

/* ---- Metadata & decoding ------------------------------------------------- */

/** Duration via a detached <audio> element. Resolves null when unknown. */
export function readDuration(source, { timeoutMs = 8000 } = {}) {
  return new Promise((resolve) => {
    const ownsUrl = source instanceof Blob;
    const url = ownsUrl ? URL.createObjectURL(source) : source;
    const probe = new Audio();
    let settled = false;

    const finish = (value) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      probe.removeAttribute('src');
      probe.load();
      if (ownsUrl) URL.revokeObjectURL(url);
      resolve(Number.isFinite(value) && value > 0 ? value : null);
    };

    const timer = window.setTimeout(() => finish(null), timeoutMs);
    probe.preload = 'metadata';
    probe.addEventListener('loadedmetadata', () => {
      if (Number.isFinite(probe.duration)) {
        finish(probe.duration);
        return;
      }
      // Some containers (e.g. Opus) report Infinity until the end is probed.
      probe.addEventListener('durationchange', () => {
        if (Number.isFinite(probe.duration)) finish(probe.duration);
      });
      probe.currentTime = 1e101;
    });
    probe.addEventListener('error', () => finish(null));
    probe.src = url;
  });
}

/** Decodes to a mono Float32Array for drawing. Resolves null if unsupported. */
export async function decodeToMono(file, sampleRate = CONFIG.visual.analysisSampleRate) {
  const OfflineCtx = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  if (!OfflineCtx) return null;

  const buffer = await file.arrayBuffer();
  const ctx = new OfflineCtx(1, 1, sampleRate);
  const audioBuffer = await new Promise((resolve, reject) => {
    const maybePromise = ctx.decodeAudioData(buffer, resolve, reject);
    if (maybePromise && typeof maybePromise.then === 'function') maybePromise.then(resolve, reject);
  });

  const channels = audioBuffer.numberOfChannels;
  let samples;
  if (channels === 1) {
    samples = audioBuffer.getChannelData(0);
  } else {
    samples = new Float32Array(audioBuffer.length);
    for (let c = 0; c < channels; c += 1) {
      const data = audioBuffer.getChannelData(c);
      for (let i = 0; i < data.length; i += 1) samples[i] += data[i] / channels;
    }
  }
  return { samples, sampleRate: audioBuffer.sampleRate, duration: audioBuffer.duration, channels };
}

/** RMS envelope normalised to 0–1, one value per bucket. */
export function computeEnvelope(samples, buckets = 1200) {
  const envelope = new Float32Array(buckets);
  const size = samples.length / buckets;
  let max = 0;
  for (let b = 0; b < buckets; b += 1) {
    const start = Math.floor(b * size);
    const end = Math.min(samples.length, Math.floor((b + 1) * size));
    const step = Math.max(1, Math.floor((end - start) / 256));
    let sum = 0;
    let count = 0;
    for (let i = start; i < end; i += step) {
      sum += samples[i] * samples[i];
      count += 1;
    }
    const rms = count ? Math.sqrt(sum / count) : 0;
    envelope[b] = rms;
    if (rms > max) max = rms;
  }
  if (max > 0) {
    for (let b = 0; b < buckets; b += 1) envelope[b] = Math.pow(envelope[b] / max, 0.75);
  }
  return envelope;
}

/* ---- Waveform ------------------------------------------------------------ */

export function drawWaveform(canvas, envelope, progress = 0) {
  const { ctx, width, height } = fitCanvas(canvas);
  const styles = getComputedStyle(canvas);
  const played = styles.getPropertyValue('--wave-played').trim() || '#3b2d22';
  const rest = styles.getPropertyValue('--wave-rest').trim() || '#cdba9b';
  const barWidth = 3;
  const gap = 2;
  const bars = Math.max(1, Math.floor((width + gap) / (barWidth + gap)));
  const offset = (width - (bars * (barWidth + gap) - gap)) / 2;

  ctx.clearRect(0, 0, width, height);
  for (let i = 0; i < bars; i += 1) {
    const value = envelope[Math.min(envelope.length - 1, Math.floor((i / bars) * envelope.length))];
    const barHeight = Math.max(3, value * (height - 6));
    const x = offset + i * (barWidth + gap);
    const y = (height - barHeight) / 2;
    ctx.fillStyle = (i + 0.5) / bars <= progress ? played : rest;
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(x, y, barWidth, barHeight, 1.5);
    else ctx.rect(x, y, barWidth, barHeight);
    ctx.fill();
  }
}

/* ---- Session: one selected clip, one <audio> element --------------------- */

export function createAudioSession(audio) {
  let current = null; // { file, url, decoded, duration }
  let rangeEnd = null;
  let frame = 0;
  const frameListeners = new Set();

  const emitFrame = () => frameListeners.forEach((listener) => listener(audio.currentTime));

  const loop = () => {
    if (rangeEnd != null && audio.currentTime >= rangeEnd) {
      audio.pause();
      rangeEnd = null;
    }
    emitFrame();
    frame = !audio.paused && !audio.ended ? requestAnimationFrame(loop) : 0;
  };

  audio.addEventListener('play', () => {
    if (!frame) frame = requestAnimationFrame(loop);
  });
  audio.addEventListener('pause', () => {
    rangeEnd = null;
    emitFrame();
  });
  audio.addEventListener('seeked', emitFrame);
  audio.addEventListener('ended', emitFrame);

  return {
    get file() {
      return current?.file ?? null;
    },
    get decoded() {
      return current?.decoded ?? null;
    },
    get duration() {
      if (Number.isFinite(audio.duration) && audio.duration > 0) return audio.duration;
      return current?.duration ?? null;
    },

    /**
     * Validates, measures and decodes a file, then makes it the active clip.
     * The previous clip stays active if the new one is rejected.
     */
    async load(file) {
      const { ext } = checkFileBasics(file);
      const url = URL.createObjectURL(file);
      const [durationResult, decodeResult] = await Promise.allSettled([readDuration(url), decodeToMono(file)]);
      const decoded = decodeResult.status === 'fulfilled' ? decodeResult.value : null;
      let duration = durationResult.status === 'fulfilled' ? durationResult.value : null;
      if (!Number.isFinite(duration) && decoded) duration = decoded.duration;

      const details = { name: file.name, ext: ext.toUpperCase(), size: file.size, duration };
      const reject = (code) => {
        URL.revokeObjectURL(url);
        throw new SadaError(code, details);
      };
      const isVideo = CONFIG.formats.video.includes(ext);
      if (!Number.isFinite(duration) || duration <= 0) {
        // Some browsers cannot read a video's sound (e.g. iPhone HEVC .mov in Chrome):
        // the server decodes it with ffmpeg and checks the length itself.
        if (!isVideo) reject('invalid_file');
        duration = null;
      } else {
        if (duration < CONFIG.limits.minDurationSec) reject('file_too_short');
        if (duration > CONFIG.limits.maxDurationSec) reject('file_too_long');
      }

      this.clear();
      current = { file, url, decoded, duration };
      audio.src = url;
      audio.load();
      return {
        name: file.name,
        size: file.size,
        type: file.type,
        ext,
        duration,
        canVisualise: Boolean(decoded),
      };
    },

    /** Releases the clip from the page (object URL, decoded samples, player). */
    clear() {
      audio.pause();
      rangeEnd = null;
      if (current?.url) URL.revokeObjectURL(current.url);
      current = null;
      audio.removeAttribute('src');
      audio.load();
      emitFrame();
    },

    seek(seconds) {
      const duration = this.duration;
      if (!Number.isFinite(duration)) return;
      rangeEnd = null;
      audio.currentTime = Math.min(Math.max(0, seconds), duration);
    },

    /** Plays [start, end] and pauses at the end (used for flagged segments). */
    playRange(start, end) {
      audio.currentTime = Math.max(0, start);
      const play = audio.play();
      rangeEnd = end;
      if (play?.catch) play.catch(() => { rangeEnd = null; });
    },

    onFrame(listener) {
      frameListeners.add(listener);
      return () => frameListeners.delete(listener);
    },
  };
}

/* ---- Player -------------------------------------------------------------- */

/**
 * Accessible play/pause + seek slider bound to the shared <audio> element.
 * Rendered left-to-right in every locale, like media timelines.
 */
export function createPlayer(root, audio, session) {
  const playButton = h(
    'button',
    { type: 'button', class: 'player__play', 'aria-label': t('player.play') },
    icon('play', { className: 'player__icon-play' }),
    icon('pause', { className: 'player__icon-pause' }),
  );
  const currentTime = h('span', { class: 'player__time', text: '00:00' });
  const totalTime = h('span', { class: 'player__time', text: '00:00' });
  const range = h('input', {
    type: 'range',
    class: 'player__range',
    min: '0',
    max: '1000',
    step: '1',
    value: '0',
    'aria-label': t('player.seek'),
  });

  root.classList.add('player');
  root.setAttribute('dir', 'ltr');
  root.replaceChildren(playButton, currentTime, range, totalTime);

  let dragging = false;

  const sync = () => {
    const duration = session.duration;
    const position = audio.currentTime || 0;
    const ratio = Number.isFinite(duration) && duration > 0 ? Math.min(1, position / duration) : 0;
    currentTime.textContent = formatDuration(position);
    totalTime.textContent = formatDuration(duration);
    if (!dragging) range.value = String(Math.round(ratio * 1000));
    range.style.setProperty('--progress', `${(Number(range.value) / 10).toFixed(2)}%`);
    range.setAttribute('aria-valuetext', `${formatDuration(position)} / ${formatDuration(duration)}`);
    const playing = !audio.paused && !audio.ended;
    root.classList.toggle('is-playing', playing);
    playButton.setAttribute('aria-label', playing ? t('player.pause') : t('player.play'));
  };

  playButton.addEventListener('click', () => {
    if (audio.paused || audio.ended) audio.play().catch(() => {});
    else audio.pause();
  });

  range.addEventListener('input', () => {
    dragging = true;
    const duration = session.duration;
    if (Number.isFinite(duration)) session.seek((Number(range.value) / 1000) * duration);
    sync();
  });
  range.addEventListener('change', () => {
    dragging = false;
    sync();
  });

  const events = ['timeupdate', 'play', 'pause', 'ended', 'loadedmetadata', 'durationchange', 'emptied'];
  events.forEach((name) => audio.addEventListener(name, sync));
  const stopFrames = session.onFrame(sync);
  sync();

  return {
    sync,
    destroy() {
      events.forEach((name) => audio.removeEventListener(name, sync));
      stopFrames();
      root.replaceChildren();
    },
  };
}
