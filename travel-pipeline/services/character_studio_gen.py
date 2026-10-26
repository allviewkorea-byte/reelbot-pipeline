"""캐릭터 스튜디오 — 이미지 생성(Muse) + AI bible 작성 + AI 역할 추천 (A0-3).

대표 원칙: 프롬프트를 붙여넣거나 파일명을 맞추는 일이 없어야 한다(클릭과 선택만).
- 새 캐릭터: 이름 + 자유 설명 → Claude 가 bible(JSON) 작성 → 얼굴 프롬프트(검증된 템플릿) →
  text-to-image 후보 4장. 대표가 1장 확정 = 01_face.
- 체형(02_body)·헤어(hair_NN_key)·포즈(pose_key): 확정 얼굴(포즈는 + 확정 체형)을 참조로 edit 후보 2장.
- 프롬프트 템플릿은 2026-10 실측으로 안전 필터를 통과한 문구 그대로. 체형은 02_body 이미지가
  담당하고 글로는 'same body shape as the reference' 만 쓴다.
- 안전 필터 거부(RefBlocked) → 금지 표현을 안전 표현으로 바꿔 1회 재시도 → 그래도 실패면 사유를 잡에 남긴다.
- 생성은 수십 초라 백그라운드 잡(인메모리 _JOBS, 재시작 시 소실 — 후보는 이미 DB 에 저장됨)으로 돌리고
  화면이 폴링한다. 결과는 studio_character_refs 에 source='generated'·prompt·parent_ref_id·batch_id 로 남는다.
- 프리셋(헤어·포즈) 추가·삭제는 studio_characters.bible['studio_presets'] 에 저장(새 컬럼 없음).
"""

from __future__ import annotations

import asyncio
import base64
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

from adapters import r2_storage
from adapters.base import ImageGenerationRequest
from adapters.factory import get_muse_adapter
from adapters.image.muse_adapter import USD_PER_IMAGE
from adapters.video.wavespeed_ref_video_adapter import RefBlocked
from services import character_studio as cs

logger = logging.getLogger(__name__)

FACE_COUNT = 4
DEFAULT_COUNT = 2
MAX_COUNT = 6
MAX_ITEMS = 16          # 한 번에 생성할 역할 수 상한(헤어 11종 + 여유)
_CONCURRENCY = 4

FACE_ROLE = "01_face"
BODY_ROLE = "02_body"

# ── 프리셋(실측 검증 문구 — 그대로) ─────────────────────────────────────
HAIR_PRESETS: list[dict] = [
    {"key": "straight", "line": "long straight hair worn down naturally with soft layers"},
    {"key": "wave", "line": "long hair in loose, glossy big waves"},
    {"key": "halfup", "line": "long hair in a neat half-up half-down style"},
    {"key": "lowbun", "line": "long hair in a low messy bun with a few loose face-framing strands"},
    {"key": "ponytail", "line": "long hair in a sleek high ponytail"},
    {"key": "clawclip", "line": "long hair twisted up with a tortoiseshell claw clip, loose strands at the front"},
    {"key": "cap", "line": "long straight hair down, wearing a plain black baseball cap"},
    {"key": "beanie", "line": "long straight hair down, wearing a grey knit beanie"},
    {"key": "braid", "line": "long hair in one loose side braid resting over the shoulder"},
    {"key": "beret", "line": "long straight hair down, wearing a black wool beret tilted slightly to one side"},
    {"key": "headband", "line": "long straight hair down with a wide brown velvet headband"},
]

