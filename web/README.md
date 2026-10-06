# SADA — صدى · Frontend

AI-powered voice authenticity verification for Islamic religious content.
AI Challenge Serving Islamic Content 2026 — **Track 04: Knowledge & Verification Tools**.

A user uploads a clip attributed to a supported reference figure. SADA analyses it on two paths
(voice-identity match and acoustic artifact analysis), fuses them into one confidence level, and returns
one of three outcomes: **likely authentic**, **inconclusive** (refer to the official source), or
**likely synthetic**. It shows the evidence behind the outcome and recommends a next step.
An optional extra check (`splice_analysis`) looks for cuts, unnatural sequences and voice swaps inside the clip.

> SADA assists verification. It does not replace authoritative human judgment, issue fatwas, or judge
> the content of a clip. It assesses only whether the voice is authentic.

## Technology

- Plain HTML5, CSS3 and modern JavaScript (ES modules). No framework, build step or npm dependencies.
- Web Audio API to decode the clip in the browser for the waveform and the local spectrogram (STFT, mel scale).
- Google Fonts: IBM Plex Sans Arabic and IBM Plex Mono. Self-host them if you need zero third-party requests.

## Structure

```text
sada/
├── index.html            Landing page: problem, how it works, outcomes, safety, privacy
├── verify.html           Verification app: upload → speaker → pre-check → analysis → result
├── css/
│   ├── variables.css     Design tokens (colors, type, spacing, radius, motion)
│   ├── global.css        Base styles, layout primitives, header/footer
│   ├── components.css    Buttons, cards, stepper, dropzone, player, stages, meter…
│   ├── pages.css         Landing, verification and result layouts
│   └── responsive.css    Tablet (≤1024px) and mobile (≤640px) layouts
├── js/
│   ├── app.js            Page controller for verify.html
│   ├── config.js         API mode, endpoints, upload limits, formats
│   ├── state.js          Verification state + statuses
│   ├── api.js            Service layer: live FastAPI client + response normalisation
│   ├── mock-api.js       In-browser mock with the same interface (demo mode)
│   ├── mock-data.js      Demo-only scenarios and placeholder speakers (isolated)
│   ├── audio.js          File validation, decoding, waveform, player
│   ├── link.js           Pasted link → File (parsing, download guard, file naming); shared by both API modes
│   ├── link-input.js     "Paste a link" control on the audio step
│   ├── back-to-top.js    Back-to-top button (classic script, loaded by both pages, works from file:// too)
│   ├── spectrogram.js    FFT/STFT, colour map, backend image/matrix rendering
│   ├── analysis.js       Analysis-stage progress view
│   ├── result.js         Result, evidence, spectrogram, segments, sources
│   ├── ui.js             DOM helpers, formatters, error copy
│   ├── i18n.js           All JS-generated UI text (Arabic; add `en` here)
│   └── errors.js         Error codes shared by the API layer and the UI
└── assets/
    ├── icons/            sprite.svg (icon set) and favicon.svg (logo mark)
    └── images/           pattern.svg (geometric background)
```

`result.html` from the original brief was merged into `verify.html`. The result needs the uploaded audio
for segment playback and the spectrogram, and the audio cannot be passed between pages without storing it.

## Run locally

ES modules need an HTTP server; opening the files with `file://` will not work. From the `sada/` folder:

```bash
npx serve .
```

or `python -m http.server 8000`. Then open `/index.html`, or `/verify.html` to go straight to the tool.

## Modes

| Mode | How to enable | Behaviour |
| --- | --- | --- |
| `mock` (default) | `<meta name="sada-api-mode" content="mock">` in `verify.html` | Runs fully in the browser. The clip is never uploaded. Results carry a visible **demo** badge. |
| `live` | Set the meta to `live`, or add `?mode=live` to the URL | Calls the FastAPI endpoints below. |

`<meta name="sada-api-base">` holds the backend origin. Leave it empty when FastAPI serves the frontend.

