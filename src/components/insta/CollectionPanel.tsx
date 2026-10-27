"use client"

import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { Clapperboard, Eye, Loader2, RefreshCw } from "lucide-react"
import { jsonOrThrow } from "@/components/studio/studio-lib"

// 컬렉션 릴스(A3) — 테마 하나로 01~05, 룩마다 다른 포즈·장소·코디 + 표지(슬로건 "코디 저장소").
// 1) "기획 미리보기": 테마·장면(자세·장소)·상품만 먼저 보여 준다(이미지 생성 없음, 저렴).
// 2) "이대로 릴스 만들기": 확인한 기획 그대로 Look 1 → 옷 교체 → 영상. 결과: 영상 · 표지 · 룩별 사진·상품.

interface Prod { name?: string | null; mall?: string | null; price?: number | null; image_url?: string | null; kind?: string | null }
interface Scene { pose_ko?: string; location_ko?: string; face?: string }
interface LookRow { idea?: string; n: number; image_url: string | null; product_image?: string | null; product?: Prod; items?: Prod[]; scene?: Scene; spare?: boolean }
interface Collection {
  id: string; status: "planned" | "making" | "ok" | "failed" | "hidden"; error: string | null; cost_usd: number | null
  theme: { concept?: string; title_ko?: string[]; zip?: string; title_en?: string }
  base_items?: Prod[]
  video_url: string | null; cover_url: string | null; looks: LookRow[]; created_at: string
}
interface Job { id: string; state: "queued" | "running" | "done" | "failed"; step: string; error: string | null; done_looks?: number; n?: number }

const POLL_MS = 4000