# 포즈: 얼굴 가림(어깨 아래 프레이밍 / 폰으로 가린 미러셀카). 신발이 보이면 실내(거실·방) 금지 —
# 현관 타일·엘리베이터·야외만. 신발 없는 실내 컷은 양말 + 방·거실.
POSE_PRESETS: list[dict] = [
    {"key": "stand", "label": "서기(현관 미러셀카)",
     "line": "standing on the entryway tile floor by the shoe cabinet, taking a mirror selfie with the phone "
             "held up covering her face, full body visible in the mirror, casual everyday outfit with white sneakers"},
    {"key": "sit", "label": "앉기(거실, 신발 없음)",
     "line": "sitting relaxed on a sofa in a bright living room, wearing cozy loungewear and socks, no shoes, "
             "framed from the shoulders down so her face is not visible"},
    {"key": "walk", "label": "걷기(거리)",
     "line": "walking across a city crosswalk on a clear day, casual outfit with sneakers, "
             "framed from the shoulders down so her face is not visible"},
    {"key": "lean", "label": "기대기(엘리베이터 거울)",
     "line": "leaning against the wall inside an apartment elevator, taking a mirror selfie with the phone "
             "held up covering her face, full body visible in the mirror, smart casual outfit with loafers"},
    {"key": "detail", "label": "디테일(손·소매)",
     "line": "close-up of her hands holding a takeaway coffee cup, showing the sleeve and fabric texture of her knit "
             "cardigan, framed from the shoulders down so her face is not visible"},
]

_KEY_RE = re.compile(r"^[a-z][a-z0-9]{1,23}$")

# 안전 필터에 걸린 표현 → 안전 표현(실측). 재시도 때만 적용한다.
_UNSAFE: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bcropped at the neck\b", re.I), "framed from the shoulders down so her face is not visible"),
    (re.compile(r"\b(fuller|full|large|big|ample|small)\s+(bust|breasts?|chest)\b", re.I), ""),
    (re.compile(r"\b(bust|breasts?|cleavage|chest|butt|buttocks|hips|thighs|curves?|curvy|voluptuous)\b", re.I), ""),
    (re.compile(r"\b(sexy|seductive|sensual|revealing|lingerie|bikini|underwear)\b", re.I), ""),
]
_SAFE_SUFFIX = " Modest, fully clothed, non-revealing, fashion catalog style."


def strip_unsafe(text: str) -> str:
    """금지 표현 제거·치환(공백·쉼표 정리)."""
    out = text
    for pat, rep in _UNSAFE:
        out = pat.sub(rep, out)
    return re.sub(r"\s+,", ",", re.sub(r"[ \t]{2,}", " ", out)).strip()


def sanitize(prompt: str) -> str:
    """재시도용: 금지 표현 제거. 바뀐 게 없으면 안전 문구를 덧붙여 항상 다른 프롬프트로 보낸다."""
    out = strip_unsafe(prompt)
    return out + _SAFE_SUFFIX if out == prompt.strip() else out


# ── 프리셋 저장(bible.studio_presets) ────────────────────────────────────
def presets(char: dict) -> dict:
    sp = (char.get("bible") or {}).get("studio_presets") or {}
    hair = sp.get("hair") if isinstance(sp.get("hair"), list) else HAIR_PRESETS
    pose = sp.get("pose") if isinstance(sp.get("pose"), list) else POSE_PRESETS
    hair = [{**h, "role": f"hair_{i + 1:02d}_{h['key']}"} for i, h in enumerate(hair)]
    pose = [{**p, "role": f"pose_{p['key']}"} for p in pose]
    return {"hair": hair, "pose": pose}


