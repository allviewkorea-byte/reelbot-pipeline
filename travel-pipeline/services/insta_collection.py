"""인스타 쇼핑 A3 — 컬렉션 릴스(대표 승인 2026-10-27).

"테마 하나(예: 가디건)로 01~05, 컷마다 다른 포즈·장소·코디" 릴스 1개를 끝까지 자동으로 만든다.
(2026-10-27 대표 변경: 같은 포즈에 옷만 바꾸던 방식 → 매번 다른 포즈·배경·코디. 같은 포즈 방식은 없앰)
  1) 테마: AI가 계절·생활·스타일 가이드로 카테고리 1개 + 표지 카피(영문 소제목·"○○ 모음.zip")
  2) 상품: 테마 종류 N개(색·소재가 겹치지 않게) + 함께 입는 종류(하의·신발 등)는 종류마다 후보 여러 개를 골라
     룩마다 다른 것을 짝지음(쿠팡 검색은 종류당 1회 — 시간당 한도)
  3) 장면: 룩마다 A1 장면 기획(plan_scene)으로 서로 다른 포즈·장소·얼굴 컷 — 미리보기에서 보여 준다
  4) 생성: 룩마다 A1 착장 파이프라인(기준 얼굴·체형 검수 포함)
  5) 영상: ffmpeg — 표지 1.2초 + 컷마다 1.8초, 번호 스티커 01~05. 무음(음악은 올릴 때 인스타에서)
  6) 저장: R2 + ig_collections. 쿠팡 이미지 사본은 끝나면 삭제(약관 제5조)
"""

from __future__ import annotations

import json
import logging
import os
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

from services import character_studio as cs
from services import character_studio_gen as gen
from services import insta_brands as BR
from services import insta_coordi as coordi
from services import insta_outfit as io
from services import insta_outfit_plan as P
from services import insta_picks as picks
from services import insta_style_guide as SG

logger = logging.getLogger(__name__)

N_LOOKS = 5
MIN_LOOKS = 4     # 대표 2026-10-28: 최소 4룩은 나와야 함
SPARE_LOOKS = 1   # 예비 룩 — 만들다 실패하면 대신 만든다(미리보기엔 숨김)
COVER_SEC = 1.2
LOOK_SEC = 1.8
W, H = 1080, 1920
SCENE_TRIES = 3   # 앞 룩과 포즈·장소가 겹치면 다시 기획하는 횟수

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
    "(꾸안꾸, Seoul street vibe). The reel shows N different everyday outfits, each built around one item of the "
    "theme category, in different places and poses. "
    "Follow the style_guide. Return ONE JSON object: "
    '{"kind": "outerwear|top|bottoms|dress|shoes|bag", "concept": "<짧은 한글 테마, 8자 이내>", '
    '"title_en": "<UPPERCASE english subtitle like FUR OUTER COLLECTION>", '
    '"title_ko": ["<표지 1줄, 12자 이내>", "<표지 2줄, 14자 이내>"], "zip": "<○○ 모음.zip>", '
    '"queries": ["<쿠팡 검색어 — 여성 + 종류 + 특징>", "...", "..."], '
    '"base": [{"kind": "...", "queries": ["<고정으로 함께 입을 아이템 검색어>"]}], '
    '"styling_en": "<optional non-product styling like sheer black tights, or empty>"} — base has 1-2 items, '
    "different kinds from the theme kind, plain and versatile (we pick several of each, one per look). "
    "The 3 queries MUST differ in material or color (e.g. leather / suede / wool, or black / brown / cream) so the "
    "looks are clearly different from each other — never 3 queries for the same material."
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
    llm = llm or (lambda s, u: music_lyrics._call(s, u, max_tokens=700, task="insta_collection_theme",
                                                  model=picks.strong_model()))
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


# 표지 맨 위 가장 큰 글씨 — 채널 슬로건(대표 2026-10-27). 아래 박스는 테마별 "○○ 모음.zip".
SLOGAN = "코디 저장소"

VARIANT_SCORE_TOP = 15   # 컬렉션은 5개를 색 고르게 뽑아야 해서 코디(8)보다 많이 심사


# 소재 묶음 — 같은 색·같은 소재가 연달아 나오면 룩끼리 구분이 안 됨(대표 2026-10-27: 블랙 레더 3벌)
_MATERIALS = [
    ("leather", re.compile(r"(레더|가죽|PU|라이더|leather)", re.I)),
    ("suede", re.compile(r"(스웨이드|스웨드|suede)", re.I)),
    ("denim", re.compile(r"(데님|청\s?자켓|진\s?자켓|denim)", re.I)),
    ("fur", re.compile(r"(페이크\s?퍼|퍼\s?(자켓|재킷|코트|점퍼)|무스탕|시어링|양털|플리스|뽀글)", re.I)),
    ("tweed", re.compile(r"(트위드|tweed)", re.I)),
    ("knit", re.compile(r"(니트|가디건|knit)", re.I)),
    ("corduroy", re.compile(r"(코듀로이|골덴)", re.I)),
    ("nylon", re.compile(r"(나일론|바람막이|윈드|패딩|푸퍼)", re.I)),
    ("wool", re.compile(r"(울\s?(코트|자켓|재킷|블렌드)|모직|wool)", re.I)),
]


def material_of(name: str) -> str:
    for key, rx in _MATERIALS:
        if rx.search(name or ""):
            return key
    return "other"


