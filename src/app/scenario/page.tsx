"use client"

import { Suspense, useState, useEffect, useCallback, useMemo } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { RefreshCw, Pencil, Check, X, ChevronDown, ChevronUp, ArrowRight, Loader2, Sparkles, Hash, TrendingUp, Save } from "lucide-react"
import { useChannels } from "@/components/channels/ChannelProvider"
import {
  fetchInsights,
  parseTrendId,
  buildTitleCandidates,
  buildDescription,
  combineHashtags,
  recommendDurationMin,
  FORMAT_LABEL,
} from "@/lib/trends"
import type { TrendInsight, VideoFormat } from "@/types/trend"
import { saveScenarioHandoff } from "@/lib/scenario-handoff"

// 시나리오 페이지의 형식("long"|"short")과 트렌드 형식("long"|"shorts") 매핑.
function toTrendFormat(f: "long" | "short"): VideoFormat {
  return f === "short" ? "shorts" : "long"
}

const TITLE_LOG_KEY = "reelbot.titleSelections.v1"

// 기존 여행 기본값 (100% 보존)
const META = {
  channel: "방콕 여행 채널",
  spots: "왓아룬, 왕궁, 카오산로드, 아시아티크",
  duration: "4분 (24장면)",
  mode: "B 하이브리드",
}

const INITIAL_SCENES_RAW = [
  { id: "S01", title: "오프닝 — 새벽 왓아룬 전경 (훅)",         sec: 10, desc: "충격적 새벽빛 전경으로 시청자 시선 즉시 고정" },
  { id: "S02", title: "입구 도착 — 캐릭터 인사",                 sec: 10, desc: "카메라 향해 밝게 인사, 오늘 일정 간단히 소개" },
  { id: "S03", title: "계단 올라가며 역사 설명",                  sec: 10, desc: "왓아룬 79m 탑 계단, 아유타야 시대 역사 나레이션" },
  { id: "S04", title: "전망대 도착 — 뷰 감탄",                   sec: 10, desc: "차오프라야 강과 방콕 스카이라인 파노라마 리액션" },
  { id: "S05", title: "왕궁 이동 — 툭툭 탑승",                   sec: 10, desc: "노란 툭툭에 탑승, 이동 중 거리 풍경 담기" },
  { id: "S06", title: "왕궁 입구 — 복장 체크",                   sec: 10, desc: "어깨·무릎 가리는 복장 규정 안내, 사롱 대여" },
  { id: "S07", title: "에메랄드 사원 — 내부 탐방",               sec: 10, desc: "전설의 에메랄드 불상, 벽화 스토리텔링" },
  { id: "S08", title: "왕궁 정원 — 인생샷 촬영",                 sec: 10, desc: "황금 첨탑 배경 포즈, 관광객 많아 타이밍 팁 공유" },
  { id: "S09", title: "카오산로드 이동 — 점심 타임",             sec: 10, desc: "배고픔 리액션, 카오산로드 방향 걸어서 이동" },
  { id: "S10", title: "팟타이 먹방 — 첫 입",                     sec: 10, desc: "노점 팟타이 60바트, 면 뽑는 현지 장인 클로즈업" },
  { id: "S11", title: "카오산로드 야시장 탐방",                  sec: 10, desc: "형광 칵테일, 파인애플 볶음밥, 기념품 구경" },
  { id: "S12", title: "마사지숍 — 발 마사지 체험",               sec: 10, desc: "200바트 발 마사지, 피로 회복 반응 리얼 담기" },
  { id: "S13", title: "아시아티크 이동 — 선셋 크루즈",           sec: 10, desc: "차오프라야 강 선셋 유람선, 황금빛 노을 타임랩스" },
  { id: "S14", title: "아시아티크 도착 — 대관람차 배경",         sec: 10, desc: "조명 켜진 대관람차 앞 인증샷, 야경 기대감 표현" },
  { id: "S15", title: "야시장 쇼핑 — 수공예품 구경",             sec: 10, desc: "수공예 코끼리 장식품, 가격 흥정 과정 담기" },
  { id: "S16", title: "씨푸드 저녁 — 랍스터 먹방",              sec: 10, desc: "아시아티크 씨푸드 레스토랑, 랍스터 크랙 리액션" },
  { id: "S17", title: "야경 감상 — 강변 산책",                   sec: 10, desc: "방콕 야경 리플렉션, 강변 로맨틱 분위기 촬영" },
  { id: "S18", title: "현지인 인터뷰 — 추천 맛집",              sec: 10, desc: "영어·태국어 섞어 현지인에게 맛집 물어보기" },
  { id: "S19", title: "디저트 타임 — 코코넛 아이스크림",         sec: 10, desc: "코코넛 껍데기 그릇에 담긴 아이스크림, ASMR 촬영" },
  { id: "S20", title: "야간 사원 — 왓포 라이트업",              sec: 10, desc: "황금 와불상 야간 조명, 신비로운 분위기 타임랩스" },
  { id: "S21", title: "루프탑 바 — 방콕 야경 건배",             sec: 10, desc: "35층 루프탑, 방콕 전경 배경 목테일 건배" },
  { id: "S22", title: "숙소 복귀 — 하루 정리",                  sec: 10, desc: "오늘 동선·비용 총정리, 내일 예고 짧게" },
  { id: "S23", title: "하이라이트 몽타주 — 베스트 컷",           sec: 10, desc: "오늘 최고 순간 5컷 빠른 편집, BGM 클라이맥스" },
  { id: "S24", title: "아웃트로 — 구독·좋아요 CTA",             sec: 10, desc: "카메라 향해 구독 부탁, 다음 여행지 티저 공개" },
]

// 기본 씬에는 script/durationSec 가 없으므로 빈 값으로 보정한다.
const INITIAL_SCENES: Scene[] = INITIAL_SCENES_RAW.map((s) => ({
  ...s,
  script: "",
  durationSec: s.sec,
}))

