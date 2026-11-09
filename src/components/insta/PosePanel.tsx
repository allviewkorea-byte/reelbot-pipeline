"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import { ChevronDown, Loader2, X } from "lucide-react"
import { jsonOrThrow } from "@/components/studio/studio-lib"
import { useFold } from "@/components/insta/useFold"

// 포즈 라이브러리 — 착장 생성 때 포즈 참고 이미지(얼굴 없는 회색 마네킹 선화)를 같이 넣는다.
// 무엇을 쓸지는 대표가 고른다: 사용 켜기/끄기 · 카테고리 · 각도 · 포즈별 빼기(사진 길게 보기 → 빼기).
// 이미지는 작가 사이트 원본을 그대로 보여 준다(우리 쪽에 저장·재배포 안 함).

interface Angle { angle: string; ko: string; url: string }
interface Pose { key: string; id: string; series: number; cat_key: string; ko: string; zh: string; excluded: boolean; angles: Angle[] }
interface Cat { key: string; series: number; series_ko: string; cat: string; ko: string; count: number; enabled: boolean }
interface Settings { enabled: boolean; cats: string[]; angles: string[]; excluded: string[] }
interface Listing {
  source: string; credit: string; settings: Settings; angles: { angle: string; ko: string }[]
  categories: Cat[]; poses: Pose[]; translated: number; total: number
}

const PAGE = 24