# 테마 이름의 일반 단어 → 상품명에서 같이 인정할 말(예: 아우터 = 자켓·코트…)
_SYNONYMS = {
    "아우터": ["아우터", "자켓", "재킷", "코트", "점퍼", "블루종", "패딩", "무스탕", "가디건"],
    "니트": ["니트", "스웨터", "풀오버", "가디건"], "가디건": ["가디건"], "스커트": ["스커트", "치마"],
    "치마": ["스커트", "치마"], "바지": ["팬츠", "바지", "슬랙스", "데님", "진"], "팬츠": ["팬츠", "바지", "슬랙스"],
    "패딩": ["패딩", "푸퍼", "다운"], "원피스": ["원피스", "드레스"], "부츠": ["부츠"], "가방": ["백", "가방"],
    "미니스커트": ["스커트", "치마"], "숏패딩": ["패딩", "푸퍼"], "나시": ["나시", "슬리브리스", "민소매", "탱크"],
    "데님": ["데님", "청", "진"],
}
_GENERIC = {"여성", "여자", "모음", "코디", "컬렉션", "룩", "데일리"}


def concept_terms(theme: dict) -> list[list[str]]:
    """테마 이름 → 상품명에 하나라도 들어가야 하는 말 묶음. (대표 2026-10-28: '앙고라 가디건' 테마에 후드 집업·
    자켓이 섞임 — 점수 미달이어도 그대로 쓰던 것 + 종류(아우터)만 맞으면 통과하던 것)"""
    words = [w for w in str(theme.get("concept") or "").replace(".zip", "").split() if w and w not in _GENERIC]
    return [_SYNONYMS.get(w, [w]) for w in words]


def concept_match(name: str, theme: dict) -> bool:
    """상품명에 테마의 아이템 말(마지막 단어 또는 그 동의어)이 있거나, 앞 단어(예: 앙고라)가 있으면 통과."""
    terms = concept_terms(theme)
    if not terms:
        return True
    low = (name or "").replace(" ", "").lower()
    if any(t.replace(" ", "").lower() in low for t in terms[-1]):
        return True
    return any(t.lower() in low for g in terms[:-1] for t in g if len(t) >= 2)


def pick_variants(theme: dict, d: picks.Deps, usage: dict, n: int = N_LOOKS,
                  rng: random.Random | None = None) -> list[dict]:
    """테마 종류 상품 n개 — 색 계열·소재가 겹치지 않게(1차: 둘 다 새로움, 2차: 하나라도 새로움, 3차: 나머지).

    검색어: A 브랜드 + 검색어1 / B 브랜드 + 검색어2 / 검색어3(보세) — insta_brands.mix_queries.
    """
    spec = {"kind": theme["kind"], "queries": theme["queries"], "color_name": "", "hex": None, "fit": "", "length": "",
            "material": "", "details": theme.get("concept", "")}
    with tempfile.TemporaryDirectory() as td:
        # 코디는 1개만 고르면 돼서 gather 가 검색어 1개(10개)만 쓴다 — 컬렉션은 5개가 필요해 검색어 3개를 다 쓴다.
        cands = []
        for q in BR.mix_queries(theme["kind"], theme["queries"], rng):
            got, notes = picks.gather({**spec, "queries": [q]}, d, usage)
            cands += got
            usage.setdefault("notes", []).extend(notes)
            if any("한도" in n for n in notes):
                break
        kept, _ = picks.code_filter(cands, spec["kind"])
        scored, _ = picks.judge(spec, {"seasons": [_season()]}, kept, d, usage, Path(td),
                                top=VARIANT_SCORE_TOP) if kept else ([], [])
    # 점수 미달은 버린다(예전엔 모자라면 미달도 썼음) + 테마 아이템이 맞는지 상품명으로 한 번 더
    scored = [c for c in scored if c.get("score", 0) >= picks.MIN_SCORE and concept_match(c.get("name", ""), theme)]
    def key(c: dict) -> tuple[str, str]:
        return picks.color_family((c.get("scores") or {}).get("hex"))[0], material_of(c.get("name", ""))

    out: list[dict] = []
    fams: set[str] = set()
    mats: set[str] = set()
    for need_both in (True, False):
        for c in scored:
            if len(out) >= n:
                break
            if c in out:
                continue
            fam, mat = key(c)
            new_fam = fam not in fams or fam == "unknown"
            new_mat = mat not in mats or mat == "other"
            if (new_fam and new_mat) if need_both else (new_fam or new_mat):
                out.append(c)
                fams.add(fam)
                mats.add(mat)
    for c in scored:  # 3차: 그래도 모자라면 나머지
        if len(out) >= n:
            break
        if c not in out:
            out.append(c)
    return out[:n]


def base_specs(theme: dict, season: str, llm=None) -> list[dict]:
    """테마 아이템에 어울리는 '나머지 코디' 명세 — 코디 찾기의 빈칸 채우기와 같은 규칙·AI(대표 2026-10-27:
    미니스커트 테마인데 롱부츠만 붙고 상의·아우터가 없었음).

    필요한 종류: 원피스가 아니면 상·하의, 가을·겨울은 아우터, 그다음 신발·가방(착장 참조 상한 안에서).
    명세(색·핏·검색어)는 테마 아이템을 기준으로 AI가 어울리게 설계(fill_specs) — 테마 AI가 준 base 검색어가
    같은 종류면 앞에 붙인다.
    """
    need = coordi._auto_need([theme["kind"]], season)
    if not need:
        return []
    hint = [{"kind": theme["kind"], "desc": f"{theme.get('concept', '')} ({theme['queries'][0] if theme.get('queries') else ''})"}]
    _, specs = coordi.fill_specs(hint, need, season, llm=llm)
    by_kind = {b.get("kind"): b.get("queries") or [] for b in theme.get("base") or []}
    for sp in specs:
        sp["queries"] = (by_kind.get(sp["kind"]) or [])[:1] + [q for q in sp.get("queries") or [] if q][:2]
    return specs


