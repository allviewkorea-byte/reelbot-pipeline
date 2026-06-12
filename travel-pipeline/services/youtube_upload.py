"""유튜브 업로드 서비스 — YouTube Data API v3 videos.insert + thumbnails.set.

사연 영상(mp4) + 썸네일(png) 을 채널에 업로드한다. 제목은 썸네일 카피, 설명은 대본
요약 + 고정 푸터/해시태그, 태그는 고정 리스트. 기본 공개(public), 아동용 아님,
카테고리 22(사람/블로그), 기본 언어 ko.

자격증명은 youtube_oauth.get_credentials()(refresh_token 기반, 자동 갱신).
googleapiclient import 는 함수 안에서 지연 로딩(미설치 환경 import 안전).
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path

# 영상/썸네일 다운로드는 검증된 합성 엔진 헬퍼 재사용(http URL/로컬 경로 모두 처리).
from services.sayeon_assemble import _fetch
from services.youtube_oauth import get_credentials

logger = logging.getLogger(__name__)

# 고정 태그(작업지시서).
DEFAULT_TAGS = ["실화", "사연", "공감", "백곰", "실화사연", "숏폼", "실화보고서"]

_DESC_FOOTER = (
    "📮 사연 제보는 댓글로 남겨주세요\n"
    "매일 새 실화 업로드\n\n"
    "#실화 #사연 #공감 #백곰 #실화사연 #숏폼 #백곰의실화보고서"
)


def _summarize(script: str, max_sentences: int = 3) -> str:
    """대본 첫 2~3문장 요약."""
    text = " ".join(line.strip() for line in (script or "").splitlines() if line.strip())
    if not text:
        return ""
    sentences = re.split(r"(?<=[.?!…])\s+", text)
    summary = " ".join(s for s in sentences[:max_sentences] if s).strip()
    return summary or text[:120]


def build_video_metadata(hook_text: str, script: str) -> tuple[str, str, list[str]]:
    """(제목, 설명, 태그). 제목=썸네일 카피, 설명=요약+푸터, 태그=고정."""
    title = " ".join((hook_text or "").replace("\\n", "\n").split())
    if not title:
        title = _summarize(script, 1)[:40]
    title = title[:100]  # 유튜브 제목 한도
    summary = _summarize(script)
    description = f"{summary}\n\n{_DESC_FOOTER}" if summary else _DESC_FOOTER
    return title, description, list(DEFAULT_TAGS)


def upload_video(
    video_path: str,
    title: str,
    description: str,
    thumbnail_path: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    """영상 1개를 업로드하고 (가능하면) 썸네일을 첨부. Returns {video_id, video_url}."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"업로드할 영상 파일 없음: {video_path}")

    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    privacy = (os.getenv("YOUTUBE_PRIVACY_STATUS") or "public").strip().lower()
    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags or list(DEFAULT_TAGS),
            "categoryId": "22",          # 사람 및 블로그
            "defaultLanguage": "ko",
        },
        "status": {
            "privacyStatus": privacy,    # 기본 public (테스트 시 YOUTUBE_PRIVACY_STATUS=private)
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(video_path, mimetype="video/mp4", chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()
    video_id = response["id"]
    logger.info("유튜브 업로드 완료: video_id=%s privacy=%s", video_id, privacy)

    if thumbnail_path and os.path.exists(thumbnail_path):
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype="image/png"),
            ).execute()
            logger.info("유튜브 썸네일 첨부 완료: video_id=%s", video_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("썸네일 첨부 실패(영상은 업로드됨): %s", e)

    return {"video_id": video_id, "video_url": f"https://www.youtube.com/watch?v={video_id}"}


def publish_to_youtube(
    video_url: str, thumbnail_url: str, hook_text: str, script: str
) -> dict:
    """완성 영상(URL/로컬) + 썸네일 → 메타데이터 생성 → 업로드. Returns {video_id, video_url}.

    오케스트레이터가 호출. video_url/thumbnail_url 은 R2 URL 또는 로컬 경로 모두 가능
    (_fetch 가 처리). 임시 디렉터리에 받아 업로드한다.
    """
    title, description, tags = build_video_metadata(hook_text, script)
    with tempfile.TemporaryDirectory(prefix="yt_") as tmp:
        tmp_dir = Path(tmp)
        local_video = tmp_dir / "video.mp4"
        _fetch(video_url, local_video)
        local_thumb: str | None = None
        if thumbnail_url:
            try:
                t = tmp_dir / "thumb.png"
                _fetch(thumbnail_url, t)
                local_thumb = str(t)
            except Exception as e:  # noqa: BLE001
                logger.warning("썸네일 다운로드 실패(영상만 업로드): %s", e)
        return upload_video(str(local_video), title, description, local_thumb, tags)
