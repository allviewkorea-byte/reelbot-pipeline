"""인스타 쇼핑 A3 — 컬렉션 릴스(대표 승인 2026-10-27: 롤모델 @yxyxeon 포맷).

"같은 자세·같은 배경에 옷만 바꾼 Look 1~N" 릴스 1개를 끝까지 자동으로 만든다.
  1) 테마: AI가 계절·생활·스타일 가이드로 카테고리 1개(예: 퍼 아우터) + 표지 카피(영문 소제목·한글 2줄·.zip 박스)
  2) 상품: 테마 종류 N개(색이 겹치지 않게) + 고정 베이스(하의·신발 등)를 쿠팡 공식 API로 픽
  3) Look 1: A1 착장 파이프라인(턱 아래로 자른 착장 중심 컷 — 롤모델 스타일)
  4) Look 2~N: Look 1 결과를 참조로 "같은 사람·자세·배경, 그 옷만 교체"(Muse edit) + 검수 1회 재생성
  5) 영상: ffmpeg — 표지 1.2초 + 컷마다 1.8초, 가운데 세리프 "Look N". 무음(음악은 올릴 때 인스타에서)
  6) 저장: R2 insta/collections/{id}/ + ig_collections. 쿠팡 이미지 사본은 끝나면 삭제(약관 제5조)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import secrets
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from adapters import r2_storage
from adapters.base import ImageGenerationRequest

from services import character_studio_gen as gen
from services import insta_coordi as coordi
from services import insta_outfit as io
from services import insta_outfit_plan as P
from services import insta_picks as picks
from services import insta_style_guide as SG

logger = logging.getLogger(__name__)

N_LOOKS = 5
COVER_SEC = 1.2
LOOK_SEC = 1.8
SWAP_RETRY = 1
W, H = 1080, 1920
LOOK1_POSES = ["mirror_lean", "wall_knee_camera"]   # 롤모델처럼 전신·착장 중심, 얼굴은 턱 아래로

# AI 실패 시 계절별 기본 테마
FALLBACK_THEMES: dict[str, list[dict]] = {
    "autumn": [
        {"kind": "outerwear", "concept": "퍼 아우터", "title_en": "FUR OUTER COLLECTION",
         "title_ko": ["추워지기 전에", "쟁여둘 퍼 아우터"], "zip": "퍼 아우터 모음.zip",
         "queries": ["여성 퍼 자켓", "여성 뽀글이 자켓", "여성 페이크퍼 아우터"],
         "base": [{"kind": "bottoms", "queries": ["여성 블랙 미니스커트"]}, {"kind": "shoes", "queries": ["여성 블랙 롱부츠"]}],
         "styling_en": "sheer black tights"},
        {"kind": "outerwear", "concept": "앙고라 가디건", "title_en": "ANGORA COLLECTION",
         "title_ko": ["자꾸 눈길 가는", "복슬복슬 앙고라"], "zip": "앙고라 코디 모음.zip",
         "queries": ["여성 앙고라 가디건", "여성 퍼 니트 가디건", "여성 헤어리 가디건"],
         "base": [{"kind": "top", "queries": ["여성 레이스 나시"]}, {"kind": "bottoms", "queries": ["여성 와이드 데님"]}]},
    ],
    "winter": [
        {"kind": "outerwear", "concept": "숏패딩", "title_en": "PADDING COLLECTION",
         "title_ko": ["한파 오기 전에", "꼭 필요한 숏패딩"], "zip": "숏패딩 모음.zip",
         "queries": ["여성 크롭 숏패딩", "여성 숏패딩 자켓", "여성 무광 숏패딩"],
         "base": [{"kind": "bottoms", "queries": ["여성 와이드 데님"]}, {"kind": "shoes", "queries": ["여성 어그 부츠"]}]},
    ],
    "spring": [
        {"kind": "outerwear", "concept": "가디건", "title_en": "CARDIGAN COLLECTION",
         "title_ko": ["간절기에 딱", "매일 손이 가는 가디건"], "zip": "가디건 모음.zip",
         "queries": ["여성 크롭 가디건", "여성 니트 가디건", "여성 파스텔 가디건"],
         "base": [{"kind": "bottoms", "queries": ["여성 연청 와이드 데님"]}, {"kind": "shoes", "queries": ["여성 메리제인"]}]},
    ],
    "summer": [
        {"kind": "top", "concept": "나시", "title_en": "SLEEVELESS COLLECTION",
         "title_ko": ["여름엔 이거 하나면", "끝나는 나시"], "zip": "나시 모음.zip",
         "queries": ["여성 골지 나시", "여성 레이스 나시", "여성 홀터 나시"],
         "base": [{"kind": "bottoms", "queries": ["여성 와이드 데님"]}, {"kind": "shoes", "queries": ["여성 스니커즈"]}]},
    ],
}

_THEME_SYSTEM = (
    "You plan ONE Instagram 'collection reel' for a hip Korean virtual fashion influencer in her early 20s "
    "(꾸안꾸, Seoul street vibe). The reel shows the same pose N times while ONLY one garment category changes. "
    "Follow the style_guide. Return ONE JSON object: "
    '{"kind": "outerwear|top|bottoms|dress|shoes|bag", "concept": "<짧은 한글 테마, 8자 이내>", '
    '"title_en": "<UPPERCASE english subtitle like FUR OUTER COLLECTION>", '
    '"title_ko": ["<표지 1줄, 12자 이내>", "<표지 2줄, 14자 이내>"], "zip": "<○○ 모음.zip>", '
    '"queries": ["<쿠팡 검색어 — 여성 + 종류 + 특징>", "...", "..."], '
    '"base": [{"kind": "...", "queries": ["<고정으로 함께 입을 아이템 검색어>"]}], '
    '"styling_en": "<optional non-product styling like sheer black tights, or empty>"} — base has 1-2 items, '
    "different kinds from the theme kind, plain and versatile so every variant looks good with them."
)


class CollectionError(ValueError):
    """사용자에게 보여 줄 400 사유."""


def _season() -> str:
    return P.season_of(datetime.now(P.KST).date())


def plan_theme(season: str, life: str, recent: list[str] | None = None, llm=None,
               rng: random.Random | None = None) -> dict:
    """테마 1개(AI, 실패 시 계절 기본). 최근 쓴 컨셉은 피한다."""
    r = rng or random
    from services import music_lyrics
    llm = llm or (lambda s, u: music_lyrics._call(s, u, max_tokens=700, task="insta_collection_theme"))
    try:
        data = music_lyrics._extract_json(llm(_THEME_SYSTEM, json.dumps({
            "season": season, "life": life, "avoid_recent_concepts": recent or [],
            "style_guide": SG.guide_text(season, life)}, ensure_ascii=False)))
        kind = data.get("kind")
        qs = [str(q)[:40] for q in (data.get("queries") or []) if str(q).strip()][:3]
        title_ko = [str(x)[:16] for x in (data.get("title_ko") or [])][:2]
        if kind in P.PRODUCT_KINDS and qs and len(title_ko) == 2:
            base = [{"kind": b.get("kind"), "queries": [str(q)[:40] for q in (b.get("queries") or [])][:2]}
                    for b in (data.get("base") or []) if b.get("kind") in P.PRODUCT_KINDS and b.get("kind") != kind
                    and b.get("queries")][:2]
            return {"kind": kind, "concept": str(data.get("concept") or "")[:12] or "코디 모음",
                    "title_en": str(data.get("title_en") or "COLLECTION")[:32].upper(), "title_ko": title_ko,
                    "zip": str(data.get("zip") or "코디 모음.zip")[:20], "queries": qs, "base": base,
                    "styling_en": str(data.get("styling_en") or "")[:80] or None, "source": "ai"}
    except Exception as e:  # noqa: BLE001
        logger.warning("[insta-collection] 테마 AI 실패 → 기본: %s", str(e)[:160])
    pool = FALLBACK_THEMES.get(season) or FALLBACK_THEMES["autumn"]
    fresh = [t for t in pool if t["concept"] not in set(recent or [])] or pool
    return {**r.choice(fresh), "source": "fallback"}


def pick_variants(theme: dict, d: picks.Deps, usage: dict, n: int = N_LOOKS) -> list[dict]:
    """테마 종류 상품 n개 — 점수 순, 같은 색 계열은 뒤로(색이 고르게)."""
    spec = {"kind": theme["kind"], "queries": theme["queries"], "color_name": "", "hex": None, "fit": "", "length": "",
            "material": "", "details": theme.get("concept", "")}
    with tempfile.TemporaryDirectory() as td:
        cands, _ = picks.gather(spec, d, usage)
        kept, _ = picks.code_filter(cands, spec["kind"])
        scored, _ = picks.judge(spec, {"seasons": [_season()]}, kept, d, usage, Path(td)) if kept else ([], [])
    scored = [c for c in scored if c.get("score", 0) >= picks.MIN_SCORE] or scored
    out, fams = [], set()
    for c in scored:  # 1차: 새 색 계열만
        fam = picks.color_family((c.get("scores") or {}).get("hex"))[0]
        if fam not in fams or fam == "unknown":
            out.append(c)
            fams.add(fam)
        if len(out) >= n:
            break
    for c in scored:  # 2차: 모자라면 나머지
        if len(out) >= n:
            break
        if c not in out:
            out.append(c)
    return out[:n]


def pick_base(theme: dict, d: picks.Deps, usage: dict) -> list[dict]:
    """고정 베이스 아이템(종류마다 1등)."""
    items = []
    with tempfile.TemporaryDirectory() as td:
        for b in theme.get("base") or []:
            spec = {"kind": b["kind"], "queries": b["queries"], "color_name": "", "hex": None, "fit": "", "length": "",
                    "material": "", "details": ""}
            cands, _ = picks.gather(spec, d, usage)
            kept, _ = picks.code_filter(cands, spec["kind"])
            scored, _ = picks.judge(spec, {"seasons": [_season()]}, kept, d, usage, Path(td)) if kept else ([], [])
            pick, _, _ = picks.choose(scored)
            if pick:
                items.append({"kind": b["kind"], "pick": pick})
    return items


def _saved(cands: list[dict], d: picks.Deps) -> list[dict]:
    saved = picks.save_products(cands, d)
    out = []
    for c in cands:
        row = saved.get((c["channel"], c["product_id"])) or {}
        out.append({**picks._public(c), "id": row.get("id"), "image_key": row.get("image_key"),
                    "affiliate_link": row.get("affiliate_link")})
    return out


# ── 옷 교체(Look 2~N) ─────────────────────────────────────────────────────
_SWAP_REVIEW = (
    "You check one frame of an Instagram 'same pose, different outfit' reel. Image 1 is the base photo, image 2 is "
    "the new frame, image 3 is the product photo of the garment that must now be worn. Fail if ANY:\n"
    "1. different: the person, hair, pose, hand position, background, lighting or framing clearly changed from image 1.\n"
    "2. product_mismatch: the swapped garment is noticeably different from image 3 (color, pattern, key details, length).\n"
    "3. anatomy: wrong fingers/limbs, melted hands.\n"
    "4. text: captions, watermarks, or AI-made logos on clothing.\n"
    'Return ONE JSON object only: {"pass": true|false, "violations": [{"type": "<key>", "detail": "짧은 한국어"}], '
    '"fix_en": "<one short English fix or empty>"}.'
)


def swap_prompt(kind: str, fix: str | None = None) -> str:
    noun = P.PRODUCT_KINDS.get(kind, ("", "the garment"))[1]
    prompt = (f"Same photo as image 1 — exactly the same woman, same face, same hair, same pose, same hand position, "
              f"same background, same lighting and the same framing. Replace ONLY {noun} with {noun} from image 2 — "
              f"take only the clothing from image 2 and ignore any model wearing it; {P._DETAIL}. Everything else in "
              f"the photo stays exactly as it is.")
    if fix:
        prompt += f" Important fix from the last attempt: {fix.strip().rstrip('.')}."
    return gen.strip_unsafe(prompt)


def swap_look(base_url: str, base_path: Path, product: dict, product_path: Path, out: Path) -> dict:
    """Look 1 → 옷만 교체. 검수 실패면 1회 재생성. → {cost, attempts, review}."""
    adapter = io.get_muse_adapter()
    cost, fix, review = 0.0, None, None
    for attempt in range(1 + SWAP_RETRY):
        prompt = swap_prompt(product["kind"], fix)
        res = asyncio.run(adapter.generate(ImageGenerationRequest(
            prompt=prompt, reference_images=[base_url, product["url"]], aspect_ratio="9:16", output_path=str(out))))
        cost += res.cost_usd
        try:
            with tempfile.TemporaryDirectory() as td:
                t = Path(td)
                imgs = [gen._small_jpeg(base_path, t / "a.jpg"), gen._small_jpeg(out, t / "b.jpg"),
                        gen._small_jpeg(product_path, t / "c.jpg")]
                data = io._vision_json(_SWAP_REVIEW, imgs, "기준대로 검수하고 JSON 만 출력해.", "insta_swap_review")
            vio = [v for v in (data.get("violations") or []) if isinstance(v, dict)][:4]
            review = {"pass": bool(data.get("pass")) and not vio, "violations": vio}
            fix = str(data.get("fix_en") or "") or "; ".join(str(v.get("detail", "")) for v in vio) or None
        except Exception as e:  # noqa: BLE001 - 검수 실패는 통과(반자동 기간)
            review = {"pass": True, "skipped": str(e)[:120], "violations": []}
        if review["pass"]:
            return {"cost": cost, "attempts": attempt + 1, "review": review}
    return {"cost": cost, "attempts": 1 + SWAP_RETRY, "review": review}


# ── 영상 ─────────────────────────────────────────────────────────────────
_SERIF = ["/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc", "/usr/share/fonts/truetype/nanum/NanumMyeongjo.ttf"]
_BOLD = ["/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
         "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"]


def _font(cands: list[str]) -> str:
    for p in cands:
        if os.path.exists(p):
            return p
    from services import music_video
    return music_video._resolve_font()


def _stage(work: Path, src: str, name: str) -> str:
    dst = work / f"{name}{os.path.splitext(src)[1] or '.ttf'}"
    if not dst.exists():
        shutil.copy(src, dst)
    return dst.name


def _txt(work: Path, name: str, text: str) -> str:
    (work / name).write_text(text, encoding="utf-8")
    return name


_FIT = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"


def _segment(work: Path, img: str, dur: float, draws: list[str], out: str) -> None:
    vf = ",".join([_FIT, *draws, "format=yuv420p"])
    cmd = ["ffmpeg", "-y", "-loop", "1", "-t", f"{dur}", "-i", img, "-vf", vf, "-r", "30", "-c:v", "libx264",
           "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", out]
    res = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=120)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg 실패: {res.stderr[-300:]}")


def render_reel(work: Path, look_images: list[str], theme: dict, out_name: str = "reel.mp4") -> tuple[str, str]:
    """표지(Look 1 + 카피) + Look 1~N → mp4, 표지 jpg. 파일명은 work 기준 상대."""
    serif = _stage(work, _font(_SERIF), "serif")
    bold = _stage(work, _font(_BOLD), "bold")
    shadow = "shadowcolor=black@0.45:shadowx=2:shadowy=2"
    cover = [
        f"drawtext=fontfile={bold}:textfile={_txt(work, 't_en.txt', theme['title_en'])}:fontsize=34:fontcolor=white:"
        f"x=90:y=h*0.64:{shadow}",
        f"drawtext=fontfile={bold}:textfile={_txt(work, 't_k1.txt', theme['title_ko'][0])}:fontsize=76:fontcolor=white:"
        f"x=90:y=h*0.67:{shadow}",
        f"drawtext=fontfile={bold}:textfile={_txt(work, 't_k2.txt', theme['title_ko'][1])}:fontsize=76:fontcolor=white:"
        f"x=90:y=h*0.67+96:{shadow}",
        f"drawtext=fontfile={bold}:textfile={_txt(work, 't_zip.txt', theme['zip'])}:fontsize=34:fontcolor=black:"
        f"box=1:boxcolor=white@0.95:boxborderw=12:x=90:y=h*0.67+214",
    ]
    _segment(work, look_images[0], COVER_SEC, cover, "seg0.mp4")
    segs = ["seg0.mp4"]
    for i, img in enumerate(look_images, start=1):
        draw = (f"drawtext=fontfile={serif}:textfile={_txt(work, f'look{i}.txt', f'Look {i}')}:fontsize=128:"
                f"fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2:{shadow}")
        _segment(work, img, LOOK_SEC, [draw], f"seg{i}.mp4")
        segs.append(f"seg{i}.mp4")
    (work / "list.txt").write_text("".join(f"file '{s}'\n" for s in segs), encoding="utf-8")
    res = subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy", out_name],
                         cwd=work, capture_output=True, text=True, timeout=120)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg 합치기 실패: {res.stderr[-300:]}")
    res = subprocess.run(["ffmpeg", "-y", "-ss", "0.5", "-i", "seg0.mp4", "-frames:v", "1", "-q:v", "3", "cover.jpg"],
                         cwd=work, capture_output=True, text=True, timeout=60)
    if res.returncode != 0:
        raise RuntimeError(f"표지 추출 실패: {res.stderr[-300:]}")
    return out_name, "cover.jpg"


# ── 잡 ───────────────────────────────────────────────────────────────────
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


def _set(job_id: str, **kw) -> None:
    with _LOCK:
        _JOBS[job_id].update(kw)


def public_job(j: dict) -> dict:
    return {k: v for k, v in j.items() if not k.startswith("_")}


def get_job(job_id: str) -> dict:
    with _LOCK:
        if job_id not in _JOBS:
            raise LookupError("작업을 찾을 수 없어요(서버 재시작 — 아래 목록에서 확인해 주세요).")
        return public_job(_JOBS[job_id])


def _recent_concepts(d: picks.Deps, limit: int = 6) -> list[str]:
    try:
        rows = d.rest("ig_collections", "GET", params={"select": "theme", "order": "created_at.desc", "limit": str(limit)})
        return [((r.get("theme") or {}).get("concept")) for r in rows if (r.get("theme") or {}).get("concept")]
    except Exception:  # noqa: BLE001
        return []


def start(character_id: str = "chaei", n: int = N_LOOKS, d: picks.Deps | None = None) -> dict:
    d = d or picks.Deps()
    coordi._ready(character_id)
    if not d.coupang.is_available():
        raise CollectionError("쿠팡 연결이 필요해요(키 없음).")
    if not io.get_muse_adapter().is_available():
        raise CollectionError("이미지 생성 키(WAVESPEED)가 없어요.")
    with _LOCK:
        for j in _JOBS.values():
            if j["state"] in ("queued", "running") and j["_args"]["character_id"] == character_id:
                return public_job(j)
    n = max(3, min(7, int(n or N_LOOKS)))
    cid = f"cl-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(3)}"
    d.rest("ig_collections", "POST", json_body=[{"id": cid, "character_id": character_id, "status": "making"}],
           prefer="return=minimal")
    job_id = f"clj_{secrets.token_hex(5)}"
    with _LOCK:
        _JOBS[job_id] = {"id": job_id, "collection_id": cid, "state": "queued", "step": "준비", "error": None,
                         "done_looks": 0, "n": n, "_deps": d, "_args": {"character_id": character_id, "n": n}}
    return public_job(_JOBS[job_id])


def _patch(d: picks.Deps, cid: str, fields: dict) -> None:
    d.rest("ig_collections", "PATCH", params={"id": f"eq.{cid}"}, prefer="return=minimal",
           json_body={**fields, "updated_at": datetime.now(timezone.utc).isoformat()})


def run(job_id: str, *, llm=None, rng: random.Random | None = None) -> None:
    with _LOCK:
        j = _JOBS[job_id]
        j["state"] = "running"
        d, cid, args = j["_deps"], j["collection_id"], dict(j["_args"])
    character_id, n = args["character_id"], args["n"]
    rng = rng or random.Random()
    tmp = Path(tempfile.mkdtemp(prefix="insta_coll_"))
    usage: dict = {}
    cost = 0.0
    all_products: list[dict] = []
    try:
        season = _season()
        life = coordi._life_today()
        _set(job_id, step="테마 정하는 중")
        theme = plan_theme(season, life, _recent_concepts(d), llm=llm, rng=rng)
        _set(job_id, step=f"「{theme['concept']}」 상품 고르는 중", theme={k: theme[k] for k in ("concept", "title_ko", "zip")})
        _patch(d, cid, {"theme": theme})
        variants = _saved(pick_variants(theme, d, usage, n), d)
        base = pick_base(theme, d, usage)
        base_saved = _saved([b["pick"] for b in base], d) if base else []
        all_products = variants + base_saved
        if len(variants) < 3:
            raise CollectionError(f"「{theme['concept']}」 상품을 3개 이상 못 찾았어요 — 다시 눌러 주세요.")
        for c in all_products:
            c["kind"] = c.get("kind") or theme["kind"]
        items = [{"kind": theme["kind"], "pick": variants[0], "source": "coupang"}] + \
                [{"kind": b["kind"], "pick": s, "source": "coupang"} for b, s in zip(base, base_saved)]

        # Look 1 — A1 파이프라인(턱 아래 크롭·착장 중심)
        _set(job_id, step="Look 1 만드는 중")
        coordi.ensure_images(items, d)
        opts = {"pose": rng.choice(LOOK1_POSES), "face": "chin_crop"}
        if theme.get("styling_en"):
            opts["styling_en"] = theme["styling_en"]
        oj = io.start(character_id, coordi._cap_products(coordi._outfit_products(items)), opts,
                      remake_of=f"{cid}:{secrets.token_hex(2)}")
        io.run(oj["id"], rng=rng)
        oj = io.get_job(oj["id"])
        cost += oj.get("cost_usd") or 0.0
        if oj["state"] != "done":
            raise CollectionError(f"Look 1 생성 실패: {oj.get('error') or ''}")
        row = io.get_outfit(oj["outfit_id"])
        base_key = row["image_key"]
        base_url = io.public_url(base_key)
        base_path = io._download(base_url, tmp / "look1.png")
        looks = [{"n": 1, "outfit_id": oj["outfit_id"], "image_key": base_key, "processed_key": row.get("processed_key"),
                  "product": {k: variants[0].get(k) for k in ("id", "name", "mall", "price", "link", "affiliate_link")},
                  "review": row.get("review")}]
        _set(job_id, done_looks=1)

        # Look 2~N — 옷만 교체
        imgs = [str(io.postprocess(base_path, tmp / "p1.jpg").name)]
        for i, v in enumerate(variants[1:], start=2):
            _set(job_id, step=f"Look {i} 만드는 중")
            coordi.ensure_images([{"kind": theme["kind"], "pick": v}], d)
            prod = {"kind": theme["kind"], "url": io.public_url(v["image_key"])}
            prod_path = io._download(prod["url"], tmp / f"prod{i}.jpg")
            out = tmp / f"look{i}.png"
            got = swap_look(base_url, base_path, prod, prod_path, out)
            cost += got["cost"]
            key = f"insta/collections/{cid}/look{i}.png"
            r2_storage.upload_image(str(out), key, bucket=r2_storage._character_bucket(),
                                    public_base_url=r2_storage._character_public_base(), content_type="image/png")
            imgs.append(str(io.postprocess(out, tmp / f"p{i}.jpg").name))
            looks.append({"n": i, "image_key": key, "review": got["review"], "attempts": got["attempts"],
                          "product": {k: v.get(k) for k in ("id", "name", "mall", "price", "link", "affiliate_link")}})
            _set(job_id, done_looks=i)
            _patch(d, cid, {"looks": looks})

        # 영상
        _set(job_id, step="릴스 영상 만드는 중")
        video, cover = render_reel(tmp, imgs, theme)
        vkey, ckey = f"insta/collections/{cid}/reel.mp4", f"insta/collections/{cid}/cover.jpg"
        bucket, pub = r2_storage._character_bucket(), r2_storage._character_public_base()
        r2_storage.upload_image(str(tmp / video), vkey, bucket=bucket, public_base_url=pub, content_type="video/mp4")
        r2_storage.upload_image(str(tmp / cover), ckey, bucket=bucket, public_base_url=pub, content_type="image/jpeg")
        total = round(cost + picks.vision_cost_usd(d.meter), 4)
        _patch(d, cid, {"looks": looks, "base_items": [{k: b.get(k) for k in ("id", "name", "mall", "link")} for b in base_saved],
                        "video_key": vkey, "cover_key": ckey, "status": "ok", "cost_usd": total, "usage": usage})
        _set(job_id, state="done", step="완료", cost_usd=total)
    except Exception as e:  # noqa: BLE001
        msg = str(e)[:300]
        logger.warning("[insta-collection] %s 실패: %s", cid, msg)
        _set(job_id, state="failed", step="실패", error=msg)
        try:
            _patch(d, cid, {"status": "failed", "error": msg, "cost_usd": round(cost, 4)})
        except Exception:  # noqa: BLE001
            pass
    finally:
        picks.delete_images(all_products, d)   # 쿠팡 이미지 사본: 쓰고 지운다
        shutil.rmtree(tmp, ignore_errors=True)


def view(row: dict) -> dict:
    url = io.public_url
    return {**row, "video_url": url(row.get("video_key")), "cover_url": url(row.get("cover_key")),
            "looks": [{**lk, "image_url": url(lk.get("processed_key") or lk.get("image_key"))} for lk in (row.get("looks") or [])]}


def list_collections(limit: int = 10, d: picks.Deps | None = None) -> list[dict]:
    d = d or picks.Deps()
    rows = d.rest("ig_collections", "GET", params={"select": "*", "order": "created_at.desc", "limit": str(limit)})
    return [view(r) for r in rows]
