# Phase 2 완료 보고 — UI ↔ API 연결

작업 브랜치: `claude/phase2-status-check-4JVhZ`

## 구현된 것
- **API 클라이언트** `src/lib/api.ts` — `ApiError`, 타입(백엔드 `schemas.py`·`main.generate_scenario` 모양과 일치), 폴링 헬퍼(`pollJobStatus`, cleanup 반환).
- **Proxy 헬퍼** `src/lib/proxy.ts` + **Next API Route 6개**
  - `GET /api/health`
  - `POST /api/storyboard/scenario` → 백엔드 `/storyboard/scenario`
  - `POST /api/storyboard/generate`
  - `POST /api/storyboard/regenerate`
  - `POST /api/video/start`
  - `GET /api/jobs/[jobId]/status`
  - 백엔드 미응답 시 503 + 한국어 에러 메시지.
- **React Hooks 3개** `src/hooks/`
  - `useHealthCheck` (5초 폴링)
  - `useStoryboard` (콘티 생성/폴링/단일 씬 재생성)
  - `useVideoGeneration` (영상 생성/폴링)
- **컴포넌트 5개** `src/components/video/`
  - `HealthIndicator` (사이드바 하단 dot)
  - `StoryboardReview` / `SceneCard` (콘티 그리드 + 승인/재생성/수정)
  - `ProgressTracker` (진행률 바)
  - `ResultViewer` (영상 미리보기 + 다운로드)
- **페이지** `src/app/video/create/page.tsx` — `input → storyboard → generating → done` 4단계 흐름.

## 변경된 파일 (최소)
- `src/components/layout/Sidebar.tsx` — 하단에 `<HealthIndicator />` dot 추가.
- `src/app/video/page.tsx` — 헤더에 `/video/create`로 가는 "자동 제작" 링크 1개 추가 (기존 mock UI 보존).
- `.env.example` 신규 — `NEXT_PUBLIC_API_BASE_URL`.
- **디자인 시스템(`globals.css`, tailwind 설정, 색상 토큰) 일절 미수정.** 신규 UI는 기존 토큰/유틸 클래스(emerald/amber/red, `bg-card`, `border-border`, `text-primary` 등)만 사용.

## 검증 결과 (이 컨테이너에서 가능한 부분)
- `tsc --noEmit`: 통과
- `eslint` (신규 파일): 통과
- `next build`: Phase 2 라우트/페이지 정상 빌드 (※ 무관한 기존 `/api/scenario/generate`가 빌드 시 `OPENAI_API_KEY`를 요구해 더미 키로 우회 확인)
- dev 서버 런타임: `/video/create` 200, `/api/health`·`/api/jobs/*` 백엔드 오프라인 시 503+한국어 메시지, 기존 `/video` 200
- 실제 API 호출·영상 생성: ⚠️ 사용자 로컬에서 두 서버 띄우고 확인 필요

## 알려진 이슈 / 의문점
- **콘티/영상 이미지 정적 서빙 미정**: 백엔드는 `image_path`(서버 로컬 경로, 예 `output/storyboard/{job}/scene_1.png`)만 반환하고 정적 URL을 노출하지 않음. 프론트는 `image_url` 우선, 없으면 `API_BASE/{path}`로 시도하고 실패 시 플레이스홀더 표시. 실제 미리보기가 보이려면 **FastAPI에 `StaticFiles`로 `output/` 마운트**가 필요해 보임.
- 영상 결과 키(`video_url`/`video_path`/`output_path`)를 다중 폴백으로 처리 — 백엔드 실제 반환 키 확인 권장.
- 빌드 차단 요인인 `/api/scenario/generate`의 모듈 로드 시 `new OpenAI()`는 Phase 2 범위 밖이라 손대지 않음.

## 다음 단계
사용자 로컬에서 `npm run dev`(3000) + `python -m api.server`(8000) 띄우고 `/video/create` 접속 → 실제 영상 1편 생성 시도. 문제 발생 시 보고.
