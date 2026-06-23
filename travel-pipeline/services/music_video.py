"""음악 영상화 1차 (Rooftop Music) — 믹스 mp3 → 유튜브용 mp4.

비주얼 = 주제 분위기 배경(gpt-image-1, 가로) + Ken Burns 미세 모션 + 오디오
비주얼라이저(ffmpeg showwaves) + 텍스트(주제 제목 + 곡 전환 시 현재 곡 제목).
16:9 1920x1080 H.264, 믹스 길이만큼, 믹스 오디오 그대로.

⚠️ 가사 자막은 2차(#6b) — 이번엔 제외.

배경 이미지는 gpt-image-1(기존 패턴 재사용, 가로 1536x1024)로 1장 만들어
R2 music-videos/{slug}/bg.png 에 보존(멱등). 완성 mp4 는 music-videos/{slug}/{id}.mp4.
ffmpeg 헬퍼는 백곰 엔진과 결합하지 않도록 이 모듈에 소량 복제(subprocess).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import platform
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx

from adapters import r2_storage

logger = logging.getLogger(__name__)

W, H = 1920, 1080
FPS = 30
# 채널 톤 컬러(디자인 액센트: 보라·시안) — 비주얼라이저 색.
_VIZ_COLORS = "0x8b5cf6|0x22d3ee"
_IMAGE_MODEL = "gpt-image-1"
_IMAGE_SIZE = "1536x1024"  # 가로
_IMAGE_QUALITY = "high"
_BG_NAME = "bg.png"

# ── Remotion(#18) — 굵은 둥근 바 비주얼라이저. USE_REMOTION 토글, 실패 시 ffmpeg 폴백.
_REMOTION_DIR = Path(__file__).resolve().parents[1] / "remotion"
_REMOTION_TIMEOUT = int(os.getenv("REMOTION_TIMEOUT", "1200"))  # 초


# ── ffmpeg 헬퍼(디커플링 복제) ───────────────────────────────────────────
def _require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"{tool} 가 PATH 에 없습니다 — 영상 합성에 ffmpeg 필요.")


def _run(args: list[str], cwd: Path | None = None) -> None:
    result = subprocess.run(
        ["ffmpeg", "-y", *args],
        cwd=(str(cwd) if cwd else None),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg 오류:\n{result.stderr[-2500:]}")


def _duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nokey=1:noprint_wrappers=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip())


def _fetch(url_or_path: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if url_or_path.startswith(("http://", "https://")):
        with httpx.Client(timeout=300.0, follow_redirects=True) as c:
            r = c.get(url_or_path)
            r.raise_for_status()
            dest.write_bytes(r.content)
    else:
        shutil.copy(url_or_path, dest)


def _font_candidates(system: str | None = None) -> list[str]:
    """한국어 폰트 후보 경로(우선순위 순). env SUBTITLE_FONT_PATH 가 최우선."""
    system = system or platform.system()
    cands: list[str] = []
    env = os.getenv("SUBTITLE_FONT_PATH")
    if env:
        cands.append(env)
    if system == "Windows":
        fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        cands += [
            os.path.join(fonts, "malgun.ttf"),    # 맑은 고딕
            os.path.join(fonts, "malgunbd.ttf"),  # 맑은 고딕 Bold
            os.path.join(fonts, "gulim.ttc"),     # 굴림
            os.path.join(fonts, "batang.ttc"),    # 바탕
        ]
    elif system == "Darwin":  # macOS
        cands += [
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
            "/Library/Fonts/AppleGothic.ttf",
        ]
    else:  # Linux 등
        cands += [
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        ]
    return cands


def _resolve_font(system: str | None = None) -> str:
    """존재하는 첫 폰트 파일 경로를 반환. 하나도 없으면 본 경로 목록과 함께 에러."""
    cands = _font_candidates(system)
    for p in cands:
        if p and os.path.exists(p):
            return p
    raise RuntimeError(
        "한국어 자막 폰트를 찾지 못했습니다. 다음 경로를 확인했습니다:\n  "
        + "\n  ".join(cands)
        + "\n→ SUBTITLE_FONT_PATH 환경변수로 폰트 파일(.ttf/.ttc) 경로를 지정하세요."
    )


def _stage_font(work: Path, system: str | None = None) -> str:
    """결정된 한국어 폰트를 work 로 복사하고 **상대경로** fontfile 인자를 반환.

    절대경로(특히 Windows 'C:\\...\\malgun.ttf')를 filtergraph 에 직접 쓰면 ':'·'\\' 가
    파싱을 깨뜨린다. 폰트를 work/font.<ext> 로 복사하고 cwd=work + 상대명으로 회피한다
    (백곰 sayeon 의 cwd+상대명 선례와 동일). drawtext 는 항상 fontfile= 만 쓴다 —
    font=(이름) fontconfig 조회는 Windows 에서 'Cannot load default config file' 의
    원인이라 절대 쓰지 않는다.
    """
    src = _resolve_font(system)
    ext = os.path.splitext(src)[1].lower() or ".ttf"
    shutil.copy(src, work / f"font{ext}")
    return f"fontfile=font{ext}"


# ── 배경 이미지 (gpt-image-1, 가로) ──────────────────────────────────────
def image_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def _bg_prompt(theme: dict) -> str:
    genre = theme.get("genre", "")
    mood = theme.get("mood", "")
    situation = theme.get("situation", "")
    style = theme.get("style_prompt", "")
    return (
        f"Atmospheric cinematic background scene for {genre} music. "
        f"Mood: {mood}. Setting: {situation}. {style}. "
        "Wide horizontal 16:9 composition, soft depth of field, rich ambient lighting, "
        "no text, no words, no letters, no people in focus. Immersive, aesthetic, high quality."
    )


# ── 썸네일 GPT 프롬프트 (After Rain 스타일) ─────────────────────────────
# 주제 → 썸네일 배경 장소 매핑(데이터). 첫 매칭 우선. tone 은 라이팅 톤 결정.
_THUMB_SCENES: list[tuple[tuple[str, ...], str, str]] = [
    (("카페", "cafe", "coffee", "커피", "재즈", "jazz", "브런치", "라운지", "lounge"),
     "a cozy cafe interior with warm window light and coffee on a wooden table", "bright"),
    (("출근", "퇴근", "운전", "드라이브", "commute", "drive", "driving", "시티팝",
      "city pop", "citypop", "도로", "road", "highway", "통근"),
     "an early-morning city road seen from inside a car, soft dawn light through the windshield",
     "bright"),
    (("운동", "헬스", "러닝", "조깅", "workout", "gym", "running", "fitness", "exercise", "트레이닝"),
     "an outdoor running track and a modern gym, bright energetic daylight", "bright"),
    (("공부", "스터디", "집중", "study", "studying", "focus", "독서", "reading", "작업", "desk"),
     "a tidy study desk beside a bright window with open books and a warm lamp", "bright"),
    (("이별", "헤어", "슬픔", "눈물", "breakup", "sad", "lonely", "발라드", "ballad", "그리움"),
     "a rain-streaked window at night overlooking a quiet city street with soft neon glow",
     "moody"),
    (("수면", "잠", "취침", "자장", "sleep", "bedtime", "꿈", "밤하늘", "lullaby"),
     "a calm dark bedroom at night with a starry sky outside and soft moonlight", "moody"),
]

# 매핑 미스 시 톤만 가르는 mood 힌트(밝음 기본, 아래 단어 매칭되면 무드).
_MOODY_HINTS = (
    "밤", "차분", "잔잔", "쓸쓸", "감성", "새벽", "비", "night", "calm", "chill",
    "mellow", "moody", "lonely", "dark", "rain",
)


def _thumb_scene(theme: dict) -> tuple[str, str]:
    """주제(situation/genre/mood/제목) → (배경 장소, 톤). 미매칭 시 mood 기반 일반 장면."""
    hay = " ".join(
        str(theme.get(k, "")) for k in ("situation", "genre", "mood", "title_kr", "slug")
    ).lower()
    for keys, scene, tone in _THUMB_SCENES:
        if any(k.lower() in hay for k in keys):
            return scene, tone
    if any(h.lower() in hay for h in _MOODY_HINTS):
        return "a moody atmospheric lifestyle scene with soft low light and gentle bokeh", "moody"
    return "a bright clean lifestyle scene with soft natural light", "bright"


def _thumb_person() -> str:
    """싱글/커플 + 성별 다양화(매 호출 랜덤)."""
    return random.choice([
        "a young woman", "a young man", "a young woman",
        "a young couple", "a young couple",
    ])


def _thumb_subject() -> str:
    """#27 인물 비중 — 80% 풍경(사람 없음) / 15% 먼 인물(얼굴 강조 X) / 5% 애견·동물."""
    r = random.random()
    if r < 0.80:
        return "No people — focus entirely on the landscape, architecture and nature."
    if r < 0.95:
        return "A distant figure as a small part of the scene, seen from afar, no face emphasis."
    return "A cute dog or small animal naturally in the scene (e.g. swimming or strolling)."