## Demo scenarios (mock mode)

- **Demo panel:** in mock mode, the "وضع العرض التجريبي" pill in the header opens a small panel. Pick the
  outcome (auto / authentic / inconclusive / synthetic) or simulate an error (backend unavailable,
  processing failure, unsupported speaker).
- **URL:** `verify.html?scenario=likely_authentic|inconclusive|likely_synthetic` and
  `&simulate=backend_unavailable|processing_failure|unsupported_speaker`. `&speaker=ref_a` preselects a speaker.
- **Auto mode:** the scenario comes from the file name (`…authentic…`, `…inconclusive…`, `…synthetic…`/`…fake…`).
  Any other name shows **inconclusive**, the safest outcome when nothing was really analysed.
- File errors need no setup: try a `.txt` file, a `.wma` file, a clip shorter than 3 s, or a file over 20 MB.

All demo values live in `js/mock-data.js`. They are illustrative only, are not model output, and make no
accuracy claim. Flagged segments are placed relative to the real clip duration. The spectrogram is computed
from the real clip in the browser and is labelled as a display aid.

## FastAPI integration

| Endpoint | Required | Purpose |
| --- | --- | --- |
| `GET /api/v1/speakers` | yes | Supported reference figures |
| `POST /api/v1/verify` | yes | Analyse a clip (multipart: `audio`, `speaker_id`) |
| `POST /api/v1/fetch-audio` | only for the "paste a link" field | Download the audio behind a link (see below) |

Implement them, then either serve the frontend from FastAPI (same origin, no CORS) or set
`sada-api-base` and enable CORS for the frontend origin. If the API is on another origin, also expose the
`Content-Disposition` header (`Access-Control-Expose-Headers`) so the clip keeps its file name.

Without `fetch-audio`, the link field fails in live mode with a "backend unavailable" message; hide the field or
implement the endpoint before going live. The skeleton below covers `speakers` and `verify` only.

```python
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

app = FastAPI()

@app.get("/api/v1/speakers")
def speakers():
    return [{"id": "speaker_01", "name": "…", "role": "قارئ", "reference_count": 6,
             "official_source": {"label": "الموقع الرسمي", "url": "https://…"}}]

@app.post("/api/v1/verify")
async def verify(audio: UploadFile = File(...), speaker_id: str = Form(...)):
    if speaker_id not in SPEAKERS:
        raise HTTPException(422, detail={"code": "unsupported_speaker"})
    data = await audio.read()          # process in memory — do not persist user audio
    return run_pipeline(data, speaker_id)

app.mount("/", StaticFiles(directory="sada", html=True), name="frontend")  # mount last
```

## API contract

`GET /api/v1/speakers` returns the supported reference figures. *(Assumption: the proposal fixes three
consented figures but does not define this endpoint. The UI never hard-codes real names.)*

`POST /api/v1/verify` (multipart/form-data: `audio`, `speaker_id`) returns:

```json
{
  "status": "likely_synthetic",
  "confidence": 0.83,
  "decision_threshold": 0.70,
  "speaker": { "id": "speaker_01", "name": "…" },
  "voiceprint": { "match": 0.97, "flag": "unusually_high_match", "references_compared": 6 },
  "acoustic_analysis": {
    "score": 0.29, "pitch_stability": 0.24, "high_frequency_energy": 0.33,
    "pause_regularity": 0.21, "anomalies": ["…"]
  },
  "flagged_segments": [{ "start": 14.0, "end": 18.0, "reason": "تغير غير معتاد في الخصائص الصوتية" }],
  "spectrogram": null,
  "recommendation": "…",
  "observations": ["…"],
  "limitations": [],
  "official_source": { "label": "…", "url": "https://…" },
  "sources": [{ "type": "reference_recording", "title": "…", "description": "…", "url": null }],
  "duration": 72.4,
  "meta": {
    "analysis_id": "…", "analyzed_at": "2026-10-04T09:00:00Z",
    "models": { "speaker_encoder": "…", "artifact_classifier": "…" },
    "reference_set": "…", "processing_ms": 1480
  }
}
```