def save_presets(character_id: str, kind: str, items: list[dict]) -> dict:
    """헤어·포즈 프리셋 목록 저장(추가·삭제·순서). 헤어 번호(hair_NN)는 목록 순서로 매겨진다."""
    if kind not in ("hair", "pose"):
        raise cs.StudioError("프리셋 종류는 hair 또는 pose 예요.")
    clean: list[dict] = []
    seen: set[str] = set()
    for it in items or []:
        key = str(it.get("key") or "").strip().lower()
        line = str(it.get("line") or "").strip()
        if not _KEY_RE.match(key):
            raise cs.StudioError(f"프리셋 키는 영문 소문자로 시작하는 2~24자(소문자·숫자)여야 해요: {key or '(빈 값)'}")
        if key in seen:
            raise cs.StudioError(f"같은 키가 두 번 있어요: {key}")
        if not (5 <= len(line) <= 400):
            raise cs.StudioError(f"{key}: 설명(영문 한 줄)을 5~400자로 적어 주세요.")
        seen.add(key)
        row = {"key": key, "line": line}
        if it.get("label"):
            row["label"] = str(it["label"])[:40]
        clean.append(row)
    if len(clean) > 30:
        raise cs.StudioError("프리셋은 30개까지예요.")
    char = cs.get_character(character_id)
    bible = dict(char.get("bible") or {})
    sp = dict(bible.get("studio_presets") or {})
    sp[kind] = clean
    bible["studio_presets"] = sp
    cs.upsert_character(char["id"], char["name"], bible=bible)
    return presets({**char, "bible": bible})


# ── 프롬프트 ─────────────────────────────────────────────────────────────
def _subject(bible: dict) -> str:
    s = str(bible.get("subject_en") or "woman").strip().lower()
    return "man" if s in ("man", "male", "boy") else "woman"


def _pron(bible: dict) -> str:
    return "his" if _subject(bible) == "man" else "her"


def face_prompt(bible: dict) -> str:
    summary = str(bible.get("summary_en") or f"{bible.get('age') or 24}-year-old Korean {_subject(bible)}").strip().rstrip(".")
    default_hair = "short black hair" if _subject(bible) == "man" else "long straight black hair"
    hair = str(bible.get("hair_en") or default_hair).strip().rstrip(".")
    return (f"Original fictional {summary}, not resembling any real person or celebrity. {hair[:1].upper()}{hair[1:]}, "
            "natural makeup, calm confident expression. Youthful and fresh-faced, looking her real age. Upper body "
            "portrait, front-facing, plain light gray background, soft natural window light, photorealistic, shot on "
            "50mm lens.")


# 얼굴 후보 다양화 — 후보마다 얼굴형·눈매·분위기를 겹치지 않게 한 줄씩(같은 얼굴 4장 방지).
FACE_SHAPES = ["an oval face", "a soft round face", "a slim, narrow face with a delicate jawline"]
FACE_EYES = [
    "double eyelids with slightly upturned outer eye corners",
    "monolid eyes without a double eyelid crease, softly downturned outer corners",
    "subtle inner double eyelids with a straight, calm eye line",
    "clear double eyelids with gently drooping, friendly outer corners",
]
FACE_VIBES = ["an innocent, pure look", "a chic, cool look", "a bright, cheerful look", "a calm, gentle look"]


def face_variants(n: int, rng: random.Random | None = None) -> list[str]:
    """n 개 후보용 한 줄씩. 같은 잡 안에서 얼굴형(3)·눈매(4)·분위기(4)가 최대한 겹치지 않게 섞는다."""
    rng = rng or random.Random()
    shapes, eyes, vibes = (rng.sample(x, len(x)) for x in (FACE_SHAPES, FACE_EYES, FACE_VIBES))
    return [f"Distinct features for this candidate: {shapes[i % len(shapes)]}, {eyes[i % len(eyes)]}, "
            f"{vibes[i % len(vibes)]}." for i in range(n)]


def body_prompt(bible: dict) -> str:
    h = bible.get("height_cm")
    tall = f"{int(h)}cm tall " if isinstance(h, (int, float)) and 140 <= h <= 210 else ""
    who = _subject(bible)
    return (f"Same {who} as the reference image, keep the exact same face, moles and hair. Full body front view and side "
            f"profile view side by side, standing naturally, {tall}model proportions. Wearing a light grey fitted ribbed "
            "tank top and matching light grey high-waist leggings, white sneakers. Plain light grey studio background, "
            "soft even lighting, photorealistic, body reference sheet.")


def hair_prompt(bible: dict, line: str) -> str:
    return (f"Same {_subject(bible)} as the reference image — keep the exact same face, moles and black hair color. "
            f"Change only the hairstyle: {line.strip().rstrip('.')}. Upper body and head, front view, wearing a plain "
            "white t-shirt, plain light grey studio background, soft even lighting, photorealistic.")


