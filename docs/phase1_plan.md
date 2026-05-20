# 릴봇 자동화 Phase 1 작업 지시서

> **이 문서는 Claude Code 세션에 던지기 위한 작업 지시서입니다.**  
> 작성일: 2026-05-20  
> 작성: claude.ai 채팅 (Opus 4.7) — 사용자와 설계 합의 후 작성  
> 실행자: Claude Code

---

## 📚 전체 컨텍스트 (먼저 읽어주세요)

### 프로젝트 상태
릴봇(ReelBot)은 AI 여행 영상 자동화 파이프라인입니다. 현재 상태:
- ✅ Python 파이프라인(`travel-pipeline/`)으로 방콕 19초 영상 1편 완성 — 인프라 검증 완료
- ✅ Next.js UI(`app/`)에 시나리오/캐릭터 라이브러리 구현 완료
- ❌ **UI ↔ Python 파이프라인이 분리됨** — 현재 영상 생성은 PowerShell에서 `py main.py` 수동 실행
- ⚠️ 영상 생성 전에 결과 예측이 어려움 — 결과 안 좋으면 $0.5+ 비용 손실

### 이번 Phase 1의 위치
전체 자동화 로드맵 중 1단계 (MVP):
1. **[이번] Phase 1**: FastAPI 백엔드 + 콘티 검증 단계 추가
2. Phase 2: UI 통합 (콘티 검토 화면, 진행률 표시)
3. Phase 3: 확장 포인트 (모델 옵션, Premiere export)

**Phase 1 핵심 가치**: 
- UI ↔ Python 사이 다리(FastAPI 서버) 만들기
- 영상 생성 전에 **콘티(스토리보드) 이미지로 시각 검증** 단계 추가
- 비용 효율적 — 실패 영상 생성 줄임

### 참고 문서
- 인수인계서: `travel-pipeline/` 또는 프로젝트 루트의 `reelbot_handover_v4.md`
- 디자인 시스템: `app/globals.css`의 `@theme inline` 블록

---

## 🎯 Phase 1 목표

**`travel-pipeline/api/` 폴더에 FastAPI 서버를 구축하고, 다음 5개 엔드포인트를 제공한다:**

| Endpoint | 메서드 | 기능 |
|---|---|---|
| `/health` | GET | 서버 헬스체크 |
| `/storyboard/generate` | POST | 시나리오 → 씬별 콘티 이미지 생성 |
| `/storyboard/regenerate` | POST | 특정 씬의 콘티만 재생성 |
| `/video/start` | POST | 콘티 승인 후 영상 생성 시작 |
| `/jobs/{job_id}/status` | GET | 작업 진행 상황 폴링 |

**Phase 1 완료 조건**:
- FastAPI 서버 `uvicorn` 으로 띄울 수 있음 (`http://localhost:8000`)
- Postman/curl로 5개 엔드포인트 호출 시 정상 응답
- 시나리오 1개 → 콘티 이미지 N개 생성 → 영상 1편 완성까지 흐름 검증
- **이번 Phase에서는 UI 작업 안 함** (Phase 2 영역)

---

## ⛔ 절대 지킬 것 (위반 시 작업 중단하고 사용자에게 보고)

### 1. 디자인 시스템 — UI 파일 건드리지 말 것
이번 Phase 1은 **백엔드 작업만**입니다. 다음 색상/스타일은 **절대 수정 금지**:
- `--background: 222 47% 11%` (다크 네이비)
- `--sidebar: 222 47% 8%`
- `--card: 222 47% 14%`
- `--primary: 265 89% 66%` (라벤더 보라)
- 액센트: emerald-600
- Tailwind v4 + shadcn/ui 구성

이번 Phase는 `app/globals.css`, `app/`의 페이지/컴포넌트 파일은 건드리지 않습니다.

### 2. OpenAI 이미지 모델 — 변경 금지
- ✅ 사용: `gpt-image-1`, 사이즈 `1024x1536`, quality `high`
- ❌ 금지: `dall-e-3` (잘못된 모델)

기존 `character.py`에서 이미 이 설정 쓰고 있을 것입니다. **콘티 이미지 생성도 동일 모델 사용**.

