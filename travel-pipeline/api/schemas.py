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


class SayeonSplitRequest(BaseModel):
    script: str  # 국문 사연 대본
    num_scenes: int | None = None
    character_anchor: str | None = None


class SayeonScene(BaseModel):
    index: int
    narration: str   # 국문, TTS 낭독 (S3)
    subtitle: str    # 국문, 화면 자막 (S4)
    highlight: str   # subtitle 내 강조 핵심구 (S4)
    image_prompt: str  # 영문, 배경·상황·동작·감정·구도 (S2)
    motion: str      # zoom_in | zoom_out | pan_left | pan_right (S4)


class SayeonSplitResponse(BaseModel):
    scenes: list[SayeonScene]


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


class SayeonTtsRequest(BaseModel):
    scenes: list[dict]  # [{"index", "narration"}, ...] (S1 출력)
    voice_id: str | None = None
    gap_sec: float = 0.4


class SayeonScenesRequest(BaseModel):
    channel_id: str = ""
    sheet_url: str  # PR-S2a 가 만든 캐릭터 시트 공개 URL (reference)
    anchor: str = ""
    scenes: list[dict]  # PR-S1 산출물: [{"index", "image_prompt", ...}]
    num_images: int = 2
    seed: int = -1


class SayeonAssembleRequest(BaseModel):
    # 씬: [{index, image_url, subtitle, highlight, motion}] (S1+S2 결합)
    scenes: list[dict]
    # 타이밍: [{index, start, end, duration}] (S3 출력)
    scene_timings: list[dict]
    audio_url: str  # S3 나레이션 오디오 URL


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
