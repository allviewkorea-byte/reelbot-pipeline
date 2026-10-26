"""캐릭터 스튜디오(채널 공통) API — 캐릭터·역할별 기준 이미지 (A0-1). 쇼츠 /shorts/cast* 와 분리."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from services import character_measurements as cm
from services import character_studio as cs
from services import character_studio_gen as gen
from services import character_studio_import as imp

router = APIRouter()


class CharacterReq(BaseModel):
    id: str
    name: str
    channel_id: str | None = None
    bible: dict | None = None


class NewCharacterReq(BaseModel):
    name: str
    description: str
    channel_id: str | None = None


class GenItem(BaseModel):
    role: str
    prompt: str | None = None
    count: int | None = None
    refs: list[str] | None = None  # 전문가 모드: 참조로 넣을 확정 역할(빈 목록 = 참조 없음)


class GenerateReq(BaseModel):
    items: list[GenItem]
    count: int | None = None


class ImportShortsReq(BaseModel):
    channel: str = "workout_music"
    role: str


class PresetsReq(BaseModel):
    kind: str
    items: list[dict]


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except cs.StudioError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except cs.StudioNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except cs.StudioStoreError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/roles")
def roles():
    """역할 분류·필수 역할·이름 규칙."""
    return cs.role_presets()


@router.get("/characters")
def characters():
    return {"characters": _call(cs.list_characters)}


@router.post("/characters")
def save_character(req: CharacterReq):
    """캐릭터 생성·수정(id 기준)."""
    return _call(cs.upsert_character, req.id, req.name, channel_id=req.channel_id, bible=req.bible)


@router.get("/characters/{character_id}")
def character(character_id: str):
    """캐릭터 + 역할별 확정·후보 + 필수 역할(01_face·02_body) 충족 여부 + 헤어·포즈 프리셋."""
    view = _call(cs.character_view, character_id)
    return {**view, "presets": gen.presets(view["character"])}


@router.post("/characters/{character_id}/upload")
async def upload(
    character_id: str,
    file: UploadFile = File(...),
    role: str = Form(...),
    confirm: bool = Form(True),
):
    """이미지 1장 업로드 + 역할 지정. confirm=true(기본)면 그 역할의 확정으로 바로 등록."""
    data = await file.read()
    return _call(cs.save_upload, character_id, role, data, file.filename or "", confirm=confirm)


@router.post("/refs/{ref_id}/confirm")
def confirm(ref_id: int):
    """이 이미지를 그 역할의 확정으로(이전 확정은 후보로 내려감)."""
    return _call(cs.confirm_ref, ref_id)


@router.post("/refs/{ref_id}/discard")
def discard(ref_id: int):
    """버리기(목록에서 숨김, R2 파일은 보존)."""
    return _call(cs.discard_ref, ref_id)


# ── 생성(A0-3) ───────────────────────────────────────────────────────────
@router.post("/create")
def new_character(req: NewCharacterReq, bg: BackgroundTasks):
    """이름 + 자유 설명 → AI 가 bible 작성 → 캐릭터 등록 → 얼굴 후보 4장 생성 시작."""
    char = _call(gen.create_character, req.name, req.description, req.channel_id)
    job = _call(gen.prepare_job, char["id"], [{"role": gen.FACE_ROLE}])
    bg.add_task(gen.run_job, job["id"])
    return {"character": char, "job": gen.public_job(job)}


@router.post("/characters/{character_id}/generate")
def generate(character_id: str, req: GenerateReq, bg: BackgroundTasks):
    """역할별 후보 생성(얼굴 4장·그 외 2장 기본). 고급 보기에서 고친 프롬프트는 item.prompt."""
    job = _call(gen.prepare_job, character_id, [i.model_dump() for i in req.items], req.count)
    bg.add_task(gen.run_job, job["id"])
    return gen.public_job(job)


@router.get("/jobs/{job_id}")
def job(job_id: str):
    return gen.public_job(_call(gen.get_job, job_id))


@router.get("/characters/{character_id}/plan")
def plan(character_id: str, role: str):
    """그 역할의 기본 프롬프트(고급 보기 — 업로드 이미지처럼 프롬프트가 없는 경우)."""
    char = _call(cs.get_character, character_id)
    p = _call(gen.plan, char, role, _call(cs.confirmed_refs, character_id))
    return {k: p[k] for k in ("kind", "prompt", "aspect")}


@router.post("/characters/{character_id}/presets")
def save_presets(character_id: str, req: PresetsReq):
    """헤어·포즈 프리셋 추가·삭제(목록 통째 저장)."""
    return _call(gen.save_presets, character_id, req.kind, req.items)


@router.post("/characters/{character_id}/suggest-role")
async def suggest_role(character_id: str, file: UploadFile = File(...)):
    """비전 AI 역할 추천(저장 안 함) → {kind, role, confidence, reason}."""
    data = await file.read()
    return _call(gen.suggest_role, character_id, data, file.filename or "")


# ── 채널별 목록 · 쇼츠 가져오기 ──────────────────────────────────────────
@router.get("/overview")
def overview():
    """첫 화면: 채널별 캐릭터(얼굴 썸네일·준비 상태)."""
    return {"channels": _call(imp.overview)}


@router.get("/shorts-cast")
def shorts_cast(channel: str = "workout_music"):
    """쇼츠 캐스트 중 스튜디오로 가져올 수 있는 캐릭터(얼굴 이미지가 있는 역할)."""
    return {"cast": _call(imp.shorts_candidates, channel)}


@router.post("/import-shorts")
def import_shorts(req: ImportShortsReq):
    """쇼츠 캐스트 1명을 스튜디오 캐릭터로 복사(원본 cast/… 무변경)."""
    return _call(imp.import_shorts, req.channel, req.role)


# ── 치수(A2 0-1) ─────────────────────────────────────────────────────────
class MeasurementsReq(BaseModel):
    values: dict


@router.get("/characters/{character_id}/measurements")
def get_measurements(character_id: str):
    """실측 치수(저장 전이면 초안) + 입력 칸 정의."""
    return _call(cm.get, character_id)


@router.post("/characters/{character_id}/measurements")
def save_measurements(character_id: str, req: MeasurementsReq):
    """치수 저장(bible.measurements). 착장 핏 계산의 입력."""
    return _call(cm.save, character_id, req.values)