// ── 파라미터 옵션 ───────────────────────────────────────────────────
const CATEGORIES = [
  "여행", "음식·맛집", "라이프스타일", "패션·뷰티", "교육·정보",
  "유머·엔터테인먼트", "동기부여", "일상", "비즈니스",
]
const TONES = ["밝고 경쾌", "감성적·잔잔", "유머러스", "진지·정보전달", "영감·동기부여"]
const DURATIONS = [
  { label: "1분", min: 1 },
  { label: "2분", min: 2 },
  { label: "4분", min: 4 },
  { label: "10분", min: 10 },
]
const SCENE_PRESETS = [6, 12, 24]
const MODEL_COUNTS = ["1인", "2인", "3인+"]

// 분량 → 권장 장면 수 (10초 기준)
function recommendSceneCount(min: number): number {
  return Math.max(6, min * 6)
}

// 씬 목록 생성에 영향을 주는 입력들의 시그니처.
// 이 값이 마지막 생성 시점과 달라지면 현재 씬 목록은 옛 설정 기준이라
// 무효(stale)로 간주하고, 흐리게 + 재생성 안내를 노출한다.
interface ScenarioParams {
  category: string
  topic: string
  tone: string
  format: "long" | "short"
  durationMin: number
  sceneCount: number
  modelCount: string
  models: string[]
}
function paramSignature(p: ScenarioParams): string {
  return JSON.stringify({
    category: p.category,
    topic: p.topic,
    tone: p.tone,
    format: p.format,
    durationMin: p.durationMin,
    sceneCount: p.sceneCount,
    modelCount: p.modelCount,
    models: [...p.models].sort(),
  })
}

const SCENARIO_STORE_KEY = "reelbot.scenarios.v1"
// 현재 작업 중인 시나리오 초안(씬 스크립트 + 본문 편집)을 reload 후에도 유지.
const SCENARIO_DRAFT_KEY = "reelbot.scenarioDraft.v1"

interface ScenarioDraft {
  scenes?: Scene[]
  metaTitle?: string | null
  metaDescription?: string | null
  metaTags?: string[] | null
}