### 3. 환경 변수 — `.env` 그대로 사용
다음 키들은 이미 `.env`에 설정되어 있음:
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GOOGLE_STREET_VIEW_KEY`
- `KIE_ACCESS_KEY` (Kling AI)
- `KIE_SECRET_KEY` (Kling AI)
- `CHARACTER_LIBRARY_FRONT` (김이안 이미지 경로)

**새로 환경 변수 추가할 거면 `.env.example`도 같이 업데이트하고 사용자에게 보고**.

### 4. 기존 코드 깨지 않기
- `main.py`의 기존 CLI 실행(`py main.py --duration 1 ...`)은 **여전히 작동해야 함**
- 즉 기존 함수들은 그대로 두고, FastAPI에서 **재사용**하는 구조로 가야 함
- 만약 `main.py` 모듈화 위해 리팩토링 필요하면 → 기존 CLI 흐름도 동일하게 작동하는지 검증

### 5. GitHub Push
- 작업 끝나면 commit + push
- Claude Code 웹 환경이라면 `claude/phase1-fastapi-backend` 같은 브랜치로 push될 것 (정상 동작)
- main 직접 push는 시도하지 마세요

---

## 🗂️ 폴더 구조 (목표)

```
reelbot-pipeline/
├── travel-pipeline/
│   ├── main.py                    (기존 — 함수화만 진행)
│   ├── kie_client.py              (기존 — 그대로)
│   ├── character.py               (기존 — 그대로)
│   ├── compose.py                 (기존 — 그대로)
│   ├── config.py                  (기존 — 그대로)
│   ├── storyboard.py              ← NEW (콘티 이미지 생성)
│   └── api/                       ← NEW 폴더
│       ├── __init__.py
│       ├── server.py              (FastAPI 앱 진입점)
│       ├── jobs.py                (in-memory job queue)
│       ├── schemas.py             (Pydantic 모델)
│       └── routes/
│           ├── __init__.py
│           ├── health.py
│           ├── storyboard.py
│           ├── video.py
│           └── status.py
└── (app/ Next.js — 이번 Phase는 건드리지 않음)
```

---

## 🔨 단계별 작업 체크리스트

### Step 0: 현황 점검 (먼저!)
- [ ] `travel-pipeline/` 폴더 전체 트리 확인 (실제 파일들 파악)
- [ ] `main.py` 메인 함수 흐름 파악 — 어디서 캐릭터 생성, 어디서 Kling 호출, 어디서 합성하는지
- [ ] `kie_client.py` 인증 방식 확인 (JWT Access + Secret 방식 맞는지)
- [ ] `character.py`에서 OpenAI 이미지 호출 부분 확인 — `gpt-image-1` 쓰는지
- [ ] `requirements.txt` 또는 `pyproject.toml` 위치 확인
- [ ] **사용자에게 현황 보고** — "구조 파악 끝났고 이렇게 진행하겠습니다" 한 줄 요약

### Step 1: 의존성 추가
- [ ] `requirements.txt`에 추가:
  ```
  fastapi>=0.110.0
  uvicorn[standard]>=0.27.0
  pydantic>=2.0
  python-multipart
  ```
- [ ] `pip install -r requirements.txt` 로 설치
- [ ] `import fastapi` 가 에러 없이 되는지 확인

### Step 2: `storyboard.py` 신규 작성
콘티 이미지 생성 로직. 다음 함수를 제공:

```python
def generate_storyboard(
    scenes: list[dict],         # [{"scene_id": 1, "description": "...", "camera": "wide shot"}, ...]
    character_image_path: str,  # config.character_library_front
    output_dir: str             # output/storyboard/{job_id}/
) -> list[dict]:
    """
    각 씬마다 gpt-image-1로 콘티 이미지를 생성한다.
    
    Returns:
        [{"scene_id": 1, "image_path": "...", "prompt": "..."}, ...]
    """
```

핵심 요구사항:
- `gpt-image-1`, `1024x1536`, quality `high` 사용
- 캐릭터 이미지를 reference로 활용 (character.py 기존 패턴 따르기)
- 카메라 앵글, 구도, 인물 배치가 잘 보이도록 프롬프트 구성
- **씬별로 1장씩 — 영상이 아닌 정지 이미지**
- 결과를 `output/storyboard/{job_id}/scene_N.png` 형식으로 저장

```python
def regenerate_single_scene(
    scene: dict,
    character_image_path: str,
    output_path: str,
    extra_instructions: str = None  # 사용자가 "더 클로즈업으로" 같은 추가 지시 가능
) -> dict:
    """한 씬만 재생성. 사용자가 마음에 안 든 씬을 다시 만들 때 사용."""
