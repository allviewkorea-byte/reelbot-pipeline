"use client"

import { Suspense } from "react"
import { useSearchParams } from "next/navigation"
import { CharacterView } from "@/components/studio/CharacterView"
import { StudioHome } from "@/components/studio/StudioHome"

// 캐릭터 스튜디오(채널 공통) — /studio = 채널별 캐릭터 목록, /studio?character=<id> = 그 캐릭터 화면.
// (&job=<id> 는 새 캐릭터를 만든 직후 얼굴 후보 생성 진행을 이어서 보여 준다.)
// 백엔드: /studio/*(character_studio.py · character_studio_gen.py · character_studio_import.py).

function StudioInner() {
  const params = useSearchParams()
  const character = params.get("character")
  return character
    ? <CharacterView key={character} characterId={character} initialJobId={params.get("job")} />
    : <StudioHome />
}

export default function StudioPage() {
  return (
    <Suspense fallback={null}>
      <StudioInner />
    </Suspense>
  )
}
