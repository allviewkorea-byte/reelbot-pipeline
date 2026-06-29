/**
 * 8축 태그 풀 SSOT — 프론트엔드.
 * 백엔드: travel-pipeline/services/music_tags.py (동일 구조, 둘 다 갱신).
 *
 * Q&A 단계 순서: 어떨때(드롭다운) → 장르 → 상황 → 감정 → 템포 → 형식 → 매력
 */

export interface Tag {
  id: string
  label_kr: string
  prompt_en: string
}

export interface TagAxis {
  key: string
  label_kr: string
  emoji: string
  tags: Tag[]
}

// ── 축1 어떨때(행동) — 메인 드롭다운 ──────────────────────────────
export const ACTION_TAGS: Tag[] = [
  { id: "study", label_kr: "공부할때", prompt_en: "for studying, focus" },
  { id: "work", label_kr: "일할때", prompt_en: "for working, productivity" },
  { id: "workout", label_kr: "운동할때", prompt_en: "for workout, energetic" },
  { id: "running", label_kr: "러닝할때", prompt_en: "for running, high energy" },
  { id: "sleep", label_kr: "잠들때", prompt_en: "for sleep, soothing lullaby" },
  { id: "rest", label_kr: "휴식할때", prompt_en: "for relaxation, unwinding" },
  { id: "drive", label_kr: "운전할때", prompt_en: "for driving, cruising" },
  { id: "drive_scenic", label_kr: "드라이브할때", prompt_en: "for scenic drive, road trip" },
  { id: "commute_morning", label_kr: "출근할때", prompt_en: "morning commute, uplifting start" },
  { id: "commute_evening", label_kr: "퇴근할때", prompt_en: "evening commute, unwinding" },
  { id: "cafe", label_kr: "카페에서", prompt_en: "cafe ambience, coffee shop" },
  { id: "walk", label_kr: "산책할때", prompt_en: "for a walk, strolling" },
  { id: "cleaning", label_kr: "청소할때", prompt_en: "for cleaning, upbeat chores" },
  { id: "cooking", label_kr: "요리할때", prompt_en: "for cooking, kitchen vibes" },
  { id: "shower", label_kr: "샤워할때", prompt_en: "for shower, sing-along" },
  { id: "reading", label_kr: "독서할때", prompt_en: "for reading, quiet focus" },
  { id: "coding", label_kr: "코딩할때", prompt_en: "for coding, deep focus" },
  { id: "meditation", label_kr: "명상할때", prompt_en: "for meditation, mindfulness" },
  { id: "date", label_kr: "데이트할때", prompt_en: "for a date, romantic" },
  { id: "singing", label_kr: "노래하고싶을때", prompt_en: "sing-along, karaoke vibe" },
  { id: "swimming", label_kr: "물놀이할때", prompt_en: "for swimming, summer pool" },
  { id: "pet", label_kr: "애견과함께있을때", prompt_en: "with pets, gentle and warm" },
  { id: "couple", label_kr: "남친여친과함께있을때", prompt_en: "with significant other, romantic" },
  { id: "startup", label_kr: "창업할때", prompt_en: "for entrepreneurship, motivational" },
  { id: "zone_out", label_kr: "멍때리고싶을때", prompt_en: "zoning out, ambient drift" },
  { id: "confidence", label_kr: "자신감얻고싶을때", prompt_en: "for confidence boost, empowering" },
  { id: "hungry", label_kr: "배고플때", prompt_en: "feeling hungry, fun and playful" },
  { id: "full", label_kr: "배부를때", prompt_en: "after a meal, cozy and satisfied" },
  { id: "stretching", label_kr: "스트레칭할때", prompt_en: "for stretching, gentle flow" },
  { id: "pilates", label_kr: "필라테스할때", prompt_en: "for pilates, controlled tempo" },
  { id: "yoga", label_kr: "요가할때", prompt_en: "for yoga, serene and balanced" },
]

// ── 축2~8 (칩 기반) ──────────────────────────────────────────────