def _thumb_subject_kr() -> str:
    """#31 인물 비중(한국어) — 80% 풍경 / 15% 먼 인물(얼굴X) / 5% 애견·동물."""
    r = random.random()
    if r < 0.80:
        return "사람은 없이 풍경·건축·자연에만 집중."
    if r < 0.95:
        return "멀리 작게 보이는 사람 한둘(얼굴은 보이지 않게, 거리감 있게)."
    return "수영하거나 거니는 강아지 등 작은 동물 한 마리가 자연스럽게."


# #31 무드별 글로벌 도시 풀(한국어) — 같은 무드라도 매번 다른 도시(랜덤). 시네마틱 표현 제외.
_CITY_POOLS: dict[str, dict] = {
    "citypop": {
        "keys": ["시티팝", "citypop", "city pop", "드라이브", "drive", "운전", "출근", "퇴근"],
        "cities": ["뉴욕 맨해튼 도심 거리", "도쿄 시부야 거리", "서울 강남 도심",
                   "홍콩 도심 거리", "LA 다운타운", "시드니 하버 도심"],
        "scene": "고층 빌딩과 활기찬 거리", "time": "맑은 한낮",
        "tone": "맑고 청량하고 밝은 분위기", "light": "따뜻한 햇살",
        "accent": "도시적 세련미와 여행 감성",
    },
    "cafe": {
        "keys": ["카페", "cafe", "재즈", "jazz", "커피", "coffee", "브런치", "라운지"],
        "cities": ["파리 골목 카페거리", "서울 한남동 카페거리", "교토 청수사 골목",
                   "비엔나 구시가 거리", "멜버른 레인웨이 골목"],
        "scene": "감성적인 카페거리와 창가", "time": "맑은 오후",
        "tone": "맑고 청량하고 밝은 분위기", "light": "따뜻한 자연광",
        "accent": "여유로운 여행 감성",
    },
    "ballad": {
        "keys": ["이별", "헤어", "breakup", "발라드", "ballad", "슬픔", "sad", "그리움", "눈물"],
        "cities": ["비 오는 뉴욕 거리", "도쿄 밤거리", "서울 한강 야경",
                   "런던 골목", "시애틀 비 오는 거리"],
        "scene": "고요한 거리와 반짝이는 불빛", "time": "저녁 무렵",
        "tone": "차분하고 감성적인 분위기", "light": "은은한 자연광",
        "accent": "잔잔한 여행 감성",
    },
    "workout": {
        "keys": ["운동", "헬스", "workout", "gym", "러닝", "running", "동기", "motivat", "fitness"],
        "cities": ["바르셀로나 해변", "산타모니카 해변", "시드니 하버", "두바이 도심"],
        "scene": "탁 트인 해변과 도시 전경", "time": "맑은 아침",
        "tone": "맑고 청량하고 밝은 분위기", "light": "밝은 햇살",
        "accent": "활기찬 여행 감성",
    },
    "sleep": {
        "keys": ["수면", "잠", "취침", "sleep", "공부", "스터디", "study", "집중", "focus", "독서", "lofi"],
        "cities": ["교토 일본 정원", "노르웨이 피요르드", "알프스 산골 마을", "제주 호수"],
        "scene": "고요한 자연 풍경", "time": "맑은 새벽",
        "tone": "고요하고 평온한 분위기", "light": "부드러운 자연광",
        "accent": "차분한 여행 감성",
    },
    "summer": {
        "keys": ["여름", "summer", "수영", "해변", "beach", "pool", "트로피컬", "tropical"],
        "cities": ["마이애미 해변", "산토리니", "발리 해변", "하와이 해변", "칸쿤"],
        "scene": "푸른 바다와 야자수", "time": "맑은 한낮",
        "tone": "맑고 청량하고 밝은 분위기", "light": "눈부신 햇살",
        "accent": "시원한 여행 감성",
    },
}


