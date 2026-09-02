import { redirect } from "next/navigation"

// 릴봇 시작 화면 = 운동 채널(2주안에몸매만들기). 사이드바 운동 카드와 같은 목적지
// (withChannel("/music", "workout_music") 결과와 동일 문자열).
// 백곰은 사이드바 백곰 카드(/dashboard)로 그대로 들어간다.
// 하드코딩 유지 — 시작 화면은 거의 바뀌지 않는 값이라 env·화이트리스트 맵을 도입할
// 값어치가 없고, 그래야 오픈 리다이렉트 위험이 없고 / 도 정적으로 남는다.
export default function RootPage() {
  redirect("/music?channel=workout_music")
}
