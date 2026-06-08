"""Pydantic 요청/응답 모델."""

from __future__ import annotations

from pydantic import BaseModel


class ScenarioGenerateRequest(BaseModel):
    country: str
    duration_min: int = 1


class StoryboardGenerateRequest(BaseModel):
    scenario: str = ""
    character_name: str = ""
    character_image_path: str | None = None
    scenes: list[dict]
    storyboard_model: str = "default"


class StoryboardGenerateResponse(BaseModel):
    job_id: str
    status: str


class StoryboardRegenerateRequest(BaseModel):
    job_id: str
    scene_id: int
    scene: dict
    character_image_path: str | None = None
    extra_instructions: str | None = None
    storyboard_model: str = "default"


class VideoStartRequest(BaseModel):
    job_id: str  # 이전 storyboard job의 id (참조용)
    scenes: list[dict]
    approved_storyboards: list[dict]
    scenario_mode: str = "B"
    seedance_mode: str = "kie"
    video_model: str = "default"
    character_id: str | None = None


class CharacterSpec(BaseModel):
    """사연 캐릭터 명세 (캐릭터 라이브러리 설정 폼과 대응)."""

    gender: str = ""
    age: str = ""
    face: str = ""
    hair: str = ""
    outfit: str = ""
    accessories: str = ""
    signature: str = ""
    extra: str = ""


class SayeonSheetRequest(BaseModel):
    channel_id: str
    character: CharacterSpec
    sheet_model: str | None = None


class SayeonScenesRequest(BaseModel):
    channel_id: str = ""
    sheet_url: str  # PR-S2a 가 만든 캐릭터 시트 공개 URL (reference)
    anchor: str = ""
    scenes: list[dict]  # PR-S1 산출물: [{"index", "image_prompt", ...}]
    num_images: int = 2
    seed: int = -1


class SayeonJobResponse(BaseModel):
    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    current_step: str
    result: dict | None = None
    error: str | None = None