def _city_bucket(theme: dict, viz_spec: dict | None) -> str:
    """곡 → 도시 풀 키. season=summer 우선, 이후 mood/location 카테고리, 끝으로 키워드."""
    vs = viz_spec or {}
    if str(vs.get("season", "")).lower() == "summer":
        return "summer"
    mc = str(vs.get("mood_category", "")).lower()
    lc = str(vs.get("location_category", "")).lower()
    if mc == "sad":
        return "ballad"
    if mc == "energetic" or lc == "beach":
        return "workout"
    if mc == "focus" or lc in ("nature", "home"):
        return "sleep"
    if lc == "cafe":
        return "cafe"
    hay = _haystack_theme(theme)
    for key, pool in _CITY_POOLS.items():
        if any(k.lower() in hay for k in pool["keys"]):
            return key
    return "citypop"


def _haystack_theme(theme: dict) -> str:
    return " ".join(
        str(theme.get(k, "")) for k in ("genre", "mood", "situation", "title_kr", "slug")
    ).lower()


def _thumb_trend_hint() -> str:
    """최신 트렌드 mood_keywords 가 있으면 톤에 살짝 섞을 한 줄(없으면 빈값 → 회귀 0)."""
    try:
        from services import music_trend
        insight = music_trend.get_latest() or {}
    except Exception:  # noqa: BLE001 - 트렌드 미설정/오류는 영감 생략(주제는 불변)
        return ""
    kws = [k.strip() for k in (insight.get("mood_keywords") or []) if isinstance(k, str) and k.strip()]
    if not kws:
        return ""
    return f", with a {', '.join(kws[:2])} feel"


