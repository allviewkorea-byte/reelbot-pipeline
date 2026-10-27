"""운동 채널 배경 이미지 자동화(PR-1) — 생성 · 자동 검수 · 렌더 정합 표식.

지금까지 운동 채널 배경은 대표가 폰 ChatGPT 로 만들어 "깨끗한 이미지 업로드"로 올렸다.
이 모듈은 그 손 단계를 대신한다.

  ① generate_reviewed  — GPT-Image-2.5 로 1장 생성 → Claude 비전으로 검수.
                         불합격이면 사유를 다음 프롬프트에 "반드시 피할 것"으로 붙여 재생성(최대 3회).
                         합격본은 R2 축별 보관함(music-auto-bg/{축}/)에 쌓는다.
                         전부 불합격이면 같은 축 합격본(최근 30일) 중 1장을 재사용하고,
                         보관함이 비었을 때만 이미지 없음(ok=False → 블랙 배경).
  ② attach_after_render — 렌더가 끝난 뒤 그 이미지를 대표 업로드와 **같은 자리**
                         (R2 music-thumbnails/{slug}/{mix_id}.png + thumbnail_r2_key)에 둔다.
                         그래야 재렌더·썸네일·검토대기 표시가 기존 경로를 그대로 탄다.
  ③ record_render / matching_render — "이 mp4 가 지금 배경으로 렌더된 것인가"를 R2
                         사이드카(music-videos/{slug}/{mix_id}_render.json)로 판정한다.
                         publish 가 재렌더를 건너뛸지 여기서 정한다. 애매하면 None(=재렌더).

★ 운동 채널 전용. where 는 이 모듈을 한 줄도 타지 않는다(호출부가 채널로 가른다).
★ music_video.py 무수정 — 이미지는 make_video(background_path=...) 로 바깥에서 넘긴다.
★ gpt-image-1 경로(music_video.generate_background 의 옛 코드)는 되살리지 않는다.

모델·사이즈·quality 는 env 로 덮을 수 있다. 기본값은 0단계에서 OpenAI 공식 도메인 검색으로
확인한 값이다(문서 원문 직접 열람은 네트워크 정책상 불가). 첫 실호출 로그가 확인 절차다.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import random
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# ── 설정(env 로 덮기) ──────────────────────────────────────────────────
_DEFAULT_MODEL = "gpt-image-2.5-flare"
_DEFAULT_SIZE = "2048x1152"  # 16:9, 양 변 16의 배수, 2560x1440(실험 구간) 미만
_DEFAULT_QUALITY = "high"
# 이미지 출력 토큰 단가(USD / 1M) — 비용 추정 로그용. 공식 가격표가 바뀌면 env 로 덮는다.
_DEFAULT_OUTPUT_USD_PER_M = 30.0
_MAX_ATTEMPTS = 3  # 1회 + 불합격 시 재생성 최대 2회(1회 ≈ 20초 — 6분 상한 안에 충분) — where
# 운동(2026-10-27 대표 승인): 인물 2회 → 불합격이면 인물 없는 장면 2회(총 4회). 옛 배경 재사용은 그 뒤 최후 수단.
_WORKOUT_PEOPLE_ATTEMPTS = 2
_WORKOUT_MAX_ATTEMPTS = 4

# 단계 상한(2026-10: 수동 생성이 이미지 단계에서 멈춘 사례). SDK 기본값은 OpenAI·Anthropic 모두
# read timeout 600초 × 재시도 2회라, 상한 없이는 이미지 단계 하나가 1시간 넘게 잡을 수 있었다.
# 넘거나 예외면 이미지 없이(bg_path=None) 기존 블랙 배경 렌더로 계속한다. env 로 덮을 수 있다.
_DEFAULT_IMAGE_TIMEOUT_SEC = 180.0   # OpenAI 이미지 1회(재시도 0)
_DEFAULT_REVIEW_TIMEOUT_SEC = 60.0   # Claude 검수 1회(재시도 0)
_DEFAULT_PREPARE_TIMEOUT_SEC = 480.0  # prepare_for_render 전체(생성·검수·재생성 포함) 8분(운동 4회 시도분)
_FFMPEG_TIMEOUT_SEC = 60             # PNG 변환·검수용 축소

# 검수용 축소본 — Claude 이미지 입력 한도(장당 5MB) 안에 넉넉히 들게 1024px JPEG 로.
_REVIEW_MAX_PX = 1024


def _env(key: str, default: str) -> str:
    return (os.getenv(key) or default).strip()


def _float_env(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except ValueError:
        return default


def image_timeout_sec() -> float:
    return _float_env("MUSIC_IMAGE_TIMEOUT_SEC", _DEFAULT_IMAGE_TIMEOUT_SEC)


def review_timeout_sec() -> float:
    return _float_env("MUSIC_IMAGE_REVIEW_TIMEOUT_SEC", _DEFAULT_REVIEW_TIMEOUT_SEC)


def prepare_timeout_sec() -> float:
    return _float_env("MUSIC_IMAGE_PREPARE_TIMEOUT_SEC", _DEFAULT_PREPARE_TIMEOUT_SEC)


def image_model() -> str:
    return _env("MUSIC_IMAGE_MODEL", _DEFAULT_MODEL)


def image_size() -> str:
    return _env("MUSIC_IMAGE_SIZE", _DEFAULT_SIZE)


def image_quality() -> str:
    return _env("MUSIC_IMAGE_QUALITY", _DEFAULT_QUALITY)


def _output_usd_per_m() -> float:
    try:
        return float(_env("MUSIC_IMAGE_OUTPUT_USD_PER_M", str(_DEFAULT_OUTPUT_USD_PER_M)))
    except ValueError:
        return _DEFAULT_OUTPUT_USD_PER_M


def review_model() -> str:
    from config import CLAUDE_MODEL
    return _env("MUSIC_IMAGE_REVIEW_MODEL", CLAUDE_MODEL)


WHERE_CHANNEL = "rooftop_music"


def is_where_auto(channel: str | None) -> bool:
    """where 자동 배경 프로필을 쓸지 — 채널이 'rooftop_music' 으로 **명시**된 경우만(자동 회차).

    where 수동 화면은 채널을 None 으로 보내므로 이 프로필을 타지 않는다(기존 동작 그대로).
    """
    return isinstance(channel, str) and channel.strip() == WHERE_CHANNEL


def wants_auto_image(channel: str | None, requested: bool | None) -> bool:
    """수동/라이브러리 생성에서 이미지 자동 생성을 할지. 운동 채널은 기본 ON(명시 False 만 끔).

    where 는 요청값이 **명시 True** 이고 채널이 'rooftop_music' 으로 명시될 때만(자동 회차).
    where 수동 화면(채널 None·auto_image 미전송)은 기존처럼 항상 False.
    """
    from services.music_workout_style import is_workout_channel
    if is_where_auto(channel):
        return requested is True
    return is_workout_channel(channel) and requested is not False


# ── 프롬프트 ──────────────────────────────────────────────────────────
# API 전용 프리픽스 = 폰 ChatGPT 지침 공통 규칙 + 운동 톤(music_image_prompts.WORKOUT_TONE,
# 단일 정의) + 복사용 프리픽스엔 없던 항목("한 폭의 그림 같은 분위기", "보는 순간 몸을
# 움직이고 싶어지는 느낌", "현장감 허용·완벽하게 정돈하지 말 것").
# music_image_prompts 의 _WORKOUT_PREFIX·IMAGE_PROMPT_PREFIX 는 여기서 건드리지 않는다.
def api_prefix() -> str:
    from services.music_image_prompts import WORKOUT_TONE
    return (
        "실제 사진작가가 고급 카메라로 촬영한 가로 16:9 비율 사진. 한 폭의 그림 같은 분위기. "
        "고해상도, 선명하고 디테일이 풍부하게. AI가 만든 느낌 절대 없이. 텍스트, 글자, 워터마크 없이. "
        f"{WORKOUT_TONE} "
        "원판·덤벨·땀·트랙 등 현장감 있는 요소 허용. 완벽하게 정돈하지 말 것. "
        "보는 순간 몸을 움직이고 싶어지는 느낌."
    )


def build_prompt(
    action: str | None, avoid: list[str] | None = None, *, recent_scenes: list[str] | None = None,
) -> str:
    """5단계 운동 풀(workout_core) + API 전용 프리픽스. [WORKOUT] 태그(폰 지침용 표식)는 없다.

    avoid: 앞 시도의 검수 불합격 사유 — "이번엔 반드시 피할 것"으로 맨 끝에 붙인다.
    recent_scenes: 같은 축 최근 영상 장면 — 장면을 쓰는 LLM 에 "겹치지 않게"로 넘긴다.
    """
    return _workout_prompt(action, avoid, recent_scenes)[0]


def _workout_prompt(action: str | None, avoid: list[str] | None, recent_scenes: list[str] | None) -> tuple[str, str]:
    """(최종 프롬프트, 장면). 장면은 최근 기록(_recent_workout.json)에 남긴다."""
    from services import music_image_prompts as mip

    raw, scene = mip.workout_core(action, avoid_recent=recent_scenes)
    outfit = random.choice(mip.WORKOUT_OUTFITS)
    prompt = (f"{api_prefix()} {raw.strip()} 인물이 있다면 복장은 반드시: {outfit} "
              "(크롭탑·스포츠브라·민소매 크롭 금지, 복부·허리 노출 없음).").strip()
    if avoid:
        prompt += " 이번엔 반드시 피할 것(직전 시도 검수 불합격 사유): " + "; ".join(avoid) + "."
    return prompt, scene


def _workout_no_people_prompt(action: str | None, avoid: list[str] | None) -> tuple[str, str]:
    """(인물 없는 대체 프롬프트, 장면). 인물 시도가 전부 불합격일 때 쓴다(2026-10-27 대표 승인)."""
    from services import music_image_prompts as mip
    from services.music_workout_style import axis_for_action

    scene = random.choice(mip.WORKOUT_NO_PEOPLE_SCENES[axis_for_action(action)])
    prompt = (f"{api_prefix()} {scene}. 이 장면에는 사람이 한 명도 없다 — 인물·손·발·신체 일부·그림자 속 "
              "사람 실루엣 모두 금지. 기구·공간·빛만으로 운동하고 싶어지는 분위기.")
    if avoid:
        prompt += " 이번엔 반드시 피할 것(직전 시도 검수 불합격 사유): " + "; ".join(avoid) + "."
    return prompt, f"[인물없음] {scene}"


# ── 이미지 생성 ────────────────────────────────────────────────────────
def _usage_dict(resp) -> dict:
    usage = getattr(resp, "usage", None)
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        try:
            return usage.model_dump()
        except Exception:  # noqa: BLE001
            pass
    return dict(usage) if isinstance(usage, dict) else {}


def _image_kind(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "unknown"


def _to_png(src: Path, dest: Path) -> None:
    """PNG 가 아니면 ffmpeg 로 PNG 변환(대표 업로드와 같은 .png·image/png 로 맞춘다)."""
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-frames:v", "1", str(dest)],
        check=True, capture_output=True, text=True, timeout=_FFMPEG_TIMEOUT_SEC,
    )


def generate_image(prompt: str, out_path: str) -> dict:
    """GPT-Image 1장 → out_path(PNG). 사용량·추정 비용 dict 반환. 실패 시 예외.

    응답은 b64_json / url 둘 다 처리한다(2.5 의 응답 형식은 문서 원문으로 확정하지 못했다).
    response_format 은 보내지 않는다(GPT Image 계열은 이 인자를 받지 않는 것으로 알려짐).
    """
    from openai import OpenAI
    import httpx

    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY 미설정 — 이미지를 생성할 수 없습니다.")
    model, size, quality = image_model(), image_size(), image_quality()
    timeout = image_timeout_sec()
    client = OpenAI(api_key=key, timeout=timeout, max_retries=0)
    t0 = time.monotonic()
    logger.warning("[auto-image] OpenAI 이미지 호출 시작 model=%s timeout=%.0fs retries=0", model, timeout)
    try:
        resp = client.images.generate(model=model, prompt=prompt, size=size, quality=quality, n=1)
    except Exception as e:  # noqa: BLE001 - 소요시간을 남기고 그대로 올린다(시도 실패로 기록됨)
        logger.warning("[auto-image] OpenAI 이미지 호출 실패 %.1fs: %s", time.monotonic() - t0, str(e)[:200])
        raise
    logger.warning("[auto-image] OpenAI 이미지 호출 끝 %.1fs", time.monotonic() - t0)
    data = getattr(resp, "data", None) or []
    if not data:
        raise RuntimeError("이미지 응답이 비어 있습니다.")
    item = data[0]
    b64 = getattr(item, "b64_json", None)
    url = getattr(item, "url", None)
    if b64:
        raw, fmt = base64.b64decode(b64), "b64_json"
    elif url:
        r = httpx.get(url, timeout=120.0, follow_redirects=True)
        r.raise_for_status()
        raw, fmt = r.content, "url"
    else:
        raise RuntimeError("이미지 응답에 b64_json/url 이 모두 없습니다.")

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    kind = _image_kind(raw)
    if kind == "png":
        out.write_bytes(raw)
    else:
        tmp = out.with_suffix(f".{kind if kind != 'unknown' else 'img'}")
        tmp.write_bytes(raw)
        _to_png(tmp, out)
        tmp.unlink(missing_ok=True)

    usage = _usage_dict(resp)
    out_tok = usage.get("output_tokens")
    in_tok = usage.get("input_tokens")
    est = round(out_tok * _output_usd_per_m() / 1_000_000, 4) if isinstance(out_tok, (int, float)) else None
    info = {
        "model": model, "size": size, "quality": quality, "response_format": fmt,
        "image_kind": kind, "bytes": len(raw),
        "output_tokens": out_tok, "input_tokens": in_tok, "est_output_usd": est,
    }
    # 첫 실호출 확인 절차 — 모델 ID·응답 형식·사용량이 이 한 줄에 다 찍힌다.
    logger.warning(
        "[auto-image] 생성 OK model=%s size=%s quality=%s format=%s kind=%s bytes=%d "
        "output_tokens=%s input_tokens=%s est_output_usd=%s usage=%s",
        model, size, quality, fmt, kind, len(raw), out_tok, in_tok, est, usage,
    )
    return info


# ── 자동 검수(Claude 비전) ─────────────────────────────────────────────
_REVIEW_SYSTEM = (
    "너는 운동·피트니스 유튜브 음악 채널의 배경 이미지 검수자다. 이 이미지는 영상 전체 배경과 "
    "썸네일로 그대로 쓰인다. 채널 톤은 '밝은 햇살 + 쨍한 원색 대비'다.\n"
    "합격 기준: 글로벌 스포츠웨어 브랜드 캠페인 화보 수준의 운동 장면. 인물은 허용된다 — "
    "노출 적은 운동복(티셔츠·탱크탑 + 긴 레깅스·조거팬츠·트레이닝 팬츠)을 입고 운동하는 역동적인 "
    "순간이면 정상이다. 인물 없는 기구·트랙·스튜디오 장면도 정상이다.\n"
    "아래 불합격 기준 중 하나라도 해당하면 불합격이다.\n"
    "1. 복장: 크롭탑, 스포츠브라 단독, 짧은 반바지.\n"
    "2. 가슴·엉덩이·허리 라인을 부각하는 포즈·앵글(화보·수영복처럼 몸매를 강조).\n"
    "3. 얼굴 정면 클로즈업.\n"
    "4. 간판·포스터·벽 글자·큰 글자·로고(옷·기구의 브랜드 로고 포함)·워터마크.\n"
    "5. 화면 중앙이 하얗게 날아가 있다(창문·출입구·역광 광원이 중앙에서 과노출) — 영상 중앙에 "
    "흰 로고가 올라가는데 안 보일 정도로 중앙이 희면 불합격.\n"
    "6. 전체가 어둡거나 칙칙하다(야간·저조도·회색조·탁한 색감).\n"
    "7. AI 티: 손가락·관절·팔다리 왜곡, 기구(바벨·덤벨·머신)가 물리적으로 어색하다.\n"
    "8. 운동과 무관한 카페·거리·여행 풍경.\n"
    "허용(불합격 사유 아님): 원판 무게 숫자(예: 15 KG)·덤벨 눈금처럼 기구에 붙은 작고 자연스러운 "
    "표시는 읽혀도 정상이다. 밝은 햇살, 선명한 그림자, 쨍한 원색, 땀·분필 가루 같은 현장감도 정상이다. "
    "애매하면 불합격으로 판단한다.\n"
    '반드시 JSON 한 개만 출력한다: {"pass": true 또는 false, "reasons": ["불합격 사유(한국어, 짧게)"]}. '
    "합격이면 reasons 는 빈 배열."
)


def _review_copy(src: str, dest: str) -> str:
    """검수용 축소 JPEG(가로 최대 1024px)."""
    subprocess.run(
        ["ffmpeg", "-y", "-i", src, "-vf", f"scale='min({_REVIEW_MAX_PX},iw)':-2",
         "-frames:v", "1", "-q:v", "3", dest],
        check=True, capture_output=True, text=True, timeout=_FFMPEG_TIMEOUT_SEC,
    )
    return dest


def _parse_review(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        raise ValueError(f"검수 응답에 JSON 이 없습니다: {(text or '')[:120]}")
    obj = json.loads(m.group(0))
    passed = obj.get("pass")
    if not isinstance(passed, bool):
        raise ValueError(f"검수 응답의 pass 가 bool 이 아닙니다: {obj!r}"[:200])
    reasons = obj.get("reasons") or []
    if not isinstance(reasons, list):
        reasons = [str(reasons)]
    return {"pass": passed, "reasons": [str(r)[:120] for r in reasons][:5]}


def review_image(path: str, system: str | None = None) -> dict:
    """이미지 1장을 Claude 비전으로 검수 → {pass, reasons, model}. 호출·파싱 실패 시 예외.

    system: 검수 기준(기본 운동 _REVIEW_SYSTEM, where 는 music_where_image.REVIEW_SYSTEM).
    """
    from services import music_lyrics

    timeout = review_timeout_sec()
    client = music_lyrics._client().with_options(timeout=timeout, max_retries=0)
    tmpdir = Path(tempfile.mkdtemp(prefix="imgrev_"))
    t0 = time.monotonic()
    try:
        small = _review_copy(path, str(tmpdir / "review.jpg"))
        b64 = base64.b64encode(Path(small).read_bytes()).decode("ascii")
        model = review_model()
        ask = "이 배경 이미지를 기준대로 검수하고 JSON 만 출력해."
        try:
            msg = client.messages.create(
                model=model,
                max_tokens=400,
                system=system or _REVIEW_SYSTEM,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                        {"type": "text", "text": ask},
                    ],
                }],
            )
            text = "".join(getattr(b, "text", "") for b in (msg.content or []))
            from services import music_ops_log
            music_ops_log.add_usage_from(msg, model)  # 대시보드 비용 실측(기록만)
        except Exception as e:  # noqa: BLE001 - Claude API 오류면 같은 기준(system)으로 OpenAI 비전 1회 대체
            from services import music_llm_fallback as fb
            if not (fb.enabled() and fb.is_anthropic_api_error(e)):
                raise
            text, model = fb.vision(system or _REVIEW_SYSTEM, b64, ask, max_tokens=400, task="image_review", cause=e)
        out = _parse_review(text)
        out["model"] = model
        logger.warning("[auto-image] Claude 검수 끝 %.1fs (timeout=%.0fs)", time.monotonic() - t0, timeout)
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("[auto-image] Claude 검수 실패 %.1fs: %s", time.monotonic() - t0, str(e)[:200])
        raise
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _profile(
    action: str | None, channel: str | None, genre: str | None, recent_scenes: list[str] | None = None,
    style: str | None = None,
):
    """채널별 (프롬프트 함수(avoid)->str, 검수 기준, 보관함 축). 기본은 운동(기존 그대로).

    운동 프롬프트 함수는 마지막에 만든 장면을 .scene 에 남긴다(합격 시 최근 기록용).
    where style="street": 유럽 거리 필름 스냅 — 전용 프롬프트·검수, 보관함 where-street/{장르}.
      그 외(None·"space")는 건축 공간(#341) 그대로.
    """
    if is_where_auto(channel):
        from services import music_where_image as mwi
        g = (genre or "").strip() or "citypop"
        if style == mwi.STYLE_STREET:
            return (lambda avoid: mwi.build_street_prompt(g, avoid)), mwi.STREET_REVIEW_SYSTEM, f"{_STREET_PREFIX}/{g}"
        return (lambda avoid: mwi.build_prompt(g, avoid)), mwi.REVIEW_SYSTEM, f"where/{g}"
    from services.music_workout_style import axis_for_action

    def make(avoid):
        prompt, make.scene = _workout_prompt(action, avoid, recent_scenes)
        return prompt

    def no_people(avoid):
        prompt, make.scene = _workout_no_people_prompt(action, avoid)
        return prompt
    make.scene = None
    make.no_people = no_people  # 인물 시도 불합격 후 대체(generate_reviewed 가 사용)
    return make, None, axis_for_action(action)


def generate_reviewed(
    action: str | None, out_path: str, *, deadline: float | None = None,
    channel: str | None = None, genre: str | None = None, recent_scenes: list[str] | None = None,
    style: str | None = None,
) -> dict:
    """생성 → 검수. 불합격이면 재생성. where 최대 3회, 운동은 인물 2회 + 인물 없는 장면 2회.
    {ok, path, attempts, summary(, scene)}.

    API 오류·검수 실패(응답 파싱 불가 포함)도 그 시도의 불합격으로 친다 — 검수를 못 했으면
    쓰지 않는다. 어떤 경우에도 예외를 던지지 않는다(호출부는 ok 만 보면 된다).
    deadline(time.monotonic 기준): 남은 시간이 1회분(생성+검수 상한)보다 적으면 재생성을 건너뛴다.
    """
    out = Path(out_path)
    attempts: list[dict] = []
    avoid: list[str] = []  # 앞 시도들의 검수 불합격 사유(중복 제거) → 다음 프롬프트에 붙인다
    make_prompt, review_system, _ = _profile(action, channel, genre, recent_scenes, style)
    no_people = getattr(make_prompt, "no_people", None)   # 운동만 — 인물 2회 불합격 → 인물 없는 장면
    max_attempts = _WORKOUT_MAX_ATTEMPTS if no_people else _MAX_ATTEMPTS
    for i in range(1, max_attempts + 1):
        rec: dict = {"attempt": i}
        cand = out.with_name(f"{out.stem}_try{i}.png")
        if i > 1 and deadline is not None and (
            time.monotonic() + image_timeout_sec() + review_timeout_sec() > deadline
        ):
            rec.update({"pass": False, "error": "시간 상한 — 재생성 생략"})
            attempts.append(rec)
            logger.warning("[auto-image] 시도 %d/%d 생략 — 남은 시간 부족", i, max_attempts)
            break
        t_try = time.monotonic()
        logger.warning("[auto-image] 시도 %d/%d 시작", i, max_attempts)
        try:
            if no_people and i > _WORKOUT_PEOPLE_ATTEMPTS:
                rec["no_people"] = True
                prompt = no_people(avoid)
            else:
                prompt = make_prompt(avoid)
            rec["prompt"] = prompt[:400]
            if avoid:
                rec["avoid"] = list(avoid)
            info = generate_image(prompt, str(cand))
            rec.update({k: info.get(k) for k in ("model", "output_tokens", "est_output_usd", "response_format")})
            review = review_image(str(cand), review_system) if review_system else review_image(str(cand))
            rec["pass"] = review["pass"]
            rec["reasons"] = review["reasons"]
            rec["review_model"] = review.get("model")
            logger.warning(
                "[auto-image] 검수 %s (시도 %d/%d, %.1fs) 사유=%s",
                "합격" if review["pass"] else "불합격", i, max_attempts,
                time.monotonic() - t_try, review["reasons"],
            )
            if review["pass"]:
                shutil.move(str(cand), str(out))
                attempts.append(rec)
                done = {"ok": True, "path": str(out), "attempts": attempts, "summary": "합격"}
                if getattr(make_prompt, "scene", None):
                    done["scene"] = make_prompt.scene
                return done
            for r in review["reasons"]:
                if r and r not in avoid:
                    avoid.append(r)
        except Exception as e:  # noqa: BLE001 - 시도 실패로 기록하고 다음 시도
            rec["pass"] = False
            rec["error"] = str(e)[:300]
            logger.warning("[auto-image] 시도 %d/%d 실패: %s", i, max_attempts, e)
        cand.unlink(missing_ok=True)
        attempts.append(rec)
    return {"ok": False, "path": None, "attempts": attempts, "summary": _fail_summary(attempts)}


def _fail_summary(attempts: list[dict]) -> str:
    bits = []
    for a in attempts:
        if a.get("error"):
            bits.append(f"{a['attempt']}차 오류: {a['error'][:80]}")
        else:
            bits.append(f"{a['attempt']}차 불합격: {', '.join(a.get('reasons') or ['사유 없음'])[:80]}")
    return " / ".join(bits) or "생성 실패"


def job_summary(res: dict) -> dict:
    """music_jobs.metadata·폴링 응답용 요약(프롬프트 원문은 짧게)."""
    return {
        "ok": bool(res.get("ok")),
        "summary": res.get("summary") or "",
        "attempts": [
            {k: a.get(k) for k in (
                "attempt", "pass", "reasons", "error", "model", "review_model",
                "output_tokens", "est_output_usd", "response_format", "prompt", "avoid", "no_people",
            ) if a.get(k) is not None}
            for a in (res.get("attempts") or [])
        ],
        **({"reused": res["reused"]} if res.get("reused") else {}),
    }


# ── 합격본 보관함(축별) — 전부 불합격일 때 검은 배경 대신 재사용 ─────────────
# R2 음악 버킷 music-auto-bg/{axis}/{UTC시각}_{sha12}.png. 직전 영상에 쓴 키는
# music-auto-bg/_last_{axis}.txt 에 적어 두고 재사용 후보에서 뺀다.
_ARCHIVE_PREFIX = "music-auto-bg"
_REUSE_MAX_AGE_SEC = 30 * 24 * 3600


def _archive_dir(axis: str) -> str:
    return f"{_ARCHIVE_PREFIX}/{axis}/"


def _last_key(axis: str) -> str:
    # where 축은 "where/{장르}" — 파일 이름에는 "/" 대신 "_"(운동 축 키는 그대로).
    return f"{_ARCHIVE_PREFIX}/_last_{axis.replace('/', '_')}.txt"


def _write_last(axis: str, key: str) -> None:
    """직전 영상에 쓴 배경 키 기록(best-effort)."""
    try:
        from adapters import r2_storage
        r2_storage._get_client().put_object(
            Bucket=r2_storage._music_bucket(), Key=_last_key(axis),
            Body=key.encode("utf-8"), ContentType="text/plain",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[auto-image] 직전 배경 기록 실패(무시): %s", str(e)[:160])


def _read_last(axis: str) -> str | None:
    try:
        from adapters import r2_storage
        obj = r2_storage._get_client().get_object(Bucket=r2_storage._music_bucket(), Key=_last_key(axis))
        return obj["Body"].read().decode("utf-8").strip() or None
    except Exception:  # noqa: BLE001 - 없음 → 제외할 키 없음
        return None


def archive_passed(path: str, axis: str) -> str | None:
    """합격 이미지를 축별 보관함에 올리고 직전 배경으로 기록. 키 반환, 실패 시 None."""
    try:
        from adapters import r2_storage
        if not r2_storage.is_available():
            return None
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        key = f"{_archive_dir(axis)}{stamp}_{(_sha256(path) or 'x')[:12]}.png"
        r2_storage.upload_image(
            path, key, bucket=r2_storage._music_bucket(),
            public_base_url=r2_storage._music_public_base(), content_type="image/png",
        )
        _write_last(axis, key)
        logger.warning("[auto-image] 합격본 보관 axis=%s key=%s", axis, key)
        return key
    except Exception as e:  # noqa: BLE001
        logger.warning("[auto-image] 합격본 보관 실패(무시): %s", str(e)[:160])
        return None


def pick_reuse(
    axis: str, dest: str, *, exclude: list[str] | None = None, max_age_sec: float | None = _REUSE_MAX_AGE_SEC,
) -> dict | None:
    """같은 축 합격본(최근 30일) 중 직전 영상 배경을 뺀 무작위 1장 → dest. 없으면 None.

    후보가 직전 배경 1장뿐이면 그것이라도 쓴다(검은 배경보다 낫다).
    exclude: 최근 사용 키(오래된 것 → 최근 순). 이 키들도 뺀다 — 후보가 전부 최근 사용분이면
      그중 가장 오래전에 쓴 것을 고른다(운동 최근 10장 제외).
    max_age_sec=None: 기간 제한 없음(where 전 장르 폴백).
    """
    import random
    try:
        from adapters import r2_storage
        if not r2_storage.is_available():
            return None
        client, bucket = r2_storage._get_client(), r2_storage._music_bucket()
        cutoff = time.time() - max_age_sec if max_age_sec else 0.0
        cands: list[tuple[str, float]] = []
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=_archive_dir(axis)):
            for obj in page.get("Contents", []):
                lm = obj.get("LastModified")
                ts = lm.timestamp() if lm is not None else 0.0
                if obj["Key"].endswith(".png") and ts >= cutoff:
                    cands.append((obj["Key"], ts))
        if not cands:
            logger.warning("[auto-image] 재사용할 합격본 없음 axis=%s(최근 30일)", axis)
            return None
        last = _read_last(axis)
        recent = list(exclude or [])
        skip = set(recent) | ({last} if last else set())
        pool = [c for c in cands if c[0] not in skip]
        if pool:
            key, ts = random.choice(pool)
        elif recent:  # 전부 최근 사용분 → 가장 오래전에 쓴 것(최근 목록에 없는 직전 배경은 맨 뒤)
            key, ts = min(cands, key=lambda c: recent.index(c[0]) if c[0] in recent else len(recent))
        else:
            key, ts = random.choice(cands)
        client.download_file(bucket, key, dest)
        _write_last(axis, key)
        return {"key": key, "archived_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
                "candidates": len(cands), "avoided_last": bool(last and last != key),
                **({"avoided_recent": len(skip & {c[0] for c in cands})} if recent else {})}
    except Exception as e:  # noqa: BLE001 - 재사용 실패 → 블랙 배경(기존 동작)
        logger.warning("[auto-image] 합격본 재사용 실패 axis=%s: %s", axis, str(e)[:160])
        return None


# ── 운동 배경 최근 기록 · 축 로테이션(2026-10-19 대표 승인) ─────────────────
# R2 music-auto-bg/_recent_workout.json = {"axes": [...], "scenes": {축: [...]}, "keys": {축: [...]}}
# (오래된 것 → 최근, 각 최대 10). SQL 없이 R2 JSON 한 개. 동시 제작 1개라 읽고-쓰기 경합이 없다.
RECENT_N = 10
_RECENT_KEY = f"{_ARCHIVE_PREFIX}/_recent_workout.json"
WORKOUT_AXIS_WEIGHTS: dict[str, int] = {"strength": 50, "cardio": 30, "warmup": 20}
# 축 → 대표 action(배경 프롬프트·보관함 축만 바꾼다 — 음악·제목·설명은 기존 그대로).
AXIS_ACTION: dict[str, str] = {"strength": "workout", "cardio": "running", "warmup": "stretching"}


def read_recent() -> dict:
    try:
        from adapters import r2_storage
        obj = r2_storage._get_client().get_object(Bucket=r2_storage._music_bucket(), Key=_RECENT_KEY)
        data = json.loads(obj["Body"].read().decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 - 없음·읽기 실패 → 빈 기록(제외할 것 없음)
        return {}


def _write_recent(data: dict) -> None:
    try:
        from adapters import r2_storage
        r2_storage._get_client().put_object(
            Bucket=r2_storage._music_bucket(), Key=_RECENT_KEY,
            Body=json.dumps(data, ensure_ascii=False).encode("utf-8"), ContentType="application/json",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[auto-image] 최근 배경 기록 실패(무시): %s", str(e)[:160])


def _push(lst, value, n: int = RECENT_N) -> list:
    out = [v for v in (lst if isinstance(lst, list) else []) if v != value] + [value]
    return out[-n:]


def recent_for(data: dict, field: str, axis: str) -> list[str]:
    v = (data.get(field) or {}).get(axis) if isinstance(data.get(field), dict) else None
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


def note_recent(axis: str, *, scene: str | None = None, key: str | None = None) -> None:
    """운동 배경 1장 사용 기록 — 축 순서·같은 축 장면·보관함 키(각 최근 10)."""
    data = read_recent()
    data["axes"] = (data.get("axes") if isinstance(data.get("axes"), list) else [])[-(RECENT_N - 1):] + [axis]
    for field, value in (("scenes", scene), ("keys", key)):
        if value:
            box = data.get(field) if isinstance(data.get(field), dict) else {}
            box[axis] = _push(box.get(axis), value)
            data[field] = box
    _write_recent(data)


def pick_workout_axis(recent_axes: list[str] | None = None, *, rng=None) -> str:
    """가중 랜덤 50/30/20(근력/유산소/워밍업). 직전 2회가 같은 축이면 그 축은 뺀다(3연속 금지)."""
    import random as _r
    r = rng or _r
    axes = [a for a in (recent_axes or []) if a in WORKOUT_AXIS_WEIGHTS]
    pool = dict(WORKOUT_AXIS_WEIGHTS)
    if len(axes) >= 2 and axes[-1] == axes[-2]:
        pool.pop(axes[-1], None)
    names = list(pool)
    return r.choices(names, weights=[pool[n] for n in names], k=1)[0]


# ── where 배경 폴백(장르 보관함 → where 전 장르 보관함 → 기존 where 배경) ──────────
class NoBackground(RuntimeError):
    """where 자동 회차 배경을 끝내 못 구함 — 검은 배경 발행 금지라 렌더 전에 멈춘다(fail_reason=upload_gate)."""


def pick_where_legacy(dest: str, *, tries: int = 5) -> dict | None:
    """기존 where 영상의 배경(music_uploads.thumbnail_r2_key, channel=rooftop_music) 무작위 1장 → dest.

    옛 대표 업로드 이미지라 일부는 R2 수명 정책으로 지워졌을 수 있어 몇 장까지 차례로 시도한다.
    """
    import random
    from adapters import r2_storage
    from services import music_uploads
    keys = music_uploads.list_thumbnail_keys(WHERE_CHANNEL)
    random.shuffle(keys)
    for key in keys[:tries]:
        try:
            r2_storage.download_music_object(key, dest)
            return {"key": key, "candidates": len(keys), "source": "where_legacy"}
        except Exception as e:  # noqa: BLE001 - 지워진 키 → 다음 후보
            logger.warning("[auto-image] 기존 where 배경 내려받기 실패 key=%s: %s", key, str(e)[:120])
    return None


# 거리 스냅 보관함 — where/ 와 접두사를 분리해 건축 공간 재사용·전 장르 폴백(#343)에 섞이지 않게 한다.
_STREET_PREFIX = "where-street"


def _street_fallback(genre: str | None, dest: str) -> dict | None:
    """거리 스냅 장르 보관함이 비었을 때 — 거리 스냅 전 장르(기간 무제한) → 건축 장르 보관함 →
    기존 #343 체인(건축 전 장르 → 기존 where 배경)."""
    picked = pick_reuse(_STREET_PREFIX, dest, max_age_sec=None)
    if picked:
        return {**picked, "source": "where_street_all"}
    g = (genre or "").strip() or "citypop"
    picked = pick_reuse(f"where/{g}", dest)
    if picked:
        return {**picked, "source": "where_genre"}
    return _where_fallback(f"where/{g}", dest)


def _where_fallback(axis: str, dest: str) -> dict | None:
    """where 장르 보관함이 비었을 때 — 전 장르 보관함(기간 무제한) → 기존 where 배경."""
    picked = pick_reuse("where", dest, max_age_sec=None)
    if picked:
        return {**picked, "source": "where_all"}
    return pick_where_legacy(dest)


# ── 렌더 정합 표식(publish 재렌더 건너뛰기 판정) ───────────────────────
_MARKER_VERSION = 1


def _marker_name(mix_id: str) -> str:
    return f"{mix_id}_render.json"


def _sha256(path: str | None) -> str | None:
    if not path or not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _design_hash(channel: str | None) -> str:
    """make_video 가 읽는 것과 **같은 호출**(theme 채널)의 디자인 설정 해시.

    make_video 는 get_design_config(channel=theme["channel"]) 를 읽는다(채널별 디자인).
    표식 기록·판정 모두 그 영상의 채널로 계산해야 같은 값을 비교한다.
    """
    from services import music_channel
    cfg = music_channel.get_design_config(channel=channel)
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _norm_key(v) -> str | None:
    s = (v or "").strip() if isinstance(v, str) else ""
    return s or None


def record_render(
    slug: str, mix_id: str, *, bg_path: str, char_path: str | None, char_key: str | None,
    show_playlist: bool, vres: dict, channel: str | None = "workout_music",
) -> bool:
    """렌더 직후 사이드카 기록. 첫프레임(=Remotion 렌더 성공)이 없으면 기록하지 않는다.

    best-effort — 실패하면 표식이 없을 뿐이고, 표식이 없으면 publish 는 재렌더한다(안전 쪽).
    """
    try:
        from adapters import r2_storage
        if not (vres.get("frame_thumb_key") and vres.get("video_url")):
            logger.info("[auto-image] 렌더 표식 생략(첫프레임 없음 = 폴백 렌더) mix_id=%s", mix_id)
            return False
        if not r2_storage.is_available():
            return False
        marker = {
            "v": _MARKER_VERSION,
            "mix_id": mix_id,
            "mp4_url": vres["video_url"],
            "frame_thumb_key": vres["frame_thumb_key"],
            "bg_sha256": _sha256(bg_path),
            "char_key": _norm_key(char_key),
            "char_sha256": _sha256(char_path) if char_path else None,
            "show_playlist": bool(show_playlist),
            "design_hash": _design_hash(channel),
        }
        if not marker["bg_sha256"]:
            return False
        tmpdir = Path(tempfile.mkdtemp(prefix="rmark_"))
        try:
            p = tmpdir / _marker_name(mix_id)
            p.write_text(json.dumps(marker, ensure_ascii=False), encoding="utf-8")
            r2_storage.upload_music_video(str(p), slug, _marker_name(mix_id), content_type="application/json")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
        logger.info("[auto-image] 렌더 표식 기록 mix_id=%s bg=%s", mix_id, marker["bg_sha256"][:12])
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("[auto-image] 렌더 표식 기록 실패(publish 는 재렌더로 안전): %s", e)
        return False


def matching_render(row: dict, *, bg_path: str, char_path: str | None, show_playlist: bool) -> dict | None:
    """publish 직전 판정 — 현재 mp4 가 **지금 배경·인물·PLAY LIST·디자인**으로 렌더된 것인가.

    전부 일치할 때만 표식(dict, frame_thumb_key 포함)을 돌려준다. 하나라도 다르거나 표식이
    없거나 읽기/계산이 실패하면 None → 호출부는 재렌더한다(배경이 바뀌었는데 옛 mp4 가
    올라가는 사고가 최악이므로, 애매하면 항상 재렌더 쪽).
    """
    slug, mix_id = row.get("slug") or "", row.get("mix_id") or ""
    if not (slug and mix_id):
        return None
    try:
        from adapters import r2_storage
        tmpdir = Path(tempfile.mkdtemp(prefix="rmatch_"))
        try:
            p = tmpdir / "marker.json"
            r2_storage.download_music_object(r2_storage.music_video_key(slug, _marker_name(mix_id)), str(p))
            marker = json.loads(p.read_text(encoding="utf-8"))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception as e:  # noqa: BLE001 - 표식 없음/읽기 실패 → 재렌더
        logger.info("[auto-image] 렌더 표식 없음 → 재렌더 mix_id=%s (%s)", mix_id, str(e)[:120])
        return None

    try:
        row_char_key = _norm_key(row.get("character_r2_key"))
        checks = {
            "version": marker.get("v") == _MARKER_VERSION,
            "mix_id": marker.get("mix_id") == mix_id,
            "mp4_url": bool(row.get("mp4_url")) and marker.get("mp4_url") == row.get("mp4_url"),
            "frame": bool(marker.get("frame_thumb_key")),
            "bg": bool(marker.get("bg_sha256")) and marker.get("bg_sha256") == _sha256(bg_path),
            "char_key": marker.get("char_key") == row_char_key,
            # 인물 키가 있는데 파일을 못 받았으면(char_path None) 불일치로 본다.
            "char": (marker.get("char_sha256") == (_sha256(char_path) if char_path else None))
                     and not (row_char_key and not char_path),
            "show_playlist": marker.get("show_playlist") is bool(show_playlist),
            "design": marker.get("design_hash") == _design_hash(row.get("channel")),
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("[auto-image] 렌더 정합 판정 실패 → 재렌더 mix_id=%s: %s", mix_id, e)
        return None
    failed = [k for k, ok in checks.items() if not ok]
    if failed:
        logger.warning("[auto-image] 렌더 정합 불일치 → 재렌더 mix_id=%s 불일치=%s", mix_id, ",".join(failed))
        return None
    logger.warning("[auto-image] 렌더 정합 일치 → publish 재렌더 생략 mix_id=%s", mix_id)
    return marker


def prepare_for_render(
    job_id: str, action: str | None, workdir: str, *, reuse: bool = True,
    channel: str | None = None, genre: str | None = None, style: str | None = None,
) -> tuple[str | None, dict]:
    """렌더 직전 — 생성·검수 후 (배경 경로 또는 None, 요약). 요약은 music_jobs.metadata 에 남긴다.

    style: where 배경 스타일("street" 거리 스냅 / None·"space" 건축 공간). 운동은 무시된다.

    합격 → 축별 보관함에 보관. 전부 불합격·시간 초과 → reuse 면 같은 축 합격본 재사용
    (요약에 reused). 그것도 없으면 None → 호출부는 지금까지처럼 블랙 배경으로 렌더한다.
    reuse=False: 검토 카드의 [AI 이미지 다시 만들기] 처럼 "새 이미지"를 원한 경로 — 옛 이미지로
    바꾸지 않고 실패로 돌려준다(기존 상태 유지).
    """
    limit = prepare_timeout_sec()
    t0 = time.monotonic()
    logger.warning("[auto-image] 이미지 단계 시작 job=%s action=%s 상한=%.0fs", job_id, action or "-", limit)
    # 전체 상한 — 생성/검수가 무응답이어도 렌더로 넘어가게 **데몬 스레드**에서 돌리고 limit 초에 끊는다.
    # ThreadPoolExecutor 는 쓰지 않는다: 워커가 데몬이 아니라 무응답 스레드가 프로세스 종료(재배포)
    # 시 join 에서 막힌다. 끊긴 스레드는 강제 종료할 수 없지만(파이썬 제약) 결과는 버리고, 각 호출에
    # 개별 timeout 이 있어 오래 남지 않는다.
    box: dict = {}
    where = is_where_auto(channel)
    street = where and style == "street"
    axis = _profile(action, channel, genre, style=style)[2]  # 운동: 축, where: where/{장르} · where-street/{장르}
    recent = {} if where else read_recent()      # 운동만 — 최근 장면·키 10개 피하기

    def _work() -> None:
        try:
            box["res"] = generate_reviewed(
                action, str(Path(workdir) / "auto_bg.png"), deadline=t0 + limit, channel=channel, genre=genre,
                recent_scenes=None if where else recent_for(recent, "scenes", axis), style=style,
            )
        except Exception as e:  # noqa: BLE001
            box["err"] = e

    th = threading.Thread(target=_work, name="auto-image", daemon=True)
    th.start()
    th.join(timeout=limit)
    if th.is_alive():
        res = {"ok": False, "path": None, "attempts": [],
               "summary": f"이미지 단계 시간 초과({limit:.0f}초) — 이미지 없이 진행"}
        logger.warning("[auto-image] 이미지 단계 시간 초과 %.0fs → 이미지 없이 렌더 진행 job=%s", limit, job_id)
    elif "err" in box:  # generate_reviewed 는 예외를 안 던지지만 방어
        res = {"ok": False, "path": None, "attempts": [], "summary": f"이미지 단계 오류: {str(box['err'])[:200]}"}
        logger.warning("[auto-image] 이미지 단계 오류 → 이미지 없이 렌더 진행 job=%s: %s", job_id, box["err"])
    else:
        res = box.get("res") or {"ok": False, "path": None, "attempts": [], "summary": "결과 없음"}
    if res.get("ok"):
        key = archive_passed(res["path"], axis)
        if not where:
            note_recent(axis, scene=res.get("scene"), key=key)
    elif reuse:
        dest = str(Path(workdir) / "reuse_bg.png")
        picked = pick_reuse(axis, dest, exclude=None if where else recent_for(recent, "keys", axis))
        if not picked and where:
            picked = _street_fallback(genre, dest) if street else _where_fallback(axis, dest)
            if picked:
                logger.warning("[auto-image] where 장르 보관함 비어 있음 → 폴백 배경(%s) job=%s key=%s",
                               picked["source"], job_id, picked["key"])
        if picked and not where:
            note_recent(axis, key=picked["key"])
        if picked:
            fail = res.get("summary") or ""
            res = {**res, "ok": True, "path": dest, "reused": picked,
                   "summary": f"생성 이미지 전부 불합격 → 합격본 재사용({picked['key']}) · {fail}"[:400]}
            logger.warning(
                "[auto-image] 생성 전부 불합격 → 합격본 재사용 job=%s axis=%s key=%s (불합격: %s)",
                job_id, axis, picked["key"], fail[:200],
            )
    logger.warning(
        "[auto-image] 이미지 단계 끝 job=%s ok=%s reused=%s 소요=%.1fs",
        job_id, bool(res.get("ok")), bool(res.get("reused")), time.monotonic() - t0,
    )
    summary = job_summary(res)
    if where:
        summary["bg_style"] = "street" if street else "space"
    try:
        from services import music_jobs
        music_jobs.merge_metadata(job_id, {"auto_image": summary})
    except Exception:  # noqa: BLE001 - 추적 실패는 무시
        pass
    return (res["path"] if res.get("ok") else None), summary


def attach_after_render(
    slug: str, mix_id: str, bg_path: str, vres: dict, *, channel: str | None = "workout_music",
) -> dict:
    """렌더 후 처리 — 이미지를 대표 업로드와 같은 자리에 두고(R2 + thumbnail_r2_key) 표식 기록.

    렌더 전에는 큐 행이 없어(record_pending 이 렌더 끝에 만든다) set_thumbnail 이 0행을 고친다.
    그래서 반드시 렌더 **뒤에** 부른다. {thumbnail_r2_key, error}.
    """
    from adapters import r2_storage
    from services import music_uploads

    try:
        r2_storage.upload_music_thumbnail(bg_path, slug, mix_id)
        key = r2_storage.music_thumbnail_key(slug, mix_id)
        res = music_uploads.set_thumbnail(mix_id, key)
        if res.get("error"):
            raise RuntimeError(res["error"])
    except Exception as e:  # noqa: BLE001 - 영상은 이미 만들어졌다(이미지 없이 검토대기)
        logger.warning("[auto-image] 썸네일 연결 실패 mix_id=%s: %s", mix_id, e)
        return {"thumbnail_r2_key": None, "error": str(e)[:300]}
    record_render(
        slug, mix_id, bg_path=bg_path, char_path=None, char_key=None, show_playlist=True,
        vres=vres, channel=channel,
    )
    return {"thumbnail_r2_key": key, "error": None}
