"use client"

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { toast } from "sonner"
import { ChevronDown, ImageIcon, Loader2, RefreshCw, Shirt, Sparkles, ThumbsDown, ThumbsUp, Upload, Wand2, X } from "lucide-react"
import { prepareFile } from "@/components/shorts/FamilyCastPanel"
import { CollectionPanel } from "@/components/insta/CollectionPanel"
import { CoordiProducts, HideButton, type CoordiLook } from "@/components/insta/CoordiProducts"
import { PicksPanel } from "@/components/insta/PicksPanel"
import { RefsPanel } from "@/components/insta/RefsPanel"
import { useFold } from "@/components/insta/useFold"
import { jsonOrThrow, usd, type View } from "@/components/studio/studio-lib"

// 착장 1장 만들기(테스트 화면, A1 — A4 에서 /insta 로 합침). 대표는 상품 사진 넣기 + 버튼만:
// 장면(요일·장소·포즈·헤어·아이웨어)·프롬프트는 시스템이 정한다. 생성 → AI 검수(최대 2회 재생성) →
// 폰카 후처리. 결과는 처리본 크게 + 원본 토글, 기획·검수·시도·비용, 다시 만들기, 최근 착장.
// 백엔드: /insta/*(insta_outfit.py · insta_outfit_plan.py). 캐릭터는 스튜디오 확정 기준 이미지(읽기만).
// A2-3a "내 상품으로 코디": 보세몰 상품 사진 + 링크(저장·표시만, 서버가 접속하지 않음) + 쇼핑몰·종류 →
// "이것만 입히기"(A1 그대로) 또는 "나머지 AI가 채우기"(빈 종류를 쿠팡에서 골라 함께 입힘, insta_coordi.py).
// 결과: 상품별 사진·이름·쇼핑몰·링크, 쿠팡 상품은 교체, 이 코디 좋아요/다른 코디/내리기, 이번 코디 비용.
// 캐릭터는 ?character= (스튜디오 "이 캐릭터로 착장 만들기"), 없으면 채이.

const DEFAULT_CHARACTER = "chaei"
const HTTPS_RE = /^https:\/\/[^\s/$.?#][^\s]*$/
const MAX_PRODUCTS = 4
const POLL_MS = 3000

interface Opt { value: string | number; label: string; cut?: string }
interface Options {
  weekdays: Opt[]; cuts: string[]; locations: Opt[]; poses: Opt[]; eyewear: Opt[]; kinds: Opt[]
  estimate: { per_image: number; min: number; max: number }
}
interface Product {
  slot: number
  preview: string
  state: "uploading" | "ready" | "error"
  key?: string
  kind: string
  desc?: string
  revealing?: boolean
  aiKind?: string | null
  error?: string
  link: string
  mall: string
}
interface Plan {
  weekday_ko: string; life: string; location_ko: string; pose_ko: string; cut: string; hair_role: string | null
  eyewear_ko: string | null; season_ko: string; reason: string; source: string; notes?: string[]
}
interface Review { pass?: boolean; violations?: { type: string; detail: string }[]; skipped?: string; history?: unknown[] }
interface Outfit {
  id: string; status: "generating" | "ok" | "review_failed" | "failed"; plan: Plan | Record<string, never>
  review: Review | null; attempts: number; cost_usd: number; error: string | null
  image_url: string | null; processed_url: string | null; created_at: string
  look_id?: string | null; look?: CoordiLook | null; decision?: "approved" | "rejected" | null; caption_note?: string | null
}
interface Cost { usd: number; krw: number }
// kind: coordi = 내 상품 코디 잡(/insta/coordi/jobs), outfit = 예전 다시 만들기 잡(/insta/outfit-jobs)
interface Job {
  id: string; kind: "coordi" | "outfit"; outfit_id: string | null; state: "queued" | "running" | "done" | "failed"; step: string
  attempts?: number; cost_usd?: number; error: string | null; cost?: Cost | null; notes?: string[]
}

const STATUS: Record<Outfit["status"], { label: string; cls: string }> = {
  ok: { label: "검수 통과", cls: "bg-emerald-500/15 text-emerald-400" },
  review_failed: { label: "검수 실패", cls: "bg-amber-500/10 text-amber-400" },
  failed: { label: "생성 실패", cls: "bg-red-500/10 text-red-400" },
  generating: { label: "생성 중", cls: "bg-primary/20 text-primary" },
}

function newBatch(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(5)), (b) => b.toString(16).padStart(2, "0")).join("")
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: Opt[] }) {
  return (
    <label className="flex min-w-0 flex-col gap-1 text-[11px] text-muted-foreground">
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)} className="w-full min-w-0 rounded-md border border-border bg-background px-1.5 py-1 text-xs text-foreground">
        <option value="">자동</option>
        {options.map((o) => (
          <option key={String(o.value)} value={String(o.value)}>{o.label}</option>
        ))}
      </select>
    </label>
  )
}

