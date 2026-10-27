"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import { ChevronDown, ExternalLink, ImagePlus, Loader2, Search } from "lucide-react"
import { prepareFile } from "@/components/shorts/FamilyCastPanel"
import { jsonOrThrow } from "@/components/studio/studio-lib"
import { useFold } from "@/components/insta/useFold"

// 오늘의 레퍼런스(A2-1) — 유튜브 코디 영상 썸네일 + AI 가 읽은 컨셉 이름. 참고용(결과물에 그대로 쓰지 않음).
// "레퍼런스 모으기" = 오늘 검색어로 수집(하루 1회, 이미 했으면 분석만) → 백그라운드, 5초마다 다시 읽는다.
// "스크린샷 넣기"(A2-3a) = 대표가 본 코디 캡처 1장 → 같은 분석 → 상품 고르기에 쓰임. 분석용 보관만, 게시물엔 안 씀.
// 남성·명품 토크·전신 착장 없음은 "참고 안 함"(흐리게, 상품 고르기에서 빠짐).

interface Look { concept: string }
interface RefRow {
  video_id: string; title: string; thumb_url: string | null; video_url: string | null; views: number | null
  source?: "youtube" | "screenshot"; usable?: boolean
  status: "new" | "analyzed" | "failed" | "used"; analysis: { looks?: Look[]; usable_reason?: string } | null
}
interface Usage { youtube: { units: number; cap: number }; has_youtube_key: boolean }

export function RefsPanel() {
  const [refs, setRefs] = useState<RefRow[]>([])
  const [running, setRunning] = useState(false)
  const [open, toggle] = useFold("insta-refs", false)
  const [usage, setUsage] = useState<Usage | null>(null)
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

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

  async function addScreenshot(file: File) {
    setUploading(true)
    try {
      const prepared = await prepareFile(file, 2048)
      const fd = new FormData()
      fd.append("file", prepared, prepared.name)
      const d = await jsonOrThrow(await fetch("/api/insta/refs/screenshot", { method: "POST", body: fd }))
      if (d.error) toast.error(`분석하지 못했어요 — ${d.error}`)
      else if (d.analysis?.usable === false) toast.message("참고하기 어려운 사진이에요(여성 전신 코디가 잘 보이는 사진이 좋아요)")
      else toast.success("스크린샷을 분석했어요 — 상품 고르기에 쓸 수 있어요")
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "올리지 못했어요")
    } finally {
      setUploading(false)
    }
  }

  return (
    <section className="flex min-w-0 flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <button onClick={toggle} className="flex items-center gap-1 text-sm font-semibold text-foreground">
          오늘의 레퍼런스 <span className="font-normal text-muted-foreground">{refs.length}</span>
          <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
        </button>
        {open && usage && (
          <span className="text-[11px] text-muted-foreground">
            {usage.has_youtube_key ? `유튜브 사용량 ${usage.youtube.units}/${usage.youtube.cap}` : "유튜브 연결 필요"}
          </span>
        )}
        <button onClick={() => fileRef.current?.click()} disabled={uploading}
          className="ml-auto flex min-h-[36px] items-center gap-1.5 rounded-lg border border-border bg-background px-3 text-xs font-medium text-foreground hover:border-primary/40 disabled:opacity-50">
          {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ImagePlus className="h-3.5 w-3.5" />} {uploading ? "분석 중…" : "스크린샷 넣기"}
        </button>
        <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) addScreenshot(f)
            e.target.value = ""
          }}
        />
        <button onClick={collect} disabled={running || (usage ? !usage.has_youtube_key : false)}
          className="flex min-h-[36px] items-center gap-1.5 rounded-lg border border-border bg-background px-3 text-xs font-medium text-foreground hover:border-primary/40 disabled:opacity-50">
          {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />} {running ? "찾는 중…" : "레퍼런스 모으기"}
        </button>
      </div>
      {!open ? null : refs.length === 0 ? (
        <p className="text-xs text-muted-foreground">아직 모은 레퍼런스가 없어요.</p>
      ) : (
        <div className="grid min-w-0 grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6">
          {refs.map((r) => {
            const looks = r.analysis?.looks ?? []
            const skip = r.usable === false
            const label = skip ? "참고 안 함" : looks.length ? looks.map((l) => l.concept).join(" · ") : r.status === "failed" ? "분석 못함" : "분석 대기"
            const body = (
              <>
                <div className={`aspect-video overflow-hidden rounded-md bg-secondary/30 ${skip ? "opacity-40" : ""}`}>
                  {r.thumb_url && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={r.thumb_url} alt="" className="h-full w-full object-cover" />
                  )}
                </div>
                <span className={`truncate text-[11px] font-medium ${skip ? "text-muted-foreground" : "text-foreground"}`}>{label}</span>
                <span className="flex items-center gap-1 truncate text-[10px] text-muted-foreground">
                  {r.video_url ? <><ExternalLink className="h-2.5 w-2.5 shrink-0" /> 참고한 영상</> : "스크린샷"}
                </span>
              </>
            )
            const cls = `flex min-w-0 flex-col gap-1 rounded-lg border border-border bg-background p-1.5 ${skip ? "opacity-60" : ""}`
            const tip = skip ? `${r.title} — ${r.analysis?.usable_reason || "참고하기 어려운 영상"}` : r.title
            return r.video_url ? (
              <a key={r.video_id} href={r.video_url} target="_blank" rel="noreferrer" title={tip} className={`${cls} hover:border-primary/40`}>{body}</a>
            ) : (
              <div key={r.video_id} title={tip} className={cls}>{body}</div>
            )
          })}
        </div>
      )}
    </section>
  )
}
