/**
 * SADA — Mock implementation of the verification API.
 *
 * Same interface as the live client in api.js, so the UI cannot tell them
 * apart. Runs entirely in the browser: the clip is never uploaded anywhere.
 * Progress stages are simulated for demonstration and labelled as such.
 */

import { CONFIG } from './config.js';
import { SadaError, abortError } from './errors.js';
import { readDuration } from './audio.js';
import { downloadLinkedAudio } from './link.js';
import {
  MOCK_SPEAKERS,
  MOCK_STAGE_TIMELINE,
  SCENARIO_KEYWORDS,
  buildMockResult,
} from './mock-data.js';

const STORAGE_KEY = 'sada.demo-settings';
const SCENARIOS = ['auto', 'likely_authentic', 'inconclusive', 'likely_synthetic'];
const SIMULATED_ERRORS = ['none', 'backend_unavailable', 'processing_failure', 'unsupported_speaker'];

let settings = loadSettings();

function loadSettings() {
  let stored = {};
  try {
    stored = JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) || '{}');
  } catch {
    stored = {};
  }
  const scenario = CONFIG.demo.scenario ?? stored.scenario;
  const error = CONFIG.demo.simulate ?? stored.error;
  return {
    scenario: SCENARIOS.includes(scenario) ? scenario : 'auto',
    error: SIMULATED_ERRORS.includes(error) ? error : 'none',
  };
}

function saveSettings() {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch {
    /* storage unavailable (private mode) — settings stay in memory */
  }
}

function delay(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError());
      return;
    }
    const onAbort = () => {
      window.clearTimeout(timer);
      reject(abortError());
    };
    const timer = window.setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

function resolveScenario(fileName) {
  if (settings.scenario !== 'auto') return settings.scenario;
  const name = fileName.toLowerCase();
  const match = SCENARIO_KEYWORDS.find(([, pattern]) => pattern.test(name));
  // Without an explicit choice the demo shows the safest outcome.
  return match ? match[0] : 'inconclusive';
}

export const mockApi = {
  mode: 'mock',

  async getSpeakers({ signal } = {}) {
    await delay(350, signal);
    return JSON.parse(JSON.stringify(MOCK_SPEAKERS));
  },

  async verifyAudio(file, speakerId, { signal, onStage } = {}) {
    const startedAt = performance.now();
    const simulated = settings.error;

    if (simulated === 'backend_unavailable') {
      await delay(900, signal);
      throw new SadaError('backend_unavailable');
    }

    const speaker = MOCK_SPEAKERS.find((item) => item.id === speakerId);
    if (!speaker || simulated === 'unsupported_speaker') {
      await delay(600, signal);
      throw new SadaError('unsupported_speaker');
    }

    for (const stage of MOCK_STAGE_TIMELINE) {
      onStage?.(stage.id, 'active');
      await delay(stage.ms, signal);
      if (simulated === 'processing_failure' && stage.id === 'acoustic') {
        throw new SadaError('processing_failure');
      }
      onStage?.(stage.id, 'done');
    }

    const duration = await readDuration(file);
    return buildMockResult(resolveScenario(file.name), {
      speaker,
      duration,
      processingMs: performance.now() - startedAt,
    });
  },

  /**
   * Direct download from the browser. Only works for a direct link to an audio file whose
   * server allows cross-origin reads (CORS); the live client has the backend do this instead.
   */
  async fetchAudioFromLink(link, { signal } = {}) {
    return downloadLinkedAudio(
      link,
      (requestSignal) =>
        fetch(link.href, { signal: requestSignal, credentials: 'omit', referrerPolicy: 'no-referrer' }),
      { signal },
    );
  },

  /** Demo-only controls, exposed to the UI through api.demo. */
  demo: {
    scenarios: SCENARIOS,
    errors: SIMULATED_ERRORS,
    getSettings: () => ({ ...settings }),
    setSettings(patch) {
      const next = { ...settings, ...patch };
      settings = {
        scenario: SCENARIOS.includes(next.scenario) ? next.scenario : 'auto',
        error: SIMULATED_ERRORS.includes(next.error) ? next.error : 'none',
      };
      saveSettings();
      return { ...settings };
    },
  },
};
