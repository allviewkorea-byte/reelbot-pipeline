"""쇼츠 대본 — 시즌 1 "돌잔치 D-14" 회차별 대본(한국어 자막·훅·장면) 생성 + 콘텐츠 규칙 검사.

Claude(music_lyrics._call, task=shorts_script) — Claude API 오류 시 #343 OpenAI 대체가 그대로 따라온다.
목소리는 이번 단계에서 쓰지 않는다(대표 결정): voice_line 은 생성·저장만, 영상은 무대사 + 자막 + 음악.

콘텐츠 규칙(대표 지시) — 프롬프트로 지시하고, 생성 결과는 check_rules() 로 **기계 검사**한다:
- 아기: 몸매·체중·다이어트 언급·연출 금지, 노출 연출 금지. 따라 하는 귀여운 조연까지만.
- 엄마: 체형 비하·놀림 금지, 체중 숫자 금지. 목표는 체력·자신감·돌잔치 원피스.
- 선정적 구도 금지(엉덩이·가슴 클로즈업 등). 운동 동작은 전신 또는 무릎 위 중거리.
- 실존 인물·브랜드 로고·글자 없음.
위반이면 사유를 붙여 다시 생성(최대 MAX_TRIES), 그래도 위반이면 ScriptRejected.
"""

from __future__ import annotations

import logging
import os
import re

from services import shorts_series

logger = logging.getLogger(__name__)

MAX_TRIES = 3
MIN_TOTAL, MAX_TOTAL = 15, 30          # 영상 길이(초)
MIN_SCENE, MAX_SCENE = 3, 15           # Kling O3 Reference duration 범위
_MODEL = os.getenv("SHORTS_SCRIPT_MODEL", "claude-sonnet-4-6")

ROLE_KO = {"dad": "아빠", "mom": "엄마", "baby": "아기"}


class ScriptRejected(RuntimeError):
    """콘텐츠 규칙을 끝내 통과하지 못한 대본."""


# ── 금지어 검사 ──────────────────────────────────────────────────────────
# (패턴, 사유). 한국어 자막·대사·요약과 영어 장면 묘사 모두에 적용.
_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\d+(\.\d+)?\s*(kg|㎏|킬로|키로|lbs?|pounds?)\b", re.I), "체중 숫자"),
    (re.compile(r"체중|몸무게|weigh(t|s|ing)\b|\bscale\b|체지방|BMI", re.I), "체중 언급"),
    (re.compile(r"다이어트|\bdiet(ing)?\b|살\s*빼|살\s*빠|감량|lose\s+weight|weight\s*loss|slim\s*down", re.I),
     "다이어트·감량 표현(시즌 목표는 체력·자신감)"),
    (re.compile(r"뚱뚱|돼지|살쪘|살찐|뱃살|똥배|비만|통통|못생|\bfat\b|chubby|obese|ugly|flabby", re.I),
     "체형 비하·놀림"),
    (re.compile(r"섹시|야하|엉덩이|가슴골|노출|볼륨\s*몸매|sexy|seductive|cleavage|\bbutt\b|buttock|booty|"
                r"lingerie|bikini|nude|naked|shirtless|topless|bare\s*(chest|skin)", re.I), "선정적 표현·노출"),
    (re.compile(r"close[\s-]*up\s+(of\s+)?(the\s+|her\s+|his\s+)?(chest|breast|hips?|butt|thighs?|body|belly|waist)",
                re.I), "신체 부위 클로즈업"),
    (re.compile(r"\b(logo|brand(ed)?|nike|adidas|puma|under\s*armour|lululemon|text\s+on\s+screen|"
                r"subtitles?|captions?|letters|signage)\b", re.I), "로고·브랜드·화면 글자"),
]
# 아기에게만 걸리는 추가 규칙(아기가 등장하는 장면 묘사에 적용).
_BABY_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"몸매|살(이|을|찐|쪄|빼|빠)|체형|배가|\bbody\s*(shape|line)|tummy|belly|figure", re.I), "아기 몸매·체형 언급"),
]


def check_rules(script: dict) -> list[str]:
    """위반 사유 목록(없으면 []). 한국어·영어 필드 전체 + 아기 장면 추가 규칙."""
    texts = [script.get("hook") or "", script.get("voice_line") or "", script.get("summary") or "",
             *(script.get("captions") or [])]
    for sc in script.get("scenes") or []:
        texts += [sc.get("caption") or "", sc.get("action_en") or "", sc.get("place") or ""]
    blob = "\n".join(t for t in texts if isinstance(t, str))
    found: list[str] = []
    for pat, why in _RULES:
        m = pat.search(blob)
        if m and why not in found:
            found.append(f"{why}: '{m.group(0)}'")
    for sc in script.get("scenes") or []:
        if "baby" in (sc.get("characters") or []):
            text = f"{sc.get('caption') or ''}\n{sc.get('action_en') or ''}"
            for pat, why in _BABY_RULES:
                m = pat.search(text)
                if m:
                    found.append(f"{why}: '{m.group(0)}'")
    return found


def check_shape(script: dict, characters: list[str]) -> list[str]:
    """구조 검사 — 장면 수·길이·등장 인물·자막 줄 수."""
    errs: list[str] = []
    scenes = script.get("scenes") or []
    if not (1 <= len(scenes) <= 3):
        errs.append("장면은 1~3개")
    total = 0
    for i, sc in enumerate(scenes):
        sec = sc.get("seconds")
        if not isinstance(sec, int) or not (MIN_SCENE <= sec <= MAX_SCENE):
            errs.append(f"장면 {i + 1} 길이는 {MIN_SCENE}~{MAX_SCENE}초 정수")
        else:
            total += sec
        chars = sc.get("characters") or []
        if not chars or any(c not in characters for c in chars):
            errs.append(f"장면 {i + 1} 등장 인물은 {characters} 중에서만")
        if not (sc.get("action_en") or "").strip():
            errs.append(f"장면 {i + 1} action_en 비어 있음")
    if scenes and not (MIN_TOTAL <= total <= MAX_TOTAL):
        errs.append(f"총 길이 {total}초 — {MIN_TOTAL}~{MAX_TOTAL}초여야 함")
    caps = script.get("captions") or []
    if not (1 <= len(caps) <= 2) or not (script.get("hook") or "").strip():
        errs.append("hook 1개 + captions 1~2줄")
    return errs


