# CLAUDE.md — ReelBot (릴봇) 프로젝트 가이드

> **이 문서는 릴봇의 단일 진실 출처(Single Source of Truth)다.**
> 새 작업자(Claude Code 포함)는 작업 전 이 문서를 먼저 읽는다.
> 인수인계 시 "CLAUDE.md 읽고 와"로 충분하도록 항상 최신 상태로 유지한다.
> **다른 인수인계 문서(reelbot_handover.md 등)는 폐기됨 — 이 파일 하나만 신뢰한다.**
> 최종 갱신: 2026-06-14

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

## 🛑 최우선 보호 — 사연 제작 탭 (`/sayeon`)

**릴봇의 핵심 기능이자 완성품. 운영 중인 백곰 채널을 돌리는 엔진.**
**레이아웃·메뉴 위치만 바꿀 수 있고, 아래는 코드 차원에서 절대 수정·삭제 금지.**

- **파일**: `src/app/sayeon/page.tsx` / **라우트**: `/sayeon`
- 새 작업자는 이 파일을 **읽지도 고치지도 않는다** (UI 개편 1단계 동안 완전 격리).

### 절대 건드리면 안 되는 것
- **제작 모드 3종 토글**: 자동 / 반자동 / 수동 — 탭 구조·모드별 동작 로직 유지
- **UI 요소 전체**: 사연 대본 textarea + "사연 자동 생성" 버튼 / 캐릭터 드롭다운 +
  저장 input + "현재 캐릭터 저장" / 캐릭터 모드 탭(새 캐릭터·기존 시트 재사용) /
  새 캐릭터 8필드(성별·연령대·헤어·외모·의상·액세서리·시그니처·기타) /
  기존 시트 재사용(시트 URL + 앵커) / 고급 설정(보이스ID·씬개수·썸네일씬번호·라인사이쉼) /
  하단 액션 버튼(모드별 분기) / 결과 화면(완성 영상·썸네일·씬 그리드·새로 만들기) /
  진행 상태(스피너·진행률·에러 배너)
- **API 호출 7종**: `generateSayeonScript`, `generateSayeon`, `pollJobStatus`,
  `listSayeonCharacters`, `getDefaultSayeonCharacter`, `saveSayeonCharacter`,
  `updateSayeonCharacterSheet`
- **state 전부**: script, charMode, spec(8필드), sheetUrl, anchor / jobStatus,
  submitting, error, stopRef / savedChars, selectedCharId, saveName, saving /
  mode, advancedOpen, voiceId, numScenes, thumbIndex, gapSec
- **`FALLBACK_SPEC` 로직** — 건드리면 자동 모드 작동 안 함

### 핵심 원칙 (어기면 완성품이 깨진다)
- 이 탭은 **채널과 완전 독립**으로 동작한다 (`channel_id` 연결 없음).
- 프론트에 **채널 선택 UI 추가 금지** (현재 설계 의도).
- 유튜브 자동 업로드는 **백엔드 환경변수로만** 작동 (`YOUTUBE_AUTO_PUBLISH`,
  `YOUTUBE_CHANNEL_ID`는 Railway Variables). 이 탭엔 업로드 UI 없음 — 추가 금지.

### 바꿔도 되는 것
- 사이드바에서 이 탭으로 가는 메뉴 항목의 위치/이름
- 페이지 레이아웃 (카드 배치·여백·순서)
- 채널 허브 UI 안에서 이 페이지로 **링크/동선 연결** (단, page 코드는 그대로)

---

## 🧭 UI 개편 2단계 전략 (대표 확정)

**1단계 (지금):** 사연탭(`/sayeon`)을 그대로 둔 채, 합의한 새 UI/UX 껍데기를
하나씩 완성한다 (사이드바 채널 구조·노드그래프·캘린더·마퀴·AI채팅·연동패널).
→ 운영 중인 백곰이 한순간도 안 멈추고, 새 UI가 깨져도 사연탭은 멀쩡 (리스크 격리).

