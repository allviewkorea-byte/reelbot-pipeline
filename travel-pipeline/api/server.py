"""ReelBot Pipeline FastAPI 앱 진입점.

실행: cd travel-pipeline && python -m api.server
문서: http://localhost:8000/docs
"""

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# FastAPI 진입점에서도 .env 로드 (캐릭터 reference 등 환경변수 의존).
# main.py만 load_dotenv 하던 탓에 storyboard-only 흐름에서 누락될 수 있었다.
load_dotenv()

from api.routes import health, status, storyboard, video

app = FastAPI(title="ReelBot Pipeline API", version="1.0.0")

# Next.js dev server(3000)에서 호출 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 콘티/영상 산출물(output/)을 브라우저가 접근할 수 있도록 /static 으로 서빙.
# 예) output/storyboard/{job_id}/scene_1.png -> http://localhost:8000/static/storyboard/{job_id}/scene_1.png
_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_OUTPUT_DIR)), name="static")

app.include_router(health.router)
app.include_router(storyboard.router, prefix="/storyboard", tags=["storyboard"])
app.include_router(video.router, prefix="/video", tags=["video"])
app.include_router(status.router, tags=["status"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
