# CLAUDE.md — ReelBot (릴봇) 프로젝트 가이드

AI 기반 숏폼·롱폼 영상 자동 제작 파이프라인.
유튜브·인스타그램·틱톡·네이버클립 채널을 관리하고,
채널별 스택 설정에 따라 시나리오 → 콘티 → 영상 → 발행 흐름을 자동화한다.

- **스택**: Next.js + Tailwind v4 + shadcn/ui (프론트) / Python FastAPI (백엔드)
- **로컬 경로**: `C:\Users\micro\reelbot-pipeline\`
- **레포**: `github.com/allviewkorea-byte/reelbot-pipeline`

---

## 🚨 디자인 시스템 — 절대 불변 제약 (모든 PR에 적용, 예외 없음)

### 절대 금지
- `globals.css`의 `@theme inline` 블록 **수정 절대 금지**
- `src/components/ui/*` (shadcn 컴포넌트) **수정 절대 금지**
- 새로운 색상·폰트·간격 토큰 정의 금지 — 기존 토큰만 호출
- 기존 컴포넌트 스타일 변경 금지 — 레이아웃·기능만 수정

### 디자인 토큰 (참고용)

```css
--background: 222 47% 11%   /* 다크 네이비 */
--sidebar:    222 47% 8%
--card:       222 47% 14%
--primary:    265 89% 66%   /* 라벤더 보라 */
/* 액센트: emerald-600 (저장/완료 버튼) */
/* 차트 색상: 보라 / 시안 / 주황 */
```

### PR마다 반드시 확인

```
- [ ] tsc 통과
- [ ] lint 신규 경고 0건
- [ ] build 통과
- [ ] globals.css diff 0줄
- [ ] components/ui/* diff 0줄
- [ ] 기존 라우트 전부 보존
```

---

## 기술 스택

| 영역 | 기술 |
|---|---|
| 프론트엔드 | Next.js (App Router) + Tailwind v4 + shadcn/ui |
| 이미지 생성 | gpt-image-1 (OpenAI, 1024×1536, quality: high) / Z-Image Turbo (WaveSpeed) |
| 사연 캐릭터 일관성 | FLUX Kontext Pro Multi (WaveSpeed) — 캐릭터 시트 reference. 주인공은 **흰곰 마스코트**(동물 캐스팅, `services/sayeon_character.py`: `build_protagonist_character`/`CASTING_PALETTE`/남자상대=갈색 시바견 고정). 주인공 외 등장인물은 디렉터 `other_role`→`cast_supporting_animal`로 팔레트 동물 배정(주인공 외 곰 금지, 단독 컷엔 `SAYEON_NEGATIVE_SOLO`; 갈색곰=가족 키워드 있을 때만). 모든 씬 배경 필수(디렉터 `setting` 강제+기본값, NEGATIVE에 빈 배경 금지). 사연 톤 `tone`("serious"=선글라스/"light"=초롱초롱 눈) 토글. 그림체는 **따뜻한 파스텔 2D**(`POLAR_BEAR_ART_STYLE`)로 통일. ⚠️ 풀 포토리얼/3D 금지(일관성 깨짐). 씬 프롬프트는 부록C 빌더(`build_scene_prompt`: [STYLE]+[CHARACTER(주인공/투샷에만)]+[SHOT/SCENE]+[NEGATIVE 항상 포함]) + emotion→곰 표정(`BEAR_EXPRESSIONS`, serious=입·몸짓 위주). **detail/mood 컷은 캐릭터 블록·시트 reference 미적용**(t2i, 곰 미등장). 씬 연출은 **디렉터 단계**(`services/sayeon_director.py`, gpt-4o-mini)가 씬별 샷 스펙(shot_type/**subject_type**(protagonist·two_shot·detail·mood·flashback, 주인공 단독 ≤40%, 마지막 씬=정면 질문 엔딩 컷 고정)/**emotion**(7종, 곰 표정 매핑 재료)/angle/action/setting/mood)을 설계해 피사체·장소·샷종류를 다양화하되 시트 참조로 동일인 유지(`sayeon_split.py`·`sayeon_scene.py`). 디렉터 실패 시 기존 프롬프트 + 기본 샷 리스트로 폴백 |
| 사연 자동 대본 | gpt-4o-mini — **1인칭 고백체** + 3초 훅(사건 한복판)·갈등 공식 라이브러리(부록E 5종 중 1택)·에스컬레이션·디테일 리얼리즘·반전/사이다·질문 엔딩 + **사실적 구어체·약 90초(12~16비트)** (`services/sayeon_autoscript.py`). 씬 분할은 길이에 맞게 8~16씬 스케일 |
| 영상 생성 | Kling via WaveSpeed API |
| TTS | Supertone / Edge TTS / ElevenLabs — 사연 TTS 는 `TTS_PROVIDER`("supertone"\|"elevenlabs"\|"edge")로 선택, 미설정 시 Supertone→Edge 폴백 (`adapters/tts/`) |
| 합성 | ffmpeg (현재) / Remotion (예정) |
| 백엔드 | Python FastAPI (`travel-pipeline/`) |
| 배포 | Vercel (프론트) / Railway or Render (FastAPI, 예정) / Supabase (DB·인증·스토리지, 예정) |

---

## 로컬 개발 실행

```bash
# 터미널 1 — 프론트엔드
npm run dev                                              # localhost:3000

# 터미널 2 — 백엔드
cd travel-pipeline
py -m uvicorn api.server:app --reload --port 8000       # ⚠️ py 사용 필수
```

> ⚠️ Python은 반드시 `py` 사용. `python` / `python3` 금지 (Microsoft Store stub 충돌).

---

## 핵심 파일 경로

```
reelbot-pipeline/
├── src/
│   ├── app/
│   │   ├── api/                        # 서버사이드 API routes
│   │   │   └── character/generate/     # WaveSpeed 호출 (서버 전용)
│   │   ├── channels/[id]/page.tsx      # 채널 상세 (4탭: 개요/스택설정/워크플로/히스토리)
│   │   ├── character/                  # 캐릭터 라이브러리
│   │   ├── scenario/                   # 시나리오 보관함
│   │   ├── trends/                     # 트렌드 분석
│   │   └── competitor/                 # 경쟁사 분석
│   ├── components/
│   │   ├── layout/Sidebar.tsx          # ← 사이드바 메뉴 정의 파일
│   │   └── ui/                         # shadcn — 절대 수정 금지
│   └── lib/
│       └── wavespeed.ts                # 서버 전용 WaveSpeed 어댑터
├── travel-pipeline/                    # Python 파이프라인 + FastAPI
│   ├── api/server.py
│   └── adapters/                       # 이미지/영상 모델 어댑터 (교체 가능 구조)
├── public/
│   └── character-seeds/                # 캐릭터 앞·측·뒤 3면 reference 이미지
├── .env.local                          # Next.js 환경변수 (gitignore)
└── globals.css                         # Tailwind v4 디자인 시스템 ← @theme inline 절대 수정 금지
```

---

## 라우트 목록 (삭제·경로 변경 금지)

```
/                   대시보드
/channels           채널 목록 (플랫폼별 그룹)
/channels/[id]      채널 상세 (4탭: 개요 / 스택설정 / 워크플로 / 히스토리)
/character          캐릭터 라이브러리
/scenario           시나리오 보관함
/upload             멀티 플랫폼 발행
/video              영상 진입점 (채널 워크플로 탭에서 진입)
/video/create       실제 콘티 → 영상 작업 페이지
/adobe              어도비 편집 (트랙 C, Premiere MCP 예정) — 유지(채널 워크플로 진입)
/space              실제 공간 업로드 (트랙 B) — 유지(채널 워크플로 진입)
/subtitle-style     자막 스타일
/settings           설정
```

> UI-1(2026-06)에서 폐기된 라우트: /trends · /competitor · /publish-queue · /history · /costs · /logs
> (트렌드/경쟁사는 페이지만 폐기, 분석 로직 lib/trends.ts · lib/youtube.ts · api/trends/* 는 보존)

---

## 사이드바 IA (UI-1, 2026-06 이후 현재 구조)

```
대시보드                → /
[채널]
  내 채널 (동적 목록)    → /channels/[id]  (Supabase fetch)
    · 활성 채널          (statusVariant active/growing)
    · 미사용·보관        (그 외, 접기 가능·기본 접힘)
  새 채널                → (channels 신규 생성 동선)
[운영]
  설정                  → /settings
```

- 채널 목록은 사이드바에서 직접 렌더(`useChannels()` 재사용, `/api/channels`).
- 활성/보관 분류는 기존 `statusVariant` 필드로만 판단(스키마 변경 없음).
- 영상 제작·어도비 편집은 독립 메뉴가 아니라 채널 워크플로 탭 안에서 진입한다.

---

## 아키텍처 — 3가지 영상 제작 트랙

| 트랙 | 이름 | 설명 |
|---|---|---|
| A | 자동화 | Claude 대본 → gpt-image-1 콘티 → Kling 영상 → TTS → ffmpeg → 자동 발행 |
| B | 반자동 | 실제 촬영 영상 + AI 자동 편집 |
| C | 어도비 편집 | 실제 촬영 + Premiere Pro + Claude MCP 연동 (예정) |

트랙은 채널 속성이며 채널 상세 > 스택 설정 탭에서 지정한다.
캐릭터 일관성은 앞면·측면·뒷면 3면 reference를 통해 유지한다.

---

## 환경 변수 규칙

- **비밀 키는 `NEXT_PUBLIC_` 접두사 절대 금지** → 브라우저 번들에 노출됨
- 모든 비밀 키(`OPENAI_API_KEY`, `WAVESPEED_API_KEY` 등)는 서버사이드에서만 사용
- WaveSpeed 호출은 반드시 서버사이드 API route 경유 (`/api/character/generate`)
- 허용된 `NEXT_PUBLIC_`: `NEXT_PUBLIC_API_BASE_URL` (URL 값은 노출 무방)
- 사연 TTS 프로바이더(서버사이드, `NEXT_PUBLIC_` 금지): `TTS_PROVIDER`("supertone"|"elevenlabs"|"edge").
  - Supertone: `SUPERTONE_API_KEY`, `SUPERTONE_VOICE_ID`
  - ElevenLabs: `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL_ID`(기본 `eleven_multilingual_v2`)
  - Edge TTS: 키 불필요(무료 폴백)

---

## PR & 브랜치 규칙

- 항상 `main`에서 분기 (기존 PR 브랜치 재사용 금지)
- PR 1개당 기능 1개 — 여러 기능 혼합 금지
- PR 설명에 검증 체크리스트 결과 포함
- 브랜치명: 설명적인 slug (예: `claude/pr-channel-tabs-fix`)
- 작업 전 관련 파일 먼저 읽기 — 파일 구조 추정 금지

---

## 금기 사항 (Forbidden)

1. `globals.css` `@theme inline` 블록 수정
2. `src/components/ui/*` (shadcn) 수정
3. 새 CSS 색상·스타일 토큰 추가
4. 기존 라우트 삭제 또는 경로 변경 (명시적 지시 없이)
5. 비밀 API 키에 `NEXT_PUBLIC_` 접두사 추가
6. 하나의 PR에 여러 기능 혼합
7. Python 실행 시 `python` / `python3` 사용 (`py` 사용 필수)
8. 목표가 이미 달성된 경우 중복 코드 추가

---

## Claude Code 작업 원칙

- 작업 시작 전 관련 파일 직접 읽기 (추정하지 않음)
- tsc → lint(before/after 비교) → build → diff 범위 확인 순서로 검증
- lint 경고가 기존 것인지 신규인지 반드시 구분
- 목표가 이미 충족된 경우: 코드 수정 없이 이대로 종료 권장
- 브랜치 충돌 발생 시: main에서 새 브랜치 따기 (기존 브랜치 스택 금지)
- 디자인 시스템 0줄 수정 확인 후 커밋

---

## 현재 상태 (2026-05-22 기준)

### 완료된 PR
- PR #11: 사이드바 흐름순 IA 재배열 ✅ 머지됨

### 진행 중
- 채널 상세 4탭 가로화: PR 작업 중
- PR #10 (씬 스크립트 TTS): 브랜치 `claude/pr10-scene-script-tts-oThpU`, E2E 검증 미완료

### 알려진 이슈
- 🔴 #5 백엔드 연결 끊김 — 전역 블로커, 원인 미파악
- 🟡 #1 캐릭터 사진 확대 모달
- 🟡 #2 캐릭터 이름 동기화
- 🟡 #4 트렌드 설정 글로벌 템플릿화

### 배포 현황
- 프론트엔드: Vercel 배포 완료 (reelbot-pipeline.vercel.app)
- 백엔드: 로컬만 (localhost:8000) — Stage 2 배포 예정
- Stage 2 예정 스택: Railway/Render (FastAPI) + Supabase (DB·인증·파일 저장)

### 다음 예정 작업
- 트렌드 분석 모듈 B안: YouTube Data API v3 + GPT 분석 + 시나리오 자동 연결
- 어도비 편집 워크플로 (트랙 C): Premiere MCP 연동

---

## 인프라 현황 (2026-05-26 기준)

### 배포 구성
- 프론트엔드: Vercel (reelbot-pipeline.vercel.app) — main 브랜치 자동 배포
- 백엔드: Railway `adventurous-renewal` 프로젝트
  - 레포: allviewkorea-byte/reelbot-pipeline
  - Root Directory: travel-pipeline
  - URL: https://reelbot-pipeline-production-94d0.up.railway.app
  - 상태: Online (FastAPI /health 200 응답 확인)
- Vercel 환경변수: NEXT_PUBLIC_API_BASE_URL 설정 완료

### 완료된 PR (최신순)
- PR #40: ffmpeg concat OOM 수정 (-c copy 스트림 복사)
- PR #39: ffmpeg concat 디버그 로그 추가
- PR #37~#38: WaveSpeed 폴링 타임아웃 2시간으로 연장
- PR #36: WaveSpeed Kling v3 엔드포인트 400 수정
- PR #35: 영상 제작 화면 스택 표시 개선 + 뒤로가기 버튼
- PR #34: 콘티 스케치 스타일 불일치 수정 + Supabase 에러 로그
- PR #33: 채널 트렌드 인사이트 인라인 표시
- PR #32: Supabase Storage 영상 업로드 연동 (재시도)
- PR #31: Supabase Storage 영상 업로드 연동
- PR #30: 콘티 모델 Z-Image Turbo 스케치 스타일 (gpt-image-1 제거)
- PR #29: 스토리보드 CDN URL 수정
- PR #28: PyJWT 의존성 추가
- PR #27: 시나리오→영상 채널 핸드오프 수정
- PR #25: 하드코딩 localhost 수정 (ResultViewer, SceneCard)
- PR #24: 시나리오 자동 연결 (트렌드 → /scenario)
- PR #23: 트렌드 분석 (YouTube Data API v3 + GPT)
- PR #11 이전: 사이드바 IA, 채널 Supabase, 한글 URL 인코딩 등

### 영상 파이프라인 동작 현황
- Kling v3 + Character ID 정상 동작 확인됨
- ffmpeg concat: -c copy(스트림 복사)로 Railway OOM(SIGKILL) 해결됨

### 알려진 이슈
- 🔴 Supabase Storage 413 (파일 크기 초과) → Cloudflare R2로 교체 예정

### 다음 작업: Cloudflare R2 연동 (Supabase 413 대체)
- R2 버킷 생성 + 7일 자동 삭제 Lifecycle 설정
- supabase_storage.py → r2_storage.py 교체
- Railway Variables에 R2 키 추가 필요

### 백엔드 블로커 #5 현황
- Railway 배포 완료, URL 노출됨, Vercel 연결됨
- Railway Variables에 OPENAI_API_KEY 등 환경변수 설정 필요 여부 미확인
- 로컬 개발 시: cd travel-pipeline && py -m uvicorn api.server:app --reload --port 8000

---

### UI 개편 로드맵 (2026-06~)
- [완료] UI-1 사이드바 채널목록화 + 죽은탭 폐기
- UI-2 채널 대시보드 (월간지표 + 시작/일시정지/중단 + NEXT UP + 연동서비스 책갈피)
- UI-3 업로드 영상 마퀴 (플랫폼 탭: 유튜브/틱톡/인스타/네이버클립)
- UI-4 노드그래프 파이프라인 (React Flow)
- UI-5 콘텐츠 캘린더 (DB+API, 주간→월간, 연속 컨셉 감지)
- UI-6 릴봇 AI 알림/채팅 패널 (자가치유 보고 + 사용자 입력)
- UI-7 트렌드/경쟁사 로직 → 캘린더 자동기획 엔진으로 흡수

주의: 트렌드/경쟁사 페이지는 폐기됐으나 분석 로직은 UI-7용으로 보존.