// ── Chip ────────────────────────────────────────────────────────────
function Chip({
  active,
  onClick,
  children,
  disabled,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-all disabled:opacity-50 ${
        active
          ? "border-primary/60 bg-primary/15 text-foreground"
          : "border-border bg-background text-muted-foreground hover:border-primary/30 hover:text-foreground"
      }`}
    >
      {children}
    </button>
  )
}

type Scene = { id: string; title: string; sec: number; desc: string; script: string; durationSec: number }

// 한국어 발화 기준 1초당 약 4~5자 → 권장 글자수 범위.
function recommendedCharRange(durationSec: number): [number, number] {
  return [Math.round(durationSec * 4), Math.round(durationSec * 5)]
}

function SceneRow({
  scene,
  expanded,
  regenerating,
  onToggleScript,
  onSaveMeta,
  onSaveScript,
  onRegenerate,
}: {
  scene: Scene
  expanded: boolean
  regenerating: boolean
  onToggleScript: (id: string) => void
  onSaveMeta: (id: string, title: string, desc: string) => void
  onSaveScript: (id: string, script: string) => void
  onRegenerate: (scene: Scene) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draftTitle, setDraftTitle] = useState(scene.title)
  const [draftDesc, setDraftDesc] = useState(scene.desc)
  // scene.script 가 외부(재생성)로 바뀌면 부모가 key 를 갱신해 이 컴포넌트를
  // 리마운트하므로, 로컬 초안은 마운트 시점의 script 로 안전하게 초기화된다.
  const [draftScript, setDraftScript] = useState(scene.script)

  const [minChars, maxChars] = recommendedCharRange(scene.durationSec)
  const len = draftScript.length
  const outOfRange = len > 0 && (len < minChars || len > maxChars)
  const dirty = draftScript !== scene.script

  function handleSaveMeta() {
    onSaveMeta(scene.id, draftTitle, draftDesc)
    setEditing(false)
  }
  function handleCancelMeta() {
    setDraftTitle(scene.title)
    setDraftDesc(scene.desc)
    setEditing(false)
  }

  return (
    <div className={`border-b border-border/50 px-4 py-3 last:border-b-0 ${editing ? "bg-primary/5" : "hover:bg-secondary/20"} transition-colors`}>
      {editing ? (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <span className="w-10 shrink-0 text-xs font-bold text-primary" style={{ fontFamily: "var(--font-geist-mono)" }}>
              {scene.id}
            </span>
            <input
              autoFocus
              value={draftTitle}
              onChange={(e) => setDraftTitle(e.target.value)}
              className="flex-1 rounded border border-primary/40 bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary/40"
            />
            <span className="shrink-0 text-[10px] text-muted-foreground">{scene.durationSec}초</span>
            <button onClick={handleSaveMeta} className="rounded p-1 text-emerald-400 hover:bg-emerald-500/10">
              <Check className="h-3.5 w-3.5" />
            </button>
            <button onClick={handleCancelMeta} className="rounded p-1 text-muted-foreground hover:bg-secondary/60">
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
          <span className="mt-0.5 w-10 shrink-0 text-xs font-bold text-muted-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
            {scene.id}
          </span>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-foreground">{scene.title}</p>
            <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{scene.desc}</p>
          </div>
          <span className="mt-0.5 shrink-0 rounded-full bg-secondary/60 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
            {scene.durationSec}초
          </span>
          <button
            onClick={() => setEditing(true)}
            className="mt-0.5 shrink-0 rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:text-foreground group-hover:opacity-100"
          >
            <Pencil className="h-3 w-3" />
          </button>
        </div>
      )}

      {/* 스크립트 펼치기 토글 */}
      {!editing && (
        <div className="mt-2 pl-12">
          <button
            onClick={() => onToggleScript(scene.id)}
            className="flex items-center gap-1 text-[11px] font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            스크립트 {expanded ? "접기" : "펼치기"}
            {!expanded && scene.script && <span className="text-muted-foreground/50">· {scene.script.length}자</span>}
          </button>

          {expanded && (
            <div className="mt-2 flex flex-col gap-2">
              <textarea
                value={draftScript}
                onChange={(e) => setDraftScript(e.target.value)}
                rows={3}
                placeholder="이 씬에서 읽을 내레이션 텍스트…"
                className="w-full resize-y rounded-lg border border-border bg-card px-3 py-2 text-xs leading-relaxed text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-primary"
              />
              <div className="flex items-center justify-between gap-2">
                <span className={`text-[11px] ${outOfRange ? "text-amber-500" : "text-muted-foreground"}`}>
                  {len}자 / 권장 {minChars}~{maxChars}자
                </span>
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => onRegenerate(scene)}
                    disabled={regenerating}
                    className="flex items-center gap-1 rounded-md bg-primary px-2.5 py-1 text-[11px] font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
                  >
                    {regenerating
                      ? <Loader2 className="h-3 w-3 animate-spin" />
                      : <RefreshCw className="h-3 w-3" />}
                    재생성
                  </button>
                  <button
                    onClick={() => onSaveScript(scene.id, draftScript)}
                    disabled={!dirty}
                    className="flex items-center gap-1 rounded-md bg-emerald-600 px-2.5 py-1 text-[11px] font-semibold text-white transition-colors hover:bg-emerald-700 disabled:opacity-40"
                  >
                    <Save className="h-3 w-3" />
                    저장
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ScenarioPageInner() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { channels } = useChannels()
  const firstChannel = channels[0]

  // 시나리오 파라미터
  const [category, setCategory] = useState("여행")
  const [tone, setTone] = useState("밝고 경쾌")
  const [format, setFormat] = useState<"long" | "short">(
    firstChannel?.stack.contentType === "short" ? "short" : "long"
  )
  const [durationMin, setDurationMin] = useState(4)
  const [customDuration, setCustomDuration] = useState(false)
  const [sceneCount, setSceneCount] = useState(24)
  const [customScene, setCustomScene] = useState(false)
  const [modelCount, setModelCount] = useState("1인")
  const [topic, setTopic] = useState(META.spots)
  const [selectedModels, setSelectedModels] = useState<string[]>(
    firstChannel?.stack.characters ?? []
  )
  const [libraryNames, setLibraryNames] = useState<string[]>([])

  const [scenes, setScenes] = useState<Scene[]>(INITIAL_SCENES)
  const [expanded, setExpanded] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [expandedScripts, setExpandedScripts] = useState<Record<string, boolean>>({})
  const [regeneratingId, setRegeneratingId] = useState<string | null>(null)

  // 현재 입력 시그니처와, 마지막으로 씬 목록을 생성한 시점의 시그니처.
  // 둘이 다르면 씬 목록이 옛 설정 기준이므로 무효(stale).
  const paramSig = useMemo(
    () =>
      paramSignature({ category, topic, tone, format, durationMin, sceneCount, modelCount, models: selectedModels }),
    [category, topic, tone, format, durationMin, sceneCount, modelCount, selectedModels],
  )
  // 초기 씬 목록(INITIAL_SCENES)은 초기 입력값으로 생성된 것으로 본다.
  const [generatedSig, setGeneratedSig] = useState(() =>
    paramSignature({
      category: "여행",
      topic: META.spots,
      tone: "밝고 경쾌",
      format: firstChannel?.stack.contentType === "short" ? "short" : "long",
      durationMin: 4,
      sceneCount: 24,
      modelCount: "1인",
      models: firstChannel?.stack.characters ?? [],
    }),
  )
  const scenesStale = generatedSig !== paramSig

  // 시나리오 본문(제목/설명/해시태그) 인라인 편집 오버라이드.
  const [metaTitle, setMetaTitle] = useState<string | null>(null)
  const [metaDescription, setMetaDescription] = useState<string | null>(null)
  const [metaTags, setMetaTags] = useState<string[] | null>(null)
  const [editingMeta, setEditingMeta] = useState(false)
  const [metaTitleDraft, setMetaTitleDraft] = useState("")
  const [metaDescDraft, setMetaDescDraft] = useState("")
  const [metaTagsDraft, setMetaTagsDraft] = useState("")

  // 트렌드 연동 상태
  const [activeInsight, setActiveInsight] = useState<TrendInsight | null>(null)
  const [selectedTitle, setSelectedTitle] = useState<string | null>(null)
  const [trendLoading, setTrendLoading] = useState(false)

  const visibleScenes = expanded ? scenes : scenes.slice(0, 4)
  const durationLabel = `${durationMin}분`

  // 트렌드 데이터 기반 자동 생성 결과
  const titleCandidates = useMemo(
    () => (activeInsight ? buildTitleCandidates(activeInsight, topic) : []),
    [activeInsight, topic],
  )
  const generatedDescription = useMemo(
    () => (activeInsight ? buildDescription(activeInsight, topic) : ""),
    [activeInsight, topic],
  )
  const hashtags = useMemo(
    () => (activeInsight ? combineHashtags(activeInsight) : []),
    [activeInsight],
  )

  // 캐릭터 라이브러리에서 모델 목록 로드
  useEffect(() => {
    fetch("/api/character/library")
      .then((r) => r.json())
      .then((d) => {
        const names = (d.characters ?? [])
          .map((c: { name?: string }) => c.name)
          .filter(Boolean) as string[]
        setLibraryNames(names)
      })
      .catch(() => { /* 무시 */ })
  }, [])

  // 이전에 편집/저장한 시나리오 초안을 reload 후 복원. setState 는 마이크로태스크로
  // 미뤄 이펙트 본문에서 동기 setState 가 발생하지 않도록 한다.
  useEffect(() => {
    Promise.resolve().then(() => {
      let raw: string | null
      try {
        raw = sessionStorage.getItem(SCENARIO_DRAFT_KEY)
      } catch {
        return
      }
      if (!raw) return
      try {
        const draft = JSON.parse(raw) as ScenarioDraft
        if (Array.isArray(draft.scenes) && draft.scenes.length) setScenes(draft.scenes)
        if (typeof draft.metaTitle === "string") setMetaTitle(draft.metaTitle)
        if (typeof draft.metaDescription === "string") setMetaDescription(draft.metaDescription)
        if (Array.isArray(draft.metaTags)) setMetaTags(draft.metaTags)
      } catch {
        /* 손상된 초안 무시 */
      }
    })
  }, [])

  // 경쟁사 분석 등에서 넘어온 파라미터 자동 채우기
  useEffect(() => {
    let raw: string | null = null
    try {
      raw = sessionStorage.getItem("reelbot:scenarioParams")
    } catch {
      return
    }
    if (!raw) return
    try {
      const p = JSON.parse(raw)
      if (p.category && CATEGORIES.includes(p.category)) setCategory(p.category)
      if (p.tone && TONES.includes(p.tone)) setTone(p.tone)
      if (p.format === "long" || p.format === "short") setFormat(p.format)
      if (typeof p.durationMin === "number" && p.durationMin > 0) {
        setDurationMin(p.durationMin)
        setCustomDuration(!DURATIONS.some((d) => d.min === p.durationMin))
      }
      if (typeof p.sceneCount === "number" && p.sceneCount > 0) {
        setSceneCount(p.sceneCount)
        setCustomScene(!SCENE_PRESETS.includes(p.sceneCount))
      }
      if (typeof p.modelCount === "string") setModelCount(p.modelCount)
      if (typeof p.topic === "string") setTopic(p.topic)
      if (Array.isArray(p.models)) setSelectedModels(p.models)
    } catch {
      /* 손상된 값 무시 */
    } finally {
      sessionStorage.removeItem("reelbot:scenarioParams")
    }
  }, [])

  // 트렌드 연동 채널 (trendId 파라미터 또는 첫 채널)
  const [trendChannelId, setTrendChannelId] = useState("")

  // ?trendId= 파라미터 처리 — 카테고리·형식 자동 선택
  useEffect(() => {
    const tid = searchParams.get("trendId")
    if (!tid) return
    const parsed = parseTrendId(tid)
    if (!parsed) return
    setTrendChannelId(parsed.channelId)
    if (CATEGORIES.includes(parsed.category)) setCategory(parsed.category)
    setFormat(parsed.format === "shorts" ? "short" : "long")
  }, [searchParams])

  // 카테고리 + 형식 선택 시 해당 트렌드 데이터 자동 로드 + 길이/씬 수 자동 적용
  useEffect(() => {
    const cid = trendChannelId || firstChannel?.id
    if (!cid) return
    let cancelled = false
    setTrendLoading(true)
    fetchInsights(cid, category, toTrendFormat(format))
      .then((list) => {
        if (cancelled) return
        const found = list[0] ?? null
        setActiveInsight(found)
        setSelectedTitle(null)
        if (found) {
          const recMin = recommendDurationMin(found)
          setDurationMin(recMin)
          setCustomDuration(!DURATIONS.some((d) => d.min === recMin))
          const rec = recommendSceneCount(recMin)
          setSceneCount(rec)
          setCustomScene(!SCENE_PRESETS.includes(rec))
        }
      })
      .catch(() => {
        if (!cancelled) setActiveInsight(null)
      })
      .finally(() => {
        if (!cancelled) setTrendLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [category, format, trendChannelId, firstChannel?.id])

  // 선택값이 없거나 후보 목록에 없으면 첫 후보를 기본 선택으로 사용 (effect 불필요).
  const effectiveTitle =
    selectedTitle && titleCandidates.includes(selectedTitle)
      ? selectedTitle
      : titleCandidates[0] ?? null

  // 본문 편집 표시값: 편집 오버라이드 > 트렌드 자동 생성값.
  const displayTitle = metaTitle ?? effectiveTitle ?? ""
  const displayDescription = metaDescription ?? generatedDescription
  const displayTags = metaTags ?? hashtags

  function startEditMeta() {
    setMetaTitleDraft(displayTitle)
    setMetaDescDraft(displayDescription)
    setMetaTagsDraft(displayTags.map((t) => t.replace(/^#/, "")).join(", "))
    setEditingMeta(true)
  }

  function saveMeta() {
    const nextTitle = metaTitleDraft.trim() || null
    const nextDesc = metaDescDraft.trim() || null
    const nextTags = metaTagsDraft
      .split(/[,\n]/)
      .map((t) => t.trim().replace(/^#/, ""))
      .filter(Boolean)
    setMetaTitle(nextTitle)
    setMetaDescription(nextDesc)
    setMetaTags(nextTags.length ? nextTags : null)
    setEditingMeta(false)
    persistDraft({
      metaTitle: nextTitle,
      metaDescription: nextDesc,
      metaTags: nextTags.length ? nextTags : null,
    })
  }

  function cancelEditMeta() {
    setEditingMeta(false)
  }

  function handleSelectTitle(title: string) {
    setSelectedTitle(title)
    // 향후 학습용 선택 로그 저장
    try {
      const raw = localStorage.getItem(TITLE_LOG_KEY)
      const list = raw ? (JSON.parse(raw) as unknown[]) : []
      list.push({
        at: new Date().toISOString(),
        channelId: trendChannelId || firstChannel?.id || "",
        category,
        format: toTrendFormat(format),
        title,
      })
      localStorage.setItem(TITLE_LOG_KEY, JSON.stringify(list))
    } catch {
      /* 저장 실패는 무시 */
    }
  }

  function handleDurationSelect(min: number) {
    setCustomDuration(false)
    setDurationMin(min)
    // 분량 선택 시 장면 수 자동 추천
    if (!customScene) {
      const rec = recommendSceneCount(min)
      setSceneCount(rec)
      setCustomScene(!SCENE_PRESETS.includes(rec))
    }
  }

  function toggleModel(name: string) {
    setSelectedModels((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]
    )
  }

  const persistScenario = useCallback(
    (generated: Scene[]) => {
      try {
        const raw = localStorage.getItem(SCENARIO_STORE_KEY)
        const list = raw ? (JSON.parse(raw) as unknown[]) : []
        list.push({
          createdAt: new Date().toISOString(),
          params: { category, tone, format, durationMin, sceneCount, modelCount, topic, models: selectedModels },
          scenes: generated,
        })
        localStorage.setItem(SCENARIO_STORE_KEY, JSON.stringify(list))
      } catch {
        /* 저장 실패는 무시 */
      }
    },
    [category, tone, format, durationMin, sceneCount, modelCount, topic, selectedModels]
  )

  // 작업 중인 초안(씬 + 본문 편집)을 sessionStorage 에 저장.
  const persistDraft = useCallback(
    (patch: Partial<ScenarioDraft>) => {
      try {
        const next: ScenarioDraft = {
          scenes,
          metaTitle,
          metaDescription,
          metaTags,
          ...patch,
        }
        sessionStorage.setItem(SCENARIO_DRAFT_KEY, JSON.stringify(next))
      } catch {
        /* 저장 실패는 무시 */
      }
    },
    [scenes, metaTitle, metaDescription, metaTags],
  )

  async function handleRegenerate() {
    setGenerating(true)
    try {
      const isTravel = category === "여행"
      const res = await fetch("/api/scenario/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category,
          topic,
          tone,
          format,
          durationMin,
          sceneCount,
          modelCount,
          models: selectedModels,
          // 여행 카테고리는 기존 동작 보존을 위해 레거시 필드도 전달
          ...(isTravel
            ? {
                channel: firstChannel?.name ?? META.channel,
                spots: topic || META.spots,
                duration: `${durationLabel} (${sceneCount}장면)`,
                mode: META.mode,
              }
            : {}),
        }),
      })
      const data = await res.json()
      if (!res.ok || !data.success) throw new Error(data.error || "생성 실패")
      const generated = data.scenes as Scene[]
      setScenes(generated)
      setGeneratedSig(paramSig)
      setExpanded(false)
      setExpandedScripts({})
      persistScenario(generated)
      persistDraft({ scenes: generated })
    } catch (err) {
      console.error(err)
      alert("시나리오 생성에 실패했습니다. 다시 시도해주세요.")
    } finally {
      setGenerating(false)
    }
  }

  function toggleScript(id: string) {
    setExpandedScripts((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  function handleSaveMeta(id: string, title: string, desc: string) {
    setScenes((prev) => {
      const next = prev.map((s) => (s.id === id ? { ...s, title, desc } : s))
      persistDraft({ scenes: next })
      return next
    })
  }

  function handleSaveScript(id: string, script: string) {
    setScenes((prev) => {
      const next = prev.map((s) => (s.id === id ? { ...s, script } : s))
      persistDraft({ scenes: next })
      return next
    })
  }

  // 씬 단위 스크립트 재생성. 트렌드/캐릭터/채널 컨텍스트가 있으면 함께 전달한다.
  async function handleRegenerateScene(scene: Scene) {
    setRegeneratingId(scene.id)
    try {
      const index = scenes.findIndex((s) => s.id === scene.id)
      const res = await fetch("/api/scenario/script/regenerate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scene: { title: scene.title, description: scene.desc },
          sceneIndex: index < 0 ? 0 : index,
          totalScenes: scenes.length,
          format: format === "short" ? "shorts" : "longform",
          targetLengthSec: scene.durationSec,
          trendContext: activeInsight
            ? {
                powerWords: activeInsight.powerWords.map((p) => p.word),
                titleCandidates,
                category: activeInsight.category,
              }
            : undefined,
          characterContext: selectedModels[0]
            ? { name: selectedModels[0], tone }
            : undefined,
          channelContext: firstChannel
            ? { stack: firstChannel.stack.contentType, track: firstChannel.stack.track }
            : undefined,
        }),
      })
      const data = await res.json()
      if (!res.ok || !data.script) throw new Error(data.error || "재생성 실패")
      setScenes((prev) => {
        const next = prev.map((s) =>
          s.id === scene.id
            ? { ...s, script: data.script, durationSec: data.durationSec ?? s.durationSec }
            : s,
        )
        persistDraft({ scenes: next })
        return next
      })
    } catch (err) {
      console.error(err)
      alert("스크립트 재생성에 실패했습니다. 다시 시도해주세요.")
    } finally {
      setRegeneratingId(null)
    }
  }

  // 시나리오에서 정한 소재/길이/형식/캐릭터/씬과 트렌드 분석 결과(제목 후보·
  // 설명·해시태그)를 영상 제작 동선으로 넘긴다.
  function handleMakeVideo() {
    // 본문 편집 오버라이드를 우선 반영한다.
    const effectiveCandidates = metaTitle
      ? [metaTitle, ...titleCandidates.filter((t) => t !== metaTitle)]
      : titleCandidates
    const effectiveDescription = metaDescription ?? generatedDescription
    const effectiveHashtags = metaTags
      ? { primary: metaTags }
      : activeInsight
        ? {
            primary: activeInsight.tagsByCategory.primary,
            variation: activeInsight.tagsByCategory.variants,
            competitor: activeInsight.tagsByCategory.competitor,
            broad: activeInsight.tagsByCategory.broad,
            detail: activeInsight.tagsByCategory.niche,
          }
        : undefined

    saveScenarioHandoff({
      topic,
      duration: durationMin * 60,
      format: format === "short" ? "shorts" : "long",
      channelId: firstChannel?.id,
      characterIds: selectedModels,
      titleCandidates: effectiveCandidates.length ? effectiveCandidates : undefined,
      description: effectiveDescription || undefined,
      hashtags: effectiveHashtags,
      trendId: searchParams.get("trendId") ?? undefined,
      scenes: scenes.map((s) => ({
        title: s.title,
        description: s.desc,
        script: s.script,
        durationSec: s.durationSec,
      })),
    })
    router.push("/video")
  }

  const modelOptions = Array.from(new Set([...selectedModels, ...libraryNames]))

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <div className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold text-foreground">시나리오 생성</h1>
          <p className="mt-0.5 text-xs text-muted-foreground">카테고리·톤·분량을 선택하면 AI가 대본을 자동 생성합니다</p>
        </div>
        <button
          onClick={handleRegenerate}
          disabled={generating}
          className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground shadow-md shadow-primary/20 transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {generating
            ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
            : <RefreshCw className="h-3.5 w-3.5" />}
          {generating ? "생성 중..." : "시나리오 생성"}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="flex flex-col gap-4 p-6">
          {/* 파라미터 패널 */}
          <div className="flex flex-col gap-5 rounded-xl border border-border bg-card p-5">
            {/* 카테고리 */}
            <div>
              <label className="mb-2 block text-xs font-medium text-muted-foreground">주제 카테고리</label>
              <div className="flex flex-wrap gap-2">
                {CATEGORIES.map((c) => (
                  <Chip key={c} active={category === c} onClick={() => setCategory(c)} disabled={generating}>
                    {c}
                  </Chip>
                ))}
              </div>
            </div>

            {/* 소재 */}
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted-foreground">소재 (주제 키워드)</label>
              <input
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                disabled={generating}
                placeholder="예: 방콕 여행 / 강남 맛집 투어 / 직장인 모닝 루틴"
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/40 focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/30 disabled:opacity-50"
              />
            </div>

            {/* 톤 */}
            <div>
              <label className="mb-2 block text-xs font-medium text-muted-foreground">감정·톤</label>
              <div className="flex flex-wrap gap-2">
                {TONES.map((t) => (
                  <Chip key={t} active={tone === t} onClick={() => setTone(t)} disabled={generating}>
                    {t}
                  </Chip>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              {/* 영상 형식 */}
              <div>
                <label className="mb-2 block text-xs font-medium text-muted-foreground">영상 형식</label>
                <div className="flex flex-wrap gap-2">
                  <Chip active={format === "long"} onClick={() => setFormat("long")} disabled={generating}>롱폼 (16:9)</Chip>
                  <Chip active={format === "short"} onClick={() => setFormat("short")} disabled={generating}>숏폼 (9:16)</Chip>
                </div>
              </div>

              {/* 출연 모델 수 */}
              <div>
                <label className="mb-2 block text-xs font-medium text-muted-foreground">출연 모델 수</label>
                <div className="flex flex-wrap gap-2">
                  {MODEL_COUNTS.map((m) => (
                    <Chip key={m} active={modelCount === m} onClick={() => setModelCount(m)} disabled={generating}>
                      {m}
                    </Chip>
                  ))}
                </div>
              </div>
            </div>

            {/* 분량 */}
            <div>
              <label className="mb-2 block text-xs font-medium text-muted-foreground">분량</label>
              <div className="flex flex-wrap items-center gap-2">
                {DURATIONS.map((d) => (
                  <Chip
                    key={d.min}
                    active={!customDuration && durationMin === d.min}
                    onClick={() => handleDurationSelect(d.min)}
                    disabled={generating}
                  >
                    {d.label}
                  </Chip>
                ))}
                <Chip active={customDuration} onClick={() => setCustomDuration(true)} disabled={generating}>직접 입력</Chip>
                {customDuration && (
                  <input
                    type="number"
                    min={1}
                    value={durationMin}
                    onChange={(e) => setDurationMin(Math.max(1, Number(e.target.value) || 1))}
                    disabled={generating}
                    className="w-20 rounded-lg border border-border bg-background px-2 py-1.5 text-xs text-foreground focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/30 disabled:opacity-50"
                  />
                )}
                {customDuration && <span className="text-xs text-muted-foreground">분</span>}
              </div>
            </div>

            {/* 장면 수 */}
            <div>
              <label className="mb-2 block text-xs font-medium text-muted-foreground">
                장면 수 <span className="text-muted-foreground/60">(분량 선택 시 자동 추천)</span>
              </label>
              <div className="flex flex-wrap items-center gap-2">
                {SCENE_PRESETS.map((n) => (
                  <Chip
                    key={n}
                    active={!customScene && sceneCount === n}
                    onClick={() => { setCustomScene(false); setSceneCount(n) }}
                    disabled={generating}
                  >
                    {n}
                  </Chip>
                ))}
                <Chip active={customScene} onClick={() => setCustomScene(true)} disabled={generating}>직접 입력</Chip>
                {customScene && (
                  <input
                    type="number"
                    min={1}
                    value={sceneCount}
                    onChange={(e) => setSceneCount(Math.max(1, Number(e.target.value) || 1))}
                    disabled={generating}
                    className="w-20 rounded-lg border border-border bg-background px-2 py-1.5 text-xs text-foreground focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/30 disabled:opacity-50"
                  />
                )}
                {customScene && <span className="text-xs text-muted-foreground">개</span>}
              </div>
            </div>

            {/* 모델 선택 */}
            <div>
              <label className="mb-2 block text-xs font-medium text-muted-foreground">
                모델 선택 <span className="text-muted-foreground/60">(채널 스택 기본값 자동 불러옴)</span>
              </label>
              {modelOptions.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {modelOptions.map((name) => (
                    <Chip
                      key={name}
                      active={selectedModels.includes(name)}
                      onClick={() => toggleModel(name)}
                      disabled={generating}
                    >
                      {selectedModels.includes(name) && "✓ "}{name}
                    </Chip>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground/60">캐릭터 라이브러리에 저장된 모델이 없습니다</p>
              )}
            </div>
          </div>

          {/* 요약 카드 */}
          <div className="grid grid-cols-4 gap-3">
            {Object.entries({
              카테고리: category,
              소재: topic || "—",
              "영상 길이": `${durationLabel} (${sceneCount}장면)`,
              형식: format === "short" ? "숏폼 (9:16)" : "롱폼 (16:9)",
            }).map(([label, value]) => (
              <div key={label} className="rounded-xl border border-border bg-card p-3">
                <p className="text-[10px] text-muted-foreground">{label}</p>
                <p className="mt-1 text-xs font-semibold text-foreground leading-snug">{value}</p>
              </div>
            ))}
          </div>

          {/* 트렌드 인사이트 적용 결과 */}
          {trendLoading && !activeInsight && (
            <div className="flex items-center gap-2 rounded-xl border border-border bg-card px-4 py-3 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> 트렌드 데이터를 불러오는 중…
            </div>
          )}

          {activeInsight && (
            <div className="flex flex-col gap-4 rounded-xl border border-primary/30 bg-card p-5">
              <div className="flex items-center justify-between gap-2">
                <h2 className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
                  <TrendingUp className="h-4 w-4 text-primary" />
                  트렌드 인사이트 적용
                </h2>
                <div className="flex items-center gap-2">
                  <span className="rounded-full bg-secondary/60 px-2 py-0.5 text-xs font-medium text-muted-foreground">
                    {activeInsight.category} · {FORMAT_LABEL[activeInsight.format]}
                  </span>
                  {!editingMeta && (
                    <button
                      onClick={startEditMeta}
                      className="flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:text-foreground"
                    >
                      <Pencil className="h-3 w-3" /> 본문 편집
                    </button>
                  )}
                </div>
              </div>

              {/* 시나리오 본문(제목/설명/해시태그) 인라인 편집 */}
              {editingMeta && (
                <div className="flex flex-col gap-3 rounded-lg border border-primary/30 bg-primary/5 p-4">
                  <div>
                    <label className="mb-1 block text-[11px] font-medium text-muted-foreground">제목</label>
                    <input
                      value={metaTitleDraft}
                      onChange={(e) => setMetaTitleDraft(e.target.value)}
                      className="w-full rounded-lg border border-border bg-card px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-[11px] font-medium text-muted-foreground">설명</label>
                    <textarea
                      value={metaDescDraft}
                      onChange={(e) => setMetaDescDraft(e.target.value)}
                      rows={3}
                      className="w-full resize-y rounded-lg border border-border bg-card px-3 py-2 text-xs leading-relaxed text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-[11px] font-medium text-muted-foreground">해시태그 (쉼표로 구분)</label>
                    <textarea
                      value={metaTagsDraft}
                      onChange={(e) => setMetaTagsDraft(e.target.value)}
                      rows={2}
                      className="w-full resize-y rounded-lg border border-border bg-card px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div className="flex items-center justify-end gap-2">
                    <button
                      onClick={cancelEditMeta}
                      className="rounded-md border border-border px-3 py-1.5 text-[11px] font-medium text-muted-foreground transition-colors hover:text-foreground"
                    >
                      취소
                    </button>
                    <button
                      onClick={saveMeta}
                      className="flex items-center gap-1 rounded-md bg-emerald-600 px-3 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-emerald-700"
                    >
                      <Save className="h-3 w-3" /> 저장
                    </button>
                  </div>
                </div>
              )}

              {/* 제목 후보 A/B */}
              <div>
                <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                  <Sparkles className="h-3.5 w-3.5" />
                  제목 후보 <span className="text-muted-foreground/60">(Power Words 자동 삽입 · 클릭해 선택)</span>
                </p>
                <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                  {titleCandidates.map((title) => {
                    const active = effectiveTitle === title
                    return (
                      <button
                        key={title}
                        onClick={() => handleSelectTitle(title)}
                        className={`flex items-start gap-2 rounded-lg border p-3 text-left text-xs transition-all ${
                          active
                            ? "border-primary/50 bg-primary/10 text-foreground"
                            : "border-border bg-background text-muted-foreground hover:border-primary/30 hover:text-foreground"
                        }`}
                      >
                        <span
                          className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 ${
                            active ? "border-primary" : "border-muted-foreground/40"
                          }`}
                        >
                          {active && <span className="h-2 w-2 rounded-full bg-primary" />}
                        </span>
                        <span className="flex-1">{title}</span>
                      </button>
                    )
                  })}
                </div>
              </div>

              {/* 설명 자동 생성 */}
              <div>
                <p className="mb-1.5 text-xs font-medium text-muted-foreground">
                  설명 자동 생성 <span className="text-muted-foreground/60">(첫 150자: 키워드 + 후크)</span>
                </p>
                <p className="rounded-lg border border-border bg-background px-3 py-2 text-xs leading-relaxed text-foreground">
                  {displayDescription || "—"}
                </p>
              </div>

              {/* 해시태그 5분류 조합 */}
              <div>
                <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                  <Hash className="h-3.5 w-3.5" />
                  해시태그 5분류 조합
                </p>
                <div className="flex flex-col gap-2">
                  {metaTags && (
                    <div className="flex flex-wrap items-center gap-1.5">
                      {metaTags.map((t) => (
                        <span key={t} className="rounded-md bg-secondary/50 px-1.5 py-0.5 text-[11px] text-muted-foreground">
                          #{t.replace(/^#/, "")}
                        </span>
                      ))}
                    </div>
                  )}
                  {!metaTags && ([
                    ["주요", activeInsight.tagsByCategory.primary],
                    ["변형", activeInsight.tagsByCategory.variants],
                    ["경쟁", activeInsight.tagsByCategory.competitor],
                    ["광범위", activeInsight.tagsByCategory.broad],
                    ["세부", activeInsight.tagsByCategory.niche],
                  ] as [string, string[]][]).map(([label, tags]) =>
                    tags.length ? (
                      <div key={label} className="flex flex-wrap items-center gap-1.5">
                        <span className="w-12 shrink-0 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/60">
                          {label}
                        </span>
                        {tags.slice(0, 6).map((t) => (
                          <span
                            key={t}
                            className="rounded-md bg-secondary/50 px-1.5 py-0.5 text-[11px] text-muted-foreground"
                          >
                            #{t.replace(/^#/, "")}
                          </span>
                        ))}
                      </div>
                    ) : null,
                  )}
                  {hashtags.length === 0 && (
                    <span className="text-[11px] text-muted-foreground/60">태그 데이터 없음</span>
                  )}
                </div>
              </div>

              {/* 형식별 길이/씬 자동 결정 */}
              <div className="grid grid-cols-3 gap-2 rounded-lg border border-border/60 bg-background/40 p-3 text-center">
                <div>
                  <p className="text-[10px] text-muted-foreground">권장 영상 길이</p>
                  <p className="mt-0.5 text-xs font-semibold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
                    {activeInsight.avgVideoLengthSec ? `${Math.round(activeInsight.avgVideoLengthSec)}초` : `${durationMin}분`}
                  </p>
                </div>
                <div className="border-x border-border/60">
                  <p className="text-[10px] text-muted-foreground">씬 수</p>
                  <p className="mt-0.5 text-xs font-semibold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
                    {sceneCount}개
                  </p>
                </div>
                <div>
                  <p className="text-[10px] text-muted-foreground">씬당 길이</p>
                  <p className="mt-0.5 text-xs font-semibold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
                    {Math.max(3, Math.round((durationMin * 60) / sceneCount))}초
                  </p>
                </div>
              </div>
            </div>
          )}

          <div className="rounded-xl border border-border bg-card overflow-hidden">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <h2 className="text-sm font-semibold text-foreground">씬 목록</h2>
              <span className="text-xs font-bold text-muted-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
                {scenes.length}개 장면
              </span>
            </div>

            {/* 입력이 마지막 생성 시점과 달라지면 씬 목록은 옛 설정 기준이므로
                흐리게 + 재생성 안내. (씬 생성은 비용이 드는 LLM 호출이라 자동 재생성 대신 무효화) */}
            {scenesStale && (
              <div className="flex items-center gap-2 border-b border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-xs font-medium text-amber-600 dark:text-amber-400">
                <RefreshCw className="h-3.5 w-3.5 shrink-0" />
                설정이 바뀌었습니다 — 아래 씬 목록은 이전 설정 기준입니다. &lsquo;시나리오 생성&rsquo;을 다시 눌러주세요.
              </div>
            )}

            <div className={`divide-y-0 transition-opacity ${scenesStale ? "pointer-events-none opacity-40" : ""}`}>
              {visibleScenes.map((scene) => (
                <div key={`${scene.id}:${scene.script}`} className="group">
                  <SceneRow
                    scene={scene}
                    expanded={!!expandedScripts[scene.id]}
                    regenerating={regeneratingId === scene.id}
                    onToggleScript={toggleScript}
                    onSaveMeta={handleSaveMeta}
                    onSaveScript={handleSaveScript}
                    onRegenerate={handleRegenerateScene}
                  />
                </div>
              ))}
            </div>
            {scenes.length > 4 && (
              <button
                onClick={() => setExpanded((p) => !p)}
                className="flex w-full items-center justify-center gap-1.5 border-t border-border py-3 text-xs font-medium text-muted-foreground transition-colors hover:bg-secondary/30 hover:text-foreground"
              >
                {expanded ? (
                  <><ChevronUp className="h-3.5 w-3.5" /> 접기</>
                ) : (
                  <><ChevronDown className="h-3.5 w-3.5" /> 나머지 {scenes.length - 4}개 장면 더보기</>
                )}
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="shrink-0 flex items-center justify-between border-t border-border bg-card/50 px-6 py-4">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
            총 {sceneCount}장면
          </span>
          <span className="text-muted-foreground">/</span>
          <span className="text-sm text-muted-foreground">{durationLabel}</span>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          {scenesStale && (
            <span className="text-[11px] font-medium text-amber-600 dark:text-amber-400">
              설정이 바뀌었습니다 — 시나리오를 다시 생성한 뒤 진행하세요
            </span>
          )}
          <button
            onClick={handleMakeVideo}
            disabled={scenesStale}
            title={scenesStale ? "설정이 바뀌었습니다 — 시나리오를 다시 생성한 뒤 진행하세요" : undefined}
            className="flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-lg shadow-primary/20 transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none disabled:hover:opacity-40"
          >
            이 시나리오로 영상 만들기
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )
}

export default function ScenarioPage() {
  return (
    <Suspense
      fallback={
        <div className="flex flex-1 items-center justify-center p-6 text-sm text-muted-foreground">
          불러오는 중…
        </div>
      }
    >
      <ScenarioPageInner />
    </Suspense>
  )
}
