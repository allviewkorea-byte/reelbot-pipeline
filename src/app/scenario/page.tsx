"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { RefreshCw, Pencil, Check, X, ChevronDown, ChevronUp, ArrowRight } from "lucide-react"

const META = {
  channel: "방콕 여행 채널",
  spots: "왓아룬, 왕궁, 카오산로드, 아시아티크",
  duration: "4분 (24장면)",
  mode: "B 하이브리드",
}

const INITIAL_SCENES = [
  { id: "S01", title: "오프닝 — 새벽 왓아룬 전경 (훅)",          sec: 10, desc: "충격적 새벽빛 전경으로 시청자 시선 즉시 고정" },
  { id: "S02", title: "입구 도착 — 캐릭터 인사",                  sec: 10, desc: "카메라 향해 밝게 인사, 오늘 일정 간단히 소개" },
  { id: "S03", title: "계단 올라가며 역사 설명",                   sec: 10, desc: "왓아룬 79m 탑 계단, 아유타야 시대 역사 나레이션" },
  { id: "S04", title: "전망대 도착 — 뷰 감탄",                    sec: 10, desc: "차오프라야 강과 방콕 스카이라인 파노라마 리액션" },
  { id: "S05", title: "왕궁 이동 — 툭툭 탑승",                    sec: 10, desc: "노란 툭툭에 탑승, 이동 중 거리 풍경 담기" },
  { id: "S06", title: "왕궁 입구 — 복장 체크",                    sec: 10, desc: "어깨·무릎 가리는 복장 규정 안내, 사롱 대여" },
  { id: "S07", title: "에메랄드 사원 — 내부 탐방",                sec: 10, desc: "전설의 에메랄드 불상, 벽화 스토리텔링" },
  { id: "S08", title: "왕궁 정원 — 인생샷 촬영",                  sec: 10, desc: "황금 첨탑 배경 포즈, 관광객 많아 타이밍 팁 공유" },
  { id: "S09", title: "카오산로드 이동 — 점심 타임",              sec: 10, desc: "배고픔 리액션, 카오산로드 방향 걸어서 이동" },
  { id: "S10", title: "팟타이 먹방 — 첫 입",                      sec: 10, desc: "노점 팟타이 60바트, 면 뽑는 현지 장인 클로즈업" },
  { id: "S11", title: "카오산로드 야시장 탐방",                   sec: 10, desc: "형광 칵테일, 파인애플 볶음밥, 기념품 구경" },
  { id: "S12", title: "마사지숍 — 발 마사지 체험",                sec: 10, desc: "200바트 발 마사지, 피로 회복 반응 리얼 담기" },
  { id: "S13", title: "아시아티크 이동 — 선셋 크루즈",            sec: 10, desc: "차오프라야 강 선셋 유람선, 황금빛 노을 타임랩스" },
  { id: "S14", title: "아시아티크 도착 — 대관람차 배경",          sec: 10, desc: "조명 켜진 대관람차 앞 인증샷, 야경 기대감 표현" },
  { id: "S15", title: "야시장 쇼핑 — 수공예품 구경",              sec: 10, desc: "수공예 코끼리 장식품, 가격 흥정 과정 담기" },
  { id: "S16", title: "씨푸드 저녁 — 랍스터 먹방",               sec: 10, desc: "아시아티크 씨푸드 레스토랑, 랍스터 크랙 리액션" },
  { id: "S17", title: "야경 감상 — 강변 산책",                    sec: 10, desc: "방콕 야경 리플렉션, 강변 로맨틱 분위기 촬영" },
  { id: "S18", title: "현지인 인터뷰 — 추천 맛집",               sec: 10, desc: "영어·태국어 섞어 현지인에게 맛집 물어보기" },
  { id: "S19", title: "디저트 타임 — 코코넛 아이스크림",          sec: 10, desc: "코코넛 껍데기 그릇에 담긴 아이스크림, ASMR 촬영" },
  { id: "S20", title: "야간 사원 — 왓포 라이트업",               sec: 10, desc: "황금 와불상 야간 조명, 신비로운 분위기 타임랩스" },
  { id: "S21", title: "루프탑 바 — 방콕 야경 건배",              sec: 10, desc: "35층 루프탑, 방콕 전경 배경 목테일 건배" },
  { id: "S22", title: "숙소 복귀 — 하루 정리",                   sec: 10, desc: "오늘 동선·비용 총정리, 내일 예고 짧게" },
  { id: "S23", title: "하이라이트 몽타주 — 베스트 컷",            sec: 10, desc: "오늘 최고 순간 5컷 빠른 편집, BGM 클라이맥스" },
  { id: "S24", title: "아웃트로 — 구독·좋아요 CTA",              sec: 10, desc: "카메라 향해 구독 부탁, 다음 여행지 티저 공개" },
]