**2단계 (나중):** 새 UI/UX가 완성되면, 그때 사연탭의 검증된 기능을 새 구조에 맞게
**이식**한다. 그 전까지는 sayeon 코드 격리 유지.

> 합의 조정: "채널 선택하면 그 안에서 사연 제작이 돈다"는 **데이터 결합이 아니라
> UI 동선**으로 구현한다. 채널 대시보드의 "사연 제작 열기" 버튼 → 기존 `/sayeon`으로
> 이동. sayeon 페이지는 channel_id를 받지 않고 백엔드 환경변수로 백곰에 업로드.

---

## 🎯 핵심 사실 — 인수인계 시 반드시 알아야 할 것

이 부분을 모르면 작업이 어긋난다. 과거에 실제로 혼선이 있었던 지점들이다.

1. **사연 파이프라인(트랙 A)은 이미 E2E 완성·운영 중이다.**
   "Phase 3 캐릭터 모듈 진행 중" 같은 옛 인식은 폐기. 캐릭터 모듈은 이 파이프라인의
   한 단계로 흡수됐다.

2. **운영 채널은 "백곰의 실화보고서" 1개뿐이다.**
   이 채널은 `/sayeon` 탭으로 100% 자동 운영되며, **유튜브 비공개(private) 업로드까지
   완성**된 라이브 상태다 (공개 발행은 테스트 후 전환 예정). 흰곰 캐릭터.
   나머지 채널(방콕여행채널·도쿄일상브이로그·테스트들)은 **전부 더미 — 삭제 대상.**

3. **백곰 ↔ 사연제작 관계:** "백곰의 실화보고서"를 자동 운영하는 엔진이 곧 `/sayeon`
   탭이다. 단 sayeon은 채널 시스템과 코드로 연결돼 있지 않다(환경변수 기반). 위
   "UI 개편 2단계 전략" 참조.

4. **트랙은 채널 속성이며 셋은 완전히 분리된 파이프라인이다.** (아래 트랙 표 참조)

---

## 아키텍처 — 3가지 영상 제작 트랙

| 트랙 | 이름 | 설명 | 상태 | 진입 |
|---|---|---|---|---|
| **A** | 자동화 (사연) | 사연 자동생성 → 콘티 → 영상 → TTS → BGM → 자막 → 합성 → 자동 업로드 | **완성·운영 중 (백곰, `/sayeon`)** | `/sayeon`, `/video?mode=auto` |
| **B** | 반자동 (autoedit) | 실제 촬영 영상 + AI 자동 편집 | 대표 별도 진행 (본체와 분리) | `/space` |
| **C** | 어도비 편집 | 실제 촬영 + Premiere Pro + Claude MCP | 예정 | `/adobe` |

- 트랙은 채널 상세의 스택 설정에서 지정. `channel.stack.track` 필드.
- `startWorkflow()` 라우팅: auto→`/video?mode=auto`, semi→`/space`, adobe→`/adobe`.
  **이 라우팅은 절대 삭제 금지** (트랙 B/C 채널이 404로 깨짐).
- autoedit(트랙 B)는 대표님이 추후 별도 제작. 릴봇 본체 작업과 일정·코드 분리.

### 트랙 A 사연 파이프라인 상세 (백엔드 `travel-pipeline/services/`)
```
사연 자동생성 (sayeon_autoscript)
 → 디렉터 (sayeon_director: 와이드 오프닝, 감정 피크 클로즈업, 샷 중복 방지)
 → 캐릭터 시트 콘티 (sayeon_character·sayeon_scene, 3면 reference로 일관성)
 → Kling 영상 (WaveSpeed API)
 → TTS (sayeon_tts, ElevenLabs eleven_multilingual_v2)
 → BGM (sayeon_bgm, R2 bgm/ 랜덤, 볼륨 ~0.12, 페이드)
 → 자막 → ffmpeg 합성 (sayeon_assemble, -c copy로 Railway OOM 해결)
 → 썸네일 (sayeon_thumbnail) → 유튜브 자동 업로드 (youtube_upload)
오케스트레이터: sayeon_orchestrate
```