```

### Step 3: `main.py` 모듈화
**기존 CLI 흐름은 그대로 유지하면서**, 다음 함수들을 노출시킬 것:

```python
def generate_scenario(country: str, duration_min: int) -> dict:
    """Claude API로 시나리오 생성 (시나리오 + 씬 리스트)."""

def generate_video_from_storyboard(
    scenes: list[dict],
    approved_storyboards: list[dict],  # 콘티 단계에서 승인된 이미지 경로들
    output_dir: str,
    scenario_mode: str = "B",
    seedance_mode: str = "kie",
    progress_callback=None,            # 진행률 보고용 콜백
) -> dict:
    """승인된 콘티를 reference로 Kling 영상 생성 + 합성."""
```

**기존 `if __name__ == "__main__":` 블록은 위 함수들을 호출하는 형태로 변경** (CLI는 그대로 작동).

### Step 4: `api/jobs.py` — 간단한 in-memory Job Queue
Redis 같은 거 쓰지 말고 **순수 Python dict + threading**으로:

```python
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
import uuid
import threading

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class Job:
    job_id: str
    job_type: str  # "storyboard" or "video"
    status: JobStatus
    progress: int = 0       # 0-100
    current_step: str = ""  # "씬 2 콘티 생성 중..."
    result: dict = None
    error: str = None
    created_at: datetime = field(default_factory=datetime.now)

class JobManager:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
    
    def create_job(self, job_type: str) -> Job: ...
    def update_progress(self, job_id: str, progress: int, step: str): ...
    def complete_job(self, job_id: str, result: dict): ...
    def fail_job(self, job_id: str, error: str): ...
    def get_job(self, job_id: str) -> Job | None: ...

job_manager = JobManager()  # 싱글톤
```

⚠️ **서버 재시작하면 작업 기록 다 날아감** — 이건 MVP라 의도된 동작. 영구 저장은 Phase 3에서.

### Step 5: `api/schemas.py` — Pydantic 요청/응답 모델

```python
from pydantic import BaseModel

class StoryboardGenerateRequest(BaseModel):
    scenario: str           # 전체 시나리오 텍스트
    character_name: str     # "김이안" 등
    scenes: list[dict]      # 씬 메타데이터

class StoryboardGenerateResponse(BaseModel):
    job_id: str
    status: str

class StoryboardRegenerateRequest(BaseModel):
    job_id: str
    scene_id: int
    extra_instructions: str | None = None

class VideoStartRequest(BaseModel):
    job_id: str  # 이전 storyboard job의 id
    approved_storyboards: list[dict]
    scenario_mode: str = "B"
    seedance_mode: str = "kie"

class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    current_step: str
    result: dict | None = None
    error: str | None = None
```

### Step 6: `api/routes/` — 각 라우터 구현

#### `routes/health.py`
```python
@router.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}
```

#### `routes/storyboard.py`
- `POST /storyboard/generate` — `BackgroundTasks`로 백그라운드 실행
  - 즉시 `job_id` 반환
  - 백그라운드에서 `storyboard.generate_storyboard()` 호출
  - 진행률 업데이트 (씬당 진행률 갱신)
- `POST /storyboard/regenerate` — 특정 씬만 재생성

#### `routes/video.py`
- `POST /video/start` — 콘티 승인 후 영상 생성
  - 백그라운드에서 `main.generate_video_from_storyboard()` 호출
  - progress_callback으로 job_manager에 진행률 보고

#### `routes/status.py`
- `GET /jobs/{job_id}/status` — 현재 작업 상태 반환

### Step 7: `api/server.py` — FastAPI 앱

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import health, storyboard, video, status

app = FastAPI(title="ReelBot Pipeline API", version="1.0.0")

# Next.js dev server (3000번 포트)에서 호출 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(storyboard.router, prefix="/storyboard", tags=["storyboard"])
app.include_router(video.router, prefix="/video", tags=["video"])
app.include_router(status.router, tags=["status"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
```