- `status` is required. Unknown values are rejected, so the UI never shows a verdict it cannot explain.
- All scores are on a **0–1** scale. Missing or out-of-range values hide their widget; nothing is invented.
- Acoustic sub-scores mean consistency with natural speech (higher = more natural).
- `voiceprint.flag` can be `unusually_high_match` or `unexpected_mismatch`.
- `spectrogram` can be `null` (the UI computes a local display spectrogram),
  `{ "image_url" | "image_base64", "frequency_max_hz", "frequency_scale": "mel" | "linear" }`, or
  `{ "data": [[0–1, …], …] }` (time × frequency, low → high).
- `sources[].type` can be `reference_recording`, `methodology`, `official_source` or `traceability`.
  Only `http(s)` links are rendered.
- **Errors:** return `{"detail": {"code": "<code>"}}` (or `{"error": {"code": …}}`) with codes `invalid_file`,
  `unsupported_format`, `file_too_large`, `file_too_short`, `file_too_long`, `unsupported_speaker`,
  `processing_failure`, and, for `fetch-audio`, `invalid_link`, `link_unreachable`, `link_not_audio`.
  HTTP 413/415/502–504 and network failures are mapped automatically.

### Splice / edit detection (`splice_analysis`, optional)

Evidence that a clip was cut, re-sequenced or assembled from different voices. It is shown as an extra card
in the evidence section; its marked positions are drawn on the spectrogram and listed with the other flagged
segments. Omit the whole object when the backend does not run this check: the card is then hidden.

```json
"splice_analysis": {
  "score": 0.31,
  "cut_continuity": 0.28,
  "sequence_naturalness": 0.35,
  "voice_consistency": 0.30,
  "findings": [
    { "type": "cut", "time": 4.0, "confidence": 0.84, "reason": "…" },
    { "type": "voice_swap", "start": 7.2, "end": 8.2, "confidence": 0.79, "reason": "…" },
    { "type": "unnatural_sequence", "start": 10.7, "end": 11.4 }
  ],
  "anomalies": ["…"]
},
"meta": { "models": { "splice_detector": "…" } }
```

- All scores are on a **0–1** scale and mean consistency with continuous, unedited speech (higher = more natural),
  like the acoustic sub-scores. Missing or out-of-range values hide their widget.
- `findings[].type` is `cut`, `unnatural_sequence` or `voice_swap`; any other value is shown as a generic marker.
- Give each finding either `start` + `end` (seconds) or a single `time`. For `time` the UI marks and plays
  1 s on each side (`SPLICE_POINT_PADDING_SEC` in `js/api.js`).
- `findings` has three meanings: **absent** = unknown (the UI claims nothing), `[]` = the check ran and found nothing
  ("none detected" is shown), non-empty = the positions to review. A non-empty list whose entries are all invalid is treated as absent.
- Do **not** repeat splice findings in `flagged_segments`; the UI merges both lists, so duplicates would show twice.
- `confidence` (per finding) is optional, 0–1. `reason` is optional; the type label is used when it is missing.
- A cut is not proof of forgery (legitimate editing exists). The card says so; keep backend wording equally cautious.
- Pipeline stage: `splice` sits between `acoustic` and `fusion` in `ANALYSIS_STAGES` (`js/state.js`) and in the demo
  timeline. In live mode every stage is shown as "on the server"; **remove `'splice'` from `ANALYSIS_STAGES`
  until the backend really runs this step**, so the UI never lists a stage that did not happen.

Suggested Pydantic models for the Python backend:

```python
from typing import Annotated, Literal, Optional
from pydantic import BaseModel, Field, model_validator

Score = Annotated[Optional[float], Field(ge=0, le=1)]   # Pydantic v2

class SpliceFinding(BaseModel):
    type: Literal["cut", "unnatural_sequence", "voice_swap"]
    start: Optional[float] = Field(None, ge=0)
    end: Optional[float] = Field(None, ge=0)
    time: Optional[float] = Field(None, ge=0)
    confidence: Score = None
    reason: Optional[str] = None

    @model_validator(mode="after")
    def needs_position(self):
        if self.time is None and (self.start is None or self.end is None or self.end <= self.start):
            raise ValueError("give `time`, or `start` < `end`")
        return self

class SpliceAnalysis(BaseModel):
    score: Score = None
    cut_continuity: Score = None
    sequence_naturalness: Score = None
    voice_consistency: Score = None
    findings: Optional[list[SpliceFinding]] = None   # None = unknown, [] = none found
    anomalies: list[str] = []
```

### Audio from a pasted link (`POST /api/v1/fetch-audio`)

The audio step has a "paste a link" field next to the file chooser. The clip behind the link is downloaded and
then enters the **same flow as a chosen file** (validation, waveform, player, local spectrogram, then speaker
selection and `POST /api/v1/verify`). Nothing else in the contract changes.

- **mock mode**: the browser downloads the link itself (`js/mock-api.js`). Works only for a direct link to an audio
  file whose server allows cross-origin reads (CORS). Requests are sent without cookies and without a referrer.
- **live mode**: the browser calls this endpoint and the **backend** downloads the link. This is required for any
  link the browser cannot read itself (no CORS, redirects, platform pages).

```
POST /api/v1/fetch-audio
Content-Type: application/json
{ "url": "https://example.com/clip.mp3" }

200  body = the audio bytes
       Content-Type: audio/…            (audio/mpeg, audio/wav, audio/mp4, audio/ogg, audio/flac …)
       Content-Disposition: attachment; filename*=UTF-8''clip.mp3     (optional, used as the clip name)
       Access-Control-Expose-Headers: Content-Disposition             (only if the API is on another origin)
4xx/5xx  { "error": { "code": "<one of the codes below>" } }
```

| code | when | UI message |
|---|---|---|
| `invalid_link` | not an http(s) address, embeds credentials, blocked address | the link is not valid |
| `link_unreachable` | 404/403, timeout, DNS failure, upstream error | could not fetch the clip |
| `link_not_audio` | the target is a page, a video or any non-audio content | the link is not an audio file |
| `file_too_large` | larger than `limits.maxFileBytes` (also 413) | file too large |
| `unsupported_format` | audio, but not a supported format (also 415) | unsupported format |

A 4xx without a recognised `code` is shown as `link_unreachable`; a network failure while calling this endpoint is
shown as `backend_unavailable`. The browser also stops reading at `limits.maxFileBytes` and re-validates the file, but
**the backend must enforce all of the following itself**:

- **SSRF**: only `http`/`https`; resolve the host and refuse loopback, private, link-local (incl. `169.254.169.254`),
  multicast and reserved ranges; connect to the resolved address (DNS rebinding); re-check every redirect and cap them.
- **Limits**: stream with a hard size cap, a total timeout, and a per-client rate limit.
- **Content**: verify the type from the file's magic bytes, not only from `Content-Type` or the extension.
- **Privacy**: forward no cookies or credentials, and do not log full URLs (query strings often carry signed tokens).
- **Platform links** (video/social pages) need an extractor and a legal/terms-of-service review; until then answer
  `link_not_audio` for them.

Minimal FastAPI skeleton (the address checks are deliberately left as a `TODO` for the team):