---

## 기술 스택

| 영역 | 기술 |
|---|---|
| 프론트엔드 | Next.js (App Router) + Tailwind v4 + shadcn/ui |
| 이미지 생성 | gpt-image-1 (OpenAI, 1024×1536, quality: high) / Z-Image Turbo (WaveSpeed, 콘티) |
| 영상 생성 | Kling via WaveSpeed API |
| TTS | ElevenLabs `eleven_multilingual_v2` (Creator 플랜, 운영) / Edge TTS (폴백) |
| 합성 | ffmpeg |
| 백엔드 | Python FastAPI (`travel-pipeline/`) |
| 스토리지 | Cloudflare R2 (영상·캐릭터, 7일 자동삭제) — Supabase Storage 413 때문에 이관 |
| DB·인증 | Supabase |

---

## 디자인 시스템 — 절대 불변 제약 (모든 PR, 예외 없음)

### 절대 금지
- `globals.css`의 `@theme inline` 블록 수정 금지 (diff 0줄)
- `src/components/ui/*` (shadcn) 수정 금지 (diff 0줄)
- 새 색상·폰트·간격 토큰 정의 금지 — 기존 토큰만 호출
- 기존 컴포넌트 스타일 변경 금지 — 레이아웃·기능만 수정

### 디자인 토큰 (참고용)
```css
--background: 222 47% 11%   /* 다크 네이비 */
--sidebar:    222 47% 8%
--card:       222 47% 14%
--primary:    265 89% 66%   /* 라벤더 보라 */
/* 액센트: emerald-600 (저장/완료) · 차트: 보라 / 시안 / 주황 */
```

### shadcn ui/ 에 실제로 존재하는 컴포넌트 (확인됨)
`badge`, `button`, `coming-soon`, `scroll-area`, `separator`, `tabs`, `tooltip`
→ **Sheet, Dialog 없음.** 슬라이드 패널·모달은 기존 CloneModal 오버레이 패턴 재사용.

### PR 검증 체크리스트
```
- [ ] tsc 통과 (에러 0)
- [ ] lint 신규 경고 0건 (기존과 구분)
- [ ] build 통과
- [ ] globals.css diff 0줄
- [ ] components/ui/* diff 0줄
- [ ] sayeon/page.tsx 무수정 + 기존 라우트·기능 보존
```
> baseline lint 경고: `channels/[id]`, `character`, `scenario`, `video`,
> `video/create` 의 `react-hooks/set-state-in-effect` 9건 (신규 아님).

---

## 환경 변수 규칙

- **비밀 키는 `NEXT_PUBLIC_` 접두사 절대 금지** → 브라우저 번들 노출
- 모든 비밀 키(`OPENAI_API_KEY`, `WAVESPEED_API_KEY`, `ELEVENLABS_*`,
  `YOUTUBE_*` 등)는 서버사이드 전용
- 허용된 `NEXT_PUBLIC_`: `NEXT_PUBLIC_API_BASE_URL` (URL 값은 노출 무방)
- Vercel·Railway 양쪽에 `OPENAI_API_KEY` 있어야 빌드 통과
- 유튜브 업로드 제어: `YOUTUBE_AUTO_PUBLISH`, `YOUTUBE_CHANNEL_ID` — Railway 전용

---

## 로컬 개발 실행 (Windows PowerShell)

```powershell
# 프론트엔드
npm run dev                                        # localhost:3000
# 백엔드
cd travel-pipeline
py -m uvicorn api.server:app --port 8000           # py 필수, --reload 생략 권장
```
> - Python은 `py` 사용 (`python`/`python3` 금지 — MS Store stub 충돌)
> - PowerShell에서 `&&` 금지 — 줄 나눠 실행, `$env:` 문법
> - `localhost` 안 뜨면 `127.0.0.1`로 (IPv6 `::1` black-hole 버그)
> - 좀비 uvicorn: `netstat -ano | findstr :8000` → `Get-Process python | Stop-Process -Force`

