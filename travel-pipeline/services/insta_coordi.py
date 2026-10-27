"""인스타 쇼핑 A2-3a — 내 상품으로 코디: 보세 상품 넣기 + (선택) AI 나머지 채우기 → 착장.

결정 2026-10-27:
- 보세몰(메인, 반자동): 대표가 사진 + 상품 링크를 넣는다. 링크는 저장·표시만 — 서버가 그 URL 에 접속하지 않는다.
- 쿠팡(보조, 자동): 넣은 아이템에 어울리는 빈 종류(하의·신발·가방 등)를 A2-2 픽 로직으로 채운다.
- 네이버 제외(약관). 쿠팡 상품 이미지는 착장 생성 완료/실패 후 R2 사본 삭제(Open API 약관 제5조).
- 기록: 룩(source=bose) → 상품(bose|coupang, 링크) → 착장(look_id) → 승인/반려·교체·내리기(ig_feedback).

모드: only = 넣은 상품만 입히기(A1 그대로) / fill = 빈 종류를 AI 가 정하고 쿠팡에서 고른 뒤 입히기.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from adapters import r2_storage
from services import character_measurements as cm
from services import character_studio as cs
from services import character_studio_gen as gen
from services import insta_outfit as io
from services import insta_outfit_plan as P
from services import insta_picks as picks
from services import insta_refs as refs
from services import insta_style_guide as SG

logger = logging.getLogger(__name__)

MAX_TOTAL = io.MAX_PRODUCTS     # 넣은 상품 + 채운 상품 합계(착장 참조 상한과 같게)
FILL_ORDER = ("bottoms", "top", "shoes", "bag", "outerwear")

# 쇼핑몰 도메인 → 이름(쇼핑몰 이름 칸을 비우면 자동 표시). 모르는 곳은 도메인 앞부분.
MALLS = {
    "musinsa.com": "무신사", "29cm.co.kr": "29CM", "wconcept.co.kr": "W컨셉", "zigzag.kr": "지그재그",
    "a-bly.com": "에이블리", "ably.co.kr": "에이블리", "brandi.co.kr": "브랜디", "hiver.co.kr": "하이버",
    "coupang.com": "쿠팡", "smartstore.naver.com": "스마트스토어", "kream.co.kr": "KREAM", "ssg.com": "SSG",
    "lotteon.com": "롯데온", "11st.co.kr": "11번가", "gmarket.co.kr": "G마켓", "kakao.com": "카카오",
}


class CoordiError(ValueError):
    """대표에게 그대로 보여줄 입력 오류(400)."""


# ── 링크·쇼핑몰 ──────────────────────────────────────────────────────────
def validate_link(url: str | None) -> str | None:
    """https:// 만 허용(형식 검사만, 접속하지 않음). 빈 값이면 None."""
    u = (url or "").strip()
    if not u:
        return None
    if len(u) > 500 or not re.match(r"^https://[^\s/$.?#][^\s]*$", u):
        raise CoordiError("상품 링크는 https:// 로 시작하는 주소만 넣을 수 있어요.")
    return u