def pose_prompt(bible: dict, line: str) -> str:
    return (f"Same {_subject(bible)} as the reference images, same body shape as the reference, same hair. "
            f"{line.strip().rstrip('.')[:1].upper()}{line.strip().rstrip('.')[1:]}. "
            f"Natural candid photo, {_pron(bible)} face is not visible, photorealistic, soft natural light.")


def plan(char: dict, role: str, refs: dict[str, dict], prompt: str | None = None,
         ref_roles: list[str] | None = None) -> dict:
    """역할 → {kind, prompt, references[url], parent_ref_id, aspect}. 기준 이미지가 없으면 StudioError.

    전문가 모드: prompt 와 ref_roles(참조로 넣을 확정 역할 목록, 빈 목록이면 참조 없이 t2i)를 함께 주면
    프리셋·전제 조건 없이 그대로 쓴다(안전 필터 자동 재시도만 적용)."""
    role = cs.check_role(role)
    if prompt and ref_roles is not None:
        missing = [r for r in ref_roles if r not in refs]
        if missing:
            raise cs.StudioError(f"확정되지 않은 참조 역할이에요: {', '.join(missing)}")
        urls = [refs[r]["url"] for r in ref_roles][:10]
        face = refs.get(FACE_ROLE) if FACE_ROLE in ref_roles else None
        kind = "pose" if cs.role_category(role) == "pose" else "custom"
        return {"kind": kind, "prompt": prompt, "references": urls,
                "parent_ref_id": face["id"] if face else None, "aspect": "9:16" if kind == "pose" else "3:4"}
    bible = char.get("bible") or {}
    pr = presets(char)
    face, body = refs.get(FACE_ROLE), refs.get(BODY_ROLE)

    def need_face() -> dict:
        if not face:
            raise cs.StudioError("얼굴(01_face)을 먼저 확정해 주세요.")
        return face

    if role == FACE_ROLE:
        return {"kind": "face", "prompt": prompt or face_prompt(bible), "references": [], "parent_ref_id": None, "aspect": "3:4"}
    if role == BODY_ROLE:
        f = need_face()
        return {"kind": "body", "prompt": prompt or body_prompt(bible), "references": [f["url"]],
                "parent_ref_id": f["id"], "aspect": "3:4"}
    cat = cs.role_category(role)
    if cat == "hair":
        f = need_face()
        hit = next((h for h in pr["hair"] if h["role"] == role), None)
        if not (prompt or hit):
            raise cs.StudioError(f"헤어 프리셋에 없는 역할이에요: {role}")
        return {"kind": "hair", "prompt": prompt or hair_prompt(bible, hit["line"]), "references": [f["url"]],
                "parent_ref_id": f["id"], "aspect": "3:4"}
    if cat == "pose":
        f = need_face()
        if not body:
            raise cs.StudioError("포즈는 체형(02_body)을 먼저 확정해 주세요.")
        hit = next((p for p in pr["pose"] if p["role"] == role), None)
        if not (prompt or hit):
            raise cs.StudioError(f"포즈 프리셋에 없는 역할이에요: {role}")
        return {"kind": "pose", "prompt": prompt or pose_prompt(bible, hit["line"]),
                "references": [f["url"], body["url"]], "parent_ref_id": f["id"], "aspect": "9:16"}
    if prompt and face:
        return {"kind": "other", "prompt": prompt, "references": [face["url"]], "parent_ref_id": face["id"], "aspect": "3:4"}
    raise cs.StudioError(f"자동 생성할 수 없는 역할이에요: {role} (고급 보기에서 프롬프트를 적어 주세요)")


# ── 잡(인메모리) ─────────────────────────────────────────────────────────
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


