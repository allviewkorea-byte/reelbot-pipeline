"""ReelBot Pipeline FastAPI 앱 진입점.

실행: cd travel-pipeline && python -m api.server
문서: http://localhost:8000/docs
"""

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import health, sayeon, status, storyboard, trends, video, youtube
from services.scheduler import shutdown_scheduler, start_scheduler

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 서버 시작 시 트렌드 자동 분석 스케줄러 기동, 종료 시 정리.
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(title="ReelBot Pipeline API", version="1.0.0", lifespan=lifespan)

# Next.js dev server(3000)에서 호출 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://reelbot-pipeline.vercel.app",
    ],
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
app.include_router(trends.router, prefix="/trends", tags=["trends"])
app.include_router(trends.channels_router, tags=["trends"])
app.include_router(sayeon.router, prefix="/sayeon", tags=["sayeon"])
app.include_router(youtube.router, prefix="/api/youtube", tags=["youtube"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
