"""인스타 쇼핑 A2-2 — 레퍼런스 룩 → 쿠팡·네이버 상품 픽.

룩 명세서(ig_refs.analysis.looks[i])의 아이템마다:
  1) 후보 모으기: 검색어 2~3개 × (쿠팡 파트너스 + 네이버 쇼핑) → 최대 40개.
     쿠팡은 검색 한도가 작아(시간당 ~10회) 아이템당 첫 검색어 1개만, 네이버는 전부.
  2) 1차 필터(코드): 종류별 가격대 · 중복(같은 이미지·같은 제목) · 키즈·남성·세트 묶음 제외(성인 여성만).
  3) 2차 필터(비전): 합성에 쓸 수 있는 사진인지(옷 단독·누끼 우선, 큰 글자·배너·콜라주·옷이 작은 사진 제외).
  4) 3차 심사(비전): 명세서 대비 종류·색·핏·기장·디테일 점수 + 감지 색(HEX)·계절 적합.
     점수 순 1등 + 예비 2개. 1등이 네이버여도 쿠팡이 5점 안이면 쿠팡 채택(제휴 링크).
  5) 조합 검사(코드): 고른 아이템 색이 3색 이하·포인트(채도 높은 색) 1색 이하. 어긋나면 그 아이템을 예비로 교체.
  6) 저장: ig_products(이미지 R2 사본·쿠팡 딥링크) + ig_looks(아이템별 1등·예비·점수·조합 기록).
비전 호출이 실패하면 그 단계는 코드 점수(검색 순위·검색어 일치)로 대신하고 note 에 남긴다(반자동 — 대표 승인 단계에서 판단).
"""

from __future__ import annotations

import base64
import colorsys
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

from adapters import r2_storage
from adapters.shopping import CoupangClient, NaverClient, QuotaExceeded, ShoppingError
from services import insta_outfit as io
from services import insta_outfit_plan as P
from services import insta_refs as refs

logger = logging.getLogger(__name__)

# 네이버 쇼핑 검색은 약관상 사용 불가(검색 종료 + AI 입력·저장·수익 금지, 결정 2026-10-27) — 코드는 두고 끈다.
NAVER_ENABLED = False
# 2차 필터(합성 가능 사진인지)는 작은 썸네일 + 저렴한 모델, 3차 심사만 기본 검수 모델(결정 2026-10-27, 픽 비용↓)
SCREEN_MODEL = "claude-haiku-4-5-20251001"
SCREEN_PX, SCORE_PX = 256, 512
MAX_CANDIDATES = 40
USABLE_BATCH = 12          # 2차 필터 한 번에 보는 사진 수
SCORE_TOP = 8              # 3차 심사에 올리는 수
MIN_SCORE = 55             # 이보다 낮으면 '맞는 상품 없음'
COUPANG_MARGIN = 5         # 1등이 네이버여도 쿠팡이 이 점수 안이면 쿠팡

# 종류별 가격대(원) — 성인 여성 데일리 기준
# 2026-10-27 대표 피드백("옷 선택이 후줄근") — 하한을 올려 너무 싼 기본템을 걸러낸다.
PRICE_RANGE: dict[str, tuple[int, int]] = {
    "top": (19_000, 180_000), "bottoms": (22_000, 180_000), "dress": (29_000, 250_000),
    "outerwear": (49_000, 450_000), "shoes": (29_000, 280_000), "bag": (25_000, 350_000),
    "accessory": (9_000, 150_000),
}
_EXCLUDE = re.compile(r"(키즈|아동|주니어|유아|남아|여아|베이비|토들러|남자|남성|맨즈|남자친구|신사|"
                      r"세트|셋업\s*세트|1\s*\+\s*1|2\s*\+\s*1|[2-9]\s*종|[2-9]\s*pcs|[2-9]\s*팩|묶음|커플)", re.I)
_EXCLUDE_CAT = re.compile(r"(남성|아동|유아|출산|키즈)")


# ── 1차 필터(코드) ───────────────────────────────────────────────────────
def _norm_title(t: str) -> str:
    return re.sub(r"[\W_]+", "", re.sub(r"\[[^\]]*\]|\([^)]*\)", "", t or "")).lower()


