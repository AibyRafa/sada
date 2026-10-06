/**
 * SADA — DEMO DATA ONLY.
 *
 * Illustrative values used by mock-api.js so the interface can be demonstrated
 * end-to-end without the FastAPI backend. These numbers are NOT produced by any
 * model, are not accuracy claims, and are always displayed with a "demo" badge.
 * The shapes below follow the backend response contract (see README).
 */

/** Placeholder reference figures. Real figures are configured on the backend
 *  after approval of the reference library (public, consented recordings). */
export const MOCK_SPEAKERS = [
  {
    id: 'ref_a',
    name: 'الشخصية المرجعية (أ)',
    role: 'عالِم',
    reference_count: 6,
    official_source: { label: 'القنوات الرسمية للشخصية المرجعية (أ)', url: null },
  },
  {
    id: 'ref_b',
    name: 'الشخصية المرجعية (ب)',
    role: 'قارئ',
    reference_count: 5,
    official_source: { label: 'القنوات الرسمية للشخصية المرجعية (ب)', url: null },
  },
  {
    id: 'ref_c',
    name: 'الشخصية المرجعية (ج)',
    role: 'خطيب',
    reference_count: 4,
    official_source: { label: 'القنوات الرسمية للشخصية المرجعية (ج)', url: null },
  },
];

/** Simulated pipeline timing (ms) for the demo progress view. */
export const MOCK_STAGE_TIMELINE = [
  { id: 'preprocess', ms: 900 },
  { id: 'voiceprint', ms: 1400 },
  { id: 'acoustic', ms: 1500 },
  { id: 'splice', ms: 1100 },
  { id: 'fusion', ms: 700 },
  { id: 'report', ms: 500 },
];

/** Demo scenario chosen from the file name when the panel is set to "auto". */
export const SCENARIO_KEYWORDS = [
  ['likely_synthetic', /(^|[^a-z])(synthetic|fake|cloned?|deepfake|tts)([^a-z]|$)|مزيف|مزيّف|اصطناعي|مستنسخ/i],
  ['inconclusive', /(^|[^a-z])(inconclusive|unclear|uncertain|noisy)([^a-z]|$)|غير[\s_-]?حاسم/i],
  ['likely_authentic', /(^|[^a-z])(authentic|genuine|real|original)([^a-z]|$)|أصلي|اصلي|حقيقي/i],
];

export const mockResults = {
  likely_authentic: {
    status: 'likely_authentic',
    confidence: 0.86,
    decision_threshold: 0.7,
    voiceprint: { match: 0.91, flag: null, references_compared: 6 },
    acoustic_analysis: {
      score: 0.88,
      pitch_stability: 0.87,
      high_frequency_energy: 0.84,
      pause_regularity: 0.9,
      anomalies: [],
    },
    flagged_segments: [],
    splice_analysis: {
      score: 0.91,
      cut_continuity: 0.93,
      sequence_naturalness: 0.9,
      voice_consistency: 0.92,
      anomalies: [],
    },
    spectrogram: null,
    recommendation:
      'يمكن الاطمئنان مبدئيًا إلى نسبة الصوت، مع بقاء المصدر الرسمي مرجعًا عند الحاجة إلى اعتماد المحتوى أو الاستشهاد به.',
    observations: [
      'تتسق البصمة الصوتية مع التسجيلات المرجعية للشخصية دون نمط تطابق غير طبيعي.',
      'جاءت الخصائص الصوتية المقيسة ضمن النطاق المعتاد للكلام الطبيعي.',
    ],
  },

  inconclusive: {
    status: 'inconclusive',
    confidence: 0.54,
    decision_threshold: 0.7,
    voiceprint: { match: 0.68, flag: null, references_compared: 6 },
    acoustic_analysis: {
      score: 0.57,
      pitch_stability: 0.63,
      high_frequency_energy: 0.49,
      pause_regularity: 0.61,
      anomalies: ['ضجيج خلفي وضغط صوتي متكرر يحدّان من دقة قياس الترددات العالية.'],
    },
    flagged_segments: [],
    splice_analysis: {
      score: 0.6,
      cut_continuity: 0.66,
      sequence_naturalness: 0.58,
      voice_consistency: 0.62,
      anomalies: ['الضغط الصوتي المتكرر يحدّ من القدرة على تمييز نقاط الوصل بين أجزاء الكلام.'],
    },
    spectrogram: null,
    recommendation: 'ننصح بالرجوع إلى المصدر الرسمي قبل اعتماد المحتوى أو مشاركته.',
    observations: [
      'تباين بين المسارين: البصمة الصوتية تُظهر تشابهًا متوسطًا، والخصائص الصوتية تُظهر مؤشرات مختلطة.',
      'جودة التسجيل في أجزاء من المقطع لا تكفي لترجيح أي من الاحتمالين.',
    ],
  },

  likely_synthetic: {
    status: 'likely_synthetic',
    confidence: 0.83,
    decision_threshold: 0.7,
    voiceprint: { match: 0.97, flag: 'unusually_high_match', references_compared: 6 },
    acoustic_analysis: {
      score: 0.29,
      pitch_stability: 0.24,
      high_frequency_energy: 0.33,
      pause_regularity: 0.21,
      anomalies: [
        'ثبات في طبقة الصوت يتجاوز المعتاد في الكلام الطبيعي.',
        'انتظام شبه آلي في مدد التوقفات بين الجمل.',
      ],
    },
    flagged_segments: [],
    splice_analysis: {
      score: 0.31,
      cut_continuity: 0.28,
      sequence_naturalness: 0.35,
      voice_consistency: 0.3,
      anomalies: [
        'انقطاع حاد في ضجيج الخلفية عند نقطة وصل محتملة.',
        'تبدّل في خصائص الصوت بين عبارتين متتاليتين.',
      ],
    },
    spectrogram: null,
    recommendation:
      'ننصح بعدم مشاركة المقطع أو الاعتماد عليه، والتحقق من المصدر الرسمي للشخصية المنسوب إليها.',
    observations: [
      'تطابق البصمة الصوتية مرتفع على نحو غير معتاد، وهو نمط قد يظهر في الأصوات المستنسخة.',
      'تتركز المؤشرات الاصطناعية في مقاطع محددة موضحة على التمثيل الطيفي.',
    ],
  },
};

