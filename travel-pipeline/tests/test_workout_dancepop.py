"""운동 채널 댄스팝 위주 스타일·여성 보컬 70%(대표 결정 2026-10-20)."""
import random
from collections import Counter

from services import music_produce as mp
from services import music_workout_style as ws


def test_boost_is_dancepop_and_has_no_vocal_words():
    for axis in ("strength", "cardio"):
        b = ws.style_booster("weight" if axis == "strength" else "running", channel="workout_music")
        assert "dance-pop" in b and "BPM" in b and "808" not in b
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


def test_tempo_mix_varies_per_song():
    """2026-10-28: 매번 같은 BPM은 지루 — 빠름·중간·미드템포 섞기. warmup 은 고정."""
    import random
    rng = random.Random(7)
    got = [ws.pick_tempo("strength", rng) for _ in range(300)]
    assert len(set(got)) == 3 and got.count("150-160 BPM") < 180
    assert {ws.pick_tempo("warmup", rng) for _ in range(20)} == {"90-100 BPM"}
    assert ws.style_booster("stretching", channel="workout_music").endswith("90-100 BPM")


def test_tempo_plan_spreads_within_one_video():
    """영상 1개 안에서 비율대로 나눠 배정, 같은 템포 연달아 안 놓음, where 는 None."""
    import random
    plan = ws.tempo_plan(6, "weight", channel="workout_music", rng=random.Random(3))
    fast = "150-160 BPM"
    assert len(plan) == 6 and 2 <= plan.count(fast) <= 3 and len(set(plan)) == 3
    assert all(plan[i] != plan[i + 1] for i in range(5))                 # 같은 템포 연달아 없음
    assert ws.tempo_plan(3, "weight", channel="rooftop_music") == [None, None, None]
    st = ws.lock_vocal_style("house, for workout", None, "weight", tempo="110-118 BPM, mid-tempo groove")
    assert "110-118 BPM" in st and "unhurried vocal delivery" in st and "150-160" not in st