def code_filter(cands: list[dict], kind: str) -> tuple[list[dict], dict]:
    """가격·제외어·카테고리·중복. → (남은 후보, 제외 사유별 개수)."""
    lo, hi = PRICE_RANGE.get(kind, (3_000, 500_000))
    seen_img, seen_title = set(), set()
    out, why = [], {"price": 0, "excluded": 0, "duplicate": 0}
    for c in cands:
        if not (lo <= int(c.get("price") or 0) <= hi):
            why["price"] += 1
            continue
        if _EXCLUDE.search(c.get("name", "")) or _EXCLUDE_CAT.search(c.get("category", "")):
            why["excluded"] += 1
            continue
        img = (c.get("image_url") or "").split("?")[0]
        title = _norm_title(c.get("name", ""))
        if img in seen_img or (title and title in seen_title):
            why["duplicate"] += 1
            continue
        seen_img.add(img)
        seen_title.add(title)
        out.append(c)
    return out, why


# ── 색 조합 ──────────────────────────────────────────────────────────────
def color_family(hex_color: str | None) -> tuple[str, bool]:
    """(색 계열 이름, 포인트색 여부). 무채색·베이지·네이비·카키·브라운은 기본색(포인트 아님)."""
    if not hex_color or not re.match(r"^#[0-9a-fA-F]{6}$", hex_color):
        return "unknown", False
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    hd = h * 360
    if l < 0.16:
        return "black", False
    if l > 0.9 and s < 0.5:
        return "white", False
    if s < 0.15:
        return "grey", False
    if 20 <= hd < 50 and s < 0.6 and l > 0.55:
        return "beige", False
    if 20 <= hd < 45 and l <= 0.55:
        return "brown", False
    if 200 <= hd < 250 and l < 0.35:
        return "navy", False
    if 60 <= hd < 100 and s < 0.45 and l < 0.5:
        return "khaki", False
    names = [(15, "red"), (45, "orange"), (70, "yellow"), (160, "green"), (200, "cyan"), (260, "blue"),
             (300, "purple"), (345, "pink"), (361, "red")]
    fam = next(n for edge, n in names if hd < edge)
    return fam, s >= 0.45


def combo_violations(colors: list[str | None]) -> dict:
    """3색 이하·포인트 1색 이하. → {families, accents, ok, reason}."""
    fams = [color_family(c) for c in colors]
    known = [f for f in fams if f[0] != "unknown"]
    families = sorted({f[0] for f in known})
    accents = sorted({f[0] for f in known if f[1]})
    reasons = []
    if len(families) > 3:
        reasons.append(f"{len(families)}색(3색 이하 권장)")
    if len(accents) > 1:
        reasons.append(f"포인트색 {len(accents)}개(1개 권장)")
    return {"families": families, "accents": accents, "ok": not reasons, "reason": ", ".join(reasons)}


def fix_combo(items: list[dict], cand_color: Callable[[dict], str | None], max_swaps: int = 4) -> dict:
    """조합이 어긋나면 '문제 색'을 가진 아이템 중 점수 여유가 가장 작은 것을 예비로 교체(최대 max_swaps)."""
    swaps = []
    for _ in range(max_swaps):
        picked = [it for it in items if it.get("pick")]
        res = combo_violations([cand_color(it["pick"]) for it in picked])
        if res["ok"]:
            return {**res, "swaps": swaps}
        fam = {id(it): color_family(cand_color(it["pick"])) for it in picked}
        fam_count: dict[str, int] = {}
        for f, _ in fam.values():
            fam_count[f] = fam_count.get(f, 0) + 1
        # 포인트색이 둘 이상이면 포인트색 아이템, 아니면 혼자인 색 계열 아이템이 교체 후보
        if len(res["accents"]) > 1:
            offenders = [it for it in picked if fam[id(it)][1]]
        else:
            offenders = [it for it in picked if fam_count[fam[id(it)][0]] == 1 and fam[id(it)][0] != "unknown"]
        offenders = [it for it in offenders if it.get("backups")]
        if not offenders:
            return {**res, "swaps": swaps}
        target = min(offenders, key=lambda it: (it["pick"].get("score", 0) - it["backups"][0].get("score", 0)))
        old = target["pick"]
        target["pick"] = target["backups"].pop(0)
        target["backups"].append(old)
        swaps.append({"index": target["index"], "from": old.get("product_id"), "to": target["pick"].get("product_id"),
                      "reason": res["reason"]})
    res = combo_violations([cand_color(it["pick"]) for it in items if it.get("pick")])
    return {**res, "swaps": swaps}