def build_thumbnail_prompt(theme: dict, viz_spec: dict | None = None) -> str:
    """주제 → ChatGPT(gpt-image)에 붙여넣을 영어 썸네일 프롬프트(#8 큐 복사용).

    #27: viz_spec 가 있으면 **풍경·도시·자연 중심**(인물 거의 없음, 80/15/5) + location_en·
    씬키워드 강조 + 색감, **텍스트 0개**(글자는 Remotion 이 그림). viz_spec 없으면 #17 동작.
    배경은 데이터(_THUMB_SCENES) 매핑. 영어 한 문단.
    """
    scene, tone = _thumb_scene(theme)
    person = _thumb_person()

    if viz_spec:
        # #31: 한국어 톤(맑고 청량하고 밝은 사실적 풍경) + 무드별 글로벌 도시 랜덤.
        # #32: 금지어(cinematic/moody/dramatic/neon) 미사용, 밝은 무드는 '맑은 한낮' 강제.
        bucket = _city_bucket(theme, viz_spec)
        pool = _CITY_POOLS[bucket]
        location_label = random.choice(pool["cities"])
        bright = bucket in ("citypop", "cafe", "workout", "summer")
        bright_force = "맑은 한낮의 환한 자연광, 화창한 날씨, " if bright else ""
        return (
            f"가로형 롱폼사이즈 플레이리스트 썸네일 배경 이미지. "
            f"{location_label}, {pool['scene']}, {pool['time']}. "
            f"{bright_force}"
            f"맑은 날의 사실적인 풍경 사진, {pool['tone']}, {pool['light']}, "
            f"깊이감 있는 원근감, {pool['accent']}. "
            f"{_thumb_subject_kr()} "
            f"실제 사진처럼 선명하고 고급스럽게. "
            f"사람 얼굴은 보이지 않게, 글자 없음, 영어 없음, 로고 없음, 워터마크 없음."
        )

    # viz_spec 없음 → #17 동작(회귀 0).
    trend = _thumb_trend_hint()
    tone_desc = (
        "bright, clean, airy lighting"
        if tone == "bright"
        else "moody, warm low-key lighting"
    )
    return (
        f"YouTube playlist thumbnail, 16:9 aspect ratio. "
        f"Background: {scene}. "
        f"{person} in the scene, natural candid pose. "
        f'Large bold "PLAY LIST" text overlay as the main title. '
        f"{tone_desc}{trend}. "
        f"Cinematic, high quality, photographic, no extra random text, no watermark."
    )


