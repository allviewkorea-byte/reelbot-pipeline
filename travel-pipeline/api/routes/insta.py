"""인스타 쇼핑 API — 착장 사진 1장 생성 (A1, 테스트 화면 /insta/outfit). 상품 URL 추출(A2)·릴스(A3)는 별도."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from services import character_studio as cs
from services import insta_outfit as io
from services import insta_outfit_plan as P
from services import insta_refs as refs

router = APIRouter()


class OutfitReq(BaseModel):
    character_id: str = "chaei"
    products: list[dict]
    options: dict | None = None


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (io.OutfitError, cs.StudioError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (io.OutfitNotFound, cs.StudioNotFound) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except (io.OutfitStoreError, cs.StudioStoreError) as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/outfit-options")
def outfit_options():
    """선택 입력(접힘)용 풀 + 예상 비용."""
    return {
        "weekdays": [{"value": k, "label": f"{v['ko']} · {v['life']}"} for k, v in P.WEEKDAYS.items()],
        "cuts": sorted({p["cut"] for p in P.POSES.values()}),
        "locations": [{"value": k, "label": v["ko"]} for k, v in P.LOCATIONS.items()],
        "poses": [{"value": k, "label": v["ko"], "cut": v["cut"]} for k, v in P.POSES.items()],
        "eyewear": [{"value": "none", "label": "안 씀"}] + [{"value": k, "label": v["ko"]} for k, v in P.EYEWEAR.items()],
        "kinds": [{"value": k, "label": v[0]} for k, v in P.PRODUCT_KINDS.items()],
        "estimate": io.estimate(),
    }


@router.post("/products")
async def upload_product(file: UploadFile = File(...), batch: str = Form(...), n: int = Form(0)):
    """상품 사진 1장 업로드(PNG 통일·R2) + 비전 AI 종류 추천."""
    data = await file.read()
    return _call(io.save_product, batch, n, data, file.filename or "")


@router.post("/outfits")
def create_outfit(req: OutfitReq, bg: BackgroundTasks):
    """착장 만들기 — 같은 요청이 돌고 있으면 그 작업을 돌려준다."""
    job = _call(io.start, req.character_id, req.products, req.options)
    if job["state"] == "queued":
        bg.add_task(io.run, job["id"])
    return job


@router.post("/outfits/{outfit_id}/remake")
def remake(outfit_id: str, bg: BackgroundTasks):
    """같은 상품, 새 기획으로 다시 만들기."""
    job = _call(io.remake, outfit_id)
    if job["state"] == "queued":
        bg.add_task(io.run, job["id"])
    return job


@router.get("/outfits")
def outfits(character_id: str = "chaei", limit: int = 12):
    return {"outfits": [io.view(r) for r in _call(io.list_outfits, character_id, limit)]}


@router.get("/outfits/{outfit_id}")
def outfit(outfit_id: str):
    return io.view(_call(io.get_outfit, outfit_id))


@router.get("/outfit-jobs/{job_id}")
def outfit_job(job_id: str):
    return io.public_job(_call(io.get_job, job_id))


# ── 레퍼런스(A2-1) ───────────────────────────────────────────────────────
def _run_refs(force: bool) -> None:
    try:
        refs.run(force=force)
    except Exception:  # noqa: BLE001 - 결과는 refs.status()["last"] 에 남는다
        pass


@router.post("/refs/collect")
def collect_refs(bg: BackgroundTasks, force: bool = False):
    """유튜브 레퍼런스 수집(오늘 이미 했으면 건너뜀, force=true 면 다시) → 새 레퍼런스 분석. 백그라운드."""
    if not refs.try_begin():
        return {"started": False, "status": refs.status()}
    bg.add_task(_run_refs, force)
    return {"started": True, "status": refs.status()}


@router.get("/refs")
def list_refs(limit: int = 20):
    try:
        items = refs.list_refs(limit)
    except refs.RefsError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"refs": items, "status": refs.status()}


@router.get("/usage")
def api_usage():
    """외부 API 오늘 사용량(유튜브 유닛 상한 포함)."""
    try:
        return {"youtube": refs.usage("youtube"), "has_youtube_key": bool(refs.yt_key())}
    except refs.RefsError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
