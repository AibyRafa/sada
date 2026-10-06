/**
 * SADA — Result screen.
 * Renders only what the (normalised) result contains: a missing value hides
 * its widget instead of being filled with a placeholder number.
 */

import { CONFIG } from './config.js';
import { t, tPlural } from './i18n.js';
import { RESULT_STATUS } from './state.js';
import { createPlayer } from './audio.js';
import {
  computeSpectrogram,
  matrixToSpectrogram,
  paintSpectrogram,
  frequencyPosition,
  frequencyTicks,
  timeTicks,
} from './spectrogram.js';
import {
  h,
  icon,
  ltr,
  formatPercent,
  formatDuration,
  formatDateTime,
  formatNumber,
  observeResize,
} from './ui.js';

const TONE = {
  [RESULT_STATUS.AUTHENTIC]: 'tone-authentic',
  [RESULT_STATUS.INCONCLUSIVE]: 'tone-inconclusive',
  [RESULT_STATUS.SYNTHETIC]: 'tone-synthetic',
};

const STATUS_ICON = {
  [RESULT_STATUS.AUTHENTIC]: 'shield-check',
  [RESULT_STATUS.INCONCLUSIVE]: 'shield-minus',
  [RESULT_STATUS.SYNTHETIC]: 'shield-alert',
};

const SOURCE_ICON = {
  reference_recording: 'mic',
  methodology: 'book',
  official_source: 'link',
  traceability: 'list',
  other: 'info',
};

/**
 * @param {HTMLElement} root
 * @param {object} result   normalised result (api.normalizeResult)
 * @param {{fileMeta: object, speaker: object, session: object, audio: HTMLAudioElement,
 *          onRestart: Function, onEdit: Function}} ctx
 */
export function renderResult(root, result, ctx) {
  root.cleanup?.();
  const disposers = [];
  const mounted = [];
  const speakerName = result.speaker?.name ?? ctx.speaker?.name ?? '';
  const duration = result.meta.duration ?? ctx.fileMeta?.duration ?? ctx.session.duration;

  root.className = TONE[result.status];
  root.replaceChildren(
    renderHero(result, ctx, speakerName, duration),
    renderEvidence(result),
    renderSpectrogramSection(result, ctx, duration, disposers, mounted),
    renderSources(result),
    renderLimits(result),
    h(
      'div',
      { class: 'result-actions' },
      h('button', { type: 'button', class: 'btn btn--primary btn--lg', onClick: ctx.onRestart }, icon('upload'), t('result.next.restart')),
      h('button', { type: 'button', class: 'btn btn--secondary btn--lg', onClick: ctx.onEdit }, t('result.next.edit')),
    ),
  );

  mounted.forEach((fn) => fn());
  root.cleanup = () => {
    disposers.forEach((dispose) => dispose());
    root.cleanup = null;
  };
}

/* ---- Hero: verdict, confidence and next action --------------------------- */

function renderHero(result, ctx, speakerName, duration) {
  const copy = t(`result.status.${result.status}`, { speaker: speakerName });

  return h(
    'section',
    { class: 'result-hero', 'aria-labelledby': 'result-title' },
    result.meta.isMock ? h('p', { class: 'demo-flag' }, icon('flask'), t('result.demoFlag')) : null,
    h(
      'div',
      { class: 'result-hero__grid' },
      h(
        'div',
        { class: 'result-hero__status' },
        h('span', { class: 'result-hero__icon' }, icon(STATUS_ICON[result.status])),
        h(
          'div',
          {},
          h('p', { class: 'result-hero__eyebrow', text: t('result.eyebrow') }),
          h('h2', { id: 'result-title', class: 'result-hero__title', tabindex: '-1', text: copy.title }),
          h('p', { class: 'result-hero__lead', text: copy.lead }),
          h('p', { class: 'result-hero__note', text: copy.note }),
          h(
            'dl',
            { class: 'clip-facts' },
            fact(t('result.facts.clip'), ctx.fileMeta?.name, { title: ctx.fileMeta?.name }),
            fact(t('result.facts.speaker'), speakerName),
            fact(t('result.facts.duration'), Number.isFinite(duration) ? ltr(formatDuration(duration)) : null),
          ),
        ),
      ),
      renderConfidence(result),
    ),
    renderNextAction(result, ctx, speakerName),
  );
}