# ── 비전 ─────────────────────────────────────────────────────────────────
def vision_labeled(system: str, labeled: list[tuple[str, Path]], ask: str, task: str, max_tokens: int = 1500,
                   *, model: str | None = None, meter: dict | None = None) -> dict:
    """후보 사진마다 '후보 N' 라벨을 붙여 Claude 비전 1회 → JSON. (OpenAI 대체 없음 — 실패 시 호출부가 코드 점수로)
    meter 를 주면 {model: {"in": 토큰, "out": 토큰}} 로 누적(코디 1벌 비용 표시용)."""
    from services import music_lyrics, music_ops_log
    from services.music_auto_image import review_model

    content: list[dict] = []
    for label, p in labeled:
        content.append({"type": "text", "text": label})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                    "data": base64.b64encode(p.read_bytes()).decode("ascii")}})
    content.append({"type": "text", "text": ask})
    model = model or review_model()
    client = music_lyrics._client().with_options(timeout=90.0, max_retries=0)
    msg = client.messages.create(model=model, max_tokens=max_tokens, system=system,
                                 messages=[{"role": "user", "content": content}])
    music_ops_log.add_usage_from(msg, model)
    if meter is not None and getattr(msg, "usage", None) is not None:
        m = meter.setdefault(model, {"in": 0, "out": 0})
        m["in"] += int(getattr(msg.usage, "input_tokens", 0) or 0)
        m["out"] += int(getattr(msg.usage, "output_tokens", 0) or 0)
    data = music_lyrics._extract_json("".join(getattr(b, "text", "") for b in (msg.content or [])))
    if not isinstance(data, dict):
        raise ValueError("JSON 아님")
    return data


_USABLE_SYSTEM = (
    "You screen product photos from Korean shopping malls for an AI outfit generator that must copy the garment "
    "exactly. For EACH candidate decide if the photo is usable: the garment is clearly visible and large, ideally "
    "alone on a plain/white background (flat lay or cut-out) or worn on a model with the garment fully shown. "
    "Reject: big text/banners/price stickers over the garment, collages of several photos or many color swatches, "
    "the garment tiny in the frame, only a detail crop, or a different item type than requested. "
    'Return ONE JSON object: {"results": [{"n": <candidate number>, "usable": true|false, "reason": "짧은 한국어"}]}.'
)
_SCORE_SYSTEM = (
    "You compare shopping-mall product photos against a target item spec for a Korean women's outfit. "
    "Score EACH candidate 0-10 on: kind (same garment type), color (same color/tone as spec color/hex), fit "
    "(slim/regular/over silhouette), length, details (buttons, collar, pockets, pattern), and style (does it look "
    "like a hip, youthful, on-trend item a Korean woman in her early 20s would actually wear now — Seoul street / "
    "꾸안꾸 vibe, decent fabric, well photographed; matronly or classic office-lady pieces, cheap-looking basics, "
    "shiny polyester, dated or costume-like items score low). Also give the "
    "garment's main color as hex and whether it suits the given seasons. Be strict: a different color or type "
    "must score low. "
    'Return ONE JSON object: {"results": [{"n": <number>, "kind": 0-10, "color": 0-10, "fit": 0-10, "length": 0-10, '
    '"details": 0-10, "style": 0-10, "hex": "#RRGGBB", "season_ok": true|false, "note": "짧은 한국어"}]}.'
)
_WEIGHTS = {"kind": 3.0, "color": 3.0, "fit": 1.5, "length": 1.5, "details": 1.0, "style": 2.0}
_NEUTRAL = {"style": 6.0}   # 비전 응답에 없으면 중간값(예전 응답·폴백 호환)


def vision_cost_usd(meter: dict) -> float:
    """토큰 미터 → 달러(모델 단가는 대시보드와 같은 표, 모르는 모델은 Haiku 단가로)."""
    from services.music_dashboard_summary import _claude_price
    usd = 0.0
    for model, t in (meter or {}).items():
        p_in, p_out = _claude_price(model) or (1.0, 5.0)
        usd += (t.get("in", 0) * p_in + t.get("out", 0) * p_out) / 1_000_000
    return round(usd, 5)


def total_score(r: dict, season_ok: bool = True) -> float:
    def v(k):
        x = r.get(k)
        return _NEUTRAL.get(k, 0.0) if x is None else float(x or 0)
    s = sum(_WEIGHTS[k] * max(0.0, min(10.0, v(k))) for k in _WEIGHTS) / sum(_WEIGHTS.values()) * 10
    return round(s - (20 if not season_ok else 0), 1)


