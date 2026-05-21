"""YouTube Data API v3 어댑터.

키워드로 인기 영상을 검색하고 댓글을 수집한다.
무료 quota는 하루 10,000 units (검색 1회 = 100 units, 댓글 1회 = 1 unit).
"""

from __future__ import annotations

import os
import re
from typing import Literal

# googleapiclient 는 무거운 선택적 의존성이라 메서드 내부에서 지연 import 한다.
# (서버 부팅을 막지 않도록 — factory.py 의 선택적 어댑터 import 패턴과 동일)

VideoFormat = Literal["shorts", "long", "both"]

# ISO 8601 duration (PT#H#M#S) → 초 변환용 정규식
_DURATION_RE = re.compile(
    r"P(?:(?P<days>\d+)D)?T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?"
)


def parse_iso8601_duration(value: str) -> int:
    """ISO 8601 기간 문자열을 초 단위 정수로 변환. 파싱 실패 시 0."""
    if not value:
        return 0
    m = _DURATION_RE.fullmatch(value)
    if not m:
        return 0
    parts = {k: int(v) for k, v in m.groupdict(default="0").items()}
    return (
        parts["days"] * 86400
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )


class QuotaExceededError(RuntimeError):
    """일일 quota 한도 초과."""


class YouTubeDataAdapter:
    """YouTube Data API v3 래퍼.

    YOUTUBE_API_KEY 환경변수의 API 키를 사용한다.
    """

    SEARCH_COST = 100
    COMMENT_COST = 1
    DAILY_QUOTA = 10_000

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("YOUTUBE_API_KEY", "")
        self.quota_used = 0
        self._client = None

    def is_available(self) -> bool:
        return bool(self.api_key)

    @property
    def client(self):
        if self._client is None:
            if not self.api_key:
                raise RuntimeError("YOUTUBE_API_KEY 가 설정되지 않았습니다.")
            from googleapiclient.discovery import build

            self._client = build("youtube", "v3", developerKey=self.api_key, cache_discovery=False)
        return self._client

    def _charge(self, cost: int) -> None:
        if self.quota_used + cost > self.DAILY_QUOTA:
            raise QuotaExceededError(
                f"일일 quota 한도({self.DAILY_QUOTA}) 초과: 사용 {self.quota_used} + 요청 {cost}"
            )
        self.quota_used += cost

    def search_top_videos(
        self,
        keyword: str,
        format: VideoFormat = "both",
        max_results: int = 50,
    ) -> list[dict]:
        """키워드로 조회수 기준 인기 영상을 검색해 메타데이터를 반환한다.

        format: "shorts"(60초 이하) / "long"(60초 초과) / "both".
        반환 항목: id, title, description, tags, duration_sec, view_count,
                   published_at, channel_title.
        """
        from googleapiclient.errors import HttpError

        max_results = max(1, min(50, max_results))
        self._charge(self.SEARCH_COST)

        try:
            search = (
                self.client.search()
                .list(
                    q=keyword,
                    part="id",
                    type="video",
                    order="viewCount",
                    maxResults=max_results,
                )
                .execute()
            )
        except HttpError as e:
            raise RuntimeError(f"YouTube search 실패: {e}") from e

        video_ids = [
            item["id"]["videoId"]
            for item in search.get("items", [])
            if item.get("id", {}).get("videoId")
        ]
        if not video_ids:
            return []

        # videos.list 는 1 unit. 메타데이터 + 길이 + 통계 한 번에 조회.
        self._charge(1)
        try:
            details = (
                self.client.videos()
                .list(part="snippet,contentDetails,statistics", id=",".join(video_ids))
                .execute()
            )
        except HttpError as e:
            raise RuntimeError(f"YouTube videos.list 실패: {e}") from e

        results: list[dict] = []
        for item in details.get("items", []):
            snippet = item.get("snippet", {})
            content = item.get("contentDetails", {})
            stats = item.get("statistics", {})
            duration_sec = parse_iso8601_duration(content.get("duration", ""))

            if format == "shorts" and duration_sec > 60:
                continue
            if format == "long" and duration_sec <= 60:
                continue

            results.append(
                {
                    "id": item.get("id", ""),
                    "title": snippet.get("title", ""),
                    "description": snippet.get("description", ""),
                    "tags": snippet.get("tags", []) or [],
                    "duration_sec": duration_sec,
                    "view_count": int(stats.get("viewCount", 0) or 0),
                    "published_at": snippet.get("publishedAt", ""),
                    "channel_title": snippet.get("channelTitle", ""),
                }
            )

        results.sort(key=lambda v: v["view_count"], reverse=True)
        return results

    def get_video_comments(self, video_id: str, max_count: int = 100) -> list[str]:
        """영상의 최상위 댓글 텍스트를 최대 max_count개 수집한다."""
        from googleapiclient.errors import HttpError

        comments: list[str] = []
        page_token: str | None = None

        while len(comments) < max_count:
            self._charge(self.COMMENT_COST)
            try:
                resp = (
                    self.client.commentThreads()
                    .list(
                        part="snippet",
                        videoId=video_id,
                        maxResults=min(100, max_count - len(comments)),
                        order="relevance",
                        textFormat="plainText",
                        pageToken=page_token,
                    )
                    .execute()
                )
            except HttpError as e:
                # 댓글 비활성화 등은 치명적이지 않으므로 수집한 만큼 반환
                if e.resp.status in (403, 404):
                    break
                raise RuntimeError(f"YouTube comments 실패: {e}") from e

            for item in resp.get("items", []):
                top = item["snippet"]["topLevelComment"]["snippet"]
                text = top.get("textDisplay", "")
                if text:
                    comments.append(text)

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        return comments[:max_count]
