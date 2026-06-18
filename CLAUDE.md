# CLAUDE.md — ReelBot (릴봇) 프로젝트 가이드

AI 기반 한국어 감성 사연(썰) 숏폼 영상 자동 제작 파이프라인. **백곰 채널**을 운영하며,
트렌드 분석 → 캘린더 자동 기획 → 시나리오 → 콘티 → 영상 → TTS·BGM → 합성 → 유튜브 발행을 자동화한다.

- **스택**: Next.js 16(App Router) + Tailwind v4 + shadcn/ui (프론트) / Python FastAPI (백엔드)
- **로컬 경로**: `C:\Users\micro\reelbot-pipeline\`
- **레포**: `github.com/allviewkorea-byte/reelbot-pipeline`
- **운영자**: 이정호 대표 (백곰 단독 채널, 멀티채널은 추후)

---

## 🚨 디자인 시스템 — 절대 불변 제약 (모든 PR, 예외 없음)

### 절대 금지
- 🛑 **`src/app/sayeon/page.tsx` 수정 절대 금지** (백곰 운영 엔진). 조사 시 읽기만 허용.
- `globals.css`의 `@theme inline` 블록 **수정 금지**
- `src/components/ui/*` (shadcn) **수정 금지**
- 새 색상·폰트·간격 토큰 정의 금지 — 기존 토큰만 호출
- keyframes·글로우는 styled-jsx(컴포넌트 스코프). globals 금지. React Flow 금지(순수 SVG).

### 디자인 토큰 (참고)
```css
--background: 222 47% 11%   /* 다크 네이비 */
--sidebar:    222 47% 8%
--card:       222 47% 14%
--primary:    265 89% 66%   /* 라벤더 보라 */
/* 액센트: emerald (저장/완료) / 차트: 보라·시안·주황 */
```

### PR마다 확인
```
- [ ] tsc 통과 / lint 신규 0 / build 통과
- [ ] globals.css diff 0줄 / components/ui/* diff 0줄 / sayeon/page.tsx diff 0줄
- [ ] 기존 라우트 보존
```

---

## 환경 변수 규칙
- **비밀 키 `NEXT_PUBLIC_` 접두사 절대 금지** (브라우저 노출). 서버사이드 전용.
- WaveSpeed 등 외부 호출은 서버사이드 API route 경유.
- 허용된 `NEXT_PUBLIC_`: `NEXT_PUBLIC_API_BASE_URL` (URL은 노출 무방).
- `CRON_SECRET`: 모든 cron 잡이 공유하는 인증 시크릿. **추가/변경 후 재배포 필수.**
- `R2_CHARACTER_BUCKET`: 캐릭터 시트 영구 보존 버킷(Lifecycle 없음). 설정됨.

---

## 로컬 개발 실행
```bash
npm run dev                                        # 프론트 localhost:3000
cd travel-pipeline
py -m uvicorn api.server:app --port 8000           # ⚠️ py 필수 (--reload 좀비 주의)
```
> Python은 반드시 `py`. PowerShell: `&&` 금지, `$env:` 사용. localhost는 `127.0.0.1` 명시.

---

## PR & 브랜치 규칙
- 항상 `main`에서 분기 (기존 PR 브랜치 재사용 금지).
- PR 1개당 기능 1개. 큰 작업은 **조사 → 설계 → 작게 쪼갠 PR**.
- 작업 전 관련 파일 직접 읽기 (추정 금지). 모든 작업지시서에 **0단계 사전조사** 포함.
- 새 Supabase 테이블은 **GRANT 필수**: `grant all on table X to service_role, anon, authenticated;`
- 트렌드 영역 **가짜/더미 데이터 금지** (빈 그릇만).

---

## 인프라 (2026-06 기준)

| 영역 | 구성 |
|---|---|
| 프론트 | Next.js 16 → **Vercel (Hobby 무료, 결제수단 없음)**, `reelbot-pipeline.vercel.app`, main 자동배포 |
| 백엔드 | Python FastAPI(`travel-pipeline/`) → **Railway** `adventurous-renewal` (영상 제작 파이프라인) |
| DB/스토리지 | Supabase + Cloudflare R2 |
| 스케줄 | **cron-job.org (외부, 무료)** — Vercel Hobby 크론 제약(시간당1회·10초) 회피. 전부 무료 |
| AI | OpenAI(gpt-image-1, gpt-4o-mini) / WaveSpeed(Kling, Z-Image Turbo) / ElevenLabs(eleven_multilingual_v2) |

---

## 🎯 전체 시스템 흐름 (자동화 완성 — 2026-06-15)

```
[새벽 2시 · cron-job.org]  trend-channel 0~5 → trend-finalize → roll
   = 6개 썰채널 트렌드 분석(GPT 9컨셉 분류) + 30일 뒤 1일치 캘린더 자동 생성   (7c)

[30분마다 · cron-job.org]  produce-due
   = 가동 중이면 → 캘린더의 "시각 지난 planned 슬롯" 1개 → 그 컨셉으로 흰곰 영상
     제작 → 모드대로 공개/비공개 유튜브 업로드 → status='done'                (2단계)

[수동 · 대시보드 시작(녹색) 버튼]
   = 트렌드 가중 랜덤 컨셉으로 흰곰 영상 1개 즉석 제작 + 사이드바 "가동 중"     (1단계)
```

### 운영 모드 (토글 2종)
- **가동 토글(is_active)** = 사이드바 녹색불 = "채널 운영 ON". produce-due는 ON일 때만 자동 제작 (OFF = 정지 스위치).
- **모드 토글(channel_status.mode)** = `auto`(공개) / `semi`(반자동·비공개, 기본).
- 조합: ON+auto=완전 무인 공개 / ON+semi=자동 제작 후 비공개로 쌓임(검토 후 공개) / OFF=정지.

---

## 핵심 사실 — 반드시 숙지 (함정·교훈)

1. **백곰 캐릭터는 백엔드 코드에 하드코딩** (`travel-pipeline/services/sayeon_character.py`의 `_POLAR_BEAR_CORE`).
   → **어떤 캐릭터 spec을 넘겨도 영상 주인공은 항상 흰곰.** 사람 spec(성별·나이)은 대본 화자 힌트로만. 캐릭터는 걱정 불필요.
   시트: R2 `sayeon/characters/{job_id}/sheet.png`, `R2_CHARACTER_BUCKET`로 영구.
2. **`sayeon_characters` 등 테이블 GRANT 누락 = `permission denied`(401)**. 권한 문제는 항상 GRANT부터 의심.
3. **캘린더(content_plans)와 제작 연결** = 컨셉명을 그대로 `topic`으로 전달 → autoscript가 '소재 결'로 사용 (매핑표 불필요).
4. **영상 제작은 수 분 → Vercel 10초 불가 → Railway 비동기**(BackgroundTasks, JobManager는 **인메모리**, 재시작 시 소실). `generate`는 job_id 즉시 반환 → 크론은 트리거만.
5. **CRON_SECRET 헤더**: cron-job.org는 Key=`Authorization`, Value=`Bearer <시크릿>`. Vercel `CRON_SECRET`은 Bearer 없는 순수값. 모든 잡 동일 시크릿. 변경 후 **재배포 필수**.
6. **단일 진실 출처**: `raw.githubusercontent.com/allviewkorea-byte/reelbot-pipeline/main/CLAUDE.md` (claude.ai 프로젝트 업로드본은 자동 동기화 X).

---

## Supabase 테이블 (모두 GRANT 완료)
- `content_plans`: id, channel_id, date, concept, title, status(planned/done/skipped), memo, slot(morning/evening/night), scheduled_time
- `channel_status`: channel_id PK, is_active, **mode(auto/semi)**, updated_at
- `trend_rankings`: id('{channelId}_{date}'), channel_id, date, source(gpt/keyword), rankings jsonb
- `trend_channel_videos`: id('{date}_{index}'), channel_id, date, source_ref, videos jsonb (7c 부분저장)
- `sayeon_characters`: id, name, spec(jsonb 8필드), sheet_url, anchor, is_default, created_at  ← **GRANT 확인 필수**

---

## 백엔드 영상 파이프라인 (`travel-pipeline/services/`)
`sayeon_autoscript`(대본, gpt-4o-mini, _TOPIC_POOL/topic) → `sayeon_director`(샷리스트) → 캐릭터시트(흰곰, R2) →
씬 이미지(WaveSpeed) → `sayeon_tts`(ElevenLabs eleven_multilingual_v2) → `sayeon_bgm`(R2 랜덤) → 자막 →
`sayeon_assemble`(ffmpeg `-c copy`, OOM 회피) → `sayeon_thumbnail` → `youtube_upload`.
- 업로드 게이트: `YOUTUBE_AUTO_PUBLISH=true`. privacy = 인자 주입(#129) > `YOUTUBE_PRIVACY_STATUS` env > public.
- 트리거: 프론트 → `/api/sayeon/generate-script`(랜덤/topic) → `/api/sayeon/generate`(프록시가 mode→privacy 주입). job_id → 노드그래프(`/api/jobs/active`).

---

## 주요 크론 라우트 (Next, CRON_SECRET 보호, 멱등)
- `GET /api/cron/trend-channel?index=N` — 채널 1개 수집·부분저장 (7c)
- `GET /api/cron/trend-finalize` — 부분결과 merge → GPT 분류(최대 30개, maxDuration=60) → trend_rankings (7c)
- `GET /api/cron/roll` — rollOne 캘린더 +30일 1일치 (7c)
- `GET /api/cron/produce-due` — 가동게이트→일일상한(3)→due 1개→캘린더 컨셉 제작→done (2단계, maxDuration=60)
- `GET /api/sayeon/pick-topic` — 트렌드 가중 컨셉 1개(7b 재사용), 없으면 빈값 (1단계 수동 제작용)

---

## 완료된 주요 PR (최신 세션, 2026-06)

### 트렌드 엔진 (7a~7c)
- #119~#127: 트렌드 분류 엔진(6 썰채널 → GPT 9컨셉), 패널 시각화, 캘린더 롤링 자동생성(가중 랜덤+30% 상한+연속 회피), 7c 채널분할 자동실행 크론
- 9컨셉: 가족/이별/직장돈/복수/반전/감동/우정배신/연애/기타

### 영상 자동화 (이번 세션)
- #128: trend-finalize 타임아웃 수정(GPT 100→30, maxDuration=60)
- #129: 공개/비공개 모드 토글(channel_status.mode, 프록시 privacy 주입, sayeon/page 무수정)
- #132: 잘못 만든 "지금 제작" 버튼 제거
- #133: **1단계 PR-1** — 시작 버튼 = 가동 ON + 화면 없이 흰곰 제작 + privacy
- #134: **1단계 PR-2** — 시작 버튼 컨셉을 트렌드 가중 랜덤으로(pick-topic, 7b 재사용)
- #135: **2단계** — produce-due 크론(캘린더 due 슬롯 자동 제작)

---

## 워크플로 패턴
claude.ai(전략·작업지시서) → Claude Code(코딩·PR) → 대표 머지 → Vercel 자동배포 → 시크릿창 확인.
- 작업지시서는 복사 가능한 한국어, 0단계 조사 + 검증 + "하지 말 것" 포함.
- 응답 스타일: 간결·직접, 2~3 선택지, 명확한 추천, 행동 전 장황한 설명 금지.

---

## 🌐 멀티 채널 확장 계획 (제2 채널 ~)

목표: 백곰 릴봇을 **공유 엔진 1개 + 채널별 프로필**로 일반화 → 사이드탭에 채널 추가하면
"복붙하듯" 새 채널 가동. **UX는 복붙, 구현은 파라미터화** (코드 N개 복사 = 유지보수 N배 지옥, 금지).

### 3-버킷 분리
- **재사용(껍데기+기능)**: 대시보드·트렌드 분석·스케줄·TTS/BGM/합성/업로드·YouTube 연동·R2 로직·오케스트레이션 → 공유 엔진, 무수정.
- **채워넣기(채널 프로필)**: 채널명·마스코트 컨셉·보이스·토픽 가중치·OAuth/channel_id·R2 네임스페이스·스타일.
- **새 제작(콘텐츠 생성)**: 캐스트 시트(신규 마스코트)·스크립트/디렉터 톤·포맷·씬 생성 방식 → 채널마다 새로. ★"새 제작 여지"

### 단계
0. **(키스톤) 프로필 추출**: 백곰 하드코딩(`_POLAR_BEAR_CORE`·캐스트 바이블·보이스·R2 경로·OAuth) → 채널 프로필(DB+설정)로 분리. 엔진 채널-무관화. *이게 돼야 2번 채널 "복붙" 가능.*
1. 채널 레지스트리 + 대시보드 채널 전환(사이드바 "내 채널" 토대 활용).
2. 신규 채널 온보딩(수동 프로필 입력 → 캐스트 생성 → 가동) — **2채널 운영 증명**.
3. 레퍼런스 링크 분석기: 링크 → YouTube Data API 수집 → LLM 레시피 추론(장르·톤·캐릭터·길이·주기) → 프로필 초안 → 대표 승인 → 가동.
4. 채널별 파이프라인 변형(필요 곳만 플러그인식).

### 협업 모델
claude.ai가 "필요 정보 리스트" 제공 → 대표가 정보 제공 → Claude Code가 프로필 반영해 완성.
**신규 채널 입력값**: 정체성(이름·장르·타깃) / 마스코트(동물·외형·성격) / 나레이터 보이스 / 토픽+가중치 / 비주얼 스타일 / OAuth·channel_id / 업로드 스케줄 / ★콘텐츠 톤·포맷.

### 원칙
- 코드 복붙(채널별 사본) 금지 → 단일 엔진+프로필이 정답.
- 레퍼런스 분석은 "초안"까지만, 최종 대표 승인(취향·IP 위험).
- 비용 채널당 선형 증가.

---

## 남은 일 (우선순위 낮음, 운영하며)
1. **영상 품질**: 대본 매끄러움(피드백: "이야기가 매끄럽지 않다"), 나레이션 속도, 썸네일 다양화.
2. **음악 컨셉 매칭**: 현재 R2 랜덤 BGM → 컨셉별 선택(`sayeon_bgm`). (유튜브 API로 음악 추가 불가, 영상에 내장.)
3. **멀티 채널**: → "🌐 멀티 채널 확장 계획" 섹션 참조. (백곰 안정화 후 0단계부터)
4. **트렌드 분류 정밀도**: 이별↔가족 오분류(장례·파혼) 다듬기.
5. **누락분 캐치업**: produce-due v1은 "오늘 due"만. 지난 날짜 미처리 planned는 스킵.
6. JobManager 인메모리 → 영속화(추후).

---

## 운영 체크리스트
- 자동 제작 확인: 가동 ON + 슬롯 시각 후 → 노드그래프 / 유튜브 (비공개) 영상.
- produce-due 잡 저장·Enable·"Next execution" 확인 (TEST RUN만으론 자동 안 됨).
- 트렌드/캘린더 매일 갱신: 다음날 대시보드 분석일·캘린더 끝 날짜.
- 401 시: cron-job.org 헤더(`Authorization: Bearer <시크릿>`)가 기존 7c 잡과 동일한지.