export function CollectionPanel({ character, ready }: { character: string; ready: boolean }) {
  const [rows, setRows] = useState<Collection[]>([])
  const [job, setJob] = useState<Job | null>(null)
  const [zoom, setZoom] = useState<{ src: string; caption: string } | null>(null)   // 눌러서 크게 보기
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

  async function plan(mode: "theme" | "lookfirst" = "theme") {
    try {
      const j = await jsonOrThrow(await fetch("/api/insta/collections/plan", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ character_id: character, n: 5, mode }),
      }))
      setJob(j)
      toast.message(mode === "lookfirst" ? "스타일리스트처럼 룩을 먼저 설계하고 쿠팡에서 찾는 중 — 2~4분" : "테마·자세·옷을 고르는 중 — 1~3분 걸려요")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "시작 실패")
    }
  }

  async function make(c: Collection) {
    try {
      const j = await jsonOrThrow(await fetch(`/api/insta/collections/${encodeURIComponent(c.id)}/make`, { method: "POST" }))
      setJob(j)
      toast.message("릴스를 만드는 중 — 10~15분 걸려요")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "시작 실패")
    }
  }

  const latest = rows[0]
  const planned = latest?.status === "planned" ? latest : null
  return (
    <section className="flex min-w-0 flex-col gap-3 rounded-xl border border-primary/30 bg-card p-4">
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center">
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <h2 className="text-sm font-semibold text-foreground">컬렉션 릴스</h2>
          <p className="text-xs text-muted-foreground">
            {running
              ? `${job?.step || "진행 중…"}${job?.n ? ` (${job?.done_looks ?? 0}/${job.n})` : ""}`
              : "먼저 테마·자세·옷을 미리 보고, 마음에 들면 01~05 컬렉션 릴스로 만들어요."}
          </p>
        </div>
        <button onClick={() => plan("lookfirst")} disabled={!ready || running}
          title="룩(색·실루엣)을 먼저 설계하고 쿠팡에서 비슷한 옷을 찾아 흰 스튜디오 전신으로 — 실험"
          className="flex min-h-[44px] shrink-0 items-center justify-center gap-2 rounded-lg border border-primary/40 bg-background px-4 text-sm font-medium text-foreground hover:bg-primary/10 disabled:opacity-50">
          실험: 스튜디오 룩북
        </button>
        <button onClick={() => plan()} disabled={!ready || running}
          className={`flex min-h-[44px] shrink-0 items-center justify-center gap-2 rounded-lg px-5 text-sm font-semibold disabled:opacity-50 ${planned ? "border border-border bg-background text-foreground hover:border-primary/40" : "bg-primary text-primary-foreground hover:bg-primary/90"}`}>
          {running ? <Loader2 className="h-4 w-4 animate-spin" /> : planned ? <RefreshCw className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          {running ? "진행 중…" : planned ? "다른 기획 보기" : "기획 미리보기"}
        </button>
      </div>

      {planned && !running && (
        <div className="flex min-w-0 flex-col gap-3 rounded-lg border border-border bg-background p-3">
          <div className="flex min-w-0 flex-col gap-0.5">
            <div className="text-sm font-semibold text-foreground">{planned.theme?.concept || planned.theme?.zip}</div>
            {planned.theme?.title_ko && <p className="text-xs text-muted-foreground">표지: 코디 저장소 · {planned.theme.zip} — 캡션: {planned.theme.title_ko.join(" ")}</p>}
            <p className="text-xs text-muted-foreground">룩마다 다른 포즈·장소·코디예요. 하나가 실패하면 예비 코디로 대신 만들어 최소 4룩을 채워요.</p>
          </div>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
            {planned.looks.filter((lk) => !lk.spare).map((lk) => (
              <div key={lk.n} className="flex min-w-0 flex-col gap-1">
                {lk.product_image ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={lk.product_image} alt={lk.product?.name ?? ""} onClick={() => setZoom({ src: lk.product_image!, caption: lk.product?.name ?? "" })}
                    className="aspect-square w-full cursor-zoom-in rounded-md bg-secondary object-cover" />
                ) : <div className="aspect-square w-full rounded-md bg-secondary" />}
                <span className="text-[11px] font-medium text-foreground">{String(lk.n).padStart(2, "0")}</span>
                {lk.idea ? <span className="line-clamp-2 text-[11px] text-primary">{lk.idea}</span>
                  : lk.scene && <span className="line-clamp-2 text-[11px] text-primary">{lk.scene.location_ko} · {lk.scene.pose_ko}</span>}
                <span className="line-clamp-2 text-[11px] text-muted-foreground">{lk.product?.name ?? ""}</span>
                {lk.product?.price ? <span className="text-[11px] text-muted-foreground">{lk.product.price.toLocaleString("ko-KR")}원</span> : null}
                {(lk.items?.length ?? 0) > 0 && (
                  <span className="line-clamp-2 text-[10px] text-muted-foreground">+ {lk.items!.map((b) => b.name).filter(Boolean).join(" · ")}</span>
                )}
              </div>
            ))}
          </div>
          {(planned.base_items?.length ?? 0) > 0 && (
            <p className="text-xs text-muted-foreground">모든 룩에 같이 입는 옷: {planned.base_items!.map((b) => b.name).filter(Boolean).join(" · ")}</p>
          )}
          <button onClick={() => make(planned)} disabled={!ready || running}
            className="flex min-h-[44px] items-center justify-center gap-2 rounded-lg bg-primary px-5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
            <Clapperboard className="h-4 w-4" /> 이대로 릴스 만들기 · 약 400~700원 · 10~15분
          </button>
        </div>
      )}

      {latest && !planned && (
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
              {latest.theme?.concept || latest.theme?.zip || "컬렉션"}
              {latest.cost_usd ? <span className="ml-2 text-xs font-normal text-muted-foreground">약 {Math.round(latest.cost_usd * 1400).toLocaleString("ko-KR")}원</span> : null}
            </div>
            {latest.theme?.title_ko && <p className="text-xs text-muted-foreground">{latest.theme.title_ko.join(" ")}</p>}
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
              {latest.looks.map((lk) => (
                <div key={lk.n} className="flex min-w-0 flex-col gap-1">
                  {lk.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={lk.image_url} alt={`Look ${lk.n}`} onClick={() => setZoom({ src: lk.image_url!, caption: `${String(lk.n).padStart(2, "0")} · ${lk.product?.name ?? ""}` })}
                      className="aspect-[9/16] w-full cursor-zoom-in rounded-md object-cover" />
                  ) : <div className="aspect-[9/16] w-full rounded-md bg-secondary" />}
                  <span className="truncate text-[11px] text-muted-foreground">{String(lk.n).padStart(2, "0")} · {lk.product?.name ?? ""}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {zoom && (
        <div role="dialog" aria-modal="true" onClick={() => setZoom(null)}
          className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-black/85 p-4">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={zoom.src} alt={zoom.caption} className="max-h-[85vh] max-w-full rounded-lg object-contain" />
          <p className="max-w-full truncate text-xs text-white/80">{zoom.caption} · 눌러서 닫기</p>
        </div>
      )}
    </section>
  )
}
