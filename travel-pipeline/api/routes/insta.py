"""인스타 쇼핑 API — 착장 생성(A1) · 레퍼런스 수집·분석(A2-1) · 쿠팡·네이버 상품 픽(A2-2). 테스트 화면 /insta/outfit."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from adapters.shopping import ShoppingError
from services import character_studio as cs
from services import insta_outfit as io
from services import insta_outfit_plan as P
from services import insta_picks as picks
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


# ── 상품 픽(A2-2) ────────────────────────────────────────────────────────
class PickReq(BaseModel):
    video_id: str | None = None
    look_index: int = 0


class SwapReq(BaseModel):
    item_index: int
    product_id: int


def _pcall(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ShoppingError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except refs.RefsError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/shopping/status")
def shopping_status():
    """쿠팡·네이버 연결 여부(키 유무) + 오늘 호출 수."""
    out = {"connected": picks.connections()}
    try:
        out["usage"] = {ch: refs.usage(ch) for ch in ("coupang", "naver")}
    except refs.RefsError:
        out["usage"] = None
    return out


@router.post("/looks/pick")
def pick_look(req: PickReq, bg: BackgroundTasks):
    """레퍼런스 룩 1벌의 상품 고르기(백그라운드). video_id 없으면 분석된 레퍼런스 중 조회수 1위."""
    job = _pcall(picks.start, req.video_id, req.look_index)
    if job["state"] == "queued":
        bg.add_task(picks.run, job["id"])
    return job


@router.get("/looks/jobs/{job_id}")
def pick_job(job_id: str):
    return _pcall(picks.get_job, job_id)


@router.get("/looks")
def looks(limit: int = 10):
    return {"looks": _pcall(picks.list_looks, limit)}


@router.post("/looks/{look_id}/swap")
def swap(look_id: str, req: SwapReq):
    """아이템 1등을 예비 후보로 교체."""
    return _pcall(picks.swap, look_id, req.item_index, req.product_id)
