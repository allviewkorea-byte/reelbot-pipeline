"""포즈 라이브러리(대표 2026-10-30) — 착장 생성에 "포즈 참고 이미지"를 같이 넣는다.

출처: 작가 あぎ/ギア(@giaaibusi)의 POSE-DB-01(https://ai-pose-gallery.pages.dev/) — 얼굴 없는 회색 마네킹
선화 288포즈 × 5각도. 무료·상업 이용 OK, **이미지 재배포 금지**.
  → 우리 레포(공개)에는 이미지·썸네일을 한 장도 넣지 않는다. 목록은 중국어 검색판 깃허브
    (sleepy-zone/ai-ref-library-cn, data/pose.js)에서 런타임에 읽고 썸네일은 버린다.
  → 원본은 생성할 때 그 1장만 작가 사이트에서 받아 Muse 참고 이미지로 넘긴다(저장·공개 안 함).

쓸지 말지는 대표가 정한다(설정은 R2 JSON — SQL 불필요):
  enabled(기본 off) · cats(켤 카테고리 "시리즈|카테고리") · angles(각도) · excluded(뺄 포즈 key)
기본 카테고리는 화보용 1인 전신·상반신(추천안) — 화면에서 마음대로 바꾼다.
"""

from __future__ import annotations

import json
import logging
import random
import threading

import httpx

logger = logging.getLogger(__name__)

CATALOG_URL = "https://raw.githubusercontent.com/sleepy-zone/ai-ref-library-cn/main/data/pose.js"
SOURCE_SITE = "https://ai-pose-gallery.pages.dev/"
IMG_BASE = "https://ai-pose-gallery.pages.dev/img/"
CREDIT = "POSE-DB-01 by あぎ/ギア (@giaaibusi)"

_R2_PREFIX = "insta/poses"
SETTINGS_KEY = f"{_R2_PREFIX}/settings.json"
CATALOG_KEY = f"{_R2_PREFIX}/catalog.json"
I18N_KEY = f"{_R2_PREFIX}/i18n.json"

SERIES_KO = {0: "전신 · 섹시", 1: "전신 · 기본", 2: "상반신", 3: "2인"}

CAT_KO = {
    "站立": "서기", "坐姿": "앉기", "躺卧": "눕기", "跪立": "무릎 서기", "跪立·四肢撑": "무릎·네발",
    "侧坐·少女坐": "옆으로 앉기", "蹲姿": "쪼그려 앉기", "前倾": "숙이기", "后仰·反弓": "몸 젖히기",
    "扭转": "몸 비틀기", "特殊（高难）": "특수(고난도)", "可爱系": "귀여운", "胸景·挤胸系": "가슴 강조",
    "性感·露骨系": "섹시·노골", "贴脸系": "얼굴 밀착", "正常位": "정상위", "后入位": "후배위",
    "背坐位": "뒤로 앉기", "骑乘位": "기승위", "站立位": "선 자세", "站立贴靠": "서서 기대기",
    "侧位": "옆으로 눕기", "坐位": "앉은 자세", "面对面坐位": "마주 앉기", "坐位贴靠": "앉아 기대기",
    "贴身": "밀착",
}

ANGLE_KO = {"正面": "정면", "斜45°": "45°", "侧面": "측면", "俯视": "위에서", "仰视": "아래서"}

# 추천 기본값(대표가 화면에서 바꾼다) — 화보용 1인 전신 기본 + 상반신 귀여운.
DEFAULT_CATS = ["1|站立", "1|坐姿", "1|侧坐·少女坐", "1|蹲姿", "1|扭转", "2|可爱系"]
DEFAULT_ANGLES = ["正面", "斜45°", "侧面"]
RECENT_AVOID = 10

_LOCK = threading.Lock()
_CACHE: dict = {}
_I18N_RUNNING = False