def pick_base(theme: dict, d: picks.Deps, usage: dict, n: int = N_LOOKS, season: str | None = None,
              llm=None) -> list[dict]:
    """나머지 코디 종류마다 후보 n개(점수순, 색 계열 고르게) → [{kind, picks:[…]}]. 쿠팡 검색은 종류당 1회."""
    pools = []
    with tempfile.TemporaryDirectory() as td:
        for spec in base_specs(theme, season or _season(), llm=llm):
            scored = []
            fallback = coordi._FALLBACK.get(spec["kind"], (None, None, None))[2]
            for qs in (spec["queries"], [fallback] if fallback and fallback not in spec["queries"] else []):
                if not qs:
                    continue   # 못 찾으면 기본 검색어(예: 여성 블랙 로퍼)로 한 번 더
                cands, notes = picks.gather({**spec, "queries": qs}, d, usage)
                usage.setdefault("notes", []).extend(notes)
                kept, _ = picks.code_filter(cands, spec["kind"])
                scored, _ = picks.judge(spec, {"seasons": [season or _season()]}, kept, d, usage, Path(td)) if kept else ([], [])
                scored = [c for c in scored if c.get("score", 0) >= picks.MIN_SCORE]
                if scored:
                    break
            out, fams = [], set()
            for c in scored:
                fam = picks.color_family((c.get("scores") or {}).get("hex"))[0]
                if fam not in fams or fam == "unknown":
                    out.append(c)
                    fams.add(fam)
            out += [c for c in scored if c not in out]
            if out:
                pools.append({"kind": spec["kind"], "picks": out[:n]})
    return pools


def _hex(c: dict) -> str | None:
    return (c.get("scores") or {}).get("hex")


def pair_outfits(variants: list[dict], pools: list[list[dict]]) -> list[list[dict]]:
    """룩마다 [테마 아이템 + 종류별 1개]. 색 조합(3색·포인트 1색)이 맞는 것 우선, 같은 아이템은 되도록 안 겹치게."""
    used: list[dict] = [dict() for _ in pools]
    outfits = []
    for v in variants:
        chosen = [v]
        for k, pool in enumerate(pools):
            if not pool:
                continue

            def cost(c: dict, k: int = k) -> tuple[int, int, int]:
                combo = picks.combo_violations([_hex(x) for x in chosen] + [_hex(c)])
                return (0 if combo["ok"] else 1, used[k].get(id(c), 0), pool.index(c))

            best = min(pool, key=cost)
            used[k][id(best)] = used[k].get(id(best), 0) + 1
            chosen.append(best)
        outfits.append(chosen)
    return outfits


def _saved(cands: list[dict], d: picks.Deps) -> list[dict]:
    saved = picks.save_products(cands, d)
    out = []
    for c in cands:
        row = saved.get((c["channel"], c["product_id"])) or {}
        out.append({**picks._public(c), "id": row.get("id"), "image_key": row.get("image_key"),
                    "affiliate_link": row.get("affiliate_link")})
    return out


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
    bold = _stage(work, _font(_BOLD), "bold")
    shadow = "shadowcolor=black@0.45:shadowx=2:shadowy=2"
    # 표지(대표 2026-10-27): 맨 위 가장 큰 글씨로 슬로건 "코디 저장소" → 영문 소제목 → 흰 박스 "○○ 모음.zip".
    # 감성 카피(title_ko)는 표지에서 빼고 캡션 첫 줄용으로 남긴다.
    cover = [
        f"drawtext=fontfile={bold}:textfile={_txt(work, 't_slogan.txt', SLOGAN)}:fontsize=104:fontcolor=white:"
        f"x=90:y=h*0.64:{shadow}",
        f"drawtext=fontfile={bold}:textfile={_txt(work, 't_en.txt', theme['title_en'])}:fontsize=34:fontcolor=white:"
        f"x=94:y=h*0.64+136:{shadow}",
        f"drawtext=fontfile={bold}:textfile={_txt(work, 't_zip.txt', theme['zip'])}:fontsize=40:fontcolor=black:"
        f"box=1:boxcolor=white@0.95:boxborderw=14:x=94:y=h*0.64+198",
    ]
    _segment(work, look_images[0], COVER_SEC, cover, "seg0.mp4")
    segs = ["seg0.mp4"]
    for i, img in enumerate(look_images, start=1):
        # 번호 스티커(대표 2026-10-27 ③안, "Look N" 대신) — 흰 박스에 굵은 "01", 표지 카피와 같은 자리.
        # "몇 번 코디가 마음에 드세요?" 댓글을 번호로 받기 좋다.
        draw = (f"drawtext=fontfile={bold}:textfile={_txt(work, f'look{i}.txt', f'{i:02d}')}:fontsize=80:"
                f"fontcolor=black:box=1:boxcolor=white@0.95:boxborderw=22:x=94:y=h*0.64+60")
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




