/**
 * SADA — Spectrogram rendering.
 *
 * Two sources are supported:
 *   1. Backend-provided spectrogram (image URL/base64, or a 0–1 matrix).
 *   2. A local STFT computed in the browser from the selected clip — a plain
 *      signal-processing view of the audio, used when the backend sends none.
 * Neither is an authenticity analysis; flagged segments always come from the
 * verification result.
 */

import { fitCanvas } from './ui.js';

/* ---- Colour map (warm "copper" ramp matching the SADA palette) ----------- */

const COLOR_STOPS = [
  [0.0, [20, 15, 12]],
  [0.25, [62, 38, 30]],
  [0.5, [126, 66, 38]],
  [0.72, [190, 120, 58]],
  [0.88, [228, 184, 112]],
  [1.0, [252, 244, 222]],
];

const LUT = (() => {
  const table = new Uint8ClampedArray(256 * 3);
  for (let i = 0; i < 256; i += 1) {
    const x = i / 255;
    let s = 0;
    while (s < COLOR_STOPS.length - 2 && x > COLOR_STOPS[s + 1][0]) s += 1;
    const [x0, c0] = COLOR_STOPS[s];
    const [x1, c1] = COLOR_STOPS[s + 1];
    const f = (x - x0) / (x1 - x0);
    for (let k = 0; k < 3; k += 1) table[i * 3 + k] = c0[k] + (c1[k] - c0[k]) * f;
  }
  return table;
})();

/* ---- Frequency scales ---------------------------------------------------- */

const hzToMel = (hz) => 2595 * Math.log10(1 + hz / 700);
const melToHz = (mel) => 700 * (10 ** (mel / 2595) - 1);

/** Vertical position (0 = bottom, 1 = top) of a frequency on the display. */
export function frequencyPosition(hz, maxHz, scale = 'mel') {
  if (scale === 'linear') return hz / maxHz;
  return hzToMel(hz) / hzToMel(maxHz);
}

/* ---- FFT (iterative radix-2, in place) ----------------------------------- */

function fft(re, im) {
  const n = re.length;
  for (let i = 1, j = 0; i < n; i += 1) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      let tmp = re[i]; re[i] = re[j]; re[j] = tmp;
      tmp = im[i]; im[i] = im[j]; im[j] = tmp;
    }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const half = len >> 1;
    const angle = (-2 * Math.PI) / len;
    const wRe = Math.cos(angle);
    const wIm = Math.sin(angle);
    for (let i = 0; i < n; i += len) {
      let curRe = 1;
      let curIm = 0;
      for (let k = 0; k < half; k += 1) {
        const a = i + k;
        const b = a + half;
        const tRe = re[b] * curRe - im[b] * curIm;
        const tIm = re[b] * curIm + im[b] * curRe;
        re[b] = re[a] - tRe;
        im[b] = im[a] - tIm;
        re[a] += tRe;
        im[a] += tIm;
        const nextRe = curRe * wRe - curIm * wIm;
        curIm = curRe * wIm + curIm * wRe;
        curRe = nextRe;
      }
    }
  }
}

/* ---- Local STFT ---------------------------------------------------------- */

/**
 * Computes a display-ready spectrogram image (RGBA) from mono samples.
 * Rows are mel-spaced from 0 Hz (bottom) to maxHz (top).
 */
