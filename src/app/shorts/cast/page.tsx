"use client"

import { Suspense, useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { toast } from "sonner"
import { ArrowLeft, Check, CheckCircle2, Film, ImageIcon, Loader2, RefreshCw, Sparkles, X } from "lucide-react"
import { WORKOUT_CHANNEL_ID, withChannel } from "@/lib/music"
import { FamilyRolePanel, type UploadRole } from "@/components/shorts/FamilyCastPanel"

// 쇼츠 캐릭터 시트 — 가족 캐스트(업로드 role 탭) + 보관된 자동 생성 캐스트(lead 탭). 백곰 /cast 와 분리.
// lead: 생성은 백그라운드(폴링), 1장 재생성은 동기. 어느 탭이든 이미지가 바뀌면 그 role 확정이 풀린다.

interface Aspect { key: string; label: string }
interface CastEntry {
  role: string
  label: string
  subtitle_name?: string | null
  summary: string
  aspects: Record<string, string>
  status: "draft" | "approved"
}
interface Progress { status: "idle" | "running" | "done" | "failed"; generated: string[]; failed: string[]; total: number }

const POLL_MS = 3500

async function jsonOrThrow(res: Response) {
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(typeof data?.detail === "string" ? data.detail : `요청 실패(${res.status})`)
  return data
}

function ShortsCastInner() {
  const params = useSearchParams()
  const channel = params.get("channel") || WORKOUT_CHANNEL_ID
  const [cast, setCast] = useState<CastEntry[]>([])
  const [aspects, setAspects] = useState<Aspect[]>([])
  const [anchor, setAnchor] = useState("glow_front")
  const [roles, setRoles] = useState<UploadRole[]>([])
  const [tab, setTab] = useState("mom")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [progress, setProgress] = useState<Progress | null>(null)
  const [busyAspect, setBusyAspect] = useState<string | null>(null)
  const [approving, setApproving] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const entry = cast[0]
  const role = entry?.role ?? "lead"
  const running = progress?.status === "running"

  const apply = useCallback((p: Promise<{ cast?: CastEntry[]; aspects?: Aspect[]; anchor?: string; roles?: UploadRole[] }>) =>
    p
      .then((data) => {
        setCast(data.cast ?? [])
        setRoles(data.roles ?? [])
        setAspects(data.aspects ?? [])
        if (data.anchor) setAnchor(data.anchor)
        setError(null)
      })
      .catch((e) => setError(e instanceof Error ? e.message : "불러오기 실패"))
      .finally(() => setLoading(false)), [])

  const load = useCallback(
    () => apply(fetch(`/api/shorts/cast?channel=${encodeURIComponent(channel)}`, { cache: "no-store" }).then(jsonOrThrow)),
    [apply, channel],
  )

  const stopPoll = () => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = null
  }

  const poll = useCallback(() => {
    stopPoll()
    pollRef.current = setInterval(async () => {
      try {
        const qs = new URLSearchParams({ channel, role })
        const p: Progress = await jsonOrThrow(await fetch(`/api/shorts/cast/status?${qs}`, { cache: "no-store" }))
        setProgress(p)
        await load()
        if (p.status !== "running") {
          stopPoll()
          if (p.status === "done") toast.success(p.failed.length ? `생성 완료 (실패 ${p.failed.length}장 — 개별 재생성)` : "8장 생성 완료")
          else toast.error("생성 실패 — 정면부터 만들지 못했어요")
        }
      } catch {
        /* 일시 오류 — 다음 폴링에서 재시도 */
      }
    }, POLL_MS)
  }, [channel, role, load])

  useEffect(() => {
    load()
    return stopPoll
  }, [load])

  // 새로고침 시 진행 중이면 폴링 재개
  useEffect(() => {
    if (!entry) return
    const qs = new URLSearchParams({ channel, role: entry.role })
    fetch(`/api/shorts/cast/status?${qs}`, { cache: "no-store" })
      .then((r) => r.json())
      .then((p: Progress) => {
        if (p?.status === "running") {
          setProgress(p)
          poll()
        }
      })
      .catch(() => {})
  }, [entry?.role, channel]) // eslint-disable-line react-hooks/exhaustive-deps

  async function generateAll() {
    if (entry?.aspects[anchor] && !confirm("8장을 모두 새로 만들어요. 지금 시트는 덮어써지고 확정이 풀립니다. 진행할까요?")) return
    try {
      await jsonOrThrow(await fetch("/api/shorts/cast/generate", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ channel, role }),
      }))
      setProgress({ status: "running", generated: [], failed: [], total: aspects.length || 8 })
      poll()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "생성 시작 실패")
    }
  }

  async function regenerate(aspect: string) {
    setBusyAspect(aspect)
    try {
      const data = await jsonOrThrow(await fetch("/api/shorts/cast/aspect", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ channel, role, aspect }),
      }))
      if (data.warning) toast.warning(data.warning)
      else toast.success("다시 만들었어요")
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "재생성 실패")
    } finally {
      setBusyAspect(null)
    }
  }

  async function approve(approved: boolean) {
    setApproving(true)
    try {
      await jsonOrThrow(await fetch("/api/shorts/cast/approve", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ channel, role, approved }),
      }))
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "저장 실패")
    } finally {
      setApproving(false)
    }
  }

  const count = entry ? Object.keys(entry.aspects).length : 0

  return (
    <div className="flex flex-col gap-4 p-4 md:p-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3 pl-12 md:pl-0">
          <Link
            href={withChannel("/music", channel)}
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-border text-muted-foreground hover:border-primary/40 hover:text-foreground"
            title="채널 화면으로"
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <div>
            <h1 className="text-lg font-semibold text-foreground">쇼츠 캐릭터 시트</h1>
            <p className="text-xs text-muted-foreground">시즌1 돌잔치 D-14 · 확정한 인물만 영상 레퍼런스로 쓰입니다</p>
          </div>
          <Link
            href={`/shorts/series?channel=${encodeURIComponent(channel)}`}
            className="ml-1 flex min-h-[36px] shrink-0 items-center gap-1.5 rounded-lg border border-border px-2.5 text-xs font-medium text-muted-foreground hover:border-primary/40 hover:text-foreground"
          >
            <Film className="h-3.5 w-3.5" />
            시즌 1
          </Link>
        </div>
        {tab === "lead" && entry && (
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={generateAll}
              disabled={running || !!busyAspect}
              className="flex min-h-[40px] items-center gap-1.5 rounded-lg border border-border bg-background px-3 text-sm font-medium text-foreground hover:border-primary/40 disabled:opacity-50"
            >
              {running ? <Loader2 className="h-4 w-4 animate-spin" /> : entry.aspects[anchor] ? <RefreshCw className="h-4 w-4 text-muted-foreground" /> : <Sparkles className="h-4 w-4 text-primary" />}
              {running ? `생성 중 ${progress?.generated.length ?? 0}/${progress?.total ?? 8}` : entry.aspects[anchor] ? "전체 다시 생성" : "8장 생성"}
            </button>
            {entry.status === "approved" ? (
              <button
                onClick={() => approve(false)}
                disabled={approving || running}
                className="flex min-h-[40px] items-center gap-1.5 rounded-lg border border-emerald-500/40 px-3 text-sm font-semibold text-emerald-400 hover:bg-emerald-500/10 disabled:opacity-40"
              >
                <X className="h-4 w-4" />
                확정 해제
              </button>
            ) : (
              <button
                onClick={() => approve(true)}
                disabled={approving || running || count < (aspects.length || 8)}
                title={count < (aspects.length || 8) ? "8장이 모두 있어야 확정할 수 있어요" : "이 시트로 확정"}
                className="flex min-h-[40px] items-center gap-1.5 rounded-lg bg-emerald-600 px-3 text-sm font-semibold text-white shadow-sm hover:opacity-90 disabled:opacity-40"
              >
                <Check className="h-4 w-4" />
                확정
              </button>
            )}
          </div>
        )}
      </div>

      {loading ? (
        <div className="flex h-60 items-center justify-center text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      ) : error ? (
        <div className="rounded-xl border border-border bg-card p-4 text-sm text-red-400">{error}</div>
      ) : (
        <>
          <div className="flex gap-1.5 overflow-x-auto pb-1">
            {[...roles.map((r) => ({ key: r.role, label: r.label, ok: r.status === "approved" })),
              ...(entry ? [{ key: "lead", label: `보관 · ${entry.subtitle_name ?? entry.label}`, ok: false }] : [])].map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`flex min-h-[36px] shrink-0 items-center gap-1 rounded-lg border px-3 text-sm font-medium transition-colors ${
                  tab === t.key ? "border-primary/40 bg-primary/15 text-foreground" : "border-border text-muted-foreground hover:text-foreground"
                }`}
              >
                {t.ok && <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />}
                {t.label}
              </button>
            ))}
          </div>
          {tab !== "lead" ? (
            roles.find((r) => r.role === tab) ? (
              <FamilyRolePanel channel={channel} role={roles.find((r) => r.role === tab) as UploadRole} onChanged={load} />
            ) : (
              <div className="rounded-xl border border-border bg-card p-4 text-sm text-muted-foreground">캐스트를 불러오지 못했어요.</div>
            )
          ) : entry ? (
        <>
          <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card p-3">
            <span className="text-sm font-semibold text-foreground">
              {entry.label}{entry.subtitle_name ? ` · ${entry.subtitle_name}` : ""}
            </span>
            {entry.status === "approved" ? (
              <span className="flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-400">
                <CheckCircle2 className="h-3 w-3" />
                확정
              </span>
            ) : (
              <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[11px] font-medium text-primary">검토 중</span>
            )}
            <span className="text-xs text-muted-foreground">{entry.summary}</span>
            <p className="w-full text-[11px] text-amber-400">보관 중 — 지금 시즌 영상에는 쓰이지 않아요(나중에 재사용 가능).</p>
            <p className="w-full text-[11px] text-muted-foreground">
              ⚠️ 평소·반전 8장이 모두 같은 얼굴(이목구비)인지 확인해 주세요. 실존 인물(연예인·선수)과 닮아 보이면 확정하지 말고 기준 얼굴(반전 정면)부터 다시 만들어 주세요. 손·관절이 어색한 장은 개별 재생성. 이름은 자막에만 쓰입니다.
            </p>
          </div>

          <div className="grid grid-cols-2 items-start gap-3 md:grid-cols-4">
            {aspects.map((a) => {
              const url = entry.aspects[a.key]
              const busy = busyAspect === a.key
              const failed = progress?.failed.includes(a.key)
              const pending = running && !progress?.generated.includes(a.key) && !failed
              return (
                <div key={a.key} className="flex flex-col gap-2 rounded-xl border border-border bg-card p-2">
                  <div className={`relative overflow-hidden rounded-lg bg-secondary/30 ${a.key.startsWith("expr_") ? "aspect-square" : "aspect-[9/16]"}`}>
                    {url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <a href={url} target="_blank" rel="noreferrer"><img src={url} alt={a.label} className="h-full w-full object-cover" /></a>
                    ) : (
                      <div className="flex h-full w-full items-center justify-center">
                        <ImageIcon className="h-6 w-6 text-muted-foreground/30" />
                      </div>
                    )}
                    {(busy || pending) && (
                      <div className="absolute inset-0 flex items-center justify-center bg-background/60">
                        <Loader2 className="h-5 w-5 animate-spin text-primary" />
                      </div>
                    )}
                  </div>
                  <div className="flex items-center justify-between gap-1">
                    <span className={`truncate text-xs font-medium ${failed ? "text-red-400" : "text-foreground"}`}>
                      {a.label}{failed ? " · 실패" : ""}
                    </span>
                    <button
                      onClick={() => regenerate(a.key)}
                      disabled={running || !!busyAspect || (a.key !== anchor && !entry.aspects[anchor])}
                      title={a.key === anchor ? "기준 얼굴만 다시 — 나머지와 얼굴이 어긋날 수 있어요" : "이 장만 다시 생성"}
                      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border text-muted-foreground hover:border-primary/40 hover:text-foreground disabled:opacity-40"
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </>
          ) : (
            <div className="rounded-xl border border-border bg-card p-4 text-sm text-muted-foreground">보관된 캐스트가 없어요.</div>
          )}
        </>
      )}
    </div>
  )
}

export default function ShortsCastPage() {
  return (
    <Suspense fallback={null}>
      <ShortsCastInner />
    </Suspense>
  )
}
