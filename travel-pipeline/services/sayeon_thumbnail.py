"""사연 트랙 — 썸네일 자동 생성 (PR-S5 / PR⑧ 곰 일관성 강제).

후킹 문구(큰 글씨 + 노란 강조) + 흰곰 마스코트 이미지 → 썸네일 PNG.
부록 §4-(f) 썸네일 레시피(ffmpeg 단일 프레임 + ASS 오버레이) 그대로.

⚠️ PR⑧: 썸네일에 사람이 절대 나올 수 없는 구조.
씬 이미지(sayeon_scene)와 동일하게 [STYLE]+[CHARACTER]+[NEGATIVE] 고정 블록을
강제 주입하고, 시트 레퍼런스(Kontext) 경로로 흰곰 컷을 직접 생성한다(t2i 금지).
sheet_url 이 주어지면 썸네일 전용 곰 이미지를 생성하고, 곰이 안 잡히면 자동
재생성 1회 → 그래도 실패 시 thumbnail_fallback 플래그만 세우고 파이프라인은
계속 진행한다(영상 생성은 멈추지 않음).

후킹 문구는 hook_text 가 주어지면 그대로, 없으면 script 로 gpt-4o-mini 가 생성한다.
렌더링/다운로드 헬퍼는 S4 합성 엔진(sayeon_assemble)의 것을 재사용한다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path

from openai import OpenAI

from adapters import ImageGenerationRequest, get_kontext_adapter, r2_storage
# 씬 이미지(PR③)와 동일한 고정 블록을 재사용(재발명 금지).
from services.sayeon_character import (
    BEAR_EXPRESSIONS,
    POLAR_BEAR_ART_STYLE,
    SAYEON_NEGATIVE,
    SAYEON_NEGATIVE_SOLO,
    bear_expression,
    build_protagonist_character,
)
# S4 합성 엔진의 검증된 헬퍼 재사용(재발명 금지).
from services.sayeon_assemble import _ass_text, _fetch, _require_ffmpeg, _run

logger = logging.getLogger(__name__)

W, H = 1080, 1920
_FONT = "Noto Sans CJK KR"
_OPENAI_MODEL = "gpt-4o-mini"

# 썸네일에서 사람 등장을 막는 추가 NEGATIVE(부록 C 의 SAYEON_NEGATIVE 위에 덧댄다).
THUMBNAIL_HUMAN_NEGATIVE = (
    "realistic human, real person, child, boy, girl, man, woman, "
    "human face, human figure, person in background"
)

# 후킹 감정 → 곰 표정 매핑 재료(부록 D 와 동일한 7종).
_THUMB_EMOTIONS = set(BEAR_EXPRESSIONS)

# 곰 검출(크림-흰색 픽셀 비율) 품질 게이트.
_PROBE = 64                  # 검사용 다운스케일 한 변(px)
_BEAR_PIXEL_THRESHOLD = 0.02  # 크림-흰색 픽셀 비율 임계값(2%). 미만이면 곰 미검출 판정.

# hook_text 만 주어져 emotion 을 모를 때 한국어 키워드로 추정(기본=shock).
_EMOTION_KEYWORDS = {
    "anger": ("화", "분노", "배신", "어떻게 이럴", "용서", "참다", "뻔뻔"),
    "sadness": ("눈물", "슬픔", "울", "이별", "헤어", "떠나", "그리워"),
    "anxiety": ("불안", "걱정", "두려", "무서", "떨려", "들킬"),
    "flutter": ("설레", "두근", "고백", "사랑", "좋아해"),
    "joy": ("행복", "기쁨", "감동", "고마", "웃음"),
}


def _strip_code_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _guess_emotion(text: str) -> str:
    """hook_text 한국어 키워드 → 감정 추정(부록 D 7종). 미상은 shock(궁금증 미끼)."""
    t = text or ""
    for emo, kws in _EMOTION_KEYWORDS.items():
        if any(k in t for k in kws):
            return emo
    return "shock"


def _generate_hook(script: str) -> tuple[str, str, str]:
    """사연 대본 → (hook_text 2줄, highlight 핵심구, emotion). gpt-4o-mini JSON 모드."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 미설정 — 후킹 문구를 생성할 수 없습니다.")
    client = OpenAI(api_key=api_key)
    system = (
        "너는 한국 '사연' 숏폼 영상의 썸네일 카피라이터다. 사연 대본을 받아 클릭을 "
        "유도하는 2줄 후킹 문구와 그중 강조할 핵심구, 그리고 핵심 감정을 만든다.\n"
        "[공식 — 궁금증 생성 + 답 미공개]\n"
        "- 궁금증을 폭발시키되 결말·답은 절대 누설하지 않는다(스포일러 금지).\n"
        "- 각 줄 8~14자 내외로 짧고 강하게. 말줄임표(…)·의문형을 적극 사용한다.\n"
        "- 구체적 숫자·금액·기간을 활용하면 좋다(예: '3년 만에', '500만원').\n"
        '- 예: "시어머니가 제 통장을\\n보더니…" / "남친 집에서\\n이걸 발견했습니다".\n'
        "[규칙]\n"
        "- 출력은 오직 JSON 객체 하나. 마크다운/설명 금지.\n"
        "- hook_text: 2줄(줄바꿈은 \\n).\n"
        "- highlight: hook_text 안에 실제로 들어있는 핵심구(부분문자열).\n"
        "- emotion: 썸네일 핵심 감정 1개 — "
        "shock|sadness|anger|anxiety|joy|flutter|deadpan 중 하나.\n"
        '[출력] {"hook_text":"시어머니가 제 통장을\\n보더니…",'
        '"highlight":"통장을","emotion":"shock"}'
    )
    user = f"[사연 대본]\n{script.strip()}\n\n위 사연의 썸네일 후킹을 JSON으로 출력하라."
    resp = client.chat.completions.create(
        model=_OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )
    content = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(_strip_code_fence(content))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"LLM 후킹 응답 JSON 파싱 실패: {e}") from e
    hook = str(data.get("hook_text", "")).strip()
    highlight = str(data.get("highlight", "")).strip()
    if not hook:
        raise RuntimeError("후킹 문구 생성 결과가 비어 있습니다.")
    # highlight 가 실제 부분문자열이 아니면 버린다(줄바꿈 정규화 후 비교).
    if highlight and highlight not in hook.replace("\\n", "\n"):
        highlight = ""
    emotion = str(data.get("emotion", "")).strip().lower()
    if emotion not in _THUMB_EMOTIONS:
        emotion = _guess_emotion(hook)
    return hook, highlight, emotion


