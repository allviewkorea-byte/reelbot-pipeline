// mood/genre 힌트 문자열 → 이퀄 바 그라데이션 색상 쌍.
// music_video.py 가 mood+genre+situation 을 합쳐 한 문자열로 넘긴다(한/영 혼용 매칭).
export type ColorPair = [string, string];

const RULES: { keys: string[]; colors: ColorPair }[] = [
  // 시티팝 / 드라이브 → 보라 + 시안
  {
    keys: ["시티팝", "citypop", "city pop", "드라이브", "drive", "driving", "운전", "출근", "퇴근", "commute"],
    colors: ["#8b5cf6", "#22d3ee"],
  },
  // 카페 / 재즈 → 앰버 + 골드
  {
    keys: ["카페", "cafe", "재즈", "jazz", "커피", "coffee", "브런치", "라운지", "lounge"],
    colors: ["#f59e0b", "#fcd34d"],
  },
  // 이별 / 발라드 → 블루 + 퍼플
  {
    keys: ["이별", "헤어", "breakup", "발라드", "ballad", "슬픔", "sad", "그리움", "눈물"],
    colors: ["#3b82f6", "#a855f7"],
  },
  // 운동 / 동기부여 → 레드 + 오렌지
  {
    keys: ["운동", "헬스", "workout", "gym", "러닝", "running", "동기", "motivat", "fitness", "트레이닝"],
    colors: ["#ef4444", "#f97316"],
  },
  // 수면 / 공부 → 민트 + 소프트그린
  {
    keys: ["수면", "잠", "취침", "sleep", "공부", "스터디", "study", "집중", "focus", "독서"],
    colors: ["#34d399", "#a7f3d0"],
  },
];

const DEFAULT_COLORS: ColorPair = ["#8b5cf6", "#22d3ee"]; // 기본 보라 + 시안

export function moodColors(mood?: string): ColorPair {
  const m = (mood || "").toLowerCase();
  for (const rule of RULES) {
    if (rule.keys.some((k) => m.includes(k.toLowerCase()))) {
      return rule.colors;
    }
  }
  return DEFAULT_COLORS;
}