def generate_background(theme: dict, out_path: str, *, force: bool = False) -> str:
    """주제 분위기 배경 1장(gpt-image-1, 가로) → out_path. R2 멱등(있으면 다운로드).

    R2 music-videos/{slug}/bg.png 에 보존. force=True 면 무조건 재생성.
    """
    slug = theme.get("slug") or theme.get("theme_slug") or "untitled"
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # 멱등: 이미 R2 에 있으면 재사용(비용 0).
    if not force and r2_storage.music_video_exists(slug, _BG_NAME):
        logger.info("[video] 배경 이미 존재 — 재사용 slug=%s", slug)
        r2_storage.download_music_object(
            r2_storage.music_video_key(slug, _BG_NAME), str(out)
        )
        return str(out)

    if not image_available():
        raise RuntimeError("OPENAI_API_KEY 미설정 — 배경 이미지 생성 불가")

    from openai import OpenAI  # 기존 의존성

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    resp = client.images.generate(
        model=_IMAGE_MODEL,
        prompt=_bg_prompt(theme),
        size=_IMAGE_SIZE,
        quality=_IMAGE_QUALITY,
        n=1,
    )
    out.write_bytes(base64.b64decode(resp.data[0].b64_json))
    logger.info("[video] 배경 생성 완료 slug=%s", slug)

    # R2 보존(실패해도 합성은 로컬 파일로 계속).
    try:
        if r2_storage.is_available():
            r2_storage.upload_music_video(str(out), slug, _BG_NAME, content_type="image/png")
    except Exception as e:  # noqa: BLE001
        logger.warning("[video] 배경 R2 저장 실패: %s", e)
    return str(out)


# ── Remotion 합성(#18) ────────────────────────────────────────────────────
def remotion_enabled() -> bool:
    """USE_REMOTION 토글 + node + remotion/ 디렉터리가 모두 갖춰졌을 때만 True.

    off/미설치면 False → 기존 ffmpeg 경로(회귀 0). 기본값 off(대표가 배포 후 on).
    """
    flag = (os.getenv("USE_REMOTION") or "").strip().lower()
    if flag not in ("1", "true", "on", "yes"):
        return False
    if shutil.which("node") is None:
        logger.warning("[video] USE_REMOTION on 이지만 node 가 PATH 에 없음 → ffmpeg 폴백")
        return False
    if not (_REMOTION_DIR / "render.mjs").exists():
        logger.warning("[video] USE_REMOTION on 이지만 remotion/render.mjs 없음 → ffmpeg 폴백")
        return False
    return True


