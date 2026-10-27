"use client"

import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { Clapperboard, Loader2 } from "lucide-react"
import { jsonOrThrow } from "@/components/studio/studio-lib"

// 컬렉션 릴스(A3) — 롤모델 포맷: 같은 자세·배경에 옷만 바꾼 Look 1~N + 표지 카피(".zip").
// 버튼 하나로 테마 → 쿠팡 픽 → Look 1 → 옷 교체 → 영상까지. 결과: 영상 미리보기 · 표지 · 룩별 사진·상품.

interface LookRow { n: number; image_url: string | null; product?: { name?: string | null; mall?: string | null; price?: number | null } }
interface Collection {
  id: string; status: "making" | "ok" | "failed" | "hidden"; error: string | null; cost_usd: number | null
  theme: { concept?: string; title_ko?: string[]; zip?: string; title_en?: string }
  video_url: string | null; cover_url: string | null; looks: LookRow[]; created_at: string
}
interface Job { id: string; state: "queued" | "running" | "done" | "failed"; step: string; error: string | null; done_looks?: number; n?: number }

const POLL_MS = 4000

export function CollectionPanel({ character, ready }: { character: string; ready: boolean }) {
  const [rows, setRows] = useState<Collection[]>([])
  const [job, setJob] = useState<Job | null>(null)
  const running = job?.state === "queued" || job?.state === "running"

  const load = useCallback(
    () => fetch("/api/insta/collections", { cache: "no-store" }).then(jsonOrThrow).then((d) => setRows(d.collections ?? [])).catch(() => {}),
    [],
  )
  useEffect(() => {
    load()
  }, [load])

  const jobId = job?.id
  useEffect(() => {
    if (!jobId || !running) return
    const t = setInterval(async () => {
      try {
        const j: Job = await jsonOrThrow(await fetch(`/api/insta/collections/jobs/${encodeURIComponent(jobId)}`, { cache: "no-store" }))
        setJob(j)
        if (j.state === "done" || j.state === "failed") {
          await load()
          if (j.state === "done") toast.success("컬렉션 릴스 완성")
          else toast.error(j.error || "만들지 못했어요")
        }
      } catch {
        /* 다음 폴링에서 재시도 */
      }
    }, POLL_MS)
    return () => clearInterval(t)
  }, [jobId, running, load])

  async function make() {
    try {
      const j = await jsonOrThrow(await fetch("/api/insta/collections", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ character_id: character, n: 5 }),
      }))
      setJob(j)
      toast.message("컬렉션 릴스를 만드는 중 — 8~12분 걸려요")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "시작 실패")
    }
  }

  const latest = rows[0]
  return (
    <section className="flex min-w-0 flex-col gap-3 rounded-xl border border-primary/30 bg-card p-4">
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center">
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <h2 className="text-sm font-semibold text-foreground">컬렉션 릴스</h2>
          <p className="text-xs text-muted-foreground">
            {running
              ? `${job?.step || "진행 중…"}${job?.n ? ` (${job?.done_looks ?? 0}/${job.n})` : ""}`
              : "테마 하나로 같은 자세에 옷만 바꾼 Look 1~5 릴스를 만들어요. 누르기만 하면 돼요."}
          </p>
        </div>
        <button onClick={make} disabled={!ready || running}
          className="flex min-h-[44px] shrink-0 items-center justify-center gap-2 rounded-lg bg-primary px-5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
          {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Clapperboard className="h-4 w-4" />}
          {running ? "만드는 중…" : "컬렉션 릴스 만들기"}
        </button>
      </div>

      {latest && (
        <div className="flex min-w-0 flex-col gap-3 md:flex-row">
          {latest.video_url ? (
            <video src={latest.video_url} poster={latest.cover_url ?? undefined} controls playsInline
              className="aspect-[9/16] w-full max-w-[280px] shrink-0 rounded-lg bg-black object-cover" />
          ) : (
            <div className="flex aspect-[9/16] w-full max-w-[280px] shrink-0 items-center justify-center rounded-lg bg-secondary text-xs text-muted-foreground">
              {latest.status === "failed" ? latest.error || "실패" : "만드는 중"}
            </div>
          )}
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <div className="text-sm font-semibold text-foreground">
              {latest.theme?.zip || latest.theme?.concept || "컬렉션"}
              {latest.cost_usd ? <span className="ml-2 text-xs font-normal text-muted-foreground">약 {Math.round(latest.cost_usd * 1400).toLocaleString("ko-KR")}원</span> : null}
            </div>
            {latest.theme?.title_ko && <p className="text-xs text-muted-foreground">{latest.theme.title_ko.join(" ")}</p>}
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
              {latest.looks.map((lk) => (
                <div key={lk.n} className="flex min-w-0 flex-col gap-1">
                  {lk.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={lk.image_url} alt={`Look ${lk.n}`} className="aspect-[9/16] w-full rounded-md object-cover" />
                  ) : <div className="aspect-[9/16] w-full rounded-md bg-secondary" />}
                  <span className="truncate text-[11px] text-muted-foreground">Look {lk.n} · {lk.product?.name ?? ""}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