def build_thumbnail_prompt(anchor: str, tone: str, emotion: str) -> str:
    """썸네일 전용 흰곰 프롬프트: [STYLE]+[CHARACTER]+[감정 연출]+[NEGATIVE] 고정.

    씬 이미지(build_scene_prompt)와 같은 고정 블록을 쓰되, 카피 텍스트 공간을
    확보하는 썸네일 전용 구도와 카피와 연결되는 핵심 감정 장면으로 연출한다.
    """
    character = (anchor or "").strip() or build_protagonist_character(tone)
    expr = bear_expression(emotion, tone)
    parts = [f"{POLAR_BEAR_ART_STYLE}, soft ambient lighting, with subtle texture."]
    # 감정을 앞·뒤로 반복 강조(시트 무표정 추종 완화).
    if expr:
        parts.append(f"IMPORTANT: the bear's facial expression must clearly read as {expr}.")
    parts.append(
        "The SAME character as in the reference sheet, as the single clear focal "
        f"subject of the image: {character}."
    )
    if expr:
        parts.append(f"Facial expression: {expr}.")
    # [썸네일 전용 구도] — 곰 화면 중앙/하단 1/3, 상단에 카피 텍스트 공간 확보.
    parts.append(
        "YouTube short thumbnail composition: the bear is large and clearly visible, "
        "placed in the center or lower third of the frame, reacting emotionally toward "
        "the camera. Leave generous empty negative space in the upper area for caption "
        "text. Bold, eye-catching, high-contrast lighting with a simple, uncluttered "
        "background that supports the emotion."
    )
    parts.append("9:16 vertical composition. No text, no subtitles, no watermark.")
    # [NEGATIVE — 고정] + 곰 둘 금지 + 사람 등장 금지.
    parts.append(f"{SAYEON_NEGATIVE}.")
    parts.append(f"{SAYEON_NEGATIVE_SOLO}.")
    parts.append(f"Avoid: {THUMBNAIL_HUMAN_NEGATIVE}.")
    return " ".join(p for p in parts if p)


