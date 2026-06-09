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


class SayeonGenerateRequest(BaseModel):
    script: str                              # 사연 나레이션
    character_spec: CharacterSpec | None = None  # 시트 생성용(없고 sheet_url 없으면 에러)
    sheet_url: str | None = None             # 기존 캐릭터 시트(주면 시트 생성 스킵)
    anchor: str | None = None                # 기존 시트의 정체성 앵커
    voice_id: str | None = None              # Supertone(없으면 env 기본/Edge)
    num_scenes: int | None = None
    gap_sec: float = 0.4
    thumbnail_scene_index: int | None = None  # 썸네일용 씬(없으면 기본 컷)


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


class SayeonThumbnailRequest(BaseModel):
    image_url: str               # 썸네일 배경 씬 이미지
    hook_text: str | None = None  # 2줄 후킹(없으면 script 로 생성)
    highlight: str | None = None  # hook_text 내 노란 강조구
    script: str | None = None     # hook_text 없을 때 LLM 후킹 생성용


class SayeonThumbnailResponse(BaseModel):
    thumbnail_url: str
    hook_text: str
    highlight: str


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
