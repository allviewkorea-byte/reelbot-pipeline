"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import { ArrowLeft, Loader2, Music, Music2, Clapperboard } from "lucide-react"
import { cn } from "@/lib/utils"
import { MusicQueueCard, TestCard, type QueueItem } from "@/components/music/MusicQueueCard"

// 카테고리(음악 헌법 상황·장르 → 대표 5종) + 전체. 클라이언트 사이드 필터.
const CATEGORIES = [
  { key: "all", label: "전체", keywords: [] as string[] },
  { key: "citypop", label: "시티팝/드라이브", keywords: ["시티팝", "citypop", "city pop", "드라이브", "drive", "운전", "출근", "퇴근", "commute"] },
  { key: "cafe", label: "카페/재즈", keywords: ["카페", "cafe", "재즈", "jazz", "커피", "coffee", "브런치", "lounge", "라운지"] },
  { key: "ballad", label: "이별/발라드", keywords: ["이별", "헤어", "breakup", "발라드", "ballad", "슬픔", "sad", "그리움", "눈물"] },
  { key: "workout", label: "운동/동기부여", keywords: ["운동", "헬스", "workout", "gym", "러닝", "running", "동기", "motivat", "fitness", "트레이닝"] },
  { key: "sleep", label: "수면/공부", keywords: ["수면", "잠", "취침", "sleep", "공부", "스터디", "study", "집중", "focus", "독서", "lofi", "lo-fi"] },
]

const TEST_MOODS = [
  { key: "citypop", label: "시티팝/드라이브" },
  { key: "cafe", label: "카페/재즈" },
  { key: "ballad", label: "이별/발라드" },
  { key: "workout", label: "운동/동기부여" },
  { key: "sleep", label: "수면/공부" },
]

function matchesCategory(item: QueueItem, catKey: string): boolean {
  if (catKey === "all") return true
  const cat = CATEGORIES.find((c) => c.key === catKey)
  if (!cat) return true
  const hay = [item.genre, item.mood, item.viz_spec?.subtitle_en, item.title_kr, item.slug]
    .filter(Boolean)
    .join(" ")
    .toLowerCase()
  return cat.keywords.some((k) => hay.includes(k.toLowerCase()))
}