def _code_score(c: dict, item: dict) -> float:
    """비전 실패 시 대체 점수: 검색 순위(앞일수록) + 검색어 단어 일치."""
    words = {w for q in item.get("queries", []) for w in q.split() if len(w) >= 2}
    hit = sum(1 for w in words if w in c.get("name", ""))
    return round(40 + min(30, hit * 8) - min(20, c.get("_rank", 0)), 1)


# ── 픽 ───────────────────────────────────────────────────────────────────
class _Off:
    """꺼진 통로(네이버) — is_available 만 False."""
    def is_available(self) -> bool:
        return False


class Deps:
    def __init__(self, coupang=None, naver=None, vision=None, download=None, rest=None, now=None):
        self.coupang = coupang or CoupangClient()
        self.naver = naver or (NaverClient() if NAVER_ENABLED else _Off())
        self.meter: dict = {}
        self.vision = vision or vision_labeled
        self.download = download or io._download
        self.rest = rest or refs.rest
        self.now = now or datetime.now(timezone.utc)


def gather(item: dict, d: Deps, usage: dict) -> tuple[list[dict], list[str]]:
    """검색어 × 통로 → 후보(검색 순위 _rank). notes: 통로별 건너뜀 사유."""
    out, notes = [], []
    qs = item.get("queries") or []
    plans = []
    if d.coupang.is_available():
        plans += [("coupang", q) for q in qs[:1]]
    else:
        notes.append("쿠팡 연결 필요")
    if NAVER_ENABLED and d.naver.is_available():
        plans += [("naver", q) for q in qs[:3]]
    for ch, q in plans:
        try:
            got = d.coupang.search(q, 10) if ch == "coupang" else d.naver.search(q, 20)
        except QuotaExceeded as e:
            notes.append(f"{'쿠팡' if ch == 'coupang' else '네이버'} 검색 한도 — 잠시 후 다시 해 주세요")
            logger.warning("[insta-picks] %s 한도: %s", ch, e)
            continue
        except Exception as e:  # noqa: BLE001
            notes.append(f"{ch} 검색 실패")
            logger.warning("[insta-picks] %s 검색 실패(%s): %s", ch, q, str(e)[:160])
            continue
        if ch == "coupang" and getattr(d.coupang, "cached", False):
            usage["coupang_cached"] = usage.get("coupang_cached", 0) + 1  # 1시간 캐시 — 호출·한도에 안 셈
        else:
            usage[ch] = usage.get(ch, 0) + 1
        try:
            if not (ch == "coupang" and getattr(d.coupang, "cached", False)):
                refs.add_usage(ch, 1, d.now)
        except Exception:  # noqa: BLE001 - 사용량 기록 실패가 픽을 막지 않게
            pass
        for rank, c in enumerate(got):
            out.append({**c, "_rank": rank, "_query": q})
        if len(out) >= MAX_CANDIDATES:
            break
    return out[:MAX_CANDIDATES], notes


def _thumb(src: Path, dst: Path, px: int) -> Path:
    import subprocess
    res = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf",
                          f"scale='if(gt(iw,ih),min({px},iw),-2)':'if(gt(iw,ih),-2,min({px},ih))'",
                          "-frames:v", "1", "-q:v", "4", str(dst)], capture_output=True, text=True, timeout=60)
    if res.returncode != 0 or not dst.exists():
        raise RuntimeError(f"썸네일 실패: {res.stderr[-120:]}")
    return dst


def _small(d: Deps, c: dict, tmp: Path) -> tuple[Path, Path] | None:
    """후보 이미지 1번 받아 (2차용 256px, 3차용 512px). 받은 원본은 tmp 에만(저장 안 함)."""
    base = f"{c['channel']}_{re.sub(r'[^A-Za-z0-9]', '', c['product_id'])}"
    try:
        src = d.download(c["image_url"], tmp / f"{base}.img")
        return _thumb(src, tmp / f"{base}_s.jpg", SCREEN_PX), _thumb(src, tmp / f"{base}_m.jpg", SCORE_PX)
    except Exception as e:  # noqa: BLE001
        logger.warning("[insta-picks] 후보 이미지 실패 %s: %s", c.get("product_id"), str(e)[:120])
        return None


