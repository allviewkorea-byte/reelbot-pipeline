# CLAUDE.md — ReelBot (릴봇) 프로젝트 가이드

> **이 문서는 릴봇의 단일 진실 출처(Single Source of Truth)다.**
> 새 작업자(Claude Code 포함)는 작업 전 이 문서를 먼저 읽는다.
> 인수인계 시 "CLAUDE.md 읽고 와"로 충분하도록 항상 최신 상태로 유지한다.
> 최종 갱신: 2026-06-13

---

## 한 줄 정의

사연(감성 스토리) 기반 숏폼·롱폼 영상을 **"글 한 편 → 완성 영상 → 자동 업로드"**까지
풀자동으로 만드는 멀티채널 콘텐츠 공장. 채널마다 제작 트랙·스택이 다르며,
채널을 선택하면 그 안에서 모든 과정이 자동으로 돌아가는 구조를 지향한다.

- **스택**: Next.js (App Router) + Tailwind v4 + shadcn/ui (프론트) / Python FastAPI (백엔드)
- **로컬 경로**: `C:\Users\micro\reelbot-pipeline\`
- **레포**: `github.com/allviewkorea-byte/reelbot-pipeline`
- **프론트 배포**: Vercel — `reelbot-pipeline.vercel.app` (계정: `allviewkorea-byte`, main 자동 배포)
- **백엔드 배포**: Railway `adventurous-renewal` (Root: `travel-pipeline`)

---

## 🚨 디자인 시스템 — 절대 불변 제약 (모든 PR에 적용, 예외 없음)

### 절대 금지
- `globals.css`의 `@theme inline` 블록 **수정 절대 금지** (diff 0줄)
- `src/components/ui/*` (shadcn 컴포넌트) **수정 절대 금지** (diff 0줄)
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

### shadcn ui/ 에 실제로 존재하는 컴포넌트 (확인됨)
`badge`, `button`, `coming-soon`, `scroll-area`, `separator`, `tabs`, `tooltip`
→ **Sheet, Dialog 없음.** 슬라이드 패널·모달이 필요하면 기존 CloneModal 오버레이
패턴을 재사용한다 (ui/ 신규 추가·수정 금지).

### PR마다 반드시 확인
```
- [ ] tsc 통과 (에러 0)
- [ ] lint 신규 경고 0건 (기존 경고와 구분)
- [ ] build 통과
- [ ] globals.css diff 0줄
- [ ] components/ui/* diff 0줄
- [ ] 기존 라우트·기능 보존
```

> 참고: 알려진 baseline lint 경고 — `channels/[id]`, `character`, `scenario`,
> `video`, `video/create` 의 `react-hooks/set-state-in-effect` 9건. 신규 아님.

---

## 🎯 핵심 사실 — 인수인계 시 반드시 알아야 할 것

이 부분을 모르면 작업이 어긋난다. 과거에 실제로 혼선이 있었던 지점들이다.

1. **사연 파이프라인(트랙 A)은 이미 E2E 완성·운영 중이다.**
   "Phase 3 캐릭터 모듈 진행 중" 같은 옛 인식은 폐기. 캐릭터 모듈은 이 파이프라인의
   한 단계로 흡수됐다.

2. **"백곰의 실화보고서" = 기존 "사연 제작" 탭의 실체다.**
   별도의 추상적 "사연 제작 도구"가 따로 있는 게 아니라, 그 화면이 곧 백곰 채널을
   100% 자동으로 돌리는 엔진이었다. 흰곰 캐릭터로 사연 영상이 자동 생성·유튜브
   업로드되는 라이브 채널.

3. **트랙은 채널 속성이며 셋은 완전히 분리된 파이프라인이다.** (아래 트랙 표 참조)

4. **더미 채널 존재.** 방콕여행채널·도쿄일상브이로그 및 테스트 채널들은 실제 없는
   더미다. 정리 예정 (아래 미결 사항 참조).

---

## 아키텍처 — 3가지 영상 제작 트랙

| 트랙 | 이름 | 설명 | 상태 | 진입 |
|---|---|---|---|---|
| **A** | 자동화 (사연) | 사연 자동생성 → 콘티 → 영상 → TTS → BGM → 자막 → 합성 → 자동 업로드 | **완성·운영 중 (백곰 채널)** | `/video?mode=auto` |
| **B** | 반자동 (autoedit) | 실제 촬영 영상 + AI 자동 편집 | 대표 별도 진행 (본체와 분리) | `/space` |
| **C** | 어도비 편집 | 실제 촬영 + Premiere Pro + Claude MCP | 예정 | `/adobe` |

- 트랙은 채널 상세의 스택 설정에서 지정. `channel.stack.track` 필드.
- `startWorkflow()` 라우팅: auto→`/video?mode=auto`, semi→`/space`, adobe→`/adobe`.
  **이 라우팅은 절대 삭제 금지** (트랙 B/C 채널이 404로 깨짐).
- autoedit(트랙 B)는 대표님이 추후 별도 제작. 릴봇 본체 작업과 일정·코드 분리.

### 트랙 A 사연 파이프라인 상세
```
사연 자동생성 (100% 자동)
 → 디렉터 (sayeon_director.py: 와이드 오프닝, 감정 피크 클로즈업, 샷 중복 방지)
 → 캐릭터 시트 기반 콘티 (3면 reference로 일관성 유지)
 → Kling 영상 생성 (WaveSpeed API)
 → TTS 나레이션 (ElevenLabs eleven_multilingual_v2)
 → BGM 믹싱 (R2 bgm/ 랜덤, 볼륨 ~0.12, 페이드)
 → 자막
 → ffmpeg 합성 (-c copy 스트림 복사로 Railway OOM 해결)
 → 유튜브 자동 업로드
```

---

## 기술 스택

| 영역 | 기술 |
|---|---|
| 프론트엔드 | Next.js (App Router) + Tailwind v4 + shadcn/ui |
| 이미지 생성 | gpt-image-1 (OpenAI, 1024×1536, quality: high) / Z-Image Turbo (WaveSpeed, 콘티) |
| 영상 생성 | Kling via WaveSpeed API |
| TTS | ElevenLabs `eleven_multilingual_v2` (Creator 플랜, 현재 운영) / Edge TTS (폴백) |
| 합성 | ffmpeg |
| 백엔드 | Python FastAPI (`travel-pipeline/`) |
| 스토리지 | Cloudflare R2 (영상·캐릭터, 7일 자동삭제) — Supabase Storage 413 때문에 이관 |
| DB·인증 | Supabase |

---

## 환경 변수 규칙

- **비밀 키는 `NEXT_PUBLIC_` 접두사 절대 금지** → 브라우저 번들에 노출됨
- 모든 비밀 키(`OPENAI_API_KEY`, `WAVESPEED_API_KEY`, `ELEVENLABS_*` 등)는 서버사이드 전용
- WaveSpeed 호출은 반드시 서버사이드 API route 경유
- 허용된 `NEXT_PUBLIC_`: `NEXT_PUBLIC_API_BASE_URL` (URL 값은 노출 무방)
- Vercel·Railway 양쪽 Variables에 `OPENAI_API_KEY` 설정돼 있어야 빌드 통과

---

## 로컬 개발 실행 (Windows PowerShell)

```powershell
# 터미널 1 — 프론트엔드
npm run dev                                        # localhost:3000

# 터미널 2 — 백엔드
cd travel-pipeline
py -m uvicorn api.server:app --port 8000           # py 사용 필수, --reload 생략 권장
```

> - Python은 반드시 `py` 사용 (`python`/`python3` 금지 — MS Store stub 충돌)
> - PowerShell에서 `&&` 체이닝 금지 — 줄 나눠 실행, `$env:` 문법 사용
> - `localhost`가 안 뜨면 `127.0.0.1`로 직접 접속 (IPv6 `::1` black-hole 버그)
> - 좀비 uvicorn: `netstat -ano | findstr :8000` → `Get-Process python | Stop-Process -Force`

---

## 현재 라우트 목록

```
/                   (대시보드 — /dashboard)
/channels/[id]      채널 상세 (단일 스크롤 대시보드 — UI-2 이후 탭 제거됨)
/character          캐릭터 라이브러리
/scenario           시나리오 보관함
/사연제작            사연 제작 (= 백곰 채널 트랙 A 엔진. 채널 연결은 미결 — 아래 참조)
/subtitle-style     자막 스타일
/upload             멀티 플랫폼 발행
/video              영상 진입점
/video/create       콘티 → 영상 작업 페이지
/space              트랙 B 진입 (autoedit, 보존)
/adobe              트랙 C 진입 (어도비, 보존)
/settings           설정
```
> UI-1에서 폐기된 라우트: `/trends` `/competitor` `/publish-queue`
> `/history` `/cost` `/logs` (page 삭제). 단 트렌드/경쟁사 **분석 로직**
> (`lib/trends.ts`, `lib/youtube.ts`, `api/trends/**`)은 보존 — UI-7에서 재사용.

---

## 사이드바 IA (UI-1 이후 현재 구조)

```
대시보드                → /dashboard
[내 채널]   (+ 새 채널)
  · 활성 채널            → /channels/[id]  (status active/growing)
  · 미사용·보관 (접힘)   → /channels/[id]  (status pending — 더미·테스트 채널)
[운영]
  설정                  → /settings
```
- 채널 목록은 `useChannels()` (`/api/channels`, Supabase) 동적 렌더.
- 활성/보관 분류는 기존 `statusVariant` 필드로만 판단 (DB 스키마 변경 없음).
- 현재 보고 있는 채널이 보관 그룹이면 자동 펼침.
- 트렌드·경쟁사·영상제작·어도비는 독립 메뉴 아님 → 채널 안에서 진입/흡수.

---

## 채널 상세 화면 (UI-2 이후)

탭 없는 단일 스크롤 관제 대시보드.
- **헤더**: 뒤로가기 + 채널명 + 플랫폼/트랙/상태 뱃지 + NEXT UP(다음 업로드) +
  제어 버튼(시작▷/일시정지⏸/중단⏹ — 현재 **UI만, 동작 미연결**) +
  ⚙ 스택 설정(슬라이드 패널) + 이 채널 복제 + 채널 삭제
- **월간 지표 줄**: 영상 수 · 구독자 · 월 수익 · 평균 조회수
- **최근 영상**: 가로 스크롤 카드 (UI-3에서 마퀴 애니메이션 + 플랫폼 탭 예정)
- 스택 설정·startWorkflow 로직은 보존됨 (탭 UI만 제거).

---

## PR & 브랜치 규칙

- 항상 `main`에서 분기 (기존 PR 브랜치 재사용 금지)
- **PR 1개당 기능 1개** — 여러 기능 혼합 금지
- 브랜치명: 설명적 slug (예: `claude/pr-ui2-channel-dashboard-skeleton`)
- **작업 전 관련 파일 먼저 읽기 — 구조 추정 금지** (0단계 사전 조사 권장)
- PR 설명에 검증 체크리스트 결과 + 디자인 시스템 0줄 확인 포함

### 작업 흐름
claude.ai(전략·목업·작업지시서) → Claude Code(코딩·커밋·푸시·PR) →
대표가 GitHub 머지 → Vercel 자동배포 → Preview/시크릿창으로 확인.

---

## 금기 사항 (Forbidden)

1. `globals.css` `@theme inline` 수정
2. `src/components/ui/*` 수정 (없는 Sheet/Dialog 새로 추가도 금지)
3. 새 CSS 색상·토큰 추가
4. 기존 라우트 삭제·경로 변경 (명시적 지시 없이)
5. `startWorkflow` 라우팅(`/space`·`/adobe`·`/video?mode=auto`) 삭제
6. 트렌드/경쟁사 **분석 로직** 삭제 (페이지는 폐기됨, 로직은 보존)
7. 비밀 키에 `NEXT_PUBLIC_` 접두사
8. 하나의 PR에 여러 기능 혼합
9. Python 실행 시 `python`/`python3` (`py` 사용 필수)

---

## UI 개편 로드맵 (2026-06~)

| PR | 내용 | 상태 |
|---|---|---|
| **UI-1** | 사이드바 채널목록화 + 죽은 라우트 폐기 + 활성/보관 그룹 | ✅ 완료 (#92) |
| **UI-2** | 채널 상세 4탭 제거 → 단일 대시보드 골격 (제어버튼 UI + 지표 + ⚙스택) | ✅ 완료 (#93) |
| **UI-3** | 최근 영상 마퀴(우→좌 자동 스크롤) + 플랫폼 탭(유튜브/틱톡/인스타/네이버클립) | 예정 |
| **UI-4** | 노드그래프 파이프라인 (React Flow, 채널별 단계 시각화) | 예정 |
| **UI-5** | 콘텐츠 캘린더 (DB+API, 주간→월간 슬라이드업, 연속 컨셉 감지·자동수정) | 예정 |
| **UI-6** | 릴봇 AI 알림/채팅 패널 (자가치유 보고 + 사용자 입력, 우측 하단) | 예정 |
| **UI-7** | 트렌드/경쟁사 로직 → 캘린더 자동기획 엔진으로 흡수 | 예정 |

### 합의된 개편 철학
- 좌측 사이드바 = 채널 목록 자체 (채널명 노출, 20개+ 확장 전제)
- 채널 선택 → 그 채널 전용 관제 대시보드 (채널마다 설정 다름)
- 사연 대본 100% 자동생성
- 하단 마퀴 = **내 업로드 영상** (트렌드 아님), 플랫폼 탭으로 필터
- 연동 서비스 = 메인 영역 오른쪽 끝 세로 책갈피 탭(`<`) → 좌측 슬라이드인
  (채널별 Supabase·ElevenLabs·WaveSpeed·R2 사용량·지출)
- 릴봇 AI = 우측 하단, 수동 오픈 + 직접 입력 가능, 알림 시 자동 오픈,
  자가치유(자동 해결 후 보고 / 사람 필요 시 요청)
- 노드그래프는 처음부터 도입 (장기전·보는 맛 중시)

---

## 미결 사항 (다음 작업 후보)

1. **사연제작 ↔ 채널 연결.** `/사연제작`(백곰 트랙 A 엔진)이 채널 시스템과
   데이터로 연결돼 있는지 미확인. 백곰을 채널로 사이드바에 띄우고 채널 대시보드와
   연결하려면 구조 조사 필요. → **조사 지시서 먼저, 그 결과 보고 설계.**
2. **더미 채널 정리.** 방콕여행채널·도쿄일상브이로그·테스트 채널 삭제.
   (DB 레코드인지 하드코딩인지 확인 후 처리 — 코드 PR 불필요할 수 있음)
3. NEXT UP 실데이터 연결 (현재 플레이스홀더, UI-5 캘린더와 함께)
4. 제어 버튼(시작/일시정지/중단) 실제 동작 — 백엔드 연동 별도 PR

---

## 핵심 학습 (재방문 금지 영역)

- **한국어 TTS 오픈소스는 프로덕션 부적합** (Sesame CSM-1B, VoxCPM2, Chatterbox 모두
  한국어 부자연). Supertone(HYBE)이 한국어 최고, 현재는 ElevenLabs로 운영.
  Kokoro-82M은 영어/일본어 전용 → 향후 영어 파이프라인용으로 보류.
- **ElevenLabs Free tier는 Railway에서 차단됨** (데이터센터 IP) → Creator 플랜 필수.
- **R2 > Supabase Storage** (Kling 크기 파일에서 Supabase 413).
- **디자인 시스템이 가장 깨지기 쉬운 제약** — 모든 작업지시서 최상단에 명시.
- **0단계 사전 조사가 오판을 막는다** — 실제로 adobe/space 오삭제, Sheet/Dialog
  미존재를 사전 조사로 잡았다. 추정하지 말고 코드를 먼저 읽을 것.