export function computeSpectrogram(samples, sampleRate, {
  columns = 800,
  rows = 200,
  fftSize = 1024,
  maxHz = 16000,
  dynamicRangeDb = 80,
} = {}) {
  const topHz = Math.min(maxHz, sampleRate / 2);
  const bins = fftSize / 2;
  const binHz = sampleRate / fftSize;
  const window = new Float32Array(fftSize);
  for (let i = 0; i < fftSize; i += 1) window[i] = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (fftSize - 1));

  // Row edges in FFT-bin units (row 0 = top = highest frequency).
  const melTop = hzToMel(topHz);
  const edges = new Float32Array(rows + 1);
  for (let r = 0; r <= rows; r += 1) edges[r] = melToHz(melTop * (1 - r / rows)) / binHz;

  const re = new Float32Array(fftSize);
  const im = new Float32Array(fftSize);
  const power = new Float32Array(bins);
  const levels = new Float32Array(columns * rows);
  let maxDb = -Infinity;

  for (let c = 0; c < columns; c += 1) {
    const center = Math.floor(((c + 0.5) * samples.length) / columns);
    const start = center - fftSize / 2;
    for (let i = 0; i < fftSize; i += 1) {
      const index = start + i;
      re[i] = index >= 0 && index < samples.length ? samples[index] * window[i] : 0;
      im[i] = 0;
    }
    fft(re, im);
    for (let k = 0; k < bins; k += 1) power[k] = re[k] * re[k] + im[k] * im[k];

    for (let r = 0; r < rows; r += 1) {
      const lo = Math.min(bins - 1, Math.max(0, Math.floor(edges[r + 1])));
      const hi = Math.min(bins - 1, Math.max(lo, Math.ceil(edges[r]) - 1));
      let sum = 0;
      for (let k = lo; k <= hi; k += 1) sum += power[k];
      const db = 10 * Math.log10(sum / (hi - lo + 1) + 1e-12);
      levels[r * columns + c] = db;
      if (db > maxDb) maxDb = db;
    }
  }

  const floor = maxDb - dynamicRangeDb;
  const image = new Uint8ClampedArray(columns * rows * 4);
  for (let i = 0; i < levels.length; i += 1) {
    const v = Math.min(1, Math.max(0, (levels[i] - floor) / dynamicRangeDb));
    const lut = Math.round(v * 255) * 3;
    image[i * 4] = LUT[lut];
    image[i * 4 + 1] = LUT[lut + 1];
    image[i * 4 + 2] = LUT[lut + 2];
    image[i * 4 + 3] = 255;
  }
  return { image, columns, rows, maxHz: topHz, scale: 'mel' };
}

/**
 * Converts a backend matrix (time × frequency, values 0–1, low→high frequency)
 * into the same image structure.
 */
export function matrixToSpectrogram(matrix, { maxHz, scale = 'mel' } = {}) {
  const columns = matrix.length;
  const rows = matrix[0].length;
  const image = new Uint8ClampedArray(columns * rows * 4);
  for (let c = 0; c < columns; c += 1) {
    for (let r = 0; r < rows; r += 1) {
      const value = Math.min(1, Math.max(0, Number(matrix[c][rows - 1 - r]) || 0));
      const lut = Math.round(value * 255) * 3;
      const o = (r * columns + c) * 4;
      image[o] = LUT[lut];
      image[o + 1] = LUT[lut + 1];
      image[o + 2] = LUT[lut + 2];
      image[o + 3] = 255;
    }
  }
  return { image, columns, rows, maxHz, scale };
}

/** Paints a computed spectrogram, stretched to the canvas' CSS size. */
export function paintSpectrogram(canvas, spectrogram) {
  if (!spectrogram.bitmap) {
    const offscreen = document.createElement('canvas');
    offscreen.width = spectrogram.columns;
    offscreen.height = spectrogram.rows;
    offscreen
      .getContext('2d')
      .putImageData(new ImageData(spectrogram.image, spectrogram.columns, spectrogram.rows), 0, 0);
    spectrogram.bitmap = offscreen;
  }
  const { ctx, width, height } = fitCanvas(canvas);
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.clearRect(0, 0, width, height);
  ctx.drawImage(spectrogram.bitmap, 0, 0, width, height);
}

/** Axis ticks in Hz that fit under maxHz. */
export function frequencyTicks(maxHz) {
  return [500, 1000, 2000, 4000, 8000, 16000].filter((hz) => hz <= maxHz);
}

/** "Nice" time ticks (seconds) for an axis of the given duration. */
export function timeTicks(duration, maxTicks = 7) {
  if (!Number.isFinite(duration) || duration <= 0) return [];
  const steps = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600];
  const step = steps.find((s) => duration / s <= maxTicks - 1) ?? 900;
  const ticks = [];
  // Keep a clear gap before the final (exact duration) tick so labels never collide.
  for (let s = 0; s <= duration - step * 0.6; s += step) ticks.push(s);
  ticks.push(duration);
  return ticks;
}