def judge(item: dict, look: dict, cands: list[dict], d: Deps, usage: dict, tmp: Path) -> tuple[list[dict], list[str]]:
    """2차(사용 가능) + 3차(명세 점수) → 점수 붙인 후보 내림차순."""
    notes: list[str] = []
    imgs, mid = [], {}
    for c in cands:
        got = _small(d, c, tmp)
        if got:
            imgs.append((c, got[0]))
            mid[id(c)] = got[1]
    if not imgs:
        return [], ["후보 사진을 받을 수 없음"]
    kind_ko = P.PRODUCT_KINDS.get(item["kind"], (item["kind"],))[0]
    # 2차: 쓸 수 있는 사진
    usable: list[tuple[dict, Path]] = []
    try:
        for i in range(0, len(imgs), USABLE_BATCH):
            batch = imgs[i:i + USABLE_BATCH]
            res = d.vision(_USABLE_SYSTEM, [(f"후보 {n + 1}", p) for n, (_, p) in enumerate(batch)],
                           f"찾는 종류: {kind_ko}({item['kind']}). 후보마다 판정해 JSON 만.", "insta_pick_usable", 800,
                           model=SCREEN_MODEL, meter=d.meter)
            usage["vision"] = usage.get("vision", 0) + 1
            ok = {int(r.get("n", 0)) for r in res.get("results") or [] if r.get("usable")}
            usable += [b for n, b in enumerate(batch) if n + 1 in ok]
    except Exception as e:  # noqa: BLE001
        notes.append("사진 검사 못함(AI 호출 실패) — 검색 순위로 대신")
        logger.warning("[insta-picks] 2차 비전 실패: %s", str(e)[:160])
        usable = imgs
    if not usable:
        return [], notes + ["쓸 수 있는 사진이 없음"]
    usable.sort(key=lambda x: x[0].get("_rank", 0))
    top = usable[:SCORE_TOP]
    # 3차: 명세 점수
    spec_line = json.dumps({k: item.get(k) for k in ("kind", "color_name", "hex", "fit", "length", "material", "details")},
                           ensure_ascii=False)
    try:
        res = d.vision(_SCORE_SYSTEM, [(f"후보 {n + 1}", mid[id(c)]) for n, (c, _) in enumerate(top)],
                       f"목표 아이템: {spec_line}. 계절: {look.get('seasons') or []}. 후보마다 점수 JSON 만.",
                       "insta_pick_score", 1500, meter=d.meter)
        usage["vision"] = usage.get("vision", 0) + 1
        by_n = {int(r.get("n", 0)): r for r in res.get("results") or []}
        scored = []
        for n, (c, _) in enumerate(top):
            r = by_n.get(n + 1)
            if not r:
                continue
            scored.append({**c, "score": total_score(r, bool(r.get("season_ok", True))),
                           "scores": {k: r.get(k) for k in (*_WEIGHTS, "hex", "season_ok", "note")}})
    except Exception as e:  # noqa: BLE001
        notes.append("명세 심사 못함(AI 호출 실패) — 검색어 일치로 대신")
        logger.warning("[insta-picks] 3차 비전 실패: %s", str(e)[:160])
        scored = [{**c, "score": _code_score(c, item), "scores": {"hex": item.get("hex"), "fallback": True}} for c, _ in top]
    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored, notes


def choose(scored: list[dict]) -> tuple[dict | None, list[dict], str | None]:
    """1등 + 예비 2. 1등이 네이버여도 쿠팡이 COUPANG_MARGIN 안이면 쿠팡. MIN_SCORE 미만이면 없음."""
    ok = [c for c in scored if c["score"] >= MIN_SCORE]
    if not ok:
        return None, scored[:2], "명세에 맞는 상품을 찾지 못했어요"
    best = ok[0]
    if best["channel"] != "coupang":
        cp = next((c for c in ok if c["channel"] == "coupang" and best["score"] - c["score"] <= COUPANG_MARGIN), None)
        if cp:
            best = cp
    rest_ = [c for c in ok if c is not best]
    return best, rest_[:2], None


def _to_jpeg(src: Path, dst: Path) -> Path:
    import subprocess
    res = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-frames:v", "1", "-q:v", "2", str(dst)],
                         capture_output=True, text=True, timeout=60)
    if res.returncode != 0 or not dst.exists():
        raise RuntimeError(f"jpg 변환 실패: {res.stderr[-160:]}")
    return dst


def _public(c: dict) -> dict:
    return {k: c.get(k) for k in ("channel", "product_id", "name", "price", "mall", "image_url", "link", "category",
                                  "score", "scores", "_query")}


