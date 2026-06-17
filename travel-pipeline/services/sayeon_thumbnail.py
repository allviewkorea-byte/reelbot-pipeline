"""사연 트랙 — 썸네일 자동 생성 (PR-S5 / 씬 이미지 선택 방식).

해당 사연의 **씬 이미지 1장을 그대로 배경**으로 쓰고 그 위에 후킹 카피(큰 글씨 +
노란 강조)를 오버레이해 썸네일 PNG 를 만든다. 부록 §4-(f) 레시피(ffmpeg 단일 프레임
+ ASS 오버레이) 그대로.

⚠️ 썸네일용 이미지를 새로 생성하지 않는다(추가 생성 비용 0, 실제 영상 장면과 일치).
어떤 씬을 쓸지(마지막 질문 엔딩 제외, 감정 피크 우선 등)는 오케스트레이터가 골라
image_url 로 넘긴다. 여기서는 받은 배경 위에 카피만 얹는다.

후킹 문구는 hook_text 가 주어지면 그대로, 없으면 script 로 gpt-4o-mini 가 생성한다.
렌더링/다운로드 헬퍼는 S4 합성 엔진(sayeon_assemble)의 것을 재사용한다.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path

from openai import OpenAI

from adapters import r2_storage
# S4 합성 엔진의 검증된 헬퍼 재사용(재발명 금지).
from services.sayeon_assemble import _fetch, _require_ffmpeg, _run

logger = logging.getLogger(__name__)

W, H = 1080, 1920
_FONT = "Noto Sans CJK KR"
_OPENAI_MODEL = "gpt-4o-mini"

# ⑩ 피크 감정 → 주인공(흰곰) 표정 시트 아스펙트(썸네일 거대 얼굴 베이스).
_EMO_TO_EXPR = {
    "shock": "expr_surprised",
    "anger": "expr_angry",
    "sadness": "expr_sad",
}
# ⑩ 썸네일 핵심구 감정색(ASS BGR &HBBGGRR&). 자막용 색과 별개(썸네일 전용 톤).
_THUMB_DEFAULT_COLOR = "&H00F0FF&"  # 노랑(기본)
_THUMB_EMO_COLOR = {
    "anger": "&H0000FF&",    # 빨강
    "shock": "&H008CFF&",    # 주황
    "sadness": "&HEBCE87&",  # 하늘(sky #87CEEB)
    "joy": "&H00FFFF&",      # 노랑
}
# 후킹 카피 위 반투명 다크 밴드 높이(상단 2줄 텍스트 영역을 덮어 가독성 확보).
_BAND_H = 660


def _strip_code_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _generate_hook(script: str) -> tuple[str, str]:
    """사연 대본 → (hook_text 2줄, highlight 핵심구). gpt-4o-mini JSON 모드."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 미설정 — 후킹 문구를 생성할 수 없습니다.")
    client = OpenAI(api_key=api_key)
    system = (
        "너는 한국 '사연' 숏폼 영상의 썸네일 카피라이터다. 사연 대본을 받아 클릭을 "
        "유도하는 2줄 후킹 문구와 그중 강조할 핵심구를 만든다.\n"
        "[스타일 — 클리프행어(반전 암시 + 열린 결말)]\n"
        "- 패턴: [구체적 상황 셋업(숫자·시간 들어가면 더 좋음)]…[반전·결말을 암시하며 '…'로 끊기].\n"
        "- 결과를 살짝 흘리되 감정적 반전 직전에서 말줄임표(…)로 끊어 궁금증을 극대화한다.\n"
        "- '결국…', '하지만…', '그런데 그때…', '…했는데' 처럼 감정 반전을 암시하되 답·결말은 누설 금지.\n"
        "- ⚠️ 물음표로 끝내지 말 것(‘~는?’, ‘~일까?’ 금지). 질문형이 아니라 끊긴 서술형으로.\n"
        "- 각 줄 8~14자 내외로 짧고 강하게. 구체적 숫자·금액·기간 활용 권장('3년 만에','500만원').\n"
        "[예시]\n"
        '- ✅ "강아지가 사라진 5시간…\\n발견했지만 결국…" (셋업 후 반전 직전 끊김)\n'
        '- ✅ "시어머니가 통장을 보더니…\\n그날로 연을 끊었는데…"\n'
        '- ✅ "남친 집에서 그걸 본 순간…\\n하지만 진짜는 따로 있었다…"\n'
        '- ❌ "강아지가 사라진 5시간…\\n할아버지의 결단은?" (물음표 종결 금지)\n'
        "[규칙]\n"
        "- 출력은 오직 JSON 객체 하나. 마크다운/설명 금지.\n"
        "- hook_text: 2줄(줄바꿈은 \\n), 물음표로 끝나지 않게.\n"
        "- highlight: hook_text 안에 실제로 들어있는 핵심구(부분문자열).\n"
        '[출력] {"hook_text":"강아지가 사라진 5시간…\\n발견했지만 결국…","highlight":"결국…"}'
    )
    user = f"[사연 대본]\n{script.strip()}\n\n위 사연의 클리프행어 썸네일 후킹을 JSON으로 출력하라."
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
    return hook, highlight