# ── 프롬프트 ─────────────────────────────────────────────────────────────
_SYSTEM = """너는 한국 유튜브 쇼츠(15~30초, 세로 9:16) 시리즈의 작가다.
시리즈: "돌잔치 D-14, 엄마의 2주 챌린지" — 첫 돌잔치까지 2주, 엄마가 체력·자신감을 되찾고 돌잔치 원피스를 입는 게 목표.
가족: 엄마(주인공·노력파·밝음), 아빠(근육질 헬스 마니아 — 코치 겸 귀여운 방해꾼), 아기(돌 무렵, 옆에서 따라 하는 귀여운 조연).
형식: A=셀카(말 없이 표정·제스처 + 자막), B=운동 동작, C=일상 에피소드. 목소리·대사 음성은 없다 — 화면 자막과 음악만.

반드시 지킬 것:
- 아기: 몸매·체중·다이어트·체형 언급이나 연출 금지. 노출 금지. '따라 하는 귀여운 조연'까지만.
- 엄마: 체형 비하·놀림 금지, 체중·kg 숫자 금지, '다이어트/살 빼기' 대신 체력·자신감·원피스 같은 긍정 목표.
- 선정적 구도 금지(엉덩이·가슴 클로즈업 등). 운동 동작은 전신 또는 무릎 위 중거리 샷.
- 실존 인물·브랜드·로고·화면 속 글자 없음(자막은 우리가 따로 얹는다).
- 첫 1~2초 훅 자막으로 시선을 잡는다. 자막은 짧은 한국어 구어체.

JSON 만 출력:
{"hook": "첫 1~2초 훅 자막(한국어, 15자 내외)",
 "captions": ["본 자막 1(한국어, 20자 내외)", "본 자막 2(선택)"],
 "voice_line": "엄마의 속마음 한 문장(저장만, 음성으로 쓰지 않음)",
 "scenes": [{"seconds": 정수 3~15, "place": "장소(한국어)", "characters": ["mom", ...],
             "action_en": "영어로 쓴 화면 묘사 — 인물 동작·표정·카메라(전신 또는 무릎 위 중거리, 세로 구도). 이름·글자·로고 언급 금지",
             "caption": "이 장면 자막(선택, 한국어)"}],
 "summary": "이번 회차 한 줄 요약(다음 회차 연속성용, 한국어)"}
장면 1~3개, seconds 합계 15~30초."""


def _user_prompt(series: dict, ep: dict, characters: list[str], feedback: list[str]) -> str:
    prev = shorts_series.previous_summaries(series, ep["day"])
    who = ", ".join(f"{c}({ROLE_KO.get(c, c)})" for c in characters)
    lines = [
        f"회차: Day {ep['day']} ({ep['dday']}, 이야기 속 날짜) / 형식: {ep['format']} = "
        f"{shorts_series.FORMATS[ep['format']]}",
        f"계획 메모: {ep['plan']}",
        f"등장 인물(이 외 인물 금지): {who}",
        f"엄마 단계: {ep['mom_stage']} (mom=시작, mom_mid=점점 탄탄해지는 중, mom_after=같은 사람, 더 탄탄·자신감)",
    ]
    if ep.get("finale"):
        lines.append("마지막 편: 돌잔치 당일 가족사진. 돌잔치 의상(엄마 원피스·아빠 정장·아기 돌복).")
    if "baby" not in characters and "baby" in ep["characters"]:
        lines.append("※ 이번 회차는 아기 없이(엄마·아빠만) 같은 이야기를 자연스럽게 풀어라.")
    if prev:
        lines.append("지난 회차: " + " / ".join(prev))
    if feedback:
        lines.append("이전 출력이 규칙을 어겼다 — 고쳐서 다시: " + "; ".join(feedback))
    return "\n".join(lines)


def generate(series: dict, ep: dict, *, exclude: tuple[str, ...] = (), call=None) -> dict:
    """회차 대본 생성 + 규칙·구조 검사(위반 시 재시도). exclude=("baby",) 면 아기 없는 대본."""
    from services import music_lyrics
    call = call or (lambda s, u: music_lyrics._call(s, u, max_tokens=1500, model=_MODEL,
                                                    task="shorts_script", strong=True))
    characters = [c for c in ep["characters"] if c not in exclude]
    if not characters:
        raise ScriptRejected("등장 인물이 없습니다.")
    feedback: list[str] = []
    for attempt in range(1, MAX_TRIES + 1):
        raw = call(_SYSTEM, _user_prompt(series, ep, characters, feedback))
        try:
            script = music_lyrics._extract_json(raw)
        except RuntimeError:
            feedback = ["JSON 형식이 아님"]
            continue
        if not isinstance(script, dict):
            feedback = ["JSON 객체가 아님"]
            continue
        feedback = check_shape(script, characters) + check_rules(script)
        if not feedback:
            script["characters"] = characters
            script["attempts"] = attempt
            return script
        logger.warning("[shorts-script] Day %s 시도 %d 위반: %s", ep["day"], attempt, feedback)
    raise ScriptRejected(f"Day {ep['day']} 대본이 규칙을 통과하지 못했습니다: {feedback}")