def save_products(picks: list[dict], d: Deps) -> dict[tuple[str, str], dict]:
    """R2 이미지 사본 + 쿠팡 딥링크 + ig_products upsert → {(channel, product_id): row}."""
    links = {}
    cp_urls = [c["link"] for c in picks if c["channel"] == "coupang" and c.get("link")]
    if cp_urls:
        try:
            links = d.coupang.deeplinks(cp_urls)
        except Exception as e:  # noqa: BLE001 - 딥링크 실패해도 상품 링크는 남긴다
            logger.warning("[insta-picks] 쿠팡 딥링크 실패: %s", str(e)[:160])
    rows = []
    with tempfile.TemporaryDirectory() as td:
        for c in picks:
            key = None
            if r2_storage.is_available():
                try:
                    safe = re.sub(r"[^A-Za-z0-9_-]", "", c["product_id"])[:60]
                    src = d.download(c["image_url"], Path(td) / f"{safe}.img")
                    jpg = _to_jpeg(src, Path(td) / f"{safe}.jpg")  # 합성 참조용 — 줄이지 않고 jpg 로만
                    key = f"insta/products/{c['channel']}/{safe}.jpg"
                    r2_storage.upload_image(str(jpg), key, bucket=r2_storage._character_bucket(),
                                            public_base_url=r2_storage._character_public_base(), content_type="image/jpeg")
                except Exception as e:  # noqa: BLE001
                    logger.warning("[insta-picks] 상품 이미지 저장 실패 %s: %s", c["product_id"], str(e)[:120])
                    key = None
            rows.append({"channel": c["channel"], "product_id": c["product_id"], "name": c["name"][:300],
                         "mall": c.get("mall"), "brand": c.get("brand") or None, "category": (c.get("category") or "")[:200],
                         "price": c.get("price"), "image_url": c.get("image_url"), "image_key": key, "link": c.get("link"),
                         "affiliate_link": links.get(c.get("link")) if c["channel"] == "coupang" else None,
                         "raw": c.get("raw") or {}, "updated_at": datetime.now(timezone.utc).isoformat()})
    if not rows:
        return {}
    saved = d.rest("ig_products", "POST", params={"on_conflict": "channel,product_id"}, json_body=rows,
                   prefer="resolution=merge-duplicates,return=representation")
    return {(r["channel"], r["product_id"]): r for r in saved}


def pick_look(look_id: str, ref: dict, look_index: int, d: Deps | None = None) -> dict:
    """룩 1벌 픽 → ig_looks 갱신. 반환: 저장한 look 행."""
    d = d or Deps()
    look = ((ref.get("analysis") or {}).get("looks") or [])[look_index]
    usage: dict = {}
    items_out: list[dict] = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for idx, item in enumerate(look["items"]):
            cands, notes = gather(item, d, usage)
            kept, why = code_filter(cands, item["kind"])
            scored, n2 = judge(item, look, kept, d, usage, tmp) if kept else ([], ["가격·종류 조건에 맞는 후보가 없음"])
            pick, backups, miss = choose(scored)
            items_out.append({"index": idx, "kind": item["kind"], "spec": item, "pick": pick, "backups": backups,
                              "candidates": len(cands), "filtered": why, "notes": notes + n2 + ([miss] if miss else [])})
    combo = fix_combo(items_out, lambda c: (c.get("scores") or {}).get("hex"))
    chosen = [c for it in items_out for c in ([it["pick"]] if it["pick"] else []) + it["backups"]]
    saved = save_products(chosen, d)
    for it in items_out:
        def ref_of(c):
            row = saved.get((c["channel"], c["product_id"]))
            return {**_public(c), "id": row.get("id") if row else None, "image_key": row.get("image_key") if row else None,
                    "affiliate_link": row.get("affiliate_link") if row else None}
        it["pick"] = ref_of(it["pick"]) if it["pick"] else None
        it["backups"] = [ref_of(c) for c in it["backups"]]
    status = "picked" if any(it["pick"] for it in items_out) else "failed"
    usage["vision_usd"] = vision_cost_usd(d.meter)
    fields = {"items": items_out, "combo": combo, "status": status, "usage": usage,
              "error": None if status == "picked" else "고른 상품이 없어요", "updated_at": datetime.now(timezone.utc).isoformat()}
    d.rest("ig_looks", "PATCH", params={"id": f"eq.{look_id}"}, json_body=fields, prefer="return=minimal")
    if status == "picked":
        d.rest("ig_refs", "PATCH", params={"video_id": f"eq.{ref['video_id']}"}, prefer="return=minimal",
               json_body={"status": "used", "used_at": datetime.now(timezone.utc).isoformat()})
    return {"id": look_id, **fields}