def _guard(character_id: str, d: picks.Deps) -> None:
    coordi._ready(character_id)
    if not d.coupang.is_available():
        raise CollectionError("쿠팡 연결이 필요해요(키 없음).")
    if not io.get_muse_adapter().is_available():
        raise CollectionError("이미지 생성 키(WAVESPEED)가 없어요.")


def _register(kind: str, cid: str, d: picks.Deps, args: dict, n: int) -> dict:
    job_id = f"clj_{secrets.token_hex(5)}"
    with _LOCK:
        _JOBS[job_id] = {"id": job_id, "kind": kind, "collection_id": cid, "state": "queued", "step": "준비", "error": None,
                         "done_looks": 0, "n": n, "_deps": d, "_args": args}
    return public_job(_JOBS[job_id])


def _busy(character_id: str) -> dict | None:
    with _LOCK:
        for j in _JOBS.values():
            if j["state"] in ("queued", "running") and j["_args"]["character_id"] == character_id:
                return public_job(j)
    return None


def start_plan(character_id: str = "chaei", n: int = N_LOOKS, d: picks.Deps | None = None, mode: str = "theme") -> dict:
    """1단계(미리보기): 테마·장면·상품만 정한다(이미지 생성 없음). 결과는 ig_collections status=planned."""
    d = d or picks.Deps()
    _guard(character_id, d)
    if (j := _busy(character_id)):
        return j
    n = max(MIN_LOOKS, min(7, int(n or N_LOOKS)))
    cid = f"cl-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(3)}"
    d.rest("ig_collections", "POST", json_body=[{"id": cid, "character_id": character_id, "status": "planned"}],
           prefer="return=minimal")
    return _register("plan", cid, d, {"character_id": character_id, "n": n,
                                      "mode": "lookfirst" if mode == "lookfirst" else "theme"}, n)


def start_make(collection_id: str, d: picks.Deps | None = None) -> dict:
    """2단계: 미리보기에서 확인한 기획 그대로 이미지·영상을 만든다."""
    d = d or picks.Deps()
    rows = d.rest("ig_collections", "GET", params={"select": "*", "id": f"eq.{collection_id}"})
    if not rows:
        raise LookupError("컬렉션을 찾을 수 없어요.")
    row = rows[0]
    if row.get("status") != "planned" or not (row.get("theme") or {}).get("plan"):
        raise CollectionError("미리보기(기획)가 끝난 컬렉션만 만들 수 있어요.")
    _guard(row["character_id"], d)
    if (j := _busy(row["character_id"])):
        return j
    _patch(d, collection_id, {"status": "making"})
    return _register("make", collection_id, d, {"character_id": row["character_id"]}, len(row.get("looks") or []))


def start(character_id: str = "chaei", n: int = N_LOOKS, d: picks.Deps | None = None) -> dict:
    """호환: 기획 + 만들기를 한 번에(run 이 두 단계를 이어서 실행)."""
    j = start_plan(character_id, n, d)
    with _LOCK:
        _JOBS[j["id"]]["kind"] = "plan+make"
    return get_job(j["id"])


def _patch(d: picks.Deps, cid: str, fields: dict) -> None:
    d.rest("ig_collections", "PATCH", params={"id": f"eq.{cid}"}, prefer="return=minimal",
           json_body={**fields, "updated_at": datetime.now(timezone.utc).isoformat()})


_KEEP = ("id", "channel", "product_id", "name", "mall", "price", "image_url", "image_key", "link", "affiliate_link", "kind")


def _keep(c: dict) -> dict:
    return {k: c.get(k) for k in _KEEP}


def _scenes(character_id: str, looks_products: list[list[dict]], rng: random.Random, llm=None) -> list[dict]:
    """룩마다 A1 장면 기획 — 앞 룩들을 history 로 넘기고, 포즈·장소가 겹치면 다시(최대 SCENE_TRIES)."""
    refs = cs.confirmed_refs(character_id)
    hair_roles = sorted(r for r in refs if cs.role_category(r) == "hair")
    history = [h for h in io.list_outfits(character_id, io.HISTORY_N, include_hidden=True) if h.get("plan")]
    plans: list[dict] = []
    for prods in looks_products:
        summary = [{"kind": p.get("kind"), "desc": p.get("name") or ""} for p in prods]
        hist = [{"plan": x} for x in reversed(plans)] + history

        def fresh(pl: dict) -> bool:   # 사람 없는 플랫레이·디테일 컷은 컬렉션 룩으로 안 씀
            pose = P.POSES[pl["pose"]]
            if pose.get("person") is False or pose.get("cut") == "디테일":
                return False
            return all(pl["pose"] != x["pose"] and pl["location"] != x["location"] for x in plans)

        plan = None
        for _ in range(SCENE_TRIES):
            plan = P.plan_scene(character_id=character_id, products=summary, hair_roles=hair_roles,
                                history=hist, rng=rng, llm=llm)
            if fresh(plan):
                break
        else:  # 그래도 겹치면 규칙 후보 중 안 쓴 포즈·장소 조합으로 지정
            cand = P.candidates(weekday=datetime.now(P.KST).weekday(), products=summary, hair_roles=hair_roles,
                                history=hist, now=datetime.now(P.KST))
            free = [(loc, pose) for loc, pose in cand["pairs"]
                    if P.POSES[pose].get("person") is not False and P.POSES[pose].get("cut") != "디테일"
                    and all(pose != x["pose"] and loc != x["location"] for x in plans)]
            if free:
                loc, pose = rng.choice(free)
                plan = P.plan_scene(character_id=character_id, products=summary, hair_roles=hair_roles, history=hist,
                                    options={"location": loc, "pose": pose}, rng=rng, llm=llm)
        plans.append(plan)
    return plans