export const GENRE_TAGS: Tag[] = [
  { id: "citypop", label_kr: "시티팝", prompt_en: "city pop" },
  { id: "lofi", label_kr: "로파이", prompt_en: "lo-fi" },
  { id: "jazz", label_kr: "재즈", prompt_en: "jazz" },
  { id: "acoustic", label_kr: "어쿠스틱", prompt_en: "acoustic" },
  { id: "piano", label_kr: "피아노", prompt_en: "piano" },
  { id: "rnb", label_kr: "R&B", prompt_en: "R&B" },
  { id: "ballad", label_kr: "발라드", prompt_en: "ballad" },
  { id: "pop", label_kr: "팝", prompt_en: "pop" },
  { id: "indie", label_kr: "인디", prompt_en: "indie" },
  { id: "bossanova", label_kr: "보사노바", prompt_en: "bossa nova" },
  { id: "ambient", label_kr: "앰비언트", prompt_en: "ambient" },
  { id: "classical", label_kr: "클래식", prompt_en: "classical" },
  { id: "electronic", label_kr: "일렉트로닉", prompt_en: "electronic" },
  { id: "synthwave", label_kr: "신스웨이브", prompt_en: "synthwave" },
  { id: "soul", label_kr: "소울", prompt_en: "soul" },
  { id: "neosoul", label_kr: "네오소울", prompt_en: "neo soul" },
  { id: "dreampop", label_kr: "드림팝", prompt_en: "dream pop" },
  { id: "hiphop", label_kr: "힙합", prompt_en: "hip-hop" },
  { id: "lofihiphop", label_kr: "로파이힙합", prompt_en: "lo-fi hip-hop" },
  { id: "chillhop", label_kr: "칠합", prompt_en: "chill hop" },
  { id: "triphop", label_kr: "트립합", prompt_en: "trip-hop" },
  { id: "house", label_kr: "하우스", prompt_en: "house" },
  { id: "deephouse", label_kr: "딥하우스", prompt_en: "deep house" },
  { id: "jazzhop", label_kr: "재즈합", prompt_en: "jazz hop" },
  { id: "newage", label_kr: "뉴에이지", prompt_en: "new age" },
  { id: "kindie", label_kr: "K인디", prompt_en: "Korean indie" },
  { id: "kballad", label_kr: "K발라드", prompt_en: "Korean ballad" },
  { id: "sensballad", label_kr: "감성발라드", prompt_en: "emotional ballad" },
]

export const SITUATION_TAGS: Tag[] = [
  { id: "rain", label_kr: "비올때", prompt_en: "rainy day" },
  { id: "snow", label_kr: "눈올때", prompt_en: "snowy day" },
  { id: "sunny", label_kr: "맑은날", prompt_en: "sunny day" },
  { id: "cloudy", label_kr: "흐린날", prompt_en: "cloudy day" },
  { id: "first_snow", label_kr: "첫눈", prompt_en: "first snow" },
  { id: "spring", label_kr: "봄", prompt_en: "spring" },
  { id: "summer", label_kr: "여름", prompt_en: "summer" },
  { id: "autumn", label_kr: "가을", prompt_en: "autumn" },
  { id: "winter", label_kr: "겨울", prompt_en: "winter" },
  { id: "breakup", label_kr: "헤어질때", prompt_en: "breakup, farewell" },
  { id: "meeting", label_kr: "만날때", prompt_en: "meeting someone" },
  { id: "confession", label_kr: "고백할때", prompt_en: "confession, first love" },
  { id: "alone", label_kr: "혼자일때", prompt_en: "alone, solitude" },
  { id: "window", label_kr: "창밖을볼때", prompt_en: "looking out the window" },
  { id: "lights_off", label_kr: "불끄고누웠을때", prompt_en: "lying in the dark" },
]

export const EMOTION_TAGS: Tag[] = [
  { id: "lonely", label_kr: "외로움", prompt_en: "lonely" },
  { id: "sad", label_kr: "슬픔", prompt_en: "sad" },
  { id: "nostalgic", label_kr: "그리움", prompt_en: "nostalgic, longing" },
  { id: "depressed", label_kr: "우울", prompt_en: "melancholic" },
  { id: "desolate", label_kr: "쓸쓸함", prompt_en: "desolate" },
  { id: "happy", label_kr: "기분좋음", prompt_en: "happy, feel good" },
  { id: "refreshed", label_kr: "기분전환", prompt_en: "mood refresh, uplifting" },
  { id: "excited", label_kr: "설렘", prompt_en: "excited, fluttering" },
  { id: "heartbeat", label_kr: "두근거림", prompt_en: "heart-pounding" },
  { id: "positive", label_kr: "긍정", prompt_en: "positive, optimistic" },
  { id: "hopeful", label_kr: "희망", prompt_en: "hopeful, inspiring" },
  { id: "passionate", label_kr: "열정", prompt_en: "passionate, fiery" },
  { id: "calm", label_kr: "차분함", prompt_en: "calm, composed" },
  { id: "peaceful", label_kr: "평온", prompt_en: "peaceful, serene" },
  { id: "drowsy", label_kr: "나른함", prompt_en: "drowsy, lazy" },
  { id: "dreamy", label_kr: "몽환", prompt_en: "dreamy, ethereal" },
  { id: "comfort", label_kr: "위로", prompt_en: "comforting, consoling" },
  { id: "warm", label_kr: "따뜻함", prompt_en: "warm, heartwarming" },
  { id: "overwhelmed", label_kr: "벅참", prompt_en: "overwhelmed with emotion" },
  { id: "free", label_kr: "자유로움", prompt_en: "free, liberating" },
  { id: "sentimental", label_kr: "센치함", prompt_en: "sentimental" },
]

