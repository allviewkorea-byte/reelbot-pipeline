"""ReelBot Pipeline FastAPI 앱 진입점.

실행: cd travel-pipeline && python -m api.server
문서: http://localhost:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

app.include_router(health.router)
app.include_router(storyboard.router, prefix="/storyboard", tags=["storyboard"])
app.include_router(video.router, prefix="/video", tags=["video"])
app.include_router(status.router, tags=["status"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