function fact(label, value, attrs = {}) {
  if (value == null || value === '') return null;
  return h('div', {}, h('dt', { text: `${label}:` }), h('dd', attrs, value));
}

function renderConfidence(result) {
  const { confidence, decisionThreshold: threshold, status } = result;
  const head = h(
    'div',
    { class: 'confidence__head' },
    h('p', { class: 'confidence__label', id: 'confidence-label', text: t('result.confidence.label') }),
    confidence != null ? h('p', { class: 'confidence__value' }, ltr(formatPercent(confidence))) : null,
  );

  if (confidence == null) {
    return h('div', { class: 'confidence' }, head, h('p', { class: 'confidence__missing', text: t('result.confidence.missing') }));
  }

  // Explain the threshold only when the verdict and the numbers agree.
  const reached = threshold != null ? confidence >= threshold : null;
  let verdictText = null;
  if (reached === false && status === RESULT_STATUS.INCONCLUSIVE) verdictText = t('result.confidence.belowThreshold');
  if (reached === true && status !== RESULT_STATUS.INCONCLUSIVE) verdictText = t('result.confidence.aboveThreshold');

  const meter = h(
    'div',
    {
      class: 'meter',
      role: 'meter',
      'aria-labelledby': 'confidence-label',
      'aria-valuemin': '0',
      'aria-valuemax': '100',
      'aria-valuenow': String(Math.round(confidence * 100)),
      'aria-valuetext': verdictText
        ? t('result.confidence.valueText', { value: formatPercent(confidence), verdict: verdictText })
        : formatPercent(confidence),
    },
    h('span', { class: 'meter__fill', style: { width: `${confidence * 100}%` } }),
    threshold != null
      ? h(
          'span',
          { class: 'meter__threshold', style: { insetInlineStart: `${threshold * 100}%` }, 'aria-hidden': 'true' },
          h('span', { class: 'meter__threshold-label', text: t('result.confidence.threshold', { value: formatPercent(threshold) }) }),
        )
      : null,
  );

  return h(
    'div',
    { class: 'confidence' },
    head,
    meter,
    h('p', { class: 'confidence__caption', text: t('result.confidence.caption') }),
    verdictText ? h('p', { class: 'confidence__verdict', text: verdictText }) : null,
  );
}

function renderNextAction(result, ctx, speakerName) {
  const emphasise = result.status !== RESULT_STATUS.AUTHENTIC;
  const recommendation = result.recommendation ?? t(`result.recommendation.${result.status}`);
  const official = result.officialSource ?? ctx.speaker?.officialSource ?? null;

  let action;
  if (official?.url) {
    action = h(
      'a',
      {
        class: `btn ${emphasise ? 'btn--primary' : 'btn--secondary'}`,
        href: official.url,
        target: '_blank',
        rel: 'noopener noreferrer',
      },
      icon('external', { className: 'icon--mirror' }),
      t('result.next.official'),
      h('span', { class: 'visually-hidden', text: ` ${t('common.opensNewTab')}` }),
    );
  } else {
    // No configured URL: explain the action instead of inventing a link.
    action = h(
      'div',
      { class: 'official-placeholder' },
      h('p', { class: 'official-placeholder__title' }, icon('link'), t('result.next.official')),
      h('p', { class: 'official-placeholder__text', text: t('result.next.officialNoUrl', { speaker: speakerName }) }),
      result.meta.isMock ? h('p', { class: 'official-placeholder__dev', text: t('result.next.officialConfigNote') }) : null,
    );
  }

  return h(
    'div',
    { class: `next-action${emphasise ? ' next-action--emphasis' : ''}` },
    h(
      'div',
      { class: 'next-action__text' },
      h('h3', { class: 'next-action__title' }, icon('arrow-forward', { className: 'icon--mirror' }), t('result.next.title')),
      h('p', { class: 'next-action__rec', text: recommendation }),
    ),
    action,
  );
}

/* ---- Evidence ------------------------------------------------------------ */

