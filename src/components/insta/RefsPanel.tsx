"use client"

import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { ExternalLink, Loader2, Search } from "lucide-react"
import { jsonOrThrow } from "@/components/studio/studio-lib"

// 오늘의 레퍼런스(A2-1) — 유튜브 코디 영상 썸네일 + AI 가 읽은 컨셉 이름. 참고용(결과물에 그대로 쓰지 않음).
// "레퍼런스 모으기" = 오늘 검색어로 수집(하루 1회, 이미 했으면 분석만) → 백그라운드, 5초마다 다시 읽는다.

interface Look { concept: string }
interface RefRow {
  video_id: string; title: string; thumb_url: string | null; video_url: string; views: number | null
  status: "new" | "analyzed" | "failed" | "used"; analysis: { looks?: Look[] } | null
}
interface Usage { youtube: { units: number; cap: number }; has_youtube_key: boolean }

export function RefsPanel() {
  const [refs, setRefs] = useState<RefRow[]>([])
  const [running, setRunning] = useState(false)
  const [usage, setUsage] = useState<Usage | null>(null)

  const load = useCallback(
    () =>
      Promise.all([
        fetch("/api/insta/refs", { cache: "no-store" }).then(jsonOrThrow).then((d) => {
          setRefs(d.refs ?? [])
          setRunning(!!d.status?.running)
        }),
        fetch("/api/insta/usage", { cache: "no-store" }).then(jsonOrThrow).then(setUsage),
      ]).catch(() => {}),
    [],
  )

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!running) return
    const t = setInterval(load, 5000)
    return () => clearInterval(t)
  }, [running, load])

  async function collect() {
    try {
      const d = await jsonOrThrow(await fetch("/api/insta/refs/collect", { method: "POST" }))
      setRunning(true)
      toast.message(d.started ? "레퍼런스를 찾고 있어요" : "이미 찾는 중이에요")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "시작하지 못했어요")
    }
  }

  return (
    <section className="flex min-w-0 flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold text-foreground">오늘의 레퍼런스</h2>
        {usage && (
          <span className="text-[11px] text-muted-foreground">
            {usage.has_youtube_key ? `유튜브 사용량 ${usage.youtube.units}/${usage.youtube.cap}` : "유튜브 연결 필요"}
          </span>
        )}
        <button onClick={collect} disabled={running || (usage ? !usage.has_youtube_key : false)}
          className="ml-auto flex min-h-[36px] items-center gap-1.5 rounded-lg border border-border bg-background px-3 text-xs font-medium text-foreground hover:border-primary/40 disabled:opacity-50">
          {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />} {running ? "찾는 중…" : "레퍼런스 모으기"}
        </button>
      </div>
      {refs.length === 0 ? (
        <p className="text-xs text-muted-foreground">아직 모은 레퍼런스가 없어요.</p>
      ) : (
        <div className="grid min-w-0 grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
          {refs.map((r) => {
            const looks = r.analysis?.looks ?? []
            return (
              <a key={r.video_id} href={r.video_url} target="_blank" rel="noreferrer" title={r.title}
                className="flex min-w-0 flex-col gap-1 rounded-lg border border-border bg-background p-1.5 hover:border-primary/40">
                <div className="aspect-video overflow-hidden rounded-md bg-secondary/30">
                  {r.thumb_url && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={r.thumb_url} alt="" className="h-full w-full object-cover" />
                  )}
                </div>
                <span className="truncate text-[11px] font-medium text-foreground">
                  {looks.length ? looks.map((l) => l.concept).join(" · ") : r.status === "failed" ? "분석 못함" : "분석 대기"}
                </span>
                <span className="flex items-center gap-1 truncate text-[10px] text-muted-foreground">
                  <ExternalLink className="h-2.5 w-2.5 shrink-0" /> 참고한 영상
                </span>
              </a>
            )
          })}
        </div>
      )}
    </section>
  )
}