export function PosePanel() {
  const [open, toggle] = useFold("insta-poses", false)
  const [data, setData] = useState<Listing | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [view, setView] = useState<string | null>(null) // 보고 있는 카테고리
  const [limit, setLimit] = useState(PAGE)
  const [zoom, setZoom] = useState<Pose | null>(null)

  const load = useCallback(
    () => fetch("/api/insta/poses", { cache: "no-store" }).then(jsonOrThrow)
      .then((d: Listing) => { setErr(null); setData(d) })
      .catch((e) => setErr(e instanceof Error ? e.message : "포즈 목록을 못 불러왔어요")),
    [],
  )

  useEffect(() => {
    if (open && !data) load()
  }, [open, data, load])

  async function save(patch: Partial<Settings>) {
    if (!data) return
    setSaving(true)
    try {
      const s: Settings = await jsonOrThrow(await fetch("/api/insta/poses/settings", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch),
      }))
      setData({
        ...data, settings: s,
        categories: data.categories.map((c) => ({ ...c, enabled: s.cats.includes(c.key) })),
        poses: data.poses.map((p) => ({ ...p, excluded: s.excluded.includes(p.key) })),
      })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "저장하지 못했어요")
    } finally {
      setSaving(false)
    }
  }

  const st = data?.settings
  const toggleIn = (list: string[], v: string) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v])
  const shown = useMemo(() => (data?.poses ?? []).filter((p) => !view || p.cat_key === view), [data, view])
  const usable = useMemo(() => {
    if (!data || !st) return 0
    return data.poses.filter((p) => st.cats.includes(p.cat_key) && !p.excluded && p.angles.some((a) => st.angles.includes(a.angle))).length
  }, [data, st])
  const series = useMemo(() => {
    const m = new Map<string, Cat[]>()
    for (const c of data?.categories ?? []) m.set(c.series_ko, [...(m.get(c.series_ko) ?? []), c])
    return [...m.entries()]
  }, [data])
  const thumb = (p: Pose) => (p.angles.find((a) => a.angle === "正面") ?? p.angles[0])?.url

  return (
    <section className="flex min-w-0 flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <button onClick={toggle} className="flex items-center gap-1 text-sm font-semibold text-foreground">
          포즈 라이브러리 <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
        </button>
        {st && (
          <span className={`text-[11px] ${st.enabled ? "text-emerald-400" : "text-muted-foreground"}`}>
            {st.enabled ? `사용 중 · 후보 ${usable}개` : "꺼짐"}
          </span>
        )}
        {st && (
          <button onClick={() => save({ enabled: !st.enabled })} disabled={saving}
            className={`ml-auto flex min-h-[36px] items-center gap-1.5 rounded-lg border px-3 text-xs font-medium disabled:opacity-50 ${
              st.enabled ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300" : "border-border bg-background text-foreground hover:border-primary/40"}`}>
            {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />} {st.enabled ? "착장에 사용 중" : "착장에 사용하기"}
          </button>
        )}
      </div>

      {!open ? null : err ? (
        <p className="text-xs text-red-400">{err} <button onClick={load} className="underline">다시</button></p>
      ) : !data || !st ? (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin" /> 포즈 목록 불러오는 중…</p>
      ) : (
        <div className="flex min-w-0 flex-col gap-3">
          <p className="text-[11px] text-muted-foreground">
            켜 둔 카테고리·각도 중에서 착장마다 1개를 골라 참고 이미지로 넣어요(최근 쓴 10개는 피함). 사진을 누르면 크게 보고 뺄 수 있어요.
          </p>

          {series.map(([name, cats]) => (
            <div key={name} className="flex min-w-0 flex-col gap-1.5">
              <p className="text-[11px] font-medium text-muted-foreground">{name}</p>
              <div className="flex flex-wrap gap-1.5">
                {cats.map((c) => (
                  <span key={c.key} className="flex items-center overflow-hidden rounded-full border border-border text-[11px]">
                    <button onClick={() => save({ cats: toggleIn(st.cats, c.key) })} disabled={saving}
                      className={`px-2.5 py-1 ${c.enabled ? "bg-primary/20 text-primary" : "text-muted-foreground"}`}>
                      {c.enabled ? "✓ " : ""}{c.ko} {c.count}
                    </button>
                    <button onClick={() => { setView(view === c.key ? null : c.key); setLimit(PAGE) }}
                      className={`border-l border-border px-2 py-1 ${view === c.key ? "bg-secondary text-foreground" : "text-muted-foreground"}`}>
                      보기
                    </button>
                  </span>
                ))}
              </div>
            </div>
          ))}

          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] font-medium text-muted-foreground">각도</span>
            {data.angles.map((a) => (
              <button key={a.angle} onClick={() => save({ angles: toggleIn(st.angles, a.angle) })} disabled={saving}
                className={`rounded-full border border-border px-2.5 py-1 text-[11px] ${st.angles.includes(a.angle) ? "bg-primary/20 text-primary" : "text-muted-foreground"}`}>
                {st.angles.includes(a.angle) ? "✓ " : ""}{a.ko}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <p className="text-xs font-medium text-foreground">{view ? data.categories.find((c) => c.key === view)?.ko : "전체"} {shown.length}개</p>
            {view && <button onClick={() => setView(null)} className="text-[11px] text-muted-foreground underline">전체 보기</button>}
            {data.translated < data.total && <span className="text-[11px] text-muted-foreground">설명 번역 중 {data.translated}/{data.total}</span>}
          </div>
          <div className="grid min-w-0 grid-cols-3 gap-2 lg:grid-cols-6">
            {shown.slice(0, limit).map((p) => (
              <button key={p.key} onClick={() => setZoom(p)}
                className={`relative flex min-w-0 flex-col gap-1 rounded-lg border bg-background p-1 text-left ${p.excluded ? "border-red-500/40 opacity-40" : "border-border"}`}>
                <div className="aspect-[3/4] overflow-hidden rounded-md bg-white">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={thumb(p)} alt={p.ko} loading="lazy" className="h-full w-full object-contain" />
                </div>
                <p className="truncate text-[10px] text-muted-foreground">{p.ko}</p>
                {p.excluded && <span className="absolute left-1.5 top-1.5 rounded bg-red-600 px-1 text-[10px] text-white">뺌</span>}
              </button>
            ))}
          </div>
          {shown.length > limit && (
            <button onClick={() => setLimit(limit + PAGE * 2)} className="self-center rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground">
              더 보기 ({shown.length - limit}개 남음)
            </button>
          )}
          <p className="text-[10px] text-muted-foreground">
            출처: <a href={data.source} target="_blank" rel="noreferrer" className="underline">{data.credit}</a> · 이미지 재배포 금지
          </p>
        </div>
      )}

      {zoom && st && (
        <div className="fixed inset-0 z-50 flex flex-col bg-black/90 p-4" onClick={() => setZoom(null)}>
          <div className="flex items-center gap-2 text-white" onClick={(e) => e.stopPropagation()}>
            <p className="min-w-0 flex-1 truncate text-sm">{zoom.ko}</p>
            <button onClick={() => { const ex = toggleIn(st.excluded, zoom.key); save({ excluded: ex }); setZoom({ ...zoom, excluded: !zoom.excluded }) }}
              className={`rounded-lg border px-3 py-1.5 text-xs ${zoom.excluded ? "border-emerald-400 text-emerald-300" : "border-red-400 text-red-300"}`}>
              {zoom.excluded ? "다시 쓰기" : "이 포즈 빼기"}
            </button>
            <button onClick={() => setZoom(null)} aria-label="닫기" className="p-1"><X className="h-5 w-5" /></button>
          </div>
          <div className="mt-3 grid min-h-0 flex-1 grid-cols-2 gap-2 overflow-y-auto sm:grid-cols-5" onClick={(e) => e.stopPropagation()}>
            {zoom.angles.map((a) => (
              <div key={a.angle} className="flex flex-col gap-1">
                <div className="aspect-[3/4] overflow-hidden rounded-md bg-white">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={a.url} alt={`${zoom.ko} ${a.ko}`} className="h-full w-full object-contain" />
                </div>
                <p className={`text-center text-[11px] ${st.angles.includes(a.angle) ? "text-primary" : "text-white/50"}`}>{a.ko}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