def _render_remotion(
    bg_path: str,
    audio_path: str,
    out_path: str,
    *,
    tracks: list[dict],
    mood: str,
    duration: float,
    viz_spec: dict | None = None,
) -> str:
    """Remotion(둥근 바 + 인트로 + 텍스트) 렌더 → mp4. 실패 시 예외(호출부가 ffmpeg 폴백)."""
    props = {
        "tracks": [
            {
                "title": (t.get("title") or "").strip(),
                "start_sec": float(t.get("start_sec") or 0.0),
            }
            for t in tracks
        ],
        "mood": mood,
        "durationSec": round(duration, 3),
        "vizSpec": viz_spec or None,
    }
    cmd = [
        "node", str(_REMOTION_DIR / "render.mjs"),
        "--audio", os.path.abspath(str(audio_path)),
        "--bg", os.path.abspath(str(bg_path)),
        "--out", os.path.abspath(str(out_path)),
        "--props", json.dumps(props, ensure_ascii=False),
    ]
    result = subprocess.run(
        cmd, cwd=str(_REMOTION_DIR), capture_output=True, text=True,
        timeout=_REMOTION_TIMEOUT,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Remotion 렌더 오류:\n{result.stderr[-2500:]}")
    return str(out_path)


def _extract_first_frame(mp4_path: str, out_png: str) -> str:
    """mp4 0초 프레임 → png(#20 유튜브 썸네일 = 영상 첫 화면 100% 일치)."""
    subprocess.run(
        ["ffmpeg", "-y", "-i", os.path.abspath(str(mp4_path)),
         "-vframes", "1", "-q:v", "2", os.path.abspath(str(out_png))],
        check=True, capture_output=True, text=True,
    )
    return str(out_png)


# ── ffmpeg 합성 ──────────────────────────────────────────────────────────
def _build_filter(
    tracks: list[dict], title_kr: str, duration: float, work: Path, viz: str, font: str,
    static_bg: bool = False,
) -> str:
    """배경 + 비주얼라이저 + drawtext(주제·곡 제목) filter_complex 구성.

    static_bg=False: 배경 Ken Burns(느린 줌). True: 정지화면(줌 없음 — 썸네일 배경용).
    textfile 은 work 기준 **상대명**만 쓴다(ffmpeg cwd=work). 절대경로의 '\\'·':' 가
    filtergraph 파싱을 깨뜨리는 걸 회피한다(Windows 호환).
    """
    total_frames = int(duration * FPS) + FPS  # 여유 프레임(루프 reset 회피)

    # 1) 배경 — 정지(썸네일) 또는 Ken Burns(느린 줌) → 1920x1080.
    if static_bg:
        bg = (
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},setsar=1,format=yuv420p[bg];"
        )
    else:
        bg = (
            f"[0:v]scale={W*1.2:.0f}:{H*1.2:.0f}:force_original_aspect_ratio=increase,"
            f"crop={W*1.2:.0f}:{H*1.2:.0f},"
            f"zoompan=z='min(zoom+0.0004,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={total_frames}:s={W}x{H}:fps={FPS},setsar=1,format=yuv420p[bg];"
        )
    # 2) 오디오 비주얼라이저.
    if viz == "showcqt":
        v = f"[1:a]showcqt=s={W}x220:fps={FPS}[wave];"
    elif viz == "showspectrum":
        v = f"[1:a]showspectrum=s={W}x220:mode=combined:color=intensity:slide=scroll:scale=cbrt[wave];"
    else:  # showwaves(기본)
        v = (
            f"[1:a]showwaves=s={W}x220:mode=cline:rate={FPS}:colors={_VIZ_COLORS}[wave];"
        )
    # 3) 비주얼라이저를 하단에 오버레이.
    overlay = "[bg][wave]overlay=x=0:y=H-h[bgw];"

    # 4) drawtext — 주제 제목(상단 고정) + 곡 제목(전환 구간).
    chain = bg + v + overlay
    prev = "bgw"
    # 주제 제목 — work 기준 상대명(title.txt). 항상 표시.
    (work / "title.txt").write_text(title_kr or "", encoding="utf-8")
    chain += (
        f"[{prev}]drawtext={font}:textfile=title.txt:fontcolor=white:fontsize=54:"
        f"box=1:boxcolor=black@0.45:boxborderw=18:x=(w-text_w)/2:y=56[lbl_t];"
    )
    prev = "lbl_t"

    # 곡 제목 — 컷(duration) 안에서만. start_sec >= duration 인 곡은 스킵,
    # enable 끝은 min(다음 곡 시작, duration) 로 클램프(짧은 컷에서 구간 역전 방지).
    for i, t in enumerate(tracks):
        title = (t.get("title") or "").strip()
        if not title:
            continue
        start = float(t.get("start_sec") or 0.0)
        if start >= duration:
            continue  # 컷 이후 시작 곡은 표시 안 함
        nxt = (
            float(tracks[i + 1].get("start_sec"))
            if i + 1 < len(tracks) and tracks[i + 1].get("start_sec") is not None
            else duration
        )
        end = min(nxt, duration)
        if end <= start:
            continue  # 표시 구간 없음
        tf_name = f"song_{i}.txt"
        (work / tf_name).write_text(title, encoding="utf-8")
        lbl = f"lbl{i}"
        chain += (
            f"[{prev}]drawtext={font}:textfile={tf_name}:fontcolor=white:fontsize=40:"
            f"box=1:boxcolor=black@0.4:boxborderw=12:x=(w-text_w)/2:y=h-th-300:"
            f"enable='between(t,{start:.3f},{end:.3f})'[{lbl}];"
        )
        prev = lbl

    chain += f"[{prev}]format=yuv420p[vout]"
    return chain