# ── 잡 ───────────────────────────────────────────────────────────────────
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


def connections() -> dict:
    """화면 연결 표시. 네이버는 약관상 꺼 둠(naver_enabled False → 화면에서 표시 숨김)."""
    return {"coupang": CoupangClient().is_available(),
            "naver": NAVER_ENABLED and NaverClient().is_available(), "naver_enabled": NAVER_ENABLED}


def usable_ref(ref: dict) -> bool:
    """분석에서 '참고 안 함'(남성·명품 토크·전신 착장 없음)으로 판정된 레퍼런스는 고르지 않는다."""
    return (ref.get("analysis") or {}).get("usable", True) is not False


def next_ref(d: Deps) -> dict | None:
    rows = d.rest("ig_refs", "GET", params={"select": "*", "status": "eq.analyzed", "order": "views.desc", "limit": "20"})
    return next((r for r in rows if usable_ref(r)), None)


# ── 쿠팡 이미지: 쓰고 지우기(쿠팡 Open API 약관 제5조) ─────────────────
def delete_images(rows: list[dict], d: Deps) -> int:
    """쿠팡 상품의 R2 이미지 사본을 지우고 image_key 를 비운다(삭제 시각 기록). 보세(대표 업로드)는 건드리지 않는다."""
    n = 0
    now = datetime.now(timezone.utc).isoformat()
    for r in rows:
        if r.get("channel") != "coupang" or not r.get("image_key"):
            continue
        try:
            if r2_storage.is_available():
                r2_storage._get_client().delete_object(Bucket=r2_storage._character_bucket(), Key=r["image_key"])
            if r.get("id") is not None:
                d.rest("ig_products", "PATCH", params={"id": f"eq.{r['id']}"}, prefer="return=minimal",
                       json_body={"image_key": None, "image_deleted_at": now})
            r["image_key"] = None
            n += 1
        except Exception as e:  # noqa: BLE001 - 다음 청소 때 다시
            logger.warning("[insta-picks] 쿠팡 이미지 삭제 실패 %s: %s", r.get("image_key"), str(e)[:160])
    return n


def look_coupang_products(look: dict) -> list[dict]:
    return [c for it in look.get("items") or [] for c in ([it["pick"]] if it.get("pick") else []) + (it.get("backups") or [])
            if c.get("channel") == "coupang"]


SWEEP_HOURS = 24