---

## 현재 라우트 목록

```
/                   대시보드 (/dashboard)
/sayeon             🛑 사연 제작 — 백곰 트랙 A 엔진 (보호 대상, 위 섹션 참조)
/channels/[id]      채널 상세 (단일 스크롤 대시보드 — UI-2 이후 탭 제거됨)
/character          캐릭터 라이브러리
/scenario           시나리오 보관함
/subtitle-style     자막 스타일
/upload             멀티 플랫폼 발행
/video              영상 진입점
/video/create       콘티 → 영상 작업
/space              트랙 B 진입 (autoedit, 보존)
/adobe              트랙 C 진입 (어도비, 보존)
/settings           설정
```
> UI-1에서 폐기: `/trends` `/competitor` `/publish-queue` `/history` `/cost`
> `/logs` (page 삭제). 단 트렌드/경쟁사 **분석 로직**(`lib/trends.ts`,
> `lib/youtube.ts`, `api/trends/**`)은 보존 — UI-7에서 재사용.

---

## 사이드바 IA (UI-1 이후)

```
대시보드                → /dashboard
[내 채널]   (+ 새 채널)
  · 활성 채널            → /channels/[id]  (status active/growing)
  · 미사용·보관 (접힘)   → /channels/[id]  (status pending — 더미·테스트)
[운영]
  설정                  → /settings
```
- 채널 목록은 `useChannels()` (`/api/channels`, Supabase) 동적 렌더.
- 활성/보관 분류는 기존 `statusVariant` 필드로만 판단 (DB 스키마 변경 없음).
- 현재 보고 있는 채널이 보관 그룹이면 자동 펼침.

---

## 채널 상세 화면 (UI-2 이후)

탭 없는 단일 스크롤 관제 대시보드.
- **헤더**: 뒤로가기 + 채널명 + 플랫폼/트랙/상태 뱃지 + NEXT UP(다음 업로드) +
  제어 버튼(시작▷/일시정지⏸/중단⏹ — 현재 **UI만, 동작 미연결**) +
  ⚙ 스택 설정(CloneModal 패턴 슬라이드 패널) + 이 채널 복제 + 채널 삭제
- **월간 지표 줄**: 영상 수 · 구독자 · 월 수익 · 평균 조회수
- **최근 영상**: 가로 스크롤 카드 (UI-3에서 마퀴 + 플랫폼 탭 예정)
- 스택 설정·startWorkflow 로직 보존 (탭 UI만 제거).

---

## PR & 브랜치 규칙

- 항상 `main`에서 분기 (기존 PR 브랜치 재사용 금지)
- **PR 1개당 기능 1개**
- 브랜치명: 설명적 slug (예: `claude/pr-ui3-recent-marquee`)
- **작업 전 관련 파일 먼저 읽기 — 구조 추정 금지** (0단계 사전 조사 권장)
- PR 설명에 검증 체크리스트 결과 + 디자인 시스템 0줄 확인 포함

### 작업 흐름
claude.ai(전략·목업·작업지시서) → Claude Code(코딩·커밋·푸시·PR) →
대표가 GitHub 머지 → Vercel 자동배포 → Preview/시크릿창 확인.

---

## 금기 사항 (Forbidden)

1. **`src/app/sayeon/page.tsx` 및 그 API·state·FALLBACK_SPEC 수정** (최우선)
2. sayeon 탭에 채널 선택 UI / 유튜브 업로드 UI 추가
3. `globals.css` `@theme inline` 수정
4. `src/components/ui/*` 수정 (없는 Sheet/Dialog 추가도 금지)
5. 새 CSS 색상·토큰 추가
6. 기존 라우트 삭제·경로 변경 (명시적 지시 없이)
7. `startWorkflow` 라우팅(`/space`·`/adobe`·`/video?mode=auto`) 삭제
8. 트렌드/경쟁사 **분석 로직** 삭제 (페이지는 폐기, 로직은 보존)
9. 비밀 키에 `NEXT_PUBLIC_` 접두사
10. 하나의 PR에 여러 기능 혼합
11. Python 실행 시 `python`/`python3` (`py` 필수)