def get_job(job_id: str) -> dict:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            raise cs.StudioNotFound("생성 작업을 찾을 수 없어요(서버 재시작으로 사라졌을 수 있어요 — 후보는 저장돼 있어요).")
        return {**job, "errors": list(job["errors"])}


def _update(job_id: str, **kw) -> None:
    with _LOCK:
        job = _JOBS[job_id]
        for k, v in kw.items():
            if k == "error":
                job["errors"].append(v)
            elif k in ("inc_done", "inc_failed", "add_cost"):
                field = {"inc_done": "done", "inc_failed": "failed", "add_cost": "cost_usd"}[k]
                job[field] = round(job[field] + v, 4)
            else:
                job[k] = v


def prepare_job(character_id: str, items: list[dict], count: int | None = None) -> dict:
    """요청 검증 + 계획(프롬프트·참조) 확정 → 잡 등록. 실행은 run_job(백그라운드)."""
    char = cs.get_character(character_id)
    if not items:
        raise cs.StudioError("생성할 역할을 골라 주세요.")
    if len(items) > MAX_ITEMS:
        raise cs.StudioError(f"한 번에 {MAX_ITEMS}개 역할까지 만들 수 있어요.")
    refs = cs.confirmed_refs(char["id"])
    plans = []
    for it in items:
        role = str(it.get("role") or "")
        prompt = (str(it.get("prompt") or "").strip() or None)
        if prompt and len(prompt) > 2000:
            raise cs.StudioError("프롬프트가 너무 길어요(2000자 이하).")
        ref_roles = it.get("refs")
        if ref_roles is not None and not (isinstance(ref_roles, list) and all(isinstance(r, str) for r in ref_roles)):
            raise cs.StudioError("참조 역할 목록 형식이 올바르지 않아요.")
        p = plan(char, role, refs, prompt, ref_roles)
        n = int(it.get("count") or count or (FACE_COUNT if p["kind"] == "face" else DEFAULT_COUNT))
        if not 1 <= n <= MAX_COUNT:
            raise cs.StudioError(f"후보 장수는 1~{MAX_COUNT}장이에요.")
        # 기본 얼굴 후보는 장마다 얼굴형·눈매·분위기를 다르게(고친 프롬프트는 그대로)
        variants = face_variants(n) if p["kind"] == "face" and not prompt else None
        plans.append({**p, "role": cs.check_role(role), "count": n, "variants": variants})
    if not get_muse_adapter().is_available():
        raise cs.StudioStoreError("WAVESPEED_API_KEY 미설정 — 이미지를 생성할 수 없어요.")
    if not r2_storage.is_available():
        raise cs.StudioStoreError("R2 미설정 — 생성 이미지를 저장할 수 없어요.")
    job_id = f"sg_{datetime.now(timezone.utc):%Y%m%d%H%M%S}_{secrets.token_hex(3)}"
    total = sum(p["count"] for p in plans)
    with _LOCK:
        _JOBS[job_id] = {
            "id": job_id, "character_id": char["id"], "state": "queued",
            "roles": [p["role"] for p in plans], "total": total, "done": 0, "failed": 0,
            "errors": [], "cost_usd": 0.0, "est_usd": round(total * USD_PER_IMAGE, 3),
            "created_at": datetime.now(timezone.utc).isoformat(), "plans": plans,
        }
    return get_job(job_id)


