"""캐릭터 스튜디오(채널 공통) API — 캐릭터·역할별 기준 이미지 (A0-1). 쇼츠 /shorts/cast* 와 분리."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from services import character_studio as cs

router = APIRouter()


class CharacterReq(BaseModel):
    id: str
    name: str
    channel_id: str | None = None
    bible: dict | None = None


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
    """캐릭터 + 역할별 확정·후보 + 필수 역할(01_face·02_body) 충족 여부."""
    return _call(cs.character_view, character_id)


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