export const TEMPO_TAGS: Tag[] = [
  { id: "gentle", label_kr: "잔잔한", prompt_en: "gentle, soft" },
  { id: "slow", label_kr: "느린", prompt_en: "slow tempo" },
  { id: "relaxed", label_kr: "편안한", prompt_en: "relaxed" },
  { id: "moderate", label_kr: "적당한", prompt_en: "moderate tempo" },
  { id: "lively", label_kr: "경쾌한", prompt_en: "lively, bouncy" },
  { id: "upbeat", label_kr: "신나는", prompt_en: "upbeat, exciting" },
  { id: "fast", label_kr: "빠른", prompt_en: "fast tempo" },
  { id: "intense", label_kr: "강렬한", prompt_en: "intense, powerful" },
]

export const FORMAT_TAGS: Tag[] = [
  { id: "vocal", label_kr: "보컬있음", prompt_en: "with vocals" },
  { id: "instrumental", label_kr: "연주곡(가사없음)", prompt_en: "instrumental, no lyrics" },
  { id: "piano_solo", label_kr: "피아노솔로", prompt_en: "piano solo" },
  { id: "guitar_solo", label_kr: "어쿠스틱기타솔로", prompt_en: "acoustic guitar solo" },
  { id: "inst_only", label_kr: "인스트루멘탈", prompt_en: "pure instrumental" },
  { id: "beats_only", label_kr: "비트만(가사없는비트)", prompt_en: "beats only, no vocals" },
  { id: "nature_mix", label_kr: "자연소리믹스(음악+자연)", prompt_en: "nature sounds mixed with music" },
  { id: "nature_only", label_kr: "자연소리만(음악없음)", prompt_en: "nature sounds only, no music" },
]

export const CHARM_TAGS: Tag[] = [
  { id: "melody", label_kr: "멜로디가인상적인", prompt_en: "memorable melody" },
  { id: "beat", label_kr: "비트가매력적인", prompt_en: "attractive beat" },
  { id: "addictive", label_kr: "중독성있는", prompt_en: "addictive, catchy" },
  { id: "refined", label_kr: "세련된", prompt_en: "refined, sophisticated" },
  { id: "immersive", label_kr: "편안하게빠져드는", prompt_en: "immersive, easy listening" },
  { id: "emotional", label_kr: "감성을자극하는", prompt_en: "emotionally evocative" },
  { id: "refreshing", label_kr: "청량한", prompt_en: "refreshing, crisp" },
  { id: "deep", label_kr: "깊이있는", prompt_en: "deep, profound" },
]

// Q&A 칩 단계 순서 (어떨때는 드롭다운이므로 여기 미포함)
export const CHIP_AXES: TagAxis[] = [
  { key: "genre", label_kr: "장르", emoji: "🎵", tags: GENRE_TAGS },
  { key: "situation", label_kr: "상황", emoji: "🌧️", tags: SITUATION_TAGS },
  { key: "emotion", label_kr: "감정", emoji: "💗", tags: EMOTION_TAGS },
  { key: "tempo", label_kr: "템포", emoji: "⏱️", tags: TEMPO_TAGS },
  { key: "format", label_kr: "형식", emoji: "🎙️", tags: FORMAT_TAGS },
  { key: "charm", label_kr: "매력", emoji: "✨", tags: CHARM_TAGS },
]

// ── 충돌 규칙 — 행동 그룹별 숨길 칩 ──────────────────────────────

const CALM_ACTIONS = new Set(["sleep", "meditation", "rest", "yoga", "stretching", "pilates"])
const INTENSE_ACTIONS = new Set(["workout", "running", "confidence"])

export type HiddenChips = Record<string, Set<string>>

export function getHiddenChips(actionId: string | null): HiddenChips {
  if (!actionId) return {}
  const hidden: HiddenChips = {}

  if (CALM_ACTIONS.has(actionId)) {
    hidden.tempo = new Set(["intense", "fast", "upbeat"])
    hidden.charm = new Set(["addictive", "beat"])
  }
  if (INTENSE_ACTIONS.has(actionId)) {
    hidden.tempo = new Set(["gentle", "slow"])
  }
  if (actionId === "meditation") {
    hidden.format = new Set(
      FORMAT_TAGS.filter((t) => t.id !== "instrumental").map((t) => t.id),
    )
  }
  if (actionId === "singing") {
    hidden.format = new Set(["instrumental", "inst_only", "nature_only", "beats_only"])
  }
  return hidden
}

// ── 태그 콤보 타입 ──────────────────────────────────────────────
export interface TagCombo {
  action?: string
  genre?: string[]
  situation?: string[]
  emotion?: string[]
  tempo?: string[]
  format?: string[]
  charm?: string[]
}