# ── R2 JSON(best-effort) ───────────────────────────────────────────────
def _r2_get(key: str):
    try:
        from adapters import r2_storage
        obj = r2_storage._get_client().get_object(Bucket=r2_storage._music_bucket(), Key=key)
        return json.loads(obj["Body"].read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - 없음/미설정
        return None


def _r2_put(key: str, data) -> bool:
    try:
        from adapters import r2_storage
        r2_storage._get_client().put_object(
            Bucket=r2_storage._music_bucket(), Key=key,
            Body=json.dumps(data, ensure_ascii=False).encode("utf-8"), ContentType="application/json",
        )
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("[pose-lib] R2 저장 실패 %s: %s", key, str(e)[:160])
        return False


# ── 목록 ───────────────────────────────────────────────────────────────
def parse_catalog(js_text: str) -> list[dict]:
    """data/pose.js(window.LIB_POSE={...}) → 포즈 목록(썸네일 img 는 버린다)."""
    body = js_text[js_text.index("=") + 1:].strip().rstrip(";")
    data = json.loads(body)["data"]
    out = []
    for p in data["poses"]:
        angles = {a: base for a, base in (p.get("ang") or {}).items() if base}
        if not angles:
            continue
        out.append({"key": p["key"], "id": p["id"], "s": int(p["s"]), "cat": p["cat"],
                    "zh": p.get("zh") or "", "ja": p.get("ja") or "", "angles": angles})
    return out


def _fetch_catalog(http=None) -> list[dict]:
    with (http or httpx.Client(timeout=60.0, follow_redirects=True)) as c:
        r = c.get(CATALOG_URL)
        r.raise_for_status()
        return parse_catalog(r.text)


def catalog(*, http=None, refresh: bool = False) -> list[dict]:
    """메모리 → R2 캐시 → 깃허브 순. 실패하면 빈 목록."""
    with _LOCK:
        if _CACHE.get("poses") and not refresh:
            return _CACHE["poses"]
    poses = None if refresh else _r2_get(CATALOG_KEY)
    if not poses:
        try:
            poses = _fetch_catalog(http)
            _r2_put(CATALOG_KEY, poses)
        except Exception as e:  # noqa: BLE001
            logger.warning("[pose-lib] 목록 받기 실패: %s", str(e)[:200])
            poses = []
    with _LOCK:
        if poses:
            _CACHE["poses"] = poses
    return poses


def cat_key(p: dict) -> str:
    return f"{p['s']}|{p['cat']}"


def image_url(base: str) -> str:
    return f"{IMG_BASE}{base}.png"


# ── 한글·영문 설명(1회 번역 후 R2 캐시) ───────────────────────────────────
_I18N_SYSTEM = (
    "You translate short Chinese pose descriptions for a pose reference library. For each item return a natural "
    "Korean label (짧게) and a precise English pose description usable in an image prompt (body, arms, legs, head; "
    'no extra words). Return ONE JSON object: {"<key>": {"ko": "...", "en": "..."}, ...} for every key given.'
)


def i18n() -> dict:
    with _LOCK:
        if "i18n" in _CACHE:
            return _CACHE["i18n"]
    got = _r2_get(I18N_KEY) or {}
    with _LOCK:
        if got:
            _CACHE["i18n"] = got
    return got


def _translate_batch(items: list[dict], llm) -> dict:
    from services import music_lyrics
    user = json.dumps({p["key"]: p["zh"] for p in items}, ensure_ascii=False)
    out = music_lyrics._extract_json(llm(_I18N_SYSTEM, user))
    return {k: {"ko": str(v.get("ko") or "")[:60], "en": str(v.get("en") or "")[:200]}
            for k, v in (out or {}).items() if isinstance(v, dict)}


def build_i18n(poses: list[dict] | None = None, llm=None, batch: int = 60) -> dict:
    """번역 안 된 포즈만 묶어서 번역 → R2 저장. 실패한 묶음은 다음에 다시."""
    from services import music_lyrics
    llm = llm or (lambda s, u: music_lyrics._call(s, u, max_tokens=8000, task="insta_pose_i18n"))
    poses = poses if poses is not None else catalog()
    have = dict(i18n())
    todo = [p for p in poses if p["key"] not in have and p.get("zh")]
    for i in range(0, len(todo), batch):
        try:
            have.update(_translate_batch(todo[i:i + batch], llm))
        except Exception as e:  # noqa: BLE001
            logger.warning("[pose-lib] 번역 실패(다음에 재시도): %s", str(e)[:160])
    if have:
        _r2_put(I18N_KEY, have)
        with _LOCK:
            _CACHE["i18n"] = have
    return have


def ensure_i18n_async() -> None:
    """번역이 비어 있으면 백그라운드 1회(프로세스당 동시 1개)."""
    global _I18N_RUNNING
    poses = catalog()
    if not poses or len(i18n()) >= len(poses):
        return
    with _LOCK:
        if _I18N_RUNNING:
            return
        _I18N_RUNNING = True

    def _work():
        global _I18N_RUNNING
        try:
            build_i18n(poses)
        finally:
            _I18N_RUNNING = False
    threading.Thread(target=_work, name="pose-i18n", daemon=True).start()


# ── 설정 ───────────────────────────────────────────────────────────────
def default_settings() -> dict:
    return {"enabled": False, "cats": list(DEFAULT_CATS), "angles": list(DEFAULT_ANGLES), "excluded": []}


def get_settings() -> dict:
    s = default_settings()
    got = _r2_get(SETTINGS_KEY)
    if isinstance(got, dict):
        s.update({k: got[k] for k in s if k in got})
    return s


def save_settings(patch: dict) -> dict:
    s = get_settings()
    if "enabled" in patch:
        s["enabled"] = bool(patch["enabled"])
    for k in ("cats", "angles", "excluded"):
        if k in patch and isinstance(patch[k], list):
            s[k] = sorted({str(x) for x in patch[k]})
    s["angles"] = [a for a in s["angles"] if a in ANGLE_KO]
    if not _r2_put(SETTINGS_KEY, s):
        raise RuntimeError("설정 저장 실패(R2)")
    return s


# ── 화면용 ─────────────────────────────────────────────────────────────
def listing() -> dict:
    """카테고리(개수·켜짐) + 포즈(한글 설명·각도별 원본 주소) + 설정."""
    poses = catalog()
    ensure_i18n_async()
    tr = i18n()
    st = get_settings()
    cats: dict[str, dict] = {}
    for p in poses:
        k = cat_key(p)
        c = cats.setdefault(k, {"key": k, "series": p["s"], "series_ko": SERIES_KO.get(p["s"], str(p["s"])),
                                "cat": p["cat"], "ko": CAT_KO.get(p["cat"], p["cat"]), "count": 0,
                                "enabled": k in st["cats"]})
        c["count"] += 1
    items = [{"key": p["key"], "id": p["id"], "series": p["s"], "cat_key": cat_key(p),
              "ko": (tr.get(p["key"]) or {}).get("ko") or p["zh"], "zh": p["zh"],
              "excluded": p["key"] in st["excluded"],
              "angles": [{"angle": a, "ko": ANGLE_KO.get(a, a), "url": image_url(b)} for a, b in p["angles"].items()]}
             for p in poses]
    return {"source": SOURCE_SITE, "credit": CREDIT, "settings": st,
            "angles": [{"angle": a, "ko": ko} for a, ko in ANGLE_KO.items()],
            "categories": sorted(cats.values(), key=lambda c: (c["series"], -c["count"])),
            "poses": items, "translated": len(tr), "total": len(poses)}


# ── 생성용 ─────────────────────────────────────────────────────────────
def pick(*, recent: list[str] | None = None, rng: random.Random | None = None,
         settings: dict | None = None) -> dict | None:
    """켜진 카테고리·각도 중 1개(최근 쓴 포즈 회피). 꺼져 있거나 후보가 없으면 None."""
    r = rng or random
    st = settings or get_settings()
    if not st.get("enabled"):
        return None
    pool = [p for p in catalog() if cat_key(p) in st["cats"] and p["key"] not in st["excluded"]
            and any(a in p["angles"] for a in st["angles"])]
    if not pool:
        return None
    fresh = [p for p in pool if p["key"] not in set((recent or [])[:RECENT_AVOID])] or pool
    p = r.choice(fresh)
    angle = r.choice([a for a in st["angles"] if a in p["angles"]])
    tr = i18n().get(p["key"]) or {}
    return {"key": p["key"], "id": p["id"], "cat": p["cat"], "cat_ko": CAT_KO.get(p["cat"], p["cat"]),
            "angle": angle, "base": p["angles"][angle], "url": image_url(p["angles"][angle]),
            "ko": tr.get("ko") or p["zh"], "en": tr.get("en") or ""}


def download(pose: dict, dest, http=None) -> str:
    """원본 1장 받기(생성 직전, 저장·공개 안 함)."""
    with (http or httpx.Client(timeout=30.0, follow_redirects=True)) as c:
        r = c.get(pose["url"])
        r.raise_for_status()
        if not r.content or len(r.content) < 1000:
            raise RuntimeError("포즈 이미지가 비어 있음")
        with open(dest, "wb") as f:
            f.write(r.content)
    return str(dest)