async def _one(adapter, job_id: str, character_id: str, p: dict, sem: asyncio.Semaphore, tmp: Path, idx: int) -> None:
    async with sem:
        prompt = p["prompt"]
        if p.get("variants"):
            prompt = f"{prompt} {p['variants'][idx % len(p['variants'])]}"
        out = tmp / f"{p['role']}_{idx}.png"
        retried = False
        while True:
            try:
                res = await adapter.generate(ImageGenerationRequest(
                    prompt=prompt, reference_images=p["references"] or None,
                    aspect_ratio=p["aspect"], output_path=str(out)))
                break
            except RefBlocked as e:
                if retried:
                    _update(job_id, inc_failed=1, error=f"{p['role']}: 안전 필터에 걸렸어요(표현 바꿔 재시도도 실패) — {str(e)[:160]}")
                    return
                retried = True
                prompt = sanitize(prompt)
                logger.warning("[studio-gen] %s 안전 필터 → 표현 바꿔 1회 재시도", p["role"])
            except Exception as e:  # noqa: BLE001
                _update(job_id, inc_failed=1, error=f"{p['role']}: 생성 실패 — {str(e)[:200]}")
                return
        _update(job_id, add_cost=res.cost_usd)
        try:
            key = cs._r2_key(character_id, p["role"])
            url = await asyncio.to_thread(
                r2_storage.upload_image, res.image_path, key,
                bucket=r2_storage._character_bucket(),
                public_base_url=r2_storage._character_public_base(),
                content_type="image/png")
            await asyncio.to_thread(
                cs.insert_ref, character_id, p["role"], r2_key=key, url=url, source="generated",
                prompt=prompt, parent_ref_id=p["parent_ref_id"], batch_id=job_id)
            _update(job_id, inc_done=1)
        except Exception as e:  # noqa: BLE001
            _update(job_id, inc_failed=1, error=f"{p['role']}: 저장 실패 — {str(e)[:200]}")