_SCENE_KEEP = ("pose", "pose_ko", "location", "location_ko", "face", "hair_role", "eyewear", "eyewear_ko", "season")


# ── 룩 먼저(스튜디오 룩북) 실험 — 대표 2026-10-28: "옷맵시·몸매가 안 드러나고 스타일리시하지 않다" ──────────
# 지금 방식(쿠팡에서 아이템 하나 → 나머지 채우기)은 '검색에 걸린 옷의 조합'이라 룩이 약하다. 스타일리스트처럼
# 완성 룩(색·실루엣·기장 균형)을 먼저 설계하고, 쿠팡에서 비슷한 게 없으면 그 룩은 버린다. 촬영은 흰 스튜디오 전신·눈높이.
_LOOKFIRST_SYSTEM = (
    "You are a top Korean fashion stylist for a hip early-20s virtual influencer with a tall, slim, well-proportioned "
    "figure (172 cm). Design N complete, genuinely stylish outfits worth saving on Instagram — like a lookbook from "
    "Musinsa or a Seoul street-style editorial. Rules: (1) each outfit has a clear silhouette idea that shows off her "
    "figure tastefully: e.g. cropped or fitted top + high-waist bottom, oversized outer + short/slim bottom, long boots "
    "with a mini, defined waist; never boxy-on-boxy or frumpy. (2) a coherent palette of max 3 colors (tonal or one "
    "accent), each outfit a different palette. (3) season-appropriate, on-trend now, never matronly or office-lady. "
    "(4) 3-4 items each: top/bottoms or dress, plus outerwear if the season needs it, plus shoes; items must be common "
    "enough to find on Coupang. Return ONE JSON object: "
    '{"concept": "<짧은 한글 컬렉션 이름, 10자 이내>", "title_en": "<UPPERCASE english, e.g. AUTUMN LOOKBOOK>", '
    '"zip": "<○○ 모음.zip>", "looks": [{"idea": "<한국어 한 줄: 실루엣·색 포인트>", "items": [{"kind": '
    '"top|bottoms|dress|outerwear|shoes|bag", "color_name": "<한글>", "hex": "#RRGGBB", "fit": "slim|regular|over|cropped", '
    '"length": "<짧게>", "material": "<한글>", "details": "<short English>", "queries": ["<쿠팡 검색어: 여성 + 색 + '
    '특징 + 종류>", "<다른 표현>"]}]}]}.'
)
LOOKFIRST_MIN_SCORE = 60   # 룩 먼저 방식은 '비슷한 게 없으면 버림' — 일반(55)보다 엄격
_CORE_KINDS = {"top", "bottoms", "dress", "outerwear"}


def design_looks(season: str, life: str, n: int, llm=None) -> dict:
    """Opus가 완성 룩 n개를 설계(아이템 명세 + 쿠팡 검색어)."""
    from services import music_lyrics
    llm = llm or (lambda s, u: music_lyrics._call(s, u, max_tokens=3000, task="insta_lookfirst",
                                                  model=picks.strong_model()))
    data = music_lyrics._extract_json(llm(_LOOKFIRST_SYSTEM, json.dumps({
        "N": n, "season": season, "life": life, "style_guide": SG.guide_text(season, life)}, ensure_ascii=False)))
    looks = []
    for lk in (data.get("looks") or [])[: n + 2]:
        items = []
        for it in lk.get("items") or []:
            if it.get("kind") in P.PRODUCT_KINDS and it.get("queries"):
                items.append({"kind": it["kind"], "color_name": str(it.get("color_name") or ""),
                              "hex": it.get("hex"), "fit": str(it.get("fit") or ""), "length": str(it.get("length") or ""),
                              "material": str(it.get("material") or ""), "details": str(it.get("details") or "")[:120],
                              "queries": [str(q)[:40] for q in it["queries"] if str(q).strip()][:2]})
        if any(i["kind"] in _CORE_KINDS for i in items):
            looks.append({"idea": str(lk.get("idea") or "")[:80], "items": items[:4]})
    if not looks:
        raise CollectionError("룩 설계를 받지 못했어요 — 다시 해 주세요.")
    return {"concept": str(data.get("concept") or "스튜디오 룩북")[:12],
            "title_en": str(data.get("title_en") or "LOOKBOOK")[:32].upper(),
            "zip": str(data.get("zip") or "룩북 모음.zip")[:20], "looks": looks}


def find_look(look: dict, d: picks.Deps, usage: dict, season: str, td: Path) -> list[dict] | None:
    """룩의 아이템마다 쿠팡 1등(엄격 점수). 옷(상·하의·원피스·아우터)이 하나라도 없으면 None(그 룩은 버림)."""
    got = []
    for spec in look["items"]:
        cands, notes = picks.gather(spec, d, usage)
        usage.setdefault("notes", []).extend(notes)
        kept, _ = picks.code_filter(cands, spec["kind"])
        scored, _ = picks.judge(spec, {"seasons": [season]}, kept, d, usage, td) if kept else ([], [])
        best = next((c for c in scored if c.get("score", 0) >= LOOKFIRST_MIN_SCORE), None)
        if best is None:
            if spec["kind"] in _CORE_KINDS:
                return None
            continue
        got.append({**best, "kind": spec["kind"]})
    return got if any(c["kind"] in _CORE_KINDS for c in got) else None