def _generate_bear_image(prompt: str, sheet_url: str, dest: Path, seed: int) -> None:
    """시트 레퍼런스(Kontext) 경로로 곰 썸네일 배경 1장 생성. t2i 경로 사용 금지."""
    adapter = get_kontext_adapter()
    if not adapter.is_available():
        raise RuntimeError("WAVESPEED_API_KEY 미설정 — 썸네일 곰 이미지를 생성할 수 없습니다.")
    extra: dict = {"num_images": 1}
    if seed is not None and seed >= 0:
        extra["seed"] = seed
    request = ImageGenerationRequest(
        prompt=prompt,
        reference_images=[sheet_url],
        aspect_ratio="9:16",
        output_path=str(dest),
        extra_params=extra,
    )
    asyncio.run(adapter.generate(request))


def _cream_white_ratio(png: Path) -> float:
    """이미지의 크림-흰색(곰 털) 픽셀 비율. ffmpeg 로 raw RGB 다운스케일 후 계산.

    PIL/numpy 의존 없이 ffmpeg 만으로 곰 존재를 추정한다(곰 미등장 컷 판정용).
    """
    raw = png.parent / f"{png.stem}_probe.raw"
    _run(
        ["-i", png.name, "-vf", f"scale={_PROBE}:{_PROBE}",
         "-pix_fmt", "rgb24", "-f", "rawvideo", raw.name],
        cwd=png.parent,
    )
    data = raw.read_bytes()
    raw.unlink(missing_ok=True)
    total = len(data) // 3
    if total == 0:
        return 0.0
    cream = 0
    for i in range(0, total * 3, 3):
        r, g, b = data[i], data[i + 1], data[i + 2]
        lo = min(r, g, b)
        hi = max(r, g, b)
        # 크림-흰색: 매우 밝고(저채도) 약간 따뜻한(R≳B) 픽셀.
        if lo >= 200 and (hi - lo) <= 45 and r + 8 >= b:
            cream += 1
    return cream / total


def _render_bear_background(
    out_dir: Path, sheet_url: str, anchor: str, tone: str, emotion: str, seed: int
) -> tuple[Path, bool]:
    """곰 썸네일 배경 생성 + 품질 게이트(3단계).

    1) 생성 → 크림-흰색 픽셀 비율 체크.
    2) 곰 미검출 시 seed 변경해 자동 재생성 1회.
    3) 그래도 실패면 thumbnail_fallback=True + WARNING(파이프라인은 멈추지 않음).

    Returns: (배경 png 경로, thumbnail_fallback)
    """
    prompt = build_thumbnail_prompt(anchor, tone, emotion)
    bg = out_dir / "bg.png"
    # 재생성은 seed 만 바꿔 동일 프롬프트로 1회.
    second_seed = (seed + 7919) if (seed is not None and seed >= 0) else 20260611
    attempts = [seed, second_seed]
    last_ratio = 0.0
    for i, s in enumerate(attempts, 1):
        _generate_bear_image(prompt, sheet_url, bg, s)
        last_ratio = _cream_white_ratio(bg)
        if last_ratio >= _BEAR_PIXEL_THRESHOLD:
            logger.info("썸네일 곰 검출 OK (시도 %d, 크림픽셀 %.3f)", i, last_ratio)
            return bg, False
        logger.warning(
            "썸네일 곰 미검출 (시도 %d, 크림픽셀 %.3f < %.3f)",
            i, last_ratio, _BEAR_PIXEL_THRESHOLD,
        )
    logger.warning("썸네일 자동생성 실패 — 수동 확인 필요 (크림픽셀 %.3f)", last_ratio)
    return bg, True