def run_job(job_id: str) -> None:
    """BackgroundTasks 진입점. 모든 후보를 병렬(_CONCURRENCY)로 생성·저장."""
    with _LOCK:
        job = _JOBS[job_id]
        plans, character_id = job["plans"], job["character_id"]
    _update(job_id, state="running")
    tmp = Path(tempfile.mkdtemp(prefix="studio_gen_"))
    try:
        adapter = get_muse_adapter()

        async def main() -> None:
            sem = asyncio.Semaphore(_CONCURRENCY)
            await asyncio.gather(*[
                _one(adapter, job_id, character_id, p, sem, tmp, i)
                for p in plans for i in range(p["count"])
            ])
        asyncio.run(main())
        job = get_job(job_id)
        _update(job_id, state="done" if job["done"] else "failed")
    except Exception as e:  # noqa: BLE001
        _update(job_id, state="failed", error=f"작업 실패 — {str(e)[:200]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        logger.info("[studio-gen] %s 끝: %s", job_id, {k: v for k, v in get_job(job_id).items() if k != "plans"})


def public_job(job: dict) -> dict:
    return {k: v for k, v in job.items() if k != "plans"}


# ── 새 캐릭터: Claude 가 bible 작성 ──────────────────────────────────────
_BIBLE_SYSTEM = (
    "You design original fictional characters for an AI fashion/short-video studio. Given a name and a free-form "
    "Korean description, return ONE JSON object only, with these keys:\n"
    '  "id": short lowercase ascii romanization of the name for a database id (regex ^[a-z][a-z0-9_]{1,31}$),\n'
    '  "subject_en": "woman" or "man",\n'
    '  "age": integer,\n'
    '  "height_cm": integer or null,\n'
    '  "summary_en": one short English phrase used in an image prompt, e.g. '
    '"24-year-old Korean woman, an office worker living in Seoul" (no names, no celebrities),\n'
    '  "hair_en": short English hair description, e.g. "long straight black hair",\n'
    '  "vibe_en": a few English words about style and mood,\n'
    '  "notes_ko": one Korean sentence summary.\n'
    "Never mention body parts or body-shape emphasis (no bust, chest, hips, curves, sexy, etc.); body shape is handled "
    "by a separate reference image. Keep it wholesome and non-revealing."
)


def draft_bible(name: str, description: str) -> dict:
    from services import music_lyrics

    text = music_lyrics._call(_BIBLE_SYSTEM, f"Name: {name}\nDescription: {description}", max_tokens=600,
                              task="studio_bible")
    data = music_lyrics._extract_json(text)
    if not isinstance(data, dict):
        raise cs.StudioError("AI 응답을 읽지 못했어요 — 다시 시도해 주세요.")
    bible = {k: data.get(k) for k in ("subject_en", "age", "height_cm", "summary_en", "hair_en", "vibe_en", "notes_ko")}
    for k in ("summary_en", "hair_en", "vibe_en"):
        if bible.get(k):
            bible[k] = strip_unsafe(str(bible[k]))
    bible["description_ko"] = description
    return {"id": str(data.get("id") or ""), "bible": bible}


def _unique_id(base: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9_]", "", base.lower())
    if not re.match(r"^[a-z]", base or ""):
        base = f"char_{base}" if base else f"char_{secrets.token_hex(2)}"
    base = base[:28]
    if len(base) < 2:
        base = f"char_{secrets.token_hex(2)}"
    cid, n = base, 2
    while cid in taken:
        cid, n = f"{base}_{n}", n + 1
    return cs.check_character_id(cid)


def create_character(name: str, description: str, channel_id: str | None = None) -> dict:
    """이름 + 자유 설명 → bible 작성 → 캐릭터 등록. 얼굴 후보 생성은 호출부가 prepare_job 으로 이어서."""
    name, description = (name or "").strip(), (description or "").strip()
    if not name:
        raise cs.StudioError("캐릭터 이름을 입력해 주세요.")
    if not (5 <= len(description) <= 1000):
        raise cs.StudioError("설명을 5~1000자로 적어 주세요(예: 서울 사는 24살 직장인, 긴 흑발, 172cm).")
    if not get_muse_adapter().is_available():  # 얼굴 후보를 못 만들면 빈 캐릭터만 남으니 먼저 막는다
        raise cs.StudioStoreError("WAVESPEED_API_KEY 미설정 — 이미지를 생성할 수 없어요.")
    draft = draft_bible(name, description)
    taken = {c["id"] for c in cs.list_characters()}
    cid = _unique_id(draft["id"] or name, taken)
    return cs.upsert_character(cid, name, channel_id=channel_id, bible=draft["bible"])


# ── AI 역할 추천(가져오기) ───────────────────────────────────────────────
def _suggest_system(hair: list[dict], pose: list[dict]) -> str:
    hair_lines = "\n".join(f'    - "{h["role"]}": {h["line"]}' for h in hair)
    pose_lines = "\n".join(f'    - "{p["role"]}": {p["line"]}' for p in pose)
    return (
        "You sort reference images for an AI character studio. Look at ONE image and classify it.\n"
        "Reference images are plain studio shots made to define a character. Kinds:\n"
        '  - "face": a single person, head/upper-body portrait, face clearly visible, plain background.\n'
        '  - "body": a body reference sheet — the same person shown front view AND side view, in plain workout '
        "clothes (tank top + leggings), plain background.\n"
        '  - "hair": upper body + head of one person, front view, plain studio background, plain t-shirt, where the '
        "hairstyle or headwear is the point. Pick the closest role from this list by what you SEE (ignore any "
        "file name):\n"
        f"{hair_lines}\n"
        '  - "pose": only if it clearly matches one of these pose samples:\n'
        f"{pose_lines}\n"
        '  - "not_reference": everything else. IMPORTANT: outfit / fashion / lookbook / street / mirror-selfie photos '
        "that show styled clothes are NOT references even when a person is visible — classify them as "
        '"not_reference". Also product shots, screenshots, text, several different people, scenery.\n'
        'Return ONE JSON object only: {"kind": "face" | "body" | "hair" | "pose" | "not_reference", '
        '"role": "01_face" | "02_body" | "<a role from the lists above>" | "", "confidence": 0.0-1.0, '
        '"reason": "짧은 한국어 이유"}.'
    )


def _small_jpeg(src: Path, dst: Path) -> Path:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", "scale='min(768,iw)':-2",
                    "-frames:v", "1", "-q:v", "4", str(dst)], check=True, capture_output=True, timeout=60)
    return dst


