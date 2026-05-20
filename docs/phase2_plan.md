# 릴봇 자동화 Phase 2 작업 지시서

> **이 문서는 Claude Code 세션에 던지기 위한 작업 지시서입니다.**  
> 작성일: 2026-05-20  
> 작성: claude.ai 채팅 (Opus 4.7) — 사용자와 설계 합의 후 작성  
> 실행자: Claude Code

---

## 📚 전체 컨텍스트 (먼저 읽어주세요)

### Phase 1까지의 진행 상황
- ✅ Next.js UI (`localhost:3000`) — 디자인 시스템, 시나리오/캐릭터 페이지 완성
- ✅ FastAPI 백엔드 (`localhost:8000`) — 5+1개 엔드포인트, 콘티 생성, 영상 생성, 폴링
- ✅ Python 파이프라인 — 방콕 19초 영상 1편 완성으로 검증
- ❌ **UI ↔ 백엔드 미연결** — 이번 Phase의 미션

### Phase 2의 핵심 가치
**사용자가 `localhost:3000`에서 클릭만으로 시나리오 입력 → 콘티 검토 → 영상 생성까지 끝낼 수 있게 한다.**

PowerShell, Swagger UI, JSON 입력 같은 개발자 도구를 **사용자가 더 이상 만질 필요 없게** 만드는 게 목표.

### 검증 전략 — "점진적 업데이트"
Phase 1 검증은 의도적으로 건너뜀. UI 통합 후 다음과 같이 자연스럽게 검증:
1. UI 헤더에 백엔드 헬스체크 인디케이터 (✓/✗) 표시
2. 각 단계마다 에러 핸들링 + 사용자 친화적 메시지
3. 실제 영상 1편 생성으로 end-to-end 검증
4. 문제 생기면 그 시점에 그 자리에서 디버깅

### 참고 문서
- Phase 1 작업 지시서: `docs/phase1_plan.md`
- 인수인계서: `reelbot_handover_v4.md`
- 디자인 시스템: `src/app/globals.css`의 `@theme inline` 블록

---

## ⛔ 절대 지킬 것 (위반 시 작업 중단하고 사용자에게 보고)

### 1. 🎨 디자인 시스템 — 절대 변경 금지 (재차 강조)
이번 Phase는 **UI 작업이라 디자인 시스템을 가장 많이 만질 위험**이 있습니다. 다음을 절대 수정하지 마세요:

```css
--background: 222 47% 11%   /* 다크 네이비 */
--sidebar: 222 47% 8%
--card: 222 47% 14%
--primary: 265 89% 66%      /* 라벤더 보라 */
/* 액센트: emerald-600 (저장 버튼 등) */
```

- `src/app/globals.css`의 `@theme inline` 블록 **수정 금지**
- 컴포넌트에서 색상 변경 시 **CSS 변수만 사용** (하드코딩 hex 금지)
- shadcn/ui 컴포넌트의 기존 스타일 변경 금지
- 차트 컬러: 보라/시안/주황 (이미 정의된 그대로)

새 컴포넌트 만들 때도 **기존 디자인 토큰만 사용**. 새 색상 추가 절대 금지.

### 2. 기존 페이지/컴포넌트 깨지 않기
- 기존 `/dashboard`, `/scenario`, `/character`, `/video` 등 페이지가 **여전히 작동해야 함**
- 기존 API Route (`src/app/api/...`)가 있다면 그대로 유지하면서 확장
- 기존 컴포넌트 props 변경 시 backward compatibility 유지

### 3. 환경 변수
이번 Phase에서 추가할 환경 변수:
```
# .env.local
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

- `.env.example`에도 추가
- 기존 환경 변수 건드리지 말 것

### 4. GitHub Push
- 작업 끝나면 commit + push (브랜치명: `claude/phase2-ui-integration` 권장)
- main 직접 push 시도하지 말 것
- 푸시 후 main 머지는 사용자가 결정

---

## 🎯 Phase 2 목표

### 사용자 시나리오 (이게 완성되면 Phase 2 끝)
1. 사용자가 `http://localhost:3000` 접속
2. (가능하면) 사이드바 또는 헤더에 백엔드 연결 상태 표시 (✓ 또는 ✗)
3. 영상 생성 페이지(`/video` 또는 새 페이지) 접속
4. 시나리오 입력 폼 (또는 기존 시나리오 페이지 활용)
5. **[콘티 생성] 버튼 클릭** → 진행률 표시
6. 콘티 검토 화면 (씬별 이미지 그리드)
   - 각 씬: [✅ 승인] / [🔄 재생성] / [✏️ 프롬프트 수정]