def _plan_lookfirst(job_id: str, d: picks.Deps, cid: str, args: dict, rng: random.Random) -> dict:
    usage: dict = {"mode": "lookfirst"}
    products: list[dict] = []
    try:
        season, life = _season(), coordi._life_today()
        n = args["n"]
        _set(job_id, step="스타일리스트처럼 완성 룩 설계 중")
        design = design_looks(season, life, n + SPARE_LOOKS, llm=args.get("look_llm"))
        outfits = []
        with tempfile.TemporaryDirectory() as td:
            for k, lk in enumerate(design["looks"]):
                if len(outfits) >= n + SPARE_LOOKS:
                    break
                _set(job_id, step=f"룩 {k + 1}/{len(design['looks'])} — 쿠팡에서 비슷한 옷 찾는 중")
                found = find_look(lk, d, usage, season, Path(td))
                if not found:
                    usage.setdefault("dropped", []).append(lk["idea"])
                    continue
                saved = _saved(found, d)
                for c, src in zip(saved, found):
                    c["kind"] = src["kind"]
                products += saved
                order = {"outerwear": 0, "dress": 1, "top": 2, "bottoms": 3, "shoes": 4, "bag": 5}
                saved.sort(key=lambda c: order.get(c["kind"], 9))
                outfits.append((lk, saved))
        if len(outfits) < MIN_LOOKS:
            raise CollectionError(f"쿠팡에서 설계대로의 룩을 {len(outfits)}개만 찾았어요 — 다시 해 주세요.")
        scene = {"pose": "studio_full_body", "pose_ko": P.POSES["studio_full_body"]["ko"], "location": "white_studio",
                 "location_ko": P.LOCATIONS["white_studio"]["ko"], "face": "full", "season": season}
        theme = {"kind": outfits[0][1][0]["kind"], "concept": design["concept"], "title_en": design["title_en"],
                 "title_ko": [design["concept"], outfits[0][0]["idea"][:14]], "zip": design["zip"], "queries": [],
                 "plan": {"mode": "lookfirst", "season": season}, "source": "lookfirst"}
        looks = [{"n": i + 1, "product": _keep(o[0]), "items": [_keep(c) for c in o[1:]], "idea": lk["idea"],
                  "scene": dict(scene), **({"spare": True} if i >= n else {})}
                 for i, (lk, o) in enumerate(outfits)]
        _patch(d, cid, {"theme": theme, "looks": looks, "base_items": [], "status": "planned", "usage": usage,
                        "cost_usd": round(picks.vision_cost_usd(d.meter), 4)})
        return {"theme": theme, "looks": looks}
    finally:
        picks.delete_images(products, d)
        for c in products:
            c["image_key"] = None


THEME_TRIES = 3   # 테마 상품이 모자라면 테마를 바꿔 다시(대표 2026-10-27: 실패하면 스스로 다시)


def broaden_queries(theme: dict) -> list[str]:
    """테마 상품이 모자랄 때 더 넓은 검색어 — 컨셉 그대로 / 종류 일반명. 브랜드는 안 붙인다."""
    concept = str(theme.get("concept") or "").replace("모음", "").strip()
    last = concept.split()[-1] if concept.split() else ""
    out = []   # 종류 일반명(여성 아우터)은 테마와 다른 옷이 섞여서 안 씀 — 컨셉 / 컨셉 마지막 단어만
    for q in (f"여성 {concept}", f"여성 {last}" if last and last != concept else ""):
        q = q.strip()
        if q and q != "여성" and q not in theme.get("queries", []) and q not in out:
            out.append(q)
    return out


def _variants_for(theme: dict, d: picks.Deps, usage: dict, n: int, rng: random.Random) -> list[dict]:
    """테마 상품 n개 — 모자라면 넓은 검색어로 한 번 더(브랜드 없이) 찾아 합친다."""
    raw = pick_variants(theme, d, usage, n, rng=rng)
    if len(raw) < n and not any("한도" in x for x in usage.get("notes") or []):
        extra = broaden_queries(theme)
        if extra:
            more = pick_variants({**theme, "queries": extra}, d, usage, n)
            seen = {(c["channel"], c["product_id"]) for c in raw}
            raw += [c for c in more if (c["channel"], c["product_id"]) not in seen][: n - len(raw)]
    return raw