function bar(value, color) {
  return h(
    'div',
    { class: 'bar', 'aria-hidden': 'true' },
    h('span', { class: 'bar__fill', style: { width: `${value * 100}%`, ...(color ? { '--bar-color': color } : {}) } }),
  );
}

/** `tone`: a CSS colour that marks the figure as suspicious; `caption`: a note on how to read it. */
function metric(value, label, { tone = null, caption = null } = {}) {
  return h(
    'div',
    { class: 'metric' },
    h(
      'div',
      { class: 'metric__row' },
      h('span', { class: 'metric__label', text: label }),
      h('span', { class: tone ? 'metric__value metric__value--flag' : 'metric__value' }, ltr(formatPercent(value))),
    ),
    bar(value, tone),
    caption ? h('p', { class: 'metric__caption', text: caption }) : null,
  );
}

function pathHead(iconName, kicker, title, id) {
  return h(
    'header',
    { class: 'path-card__head' },
    h('span', { class: 'path-card__icon' }, icon(iconName)),
    h('div', {}, h('p', { class: 'path-card__kicker', text: kicker }), h('h3', { class: 'path-card__title', id, text: title })),
  );
}

function renderVoiceprint({ voiceprint }) {
  const flagKey = voiceprint.flag ? `evidence.pathA.flags.${voiceprint.flag}` : null;
  const knownFlags = ['unusually_high_match', 'unexpected_mismatch'];
  const flagText = flagKey ? t(knownFlags.includes(voiceprint.flag) ? flagKey : 'evidence.pathA.flags.unknown') : null;

  return h(
    'article',
    { class: 'path-card', 'aria-labelledby': 'path-a-title' },
    pathHead('fingerprint', t('evidence.pathA.kicker'), t('evidence.pathA.title'), 'path-a-title'),
    voiceprint.match != null
      ? metric(voiceprint.match, t('evidence.pathA.metric'), {
          // A flagged similarity (too perfect, or unexpectedly low) is shown in the warning colour,
          // so a high figure is never mistaken for a good score.
          tone: voiceprint.flag ? 'var(--status-synthetic)' : null,
          caption: t('evidence.pathA.caption'),
        })
      : h('p', { class: 'path-card__missing', text: t('evidence.notProvided') }),
    flagText ? h('p', { class: 'flag-note' }, icon('alert'), h('span', { text: flagText })) : null,
    h('p', { class: 'path-card__desc', text: t('evidence.pathA.desc') }),
    // The number of reference recordings is not shown to users (it is in reports/ and README).
  );
}

function renderAcoustic({ acoustic }) {
  const indicators = acoustic.indicators.map(({ key, value }) => {
    const copy = t(`evidence.indicators.${key}`);
    const known = typeof copy === 'object';
    return h(
      'li',
      { class: 'indicator' },
      h(
        'div',
        { class: 'indicator__row' },
        h('span', { class: 'indicator__label', text: known ? copy.label : key.replace(/_/g, ' ') }),
        h('span', { class: 'indicator__value' }, ltr(formatPercent(value))),
      ),
      bar(value, 'var(--color-secondary)'),
      known ? h('p', { class: 'indicator__desc', text: copy.desc }) : null,
    );
  });

  return h(
    'article',
    { class: 'path-card', 'aria-labelledby': 'path-b-title' },
    pathHead('sliders', t('evidence.pathB.kicker'), t('evidence.pathB.title'), 'path-b-title'),
    acoustic.score != null
      ? metric(acoustic.score, t('evidence.pathB.metric'))
      : h('p', { class: 'path-card__missing', text: t('evidence.notProvided') }),
    h('p', { class: 'path-card__desc', text: t('evidence.pathB.desc') }),
    indicators.length
      ? [
          h('p', { class: 'scale-note' }, icon('info'), t('evidence.pathB.scale')),
          h('ul', { class: 'indicator-list', role: 'list' }, indicators),
        ]
      : null,
    acoustic.anomalies.length
      ? h(
          'div',
          {},
          h('h4', { class: 'indicator__label', text: t('evidence.pathB.anomaliesTitle') }),
          h('ul', { class: 'anomaly-list', role: 'list' }, acoustic.anomalies.map((item) => h('li', {}, icon('alert'), h('span', { text: item })))),
        )
      : null,
  );
}

