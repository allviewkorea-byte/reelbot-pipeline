"use client"

import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { ExternalLink, Loader2, ShoppingBag } from "lucide-react"
import { jsonOrThrow } from "@/components/studio/studio-lib"

// 상품 픽(A2-2) — 레퍼런스 룩 → 쿠팡·네이버에서 아이템마다 1등 + 예비 2개. 예비 사진을 누르면 교체.
// 초보자 화면: 사진·이름·가격·몰만. 점수·검색어는 숨김. (A2-3 에서 "오늘의 코디 찾기" 한 번에 흐름으로 합친다)

interface Prod { id: number | null; channel: "coupang" | "naver"; name: string; price: number | null; mall: string | null; image: string | null; link: string | null; affiliate_link: string | null }
interface Item { index: number; kind: string; pick: Prod | null; backups: Prod[]; notes: string[] }
interface Look { id: string; concept: string | null; status: string; items: Item[]; ref_video_id: string | null; error: string | null }
interface Status { connected: { coupang: boolean; naver: boolean } }
interface Job { id: string; state: "queued" | "running" | "done" | "failed"; error: string | null }

const KIND_KO: Record<string, string> = { top: "상의", bottoms: "하의", dress: "원피스", outerwear: "아우터", shoes: "신발", bag: "가방", accessory: "액세서리" }

function won(n: number | null) {
  return n ? `${n.toLocaleString("ko-KR")}원` : ""
}

export function PicksPanel() {
  const [looks, setLooks] = useState<Look[]>([])
  const [status, setStatus] = useState<Status | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [swapping, setSwapping] = useState<string | null>(null)

  const load = useCallback(
    () => Promise.all([
      fetch("/api/insta/looks", { cache: "no-store" }).then(jsonOrThrow).then((d) => setLooks(d.looks ?? [])),
      fetch("/api/insta/shopping/status", { cache: "no-store" }).then(jsonOrThrow).then(setStatus),
    ]).catch(() => {}),
    [],
  )

  useEffect(() => {
    load()
  }, [load])

  const running = job?.state === "queued" || job?.state === "running"
  const jobId = job?.id
  useEffect(() => {
    if (!jobId || !running) return
    const t = setInterval(async () => {
      try {
        const j: Job = await jsonOrThrow(await fetch(`/api/insta/looks/jobs/${encodeURIComponent(jobId)}`, { cache: "no-store" }))
        setJob(j)
        if (j.state === "done" || j.state === "failed") {
          await load()
          if (j.state === "done") toast.success("상품을 골랐어요")
          else toast.error(j.error || "상품을 고르지 못했어요")
        }
      } catch {
        /* 다음 폴링 */
      }
    }, 3000)
    return () => clearInterval(t)
  }, [jobId, running, load])

  async function pick() {
    try {
      setJob(await jsonOrThrow(await fetch("/api/insta/looks/pick", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })))
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "시작하지 못했어요")
    }
  }

  async function swap(look: Look, item: Item, p: Prod) {
    if (p.id == null) return
    setSwapping(`${look.id}:${item.index}`)
    try {
      await jsonOrThrow(await fetch(`/api/insta/looks/${encodeURIComponent(look.id)}/swap`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ item_index: item.index, product_id: p.id }),
      }))
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "교체하지 못했어요")
    } finally {
      setSwapping(null)
    }
  }

  const look = looks[0]
  const conn = status?.connected
  const none = conn && !conn.coupang && !conn.naver

  return (
    <section className="flex min-w-0 flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold text-foreground">상품 고르기</h2>
        {conn && (
          <span className="flex gap-1.5 text-[11px]">
            <span className={conn.coupang ? "text-emerald-400" : "text-amber-400"}>쿠팡 {conn.coupang ? "연결됨" : "연결 필요"}</span>
            <span className="text-muted-foreground">·</span>
            <span className={conn.naver ? "text-emerald-400" : "text-amber-400"}>네이버 {conn.naver ? "연결됨" : "연결 필요"}</span>
          </span>
        )}
        <button onClick={pick} disabled={running || !!none}
          className="ml-auto flex min-h-[36px] items-center gap-1.5 rounded-lg border border-border bg-background px-3 text-xs font-medium text-foreground hover:border-primary/40 disabled:opacity-50">
          {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShoppingBag className="h-3.5 w-3.5" />} {running ? "고르는 중…" : "상품 고르기"}
        </button>
      </div>

      {!look ? (
        <p className="text-xs text-muted-foreground">레퍼런스를 모은 뒤 상품 고르기를 눌러 주세요.</p>
      ) : (
        <div className="flex min-w-0 flex-col gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <p className="truncate text-sm font-medium text-foreground">{look.concept ?? "코디"}</p>
            {look.ref_video_id && (
              <a href={`https://www.youtube.com/watch?v=${look.ref_video_id}`} target="_blank" rel="noreferrer"
                className="flex shrink-0 items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground">
                <ExternalLink className="h-3 w-3" /> 참고한 영상
              </a>
            )}
            {look.status === "picking" && <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />}
          </div>
          {look.status === "failed" && <p className="text-xs text-red-400">{look.error ?? "상품을 고르지 못했어요"}</p>}
          <div className="grid min-w-0 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {(look.items ?? []).map((it) => (
              <div key={it.index} className="flex min-w-0 flex-col gap-2 rounded-lg border border-border bg-background p-2">
                <p className="text-xs font-medium text-muted-foreground">{KIND_KO[it.kind] ?? it.kind}</p>
                {it.pick ? (
                  <a href={it.pick.affiliate_link || it.pick.link || "#"} target="_blank" rel="noreferrer" className="flex min-w-0 flex-col gap-1">
                    <div className="aspect-square overflow-hidden rounded-md bg-secondary/30">
                      {it.pick.image && (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={it.pick.image} alt={it.pick.name} className="h-full w-full object-contain" />
                      )}
                    </div>
                    <span className="line-clamp-2 text-xs text-foreground">{it.pick.name}</span>
                    <span className="text-xs font-semibold text-foreground">{won(it.pick.price)} <span className="font-normal text-muted-foreground">· {it.pick.mall}</span></span>
                  </a>
                ) : (
                  <p className="text-xs text-amber-400">{it.notes?.at(-1) ?? "맞는 상품을 못 찾았어요"}</p>
                )}
                {it.backups.length > 0 && (
                  <div className="flex min-w-0 flex-col gap-1">
                    <p className="text-[11px] text-muted-foreground">다른 후보 — 누르면 바꿔요</p>
                    <div className="flex gap-1.5">
                      {it.backups.map((b) => (
                        <button key={`${b.channel}-${b.id}`} onClick={() => swap(look, it, b)} disabled={swapping !== null} title={`${b.name} · ${won(b.price)}`}
                          className="relative h-14 w-14 shrink-0 overflow-hidden rounded-md border border-border bg-secondary/30 hover:border-primary/60 disabled:opacity-50">
                          {b.image && (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img src={b.image} alt="" className="h-full w-full object-contain" />
                          )}
                          {swapping === `${look.id}:${it.index}` && <span className="absolute inset-0 flex items-center justify-center bg-background/60"><Loader2 className="h-3.5 w-3.5 animate-spin" /></span>}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