def _plan(job_id: str, d: picks.Deps, cid: str, args: dict, llm, rng: random.Random) -> dict:
    """테마 → 상품(테마 N개 + 함께 입을 후보) → 룩별 코디·장면 → ig_collections(planned). 쿠팡 사본은 지운다.

    테마 상품이 3개 미만이면 넓은 검색어로 더 찾고, 그래도 모자라면 테마를 바꿔 최대 THEME_TRIES 번.
    """
    usage: dict = {}
    products: list[dict] = []
    try:
        season, life = _season(), coordi._life_today()
        avoid = _recent_concepts(d)
        theme, variants, tried = None, [], []
        for attempt in range(THEME_TRIES):
            _set(job_id, step="테마 정하는 중" if not attempt else f"상품이 부족해 다른 테마로 다시({attempt + 1}/{THEME_TRIES})")
            theme = plan_theme(season, life, avoid + tried, llm=llm, rng=rng)
            theme["plan"] = {"mode": "varied", "season": season}
            tried.append(theme["concept"])
            _set(job_id, step=f"「{theme['concept']}」 상품 고르는 중",
                 theme={k: theme[k] for k in ("concept", "title_ko", "zip")})
            raw = _variants_for(theme, d, usage, args["n"] + SPARE_LOOKS, rng)
            got = _saved(raw, d)
            products += got
            for c, src in zip(got, raw):
                c["scores"] = src.get("scores")
                c["kind"] = theme["kind"]
            if len(got) >= MIN_LOOKS:
                variants = got
                break
            if any("한도" in x for x in usage.get("notes") or []):
                raise CollectionError("쿠팡 검색 한도에 걸렸어요 — 1분쯤 뒤에 다시 기획해 주세요.")
        if len(variants) < MIN_LOOKS:
            raise CollectionError(f"테마 {len(tried)}개({', '.join(tried)})를 시도했지만 상품이 모자라요 — 잠시 뒤 다시 해 주세요.")
        usage["themes_tried"] = tried
        _set(job_id, step=f"「{theme['concept']}」에 어울리는 상의·아우터·신발 고르는 중")
        pools = pick_base(theme, d, usage, len(variants), season=season, llm=args.get("fill_llm"))
        saved_pools = []
        for pool in pools:
            got = _saved(pool["picks"], d)
            products += got
            for c, src in zip(got, pool["picks"]):
                c["kind"] = pool["kind"]
                c["scores"] = src.get("scores")   # 색 조합 짝짓기용(저장은 _keep 에서 빠짐)
            saved_pools.append(got)
        outfits = pair_outfits(variants, saved_pools)
        _set(job_id, step="룩마다 포즈·장소 정하는 중")
        plans = _scenes(args["character_id"], outfits, rng, llm=args.get("scene_llm"))
        main_n = min(args["n"], len(outfits))
        looks = [{"n": i + 1, "product": _keep(o[0]), "items": [_keep(c) for c in o[1:]],
                  "scene": {k: pl.get(k) for k in _SCENE_KEEP}, **({"spare": True} if i >= main_n else {})}
                 for i, (o, pl) in enumerate(zip(outfits, plans))]
        _patch(d, cid, {"theme": theme, "looks": looks, "base_items": [], "status": "planned", "usage": usage,
                        "cost_usd": round(picks.vision_cost_usd(d.meter), 4)})
        return {"theme": theme, "looks": looks}
    finally:
        picks.delete_images(products, d)
        for c in products:
            c["image_key"] = None


def _make(job_id: str, d: picks.Deps, cid: str, character_id: str, rng: random.Random) -> None:
    """기획(ig_collections) 그대로: 룩마다 A1 착장(그 룩의 코디·포즈·장소) → 영상."""
    row = d.rest("ig_collections", "GET", params={"select": "*", "id": f"eq.{cid}"})[0]
    theme = row["theme"]
    plan_looks = row.get("looks") or []
    all_items = []
    tmp = Path(tempfile.mkdtemp(prefix="insta_coll_"))
    cost = float(row.get("cost_usd") or 0)
    meter0 = picks.vision_cost_usd(d.meter)
    try:
        looks, imgs, skipped = [], [], []
        main = [x for x in plan_looks if not x.get("spare")]
        spares = [x for x in plan_looks if x.get("spare")]
        target = len(main)
        _set(job_id, n=target)
        queue = list(main)
        while queue and len(looks) < target:
            lk = queue.pop(0)
            i = lk["n"]
            _set(job_id, step=f"{i:02d} 만드는 중")
            outfit = [dict(lk["product"])] + [dict(c) for c in lk.get("items") or []]
            for c in outfit:
                c["image_key"] = None   # 기획 때 지웠으므로 원본 URL 에서 다시 받는다
            all_items += outfit
            items = [{"kind": c.get("kind"), "pick": c, "source": "coupang"} for c in outfit]
            coordi.ensure_images(items, d)
            sc = lk.get("scene") or {}
            opts = {k: v for k, v in {"pose": sc.get("pose"), "location": sc.get("location"), "face": sc.get("face"),
                                      "hair": sc.get("hair_role"), "styling_en": theme.get("styling_en")}.items() if v}
            try:   # 한 룩이 실패해도 나머지로 계속(대표 2026-10-27: 실패하면 스스로) — 4룩 이상이면 완성
                for scene_try in range(2):   # 1회 실패하면 장면(포즈·장소)을 AI에 맡겨 한 번 더
                    o = opts if scene_try == 0 else {k: v for k, v in opts.items() if k in ("hair", "styling_en")}
                    oj = io.start(character_id, coordi._cap_products(coordi._outfit_products(items)), o,
                                  remake_of=f"{cid}:{i}:{scene_try}:{secrets.token_hex(2)}")
                    io.run(oj["id"], rng=rng)
                    oj = io.get_job(oj["id"])
                    cost += oj.get("cost_usd") or 0.0
                    if oj["state"] == "done":
                        break
                    logger.warning("[insta-collection] %s %02d 시도 %d 실패: %s", cid, i, scene_try + 1,
                                   str(oj.get("error"))[:160])
                if oj["state"] != "done":
                    raise CollectionError(oj.get("error") or "생성 실패")
                out = io.get_outfit(oj["outfit_id"])
                path = io._download(io.public_url(out["image_key"]), tmp / f"look{i}.png")
                imgs.append(str(io.postprocess(path, tmp / f"p{i}.jpg").name))
            except Exception as e:  # noqa: BLE001
                logger.warning("[insta-collection] %s %02d 실패 → 건너뜀: %s", cid, i, str(e)[:200])
                skipped.append({"n": i, "error": str(e)[:160]})
                if spares:   # 예비 룩으로 대신
                    queue.append(spares.pop(0))
                continue
            looks.append({**lk, "n": len(looks) + 1, "plan_n": i, "outfit_id": oj["outfit_id"],
                          "image_key": out["image_key"], "processed_key": out.get("processed_key"),
                          "review": out.get("review")})
            _set(job_id, done_looks=len(looks))
            _patch(d, cid, {"looks": looks + queue})
        if len(looks) < min(MIN_LOOKS, target):
            raise CollectionError(f"룩 {len(plan_looks)}개 중 {len(looks)}개만 만들어졌어요 — " +
                                  "; ".join(f"{x['n']:02d}: {x['error']}" for x in skipped))
        _set(job_id, step="릴스 영상 만드는 중")
        video, cover = render_reel(tmp, imgs, theme)
        vkey, ckey = f"insta/collections/{cid}/reel.mp4", f"insta/collections/{cid}/cover.jpg"
        bucket, pub = r2_storage._character_bucket(), r2_storage._character_public_base()
        r2_storage.upload_image(str(tmp / video), vkey, bucket=bucket, public_base_url=pub, content_type="video/mp4")
        r2_storage.upload_image(str(tmp / cover), ckey, bucket=bucket, public_base_url=pub, content_type="image/jpeg")
        total = round(cost + picks.vision_cost_usd(d.meter) - meter0, 4)
        _patch(d, cid, {"looks": looks, "video_key": vkey, "cover_key": ckey, "status": "ok", "cost_usd": total,
                        **({"error": f"{len(skipped)}개 룩 건너뜀"} if skipped else {})})
        _set(job_id, cost_usd=total)
    finally:
        picks.delete_images(all_items, d)
        shutil.rmtree(tmp, ignore_errors=True)


