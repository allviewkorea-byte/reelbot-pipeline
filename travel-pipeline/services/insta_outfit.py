"""인스타 쇼핑 — 착장 사진 1장 자동 생성 (A1).

대표는 상품 사진 넣기 + 버튼만. 흐름:
  상품 업로드(PNG 통일 → R2 insta/products/upload/{batch}/{n}.png) + 비전 AI 종류 추천
  → 장면 기획(insta_outfit_plan: 규칙 후보 + Claude) → Muse edit(9:16, 참조 ① face ② body ③ hair ④~ 상품)
  → 비전 검수(결과 + 상품 사진, JSON) → 위반이면 사유를 프롬프트에 넣어 최대 2회 재생성
  → 폰카 후처리(ffmpeg: 노이즈·채도↓·비네팅·긴 변 1440 jpg) → R2 insta/outfits/{id}/original.png·processed.jpg
  → ig_outfits 행(docs/ig_outfits.sql).
생성은 수십 초라 백그라운드 잡(인메모리, 재시작 시 진행 표시만 소실 — 행은 'generating' 으로 남음) + 폴링.
같은 요청(같은 상품·옵션)이 돌고 있으면 새로 만들지 않고 그 잡을 돌려준다.
스튜디오 테이블은 읽기만(confirmed_refs). 음악·백곰·쇼츠 코드는 import 만.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import random
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

import httpx

from adapters import r2_storage
from adapters.base import ImageGenerationRequest
from adapters.factory import get_muse_adapter
from adapters.image.muse_adapter import USD_PER_IMAGE
from adapters.video.wavespeed_ref_video_adapter import RefBlocked
from services import character_measurements as cm
from services import character_studio as cs
from services import character_studio_gen as gen
from services import insta_outfit_plan as P
from services import shorts_cast_upload as up
from services.music_store import _http_err, _supabase_cfg

logger = logging.getLogger(__name__)

_TABLE = "ig_outfits"
MAX_PRODUCTS = 4
MAX_REGEN = 2                 # 검수 위반 시 재생성 최대 횟수(총 시도 = 1 + 2)
HISTORY_N = 14                # 연속 금지 판정에 보는 최근 이력

# 폰카 후처리 강도(상수 — 테스트 화면에서 원본/처리본 비교 후 조정)
POST_LONG_EDGE = 1440
# 2026-10-27: 노이즈·채도↓·비네팅이 사진을 탁하게 해 AI 티를 키움 → 끔(축소·jpg 만). 값 0 이면 그 필터를 안 건다.
POST_NOISE = 0                # ffmpeg noise alls(0~100)
POST_SATURATION = 1.0         # eq saturation
POST_VIGNETTE = ""            # vignette angle — 빈 값이면 안 씀
POST_JPEG_Q = 3               # ffmpeg -q:v (≈ quality 85)

_BATCH_RE = re.compile(r"^[a-z0-9]{6,24}$")


class OutfitError(ValueError):
    """대표에게 그대로 보여줄 수 있는 입력 오류(400)."""


class OutfitNotFound(LookupError):
    """없음(404)."""


class OutfitStoreError(RuntimeError):
    """Supabase·R2·외부 호출 실패(502)."""


# ── Supabase(PostgREST) ──────────────────────────────────────────────────
def _rest(method: str, *, params: dict | None = None, json_body: object = None, prefer: str | None = None) -> list[dict]:
    url, key = _supabase_cfg()
    if not (url and key):
        raise OutfitStoreError("Supabase 미설정 — 착장 이력을 저장할 수 없어요.")
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.request(method, f"{url}/rest/v1/{_TABLE}", headers=headers, params=params, json=json_body)
            r.raise_for_status()
            data = r.json() if r.content else []
    except Exception as e:  # noqa: BLE001
        msg = _http_err(e)
        logger.warning("[insta-outfit] %s 실패: %s", method, msg)
        raise OutfitStoreError(f"저장소 오류: {msg}") from e
    return data if isinstance(data, list) else []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_outfits(character_id: str, limit: int = 12, *, include_hidden: bool = False) -> list[dict]:
    """최근 착장. 내린 착장(hidden_at)은 기본 제외(연속 금지 이력엔 include_hidden=True 로 모두)."""
    cid = cs.check_character_id(character_id)
    rows = _rest("GET", params={"select": "*", "character_id": f"eq.{cid}", "order": "created_at.desc",
                                "limit": str(max(1, min(int(limit), 50)))})
    return rows if include_hidden else [r for r in rows if not r.get("hidden_at")]


def get_outfit(outfit_id: str) -> dict:
    rows = _rest("GET", params={"select": "*", "id": f"eq.{outfit_id}"})
    if not rows:
        raise OutfitNotFound(f"착장이 없어요: {outfit_id}")
    return rows[0]


def _insert(row: dict) -> dict:
    rows = _rest("POST", json_body=[row], prefer="return=representation")
    return rows[0] if rows else row


def _patch(outfit_id: str, fields: dict) -> None:
    _rest("PATCH", params={"id": f"eq.{outfit_id}"}, json_body={**fields, "updated_at": _now()}, prefer="return=minimal")


def public_url(key: str | None) -> str | None:
    return f"{r2_storage._character_public_base().rstrip('/')}/{key}" if key else None


def view(row: dict) -> dict:
    return {**row, "image_url": public_url(row.get("image_key")), "processed_url": public_url(row.get("processed_key"))}


# ── 상품 업로드 + 종류 추천 ──────────────────────────────────────────────
_KIND_SYSTEM = (
    "You label ONE fashion product photo for an outfit generator. Return ONE JSON object only: "
    '{"kind": "top" | "bottoms" | "dress" | "outerwear" | "shoes" | "bag" | "accessory", '
    '"desc": "<short English description: color, material, type, key details>", '
    '"revealing": true if it is a top/dress that shows a lot of skin (crop top, deep neckline, sheer, '
    'strapless, backless) else false, "has_model": true if a real person wears it in the photo}. '
    "Never describe the model's body."
)


def _vision_json(system: str, images: list[Path], ask: str, task: str, max_tokens: int = 400,
                 model: str | None = None) -> dict:
    """Claude 비전(여러 장) → JSON. Claude API 오류면 OpenAI 비전 1회 대체(첫 장만)."""
    from services import music_lyrics
    from services import music_llm_fallback as fb
    from services import music_ops_log
    from services.music_auto_image import review_model

    b64s = [base64.b64encode(p.read_bytes()).decode("ascii") for p in images]
    model = model or review_model()
    try:
        client = music_lyrics._client().with_options(timeout=120.0, max_retries=0)
        content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b}} for b in b64s]
        messages = [{"role": "user", "content": [*content, {"type": "text", "text": ask}]}]
        try:
            msg = client.messages.create(model=model, max_tokens=max_tokens, system=system, messages=messages)
        except Exception as e:  # noqa: BLE001 - 지정 모델 실패면 기본 모델로 1회
            if model == review_model():
                raise
            logger.warning("[insta-outfit] %s 실패 → 기본 모델: %s", model, str(e)[:160])
            model = review_model()
            msg = client.messages.create(model=model, max_tokens=max_tokens, system=system, messages=messages)
        text = "".join(getattr(b, "text", "") for b in (msg.content or []))
        music_ops_log.add_usage_from(msg, model)
    except Exception as e:  # noqa: BLE001
        if not (fb.enabled() and fb.is_anthropic_api_error(e)):
            raise
        text, model = fb.vision(system, b64s[0], ask, max_tokens=max_tokens, task=task, cause=e)
    data = music_lyrics._extract_json(text)
    if not isinstance(data, dict):
        raise ValueError("JSON 아님")
    data["_model"] = model
    return data


def save_product(batch: str, n: int, data: bytes, filename: str) -> dict:
    """상품 사진 1장 → PNG → R2 → {key, url, kind?, desc, revealing, has_model, suggest_error?}."""
    if not _BATCH_RE.match(batch or ""):
        raise OutfitError("잘못된 업로드 묶음 ID 예요.")
    if not 0 <= int(n) < MAX_PRODUCTS:
        raise OutfitError(f"상품 사진은 {MAX_PRODUCTS}장까지예요.")
    ext = (filename.rsplit(".", 1)[-1] if "." in (filename or "") else "").lower()
    if ext not in up.ALLOWED_EXT:
        raise OutfitError("png·jpg·webp 이미지만 올릴 수 있어요.")
    if not data or len(data) > up.MAX_BYTES:
        raise OutfitError("빈 파일이거나 15MB 를 넘어요.")
    if not r2_storage.is_available():
        raise OutfitStoreError("R2 미설정 — 상품 사진을 저장할 수 없어요.")
    key = f"insta/products/upload/{batch}/{int(n)}.png"
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        src = tmp / f"src.{ext}"
        src.write_bytes(data)
        try:
            w, h = up.probe(src)
            png = tmp / "p.png"
            up._ffmpeg(src, png)
        except up.UploadError as e:
            raise OutfitError(str(e)) from e
        try:
            url = r2_storage.upload_image(str(png), key, bucket=r2_storage._character_bucket(),
                                          public_base_url=r2_storage._character_public_base(), content_type="image/png")
        except Exception as e:  # noqa: BLE001
            raise OutfitStoreError(str(e)) from e
        out = {"key": key, "url": url, "w": w, "h": h, "kind": None, "desc": "", "revealing": False, "has_model": False}
        try:
            small = gen._small_jpeg(png, tmp / "s.jpg")
            got = _vision_json(_KIND_SYSTEM, [small], "이 상품을 분류하고 JSON 만 출력해.", "insta_kind", 300)
            kind = str(got.get("kind") or "")
            out.update(kind=kind if kind in P.PRODUCT_KINDS else None, desc=str(got.get("desc") or "")[:160],
                       revealing=bool(got.get("revealing")), has_model=bool(got.get("has_model")))
        except Exception as e:  # noqa: BLE001 - 추천 실패해도 업로드는 성공(대표가 종류 선택)
            logger.warning("[insta-outfit] 상품 종류 추천 실패 %s: %s", key, str(e)[:200])
            out["suggest_error"] = str(e)[:160]
    return out


# ── 검수 ─────────────────────────────────────────────────────────────────
_REVIEW_SYSTEM = (
    "You review an AI-generated everyday outfit photo for a Korean Instagram fashion account. Image 1 is the "
    "generated photo. When labeled, 'face reference' is the model's real face and 'body reference' is her real figure; "
    "the remaining images are the product photos it must reproduce. Fail it if ANY of these:\n"
    "1. indoor_shoes: it is a living room or bedroom and outdoor shoes are visible on her feet.\n"
    "2. face_visible: her EYES are visible. Her eyes must be hidden — by a phone, by the frame cropping just below "
    "the eyes, or by sunglasses. Lips, chin and the lower face may show. SKIP this check when the scene note says "
    "'얼굴 공개' (a face selfie) — then instead fail as face_visible only if the face looks distorted or unnatural.\n"
    "3. season: clothing and background season/weather clearly contradict (heavy coat on a summer street, etc.).\n"
    "4. product_mismatch: a product is noticeably different — color, pattern, or a key detail (buttons, logo "
    "position, length).\n"
    "5. anatomy: wrong number of fingers/arms/legs, twisted limbs, melted hands.\n"
    "6. text: captions, overlaid text, watermarks, or AI-made logos on the clothing. Natural background shop signs "
    "(e.g. Korean street signage) are fine.\n"
    "7. identity: (only if a face reference is given) the visible part of her face — whole face, or lips, chin and "
    "jawline when the eyes are hidden — looks like a clearly different person from the face reference. Hairstyle "
    "differences are fine.\n"
    "8. body: (only if a body reference is given) her figure is noticeably different from the body reference — "
    "clearly slimmer or flatter chest, narrower hips, a smaller or boxier frame, or shorter legs.\n"
    "9. ref_clothes: (only if a body reference is given) she is wearing the plain grey ribbed top or grey leggings "
    "from the body reference instead of the outfit products.\n"
    'Return ONE JSON object only: {"pass": true|false, "violations": [{"type": "<one of the keys above>", '
    '"detail": "짧은 한국어 설명"}], "fix_en": "<one short English instruction to fix it in the next attempt, '
    'or empty>"}.'
)


def review(result_path: Path, product_paths: list[Path], plan: dict, tmp: Path,
           face_path: Path | None = None, body_path: Path | None = None) -> dict:
    """결과 + (기준 얼굴·체형) + 상품 사진 비전 검수 → {pass, violations, fix_en, model}. 호출 실패면 예외.

    기준 얼굴·체형을 같이 보여 줘야 '다른 사람 얼굴 / 밋밋해진 체형'을 잡는다(대표 2026-10-27).
    """
    small = [gen._small_jpeg(result_path, tmp / "rv0.jpg")]
    labels = []
    for tag, p in (("face reference", face_path), ("body reference", body_path)):
        if p and p.exists():
            small.append(gen._small_jpeg(p, tmp / f"rv_{tag[:4]}.jpg"))
            labels.append(f"{len(small)}번 이미지 = {tag}")
    small += [gen._small_jpeg(p, tmp / f"rv{i + 1}.jpg") for i, p in enumerate(product_paths[:4])]
    face_note = " · 얼굴 공개 컷(눈 보여도 됨)" if plan.get("face") in ("full", "profile", "mirror_full") else ""
    ref_note = f" · {', '.join(labels)}, 나머지는 상품 사진" if labels else ""
    ask = (f"장면: {plan.get('location_ko')} · {plan.get('pose_ko')} · {plan.get('season_ko')}{face_note}{ref_note}. "
           "기준대로 검수하고 JSON 만 출력해.")
    from services.insta_picks import strong_model   # 순환 import 피함
    data = _vision_json(_REVIEW_SYSTEM, small, ask, "insta_review", max_tokens=600, model=strong_model())
    passed = data.get("pass")
    if not isinstance(passed, bool):
        raise ValueError("검수 응답의 pass 가 bool 이 아님")
    vio = [v for v in (data.get("violations") or []) if isinstance(v, dict)][:6]
    return {"pass": passed and not vio, "violations": [{"type": str(v.get("type", ""))[:30], "detail": str(v.get("detail", ""))[:120]} for v in vio],
            "fix_en": str(data.get("fix_en") or "")[:200], "model": data.get("_model")}


# ── 폰카 후처리 ──────────────────────────────────────────────────────────
def postprocess(src: Path, dst: Path) -> Path:
    """원본은 두고 처리본만: 긴 변 1440 축소 → (설정 시 채도·노이즈·비네팅) → jpg. 2026-10-27부터 축소·jpg 만."""
    filters = [f"scale='if(gt(iw,ih),min({POST_LONG_EDGE},iw),-2)':'if(gt(iw,ih),-2,min({POST_LONG_EDGE},ih))'"]
    if POST_SATURATION != 1.0:
        filters.append(f"eq=saturation={POST_SATURATION}")
    if POST_NOISE:
        filters.append(f"noise=alls={POST_NOISE}:allf=t")
    if POST_VIGNETTE:
        filters.append(f"vignette=angle={POST_VIGNETTE}")
    vf = ",".join(filters)
    res = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", vf, "-frames:v", "1",
                          "-q:v", str(POST_JPEG_Q), str(dst)], capture_output=True, text=True, timeout=120)
    if res.returncode != 0 or not dst.exists():
        raise RuntimeError(f"후처리 실패: {res.stderr[-200:]}")
    return dst


# ── 잡 ───────────────────────────────────────────────────────────────────
_JOBS: dict[str, dict] = {}
_ACTIVE: dict[str, str] = {}   # 요청 해시 → job_id (같은 요청 중복 실행 방지)
_LOCK = threading.Lock()


def get_job(job_id: str) -> dict:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            raise OutfitNotFound("작업을 찾을 수 없어요(서버 재시작 — 최근 착장 목록에서 확인해 주세요).")
        return dict(job)


def _job(job_id: str, **kw) -> None:
    with _LOCK:
        _JOBS[job_id].update(kw)


def _request_hash(character_id: str, products: list[dict], options: dict, nonce: str = "") -> str:
    body = json.dumps({"c": character_id, "p": [(p["key"], p["kind"]) for p in products], "o": options, "n": nonce},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(body.encode()).hexdigest()[:16]


def _clean_products(products: list[dict]) -> list[dict]:
    if not 1 <= len(products or []) <= MAX_PRODUCTS:
        raise OutfitError(f"상품 사진을 1~{MAX_PRODUCTS}장 넣어 주세요.")
    out = []
    for p in products:
        key, kind = str(p.get("key") or ""), str(p.get("kind") or "")
        if not key.startswith("insta/products/"):
            raise OutfitError("상품 사진은 이 화면에서 올린 것만 쓸 수 있어요.")
        if kind not in P.PRODUCT_KINDS:
            raise OutfitError("상품마다 종류를 골라 주세요.")
        row = {"key": key, "url": public_url(key), "kind": kind, "desc": str(p.get("desc") or "")[:160],
               "revealing": bool(p.get("revealing"))}
        # A2-3: 출처·링크·쇼핑몰(있을 때만 — 기존 A1 요청과 호환). 링크는 저장·표시만, 서버가 접속하지 않는다.
        if p.get("source") in ("bose", "coupang", "upload"):
            row["source"] = p["source"]
        for k in ("link", "mall", "name"):
            if p.get(k):
                row[k] = str(p[k])[:500]
        if isinstance(p.get("product_row_id"), int):
            row["product_row_id"] = p["product_row_id"]
        out.append(row)
    return out


def _clean_options(options: dict | None) -> dict:
    o = {k: v for k, v in (options or {}).items() if v not in (None, "", "auto")}
    allowed = {"weekday", "cut", "location", "pose", "hair", "eyewear", "season", "styling_en", "face"}
    out = {k: v for k, v in o.items() if k in allowed}
    if out.get("face") not in P.FACE_MODES:
        out.pop("face", None)
    if "styling_en" in out:  # 상품이 아닌 스타일링(스타킹·레그워머 등) — 짧은 영어 문구만
        out["styling_en"] = str(out["styling_en"])[:120]
    return out


CAPTION_NOTE = "AI 가상 착용 · 가상 모델 기준"


def start(character_id: str, products: list[dict], options: dict | None = None, *, remake_of: str | None = None,
          look_id: str | None = None) -> dict:
    """검증 → (같은 요청이 돌고 있으면 그 잡) → 잡 등록. 실행은 run(백그라운드). 반환: 잡."""
    char = cs.get_character(character_id)
    refs = cs.confirmed_refs(char["id"])
    if not (refs.get(gen.FACE_ROLE) and refs.get(gen.BODY_ROLE)):
        raise OutfitError("캐릭터가 '준비 완료'가 아니에요 — 스튜디오에서 얼굴·체형을 확정해 주세요.")
    if not cm.saved(char):  # 핏은 실측 치수로 계산(A2) — 치수 없이는 만들지 않는다
        raise OutfitError("치수를 먼저 입력해 주세요 — 스튜디오 캐릭터 화면의 '치수' 카드에서 저장해 주세요.")
    prods = _clean_products(products)
    opts = _clean_options(options)
    if not get_muse_adapter().is_available():
        raise OutfitStoreError("WAVESPEED_API_KEY 미설정 — 이미지를 생성할 수 없어요.")
    if not r2_storage.is_available():
        raise OutfitStoreError("R2 미설정 — 결과를 저장할 수 없어요.")
    h = _request_hash(char["id"], prods, opts, remake_of or "")
    with _LOCK:
        running = _ACTIVE.get(h)
        if running and _JOBS.get(running, {}).get("state") in ("queued", "running"):
            return dict(_JOBS[running])
    outfit_id = f"of-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(3)}"
    row = {"id": outfit_id, "character_id": char["id"], "product_images": prods, "status": "generating",
           "caption_note": CAPTION_NOTE}
    if look_id:
        row["look_id"] = look_id
    _insert(row)
    job_id = f"oj_{secrets.token_hex(5)}"
    with _LOCK:
        _JOBS[job_id] = {"id": job_id, "outfit_id": outfit_id, "state": "queued", "step": "대기",
                         "attempts": 0, "cost_usd": 0.0, "error": None, "hash": h,
                         "_args": {"character_id": char["id"], "products": prods, "options": opts}}
        _ACTIVE[h] = job_id
    return public_job(get_job(job_id))


def public_job(job: dict) -> dict:
    return {k: v for k, v in job.items() if not k.startswith("_")}


def _download(url: str, dest: Path) -> Path:
    with httpx.Client(timeout=60.0, follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
    dest.write_bytes(r.content)
    return dest


def run(job_id: str, *, rng: random.Random | None = None) -> None:
    """BackgroundTasks 진입점: 기획 → 생성 → 검수(최대 2회 재생성) → 후처리 → 저장."""
    with _LOCK:
        args = dict(_JOBS[job_id]["_args"])
        outfit_id = _JOBS[job_id]["outfit_id"]
    cid, prods, opts = args["character_id"], args["products"], args["options"]
    tmp = Path(tempfile.mkdtemp(prefix="insta_outfit_"))
    cost = 0.0
    attempts = 0
    try:
        _job(job_id, state="running", step="장면 기획")
        refs = cs.confirmed_refs(cid)
        hair_roles = sorted(r for r in refs if cs.role_category(r) == "hair")
        history = [h for h in list_outfits(cid, HISTORY_N, include_hidden=True) if h["id"] != outfit_id and h.get("plan")]
        plan = P.plan_scene(character_id=cid, products=prods, hair_roles=hair_roles, history=history,
                            options=opts, rng=rng)
        _patch(outfit_id, {"plan": plan})

        product_paths = [_download(p["url"], tmp / f"prod{i}.png") for i, p in enumerate(prods)]
        face_path = body_path = None
        try:  # 검수용 기준 얼굴·체형(실패해도 생성은 계속)
            face_path = _download(refs[gen.FACE_ROLE]["url"], tmp / "ref_face.png")
            body_path = _download(refs[gen.BODY_ROLE]["url"], tmp / "ref_body.png")
        except Exception as e:  # noqa: BLE001
            logger.warning("[insta-outfit] 기준 사진 받기 실패(검수는 상품만): %s", str(e)[:160])
        try:
            measurements = cm.get(cid).get("values") or None
        except Exception:  # noqa: BLE001
            measurements = None
        hair_url = refs[plan["hair_role"]]["url"] if plan.get("hair_role") in refs else None
        adapter = get_muse_adapter()
        fix, last_review, reviews = None, None, []
        out = tmp / "result.png"
        for attempt in range(1 + MAX_REGEN):
            prompt, ref_urls = P.build(plan, face_url=refs[gen.FACE_ROLE]["url"], body_url=refs[gen.BODY_ROLE]["url"],
                                       hair_url=hair_url, products=prods, fix_hint=fix, measurements=measurements)
            prompt = gen.strip_unsafe(prompt)
            _job(job_id, step=f"생성 {attempt + 1}회차")
            try:
                res = asyncio.run(adapter.generate(ImageGenerationRequest(prompt=prompt, reference_images=ref_urls,
                                                                          aspect_ratio="9:16", output_path=str(out))))
            except RefBlocked:  # 안전 필터 → 체형·피부·분위기 문장을 뺀 단순 프롬프트 + 안전 문구로 1회 재시도
                logger.warning("[insta-outfit] %s 안전 필터 → 단순 프롬프트로 재시도", outfit_id)
                prompt, ref_urls = P.build(plan, face_url=refs[gen.FACE_ROLE]["url"], body_url=refs[gen.BODY_ROLE]["url"],
                                           hair_url=hair_url, products=prods, fix_hint=None, safe=True)
                prompt = gen.sanitize(gen.strip_unsafe(prompt))
                res = asyncio.run(adapter.generate(ImageGenerationRequest(prompt=prompt, reference_images=ref_urls,
                                                                          aspect_ratio="9:16", output_path=str(out))))
            attempts = attempt + 1
            cost += res.cost_usd
            _job(job_id, attempts=attempts, cost_usd=round(cost, 4), step=f"검수 {attempts}회차")
            _patch(outfit_id, {"prompt": prompt, "refs": ref_urls, "attempts": attempts, "cost_usd": round(cost, 4)})
            try:
                last_review = review(out, product_paths, plan, tmp, face_path, body_path)
            except Exception as e:  # noqa: BLE001 - 검수 호출 실패는 통과 처리(이미지는 보여 주고 표시)
                logger.warning("[insta-outfit] 검수 실패 %s: %s", outfit_id, str(e)[:200])
                last_review = {"pass": True, "skipped": f"검수 호출 실패 — {str(e)[:120]}", "violations": []}
            reviews.append({"attempt": attempts, **{k: last_review.get(k) for k in ("pass", "violations", "skipped")}})
            if last_review["pass"]:
                break
            details = "; ".join(v["detail"] for v in last_review["violations"])
            fix = last_review.get("fix_en") or details or None

        _job(job_id, step="후처리·저장")
        processed = postprocess(out, tmp / "processed.jpg")
        base = f"insta/outfits/{outfit_id}"
        bucket, pub = r2_storage._character_bucket(), r2_storage._character_public_base()
        r2_storage.upload_image(str(out), f"{base}/original.png", bucket=bucket, public_base_url=pub, content_type="image/png")
        r2_storage.upload_image(str(processed), f"{base}/processed.jpg", bucket=bucket, public_base_url=pub,
                                content_type="image/jpeg")
        status = "ok" if last_review and last_review["pass"] else "review_failed"
        _patch(outfit_id, {"image_key": f"{base}/original.png", "processed_key": f"{base}/processed.jpg",
                           "review": {**(last_review or {}), "history": reviews}, "status": status,
                           "attempts": attempts, "cost_usd": round(cost, 4)})
        _job(job_id, state="done", step="완료", status=status)
    except Exception as e:  # noqa: BLE001
        msg = str(e)[:300]
        logger.warning("[insta-outfit] %s 실패: %s", outfit_id, msg)
        _job(job_id, state="failed", step="실패", error=msg, status="failed")
        try:
            _patch(outfit_id, {"status": "failed", "error": msg, "attempts": attempts, "cost_usd": round(cost, 4)})
        except Exception:  # noqa: BLE001
            pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        with _LOCK:
            h = _JOBS[job_id].get("hash")
            if _ACTIVE.get(h) == job_id:
                _ACTIVE.pop(h, None)


def remake(outfit_id: str) -> dict:
    """같은 상품, 새 기획(옵션 없이 자동)."""
    row = get_outfit(outfit_id)
    return start(row["character_id"], row.get("product_images") or [], {}, remake_of=f"{outfit_id}:{secrets.token_hex(2)}")


def estimate() -> dict:
    """화면 표시용 예상 비용(이미지만, AI 기획·검수 토큰 별도)."""
    return {"per_image": USD_PER_IMAGE, "min": USD_PER_IMAGE, "max": round(USD_PER_IMAGE * (1 + MAX_REGEN), 3)}