7. 모든 씬 승인 → **[영상 생성 시작] 버튼** 활성화
8. 진행 상황 표시 (씬별 진행률, 현재 단계)
9. 완성된 영상 미리보기 + 다운로드 링크

---

## 🗂️ 작업 범위 — 무엇을 만드는가

### 신규 파일

```
src/
├── lib/
│   └── api.ts                  ← NEW (FastAPI 호출 클라이언트)
├── hooks/                       ← NEW 폴더 (없다면)
│   ├── useStoryboard.ts        ← NEW (콘티 생성/폴링)
│   ├── useVideoGeneration.ts   ← NEW (영상 생성/폴링)
│   └── useHealthCheck.ts       ← NEW (백엔드 헬스체크)
├── components/
│   └── video/                  ← NEW 폴더
│       ├── StoryboardReview.tsx     ← NEW (콘티 검토 그리드)
│       ├── SceneCard.tsx            ← NEW (씬 개별 카드)
│       ├── ProgressTracker.tsx      ← NEW (진행률 바)
│       ├── ResultViewer.tsx         ← NEW (영상 결과)
│       └── HealthIndicator.tsx      ← NEW (백엔드 연결 상태)
└── app/
    ├── api/
    │   ├── storyboard/
    │   │   ├── generate/route.ts        ← NEW (proxy to FastAPI)
    │   │   ├── regenerate/route.ts      ← NEW
    │   │   └── scenario/route.ts        ← NEW
    │   ├── video/
    │   │   └── start/route.ts           ← NEW
    │   ├── jobs/
    │   │   └── [jobId]/status/route.ts  ← NEW
    │   └── health/route.ts              ← NEW (or 기존 활용)
    └── video/
        └── create/page.tsx              ← NEW or 기존 /video 확장
```

### 수정 파일 (최소화)
- `src/app/layout.tsx` — HealthIndicator를 사이드바/헤더에 추가 (조심스럽게)
- `.env.example` — `NEXT_PUBLIC_API_BASE_URL` 추가
- 기존 `/video` 페이지 — 새 흐름과 연결 (가능하면 점진적으로)

### 절대 안 만짐
- `src/app/globals.css`
- `tailwind.config.ts`
- 기존 디자인 컴포넌트 (Button, Card 등 shadcn/ui)
- `/dashboard`, `/scenario`, `/character` 기존 페이지의 시각적 요소

---

## 🔨 단계별 작업 체크리스트

### Step 0: 현황 점검 (먼저!)
- [ ] `src/app/` 전체 구조 확인 (기존 페이지/라우트 파악)
- [ ] `src/app/globals.css`의 `@theme inline` 블록 — 현재 디자인 토큰 확인
- [ ] `src/components/` 기존 컴포넌트 목록 (shadcn/ui 어떤 것들이 설치돼 있는지)
- [ ] `src/app/video/page.tsx` 현재 상태 — 어떻게 확장할지 판단
- [ ] 기존 API Route (`src/app/api/...`) 목록
- [ ] **사용자에게 현황 보고** — "구조 파악 끝났고 이렇게 진행하겠습니다" 한 줄 요약

### Step 1: API Client 모듈 (`src/lib/api.ts`)
FastAPI 호출 함수들 모음:

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export async function healthCheck(): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new ApiError('Backend health check failed', res.status);
  return res.json();
}

export async function generateScenario(params: { country: string; duration_min: number }): Promise<ScenarioResponse> { ... }
export async function generateStoryboard(params: StoryboardGenerateParams): Promise<{ job_id: string; status: string }> { ... }
export async function regenerateScene(params: SceneRegenerateParams): Promise<{ job_id: string; status: string }> { ... }
export async function startVideo(params: VideoStartParams): Promise<{ job_id: string; status: string }> { ... }
export async function getJobStatus(jobId: string): Promise<JobStatus> { ... }