def run(job_id: str, *, llm=None, rng: random.Random | None = None) -> None:
    """BackgroundTasks 진입점: kind=plan(미리보기) / make(만들기) / plan+make(한 번에)."""
    with _LOCK:
        j = _JOBS[job_id]
        j["state"] = "running"
        d, cid, args, kind = j["_deps"], j["collection_id"], dict(j["_args"]), j.get("kind", "plan+make")
    rng = rng or random.Random()
    try:
        if kind in ("plan", "plan+make"):
            if args.get("mode") == "lookfirst":
                _plan_lookfirst(job_id, d, cid, args, rng)
            else:
                _plan(job_id, d, cid, args, llm, rng)
        if kind in ("make", "plan+make"):
            if kind == "plan+make":
                _patch(d, cid, {"status": "making"})
            _make(job_id, d, cid, args["character_id"], rng)
        _set(job_id, state="done", step="완료")
    except Exception as e:  # noqa: BLE001
        msg = str(e)[:300]
        logger.warning("[insta-collection] %s 실패: %s", cid, msg)
        _set(job_id, state="failed", step="실패", error=msg)
        try:
            _patch(d, cid, {"status": "failed", "error": msg})
        except Exception:  # noqa: BLE001
            pass


def view(row: dict) -> dict:
    url = io.public_url
    return {**row, "video_url": url(row.get("video_key")), "cover_url": url(row.get("cover_key")),
            "looks": [{**lk, "image_url": url(lk.get("processed_key") or lk.get("image_key")),
                       "product_image": (lk.get("product") or {}).get("image_url")} for lk in (row.get("looks") or [])]}


# 서버 재시작(배포)으로 끊긴 작업 정리(2026-10-28: 아침에 누른 기획이 오후까지 '만드는 중').
# 잡은 메모리에만 있어서 재배포하면 사라지고 행은 making/빈 planned 로 남는다.
STALE_PLAN_MIN = 15     # 기획: 이 시간 넘게 테마가 비어 있으면
STALE_MAKE_MIN = 25     # 만들기: 이 시간 넘게 진행 기록(updated_at)이 없으면(룩 하나 ≤ 약 5분)
STALE_MSG = "서버가 다시 시작돼 작업이 중단됐어요 — 다시 해 주세요."


def _live(cid: str) -> bool:
    with _LOCK:
        return any(j.get("collection_id") == cid and j.get("state") in ("queued", "running") for j in _JOBS.values())


def _stale(row: dict, now: datetime) -> bool:
    status = row.get("status")
    plan_empty = status == "planned" and not (row.get("theme") or {}).get("plan")
    if not (plan_empty or status == "making") or _live(row["id"]):
        return False
    try:
        ts = datetime.fromisoformat(str(row.get("updated_at") or row.get("created_at")).replace("Z", "+00:00"))
    except ValueError:
        return False
    limit = STALE_PLAN_MIN if plan_empty else STALE_MAKE_MIN
    return (now - ts).total_seconds() > limit * 60


def list_collections(limit: int = 10, d: picks.Deps | None = None) -> list[dict]:
    d = d or picks.Deps()
    rows = d.rest("ig_collections", "GET", params={"select": "*", "order": "created_at.desc", "limit": str(limit)})
    now = datetime.now(timezone.utc)
    for r in rows:
        if _stale(r, now):
            try:
                _patch(d, r["id"], {"status": "failed", "error": STALE_MSG})
                r["status"], r["error"] = "failed", STALE_MSG
            except Exception as e:  # noqa: BLE001
                logger.warning("[insta-collection] 끊긴 작업 정리 실패 %s: %s", r.get("id"), str(e)[:120])
    return [view(r) for r in rows]