def mall_from_link(url: str | None, mall: str | None = None) -> str | None:
    """쇼핑몰 이름 칸이 있으면 그대로, 비었으면 링크 도메인에서."""
    if (mall or "").strip():
        return mall.strip()[:40]
    if not url:
        return None
    host = (urlparse(url).hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    hit = next((name for dom, name in MALLS.items() if host == dom or host.endswith("." + dom)), None)
    if hit:
        return hit
    parts = host.split(".")
    return (parts[-3] if len(parts) >= 3 and parts[-2] in ("co", "or", "ne") else parts[0])[:40] or None


# ── 빈 종류 정하기 ────────────────────────────────────────────────────────
def missing_kinds(kinds: list[str], season: str) -> list[str]:
    """넣은 종류 기준으로 채울 종류(합계 MAX_TOTAL 이하). 원피스면 상·하의 없이 신발·가방(+가을·겨울 아우터)."""
    have = set(kinds)
    need: list[str] = []
    if "dress" not in have:
        if "top" not in have and "bottoms" not in have:
            need += ["top", "bottoms"]
        elif "top" not in have:
            need.append("top")
        elif "bottoms" not in have:
            need.append("bottoms")
    if "shoes" not in have:
        need.append("shoes")
    if "bag" not in have:
        need.append("bag")
    if season in ("autumn", "winter") and "outerwear" not in have:
        need.append("outerwear")
    room = max(0, MAX_TOTAL - len(kinds))
    need.sort(key=FILL_ORDER.index)
    return need[:room]


_FILL_SYSTEM = (
    "You style a Korean woman's everyday outfit. Given the items she already chose (kind + short description) and "
    "the season, design the MISSING items so the whole outfit is coherent: max 3 colors with at most 1 accent, "
    "matching the season and a daily situation. Follow the given style_guide strictly — quality, on-trend pieces a "
    "hip Korean woman in her early 20s would really post (youthful Seoul street vibe, never matronly); never the "
    "items in its avoid list. Return ONE JSON object: "
    '{"concept": "<짧은 한글 컨셉, 12자 이내>", "items": [{"kind": "...", "color_name": "<한글>", "hex": "#RRGGBB", '
    '"fit": "slim|regular|over", "length": "...", "material": "<한글>", "details": "<short English>", '
    '"queries": ["<쿠팡에서 찾을 한국어 검색어 — 여성, 색, 종류 포함>", "...", "..."]}]} — only the requested kinds.'
)
_FALLBACK = {  # AI 가 실패하면 무난한 기본(계절 무관 기본색)
    "top": ("아이보리", "#F2EDE3", "여성 아이보리 니트"), "bottoms": ("차콜", "#36454F", "여성 차콜 와이드 슬랙스"),
    "shoes": ("블랙", "#111111", "여성 블랙 로퍼"), "bag": ("블랙", "#111111", "여성 블랙 숄더백"),
    "outerwear": ("베이지", "#D2B48C", "여성 베이지 트렌치코트"),
}


def _life_today() -> str:
    return P.WEEKDAYS[datetime.now(P.KST).weekday()]["life"]


def fill_specs(bose: list[dict], need: list[str], season: str, llm: Callable | None = None,
               guide: str | None = None) -> tuple[str, list[dict]]:
    """빈 종류의 아이템 명세(검색어 포함). → (컨셉, items). AI 실패·누락 종류는 기본 명세로.
    guide: 스타일 가이드(없으면 계절·오늘 생활 기준 기본 가이드)."""
    from services import music_lyrics
    llm = llm or (lambda s, u: music_lyrics._call(s, u, max_tokens=900, task="insta_fill"))
    concept, items = "내 상품 코디", []
    try:
        data = music_lyrics._extract_json(llm(_FILL_SYSTEM, json.dumps({
            "season": season, "have": [{"kind": p["kind"], "desc": p.get("desc") or p.get("name") or ""} for p in bose],
            "need": need, "style_guide": guide or SG.guide_text(season, _life_today())}, ensure_ascii=False)))
        norm = refs.normalize_analysis({"looks": [{"concept": data.get("concept") or concept, "items": data.get("items") or []}]})
        if norm["looks"]:
            concept = norm["looks"][0]["concept"]
            items = [it for it in norm["looks"][0]["items"] if it["kind"] in need]
    except Exception as e:  # noqa: BLE001
        logger.warning("[insta-coordi] 채우기 명세 AI 실패 → 기본: %s", str(e)[:160])
    got = {it["kind"] for it in items}
    for k in need:
        if k not in got:
            color, hexv, q = _FALLBACK[k]
            items.append({"kind": k, "color_name": color, "hex": hexv, "fit": "regular", "length": "", "material": "",
                          "details": "", "queries": [q]})
    items.sort(key=lambda it: need.index(it["kind"]))
    return concept, items


# ── 저장 ─────────────────────────────────────────────────────────────────
def save_bose(products: list[dict], d: picks.Deps) -> list[dict]:
    """대표가 넣은 보세 상품 → ig_products(channel=bose, 이미지는 대표 업로드라 보관). → 저장 행(+입력 정보)."""
    rows = []
    for p in products:
        pid = hashlib.sha1(p["key"].encode()).hexdigest()[:16]
        rows.append({"channel": "bose", "product_id": pid, "name": (p.get("name") or p.get("desc") or
                     P.PRODUCT_KINDS[p["kind"]][0])[:300], "mall": p.get("mall"), "category": p["kind"],
                     "image_key": p["key"], "image_url": io.public_url(p["key"]), "link": p.get("link"),
                     "raw": {"desc": p.get("desc") or "", "revealing": bool(p.get("revealing"))},
                     "updated_at": datetime.now(timezone.utc).isoformat()})
    saved = d.rest("ig_products", "POST", params={"on_conflict": "channel,product_id"}, json_body=rows,
                   prefer="resolution=merge-duplicates,return=representation")
    by_pid = {r["product_id"]: r for r in saved}
    return [{**p, "row": by_pid.get(r["product_id"], r)} for p, r in zip(products, rows)]


def _clean_bose(products: list[dict]) -> list[dict]:
    if not 1 <= len(products or []) <= MAX_TOTAL:
        raise CoordiError(f"상품을 1~{MAX_TOTAL}개 넣어 주세요.")
    out = []
    for p in products:
        key, kind = str(p.get("key") or ""), str(p.get("kind") or "")
        if not key.startswith("insta/products/upload/"):
            raise CoordiError("상품 사진은 이 화면에서 올린 것만 쓸 수 있어요.")
        if kind not in P.PRODUCT_KINDS:
            raise CoordiError("상품마다 종류를 골라 주세요.")
        link = validate_link(p.get("link"))
        out.append({"key": key, "kind": kind, "desc": str(p.get("desc") or "")[:160], "revealing": bool(p.get("revealing")),
                    "link": link, "mall": mall_from_link(link, p.get("mall")), "name": str(p.get("name") or "")[:120] or None})
    return out


def _ready(character_id: str) -> dict:
    char = cs.get_character(character_id)
    refs_ = cs.confirmed_refs(char["id"])
    if not (refs_.get(gen.FACE_ROLE) and refs_.get(gen.BODY_ROLE)):
        raise CoordiError("캐릭터가 '준비 완료'가 아니에요 — 스튜디오에서 얼굴·체형을 확정해 주세요.")
    if not cm.saved(char):
        raise CoordiError("치수를 먼저 입력해 주세요.")
    return char


# ── 잡 ───────────────────────────────────────────────────────────────────
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


def public_job(j: dict) -> dict:
    return {k: v for k, v in j.items() if not k.startswith("_")}


def get_job(job_id: str) -> dict:
    with _LOCK:
        if job_id not in _JOBS:
            raise LookupError("작업을 찾을 수 없어요(서버 재시작 — 최근 착장에서 확인해 주세요).")
        return public_job(_JOBS[job_id])


def _set(job_id: str, **kw) -> None:
    with _LOCK:
        _JOBS[job_id].update(kw)


def start(character_id: str, products: list[dict], mode: str = "only", options: dict | None = None,
          d: picks.Deps | None = None) -> dict:
    """검증 → 룩 행(source=bose) → 잡 등록. 실행은 run."""
    if mode not in ("only", "fill"):
        raise CoordiError("알 수 없는 방식이에요.")
    d = d or picks.Deps()
    char = _ready(character_id)
    bose = _clean_bose(products)
    if mode == "fill" and not d.coupang.is_available():
        raise CoordiError("쿠팡 연결이 필요해요 — '이것만 입히기'는 지금도 할 수 있어요.")
    sig = json.dumps([char["id"], mode, [(p["key"], p["kind"]) for p in bose], options or {}], sort_keys=True)
    with _LOCK:
        for j in _JOBS.values():
            if j.get("_sig") == sig and j["state"] in ("queued", "running"):
                return public_job(j)
    look_id = f"lk-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(3)}"
    d.rest("ig_looks", "POST", json_body=[{"id": look_id, "source": "bose", "concept": "내 상품 코디", "spec": {},
                                            "status": "picking"}], prefer="return=minimal")
    job_id = f"cj_{secrets.token_hex(5)}"
    with _LOCK:
        _JOBS[job_id] = {"id": job_id, "look_id": look_id, "outfit_id": None, "mode": mode, "state": "queued",
                         "step": "준비", "error": None, "cost": None, "_sig": sig, "_deps": d,
                         "_args": {"character_id": char["id"], "bose": bose, "options": options or {}}}
    return public_job(_JOBS[job_id])


def _fill(bose: list[dict], season: str, d: picks.Deps, job_id: str, llm: Callable | None,
          need: list[str] | None = None, guide: str | None = None) -> tuple[str, list[dict], dict, list[str]]:
    """빈 종류 → 명세 → 쿠팡 픽 → 저장. → (컨셉, 아이템들, 조합, 메모). need 를 주면 그 종류만."""
    need = missing_kinds([p["kind"] for p in bose], season) if need is None else need
    if not need:
        return "내 상품 코디", [], {"ok": True, "swaps": []}, ["더 채울 종류가 없어요"]
    _set(job_id, step="채울 종류 정하는 중")
    concept, specs = fill_specs(bose, need, season, llm, guide=guide)
    _set(job_id, step="쿠팡에서 고르는 중")
    usage: dict = {}
    items, notes = [], []
    quota_hit = False
    look = {"seasons": [season]}
    with tempfile.TemporaryDirectory() as td:
        for spec in specs:
            cands, n1 = picks.gather(spec, d, usage)
            quota_hit = quota_hit or any("한도" in n for n in n1)
            kept, why = picks.code_filter(cands, spec["kind"])
            scored, n2 = picks.judge(spec, look, kept, d, usage, Path(td)) if kept else ([], [])
            pick, backups, miss = picks.choose(scored)
            items.append({"kind": spec["kind"], "spec": spec, "pick": pick, "backups": backups, "source": "coupang",
                          "candidates": len(cands), "filtered": why, "notes": n1 + n2 + ([miss] if miss else [])})
    if quota_hit and not any(it["pick"] for it in items):
        raise CoordiError("쿠팡 검색 한도에 걸렸어요. 잠시 후 다시 눌러 주세요.")
    combo = picks.fix_combo(items, lambda c: (c.get("scores") or {}).get("hex"))
    chosen = [c for it in items for c in ([it["pick"]] if it["pick"] else []) + it["backups"]]
    saved = picks.save_products(chosen, d)
    for it in items:
        def ref_of(c):
            row = saved.get((c["channel"], c["product_id"])) or {}
            return {**picks._public(c), "id": row.get("id"), "image_key": row.get("image_key"),
                    "affiliate_link": row.get("affiliate_link")}
        it["pick"] = ref_of(it["pick"]) if it["pick"] else None
        it["backups"] = [ref_of(c) for c in it["backups"]]
        if not it["pick"]:
            notes.append(f"{P.PRODUCT_KINDS[it['kind']][0]}: 맞는 쿠팡 상품을 못 찾았어요")
    return concept, items, {**combo, "usage": usage}, notes


def _outfit_products(items: list[dict]) -> list[dict]:
    """룩 아이템 → 착장 입력(A1 형식 + 출처·링크·쇼핑몰)."""
    out = []
    for it in items:
        c = it.get("pick")
        if not c or not c.get("image_key"):
            continue
        out.append({"key": c["image_key"], "kind": it["kind"], "desc": (c.get("raw") or {}).get("desc") or c.get("name") or "",
                    "revealing": bool((c.get("raw") or {}).get("revealing")), "source": it.get("source"),
                    "link": c.get("affiliate_link") or c.get("link"), "mall": c.get("mall"), "name": c.get("name"),
                    "product_row_id": c.get("id")})
    return out


def ensure_images(items: list[dict], d: picks.Deps) -> None:
    """착장 직전: 이미지 사본이 지워진 쿠팡 1등(교체 후 다시 만들기 등)은 원본 URL 에서 다시 받아 임시 보관."""
    with tempfile.TemporaryDirectory() as td:
        for it in items:
            c = it.get("pick")
            if not c or c.get("channel") != "coupang" or c.get("image_key") or not c.get("image_url"):
                continue
            safe = re.sub(r"[^A-Za-z0-9_-]", "", str(c["product_id"]))[:60]
            src = d.download(c["image_url"], Path(td) / f"{safe}.img")
            jpg = picks._to_jpeg(src, Path(td) / f"{safe}.jpg")
            key = f"insta/products/coupang/{safe}.jpg"
            r2_storage.upload_image(str(jpg), key, bucket=r2_storage._character_bucket(),
                                    public_base_url=r2_storage._character_public_base(), content_type="image/jpeg")
            c["image_key"] = key
            if c.get("id") is not None:
                d.rest("ig_products", "PATCH", params={"id": f"eq.{c['id']}"}, prefer="return=minimal",
                       json_body={"image_key": key, "image_deleted_at": None,
                                  "updated_at": datetime.now(timezone.utc).isoformat()})


def run(job_id: str, *, llm: Callable | None = None, rng=None) -> None:
    """BackgroundTasks 진입점: (채우기) → 착장(A1) → 쿠팡 이미지 삭제(성공·실패 모두)."""
    with _LOCK:
        j = _JOBS[job_id]
        j["state"] = "running"
        d, look_id, mode, args = j["_deps"], j["look_id"], j["mode"], dict(j["_args"])
    items: list[dict] = []
    try:
        season = P.season_of(datetime.now(P.KST).date())
        _set(job_id, step="내 상품 저장 중")
        bose = save_bose(args["bose"], d)
        items = [{"kind": p["kind"], "source": "bose", "pick": {**p["row"], "raw": p["row"].get("raw") or {}},
                  "backups": [], "notes": []} for p in bose]
        concept, combo, notes = "내 상품 코디", None, []
        if mode == "fill":
            concept, filled, combo, notes = _fill(args["bose"], season, d, job_id, llm)
            items += filled
        for i, it in enumerate(items):
            it["index"] = i
        d.rest("ig_looks", "PATCH", params={"id": f"eq.{look_id}"}, prefer="return=minimal",
               json_body={"concept": concept, "items": items, "combo": combo, "status": "picked",
                          "usage": {**((combo or {}).get("usage") or {}), "vision_usd": picks.vision_cost_usd(d.meter)},
                          "error": "; ".join(notes) or None, "updated_at": datetime.now(timezone.utc).isoformat()})
        _set(job_id, step="입히는 중")
        ensure_images(items, d)
        oj = io.start(args["character_id"], _outfit_products(items), args["options"], look_id=look_id,
                      remake_of=f"{look_id}:{secrets.token_hex(2)}")
        _set(job_id, outfit_id=oj["outfit_id"])
        io.run(oj["id"], rng=rng)
        oj = io.get_job(oj["id"])
        cost = cost_summary(d, oj.get("cost_usd") or 0.0)
        _set(job_id, state="done" if oj["state"] == "done" else "failed", step="완료" if oj["state"] == "done" else "실패",
             error=oj.get("error"), cost=cost, notes=notes)
    except Exception as e:  # noqa: BLE001
        msg = str(e)[:300]
        logger.warning("[insta-coordi] %s 실패: %s", look_id, msg)
        _set(job_id, state="failed", step="실패", error=msg, cost=cost_summary(d, 0.0))
        try:
            d.rest("ig_looks", "PATCH", params={"id": f"eq.{look_id}"}, prefer="return=minimal",
                   json_body={"status": "failed", "error": msg})
        except Exception:  # noqa: BLE001
            pass
    finally:
        # 쿠팡 이미지는 쓰고 지운다(생성 완료·실패 모두). 화면은 원본 URL(image_url)로 다시 보여 준다.
        gone = picks.delete_images([c for it in items for c in ([it["pick"]] if it.get("pick") else []) + it.get("backups", [])], d)
        if gone:
            try:
                d.rest("ig_looks", "PATCH", params={"id": f"eq.{look_id}"}, prefer="return=minimal", json_body={"items": items})
            except Exception:  # noqa: BLE001
                pass


def cost_summary(d: picks.Deps, image_usd: float) -> dict:
    krw_rate = float(os.getenv("MUSIC_KRW_PER_USD") or 1400)
    vision = picks.vision_cost_usd(d.meter)
    usd = round(vision + float(image_usd or 0), 4)
    return {"vision_usd": vision, "image_usd": round(float(image_usd or 0), 4), "usd": usd, "krw": round(usd * krw_rate)}


def remake(outfit_id: str, d: picks.Deps | None = None) -> dict:
    """같은 룩(교체 반영), 새 장면으로 다시 입히기 — 채우기·픽은 다시 하지 않는다."""
    d = d or picks.Deps()
    row = io.get_outfit(outfit_id)
    if not row.get("look_id"):
        raise CoordiError("상품 기록이 없는 착장이에요 — '다시 만들기'를 써 주세요.")
    looks = d.rest("ig_looks", "GET", params={"select": "*", "id": f"eq.{row['look_id']}"})
    if not looks:
        raise LookupError("룩이 없어요")
    items = looks[0].get("items") or []
    job_id = f"cj_{secrets.token_hex(5)}"
    with _LOCK:
        _JOBS[job_id] = {"id": job_id, "look_id": row["look_id"], "outfit_id": None, "mode": "remake", "state": "queued",
                         "step": "준비", "error": None, "cost": None, "_deps": d,
                         "_args": {"character_id": row["character_id"], "items": items, "options": {}}}
    return public_job(_JOBS[job_id])


def run_remake(job_id: str, *, rng=None) -> None:
    with _LOCK:
        j = _JOBS[job_id]
        j["state"] = "running"
        d, look_id, args = j["_deps"], j["look_id"], dict(j["_args"])
    items = args["items"]
    try:
        _set(job_id, step="입히는 중")
        ensure_images(items, d)
        oj = io.start(args["character_id"], _outfit_products(items), {}, look_id=look_id,
                      remake_of=f"{look_id}:{secrets.token_hex(2)}")
        _set(job_id, outfit_id=oj["outfit_id"])
        io.run(oj["id"], rng=rng)
        oj = io.get_job(oj["id"])
        _set(job_id, state="done" if oj["state"] == "done" else "failed", step="완료", error=oj.get("error"),
             cost=cost_summary(d, oj.get("cost_usd") or 0.0))
    except Exception as e:  # noqa: BLE001
        _set(job_id, state="failed", step="실패", error=str(e)[:300])
    finally:
        picks.delete_images([c for it in items for c in ([it["pick"]] if it.get("pick") else []) + it.get("backups", [])], d)


# ── 오늘의 코디 찾기(완전 자동, 2026-10-27 대표: "반자동 아님") ──────────────
# 유튜브 레퍼런스(분석 완료·참고 가능, 조회수 순) → 룩 1벌 쿠팡 픽(A2-2) → 착장(A1) → 쿠팡 이미지 삭제.
# 대표 입력 없음. 스케줄 자동 실행(가동 토글)은 이 함수를 그대로 부르면 된다.
_AUTO_KIND_ORDER = ["dress", "top", "bottoms", "outerwear", "shoes", "bag", "accessory"]


def _cap_products(products: list[dict]) -> list[dict]:
    """착장 입력은 최대 4개(A1) — 옷(원피스·상의·하의·아우터) → 신발 → 가방 → 소품 순으로 남긴다."""
    rank = {k: i for i, k in enumerate(_AUTO_KIND_ORDER)}
    return sorted(products, key=lambda p: rank.get(p.get("kind"), len(rank)))[: io.MAX_PRODUCTS]


def _auto_need(kinds: list[str], season: str) -> list[str]:
    """자동 코디 빈칸: 레퍼런스 룩에서 못 고른 종류. 가을·겨울엔 아우터를 신발·가방보다 먼저(대표: 가을 코디)."""
    have = set(kinds)
    order: list[str] = []
    if "dress" not in have:
        order += [k for k in ("top", "bottoms") if k not in have]
    if season in ("autumn", "winter") and "outerwear" not in have:
        order.append("outerwear")
    order += [k for k in ("shoes", "bag") if k not in have]
    return order[: max(0, MAX_TOTAL - len(have))]


def _best_look(looks: list[dict], season: str) -> int:
    """레퍼런스 안 여러 룩 중: 이번 계절에 맞고 아이템이 많은 룩(코디가 꽉 찬 룩)."""
    def rank(i: int):
        lk = looks[i]
        seasons = lk.get("seasons") or [season]
        return (season in seasons, len(lk.get("items") or []))
    return max(range(len(looks)), key=rank)


def start_auto(character_id: str = "chaei", d: picks.Deps | None = None) -> dict:
    """다음 레퍼런스 룩으로 자동 코디 잡 등록(실행은 run_auto). 같은 캐릭터 자동 잡이 돌고 있으면 그 잡."""
    d = d or picks.Deps()
    char = _ready(character_id)
    if not d.coupang.is_available():
        raise CoordiError("쿠팡 연결이 필요해요(키 없음).")
    with _LOCK:
        for j in _JOBS.values():
            if j.get("mode") == "auto" and j["state"] in ("queued", "running") and j["_args"]["character_id"] == char["id"]:
                return public_job(j)
    picks.sweep_images(d)
    ref = picks.next_ref(d)
    looks = ((ref or {}).get("analysis") or {}).get("looks") or []
    season = P.season_of(datetime.now(P.KST).date())
    if not ref or not looks:
        # 쓸 레퍼런스가 없으면 스타일 가이드 공식으로 코디를 통째로 설계(완전 자동 — 멈추지 않게)
        f = SG.pick_formula(season, _life_today())
        look_id = f"lk-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(3)}"
        d.rest("ig_looks", "POST", json_body=[{"id": look_id, "source": "reference", "concept": f["name"],
                                                "spec": {"guide": f["name"], "hint": f["hint"]}, "status": "picking"}],
               prefer="return=minimal")
        job_id = f"cj_{secrets.token_hex(5)}"
        with _LOCK:
            _JOBS[job_id] = {"id": job_id, "look_id": look_id, "outfit_id": None, "mode": "auto", "state": "queued",
                             "step": "준비", "error": None, "cost": None, "concept": f["name"], "ref": None, "_deps": d,
                             "_args": {"character_id": char["id"], "guide": f}}
        return public_job(_JOBS[job_id])
    idx = _best_look(looks, season)
    look_id = f"lk-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(3)}"
    d.rest("ig_looks", "POST", json_body=[{"id": look_id, "ref_video_id": ref["video_id"], "look_index": idx,
                                            "concept": looks[idx].get("concept"), "spec": looks[idx], "source": "reference",
                                            "status": "picking"}], prefer="return=minimal")
    job_id = f"cj_{secrets.token_hex(5)}"
    with _LOCK:
        _JOBS[job_id] = {"id": job_id, "look_id": look_id, "outfit_id": None, "mode": "auto", "state": "queued",
                         "step": "준비", "error": None, "cost": None, "concept": looks[idx].get("concept"),
                         "ref": ref["video_id"], "_deps": d,
                         "_args": {"character_id": char["id"], "ref": ref, "look_index": idx}}
    return public_job(_JOBS[job_id])


def run_auto(job_id: str, *, rng=None) -> None:
    """BackgroundTasks 진입점: 쿠팡 픽 → 착장 → 쿠팡 이미지 삭제(성공·실패 모두)."""
    with _LOCK:
        j = _JOBS[job_id]
        j["state"] = "running"
        d, look_id, args = j["_deps"], j["look_id"], dict(j["_args"])
    items: list[dict] = []
    try:
        season = P.season_of(datetime.now(P.KST).date())
        if args.get("guide"):
            f = args["guide"]
            _set(job_id, step=f"가이드 코디 「{f['name']}」 설계 중")
            guide = SG.guide_text(season, _life_today()) + f"\n- 이번 코디 공식: {f['name']} — {f['hint']}"
            concept, filled, combo, notes = _fill([], season, d, job_id, None, need=list(f["kinds"]), guide=guide)
            items = [it for it in filled if it.get("pick")]
            if not items:
                raise CoordiError("가이드 코디에 맞는 쿠팡 상품을 못 찾았어요 — 잠시 후 다시 눌러 주세요.")
            d.rest("ig_looks", "PATCH", params={"id": f"eq.{look_id}"}, prefer="return=minimal",
                   json_body={"concept": concept or f["name"], "combo": combo, "status": "picked"})
        else:
            _set(job_id, step="레퍼런스 룩에 맞는 쿠팡 상품 고르는 중")
            look = picks.pick_look(look_id, args["ref"], args.get("look_index", 0), d)
            items = look.get("items") or []
            for it in items:
                it["source"] = "coupang"
            notes = [f"{P.PRODUCT_KINDS.get(it['kind'], [it['kind']])[0]}: 맞는 쿠팡 상품을 못 찾았어요"
                     for it in items if not it.get("pick")]
            if look.get("status") != "picked":
                raise CoordiError("맞는 쿠팡 상품을 하나도 못 찾았어요 — 다시 누르면 다음 레퍼런스로 해요.")
            # 레퍼런스 룩이 덜 찼으면(상의만 등) 빈 종류를 가이드대로 채워 완성 — 가을·겨울엔 아우터 우선
            picked = [it for it in items if it.get("pick")]
            need = _auto_need([it["kind"] for it in picked], season)
            if need:
                have = [{"kind": it["kind"], "desc": (it["pick"].get("name") or "")} for it in picked]
                _, filled, _, n3 = _fill(have, season, d, job_id, None, need=need)
                items = picked + [it for it in filled if it.get("pick")]
                notes += n3
        for i, it in enumerate(items):
            it["index"] = i
        d.rest("ig_looks", "PATCH", params={"id": f"eq.{look_id}"}, prefer="return=minimal", json_body={"items": items})
        _set(job_id, step="입히는 중")
        ensure_images(items, d)
        products = _outfit_products(items)
        capped = _cap_products(products)
        if len(capped) < len(products):
            notes.append(f"착장엔 {len(capped)}개까지만 입혀요({len(products) - len(capped)}개 제외)")
        oj = io.start(args["character_id"], capped, {}, look_id=look_id, remake_of=f"{look_id}:{secrets.token_hex(2)}")
        _set(job_id, outfit_id=oj["outfit_id"])
        io.run(oj["id"], rng=rng)
        oj = io.get_job(oj["id"])
        _set(job_id, state="done" if oj["state"] == "done" else "failed", step="완료" if oj["state"] == "done" else "실패",
             error=oj.get("error"), cost=cost_summary(d, oj.get("cost_usd") or 0.0), notes=notes)
    except Exception as e:  # noqa: BLE001
        msg = str(e)[:300]
        logger.warning("[insta-coordi] 자동 %s 실패: %s", look_id, msg)
        _set(job_id, state="failed", step="실패", error=msg, cost=cost_summary(d, 0.0))
        try:
            d.rest("ig_looks", "PATCH", params={"id": f"eq.{look_id}"}, prefer="return=minimal",
                   json_body={"status": "failed", "error": msg})
        except Exception:  # noqa: BLE001
            pass
    finally:
        gone = picks.delete_images([c for it in items for c in ([it["pick"]] if it.get("pick") else []) + it.get("backups", [])], d)
        if gone:
            try:
                d.rest("ig_looks", "PATCH", params={"id": f"eq.{look_id}"}, prefer="return=minimal", json_body={"items": items})
            except Exception:  # noqa: BLE001
                pass


# ── 승인·반려·내리기 ─────────────────────────────────────────────────────
def decide(outfit_id: str, decision: str, reason: str | None = None, d: picks.Deps | None = None) -> dict:
    """대표 승인(이 코디 좋아요)/반려(다른 코디). 착장·룩 상태 + ig_feedback."""
    if decision not in ("approved", "rejected"):
        raise CoordiError("승인 또는 반려만 할 수 있어요.")
    d = d or picks.Deps()
    row = io.get_outfit(outfit_id)
    now = datetime.now(timezone.utc).isoformat()
    io._patch(outfit_id, {"decision": decision, "decided_at": now})
    if row.get("look_id"):
        d.rest("ig_looks", "PATCH", params={"id": f"eq.{row['look_id']}"}, prefer="return=minimal",
               json_body={"status": decision, "updated_at": now})
    picks.record_feedback(d, "approve" if decision == "approved" else "reject", outfit_id=outfit_id,
                          look_id=row.get("look_id"), reason=(reason or "")[:200] or None)
    return {**row, "decision": decision, "decided_at": now}


def hide_outfit(outfit_id: str, reason: str, d: picks.Deps | None = None) -> dict:
    """내리기 — 숨김 + 사유. B단계 업로드 대상에서 빠지고, 이미 올라간 게시물은 B단계가 이 상태로 삭제 API 를 부른다."""
    reason = (reason or "").strip()
    if not reason:
        raise CoordiError("내리는 이유를 적어 주세요(예: 판매자 요청).")
    d = d or picks.Deps()
    row = io.get_outfit(outfit_id)
    now = datetime.now(timezone.utc).isoformat()
    io._patch(outfit_id, {"hidden_at": now, "hidden_reason": reason[:200]})
    picks.record_feedback(d, "hide", outfit_id=outfit_id, look_id=row.get("look_id"), reason=reason[:200])
    return {**row, "hidden_at": now, "hidden_reason": reason[:200]}


def hide_product(product_row_id: int, reason: str, d: picks.Deps | None = None) -> dict:
    reason = (reason or "").strip()
    if not reason:
        raise CoordiError("내리는 이유를 적어 주세요(예: 판매자 요청).")
    d = d or picks.Deps()
    now = datetime.now(timezone.utc).isoformat()
    d.rest("ig_products", "PATCH", params={"id": f"eq.{int(product_row_id)}"}, prefer="return=minimal",
           json_body={"hidden_at": now, "hidden_reason": reason[:200]})
    picks.record_feedback(d, "hide", product_id=int(product_row_id), reason=reason[:200])
    return {"id": int(product_row_id), "hidden_at": now, "hidden_reason": reason[:200]}


# ── 화면용 ───────────────────────────────────────────────────────────────
def attach_looks(rows: list[dict], d: picks.Deps | None = None) -> list[dict]:
    """착장 목록에 룩(상품·출처·링크·교체 후보·내림 상태)을 붙인다. 쿠팡 이미지는 원본 URL 로(저장 안 함)."""
    d = d or picks.Deps()
    ids = sorted({r["look_id"] for r in rows if r.get("look_id")})
    looks: dict[str, dict] = {}
    if ids:
        try:
            got = d.rest("ig_looks", "GET", params={"select": "*", "id": f"in.({','.join(ids)})"})
            cands = [c for lk in got for it in lk.get("items") or []
                     for c in ([it["pick"]] if it.get("pick") else []) + (it.get("backups") or [])]
            pids = sorted({int(c["id"]) for c in cands if isinstance(c.get("id"), int)})
            hidden = {}
            if pids:
                hidden = {p["id"]: p for p in d.rest("ig_products", "GET", params={
                    "select": "id,hidden_at,hidden_reason", "id": f"in.({','.join(map(str, pids))})"}) if p.get("hidden_at")}
            for c in cands:
                c["image"] = io.public_url(c.get("image_key")) if c.get("channel") == "bose" else c.get("image_url")
                h = hidden.get(c.get("id"))
                c["hidden_at"], c["hidden_reason"] = (h["hidden_at"], h.get("hidden_reason")) if h else (None, None)
            looks = {lk["id"]: lk for lk in got}
        except Exception as e:  # noqa: BLE001
            logger.warning("[insta-coordi] 룩 붙이기 실패: %s", str(e)[:160])
    return [{**io.view(r), "look": looks.get(r.get("look_id"))} for r in rows]


def stats(d: picks.Deps | None = None) -> dict:
    """이번 달 픽 승인율·합성 승인율(교체·재생성 없이 승인)·착장당 평균 비용."""
    d = d or picks.Deps()
    month = datetime.now(P.KST).strftime("%Y-%m-01")
    fb = d.rest("ig_feedback", "GET", params={"select": "event,look_id,outfit_id", "created_at": f"gte.{month}", "limit": "1000"})
    outfits = io._rest("GET", params={"select": "id,look_id,decision,attempts,cost_usd", "created_at": f"gte.{month}",
                                       "limit": "1000"})
    decided = [o for o in outfits if o.get("decision")]
    approved = [o for o in decided if o["decision"] == "approved"]
    swapped_looks = {f["look_id"] for f in fb if f["event"] == "swap"}
    clean = [o for o in approved if o.get("look_id") not in swapped_looks and int(o.get("attempts") or 1) <= 1]
    looks_decided = {o["look_id"] for o in decided if o.get("look_id")}
    looks_ok = {o["look_id"] for o in approved if o.get("look_id") and o["look_id"] not in swapped_looks}
    costs = [float(o.get("cost_usd") or 0) for o in outfits if o.get("cost_usd")]
    return {
        "pick_approval": round(len(looks_ok) / len(looks_decided), 3) if looks_decided else None,
        "compose_approval": round(len(clean) / len(decided), 3) if decided else None,
        "avg_cost_usd": round(sum(costs) / len(costs), 4) if costs else None,
        "decided": len(decided),
    }