function SceneRow({
  scene,
  onSave,
}: {
  scene: { id: string; title: string; sec: number; desc: string }
  onSave: (id: string, title: string, desc: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draftTitle, setDraftTitle] = useState(scene.title)
  const [draftDesc, setDraftDesc] = useState(scene.desc)

  function handleSave() {
    onSave(scene.id, draftTitle, draftDesc)
    setEditing(false)
  }
  function handleCancel() {
    setDraftTitle(scene.title)
    setDraftDesc(scene.desc)
    setEditing(false)
  }

  return (
    <div className={`border-b border-border/50 px-4 py-3 last:border-b-0 ${editing ? "bg-primary/5" : "hover:bg-secondary/20"} transition-colors`}>
      {editing ? (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <span
              className="w-10 shrink-0 text-xs font-bold text-primary"
              style={{ fontFamily: "var(--font-geist-mono)" }}
            >
              {scene.id}
            </span>
            <input
              autoFocus
              value={draftTitle}
              onChange={(e) => setDraftTitle(e.target.value)}
              className="flex-1 rounded border border-primary/40 bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary/40"
            />
            <span className="shrink-0 text-[10px] text-muted-foreground">
              {scene.sec}초
            </span>
            <button onClick={handleSave} className="rounded p-1 text-emerald-400 hover:bg-emerald-500/10">
              <Check className="h-3.5 w-3.5" />
            </button>
            <button onClick={handleCancel} className="rounded p-1 text-muted-foreground hover:bg-secondary/60">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="pl-12">
            <input
              value={draftDesc}
              onChange={(e) => setDraftDesc(e.target.value)}
              className="w-full rounded border border-border bg-background px-2 py-1 text-[11px] text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/30"
            />
          </div>
        </div>
      ) : (
        <div className="flex items-start gap-2">
          <span
            className="mt-0.5 w-10 shrink-0 text-xs font-bold text-muted-foreground"
            style={{ fontFamily: "var(--font-geist-mono)" }}
          >
            {scene.id}
          </span>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-foreground">{scene.title}</p>
            <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{scene.desc}</p>
          </div>
          <span className="mt-0.5 shrink-0 text-[10px] text-muted-foreground/60">
            {scene.sec}초
          </span>
          <button
            onClick={() => setEditing(true)}
            className="mt-0.5 shrink-0 rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:text-foreground group-hover:opacity-100"
          >
            <Pencil className="h-3 w-3" />
          </button>
        </div>
      )}
    </div>
  )
}

export default function ScenarioPage() {
  const router = useRouter()
  const [scenes, setScenes] = useState(INITIAL_SCENES)
  const [expanded, setExpanded] = useState(false)

  const visibleScenes = expanded ? scenes : scenes.slice(0, 4)

  function handleSave(id: string, title: string, desc: string) {
    setScenes((prev) =>
      prev.map((s) => (s.id === id ? { ...s, title, desc } : s))
    )
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold text-foreground">시나리오 생성</h1>
          <p className="mt-0.5 text-xs text-muted-foreground">
            AI가 분석한 인사이트 기반으로 대본을 자동 생성합니다
          </p>
        </div>
        <button className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-secondary/40">
          <RefreshCw className="h-3.5 w-3.5 text-muted-foreground" />
          시나리오 재생성
        </button>
      </div>

      {/* Body — scrollable */}
      <div className="flex-1 overflow-y-auto">
        <div className="flex flex-col gap-4 p-6">
          {/* Meta card */}
          <div className="grid grid-cols-4 gap-3">
            {Object.entries({
              채널: META.channel,
              여행지: META.spots,
              "영상 길이": META.duration,
              모드: META.mode,
            }).map(([label, value]) => (
              <div key={label} className="rounded-xl border border-border bg-card p-3">
                <p className="text-[10px] text-muted-foreground">{label}</p>
                <p className="mt-1 text-xs font-semibold text-foreground leading-snug">{value}</p>
              </div>
            ))}
          </div>

          {/* Scene list card */}
          <div className="rounded-xl border border-border bg-card overflow-hidden">
            {/* List header */}
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <h2 className="text-sm font-semibold text-foreground">씬 목록</h2>
              <span
                className="text-xs font-bold text-muted-foreground"
                style={{ fontFamily: "var(--font-geist-mono)" }}
              >
                {scenes.length}개 장면
              </span>
            </div>

            {/* Scenes — hover group for edit icon */}
            <div className="divide-y-0">
              {visibleScenes.map((scene) => (
                <div key={scene.id} className="group">
                  <SceneRow scene={scene} onSave={handleSave} />
                </div>
              ))}
            </div>

            {/* Show more / less toggle */}
            <button
              onClick={() => setExpanded((p) => !p)}
              className="flex w-full items-center justify-center gap-1.5 border-t border-border py-3 text-xs font-medium text-muted-foreground transition-colors hover:bg-secondary/30 hover:text-foreground"
            >
              {expanded ? (
                <>
                  <ChevronUp className="h-3.5 w-3.5" /> 접기
                </>
              ) : (
                <>
                  <ChevronDown className="h-3.5 w-3.5" />
                  나머지 {scenes.length - 4}개 장면 더보기
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Action bar */}
      <div className="shrink-0 flex items-center justify-between border-t border-border bg-card/50 px-6 py-4">
        <div className="flex items-center gap-2">
          <span
            className="text-sm font-bold text-foreground"
            style={{ fontFamily: "var(--font-geist-mono)" }}
          >
            총 {scenes.length}장면
          </span>
          <span className="text-muted-foreground">/</span>
          <span className="text-sm text-muted-foreground">4분</span>
        </div>
        <button
          onClick={() => router.push("/video")}
          className="flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-lg shadow-primary/20 transition-opacity hover:opacity-90"
        >
          이 시나리오로 영상 만들기
          <ArrowRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