// Polling helper
export function pollJobStatus(jobId: string, onUpdate: (status: JobStatus) => void, intervalMs = 2000): () => void { ... }
```

**핵심 요구사항**:
- TypeScript 엄격한 타입 (Pydantic 모델과 일치)
- 에러 핸들링 (`ApiError` 클래스)
- 폴링 헬퍼는 cleanup 함수 반환

### Step 2: Next.js API Routes (Proxy)
브라우저에서 직접 `localhost:8000` 호출도 가능하지만, **Next.js API Route를 proxy로 두는 게 안전**합니다 (CORS, 에러 처리, 미래의 SSR/캐싱 대비).

각 Route는 단순 proxy:
```typescript
// src/app/api/storyboard/generate/route.ts
export async function POST(request: Request) {
  const body = await request.json();
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/storyboard/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
```

각 엔드포인트(`scenario`, `generate`, `regenerate`, `video/start`, `jobs/[jobId]/status`, `health`)마다 proxy route 작성.

### Step 3: React Hooks
`src/hooks/`에 작업 단위 hook 작성. 각 hook은 상태 관리 + API 호출 + 폴링 캡슐화.

```typescript
// useStoryboard.ts
export function useStoryboard() {
  const [job, setJob] = useState<JobStatus | null>(null);
  const [storyboards, setStoryboards] = useState<Storyboard[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  
  const generate = async (params: StoryboardGenerateParams) => { ... };
  const regenerate = async (sceneId: number) => { ... };
  
  return { storyboards, isGenerating, generate, regenerate, error };
}
```

### Step 4: 컴포넌트 구현

#### `HealthIndicator.tsx` (사이드바/헤더에 표시)
- 5초마다 `/health` 폴링
- 연결됨: 작은 녹색 dot + "백엔드 연결됨" (또는 단순히 dot만)
- 연결 안 됨: 빨간 dot + 에러 메시지 툴팁
- **디자인 시스템 색상만 사용**: 녹색은 emerald-500, 빨강은 destructive 또는 red-500 (이미 디자인에 있다면)

#### `StoryboardReview.tsx`
- 씬별 카드 그리드 (1열 모바일, 2-3열 데스크탑)
- 카드 내부: 콘티 이미지 + 씬 설명 + 버튼 3개 (승인/재생성/수정)
- 모든 씬 승인 시 하단 "영상 생성 시작" 버튼 활성화
- **기존 Card 컴포넌트 활용** — 새 스타일 만들지 말 것

#### `SceneCard.tsx`
- props: `scene`, `storyboard`, `onApprove`, `onRegenerate`, `onEdit`
- 상태: pending / approved / regenerating
- 시각적 피드백: 승인 시 emerald 액센트, 재생성 중 로딩 스피너

#### `ProgressTracker.tsx`
- props: `jobStatus` (progress, current_step, status)
- progress bar + 현재 단계 텍스트
- **기존 Progress 컴포넌트 활용** (shadcn/ui에 있을 가능성)

#### `ResultViewer.tsx`
- 완성된 영상 미리보기 (`<video>` 태그)
- 다운로드 버튼
- 다음 액션 (새 영상 만들기 등)

### Step 5: 페이지 통합
`src/app/video/create/page.tsx` (또는 기존 `/video` 확장):

```tsx
'use client';

export default function VideoCreatePage() {
  const [phase, setPhase] = useState<'input' | 'storyboard' | 'generating' | 'done'>('input');
  // ... state for scenario, storyboards, video result
  
  return (
    <div className="container mx-auto px-4 py-8">
      {phase === 'input' && <ScenarioInputForm onSubmit={handleStartStoryboard} />}
      {phase === 'storyboard' && <StoryboardReview ... />}
      {phase === 'generating' && <ProgressTracker ... />}
      {phase === 'done' && <ResultViewer ... />}
    </div>
  );
}
```

phase 기반 흐름. 깔끔하고 디버깅 쉬움.

### Step 6: 헬스 인디케이터 통합
`src/app/layout.tsx` 또는 사이드바 컴포넌트에 `<HealthIndicator />` 추가. 
**기존 레이아웃 구조 깨지 않게 조심**. 작은 dot 하나만 추가하는 수준.

### Step 7: 로컬 테스트 (작업 끝나면 반드시)
사용자가 두 서버 띄운 상태에서:
- 창 1: `npm run dev` (localhost:3000)
- 창 2: `py -m uvicorn api.server:app --reload` (localhost:8000)

테스트 흐름:
- [ ] localhost:3000 접속 → 디자인 시스템 그대로인지 (다크 네이비 + 보라)
- [ ] HealthIndicator가 녹색 dot 표시 (백엔드 연결됨)
- [ ] 백엔드 서버 끄면 빨간 dot으로 바뀌는지
- [ ] 백엔드 다시 켜면 녹색 복귀
- [ ] /video/create (또는 새 경로) 접속 → 시나리오 입력 폼
- [ ] 시나리오 입력 → 콘티 생성 → 진행률 표시 → 콘티 그리드 나타남
- [ ] 씬 승인/재생성 버튼 작동
- [ ] 모든 씬 승인 → 영상 생성 가능
- [ ] 영상 생성 → 진행률 → 완성 → 미리보기

### Step 8: 문서화 + Commit + Push
- [ ] `docs/phase2_completion.md` 또는 README 업데이트
- [ ] `.env.example` 업데이트 확인
- [ ] git add → commit (메시지: "feat: Phase 2 - UI ↔ API integration")
- [ ] push (브랜치: `claude/phase2-ui-integration`)

---

## 📋 완료 후 사용자에게 보고할 것

```
## Phase 2 완료 보고

### ✅ 구현된 것
- API client (src/lib/api.ts)
- 7개 Next.js API Route (proxy)
- 3개 React hooks
- 5개 신규 컴포넌트
- /video/create 페이지 (전체 흐름 통합)
- HealthIndicator (사이드바/헤더)

### 📂 변경된 파일
- 신규: [목록]
- 수정: [최소화된 목록]
- 디자인 시스템(globals.css, 색상 토큰) 일절 미수정 ✓

### 🧪 검증 결과 (이 컨테이너에서 가능한 부분)
- TypeScript 컴파일: ✅
- npm run build: ✅
- 컴포넌트 렌더링 (mock 데이터): ✅
- 실제 API 호출 검증: ⚠️ 사용자 로컬에서 확인 필요

### 🐛 발견된 이슈 / 의문점
- (있으면 여기에)

### 🚀 다음 단계
사용자가 로컬에서 두 서버 띄우고 /video/create 접속 → 실제 영상 1편 생성 시도. 
문제 생기면 claude.ai 채팅으로 보고.

### 푸시된 브랜치
claude/phase2-ui-integration
```

---

## 🆘 막혔을 때 행동 지침

1. **30분 이상 같은 문제로 막힘** → 작업 중단하고 사용자에게 보고
2. **디자인 시스템 수정이 불가피해 보임** → 무조건 멈추고 사용자 confirm 요청 (디자인은 절대 변경 금지가 최우선 룰)
3. **기존 페이지가 깨질 위험** → 멈추고 확인
4. **타입 정의가 백엔드와 불일치** → `travel-pipeline/api/schemas.py` 보고 일치시키기
5. **shadcn/ui에 필요한 컴포넌트가 없음** → 새로 만들지 말고, `npx shadcn-ui@latest add [component]` 가능한지 확인 후 사용자에게 보고

---

## 💡 작업 중 참고 사항

### 디자인 일관성 (반복 강조)
- 기존 페이지(`/dashboard`, `/scenario` 등)의 **레이아웃, 간격, 폰트 크기 패턴을 그대로 따르기**
- 새 페이지는 기존 페이지를 "참고용 템플릿"으로 봐도 됨
- 새로운 시각적 스타일을 만들지 말 것

### 에러 메시지는 한국어 친화적으로
사용자가 PowerShell, JSON 같은 거 부담스러워하니까, 에러 메시지는:
- ❌ "Error: ECONNREFUSED to localhost:8000"
- ✅ "백엔드 서버가 응답하지 않습니다. PowerShell에서 서버가 실행 중인지 확인해주세요."

### 점진적 검증 메커니즘 (이번 Phase의 새 컨셉)
- HealthIndicator: 백엔드 살아있는지 시각화
- 각 API 호출에 명확한 로딩/에러 상태
- 콘티 미리보기 = 첫 단계 검증
- 영상 완성 = end-to-end 검증

검증을 별도 작업으로 두지 말고, **UI 사용 흐름 안에 내장**.

### 향후 확장 포인트 (Phase 3 대비)
다음 사항은 **자리만 마련해두고 동작은 안 만들어도 됨**:
- 모델 선택 드롭다운 (Kling v1/v2.6/v3.0) — UI placeholder만
- Premiere export 버튼 — UI placeholder만
- 다국가 채널 (도쿄, 유럽) — 현재 데이터 구조에서 확장 가능하도록

---

**끝. 이제 시작해주세요. Step 0 (현황 점검)부터.**

⚠️ **재차 강조**: 디자인 시스템(색상 토큰, globals.css)은 **어떤 경우에도** 수정하지 마세요. 이 룰이 위반되면 즉시 작업 중단하고 사용자에게 보고해주세요.