def _fallback_hook(script: str) -> tuple[str, str]:
    """LLM 후킹 실패/키 없음 시 안전 폴백(예외 방지). 대본 첫 문장을 2줄로 다듬는다."""
    text = " ".join(line.strip() for line in (script or "").splitlines() if line.strip())
    if not text:
        return ("무슨 일이…?", "")
    # 첫 문장(또는 앞부분) ~22자 → 가운데서 2줄로.
    import re as _re
    first = _re.split(r"(?<=[.?!…])\s+", text)[0].strip() or text
    first = first[:22].rstrip()
    if len(first) > 11:
        cut = first.rfind(" ", 0, 12)
        cut = cut if cut > 0 else 11
        hook = f"{first[:cut].rstrip()}\n{first[cut:].lstrip()}…"
    else:
        hook = f"{first}…"
    return (hook, "")


def _resolve_base(scene_url: str, emotion: str) -> tuple[str, bool]:
    """썸네일 베이스 결정 — 피크 감정이면 주인공 표정 시트(거대 얼굴) 우선, 없으면 씬 이미지.

    Returns (base_url, is_face). is_face 면 합성 시 비네팅으로 얼굴에 시선 집중.
    expr_* 시트가 R2에 없으면 graceful 폴백(기존 씬 이미지·기존 동작).
    """
    aspect = _EMO_TO_EXPR.get((emotion or "").strip().lower())
    if aspect and r2_storage.is_available() and r2_storage.cast_aspect_exists("protagonist", aspect):
        return r2_storage.cast_aspect_url("protagonist", aspect), True
    return scene_url, False


def _build_thumb_ass(hook_text: str, highlight: str, emotion: str, ass_path: Path) -> None:
    """썸네일 ASS: 큰 굵은 2줄, 상단(Alignment=8), 두꺼운 외곽선, 핵심구 확대+감정색."""
    # 리터럴 '\n' 도 실제 줄바꿈으로 정규화. 핵심구는 더 크게(fs168)+감정색으로 강조.
    normalized = hook_text.replace("\\n", "\n").strip()
    color = _THUMB_EMO_COLOR.get((emotion or "").strip().lower(), _THUMB_DEFAULT_COLOR)
    text = normalized
    hl = (highlight or "").strip()
    if hl and hl in text:
        text = text.replace(hl, f"{{\\fs168\\c{color}}}{hl}{{\\fs128\\c&HFFFFFF&}}", 1)
    text = text.replace("\r\n", "\\N").replace("\n", "\\N")
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
    image_url: str,
    hook_text: str = "",
    highlight: str = "",
    script: str = "",
    emotion: str = "",
    output_dir: str | None = None,
) -> dict:
    """베이스(거대 감정 얼굴 또는 씬 이미지) + 후킹 카피 오버레이 → 썸네일 PNG.

    ⑩ 베이스 = 피크 감정이면 주인공 표정 시트(cast/protagonist/expr_*) 거대 얼굴,
    없으면 image_url(씬 이미지)로 graceful 폴백. 텍스트는 반투명 다크 밴드 위에
    흰 글씨 + 핵심구 확대·감정색. 새 이미지 생성 없음(비용 0). Returns {"thumbnail_url", ...}.
    """
    _require_ffmpeg()
    if not image_url:
        raise ValueError("image_url 이 필요합니다.")

    # 후킹 카피 — 없으면 LLM 생성, 실패해도 폴백(예외 방지).
    hook_text = (hook_text or "").strip()
    if not hook_text:
        if script.strip():
            try:
                hook_text, highlight = _generate_hook(script)
            except Exception as e:  # noqa: BLE001
                logger.warning("후킹 생성 실패 → 폴백 카피 사용: %s", e)
                hook_text, highlight = _fallback_hook(script)
        if not hook_text:
            hook_text, highlight = _fallback_hook(script)

    # ⑩ 베이스 결정(피크 감정 얼굴 우선, 없으면 씬). is_face 면 비네팅 적용.
    base_url, is_face = _resolve_base(image_url, emotion)

    tid = uuid.uuid4().hex[:12]
    out_dir = Path(output_dir or f"output/sayeon/thumbnails/{tid}")
    out_dir.mkdir(parents=True, exist_ok=True)

    bg = out_dir / "bg.png"
    _fetch(base_url, bg)
    ass = out_dir / "thumb.ass"
    _build_thumb_ass(hook_text, highlight, emotion, ass)
    out = out_dir / "thumb.png"
    # 단일 프레임 합성: 9:16 cover-crop(왜곡 방지) → (얼굴 베이스면 비네팅) →
    # 상단 반투명 다크 밴드(텍스트 가독성) → ASS 후킹 카피.
    vf_parts = [
        f"scale={W}:{H}:force_original_aspect_ratio=increase",
        f"crop={W}:{H}",
        "setsar=1",
    ]
    if is_face:
        vf_parts.append("vignette=PI/4")
    vf_parts.append(f"drawbox=x=0:y=0:w={W}:h={_BAND_H}:color=black@0.42:t=fill")
    vf_parts.append(f"ass={ass.name}")
    _run([
        "-i", bg.name,
        "-vf", ",".join(vf_parts),
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
    }
