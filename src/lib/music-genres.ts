// 장르 체계 SSOT(프론트, #45) — 14장르 마스터 목록 + 분류 키워드 + 막대 색상.
// 백엔드 SSOT는 travel-pipeline/services/music_genres.py — 둘을 함께 갱신한다.
//
// 색상은 인라인 hex(기존 트렌드 패널 패턴) — globals.css 토큰/신규 디자인 토큰 아님.
// 키워드는 substring 매칭이라 너무 짧은 단어 금지("pop"은 citypop/kpop 오염).
// 옛 5분류 저장값도 잡히도록 레거시 단어를 포함(하위호환).

export interface MusicGenre {
  id: string
  label: string
  color: string
  keywords: string[]
}

export const MUSIC_GENRES: MusicGenre[] = [
  { id: "citypop", label: "시티팝", color: "#8b5cf6", keywords: ["시티팝", "citypop", "city pop", "시티 팝", "네온", "neon"] },
  { id: "sunset_drive", label: "선셋 드라이브", color: "#f97316", keywords: ["선셋", "sunset", "석양", "노을", "드라이브", "drive", "운전", "cruise", "해질", "신스웨이브", "synthwave"] },
  { id: "morning_drive", label: "모닝 드라이브", color: "#fbbf24", keywords: ["모닝", "morning", "출근", "아침", "commute", "산뜻", "상쾌"] },
  { id: "cafe", label: "카페", color: "#d97706", keywords: ["카페", "cafe", "café", "커피", "coffee", "브런치", "brunch", "라운지", "lounge", "보사노바", "bossa", "어쿠스틱", "acoustic"] },
  { id: "jazz", label: "재즈", color: "#6366f1", keywords: ["재즈", "jazz", "색소폰", "saxophone", "스윙", "swing"] },
  { id: "ballad", label: "발라드", color: "#ec4899", keywords: ["발라드", "ballad"] },
  { id: "breakup", label: "이별", color: "#3b82f6", keywords: ["이별", "헤어", "breakup", "그리움", "눈물", "쓸쓸", "회상", "슬픔", "sad", "heartbreak", "lonely", "melancholic", "비 오는", "rainy", "빗방울"] },
  { id: "workout", label: "운동/동기부여", color: "#ef4444", keywords: ["운동", "헬스", "workout", "gym", "러닝", "running", "동기", "motivat", "fitness", "트레이닝", "energetic", "edm", "하우스", "house"] },
  { id: "sleep_study", label: "수면/공부", color: "#34d399", keywords: ["수면", "숙면", "취침", "sleep", "공부", "스터디", "study", "집중", "focus", "독서", "명상", "요가", "앰비언트", "ambient", "차분", "calm"] },
  { id: "lofi", label: "로파이", color: "#14b8a6", keywords: ["로파이", "lofi", "lo-fi", "로-파이", "chill", "재즈힙합", "jazzhop", "jazz hip hop", "빈티지 비트"] },
  { id: "kpop", label: "K-pop", color: "#a855f7", keywords: ["k-pop", "kpop", "케이팝", "케이 팝", "아이돌", "idol", "댄스", "dance"] },
  { id: "pop", label: "팝송", color: "#f43f5e", keywords: ["팝송", "팝뮤직", "팝 뮤직", "american pop", "빌보드", "billboard", "radio hit"] },
  { id: "rnb_soul", label: "R&B/소울", color: "#c084fc", keywords: ["r&b", "rnb", "알앤비", "소울", "soul", "네오소울", "neo soul", "펑크", "funk", "모타운", "motown", "k-r&b", "그루브", "groove"] },
  { id: "hiphop", label: "힙합", color: "#64748b", keywords: ["힙합", "hiphop", "hip hop", "hip-hop", "랩", "rap", "트랩", "trap", "808", "비트박스"] },
]