function renderFusion(result) {
  const node = (label, value, extraClass = '') =>
    h('span', { class: `fusion__node ${extraClass}`.trim() }, label, value != null ? ltr(formatPercent(value)) : null);
  const arrow = () => h('span', { class: 'fusion__op' }, icon('arrow-forward', { className: 'icon--mirror' }));

  return h(
    'div',
    { class: 'fusion' },
    h(
      'div',
      { class: 'fusion__chain', 'aria-hidden': 'true' },
      node(t('evidence.fusion.pathA'), result.voiceprint.match),
      h('span', { class: 'fusion__op', text: '+' }),
      node(t('evidence.fusion.pathB'), result.acoustic.score),
      arrow(),
      node(t('evidence.fusion.confidence'), result.confidence),
      arrow(),
      h('span', { class: 'fusion__node fusion__node--result' }, icon(STATUS_ICON[result.status]), t(`result.status.${result.status}.short`)),
    ),
    h('p', { class: 'fusion__text' }, h('strong', { text: `${t('evidence.fusion.title')}: ` }), t('evidence.fusion.text')),
  );
}

/* Splice / edit detection: supplementary evidence. Rendered only when the response carries
 * `splice_analysis`; the marked positions themselves are drawn in the spectrogram section. */
function renderSplice({ splice }) {
  if (!splice) return null;

  const indicators = splice.indicators.map(({ key, value }) => {
    const copy = t(`splice.indicators.${key}`);
    return h(
      'li',
      { class: 'indicator' },
      h(
        'div',
        { class: 'indicator__row' },
        h('span', { class: 'indicator__label', text: copy.label }),
        h('span', { class: 'indicator__value' }, ltr(formatPercent(value))),
      ),
      bar(value, 'var(--color-secondary)'),
      h('p', { class: 'indicator__desc', text: copy.desc }),
    );
  });

  // `findings` is null when the backend sent no list: then nothing is claimed either way.
  const count = splice.findings?.length ?? 0;
  let findingsNote = null;
  if (splice.findings != null) {
    findingsNote = count
      ? h(
          'p',
          { class: 'flag-note' },
          icon('scissors'),
          h('span', { text: `${tPlural('plural.spliceFindings', count)}. ${t('splice.findingsOnSpectrogram')}` }),
        )
      : h('p', { class: 'empty-state' }, icon('check'), t('splice.findingsNone'));
  }

  return h(
    'article',
    { class: 'path-card splice-card', 'aria-labelledby': 'splice-title' },
    pathHead('scissors', t('splice.kicker'), t('splice.title'), 'splice-title'),
    splice.score != null
      ? metric(splice.score, t('splice.metric'))
      : h('p', { class: 'path-card__missing', text: t('evidence.notProvided') }),
    findingsNote,
    h('p', { class: 'path-card__desc', text: t('splice.desc') }),
    indicators.length
      ? [
          h('p', { class: 'scale-note' }, icon('info'), t('splice.scale')),
          h('ul', { class: 'indicator-list', role: 'list' }, indicators),
        ]
      : null,
    splice.anomalies.length
      ? h(
          'div',
          {},
          h('h4', { class: 'indicator__label', text: t('splice.anomaliesTitle') }),
          h('ul', { class: 'anomaly-list', role: 'list' }, splice.anomalies.map((item) => h('li', {}, icon('alert'), h('span', { text: item })))),
        )
      : null,
    h('p', { class: 'path-card__meta' }, icon('info'), t('splice.caveat')),
  );
}

function renderEvidence(result) {
  return h(
    'section',
    { class: 'result-section', 'aria-labelledby': 'evidence-title' },
    h(
      'header',
      { class: 'result-section__head' },
      h('h2', { class: 'result-section__title', id: 'evidence-title', text: t('evidence.title') }),
      h('p', { class: 'result-section__lead', text: t('evidence.lead') }),
    ),
    h('div', { class: 'evidence-grid' }, renderVoiceprint(result), renderAcoustic(result)),
    renderFusion(result),
    renderSplice(result),
    result.observations.length
      ? h(
          'div',
          { class: 'observations' },
          h('h3', { class: 'result-section__subtitle' }, icon('report'), t('evidence.observationsTitle')),
          h('ul', { role: 'list' }, result.observations.map((item) => h('li', { text: item }))),
        )
      : null,
  );
}