/** Flagged segments as fractions of the clip, scaled to the real duration. */
const MOCK_SEGMENT_TEMPLATES = {
  likely_authentic: [],
  inconclusive: [{ from: 0.58, to: 0.7, reason: 'ضجيج خلفي يحدّ من موثوقية التحليل في هذا الجزء' }],
  likely_synthetic: [
    { from: 0.14, to: 0.21, reason: 'تغيّر مفاجئ في الخصائص الصوتية' },
    { from: 0.46, to: 0.53, reason: 'نمط توقفات منتظم على نحو غير معتاد' },
    { from: 0.74, to: 0.82, reason: 'طاقة ترددات عالية غير متسقة مع بقية المقطع' },
  ],
};

/** Splice findings, as fractions of the clip. A cut is an instant (`at`); the others are ranges.
 *  Positioned away from MOCK_SEGMENT_TEMPLATES so the demo markers do not overlap. */
const MOCK_SPLICE_TEMPLATES = {
  likely_authentic: [],
  inconclusive: [],
  likely_synthetic: [
    { type: 'cut', at: 0.33, confidence: 0.84, reason: 'انقطاع حاد في ضجيج الخلفية عند نقطة وصل محتملة' },
    { type: 'voice_swap', from: 0.6, to: 0.66, confidence: 0.79, reason: 'تبدّل في خصائص الصوت بين عبارتين متتاليتين' },
    { type: 'unnatural_sequence', from: 0.89, to: 0.95, confidence: 0.72, reason: 'انتقال بين كلمتين بإيقاع لا يشبه الكلام المتصل' },
  ],
};

const round1 = (value) => Math.round(value * 10) / 10;

function randomId() {
  const bytes = new Uint8Array(6);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

/** Assembles a full contract-shaped response for one scenario. */
export function buildMockResult(scenario, { speaker, duration, processingMs }) {
  const result = JSON.parse(JSON.stringify(mockResults[scenario]));

  result.flagged_segments = Number.isFinite(duration)
    ? MOCK_SEGMENT_TEMPLATES[scenario].map(({ from, to, reason }) => {
        const start = round1(from * duration);
        const end = round1(Math.min(duration, Math.max(to * duration, start + 1)));
        return { start, end, reason };
      })
    : [];

  // Without a known duration the findings are omitted entirely, so the UI never claims "none detected".
  if (Number.isFinite(duration)) {
    result.splice_analysis.findings = MOCK_SPLICE_TEMPLATES[scenario].map((item) => {
      const { type, confidence, reason } = item;
      if (item.at != null) return { type, time: round1(item.at * duration), confidence, reason };
      const start = round1(item.from * duration);
      const end = round1(Math.min(duration, Math.max(item.to * duration, start + 1)));
      return { type, start, end, confidence, reason };
    });
  }

  result.speaker = { id: speaker.id, name: speaker.name };
  result.duration = Number.isFinite(duration) ? round1(duration) : null;
  result.official_source = speaker.official_source;
  result.sources = [
    {
      type: 'reference_recording',
      title: `التسجيلات المرجعية — ${speaker.name}`,
      description: 'تسجيلات علنية وبموافقة ضمن المكتبة المرجعية للمشروع (بيانات توضيحية في الوضع التجريبي).',
      url: null,
    },
    {
      type: 'methodology',
      title: 'منهجية التحقق ثنائي المسار',
      description: 'مطابقة البصمة الصوتية وتحليل الخصائص الصوتية، ثم دمج المؤشرات مع الامتناع عند عدم كفاية الأدلة.',
      url: 'index.html#how',
    },
    {
      type: 'official_source',
      title: speaker.official_source.label,
      description: 'المرجع النهائي للتحقق من صدور المقطع عن الشخصية.',
      url: speaker.official_source.url,
    },
  ];
  result.meta = {
    analysis_id: `demo-${randomId()}`,
    analyzed_at: new Date().toISOString(),
    mode: 'mock',
    models: {
      speaker_encoder: 'نموذج تجريبي (mock)',
      artifact_classifier: 'نموذج تجريبي (mock)',
      splice_detector: 'نموذج تجريبي (mock)',
    },
    reference_set: 'demo',
    processing_ms: Math.round(processingMs),
  };
  return result;
}