---

## UI 개편 로드맵 (2026-06~)

| PR | 내용 | 상태 |
|---|---|---|
| **UI-1** | 사이드바 채널목록화 + 죽은 라우트 폐기 + 활성/보관 그룹 | ✅ 완료 (#92) |
| **UI-2** | 채널 상세 4탭 제거 → 단일 대시보드 골격 | ✅ 완료 (#93) |
| **백곰 등록** | 백곰을 사이드바 표시용 채널로 등록 + 더미(방콕·도쿄) 정리 | 다음 |
| **UI-3** | 최근 영상 마퀴(우→좌) + 플랫폼 탭(유튜브/틱톡/인스타/네이버클립) | 예정 |
| **UI-4** | 노드그래프 파이프라인 (React Flow, 채널별 단계 시각화) | 예정 |
| **UI-5** | 콘텐츠 캘린더 (DB+API, 주간→월간 슬라이드업, 연속 컨셉 감지·자동수정) | 예정 |
| **UI-6** | 릴봇 AI 알림/채팅 패널 (자가치유 보고 + 사용자 입력, 우측 하단) | 예정 |
| **UI-7** | 트렌드/경쟁사 로직 → 캘린더 자동기획 엔진으로 흡수 | 예정 |
| **2단계** | 사연탭 기능을 새 UI/UX 구조로 이식 | 최종 |

### 합의된 개편 철학
- 좌측 사이드바 = 채널 목록 자체 (채널명 노출, 20개+ 확장 전제)
- 채널 선택 → 그 채널 전용 관제 대시보드
- 사연 대본 100% 자동생성
- 하단 마퀴 = **내 업로드 영상** (트렌드 아님), 플랫폼 탭으로 필터
- 연동 서비스 = 메인 영역 오른쪽 끝 세로 책갈피 탭(`<`) → 좌측 슬라이드인
  (채널별 Supabase·ElevenLabs·WaveSpeed·R2 사용량·지출)
- 릴봇 AI = 우측 하단, 수동 오픈 + 직접 입력, 알림 시 자동 오픈, 자가치유
- 노드그래프는 처음부터 도입 (장기전·보는 맛 중시)

---

## 미결 사항 (다음 작업)

1. **백곰 사이드바 등록 + 더미 정리.** 백곰을 표시용 채널로 사이드바에 띄우고
   (클릭 시 채널 대시보드 → "사연 제작 열기"로 `/sayeon` 이동), 더미 채널
   (방콕·도쿄·테스트) 삭제. ※ sayeon 코드 무관, channel_id 연결 안 함.
   → 백곰이 DB 채널 레코드인지/하드코딩인지 사전 조사 후 진행.
2. NEXT UP 실데이터 연결 (현재 플레이스홀더, UI-5 캘린더와 함께)
3. 제어 버튼(시작/일시정지/중단) 실제 동작 — 백엔드 연동 별도 PR

---

## 핵심 학습 (재방문 금지 영역)

- **한국어 TTS 오픈소스는 프로덕션 부적합** (Sesame CSM-1B, VoxCPM2, Chatterbox).
  Supertone(HYBE) 최고, 현재 ElevenLabs 운영. Kokoro-82M은 영어/일본어 전용(보류).
- **ElevenLabs Free tier는 Railway에서 차단** (데이터센터 IP) → Creator 플랜 필수.
- **R2 > Supabase Storage** (Kling 크기 파일 413).
- **디자인 시스템이 가장 깨지기 쉬운 제약** — 작업지시서 최상단에 항상 명시.
- **0단계 사전 조사가 오판을 막는다** — adobe/space 오삭제, Sheet/Dialog 미존재를
  사전 조사로 잡았다. 추정하지 말고 코드를 먼저 읽을 것.