### Step 8: 로컬 테스트 (작업 끝나면 반드시)
- [ ] 서버 띄우기: `cd travel-pipeline && python -m api.server`
- [ ] 브라우저에서 `http://localhost:8000/docs` 열기 → Swagger UI 보이는지 확인
- [ ] `/health` curl 테스트: `curl http://localhost:8000/health`
- [ ] `/storyboard/generate` 시나리오 1개로 호출 → job_id 반환되는지
- [ ] `/jobs/{job_id}/status` 폴링 → 진행률 갱신되는지
- [ ] 콘티 이미지 파일이 `output/storyboard/{job_id}/` 폴더에 생성되는지
- [ ] `/video/start` 호출 → 영상 생성 시작되는지
- [ ] 영상 완성까지 흐름이 깨지지 않는지

### Step 9: 문서화 + Commit + Push
- [ ] `travel-pipeline/api/README.md` 작성 — 서버 띄우는 법, 엔드포인트 설명, 테스트 방법
- [ ] `requirements.txt` 변경분 확인
- [ ] git add → commit (메시지: "feat: Phase 1 - FastAPI backend with storyboard validation")
- [ ] push (Claude Code 웹 환경이면 `claude/phase1-fastapi-backend` 브랜치로 자동 push됨)

---

## 📋 완료 후 사용자에게 보고할 것

작업 끝나면 다음 형식으로 보고:

```
## Phase 1 완료 보고

### ✅ 구현된 것
- FastAPI 서버 (api/server.py)
- 5개 엔드포인트
- storyboard.py (콘티 생성)
- main.py 모듈화
- in-memory job queue

### 📂 변경된 파일
- 신규: travel-pipeline/api/ (전체)
- 신규: travel-pipeline/storyboard.py
- 수정: travel-pipeline/main.py (모듈화)
- 수정: requirements.txt

### 🧪 테스트 결과
- /health: ✅
- /storyboard/generate: ✅ (씬 N개 콘티 생성 확인)
- /jobs/{id}/status: ✅
- /video/start: ✅ (영상 완성 확인)

### 🐛 발견된 이슈 / 의문점
- (있으면 여기에)

### 🚀 다음 Phase
Phase 2 (UI 통합) 진행 가능. claude.ai 채팅에서 Phase 2 plan.md 요청 권장.

### 푸시된 브랜치
claude/phase1-fastapi-backend
```

---

## 🆘 막혔을 때 행동 지침

1. **30분 이상 같은 문제로 막힘** → 작업 중단하고 사용자에게 상황 보고. 이때 `reelbot_handover_v5.md` 형태로 인수인계서 업데이트.
2. **인수인계서 v4와 모순되는 내용 발견** → 인수인계서가 더 신뢰됨. 사용자에게 확인 요청.
3. **이 plan.md에 명시되지 않은 큰 변경 필요** (예: 의존성 추가, 폴더 구조 변경) → 진행 전에 사용자에게 confirm 요청.
4. **테스트 실패** → 어떤 부분이 실패했는지, 어떤 에러가 났는지, 어떻게 해결 시도했는지 명확히 보고.

---

## 💡 작업 중 참고 사항

### 캐릭터 비용 절감 (중요)
인수인계서에 따르면 `character.py`는 이미 생성된 이미지를 **캐시 재사용**하도록 수정되어 있음. 콘티 생성도 같은 패턴으로:
- 동일 씬+캐릭터+프롬프트 조합이면 캐시된 이미지 재사용
- 사용자가 명시적으로 "재생성"한 경우에만 새로 호출

### 진행률 계산 가이드
- 콘티 생성 진행률: `progress = (현재 씬 / 전체 씬) * 100`
- 영상 생성 진행률: 
  - 씬당 Kling 호출 + 폴링 = 1단계
  - 합성(compose) = 1단계  
  - 전체 단계 중 현재 위치 / 전체 단계 = 진행률

### 비동기 처리 패턴
FastAPI `BackgroundTasks` 또는 `asyncio.create_task` 사용. 무거운 동기 작업(Kling 폴링)은 `asyncio.to_thread`로 래핑.

---

**끝. 이제 시작해주세요. Step 0 (현황 점검)부터.**
