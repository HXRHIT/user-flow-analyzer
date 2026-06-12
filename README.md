# User Flow Analyzer

Upload an app screen recording → get an automated user-flow analysis.

화면 녹화 영상(.mp4/.mov/.webm)을 업로드하면 AI가 자동으로 분석해 4가지 산출물을 생성합니다:

1. **Screen inventory** — 등장한 고유 화면 캡처 + 화면명 + UI 요소
2. **Flow diagram** — 화면 전환 흐름도 (Mermaid, 백트래킹 점선 표시)
3. **Action log** — 탭/입력/스크롤 등 행동 타임라인
4. **UX findings** — 헤맴·백트래킹·오류 노출·민감정보 노출 등 진단

금융앱처럼 보안 화면(비밀번호 입력)에서 OS가 캡처를 차단해 검은 화면이 되는 구간도 자동 감지해 "secure section"으로 라벨링합니다.

## How it works

```
video ─► ① ffmpeg frame extraction (scene detection + uniform sampling)
      ─► ② keyframe selection (perceptual hash dedup, blank/secure detection)
      ─► ③ screen recognition (Claude vision API, batched keyframes)
      ─► ④ flow graph + Mermaid diagram
      ─► ⑤ UX heuristics (dwell time, backtracking, re-entry, sensitive data)
```

LLM 호출은 중복 제거된 키프레임에만 수행되어 비용을 최소화합니다 (기본 상한 60장).

## Quick start

Requirements: Python ≥ 3.10, Node ≥ 18, ffmpeg, and an LLM API key — either a **free**
[Google AI Studio key](https://aistudio.google.com/apikey) (Gemini, no credit card) or a paid
[Anthropic key](https://console.anthropic.com/) (Claude).

```bash
# backend
cd backend
pip install -e ".[dev]"
export GEMINI_API_KEY=...        # free tier (or ANTHROPIC_API_KEY for Claude)
uvicorn app.main:app --reload --port 8000

# frontend (separate terminal)
cd frontend
npm install
npm run dev          # http://localhost:5173
```

Single-process deployment: `npm run build` in `frontend/`, then FastAPI serves `frontend/dist` at `/`.

## Configuration

| env var | default | description |
|---|---|---|
| `GEMINI_API_KEY` | — | free-tier key from aistudio.google.com (preferred) |
| `ANTHROPIC_API_KEY` | — | alternative: paid Claude key |
| `UFA_LLM_PROVIDER` | auto | `gemini` \| `anthropic` (auto-detected from keys) |
| `UFA_VISION_MODEL` | per provider | `gemini-flash-latest` / `claude-sonnet-4-6` |
| `UFA_DATA_DIR` | `./data` | uploads & job artifacts |
| `UFA_MAX_UPLOAD_MB` | `500` | upload size limit |
| `UFA_SCENE_THRESHOLD` | `0.18` | ffmpeg scene-change sensitivity |
| `UFA_SAMPLE_INTERVAL` | `2.0` | uniform sampling interval (s) |
| `UFA_PHASH_DISTANCE` | `8` | dedup hash distance threshold |
| `UFA_MAX_KEYFRAMES_TO_LLM` | `60` | LLM cost ceiling per video |

## Tests

```bash
cd backend && pytest
```

Deterministic pipeline stages (extraction, dedup, flow graph, heuristics) are covered by unit
tests using a synthetic ffmpeg-generated video — no API key needed.

## Privacy notes

- Recordings may contain account numbers, balances, or names. The analyzer flags frames where
  sensitive data is visible (`UX findings`), and uploads stay on the machine running the server.
- Recordings are sent to the Anthropic API for screen recognition. Don't upload videos you are
  not allowed to share with a third-party API.

## Recording tips for best results

- Enable **touch indicators** (Android: Developer options → Show taps) — tap positions make
  action inference far more accurate.
- Keep recordings under 10 minutes.

## Roadmap

See [docs/spec.md](docs/spec.md) (Korean) for the full functional spec, and
[docs/demo-report.md](docs/demo-report.md) for a sample analysis produced from a real banking-app
recording. Planned: report export (md/pdf), project history, two-video comparison, automatic
masking of sensitive regions.

## License

MIT