/* ---- Spectrogram, player and flagged segments ---------------------------- */

function renderSpectrogramSection(result, ctx, duration, disposers, mounted) {
  const { session, audio } = ctx;
  const segments = (result.flaggedSegments ?? []).filter((s) => !Number.isFinite(duration) || s.start < duration);
  const hasDuration = Number.isFinite(duration) && duration > 0;
  const position = (seconds) => `${Math.min(100, Math.max(0, (seconds / duration) * 100))}%`;

  /* Choose the visual source: backend image/matrix first, then local STFT. */
  let visual = null;
  let sourceNote;
  if (result.spectrogram?.kind === 'image') {
    visual = { kind: 'image', ...result.spectrogram };
    sourceNote = t('spectrogram.sourceBackend');
  } else if (result.spectrogram?.kind === 'matrix') {
    visual = { kind: 'canvas', data: matrixToSpectrogram(result.spectrogram.data, result.spectrogram) };
    sourceNote = t('spectrogram.sourceBackend');
  } else if (session.decoded) {
    visual = { kind: 'canvas', data: null }; // computed after mount
    sourceNote = t(result.meta.isMock ? 'spectrogram.sourceLocalMock' : 'spectrogram.sourceLocal');
  } else {
    sourceNote = t('spectrogram.unavailable');
  }

  const maxHz = visual?.kind === 'image'
    ? visual.maxHz
    : visual?.data?.maxHz ?? Math.min(CONFIG.visual.spectrogramMaxHz, (session.decoded?.sampleRate ?? 0) / 2);
  const scale = visual?.kind === 'image' ? visual.scale : visual?.data?.scale ?? 'mel';

  const canvas = visual?.kind === 'canvas'
    ? h('canvas', {
        class: 'spectro__canvas',
        role: 'img',
        'aria-label': t('spectrogram.canvasLabel', { duration: formatDuration(duration), count: segments.length }),
      })
    : null;
  const image = visual?.kind === 'image'
    ? h('img', {
        class: 'spectro__image',
        src: visual.src,
        alt: t('spectrogram.canvasLabel', { duration: formatDuration(duration), count: segments.length }),
      })
    : null;

  const playhead = h('span', { class: 'spectro__playhead', 'aria-hidden': 'true' });
  const overlayButtons = [];
  const listItems = [];

  const playSegment = (segment) => {
    session.playRange(segment.start, segment.end);
  };

  segments.forEach((segment, index) => {
    // Round outward so the displayed range always contains the flagged audio.
    const from = formatDuration(Math.floor(segment.start));
    const to = formatDuration(Math.ceil(segment.end));
    const label = t('segments.listenLabel', { index: index + 1, from, to, reason: segment.reason });
    if (hasDuration) {
      overlayButtons.push(
        h(
          'button',
          {
            type: 'button',
            class: 'spec-segment',
            style: { left: position(segment.start), width: `calc(${position(segment.end)} - ${position(segment.start)})` },
            'aria-label': label,
            onClick: () => playSegment(segment),
          },
          h('span', { class: 'spec-segment__tag', text: String(index + 1) }),
        ),
      );
    }
    listItems.push(
      h(
        'li',
        { class: 'segment' },
        h('span', { class: 'segment__index', 'aria-hidden': 'true', text: String(index + 1) }),
        h(
          'div',
          {},
          h('p', { class: 'segment__time' }, ltr(`${from} – ${to}`)),
          segment.kind
            ? h(
                'p',
                { class: 'segment__kind' },
                icon('scissors'),
                t(`splice.types.${segment.kind}`),
                segment.confidence != null ? [' · ', t('splice.confidence', { value: formatPercent(segment.confidence) })] : null,
              )
            : null,
          h('p', { class: 'segment__reason', text: segment.reason }),
        ),
        h(
          'button',
          { type: 'button', class: 'btn btn--secondary btn--sm', 'aria-label': label, onClick: () => playSegment(segment) },
          icon('headphones'),
          t('segments.listen'),
        ),
      ),
    );
  });

  /* Axes */
  const yAxis = h(
    'div',
    { class: 'spectro__yaxis', 'aria-hidden': 'true' },
    maxHz > 0
      ? frequencyTicks(maxHz).map((hz) =>
          h('span', {
            class: 'spectro__ytick',
            style: { bottom: `${frequencyPosition(hz, maxHz, scale) * 100}%` },
            text: String(hz / 1000),
          }),
        )
      : null,
  );
  const xAxis = h(
    'div',
    { class: 'spectro__xaxis', 'aria-hidden': 'true' },
    hasDuration
      ? timeTicks(duration, window.innerWidth < 640 ? 5 : 7).map((s) =>
          h('span', { class: 'spectro__xtick', style: { left: position(s) }, text: formatDuration(s) }),
        )
      : null,
  );

  const plot = h(
    'div',
    { class: 'spectro__plot' },
    canvas,
    image,
    visual ? null : h('p', { class: 'spectro__unavailable', dir: 'rtl', text: t('spectrogram.unavailable') }),
    h('div', { class: 'spectro__overlay' }, overlayButtons, playhead),
  );

  const playerRoot = h('div', { class: 'result-player' });

  /* Highlight the segment under the playhead; move the playhead. */
  const stopFrames = session.onFrame((time) => {
    if (hasDuration) {
      playhead.style.left = position(time);
      playhead.classList.toggle('is-visible', time > 0 || !audio.paused);
    }
    segments.forEach((segment, index) => {
      const active = time >= segment.start && time < segment.end && !audio.paused;
      overlayButtons[index]?.classList.toggle('is-active', active);
      listItems[index]?.classList.toggle('is-active', active);
    });
  });
  disposers.push(stopFrames);

  mounted.push(() => {
    const player = createPlayer(playerRoot, audio, session);
    disposers.push(() => player.destroy());

    if (visual?.kind === 'canvas') {
      const paint = () => {
        if (!visual.data) {
          const { samples, sampleRate } = session.decoded;
          visual.data = computeSpectrogram(samples, sampleRate, { maxHz: CONFIG.visual.spectrogramMaxHz });
        }
        paintSpectrogram(canvas, visual.data);
      };
      requestAnimationFrame(paint);
      disposers.push(observeResize(canvas, () => visual.data && paintSpectrogram(canvas, visual.data)));
    }
  });

  return h(
    'section',
    { class: 'result-section', 'aria-labelledby': 'spectro-title' },
    h(
      'header',
      { class: 'result-section__head' },
      h('h2', { class: 'result-section__title', id: 'spectro-title', text: t('spectrogram.title') }),
      h('p', { class: 'result-section__lead', text: t('spectrogram.lead') }),
    ),
    h(
      'div',
      { class: 'spectro' },
      h(
        'div',
        { class: 'spectro__frame', dir: 'ltr' },
        h('span', { class: 'spectro__unit', 'aria-hidden': 'true', text: scale === 'linear' ? t('spectrogram.unitLinear') : t('spectrogram.unitMel') }),
        yAxis,
        plot,
        xAxis,
      ),
      h(
        'div',
        { class: 'spectro__legend' },
        h('span', {}, h('span', { class: 'legend-swatch', 'aria-hidden': 'true' }), t('spectrogram.legendFlag')),
        h('span', {}, t('spectrogram.legendLow'), h('span', { class: 'legend-gradient', 'aria-hidden': 'true' }), t('spectrogram.legendHigh')),
      ),
      playerRoot,
      h('p', { class: 'spectro__note' }, icon('info'), h('span', { text: sourceNote })),
    ),
    h(
      'div',
      { class: 'segments' },
      h('h3', { class: 'result-section__subtitle' }, icon('alert'), t('segments.title')),
      result.flaggedSegments == null
        ? h('p', { class: 'empty-state' }, icon('info'), t('segments.notProvided'))
        : segments.length
          ? h('ol', { class: 'segment-list', role: 'list' }, listItems)
          : h('p', { class: 'empty-state' }, icon('check'), t('segments.none')),
    ),
  );
}