export default function MusicQueueGridPage() {
  const [items, setItems] = useState<QueueItem[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState("all")

  const [testMood, setTestMood] = useState("citypop")
  const [testLoading, setTestLoading] = useState(false)
  const [testVideo, setTestVideo] = useState<{ url: string; engine?: string } | null>(null)
  const [showTestCard, setShowTestCard] = useState(false)

  // 1곡 풀 테스트(#25)
  const [fullLoading, setFullLoading] = useState(false)
  const [fullStep, setFullStep] = useState("대기")
  const [fullVideo, setFullVideo] = useState<{ url: string } | null>(null)
  const [showFullCard, setShowFullCard] = useState(false)

  const load = useCallback(() => {
    fetch("/api/music/queue")
      .then((r) => r.json())
      .then((d) => setItems(Array.isArray(d?.queue) ? d.queue : []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const runTest = useCallback(async () => {
    setTestLoading(true)
    setTestVideo(null)
    setShowTestCard(true)
    try {
      const res = await fetch("/api/music/test-render", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mood: testMood }),
      })
      const data = await res.json()
      if (!res.ok || !data?.video_url) throw new Error(data?.detail || "테스트 렌더 실패")
      setTestVideo({ url: data.video_url, engine: data.engine })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "테스트 렌더 실패")
      setShowTestCard(false)
    } finally {
      setTestLoading(false)
    }
  }, [testMood])

  const runFull = useCallback(async () => {
    setFullLoading(true)
    setFullVideo(null)
    setFullStep("대기")
    setShowFullCard(true)
    try {
      const res = await fetch("/api/music/test-render-full", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mood: testMood }),
      })
      const data = await res.json()
      if (!res.ok || !data?.job_id) throw new Error(data?.detail || "풀 테스트 시작 실패")
      const jobId = data.job_id as string
      // 폴링 — 3초 간격, done/error 까지.
      await new Promise<void>((resolve) => {
        const tick = async () => {
          try {
            const sr = await fetch(`/api/music/test-render-full/status/${jobId}`)
            const sd = await sr.json()
            if (sd?.step) setFullStep(sd.step)
            if (sd?.status === "done" && sd?.video_url) {
              setFullVideo({ url: sd.video_url })
              resolve(); return
            }
            if (sd?.status === "error") {
              toast.error(sd?.error || "풀 테스트 실패")
              setShowFullCard(false)
              resolve(); return
            }
          } catch { /* 일시 실패는 다음 틱에 재시도 */ }
          setTimeout(tick, 3000)
        }
        tick()
      })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "풀 테스트 시작 실패")
      setShowFullCard(false)
    } finally {
      setFullLoading(false)
    }
  }, [testMood])

  const filtered = useMemo(() => items.filter((it) => matchesCategory(it, filter)), [items, filter])

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-auto p-4 md:p-6">
      <header className="flex items-center gap-3 pl-10 md:pl-0">
        <Link href="/music" className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground hover:bg-white/5 hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> 대시보드
        </Link>
        <div>
          <h1 className="text-xl font-semibold text-foreground">검토 대기 ({items.length})</h1>
          <p className="text-sm text-muted-foreground">카드에서 바로 재생·썸네일·공개를 처리하세요.</p>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-4 md:flex-row">
        {/* 좌측 패널 — 모바일은 가로 스크롤, md+ 사이드바 */}
        <aside className="flex shrink-0 flex-row gap-2 overflow-x-auto md:w-[240px] md:flex-col md:overflow-x-visible">
          {/* 테스트 영상 — 빠른 10초 + 1곡 풀(3~4분) */}
          <div className="flex shrink-0 flex-col gap-1.5 rounded-xl border border-dashed border-border bg-secondary/20 p-2.5">
            <select
              value={testMood}
              onChange={(e) => setTestMood(e.target.value)}
              disabled={testLoading || fullLoading}
              className="h-8 rounded-md border border-border bg-background px-1.5 text-xs text-foreground"
            >
              {TEST_MOODS.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
            </select>
            <button
              type="button"
              onClick={runTest}
              disabled={testLoading}
              className="inline-flex items-center justify-center gap-1.5 rounded-md bg-primary px-2.5 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90"
            >
              {testLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Clapperboard className="h-3.5 w-3.5" />} 빠른 테스트 10초
            </button>
            <button
              type="button"
              onClick={runFull}
              disabled={fullLoading}
              className="inline-flex items-center justify-center gap-1.5 rounded-md border border-cyan-500/40 bg-cyan-500/10 px-2.5 py-1.5 text-xs font-medium text-cyan-300 hover:bg-cyan-500/20 disabled:opacity-60"
              title="진짜 음원 1곡을 생성해 풀 렌더(수 분 소요, 유튜브·DB 미저장)"
            >
              {fullLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Music2 className="h-3.5 w-3.5" />} 1곡 풀 테스트 3~4분
            </button>
          </div>

          {/* 카테고리 필터 */}
          <div className="flex shrink-0 flex-row gap-1.5 md:flex-col">
            {CATEGORIES.map((c) => (
              <button
                key={c.key}
                type="button"
                onClick={() => setFilter(c.key)}
                className={cn(
                  "shrink-0 whitespace-nowrap rounded-lg border px-3 py-1.5 text-left text-xs font-medium transition-colors md:w-full",
                  filter === c.key ? "border-primary/40 bg-primary/15 text-primary" : "border-border text-muted-foreground hover:border-primary/30 hover:text-foreground",
                )}
              >
                {c.label}
              </button>
            ))}
          </div>
        </aside>

        {/* 우측 그리드 */}
        <div className="min-h-0 flex-1">
          {loading ? (
            <div className="flex h-40 items-center justify-center text-muted-foreground"><Loader2 className="h-6 w-6 animate-spin" /></div>
          ) : filtered.length === 0 && !showTestCard && !showFullCard ? (
            <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border/60 py-16 text-center text-muted-foreground">
              <Music className="h-10 w-10 opacity-40" />
              <p>{items.length === 0 ? "아직 영상이 없어요. cron이 매일 자동 생성합니다." : "이 카테고리에 해당하는 영상이 없습니다."}</p>
              <button type="button" onClick={runTest} disabled={testLoading} className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90">
                {testLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Clapperboard className="h-3.5 w-3.5" />} 테스트 영상 만들기
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {showFullCard && <TestCard loading={fullLoading} video={fullVideo} variant="full" step={fullStep} />}
              {showTestCard && <TestCard loading={testLoading} video={testVideo} variant="quick" />}
              {filtered.map((it) => (
                <MusicQueueCard key={it.mix_id} item={it} onChanged={load} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