def sweep_images(d: Deps, hours: int = SWEEP_HOURS) -> int:
    """착장으로 이어지지 않은 픽도 하루 넘게 이미지를 들고 있지 않게 — 오래된 쿠팡 사본 정리."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    try:
        rows = d.rest("ig_products", "GET", params={"select": "id,channel,image_key", "channel": "eq.coupang",
                                                   "image_key": "not.is.null", "updated_at": f"lt.{cutoff}", "limit": "200"})
    except Exception as e:  # noqa: BLE001
        logger.warning("[insta-picks] 이미지 청소 조회 실패: %s", str(e)[:160])
        return 0
    return delete_images(rows, d)


def record_feedback(d: Deps, event: str, **fields) -> None:
    """승인·반려·교체·내리기 이벤트(ig_feedback). 기록 실패가 화면 동작을 막지 않게."""
    try:
        d.rest("ig_feedback", "POST", json_body=[{"event": event, **{k: v for k, v in fields.items() if v is not None}}],
               prefer="return=minimal")
    except Exception as e:  # noqa: BLE001
        logger.warning("[insta-picks] 피드백 기록 실패(%s): %s", event, str(e)[:160])


def start(video_id: str | None = None, look_index: int = 0, d: Deps | None = None) -> dict:
    """룩 행 생성 + 잡 등록(실행은 run). video_id 없으면 분석된 레퍼런스 중 조회수 1위."""
    d = d or Deps()
    if not (d.coupang.is_available() or (NAVER_ENABLED and d.naver.is_available())):
        raise ShoppingError("쿠팡 연결이 필요해요(키 없음).")
    sweep_images(d)
    if video_id:
        rows = d.rest("ig_refs", "GET", params={"select": "*", "video_id": f"eq.{video_id}"})
        ref = rows[0] if rows else None
    else:
        ref = next_ref(d)
    if not ref or not (ref.get("analysis") or {}).get("looks"):
        raise ShoppingError("고를 레퍼런스가 없어요 — 먼저 레퍼런스를 모아 주세요.")
    looks = ref["analysis"]["looks"]
    if not 0 <= look_index < len(looks):
        raise ShoppingError("없는 룩이에요.")
    with _LOCK:
        for j in _JOBS.values():
            if j["state"] in ("queued", "running") and j["ref"] == ref["video_id"] and j["look_index"] == look_index:
                return dict(j)
    look_id = f"lk-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(3)}"
    d.rest("ig_looks", "POST", json_body=[{"id": look_id, "ref_video_id": ref["video_id"], "look_index": look_index,
                                            "concept": looks[look_index]["concept"], "spec": looks[look_index],
                                            "status": "picking"}], prefer="return=minimal")
    job_id = f"pj_{secrets.token_hex(5)}"
    with _LOCK:
        _JOBS[job_id] = {"id": job_id, "look_id": look_id, "ref": ref["video_id"], "look_index": look_index,
                         "state": "queued", "error": None, "_ref": ref, "_deps": d}
    return public_job(_JOBS[job_id])


def public_job(j: dict) -> dict:
    return {k: v for k, v in j.items() if not k.startswith("_")}


def get_job(job_id: str) -> dict:
    with _LOCK:
        if job_id not in _JOBS:
            raise LookupError("작업을 찾을 수 없어요")
        return public_job(_JOBS[job_id])


def run(job_id: str) -> None:
    with _LOCK:
        j = _JOBS[job_id]
        j["state"] = "running"
        ref, d, look_id, idx = j["_ref"], j["_deps"], j["look_id"], j["look_index"]
    try:
        out = pick_look(look_id, ref, idx, d)
        with _LOCK:
            j.update(state="done" if out["status"] == "picked" else "failed", error=out.get("error"))
    except Exception as e:  # noqa: BLE001
        msg = str(e)[:300]
        logger.warning("[insta-picks] %s 실패: %s", look_id, msg)
        with _LOCK:
            j.update(state="failed", error=msg)
        try:
            d.rest("ig_looks", "PATCH", params={"id": f"eq.{look_id}"}, json_body={"status": "failed", "error": msg},
                   prefer="return=minimal")
        except Exception:  # noqa: BLE001
            pass


def list_looks(limit: int = 10, d: Deps | None = None) -> list[dict]:
    d = d or Deps()
    rows = d.rest("ig_looks", "GET", params={"select": "*", "order": "created_at.desc", "limit": str(max(1, min(limit, 30)) * 2)})
    rows = [r for r in rows if r.get("source") != "bose"][:limit]  # 내 상품 코디 룩은 착장 결과 카드에서 보여 준다
    krw = float(os.getenv("MUSIC_KRW_PER_USD") or 1400)
    for r in rows:
        for it in r.get("items") or []:
            for c in ([it["pick"]] if it.get("pick") else []) + (it.get("backups") or []):
                c["image"] = io.public_url(c.get("image_key")) or c.get("image_url")
        vusd = (r.get("usage") or {}).get("vision_usd")
        r["cost_krw"] = round(float(vusd) * krw) if vusd is not None else None
    return rows


def swap(look_id: str, item_index: int, product_row_id: int, d: Deps | None = None) -> dict:
    """아이템의 1등을 예비 중 하나로 바꾼다(교체 기록은 A2-3 피드백에서)."""
    d = d or Deps()
    rows = d.rest("ig_looks", "GET", params={"select": "*", "id": f"eq.{look_id}"})
    if not rows:
        raise LookupError("룩이 없어요")
    items = rows[0]["items"]
    it = next((x for x in items if x["index"] == item_index), None)
    if not it:
        raise ShoppingError("없는 아이템이에요")
    nb = next((c for c in it["backups"] if c.get("id") == product_row_id), None)
    if not nb:
        raise ShoppingError("예비 후보가 아니에요")
    old = it.get("pick")
    it["backups"] = [c for c in it["backups"] if c is not nb] + ([old] if old else [])
    it["pick"] = nb
    record_feedback(d, "swap", look_id=look_id, item_index=item_index,
                    product_id=(old or {}).get("id"), to_product_id=nb.get("id"))
    d.rest("ig_looks", "PATCH", params={"id": f"eq.{look_id}"}, prefer="return=minimal",
           json_body={"items": items, "updated_at": datetime.now(timezone.utc).isoformat()})
    return {**rows[0], "items": items}