export default function InstaOutfitRoute() {
  return (
    <Suspense fallback={null}>
      <InstaOutfitPage />
    </Suspense>
  )
}

function linkError(link: string): string | undefined {
  return link.trim() && !HTTPS_RE.test(link.trim()) ? "https:// 로 시작하는 주소만 넣을 수 있어요" : undefined
}

function InstaOutfitPage() {
  const CHARACTER = (useSearchParams().get("character") || DEFAULT_CHARACTER).trim()
  const inputRef = useRef<HTMLInputElement>(null)
  const [opts, setOpts] = useState<Options | null>(null)
  const [character, setCharacter] = useState<View | null>(null)
  const [batch, setBatch] = useState(newBatch)
  const [products, setProducts] = useState<Product[]>([])
  const [choice, setChoice] = useState<Record<string, string>>({})
  const [showOpts, setShowOpts] = useState(false)
  const [mineOpen, toggleMine] = useFold("insta-mine", false)
  const [job, setJob] = useState<Job | null>(null)
  const [outfits, setOutfits] = useState<Outfit[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [showOriginal, setShowOriginal] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [measured, setMeasured] = useState<boolean | null>(null)
  const [coupang, setCoupang] = useState<boolean | null>(null)
  const [costs, setCosts] = useState<Record<string, Cost>>({})
  const [swapped, setSwapped] = useState<string | null>(null)

  const loadOutfits = useCallback(
    () => fetch(`/api/insta/outfits?character_id=${encodeURIComponent(CHARACTER)}`, { cache: "no-store" }).then(jsonOrThrow)
      .then((d) => setOutfits(d.outfits ?? [])).catch(() => {}),
    [CHARACTER],
  )

  useEffect(() => {
    fetch("/api/insta/outfit-options").then(jsonOrThrow).then(setOpts).catch(() => setOpts(null))
    fetch(`/api/studio/characters/${encodeURIComponent(CHARACTER)}`, { cache: "no-store" }).then(jsonOrThrow).then(setCharacter).catch(() => setCharacter(null))
    fetch(`/api/studio/characters/${encodeURIComponent(CHARACTER)}/measurements`, { cache: "no-store" }).then(jsonOrThrow)
      .then((d) => setMeasured(!!d.saved)).catch(() => setMeasured(null))
    fetch("/api/insta/shopping/status", { cache: "no-store" }).then(jsonOrThrow)
      .then((d) => setCoupang(!!d.connected?.coupang)).catch(() => setCoupang(null))
    loadOutfits()
  }, [loadOutfits, CHARACTER])

  const jobId = job?.id
  const jobKind = job?.kind
  const running = job?.state === "queued" || job?.state === "running"
  useEffect(() => {
    if (!jobId || !running) return
    const url = jobKind === "coordi" ? `/api/insta/coordi/jobs/${encodeURIComponent(jobId)}` : `/api/insta/outfit-jobs/${encodeURIComponent(jobId)}`
    const t = setInterval(async () => {
      try {
        const j: Job = { ...(await jsonOrThrow(await fetch(url, { cache: "no-store" }))), kind: jobKind }
        setJob(j)
        if (j.state === "done" || j.state === "failed") {
          await loadOutfits()
          if (j.outfit_id) {
            setSelected(j.outfit_id)
            const oid = j.outfit_id
            if (j.cost) setCosts((c) => ({ ...c, [oid]: j.cost as Cost }))
          }
          if (j.state === "done") toast.success("착장 완성")
          else toast.error(j.error || "생성 실패")
          ;(j.notes ?? []).forEach((n) => toast.message(n))
        }
      } catch {
        /* 일시 오류 — 다음 폴링에서 재시도 */
      }
    }, POLL_MS)
    return () => clearInterval(t)
  }, [jobId, jobKind, running, loadOutfits])

  const hairRoles = useMemo(
    () => (character?.roles ?? []).filter((r) => r.category === "hair" && r.confirmed).map((r) => ({ value: r.role, label: r.role })),
    [character],
  )
  const ready = !!character?.ready
  const current = outfits.find((o) => o.id === selected) ?? outfits[0] ?? null

  function update(slot: number, patch: Partial<Product>) {
    setProducts((prev) => prev.map((p) => (p.slot === slot ? { ...p, ...patch } : p)))
  }

  async function add(files: FileList | File[]) {
    const list = Array.from(files).filter((f) => /\.(png|jpe?g|webp)$/i.test(f.name))
    const used = new Set(products.map((p) => p.slot))
    const free = [0, 1, 2, 3].filter((n) => !used.has(n))
    if (list.length > free.length) toast.error(`상품 사진은 ${MAX_PRODUCTS}장까지예요`)
    const take = list.slice(0, free.length).map((file, i) => ({ file, slot: free[i] }))
    setProducts((prev) => [...prev, ...take.map(({ file, slot }) => ({ slot, preview: URL.createObjectURL(file), state: "uploading" as const, kind: "", link: "", mall: "" }))])
    // 한 장씩 순서대로(Vercel 4.5MB 본문 한도 — 묶어서 보내지 않는다).
    for (const { file, slot } of take) {
      try {
        const prepared = await prepareFile(file, 2048)
        const fd = new FormData()
        fd.append("file", prepared, prepared.name)
        fd.append("batch", batch)
        fd.append("n", String(slot))
        const d = await jsonOrThrow(await fetch("/api/insta/products", { method: "POST", body: fd }))
        update(slot, { state: "ready", key: d.key, kind: d.kind ?? "", aiKind: d.kind, desc: d.desc, revealing: d.revealing,
          error: d.suggest_error ? `AI 종류 추천 실패 — 직접 골라 주세요` : undefined })
      } catch (e) {
        update(slot, { state: "error", error: e instanceof Error ? e.message : "업로드 실패" })
      }
    }
  }

  function remove(slot: number) {
    setProducts((prev) => {
      const p = prev.find((x) => x.slot === slot)
      if (p) URL.revokeObjectURL(p.preview)
      return prev.filter((x) => x.slot !== slot)
    })
  }

  function reset() {
    products.forEach((p) => URL.revokeObjectURL(p.preview))
    setProducts([])
    setBatch(newBatch())
  }

  const usable = products.filter((p) => p.state === "ready")
  const canMake = ready && !running && usable.length > 0 && products.every((p) => p.state !== "uploading")
    && usable.every((p) => p.kind && !linkError(p.link))

  async function make(mode: "only" | "fill") {
    try {
      const body = {
        character_id: CHARACTER,
        mode,
        products: usable.map((p) => ({ key: p.key, kind: p.kind, desc: p.desc, revealing: p.revealing,
          link: p.link.trim() || undefined, mall: p.mall.trim() || undefined })),
        options: Object.fromEntries(Object.entries(choice).filter(([, v]) => v)),
      }
      const j = await jsonOrThrow(await fetch("/api/insta/coordi", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }))
      setJob({ ...j, kind: "coordi" })
      setSwapped(null)
      toast.message(mode === "fill" ? "나머지를 AI가 고르고 입히는 중 — 2~3분 걸려요" : "착장 만드는 중 — 1~2분 걸려요")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "시작 실패")
    }
  }

  // 오늘의 코디 찾기(완전 자동, 대표 입력 없음): 레퍼런스 → 쿠팡 픽 → 착장. 같은 잡 폴링(/insta/coordi/jobs).
  async function auto() {
    try {
      const j = await jsonOrThrow(await fetch("/api/insta/coordi/auto", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ character_id: CHARACTER }),
      }))
      setJob({ ...j, kind: "coordi" })
      setSwapped(null)
      toast.message(j.concept ? `「${j.concept}」 코디를 찾는 중 — 3~5분 걸려요` : "오늘의 코디를 찾는 중 — 3~5분 걸려요")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "시작 실패")
    }
  }

  async function remake(o: Outfit) {
    try {
      const coordi = !!o.look_id
      const url = coordi ? `/api/insta/coordi/${encodeURIComponent(o.id)}/remake` : `/api/insta/outfits/${encodeURIComponent(o.id)}/remake`
      const j = await jsonOrThrow(await fetch(url, { method: "POST" }))
      setJob({ ...j, kind: coordi ? "coordi" : "outfit" })
      setSwapped(null)
      toast.message("같은 상품으로 새 장면을 만드는 중")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "시작 실패")
    }
  }

  async function decide(o: Outfit, decision: "approved" | "rejected") {
    try {
      await jsonOrThrow(await fetch(`/api/insta/outfits/${encodeURIComponent(o.id)}/decision`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision }),
      }))
      await loadOutfits()
      toast.success(decision === "approved" ? "좋아요로 기록했어요" : "다른 코디로 기록했어요 — 다시 만들기나 교체를 해 보세요")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "기록하지 못했어요")
    }
  }

  async function hideOutfit(o: Outfit, reason: string) {
    try {
      await jsonOrThrow(await fetch(`/api/insta/outfits/${encodeURIComponent(o.id)}/hide`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason }),
      }))
      setSelected(null)
      await loadOutfits()
      toast.success("착장을 내렸어요 — 올리기 대상에서 빠져요")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "내리지 못했어요")
    }
  }

  const est = opts?.estimate
  const plan = (current?.plan ?? {}) as Partial<Plan>

  return (
    <div className="flex h-full min-h-0 w-full min-w-0 flex-col gap-3 overflow-auto p-4">
      <div className="flex min-w-0 flex-col gap-1 pl-10 md:pl-0">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <Shirt className="h-5 w-5 shrink-0 text-primary" />
          <h1 className="text-lg font-semibold text-foreground">인스타 쇼핑 · 착장 만들기</h1>
          <span className="rounded-full bg-secondary px-2 py-0.5 text-[11px] text-muted-foreground">테스트</span>
          {character && (
            <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${ready ? "bg-emerald-500/15 text-emerald-400" : "bg-amber-500/10 text-amber-400"}`}>
              {character.character.name} · {ready ? "준비 완료" : "준비 필요"}
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground">내 상품 사진과 링크를 넣고 버튼만 누르세요. 장소·포즈·헤어·아이웨어는 AI가 정해요.</p>
      </div>

      {/* 컬렉션 릴스(A3) — 메인 포맷(롤모델 @yxyxeon) */}
      <CollectionPanel character={CHARACTER} ready={ready} />

      {/* 오늘의 코디 찾기 — 완전 자동(2026-10-27 대표: 반자동 아님). 아래 "내 상품으로 코디"는 선택 기능. */}
      <section className="flex min-w-0 flex-col gap-2 rounded-xl border border-primary/30 bg-card p-4 sm:flex-row sm:items-center">
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <h2 className="text-sm font-semibold text-foreground">오늘의 코디 찾기</h2>
          <p className="text-xs text-muted-foreground">
            {running ? job?.step || "진행 중…" : "레퍼런스 룩을 골라 쿠팡에서 비슷한 옷을 찾고, 채이에게 입혀요. 누르기만 하면 돼요."}
          </p>
        </div>
        <button onClick={auto} disabled={!ready || running}
          className="flex min-h-[44px] shrink-0 items-center justify-center gap-2 rounded-lg bg-primary px-5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
          {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          {running ? "만드는 중…" : "오늘의 코디 찾기"}
        </button>
      </section>

      <RefsPanel />
      <PicksPanel />

      {character && !ready && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-400">
          캐릭터의 얼굴·체형이 아직 확정되지 않았어요. <Link href={`/studio?character=${CHARACTER}`} className="underline">캐릭터 스튜디오</Link>에서 먼저 확정해 주세요.
        </div>
      )}

      <div className="flex min-w-0 flex-col gap-3 rounded-xl border border-border bg-card p-3">
        <div className="flex min-w-0 items-center justify-between gap-2">
          <button onClick={toggleMine} className="flex items-center gap-1 text-sm font-semibold text-foreground">
            내 상품으로 코디 <span className="font-normal text-muted-foreground">(선택 · 1~{MAX_PRODUCTS}개)</span>
            <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${mineOpen ? "rotate-180" : ""}`} />
          </button>
          {mineOpen && products.length > 0 && (
            <button onClick={reset} disabled={running} className="text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-50">비우기</button>
          )}
        </div>
        {mineOpen && (<>
        {products.length < MAX_PRODUCTS && (
          <div
            role="button"
            tabIndex={0}
            onClick={() => inputRef.current?.click()}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault()
              setDragOver(true)
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragOver(false)
              if (e.dataTransfer.files?.length) add(e.dataTransfer.files)
            }}
            className={`flex min-h-[80px] cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border border-dashed px-3 py-3 text-center text-xs transition-colors ${
              dragOver ? "border-primary/60 bg-primary/5 text-foreground" : "border-border text-muted-foreground hover:border-primary/40"
            }`}
          >
            <Upload className="h-5 w-5" />
            <span>보세몰 상품 사진(상의·하의·원피스·신발·가방·아우터)을 끌어다 놓거나 눌러서 고르세요</span>
            <input ref={inputRef} type="file" multiple accept="image/png,image/jpeg,image/webp" className="hidden"
              onChange={(e) => {
                if (e.target.files?.length) add(e.target.files)
                e.target.value = ""
              }}
            />
          </div>
        )}
        {products.length > 0 && (
          <div className="grid min-w-0 grid-cols-2 gap-2 sm:grid-cols-4">
            {products.map((p) => (
              <div key={p.slot} className="flex min-w-0 flex-col gap-1 rounded-lg border border-border bg-background p-1.5">
                <div className="relative h-28 overflow-hidden rounded-md bg-secondary/30">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={p.preview} alt="상품" className="h-full w-full object-contain" />
                  {p.state === "uploading" && (
                    <span className="absolute inset-0 flex items-center justify-center bg-background/60"><Loader2 className="h-4 w-4 animate-spin text-primary" /></span>
                  )}
                  <button onClick={() => remove(p.slot)} disabled={running} aria-label="빼기" className="absolute right-1 top-1 rounded bg-background/80 p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-50">
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
                <select
                  value={p.kind}
                  disabled={p.state !== "ready" || running}
                  onChange={(e) => update(p.slot, { kind: e.target.value })}
                  title={p.desc}
                  className={`w-full min-w-0 rounded-md border bg-background px-1.5 py-1 text-xs text-foreground ${p.state === "ready" && !p.kind ? "border-amber-500/50" : "border-border"}`}
                >
                  <option value="">{p.state === "uploading" ? "AI가 보는 중…" : "종류 선택…"}</option>
                  {(opts?.kinds ?? []).map((k) => (
                    <option key={String(k.value)} value={String(k.value)}>{k.label}{p.aiKind === k.value ? " (AI)" : ""}</option>
                  ))}
                </select>
                <input value={p.link} onChange={(e) => update(p.slot, { link: e.target.value })} disabled={running} inputMode="url"
                  placeholder="상품 링크 https://…" aria-label="상품 링크"
                  className={`w-full min-w-0 rounded-md border bg-background px-1.5 py-1 text-xs text-foreground ${linkError(p.link) ? "border-red-500/50" : "border-border"}`} />
                <input value={p.mall} onChange={(e) => update(p.slot, { mall: e.target.value })} disabled={running}
                  placeholder="쇼핑몰(비우면 링크로 자동)" aria-label="쇼핑몰 이름"
                  className="w-full min-w-0 rounded-md border border-border bg-background px-1.5 py-1 text-xs text-foreground" />
                {linkError(p.link) && <p className="text-[10px] text-red-400">{linkError(p.link)}</p>}
                {p.error && <p className={`truncate text-[10px] ${p.state === "error" ? "text-red-400" : "text-amber-400"}`} title={p.error}>{p.error}</p>}
              </div>
            ))}
          </div>
        )}

        <button onClick={() => setShowOpts((v) => !v)} className="flex items-center gap-1 self-start text-[11px] text-muted-foreground hover:text-foreground">
          선택 입력(비우면 자동) <ChevronDown className={`h-3 w-3 transition-transform ${showOpts ? "rotate-180" : ""}`} />
        </button>
        {showOpts && opts && (
          <div className="grid min-w-0 grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            <Select label="요일·상황" value={choice.weekday ?? ""} onChange={(v) => setChoice((c) => ({ ...c, weekday: v }))} options={opts.weekdays} />
            <Select label="컷 종류" value={choice.cut ?? ""} onChange={(v) => setChoice((c) => ({ ...c, cut: v }))} options={opts.cuts.map((c) => ({ value: c, label: c }))} />
            <Select label="장소" value={choice.location ?? ""} onChange={(v) => setChoice((c) => ({ ...c, location: v }))} options={opts.locations} />
            <Select label="포즈" value={choice.pose ?? ""} onChange={(v) => setChoice((c) => ({ ...c, pose: v }))} options={opts.poses.filter((p) => !choice.cut || p.cut === choice.cut)} />
            <Select label="헤어" value={choice.hair ?? ""} onChange={(v) => setChoice((c) => ({ ...c, hair: v }))} options={hairRoles} />
            <Select label="아이웨어" value={choice.eyewear ?? ""} onChange={(v) => setChoice((c) => ({ ...c, eyewear: v }))} options={opts.eyewear} />
          </div>
        )}

        <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
          {est && !running && <span className="mr-auto text-[11px] text-muted-foreground">착장 1장 {usd(est.min)}~{usd(est.max)} + AI 검수</span>}
          {running && job && (
            <span className="mr-auto flex min-w-0 items-center gap-1 text-xs text-primary">
              <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" /> <span className="truncate">{job.step}{job.attempts ? ` · ${usd(job.cost_usd ?? 0)}` : ""}</span>
            </span>
          )}
          {measured === false ? (
            // 핏은 실측 치수로 계산 — 치수가 없으면 버튼 대신 안내(백엔드도 같은 이유로 거부)
            <Link href={`/studio?character=${CHARACTER}`}
              className="flex min-h-[36px] items-center rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 text-xs font-medium text-amber-400">
              치수를 먼저 입력해 주세요
            </Link>
          ) : (
            <>
              <button onClick={() => make("only")} disabled={!canMake}
                className="flex min-h-[44px] items-center gap-1.5 rounded-lg border border-primary/40 bg-background px-4 text-sm font-medium text-foreground hover:bg-primary/10 disabled:opacity-50">
                <Sparkles className="h-4 w-4 text-primary" /> 이것만 입히기
              </button>
              <button onClick={() => make("fill")} disabled={!canMake || coupang === false}
                title={coupang === false ? "쿠팡 연결이 필요해요" : "넣은 상품에 어울리는 하의·신발·가방 등을 AI가 쿠팡에서 골라 함께 입혀요"}
                className="flex min-h-[44px] items-center gap-1.5 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
                <Wand2 className="h-4 w-4" /> 나머지 AI가 채우기
              </button>
            </>
          )}
        </div>
        </>)}
      </div>

      {current && (
        <div className="grid min-w-0 gap-3 rounded-xl border border-border bg-card p-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
          <div className="flex min-w-0 flex-col gap-2">
            <div className="relative flex aspect-[9/16] max-h-[640px] w-full items-center justify-center overflow-hidden rounded-lg bg-secondary/30">
              {(showOriginal ? current.image_url : current.processed_url ?? current.image_url) ? (
                <a href={(showOriginal ? current.image_url : current.processed_url ?? current.image_url) ?? "#"} target="_blank" rel="noreferrer" className="h-full w-full">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={(showOriginal ? current.image_url : current.processed_url ?? current.image_url) ?? ""} alt="착장" className="h-full w-full object-contain" />
                </a>
              ) : current.status === "generating" ? (
                <Loader2 className="h-6 w-6 animate-spin text-primary" />
              ) : (
                <ImageIcon className="h-6 w-6 text-muted-foreground/30" />
              )}
            </div>
            {current.image_url && (
              <div className="flex items-center gap-1 self-center rounded-lg border border-border p-0.5 text-xs">
                {[false, true].map((orig) => (
                  <button key={String(orig)} onClick={() => setShowOriginal(orig)}
                    className={`rounded-md px-2.5 py-1 ${showOriginal === orig ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>
                    {orig ? "원본" : "처리본(폰카)"}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="flex min-w-0 flex-col gap-2 text-xs">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-full px-2.5 py-0.5 font-medium ${STATUS[current.status].cls}`}>{STATUS[current.status].label}</span>
              <span className="text-muted-foreground">
                {costs[current.id] ? `이번 코디 비용 약 ${costs[current.id].krw.toLocaleString("ko-KR")}원` : `시도 ${current.attempts}회 · ${usd(Number(current.cost_usd) || 0)}`}
              </span>
              <button onClick={() => remake(current)} disabled={running || !ready || current.status === "generating"}
                className="ml-auto flex min-h-[32px] items-center gap-1 rounded-lg border border-border bg-background px-2.5 font-medium text-foreground hover:border-primary/40 disabled:opacity-50">
                <RefreshCw className="h-3.5 w-3.5" /> 다시 만들기
              </button>
            </div>
            {current.status !== "generating" && (
              <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                <button onClick={() => decide(current, "approved")} disabled={running}
                  className={`flex min-h-[32px] items-center gap-1 rounded-lg border px-2.5 font-medium disabled:opacity-50 ${current.decision === "approved" ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-400" : "border-border bg-background text-foreground hover:border-emerald-500/40"}`}>
                  <ThumbsUp className="h-3.5 w-3.5" /> 이 코디 좋아요
                </button>
                <button onClick={() => decide(current, "rejected")} disabled={running}
                  className={`flex min-h-[32px] items-center gap-1 rounded-lg border px-2.5 font-medium disabled:opacity-50 ${current.decision === "rejected" ? "border-amber-500/50 bg-amber-500/10 text-amber-400" : "border-border bg-background text-foreground hover:border-amber-500/40"}`}>
                  <ThumbsDown className="h-3.5 w-3.5" /> 다른 코디
                </button>
                <span className="ml-auto"><HideButton label="착장 내리기" disabled={running} onHide={(r) => hideOutfit(current, r)} /></span>
              </div>
            )}
            {current.caption_note && <p className="text-[11px] text-muted-foreground">캡션 표기: {current.caption_note}</p>}
            {current.look && current.look.items?.length > 0 && (
              <div className="flex min-w-0 flex-col gap-2 rounded-lg border border-border bg-background/50 p-2">
                <CoordiProducts look={current.look} disabled={running}
                  onChanged={async (didSwap) => {
                    await loadOutfits()
                    if (didSwap) setSwapped(current.id)
                  }} />
                {swapped === current.id && (
                  <button onClick={() => remake(current)} disabled={running || !ready}
                    className="flex min-h-[36px] items-center justify-center gap-1.5 self-start rounded-lg bg-primary px-3 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
                    <RefreshCw className="h-3.5 w-3.5" /> 바뀐 상품으로 다시 입히기
                  </button>
                )}
              </div>
            )}
            {plan.location_ko && (
              <dl className="grid min-w-0 grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1">
                <dt className="text-muted-foreground">요일·상황</dt><dd className="text-foreground">{plan.weekday_ko} · {plan.life} · {plan.season_ko}</dd>
                <dt className="text-muted-foreground">장소</dt><dd className="text-foreground">{plan.location_ko}</dd>
                <dt className="text-muted-foreground">포즈</dt><dd className="text-foreground">{plan.pose_ko} ({plan.cut})</dd>
                <dt className="text-muted-foreground">헤어</dt><dd className="text-foreground">{plan.hair_role || "기본(헤어 이미지 없음)"}</dd>
                <dt className="text-muted-foreground">아이웨어</dt><dd className="text-foreground">{plan.eyewear_ko || "없음"}</dd>
                <dt className="text-muted-foreground">이유</dt><dd className="break-words text-foreground">{plan.reason}{plan.source === "random" ? " (AI 기획 실패 — 규칙 후보에서 선택)" : ""}</dd>
              </dl>
            )}
            {(plan.notes ?? []).map((n) => <p key={n} className="text-[11px] text-amber-400">{n}</p>)}
            {current.review && (
              <div className="flex min-w-0 flex-col gap-1 rounded-lg border border-border bg-background p-2">
                <p className="text-[11px] font-medium text-foreground">AI 검수</p>
                {current.review.skipped ? (
                  <p className="text-[11px] text-amber-400">{current.review.skipped}</p>
                ) : current.review.pass ? (
                  <p className="text-[11px] text-emerald-400">통과</p>
                ) : (
                  (current.review.violations ?? []).map((v, i) => (
                    <p key={i} className="break-words text-[11px] text-amber-400">{v.type} · {v.detail}</p>
                  ))
                )}
              </div>
            )}
            {current.error && <p className="break-words text-[11px] text-red-400">{current.error}</p>}
          </div>
        </div>
      )}

      {outfits.length > 0 && (
        <div className="flex min-w-0 flex-col gap-2 rounded-xl border border-border bg-card p-3">
          <h2 className="text-sm font-semibold text-foreground">최근 착장</h2>
          <div className="grid min-w-0 grid-cols-3 gap-2 sm:grid-cols-6">
            {outfits.map((o) => (
              <button key={o.id} onClick={() => setSelected(o.id)} title={`${STATUS[o.status].label} · ${o.id}`}
                className={`relative aspect-[9/16] overflow-hidden rounded-md border bg-secondary/30 ${current?.id === o.id ? "border-primary" : "border-border hover:border-primary/40"}`}>
                {o.processed_url || o.image_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={(o.processed_url || o.image_url) ?? ""} alt="" className="h-full w-full object-cover" />
                ) : (
                  <span className="flex h-full items-center justify-center">{o.status === "generating" ? <Loader2 className="h-4 w-4 animate-spin text-primary" /> : <ImageIcon className="h-4 w-4 text-muted-foreground/30" />}</span>
                )}
                <span className={`absolute bottom-1 left-1 rounded px-1 text-[9px] font-medium ${STATUS[o.status].cls}`}>{STATUS[o.status].label}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
