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
from services.sayeon_assemble import _ass_text, _fetch, _require_ffmpeg, _run

logger = logging.getLogger(__name__)

W, H = 1080, 1920
_FONT = "Noto Sans CJK KR"
_OPENAI_MODEL = "gpt-4o-mini"


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
        "[공식 — 궁금증 생성 + 답 미공개]\n"
        "- 궁금증을 폭발시키되 결말·답은 절대 누설하지 않는다(스포일러 금지).\n"
        "- 각 줄 8~14자 내외로 짧고 강하게. 말줄임표(…)·의문형을 적극 사용한다.\n"
        "- 구체적 숫자·금액·기간을 활용하면 좋다(예: '3년 만에', '500만원').\n"
        '- 예: "시어머니가 제 통장을\\n보더니…" / "남친 집에서\\n이걸 발견했습니다".\n'
        "[규칙]\n"
        "- 출력은 오직 JSON 객체 하나. 마크다운/설명 금지.\n"
        "- hook_text: 2줄(줄바꿈은 \\n).\n"
        "- highlight: hook_text 안에 실제로 들어있는 핵심구(부분문자열).\n"
        '[출력] {"hook_text":"시어머니가 제 통장을\\n보더니…","highlight":"통장을"}'
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
    return hook, highlight


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
    image_url: str,
    hook_text: str = "",
    highlight: str = "",
    script: str = "",
    output_dir: str | None = None,
) -> dict:
    """씬 이미지(image_url) 배경 + 후킹 카피 오버레이 → 썸네일 PNG.

    image_url 은 오케스트레이터가 고른 해당 사연의 씬 이미지(마지막 질문 엔딩 제외,
    감정 피크 우선). 새 이미지를 생성하지 않으므로 추가 비용이 없고 실제 장면과 일치한다.
    Returns {"thumbnail_url", ...}.
    """
    _require_ffmpeg()
    if not image_url:
        raise ValueError("image_url 이 필요합니다.")

    hook_text = (hook_text or "").strip()
    if not hook_text:
        if not script.strip():
            raise ValueError("hook_text 또는 script 중 하나는 필요합니다.")
        hook_text, highlight = _generate_hook(script)

    tid = uuid.uuid4().hex[:12]
    out_dir = Path(output_dir or f"output/sayeon/thumbnails/{tid}")
    out_dir.mkdir(parents=True, exist_ok=True)

    bg = out_dir / "bg.png"
    _fetch(image_url, bg)
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
    }
