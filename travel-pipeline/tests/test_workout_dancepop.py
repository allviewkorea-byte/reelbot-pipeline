"""운동 채널 댄스팝 위주 스타일·여성 보컬 70%(대표 결정 2026-10-20)."""
import random
from collections import Counter

from services import music_produce as mp
from services import music_workout_style as ws


def test_boost_is_dancepop_and_has_no_vocal_words():
    for axis in ("strength", "cardio"):
        b = ws._STYLE_BOOST[axis]
        assert "dance-pop" in b and "150-160 BPM" in b and "808" not in b
        assert "vocal" not in b.lower()          # 연주곡에도 붙으므로 보컬 단어 금지
    assert "90-100 BPM" in ws._STYLE_BOOST["warmup"]  # 스트레칭은 그대로


def test_negative_blocks_choppy_beats_except_warmup():
    for axis in ("strength", "cardio"):
        assert "trap hi-hat rolls" in ws._NEGATIVE[axis] and "drum and bass" in ws._NEGATIVE[axis]
    assert "trap" not in ws._NEGATIVE["warmup"]


def test_main_genre_pop_about_70_percent():
    random.seed(7)
    combos = [ws.refine_combo({"action": "workout", "genre": ["x"]}, channel=ws.WORKOUT_CHANNEL) for _ in range(2000)]
    first = Counter(c["genre"][0] for c in combos)
    assert abs(first["pop"] / 2000 - 0.7) < 0.04
    assert all(len(set(c["genre"])) == len(c["genre"]) for c in combos)       # 중복 장르 없음
    assert any("hiphop" in c["genre"] for c in combos) and any("triphop" in c["genre"] for c in combos)  # 변화 유지


def test_warmup_genres_unchanged_rule():
    random.seed(3)
    c = ws.refine_combo({"action": "stretching", "genre": ["x"]}, channel=ws.WORKOUT_CHANNEL)
    assert set(c["genre"]) <= set(ws._AXIS_POOLS["warmup"]["genre"])


def test_female_vocal_about_70_percent_on_workout_only():
    random.seed(11)
    g = [x for _ in range(400) for x in mp._assign_genders(10, ws.WORKOUT_CHANNEL)]
    assert abs(g.count("female") / len(g) - 0.7) < 0.03
    where = mp._assign_genders(10, "rooftop_music")
    assert "female" in where and "male" in where                              # where 는 기존(남녀 최소 1곡씩)