def _parse_suggest(text: str, hair: list[dict], pose: list[dict]) -> dict:
    from services import music_lyrics

    data = music_lyrics._extract_json(text)
    if not isinstance(data, dict):
        raise ValueError("JSON 아님")
    kind = str(data.get("kind") or "not_reference")
    role = str(data.get("role") or "")
    hair_roles = {h["role"] for h in hair}
    pose_roles = {p["role"] for p in pose}
    if kind == "face":
        role = FACE_ROLE
    elif kind == "body":
        role = BODY_ROLE
    elif kind == "hair":
        if role not in hair_roles:  # 키만 맞춘 경우("straight", "hair_straight") 보정
            tail = role.split("_")[-1]
            role = next((r for r in hair_roles if r.endswith(f"_{tail}")), "")
    elif kind == "pose" and role in pose_roles:
        pass
    else:  # 포즈인데 목록에 없는 역할(대개 착장·라이프스타일 컷)·알 수 없는 kind → 기준 이미지 아님
        kind, role = "not_reference", ""
    try:
        conf = max(0.0, min(1.0, float(data.get("confidence") or 0)))
    except (TypeError, ValueError):
        conf = 0.0
    return {"kind": kind, "role": role, "confidence": conf, "reason": str(data.get("reason") or "")[:120]}


def suggest_role(character_id: str, data: bytes, filename: str) -> dict:
    """이미지 1장을 비전 AI 로 보고 역할 추천 → {kind, role, confidence, reason, model}. 저장은 하지 않는다."""
    from services import music_lyrics
    from services import music_llm_fallback as fb
    from services.music_auto_image import review_model

    char = cs.get_character(character_id)
    pr = presets(char)
    ext = (filename.rsplit(".", 1)[-1] if "." in (filename or "") else "").lower()
    if ext not in cs.ALLOWED_EXT:
        raise cs.StudioError("png·jpg·webp 이미지만 볼 수 있어요.")
    if not data or len(data) > cs.MAX_BYTES:
        raise cs.StudioError("빈 파일이거나 너무 커요.")
    system = _suggest_system(pr["hair"], pr["pose"])
    ask = "이 이미지를 분류하고 JSON 만 출력해."
    tmp = Path(tempfile.mkdtemp(prefix="studio_sug_"))
    try:
        src = tmp / f"in.{ext}"
        src.write_bytes(data)
        try:
            small = _small_jpeg(src, tmp / "small.jpg")
        except Exception as e:  # noqa: BLE001
            raise cs.StudioError("이미지를 읽을 수 없어요.") from e
        b64 = base64.b64encode(small.read_bytes()).decode("ascii")
        model = review_model()
        try:
            client = music_lyrics._client().with_options(timeout=40.0, max_retries=0)
            msg = client.messages.create(
                model=model, max_tokens=300, system=system,
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                    {"type": "text", "text": ask},
                ]}],
            )
            text = "".join(getattr(b, "text", "") for b in (msg.content or []))
            from services import music_ops_log
            music_ops_log.add_usage_from(msg, model)
        except Exception as e:  # noqa: BLE001 - Claude API 오류면 OpenAI 비전 1회 대체
            if not (fb.enabled() and fb.is_anthropic_api_error(e)):
                logger.warning("[studio] 역할 추천 호출 실패 %s: %s", filename, str(e)[:300])
                raise cs.StudioStoreError(f"AI 역할 추천 실패: {str(e)[:160]}") from e
            text, model = fb.vision(system, b64, ask, max_tokens=300, task="studio_suggest", cause=e)
        try:
            out = _parse_suggest(text, pr["hair"], pr["pose"])
        except Exception as e:  # noqa: BLE001
            logger.warning("[studio] 역할 추천 응답 파싱 실패 %s: %s", filename, (text or "")[:200])
            raise cs.StudioStoreError("AI 역할 추천 응답을 읽지 못했어요.") from e
        out["model"] = model
        logger.info("[studio] 역할 추천 %s → %s/%s %.2f (%s)", filename, out["kind"], out["role"] or "-",
                    out["confidence"], model)
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