/* ---- Sources & traceability ---------------------------------------------- */

function renderSources(result) {
  const sourceItems = result.sources.map((source) =>
    h(
      'li',
      { class: 'source' },
      h('span', { class: 'source__icon' }, icon(SOURCE_ICON[source.type])),
      h(
        'div',
        {},
        h('p', { class: 'source__type', text: t(`sources.types.${source.type}`) }),
        h('p', { class: 'source__title', text: source.title }),
        source.description ? h('p', { class: 'source__desc', text: source.description }) : null,
        source.url
          ? h(
              'a',
              isInternal(source.url)
                ? { class: 'source__link', href: source.url }
                : { class: 'source__link', href: source.url, target: '_blank', rel: 'noopener noreferrer' },
              t('sources.open'),
              isInternal(source.url) ? null : [icon('external', { className: 'icon--mirror' }), h('span', { class: 'visually-hidden', text: ` ${t('common.opensNewTab')}` })],
            )
          : h('p', { class: 'source__nolink', text: t('sources.noLink') }),
      ),
    ),
  );

  const { meta } = result;
  const traceRows = [
    [t('trace.analysisId'), meta.analysisId ? ltr(meta.analysisId, 'mono') : null],
    [t('trace.analyzedAt'), meta.analyzedAt ? formatDateTime(meta.analyzedAt) : null],
    [t('trace.mode'), meta.isMock ? t('trace.modeMock') : t('trace.modeLive')],
    [t('trace.speakerEncoder'), meta.speakerEncoder],
    [t('trace.artifactClassifier'), meta.artifactClassifier],
    [t('trace.spliceDetector'), meta.spliceDetector],
    [t('trace.referenceSet'), meta.referenceSet ? ltr(meta.referenceSet, 'mono') : null],
    [t('trace.processing'), meta.processingMs ? t('trace.seconds', { value: formatNumber(meta.processingMs / 1000) }) : null],
  ].filter(([, value]) => value != null && value !== '');

  return h(
    'section',
    { class: 'result-section', 'aria-labelledby': 'sources-title' },
    h(
      'header',
      { class: 'result-section__head' },
      h('h2', { class: 'result-section__title', id: 'sources-title', text: t('sources.title') }),
      h('p', { class: 'result-section__lead', text: t('sources.lead') }),
    ),
    h(
      'div',
      { class: 'split-grid' },
      sourceItems.length
        ? h('ul', { class: 'source-list', role: 'list' }, sourceItems)
        : h('p', { class: 'empty-state' }, icon('info'), t('sources.empty')),
      h(
        'div',
        { class: 'trace' },
        h('h3', { class: 'result-section__subtitle' }, icon('list'), t('trace.title')),
        h('dl', { class: 'trace-list' }, traceRows.map(([label, value]) => h('div', {}, h('dt', { text: label }), h('dd', {}, value)))),
      ),
    ),
  );
}

function isInternal(url) {
  try {
    return new URL(url).origin === window.location.origin;
  } catch {
    return false;
  }
}

/* ---- Limits & privacy ---------------------------------------------------- */

function renderLimits(result) {
  const items = [...t('limitations.items'), ...result.limitations];
  return h(
    'section',
    { class: 'result-section', 'aria-labelledby': 'limits-title' },
    h(
      'div',
      { class: 'split-grid' },
      h(
        'div',
        {},
        h('h2', { class: 'result-section__subtitle', id: 'limits-title' }, icon('info'), t('limitations.title')),
        h('ul', { class: 'limits-list', role: 'list' }, items.map((item) => h('li', {}, icon('check'), h('span', { text: item })))),
      ),
      h(
        'div',
        { class: 'privacy-note' },
        icon('lock'),
        h(
          'div',
          {},
          h('p', {}, h('strong', { text: `${t('limitations.privacyTitle')}: ` }), t('limitations.privacy')),
          result.meta.isMock ? h('p', { text: t('limitations.privacyMock') }) : null,
          h('p', { text: t('limitations.privacyLocal') }),
        ),
      ),
    ),
  );
}
