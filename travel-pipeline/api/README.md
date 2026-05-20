# ReelBot Pipeline API (Phase 1)

UI ↔ Python 파이프라인을 잇는 FastAPI 백엔드. 영상 생성 전에 **콘티(스토리보드) 이미지로 시각 검증**하는 단계를 제공한다.

## 서버 실행

```bash
cd travel-pipeline
pip install -r requirements.txt          # fastapi, uvicorn, pydantic 포함
cp .env.example .env                      # 키 채우기 (OPENAI_API_KEY 등)
python -m api.server                      # http://localhost:8000
```

- Swagger UI: http://localhost:8000/docs
- CORS는 `http://localhost:3000` (Next.js dev) 허용

## 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| GET | `/health` | 헬스체크 |
| POST | `/storyboard/scenario` | (동기) 국가+길이 → 시나리오 + 씬 리스트 생성 |
| POST | `/storyboard/generate` | (비동기) 씬 리스트 → 씬별 콘티 이미지 생성, `job_id` 반환 |
| POST | `/storyboard/regenerate` | (비동기) 특정 씬 콘티만 재생성 |
| POST | `/video/start` | (비동기) 승인된 콘티 → Kling 영상 생성 + 합성 |
| GET | `/jobs/{job_id}/status` | 작업 진행 상황 폴링 |

비동기 작업은 `job_id`를 즉시 반환하고 백그라운드에서 실행된다. `/jobs/{job_id}/status`로
`progress`(0-100)와 `current_step`을 폴링한다.

> ⚠️ Job 큐는 in-memory(MVP)다. **서버 재시작 시 작업 기록은 사라진다.** 영구 저장은 Phase 3.

## 전형적 흐름

```
1. POST /storyboard/scenario   { "country": "Thailand", "duration_min": 1 }
       → { scenario, scenes: [...] }
2. POST /storyboard/generate   { "scenes": [...], "character_image_path": "..." }
       → { job_id }
3. GET  /jobs/{job_id}/status  (폴링) → result.storyboards = [{scene_id, image_path, ...}]
   (마음에 안 들면 POST /storyboard/regenerate 로 특정 씬 다시 생성)
4. POST /video/start           { "scenes": [...], "approved_storyboards": [...], "seedance_mode": "kie" }
       → { job_id }
5. GET  /jobs/{job_id}/status  (폴링) → result.final_video
```

## curl 테스트

```bash
curl http://localhost:8000/health

curl -X POST http://localhost:8000/storyboard/generate \
  -H "Content-Type: application/json" \
  -d '{"scenes":[{"scene_id":1,"description":"walking the night market","camera":"wide shot","location":"Khao San Road"}]}'

curl http://localhost:8000/jobs/<job_id>/status
```

## 이미지 모델

콘티 생성은 `gpt-image-1`, 사이즈 `1024x1536`, quality `high`를 사용한다 (`character.py`와 동일).
캐릭터 reference 이미지가 있으면 `images.edit`로 캐릭터 일관성을 유지한다.

## 산출물 경로

- 콘티: `output/storyboard/{job_id}/scene_{id}.png` (+ `.json` 메타/캐시키)
- 영상: `output/video/{job_id}/clips/`, 최종 `output/video/{job_id}/final.mp4`

동일 (씬 + 캐릭터) 조합이면 콘티는 캐시 재사용하고, `regenerate`만 강제 재호출한다.