def compose_video(
    bg_path: str,
    audio_path: str,
    out_path: str,
    *,
    tracks: list[dict],
    title_kr: str,
    duration: float,
    viz: str | None = None,
    static_bg: bool = False,
) -> str:
    """배경 이미지 + 믹스 오디오 + 비주얼라이저 + 텍스트 → mp4(1920x1080 H.264).

    static_bg=True 면 Ken Burns 줌 없이 정지화면(썸네일 배경용).
    직접 호출 가능(로컬 bg/audio 경로). make_video 가 R2 연동까지 감싼다.
    """
    _require_ffmpeg()
    viz = viz or os.getenv("MUSIC_VIZ", "showwaves")
    work = Path(tempfile.mkdtemp(prefix="mv_"))
    try:
        # 폰트는 work 로 복사해 상대명 사용. 입력/출력은 절대경로(=CLI 인자, filtergraph
        # 밖이라 OS 무관)로 둔다 — filtergraph 안에는 상대 textfile/fontfile 만 들어간다.
        font = _stage_font(work)
        filt = _build_filter(tracks, title_kr, duration, work, viz, font, static_bg=static_bg)
        _run([
            "-loop", "1", "-i", os.path.abspath(str(bg_path)),
            "-i", os.path.abspath(str(audio_path)),
            "-filter_complex", filt,
            "-map", "[vout]", "-map", "1:a",
            "-t", f"{duration:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            os.path.abspath(str(out_path)),
        ], cwd=work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return str(out_path)


def make_video(
    theme: dict,
    mix: dict,
    *,
    seconds: float | None = None,
    viz: str | None = None,
    force_bg: bool = False,
    background_path: str | None = None,
    viz_spec: dict | None = None,
    persist: bool = True,
) -> dict:
    """주제 + 믹스 → 배경 → 합성(Remotion/ffmpeg) → mp4 → R2. 영상 메타 반환.

    background_path: 주면 그 이미지(대표가 올린 깨끗한 이미지)를 배경으로 쓴다.
    viz_spec(#20): 곡 분석. None 이고 Remotion on 이면 캐시→분석으로 채운다.
    Remotion 경로(USE_REMOTION on): 인트로·텍스트·이퀄 + 첫프레임 자동 썸네일.
    off/실패 시 기존 ffmpeg 폴백(인트로·텍스트·자동썸네일 없음, 회귀 0).
    seconds: 짧은 테스트 컷(앞 N초만). 미지정 시 믹스 전체 길이.
    persist=False(#25 풀 테스트): record_pending(큐 DB) 기록을 건너뛴다(영구 저장 X).
    """
    _require_ffmpeg()
    slug = theme.get("slug") or theme.get("theme_slug") or mix.get("theme_slug") or "untitled"
    mp3_url = mix.get("mp3_url")
    if not mp3_url:
        raise ValueError("mix['mp3_url'] 이 필요합니다.")
    tracks = mix.get("tracks") or []
    title_kr = theme.get("title_kr") or theme.get("title") or slug
    video_id = mix.get("mix_id") or "video"
    use_remotion = remotion_enabled()

    # #20 곡 분석(viz_spec) — Remotion 경로에서만(회귀 안전). 캐시 우선.
    # #33 B: 캐시가 오래돼 location_en(WHERE 라벨) 등 신규 키가 없으면 fallback 으로 backfill.
    if use_remotion and viz_spec is None:
        try:
            from services import music_uploads, music_viz_analyzer
            viz_spec = music_uploads.get_viz_spec(video_id) or music_viz_analyzer.analyze_song(theme, mix)
            if isinstance(viz_spec, dict) and not viz_spec.get("location_en"):
                fb = music_viz_analyzer._fallback_spec(theme)
                for k, v in fb.items():
                    viz_spec.setdefault(k, v)
                logger.info("[video] viz_spec location_en backfill=%s", viz_spec.get("location_en"))
        except Exception as e:  # noqa: BLE001 - 분석 실패해도 렌더는 진행(텍스트 기본색)
            logger.warning("[video] 곡 분석 실패(기본값 진행): %s", e)
            viz_spec = None

    work = Path(tempfile.mkdtemp(prefix="makevid_"))
    try:
        # 오디오·배경 준비.
        audio = work / "mix.mp3"
        _fetch(mp3_url, audio)
        full = _duration(str(audio))
        duration = min(seconds, full) if seconds else full

        # 배경: 깨끗한 이미지(background_path) 우선, 없으면 gpt-image-1 생성.
        bg = work / _BG_NAME
        static_bg = bool(background_path)
        if static_bg:
            _fetch(background_path, bg)  # R2 URL/로컬 경로 모두 처리
        else:
            generate_background(theme, str(bg), force=force_bg)

        out = work / f"{video_id}.mp4"

        # 합성: Remotion(인트로+텍스트+이퀄) 우선, 실패/off 면 ffmpeg 폴백(회귀 0).
        rendered = False
        if use_remotion:
            mood_hint = " ".join(
                str(theme.get(k, "")) for k in ("mood", "genre", "situation")
            ).strip()
            try:
                _render_remotion(
                    str(bg), str(audio), str(out),
                    tracks=tracks, mood=mood_hint, duration=duration, viz_spec=viz_spec,
                )
                rendered = True
                logger.info("[video] Remotion 렌더 완료 slug=%s", slug)
            except Exception as e:  # noqa: BLE001 - Remotion 불안정 대비 ffmpeg 폴백
                logger.warning("[video] Remotion 실패 → ffmpeg 폴백: %s", e)
        if not rendered:
            compose_video(
                str(bg), str(audio), str(out),
                tracks=tracks, title_kr=title_kr, duration=duration, viz=viz, static_bg=static_bg,
            )

        video_url = str(out)
        if r2_storage.is_available():
            try:
                video_url = r2_storage.upload_music_video(
                    str(out), slug, f"{video_id}.mp4", content_type="video/mp4"
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("[video] mp4 R2 업로드 실패, 로컬 경로 사용: %s", e)
        else:
            logger.warning("[video] R2 미설정 — mp4 가 로컬에만 있습니다.")

        # #20 첫프레임 추출(유튜브 썸네일 = 영상 첫 화면 100% 일치). Remotion 렌더일 때만.
        # ⚠️ 대표가 올린 '깨끗한 배경'(thumbnail_r2_key)과 충돌하지 않게 **별도 키**에 저장한다
        #    (덮어쓰면 재렌더 시 텍스트 위에 텍스트). 게이트는 그대로(대표 업로드 유지).
        frame_thumb_key: str | None = None
        frame_thumb_url: str | None = None
        if rendered:
            try:
                thumb_png = work / f"{video_id}_frame.png"
                _extract_first_frame(str(out), str(thumb_png))
                if r2_storage.is_available():
                    frame_name = f"{video_id}_frame.png"
                    frame_thumb_url = r2_storage.upload_music_video(
                        str(thumb_png), slug, frame_name, content_type="image/png"
                    )
                    frame_thumb_key = r2_storage.music_video_key(slug, frame_name)
            except Exception as e:  # noqa: BLE001 - 첫프레임 실패해도 영상은 유효
                logger.warning("[video] 첫프레임 추출/업로드 실패: %s", e)

        # 검토 대기 큐(#8): pending 행 기록 + GPT 프롬프트(viz_spec 색감 반영) + viz_spec 캐시.
        gpt_prompt = build_thumbnail_prompt(theme, viz_spec)
        if persist:
            try:
                from services.music_uploads import record_pending
                record_pending(
                    slug, video_id, mp4_url=video_url, title_kr=title_kr,
                    genre=theme.get("genre", ""), mood=theme.get("mood", ""),
                    gpt_prompt=gpt_prompt, viz_spec=viz_spec,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("[video] 검토 큐 기록 실패(영상은 생성됨): %s", e)

            # #33 D-10 다국어 자동 번역 — 생성 시점에 미리 채워 검수 카드가 '번역 없음' 안 뜨게.
            # 이미 있으면 스킵(재렌더 시 중복 번역·비용 방지). best-effort(실패해도 영상은 유효).
            try:
                from services import music_translate, music_uploads as _mu
                if not _mu.get_localizations(video_id):
                    _lyrics = "\n".join(
                        (t.get("lyrics") or "").strip() for t in tracks if (t.get("lyrics") or "").strip()
                    )
                    src = music_translate.detect_source_lang(_lyrics or title_kr or "ko-")
                    loc = {
                        "source_lang": src,
                        "meta": music_translate.generate_localizations(theme, viz_spec, _lyrics),
                        "lyrics": music_translate.translate_lyrics(_lyrics, src) if _lyrics.strip() else {},
                        "hashtags": music_translate.generate_hashtags(theme, viz_spec),
                    }
                    _mu.set_localizations(video_id, loc)
                    logger.info("[video] 다국어 자동 번역 저장 video_id=%s langs=%d", video_id, len(loc["meta"]))
            except Exception as e:  # noqa: BLE001 - 번역 실패해도 영상은 생성됨
                logger.warning("[video] 다국어 자동 번역 실패(검수 UI 에서 생성 가능): %s", e)

        return {
            "video_id": video_id,
            "video_url": video_url,
            "duration": round(duration, 3),
            "slug": slug,
            "gpt_prompt": gpt_prompt,
            "viz_spec": viz_spec,
            "frame_thumb_key": frame_thumb_key,
            "frame_thumb_url": frame_thumb_url,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)
