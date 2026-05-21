"""트렌드 분석 도메인 모델 (pydantic).

프론트엔드 `src/types/trend.ts` 와 동일한 스키마를 유지한다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

VideoFormat = Literal["shorts", "long"]


class PowerWord(BaseModel):
    word: str
    count: int


class DescriptionPattern(BaseModel):
    first150_keywords: list[str] = Field(default_factory=list, alias="first150Keywords")
    hook_structure: str = Field(default="", alias="hookStructure")

    model_config = {"populate_by_name": True}


class TagsByCategory(BaseModel):
    primary: list[str] = Field(default_factory=list)
    variants: list[str] = Field(default_factory=list)
    competitor: list[str] = Field(default_factory=list)
    broad: list[str] = Field(default_factory=list)
    niche: list[str] = Field(default_factory=list)


class Sentiment(BaseModel):
    positive: float = 0.0
    negative: float = 0.0
    neutral: float = 0.0


class CommentInsights(BaseModel):
    sentiment: Sentiment = Field(default_factory=Sentiment)
    faqs: list[str] = Field(default_factory=list)
    content_ideas: list[str] = Field(default_factory=list, alias="contentIdeas")

    model_config = {"populate_by_name": True}


class TrendInsight(BaseModel):
    channel_id: str = Field(alias="channelId")
    category: str
    format: VideoFormat
    analyzed_at: str = Field(alias="analyzedAt")

    avg_video_length_sec: float = Field(default=0.0, alias="avgVideoLengthSec")
    avg_title_length: float = Field(default=0.0, alias="avgTitleLength")
    power_words: list[PowerWord] = Field(default_factory=list, alias="powerWords")

    description_pattern: DescriptionPattern = Field(
        default_factory=DescriptionPattern, alias="descriptionPattern"
    )
    tags_by_category: TagsByCategory = Field(
        default_factory=TagsByCategory, alias="tagsByCategory"
    )

    hook_patterns: list[str] = Field(default_factory=list, alias="hookPatterns")
    popular_upload_hours: list[int] = Field(default_factory=list, alias="popularUploadHours")

    comment_insights: CommentInsights = Field(
        default_factory=CommentInsights, alias="commentInsights"
    )

    model_config = {"populate_by_name": True}


class TrendSettings(BaseModel):
    enabled: bool = False
    keywords: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    formats: list[VideoFormat] = Field(default_factory=list)
    schedule: Literal["daily", "manual"] = "daily"
    last_analyzed_at: str | None = Field(default=None, alias="lastAnalyzedAt")

    model_config = {"populate_by_name": True}


# ── API 요청 모델 ────────────────────────────────────────────────────


class TrendAnalyzeRequest(BaseModel):
    channel_id: str = Field(alias="channelId")
    keywords: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    formats: list[VideoFormat] = Field(default_factory=lambda: ["shorts", "long"])

    model_config = {"populate_by_name": True}


class TrendAnalyzeResponse(BaseModel):
    job_id: str
    status: str
