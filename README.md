# ReelBot (릴봇)

> AI 기반 숏폼·롱폼 영상 자동 제작 파이프라인 — 채널별 스택 설정에 따라 **시나리오 → 콘티 → 영상 → 멀티 플랫폼 발행**까지 자동화합니다.

ReelBot은 유튜브·인스타그램·틱톡·네이버클립 채널을 한 곳에서 관리하고,
각 채널의 제작 방식(트랙)에 맞춰 영상 제작 흐름을 자동/반자동으로 돌리는 도구입니다.

### 핵심 기능

- **시나리오 생성** — 트렌드·키워드 기반 대본 자동 작성
- **콘티(스토리보드) 생성** — 대본을 장면별 이미지로 시각화
- **영상 생성** — 콘티를 영상으로 변환 + TTS 음성 + 자막 합성
- **멀티 플랫폼 발행** — 유튜브·인스타·틱톡·네이버클립 동시 업로드
- **트렌드·경쟁사 분석** — YouTube Data API 기반 인기 영상·댓글 분석

---

## 3가지 영상 제작 트랙 (Production Tracks)

트랙은 채널 속성이며, 채널 상세 > 스택 설정 탭에서 지정합니다.

| 트랙 | 이름 | 흐름 |
|---|---|---|
| **A** | 자동화 (Automated) | Claude 대본 → gpt-image-1 콘티 → Kling 영상 → TTS → ffmpeg 합성 → 자동 발행 |
| **B** | 반자동 (Semi-auto) | 실제 촬영 영상 + AI 자동 편집 |
| **C** | 어도비 편집 (Adobe) | 실제 촬영 + Premiere Pro + Claude MCP 연동 *(예정)* |

> 캐릭터 일관성은 앞면·측면·뒷면 3면 reference 이미지를 통해 유지합니다.

---

## 기술 스택 (Tech Stack)

| 영역 | 기술 |
|---|---|
| **Frontend** | Next.js (App Router) + Tailwind v4 + shadcn/ui — Vercel 배포 |
| **Backend** | Python FastAPI (`travel-pipeline/`) |
| **이미지 생성** | gpt-image-1 (OpenAI) / Z-Image Turbo (WaveSpeed) |
| **영상 생성** | Kling via WaveSpeed API |
| **TTS** | Edge TTS *(현재)* / ElevenLabs *(예정)* |
| **합성** | ffmpeg *(현재)* / Remotion *(예정)* |

---

## 로컬 실행 방법 (Getting Started)

두 개의 터미널이 필요합니다 — 프론트엔드(Next.js)와 백엔드(FastAPI).

### 터미널 1 — 프론트엔드

```bash
npm install
npm run dev          # http://localhost:3000
```

### 터미널 2 — 백엔드

```bash
cd travel-pipeline
py -m uvicorn api.server:app --reload --port 8000
```

> ⚠️ Python은 반드시 `py`를 사용하세요. `python` / `python3`는 Microsoft Store stub과 충돌합니다.

### 환경변수 파일

| 파일 | 용도 | 템플릿 |
|---|---|---|
| `.env.local` | Next.js (프론트엔드) | `.env.example` 참고 |
| `travel-pipeline/.env` | Python (백엔드) | `travel-pipeline/.env.example` 참고 |

각 `.env.example`을 복사해 실제 값을 채워 넣으세요. `.env.local`·`.env`는 gitignore 대상입니다.

---

## 환경변수 목록 (Environment Variables)

### Frontend — `.env.local`

| 변수 | 설명 |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | FastAPI 백엔드 주소. `localhost` 대신 `127.0.0.1` 권장 (localhost는 IPv6로 해석돼 IPv4 uvicorn과 연결 안 될 수 있음) |
| `WAVESPEED_API_KEY` | 캐릭터 라이브러리 이미지 생성(Z-Image Turbo)용 키 |
| `YOUTUBE_API_KEY` | 트렌드 분석(인기 영상·댓글 수집)용 키. 실제 분석은 백엔드에서 수행하므로 `travel-pipeline/.env`에도 동일 키 필요 |
| `CHARACTER_LIBRARY_FRONT` | 콘티 reference로 쓸 기본 캐릭터 front 이미지 경로 (비워두면 자동 설정) |

> 🔒 비밀 키에는 `NEXT_PUBLIC_` 접두사를 절대 붙이지 마세요 — 브라우저 번들에 노출됩니다. URL 값(`NEXT_PUBLIC_API_BASE_URL`)만 예외입니다.

### Backend — `travel-pipeline/.env`

| 변수 | 설명 |
|---|---|
| `OPENAI_API_KEY` | (필수) gpt-image-1 콘티 생성 등 |
| `ANTHROPIC_API_KEY` | (필수) Claude 대본 생성 |
| `GOOGLE_STREET_VIEW_KEY` | (필수) 실제 공간 이미지 수집 |
| `KIE_API_KEY` | Kling AI (KIE) 키. `--seedance-mode kie` 사용 시에만 필요 |
| `WAVESPEED_API_KEY` | Z-Image Turbo(콘티) + Kling v3(영상). 없으면 기존 모델로 자동 fallback |
| `SEEDANCE_API_KEY` | Seedance (legacy, 현재 미사용 시 비워둠) |
| `YOUTUBE_CLIENT_SECRETS_FILE` | YouTube 업로드용 (`--skip-upload` 시 불필요) |
| `YOUTUBE_API_KEY` | YouTube Data API v3 (트렌드 분석). 무료 quota 1만 units/일 |
| `CHARACTER_LIBRARY_FRONT` | 캐릭터 라이브러리 이미지를 콘티/영상 reference로 쓸 때 (옵션) |

---

## 현재 상태 (Status)

- **Frontend**: Vercel 배포 완료 → [reelbot-pipeline.vercel.app](https://reelbot-pipeline.vercel.app)
- **Backend**: 로컬 실행 중 (`localhost:8000`) — Stage 2 배포 예정 (Railway/Render + Supabase)
