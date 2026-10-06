/**
 * SADA — DOM helpers, formatters and shared UI pieces.
 * Data from the API is always inserted as text (never as HTML).
 */

import { CONFIG } from './config.js';
import { t, LOCALE } from './i18n.js';

const SVG_NS = 'http://www.w3.org/2000/svg';
const SPRITE_URL = 'assets/icons/sprite.svg';

/* ---- Element creation ---------------------------------------------------- */

/**
 * h('button', { class: 'btn', onClick: fn, 'aria-label': '…' }, child, …)
 * `text` sets textContent; `on*` functions become listeners; true → empty attribute.
 */
export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props ?? {})) {
    if (value == null || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key === 'text') el.textContent = value;
    else if (key === 'dataset') Object.assign(el.dataset, value);
    else if (key === 'style' && typeof value === 'object') {
      for (const [prop, styleValue] of Object.entries(value)) {
        if (prop.startsWith('--')) el.style.setProperty(prop, styleValue);
        else el.style[prop] = styleValue;
      }
    } else if (key.startsWith('on') && typeof value === 'function') {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (value === true) el.setAttribute(key, '');
    else el.setAttribute(key, String(value));
  }
  append(el, children);
  return el;
}

function append(parent, children) {
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false) continue;
    parent.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

export function icon(name, { className = '', label = null } = {}) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', `icon ${className}`.trim());
  if (label) {
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', label);
  } else {
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
  }
  const use = document.createElementNS(SVG_NS, 'use');
  use.setAttribute('href', `${SPRITE_URL}#i-${name}`);
  svg.append(use);
  return svg;
}

/** Left-to-right isolated run (numbers, times, identifiers) inside RTL text. */
export function ltr(text, className = '') {
  return h('bdi', { dir: 'ltr', class: `ltr ${className}`.trim(), text });
}

/* ---- Formatting ---------------------------------------------------------- */

const decimalFormat = new Intl.NumberFormat(`${LOCALE}-u-nu-latn`, { maximumFractionDigits: 1 });
const dateTimeFormat = new Intl.DateTimeFormat(`${LOCALE}-u-ca-gregory-nu-latn`, {
  dateStyle: 'medium',
  timeStyle: 'medium',
});

export function formatNumber(value) {
  return decimalFormat.format(value);
}

/** 0–1 → "87%". Integers only, to avoid false precision. */
export function formatPercent(value) {
  return Number.isFinite(value) ? `${Math.round(value * 100)}%` : '—';
}

/** Seconds → "mm:ss" (or "h:mm:ss"). */
export function formatDuration(seconds) {
  if (!Number.isFinite(seconds)) return '—';
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = String(Math.floor((total % 3600) / 60)).padStart(2, '0');
  const secs = String(total % 60).padStart(2, '0');
  return hours ? `${hours}:${minutes}:${secs}` : `${minutes}:${secs}`;
}

/** Seconds → "2.6 ث", "10 د" or "mm:ss" for limits and short clips. */
export function formatDurationHuman(seconds) {
  if (!Number.isFinite(seconds)) return '—';
  if (seconds < 60) return `${decimalFormat.format(Math.floor(seconds * 10) / 10)} ث`;
  if (seconds % 60 === 0) return `${decimalFormat.format(seconds / 60)} د`;
  return formatDuration(seconds);
}

export function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return '—';
  const mb = bytes / (1024 * 1024);
  if (mb >= 1) return `${decimalFormat.format(mb)} ${t('units.mb')}`;
  return `${decimalFormat.format(Math.max(1, Math.round(bytes / 1024)))} ${t('units.kb')}`;
}

export function formatDateTime(iso) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : dateTimeFormat.format(date);
}

export function supportedFormatsLabel() {
  return CONFIG.formats.supported.map((ext) => ext.toUpperCase()).join('، ');
}

/* ---- Errors -------------------------------------------------------------- */

/** Interpolated {title, detail, why, next} copy for a SadaError. */
export function errorCopy(error) {
  const code = error?.code ?? 'processing_failure';
  const details = error?.details ?? {};
  const { limits } = CONFIG;
  return t(`errors.${code}`, {
    name: details.name ?? '',
    ext: details.ext ?? '',
    size: Number.isFinite(details.size) ? formatBytes(details.size) : '',
    duration: Number.isFinite(details.duration) ? formatDurationHuman(details.duration) : '',
    max: code === 'file_too_long' ? formatDurationHuman(limits.maxDurationSec) : formatBytes(limits.maxFileBytes),
    min: formatDurationHuman(limits.minDurationSec),
    formats: supportedFormatsLabel(),
  });
}

/** Children for an `.alert--error` box: what happened, why, and what to do next. */
export function errorAlertContent(error, actions = []) {
  const copy = errorCopy(error);
  return [
    icon('alert', { className: 'alert__icon' }),
    h('p', { class: 'alert__title', text: copy.title }),
    copy.detail ? h('p', { class: 'alert__row', text: copy.detail }) : null,
    h('p', { class: 'alert__row' }, h('strong', { text: `${t('errorLabels.why')}: ` }), copy.why),
    h('p', { class: 'alert__row' }, h('strong', { text: `${t('errorLabels.next')} ` }), copy.next),
    actions.length ? h('div', { class: 'alert__actions' }, actions) : null,
  ];
}

/* ---- Accessibility & environment ----------------------------------------- */

export function announce(message) {
  const region = document.getElementById('sr-announcer');
  if (!region) return;
  region.textContent = '';
  window.setTimeout(() => {
    region.textContent = message;
  }, 80);
}

export function prefersReducedMotion() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
}

export function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

/* ---- Canvas -------------------------------------------------------------- */

/** Sizes a canvas backing store to its CSS box × devicePixelRatio. */
export function fitCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));
  if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
    canvas.width = width * dpr;
    canvas.height = height * dpr;
  }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, width, height };
}

/** Calls `callback` after layout changes, throttled to one frame. */
export function observeResize(element, callback) {
  if (!('ResizeObserver' in window)) return () => {};
  let frame = 0;
  const observer = new ResizeObserver(() => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(callback);
  });
  observer.observe(element);
  return () => {
    cancelAnimationFrame(frame);
    observer.disconnect();
  };
}
