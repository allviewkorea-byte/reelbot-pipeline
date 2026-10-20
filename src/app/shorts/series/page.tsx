"use client"

import { Suspense, useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { toast } from "sonner"
import { ArrowLeft, ExternalLink, Loader2, Play, Users } from "lucide-react"
import { WORKOUT_CHANNEL_ID } from "@/lib/music"

// 쇼츠 시즌 1 "돌잔치 D-14" — 15편 계획·진행·비용, 비공개 테스트 제작(1편씩, Day 1·4·6 중 선택) + Seedance 비교 1회.
// 목소리 없음(자막+운동 채널 음악). 테스트는 유튜브에 올리지 않고 이 화면(R2 미리보기)에서만 재생.

interface Episode {
  day: number
  dday: string
  format: "A" | "B" | "C"
  characters: string[]
  mom_stage: string
  plan: string
  status: string
  video_url?: string | null
  preview_url?: string | null
  cost?: { video_usd?: number; video_seconds?: number; seedance_usd?: number | null } | null
  notes?: { baby_dropped?: boolean } | null
  seedance?: { accepted?: boolean; blocked?: boolean; error?: string; model?: string } | null
  error?: string | null
  script?: { hook?: string; captions?: string[] } | null
}
interface SeriesResp {
  series: { title: string; episodes: Episode[] }
  run: { status?: string; current?: number | null; done?: number[]; failed?: Record<string, string> }
  unapproved: string[]
}

const FORMAT_KO: Record<string, string> = { A: "셀카", B: "운동", C: "일상" }
const ROLE_KO: Record<string, string> = { dad: "아빠", mom: "엄마", baby: "아기", mom_after: "엄마(후)", family: "가족" }
const STAGE_KO: Record<string, string> = { mom: "변화 전", mom_mid: "중간", mom_after: "변화 후" }
const STATUS_KO: Record<string, string> = {
  planned: "예정", producing: "제작 중", uploaded_private: "비공개 업로드", rendered: "완성(미리보기)", failed: "실패",
}
const TEST_DAYS = [1, 4, 6]
const TEST_DAY_KO: Record<number, string> = { 1: "Day 1 · 엄마 단독", 4: "Day 4 · 엄마+아빠", 6: "Day 6 · 엄마+아기" }

function SeriesInner() {
  const channel = useSearchParams().get("channel") || WORKOUT_CHANNEL_ID
  const [data, setData] = useState<SeriesResp | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [testDay, setTestDay] = useState(1)

  const load = useCallback(
    () =>
      fetch(`/api/shorts/series?channel=${encodeURIComponent(channel)}`, { cache: "no-store" })
        .then(async (r) => {
          const d = await r.json().catch(() => ({}))
          if (!r.ok) throw new Error(typeof d?.detail === "string" ? d.detail : `불러오기 실패(${r.status})`)
          setData(d)
          setError(null)
        })
        .catch((e) => setError(e instanceof Error ? e.message : "불러오기 실패")),
    [channel],
  )

  const running = data?.run?.status === "running"
  useEffect(() => {
    load()
    if (!running) return
    const t = setInterval(load, 5000)
    return () => clearInterval(t)
  }, [load, running])

  async function startTest() {
    if (!confirm(`Day ${testDay} 테스트 1편 + Seedance 비교 1회를 만들어요.\n유튜브에는 올리지 않고 이 화면에서만 볼 수 있어요.\n영상 생성 비용: 약 $4~7(Kling O3 $0.24/초, 재시도 제외). 진행할까요?`)) return
    setStarting(true)
    try {
      const r = await fetch("/api/shorts/test-run", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channel, days: [testDay], compare_seedance: true, upload: false }),
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(typeof d?.detail === "string" ? d.detail : `시작 실패(${r.status})`)
      toast.success("테스트 1편 제작을 시작했어요 — 수 분 걸려요")
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "시작 실패")
    } finally {
      setStarting(false)
    }
  }

  const eps = data?.series.episodes ?? []
  const seedance = eps.find((e) => e.seedance)?.seedance

  return (
    <div className="flex flex-col gap-4 p-4 md:p-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3 pl-12 md:pl-0">
          <Link
            href={`/shorts/cast?channel=${encodeURIComponent(channel)}`}
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-border text-muted-foreground hover:border-primary/40 hover:text-foreground"
            title="캐릭터 시트로"
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <div>
            <h1 className="text-lg font-semibold text-foreground">{data?.series.title ?? "쇼츠 시즌 1"}</h1>
            <p className="text-xs text-muted-foreground">D-14는 이야기 속 날짜 · 목소리 없음(자막+음악) · 테스트는 유튜브에 올리지 않고 여기서만 재생</p>
          </div>
        </div>
        <div className="flex items-center gap-2 self-start md:self-auto">
        <select
          value={testDay}
          onChange={(e) => setTestDay(Number(e.target.value))}
          disabled={starting || running}
          className="min-h-[40px] rounded-lg border border-border bg-card px-2 text-sm text-foreground disabled:opacity-40"
          aria-label="테스트 회차"
        >
          {TEST_DAYS.map((d) => <option key={d} value={d}>{TEST_DAY_KO[d]}</option>)}
        </select>
        <button
          onClick={startTest}
          disabled={starting || running || !data || data.unapproved.length > 0}
          title={data?.unapproved.length ? "확정되지 않은 캐스트가 있어요" : `Day ${testDay} 테스트 1편 (유튜브 업로드 없음)`}
          className="flex min-h-[40px] items-center gap-1.5 rounded-lg bg-emerald-600 px-3 text-sm font-semibold text-white shadow-sm hover:opacity-90 disabled:opacity-40"
        >
          {starting || running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          {running ? `제작 중 · Day ${data?.run.current ?? ""}` : "테스트 1편 제작"}
        </button>
        </div>
      </div>

      {error && <div className="rounded-xl border border-border bg-card p-4 text-sm text-red-400">{error}</div>}
      {data && data.unapproved.length > 0 && (
        <div className="flex items-center gap-2 rounded-xl border border-border bg-card p-3 text-sm text-muted-foreground">
          <Users className="h-4 w-4 shrink-0" />
          확정되지 않은 캐스트: {data.unapproved.map((r) => ROLE_KO[r] ?? r).join(", ")} —{" "}
          <Link href={`/shorts/cast?channel=${encodeURIComponent(channel)}`} className="text-primary underline">캐릭터 시트</Link>에서 확정해 주세요.
        </div>
      )}
      {seedance && (
        <div className="rounded-xl border border-border bg-card p-3 text-xs text-muted-foreground">
          Seedance 비교({seedance.model}): {seedance.accepted ? "레퍼런스 수락됨" : seedance.blocked ? "레퍼런스 거부됨" : "호출 실패"}
          {seedance.error ? ` — ${seedance.error}` : ""}
        </div>
      )}

      <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
        {eps.map((e) => (
          <div key={e.day} className="flex flex-col gap-1.5 rounded-xl border border-border bg-card p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-semibold text-foreground">Day {e.day} · {e.dday}</span>
              <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                e.status === "uploaded_private" || e.status === "rendered" ? "bg-emerald-500/15 text-emerald-400"
                  : e.status === "failed" ? "bg-red-500/15 text-red-400"
                  : e.status === "producing" ? "bg-primary/15 text-primary" : "bg-secondary text-muted-foreground"
              }`}>
                {STATUS_KO[e.status] ?? e.status}
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              {FORMAT_KO[e.format]} · {e.characters.map((c) => ROLE_KO[c] ?? c).join("·")} · 엄마 {STAGE_KO[e.mom_stage]}
              {TEST_DAYS.includes(e.day) ? " · 테스트" : ""}
            </p>
            <p className="text-xs text-foreground">{e.script?.hook ?? e.plan}</p>
            {e.notes?.baby_dropped && <p className="text-[11px] text-muted-foreground">아기 레퍼런스 거부 → 엄마·아빠 대본으로 대체</p>}
            {e.cost?.video_usd != null && (
              <p className="text-[11px] text-muted-foreground">영상 {e.cost.video_seconds}초 · ${e.cost.video_usd.toFixed(2)}</p>
            )}
            {e.error && <p className="truncate text-[11px] text-red-400" title={e.error}>{e.error}</p>}
            {e.preview_url && (
              <video
                src={e.preview_url}
                controls
                playsInline
                preload="metadata"
                className="mt-1 aspect-[9/16] w-full max-w-[240px] rounded-lg border border-border bg-black"
              />
            )}
            {e.video_url && (
              <a href={e.video_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-xs text-primary">
                <ExternalLink className="h-3.5 w-3.5" /> 비공개 영상 보기
              </a>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function ShortsSeriesPage() {
  return (
    <Suspense fallback={null}>
      <SeriesInner />
    </Suspense>
  )
}