def _build_thumb_ass(hook_text: str, highlight: str, ass_path: Path) -> None:
    """썸네일 ASS(§4-(f)): 큰 굵은 2줄, 상단(Alignment=8), 두꺼운 외곽선, 노란 강조."""
    # 리터럴 '\n' 도 실제 줄바꿈으로 정규화한 뒤 _ass_text 가 \N 으로 변환.
    normalized = hook_text.replace("\\n", "\n")
    text = _ass_text(normalized, highlight)
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "WrapStyle: 0\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        # 폰트 확대(104→128) + 좌우 마진 축소(60→40)로 텍스트 블록이 화면 폭의
        # ~80~90% 를 차지. 두꺼운 외곽선(8)·그림자(6)로 가독성. 상단(Alignment=8).
        f"Style: Thumb,{_FONT},128,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "1,0,0,0,100,100,0,0,1,8,6,8,40,40,150,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )
    body = f"Dialogue: 0,0:00:00.00,9:00:00.00,Thumb,,0,0,0,,{text}\n"
    ass_path.write_text(header + body, encoding="utf-8")


def generate_thumbnail(
    image_url: str = "",
    hook_text: str = "",
    highlight: str = "",
    script: str = "",
    sheet_url: str = "",
    anchor: str = "",
    tone: str = "light",
    seed: int = -1,
    output_dir: str | None = None,
) -> dict:
    """후킹 문구 + 흰곰 이미지 → 썸네일 PNG. Returns {"thumbnail_url", ...}.

    sheet_url 이 주어지면 시트 레퍼런스(Kontext)로 썸네일 전용 곰 이미지를 직접
    생성한다(t2i 금지, 사람 등장 불가). 생성/품질게이트 실패 시 image_url(기존 씬
    컷)로 폴백하고 thumbnail_fallback=True 를 돌려준다(파이프라인은 멈추지 않음).
    sheet_url 이 없으면 image_url 을 배경으로 쓰는 기존 동작.
    """
    _require_ffmpeg()

    hook_text = (hook_text or "").strip()
    emotion = ""
    if not hook_text:
        if not script.strip():
            raise ValueError("hook_text 또는 script 중 하나는 필요합니다.")
        hook_text, highlight, emotion = _generate_hook(script)
    else:
        emotion = _guess_emotion(hook_text)

    tid = uuid.uuid4().hex[:12]
    out_dir = Path(output_dir or f"output/sayeon/thumbnails/{tid}")
    out_dir.mkdir(parents=True, exist_ok=True)

    bg = out_dir / "bg.png"
    thumbnail_fallback = False
    if sheet_url:
        # 곰 썸네일 직접 생성(시트 레퍼런스). 실패 시 기존 컷으로 폴백.
        try:
            _, thumbnail_fallback = _render_bear_background(
                out_dir, sheet_url, anchor, tone, emotion, seed
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("썸네일 곰 이미지 생성 실패 — 기존 컷으로 폴백: %s", e)
            thumbnail_fallback = True
            if not image_url:
                raise
            _fetch(image_url, bg)
    elif image_url:
        _fetch(image_url, bg)
    else:
        raise ValueError("image_url 또는 sheet_url 중 하나는 필요합니다.")

    ass = out_dir / "thumb.ass"
    _build_thumb_ass(hook_text, highlight, ass)
    out = out_dir / "thumb.png"
    # §4-(f): 단일 프레임 + ASS 오버레이. 입력 이미지를 9:16 로 스케일.
    _run([
        "-i", bg.name,
        "-vf", f"scale={W}:{H},ass={ass.name}",
        "-frames:v", "1",
        out.name,
    ], cwd=out_dir)

    thumbnail_url = str(out)
    persistent = False
    if r2_storage.is_available():
        try:
            thumbnail_url = r2_storage.upload_image(
                str(out), f"sayeon/thumbnails/{tid}/thumb.png", content_type="image/png"
            )
            persistent = True
        except Exception as e:  # noqa: BLE001
            logger.warning("썸네일 R2 업로드 실패, 로컬 경로 사용: %s", e)
    else:
        logger.warning("R2 미설정 — 썸네일이 로컬에만 있습니다.")

    return {
        "thumbnail_url": thumbnail_url,
        "persistent": persistent,
        "hook_text": hook_text,
        "highlight": highlight,
        "emotion": emotion,
        "thumbnail_fallback": thumbnail_fallback,
    }
