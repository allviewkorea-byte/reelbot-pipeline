"use client"

import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type TouchEvent as ReactTouchEvent } from "react"
import Link from "next/link"
import { toast } from "sonner"
import { ArrowLeft, Loader2, Music, Music2, Clapperboard, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { MusicQueueCard, TestCard, type QueueItem } from "@/components/music/MusicQueueCard"
import { SwipeVideoViewer } from "@/components/music/SwipeVideoViewer"
import { MusicJobCard } from "@/components/music/MusicJobCard"
import type { MusicJob } from "@/lib/music-jobs"
import { estimateProductionTime, fmtMinutes } from "@/lib/music"
import { MUSIC_GENRES, PLACE_BGM_SET } from "@/lib/music-genres"

// 카테고리(14장르 SSOT) + 전체. 클라이언트 사이드 필터(genre·mood 등 텍스트 키워드 매칭).
// 옛 5분류로 저장된 영상도 raw genre 라벨을 그대로 표시하고, 키워드로 해당 장르 필터에 잡힌다.
const CATEGORIES = [
  { key: "all", label: "전체", keywords: [] as string[] },
  ...MUSIC_GENRES.map((g) => ({ key: g.id, label: g.label, keywords: g.keywords })),
]

// 테스트/수동 생성 무드 드롭다운 — 14장르.
const TEST_MOODS = MUSIC_GENRES.map((g) => ({ key: g.id, label: g.label }))

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
  // PiP·스와이프 전체화면 뷰어 — 열린 영상의 (필터된 목록 기준) 인덱스. null=닫힘.
  const [viewerIndex, setViewerIndex] = useState<number | null>(null)

  const [testMood, setTestMood] = useState("citypop")
  const [testLoading, setTestLoading] = useState(false)
  const [testVideo, setTestVideo] = useState<{ url: string; engine?: string } | null>(null)
  const [showTestCard, setShowTestCard] = useState(false)

  // 수동 영상 생성(#26) — 검토 큐 정식 적재. 진행 상태는 #36 진행 카드(DB)로 표시.
  const [manualLoading, setManualLoading] = useState(false)
  const [manualCount, setManualCount] = useState("1") // #42 수동 생성 곡수(1~100, 기본 1)
  // #26-C 취소 — 진행 중 job_id + 취소 요청 표시(현재 스텝 완료 후 중단).
  const [manualJobId, setManualJobId] = useState<string | null>(null)
  const [cancelRequested, setCancelRequested] = useState(false)

  // #36 진행 중(+미확인 실패) 작업 — DB 기준, 페이지 이동에도 유지.
  const [activeJobs, setActiveJobs] = useState<MusicJob[]>([])
  const prevJobIdsRef = useRef<Set<string>>(new Set())

  const load = useCallback(() => {
    fetch("/api/music/queue")
      .then((r) => r.json())
      .then((d) => setItems(Array.isArray(d?.queue) ? d.queue : []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [])

  const loadJobs = useCallback(() => {
    fetch("/api/music/jobs/active")
      .then((r) => r.json())
      .then((d) => {
        const jobs: MusicJob[] = Array.isArray(d?.jobs) ? d.jobs : []
        const newIds = new Set(jobs.map((j) => j.job_id))
        const prev = prevJobIdsRef.current
        if (prev.size > 0) {
          let finished = false
          prev.forEach((id) => { if (!newIds.has(id)) finished = true })
          if (finished) {
            try {
              const ctx = new AudioContext()
              const osc = ctx.createOscillator()
              const gain = ctx.createGain()
              osc.connect(gain); gain.connect(ctx.destination)
              osc.frequency.value = 880
              gain.gain.setValueAtTime(0.3, ctx.currentTime)
              gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.5)
              osc.start(); osc.stop(ctx.currentTime + 0.5)
            } catch { /* 브라우저 자동재생 정책으로 막힐 수 있음 — 무시 */ }
          }
        }
        prevJobIdsRef.current = newIds
        setActiveJobs(jobs)
      })
      .catch(() => {})
  }, [])

  useEffect(() => { load() }, [load])

  // 진행 중 작업 폴링(3초) — 진입 즉시 조회 + 주기 갱신.
  useEffect(() => {
    loadJobs()
    const id = setInterval(loadJobs, 3000)
    return () => clearInterval(id)
  }, [loadJobs])

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
      // 테스트 영상도 검토 대기(pending)에 저장됨 → 큐 새로고침하면 정식 카드(MusicQueueCard)로
      // 표시되어 이미지·인물·PLAY LIST 토글·다국어 등 모든 기능을 동일하게 사용할 수 있다.
      setShowTestCard(false)
      load()
      toast.success("테스트 영상이 검토 대기에 추가되었습니다.")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "테스트 렌더 실패")
      setShowTestCard(false)
    } finally {
      setTestLoading(false)
    }
  }, [testMood, load])

  const runManual = useCallback(async () => {
    setManualLoading(true)
    setCancelRequested(false)
    setManualJobId(null)
    try {
      const tc = Math.max(1, Math.min(100, Math.floor(Number(manualCount)) || 1)) // #42 곡수 1~100 클램프
      const res = await fetch("/api/music/manual-render", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mood: testMood, track_count: tc }),
      })
      const data = await res.json()
      if (!res.ok || !data?.job_id) throw new Error(data?.detail || "수동 생성 시작 실패")
      const jobId = data.job_id as string
      setManualJobId(jobId) // #26-C 취소 버튼 활성화용
      loadJobs() // #36 즉시 진행 카드 표시(DB row 는 시작 시 동기 생성됨)
      // 폴링 — 3초 간격, done/error/cancelled 까지.
      await new Promise<void>((resolve) => {
        const tick = async () => {
          try {
            const sr = await fetch(`/api/music/manual-render/status/${jobId}`)
            const sd = await sr.json()
            if (sd?.status === "done") {
              toast.success("영상 생성 완료 — 검토 큐에 추가되었습니다.")
              load() // 큐 새로고침 → 새 pending 카드 등장(일반 카드)
              loadJobs() // 완료된 작업은 진행 카드에서 사라짐
              resolve(); return
            }
            if (sd?.status === "error") {
              toast.error(sd?.error || "영상 생성 실패")
              loadJobs() // 실패 카드로 전환
              resolve(); return
            }
            if (sd?.status === "cancelled") {
              toast.message("생성이 취소되었습니다 — 검토 큐에 적재되지 않습니다.")
              loadJobs()
              resolve(); return
            }
          } catch { /* 일시 실패는 다음 틱에 재시도 */ }
          setTimeout(tick, 3000)
        }
        tick()
      })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "수동 생성 시작 실패")
    } finally {
      setManualLoading(false)
      setManualJobId(null)
      setCancelRequested(false)
    }
  }, [testMood, manualCount, load, loadJobs])

  // #26-C 진행 중 취소 — 현재 스텝 완료 후 큐 적재 없이 종료(즉시 중단 아님).
  const cancelManual = useCallback(async () => {
    if (!manualJobId) return
    setCancelRequested(true)
    try {
      const r = await fetch(`/api/music/manual-render/${manualJobId}/cancel`, { method: "POST" })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || d?.ok === false) throw new Error(d?.error || d?.detail || "취소 실패")
      toast.message("취소 요청됨 — 현재 단계 완료 후 중단됩니다.")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "취소 실패")
      setCancelRequested(false)
    }
  }, [manualJobId])

  const filtered = useMemo(() => items.filter((it) => matchesCategory(it, filter)), [items, filter])

  // #33 E: 모바일 pull-to-refresh — 스크롤 최상단에서 아래로 끌면 큐 새로고침(직접 구현, 데스크탑 무영향).
  const scrollRef = useRef<HTMLDivElement>(null)
  const pullStart = useRef<number | null>(null)
  const [pull, setPull] = useState(0)
  const [refreshing, setRefreshing] = useState(false)
  const onTouchStart = (e: ReactTouchEvent) => {
    pullStart.current = (scrollRef.current?.scrollTop ?? 0) <= 0 ? e.touches[0].clientY : null
  }
  const onTouchMove = (e: ReactTouchEvent) => {
    if (pullStart.current == null) return
    const d = e.touches[0].clientY - pullStart.current
    if (d > 0) setPull(Math.min(80, d))
  }
  const onTouchEnd = () => {
    if (pull > 60 && !refreshing) {
      setRefreshing(true)
      load()
      setTimeout(() => setRefreshing(false), 800)
    }
    pullStart.current = null
    setPull(0)
  }

  return (
    <div
      ref={scrollRef}
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={onTouchEnd}
      className="flex h-full min-h-0 flex-col gap-4 overflow-auto p-4 md:p-6"
    >
      {(pull > 0 || refreshing) && (
        <div className="flex items-center justify-center text-xs text-muted-foreground" style={{ height: refreshing ? 28 : pull * 0.4 }}>
          {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : pull > 60 ? "놓으면 새로고침" : "당겨서 새로고침"}
        </div>
      )}
      <header className="pl-10 md:pl-0">
        {/* 모바일: 버튼 가로 한 줄(좌/우 정렬, 줄바꿈 없음). 데스크탑은 아래 인라인 행 사용. */}
        <div className="mb-3 flex items-center justify-between gap-2 md:hidden">
          <Link href="/music" className="inline-flex min-h-[44px] items-center gap-1.5 whitespace-nowrap rounded-lg border border-border px-3 text-sm text-muted-foreground hover:bg-white/5 hover:text-foreground">
            <ArrowLeft className="h-4 w-4" /> 대시보드
          </Link>
          <Link href="/music/design" className="inline-flex min-h-[44px] items-center gap-1.5 whitespace-nowrap rounded-lg border border-border px-3 text-sm text-muted-foreground hover:border-primary/40 hover:text-foreground">
            디자인 본부
          </Link>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/music" className="hidden items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground hover:bg-white/5 hover:text-foreground md:inline-flex">
            <ArrowLeft className="h-4 w-4" /> 대시보드
          </Link>
          <div>
            <h1 className="text-xl font-semibold text-foreground">검토 대기 ({items.length})</h1>
            <p className="text-sm text-muted-foreground">카드에서 바로 재생·썸네일·공개를 처리하세요.</p>
          </div>
          <Link href="/music/design" className="ml-auto hidden items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground hover:border-primary/40 hover:text-foreground md:inline-flex">
            디자인 본부
          </Link>
        </div>
      </header>

      {/* #36 진행 중 작업 — 항상 상단 노출(페이지 이동·기기 전환에도 DB 기준 유지) */}
      {activeJobs.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-semibold text-foreground">진행 중 작업 ({activeJobs.length})</h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {activeJobs.map((j) => (
              <MusicJobCard key={j.job_id} job={j} onChanged={loadJobs} />
            ))}
          </div>
        </section>
      )}

      <div className="flex min-h-0 flex-1 flex-col gap-4 md:flex-row">
        {/* 좌측 패널 — 모바일: 필터(위) + 수동 생성(아래) 세로 스택·전체 폭 / md+: 사이드바 */}
        <aside className="flex shrink-0 flex-col gap-3 md:w-[240px]">
          {/* 영상 생성 — 수동(검토 큐 정식) + 빠른 테스트(폐기). 모바일은 아래(order-2). */}
          <div className="order-2 flex w-full flex-col gap-1.5 rounded-xl border border-dashed border-border bg-secondary/20 p-2.5 md:order-1 md:w-auto">
            <select
              value={testMood}
              onChange={(e) => setTestMood(e.target.value)}
              disabled={testLoading || manualLoading}
              className="h-8 rounded-md border border-border bg-background px-1.5 text-xs text-foreground"
            >
              {TEST_MOODS.filter((m) => !PLACE_BGM_SET.has(m.key)).map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
              <optgroup label="── 장소 BGM ──">
                {TEST_MOODS.filter((m) => PLACE_BGM_SET.has(m.key)).map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
              </optgroup>
            </select>
            {/* #42 곡수 입력(1~100) */}
            <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
              곡수
              <input
                type="number"
                min={1}
                max={100}
                value={manualCount}
                disabled={manualLoading}
                onChange={(e) => setManualCount(e.target.value)}
                className="h-7 w-14 rounded-md border border-border bg-background px-1.5 text-center text-xs text-foreground"
              />
              곡
            </label>
            {/* 메인 액션 — 수동 영상 생성(검토 큐에 정식 적재) */}
            <button
              type="button"
              onClick={runManual}
              disabled={manualLoading}
              className="inline-flex items-center justify-center gap-1.5 rounded-md bg-primary px-2.5 py-2 text-xs font-medium text-primary-foreground hover:opacity-90 disabled:opacity-60"
              title="선택한 곡수만큼 진짜 음원을 생성해 검토 큐에 추가(수 분~수십 분, 유튜브 X)"
            >
              {manualLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Music2 className="h-3.5 w-3.5" />} 수동 영상 생성
            </button>
            {/* #26-C 취소 — 진행 중(job_id 확보)에만 표시. 클릭 후 "취소 요청됨..." 안내(즉시 중단 아님). */}
            {manualLoading && manualJobId && (
              <button
                type="button"
                onClick={cancelManual}
                disabled={cancelRequested}
                className="inline-flex items-center justify-center gap-1.5 rounded-md border border-red-500/40 px-2.5 py-1.5 text-[11px] font-medium text-red-400 hover:bg-red-500/10 disabled:opacity-60"
                title="진행 중인 생성을 취소합니다(현재 단계 완료 후 중단, 검토 큐 미적재)"
              >
                {cancelRequested ? <Loader2 className="h-3 w-3 animate-spin" /> : <X className="h-3 w-3" />}
                {cancelRequested ? "취소 요청됨…" : "생성 취소"}
              </button>
            )}
            {/* #42 예상(선택 곡수 기반, #41 estimateProductionTime 연동) */}
            {(() => {
              const tc = Math.max(1, Math.min(100, Math.floor(Number(manualCount)) || 1))
              const e = estimateProductionTime(tc)
              return (
                <div className="flex flex-col gap-0.5 text-[10px] text-muted-foreground">
                  <span>📹 영상 {fmtMinutes(e.videoMinutes)} · ⏱️ 제작 {fmtMinutes(e.totalMinutes)} · {tc}곡</span>
                  <span>💰 {e.credits} 크레딧 (~${e.costUsd.toFixed(2)})</span>

                </div>
              )
            })()}
            {/* 보조 — 빠른 테스트 10초(합성 음원, 폐기) */}
            <button
              type="button"
              onClick={runTest}
              disabled={testLoading}
              className="inline-flex items-center justify-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-[11px] font-medium text-muted-foreground hover:border-primary/40 hover:text-foreground disabled:opacity-60"
              title="합성 음원으로 10초 미리보기(폐기, 유튜브·DB 미저장)"
            >
              {testLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Clapperboard className="h-3 w-3" />} 🧪 빠른 테스트 10초
            </button>
          </div>

          {/* 카테고리 필터 — 모바일: 위(order-1) + 가로 스크롤(스크롤바 숨김) / md+: 세로 */}
          <div
            className="order-1 flex flex-nowrap gap-1.5 overflow-x-auto [&::-webkit-scrollbar]:hidden md:order-2 md:flex-col md:overflow-x-visible"
            style={{ scrollbarWidth: "none" }}
          >
            {CATEGORIES.map((c) => (
              <Fragment key={c.key}>
                {c.key === "hotel_lobby" && (
                  <span className="shrink-0 self-center whitespace-nowrap px-1 text-[10px] text-muted-foreground/60">── 장소 BGM ──</span>
                )}
                <button
                  type="button"
                  onClick={() => setFilter(c.key)}
                  className={cn(
                    "shrink-0 whitespace-nowrap rounded-lg border px-3 py-1.5 text-left text-xs font-medium transition-colors md:w-full",
                    filter === c.key ? "border-primary/40 bg-primary/15 text-primary" : "border-border text-muted-foreground hover:border-primary/30 hover:text-foreground",
                  )}
                >
                  {c.label}
                </button>
              </Fragment>
            ))}
          </div>
        </aside>

        {/* 우측 그리드 */}
        <div className="min-h-0 flex-1">
          {loading ? (
            <div className="flex h-40 items-center justify-center text-muted-foreground"><Loader2 className="h-6 w-6 animate-spin" /></div>
          ) : filtered.length === 0 && !showTestCard && !manualLoading ? (
            <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border/60 py-16 text-center text-muted-foreground">
              <Music className="h-10 w-10 opacity-40" />
              <p>{items.length === 0 ? "아직 영상이 없어요. cron이 매일 자동 생성합니다." : "이 카테고리에 해당하는 영상이 없습니다."}</p>
              <button type="button" onClick={runTest} disabled={testLoading} className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90">
                {testLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Clapperboard className="h-3.5 w-3.5" />} 테스트 영상 만들기
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
              {showTestCard && <TestCard loading={testLoading} video={testVideo} />}
              {filtered.map((it, idx) => (
                <MusicQueueCard
                  key={it.mix_id}
                  item={it}
                  onChanged={load}
                  onOpenViewer={it.mp4_url ? () => setViewerIndex(idx) : undefined}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* PiP·스와이프 전체화면 뷰어 — 별도 레이어. 필터된 목록을 좌우로 탐색. */}
      {viewerIndex !== null && filtered[viewerIndex] && (
        <SwipeVideoViewer
          items={filtered}
          index={viewerIndex}
          onIndexChange={setViewerIndex}
          onClose={() => setViewerIndex(null)}
        />
      )}
    </div>
  )
}