```python
import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, AnyHttpUrl

router = APIRouter()
MAX_BYTES = 20 * 1024 * 1024            # keep in sync with CONFIG.limits.maxFileBytes

class FetchAudio(BaseModel):
    url: AnyHttpUrl

def fail(status: int, code: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code}}, status_code=status)

@router.post("/api/v1/fetch-audio")
async def fetch_audio(body: FetchAudio):
    url = str(body.url)
    # TODO: SSRF guard — resolve the host, refuse non-public addresses, pin the connection to the resolved IP.
    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=20) as client:
            async with client.stream("GET", url, headers={"Accept": "audio/*"}) as upstream:
                # TODO: follow redirects manually, re-running the SSRF guard on each hop.
                if upstream.status_code != 200:
                    return fail(502, "link_unreachable")
                ctype = upstream.headers.get("content-type", "").split(";")[0].lower()
                if ctype and not (ctype.startswith("audio/") or ctype == "application/octet-stream"):
                    return fail(422, "link_not_audio")
                data = bytearray()
                async for chunk in upstream.aiter_bytes():
                    data += chunk
                    if len(data) > MAX_BYTES:
                        return fail(413, "file_too_large")
    except httpx.HTTPError:
        return fail(502, "link_unreachable")
    # TODO: sniff magic bytes → reject non-audio with link_not_audio
    return Response(bytes(data), media_type=ctype or "application/octet-stream")
```

## Before going live

- [ ] Set `sada-api-mode` to `live` in `verify.html` (and `sada-api-base` if the API is on another origin).
- [ ] Remove `'splice'` from `ANALYSIS_STAGES` in `js/state.js` unless the backend really runs the splice check.
- [ ] Implement `fetch-audio` with the SSRF, size, timeout and rate-limit protections listed above, or hide the link field.
- [ ] Keep `limits` in `js/config.js` equal to the backend limits (size, duration, formats).
- [ ] Agree on the design question: today a pasted clip is downloaded to the browser and uploaded again for analysis.
      Sending the link straight to `verify` (for example an `audio_url` field) would avoid the double transfer but
      loses the waveform, player and local spectrogram before analysis.
- [ ] The splice card, its Arabic copy, and the demo values were written without model input: have the team
      review the wording and confirm the backend produces each field before relying on it.
- [ ] Self-host the fonts if third-party requests are not allowed.

## Privacy

- Mock mode: the clip never leaves the browser.
- Live mode, as in the proposal: clips are processed for the session only and are not retained. The
  backend must enforce this; the UI does not promise anything stronger.
- Pasted links, live mode: the link is sent to the backend, which downloads the clip. Links often carry signed
  tokens in the query string, so do not log them in full and do not forward cookies. The downloaded clip follows
  the same rule as an uploaded one (session only, not retained). In mock mode the browser downloads it directly.
- No accounts and no personal data requested. The page releases its copy of the clip on "check another
  clip" or when you leave the page.

## Safety principles reflected in the UI

- Three outcomes. **Inconclusive** is a deliberate, first-class result with an official-source next step.
- Confidence is shown against the decision threshold, with the caption "not absolute certainty".
- No single path issues a verdict; the fusion step is shown explicitly.
- Disclosed limitations, including that Arabic-speech performance is not yet officially established.
- Scope: voice authenticity only. No fatwa, no judgment of content or of people.
- No fabricated links. The official-source action renders only when the backend supplies a URL.

## Assumptions (not specified in the source materials)

- Upload limits: 20 MB, 3 s–10 min. Formats: MP3, WAV, M4A, AAC, OGG, OPUS, FLAC. Edit them in `js/config.js`.
- `decision_threshold`, `observations`, `limitations`, `official_source`, `meta` and `duration` are optional
  additions to the contract.
- Mock speakers are placeholders («الشخصية المرجعية (أ/ب/ج)»). Real figures come from the backend after approval.

## Accessibility & localisation

Semantic landmarks, skip link, keyboard-operable controls (native inputs and buttons), visible focus,
live announcements, focus moved to each new screen, and `prefers-reduced-motion` support. Arabic RTL
throughout, using CSS logical properties. Media timelines and spectrograms stay left-to-right by
convention. To add English, add an `en` dictionary in `js/i18n.js`, set `CONFIG.locale`, and provide
translated page copy.
