"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { Download, Loader2, Plus, Sparkles, UserRound, X } from "lucide-react"
import { CHANNELS, channelName, jsonOrThrow, type OverviewCharacter, type ShortsCast } from "./studio-lib"

// 스튜디오 첫 화면 — 채널별 캐릭터 목록. 카드 → /studio?character=<id>. "캐릭터 추가"(채널 → 이름·설명 →
// 얼굴 후보). 운동 채널은 쇼츠 캐스트를 스튜디오로 "가져오기"(복사만, 쇼츠 원본·제작 코드는 그대로).

interface Group { channel_id: string; characters: OverviewCharacter[] }

function Face({ url, name }: { url: string | null; name: string }) {
  return (
    <div className="flex h-24 w-20 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-secondary/40">
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt={name} className="h-full w-full object-cover" />
      ) : (
        <UserRound className="h-7 w-7 text-muted-foreground/40" />
      )}
    </div>
  )
}

function AddCharacter({ defaultChannel, onClose }: { defaultChannel: string; onClose: () => void }) {
  const router = useRouter()
  const [channel, setChannel] = useState(defaultChannel)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [busy, setBusy] = useState(false)

  async function submit() {
    setBusy(true)
    try {
      const d = await jsonOrThrow(await fetch("/api/studio/create", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, description, channel_id: channel }),
      }))
      toast.success("얼굴 사진을 만들고 있어요")
      router.push(`/studio?character=${encodeURIComponent(d.character.id)}${d.job?.id ? `&job=${encodeURIComponent(d.job.id)}` : ""}`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "만들지 못했어요")
      setBusy(false)
    }
  }

  return (
    <div className="flex min-w-0 flex-col gap-3 rounded-xl border border-primary/30 bg-card p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-foreground">새 캐릭터</h2>
        <button onClick={onClose} aria-label="닫기" className="text-muted-foreground hover:text-foreground"><X className="h-5 w-5" /></button>
      </div>
      <label className="flex flex-col gap-1 text-xs text-muted-foreground">
        어느 채널 캐릭터인가요?
        <select value={channel} onChange={(e) => setChannel(e.target.value)} className="w-full min-w-0 rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground">
          {CHANNELS.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-xs text-muted-foreground">
        이름
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="예: 채이" className="w-full min-w-0 rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground" />
      </label>
      <label className="flex flex-col gap-1 text-xs text-muted-foreground">
        어떤 사람인가요?
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3}
          placeholder="예: 서울 사는 24살 직장인, 긴 흑발, 172cm"
          className="w-full min-w-0 resize-y rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground" />
      </label>
      <button onClick={submit} disabled={busy || !name.trim() || description.trim().length < 5}
        className="flex min-h-[44px] items-center justify-center gap-1.5 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} 얼굴 사진 만들기
      </button>
    </div>
  )
}

export function StudioHome() {
  const router = useRouter()
  const [groups, setGroups] = useState<Group[] | null>(null)
  const [shorts, setShorts] = useState<ShortsCast[]>([])
  const [adding, setAdding] = useState<string | null>(null)
  const [importing, setImporting] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(
    () =>
      Promise.all([
        fetch("/api/studio/overview", { cache: "no-store" }).then(jsonOrThrow).then((d) => setGroups(d.channels ?? [])),
        fetch("/api/studio/shorts-cast?channel=workout_music", { cache: "no-store" }).then(jsonOrThrow)
          .then((d) => setShorts(d.cast ?? [])).catch(() => setShorts([])),
      ]).catch((e) => setError(e instanceof Error ? e.message : "불러오지 못했어요")),
    [],
  )

  useEffect(() => {
    load()
  }, [load])

  async function importShorts(role: string) {
    setImporting(role)
    try {
      const c = await jsonOrThrow(await fetch("/api/studio/import-shorts", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ channel: "workout_music", role }),
      }))
      toast.success("가져왔어요")
      router.push(`/studio?character=${encodeURIComponent(c.id)}`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "가져오지 못했어요")
      setImporting(null)
    }
  }

  // 알려진 채널은 비어 있어도 보여 주고, 그 밖의 채널은 뒤에 붙인다.
  const byId = new Map((groups ?? []).map((g) => [g.channel_id, g.characters]))
  const ordered = [
    ...CHANNELS.map((c) => ({ channel_id: c.id, characters: byId.get(c.id) ?? [] })),
    ...(groups ?? []).filter((g) => !CHANNELS.some((c) => c.id === g.channel_id)),
  ]

  return (
    <div className="flex h-full min-h-0 w-full min-w-0 flex-col gap-5 overflow-auto p-4 md:p-6">
      <div className="flex min-w-0 flex-wrap items-center gap-3 pl-10 md:pl-0">
        <UserRound className="h-6 w-6 shrink-0 text-primary" />
        <h1 className="text-xl font-semibold text-foreground">캐릭터 스튜디오</h1>
        <button onClick={() => setAdding(CHANNELS[0].id)}
          className="ml-auto flex min-h-[40px] items-center gap-1.5 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90">
          <Plus className="h-4 w-4" /> 캐릭터 추가
        </button>
      </div>

      {adding && <AddCharacter defaultChannel={adding} onClose={() => setAdding(null)} />}
      {error && <div className="rounded-xl border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-400">{error}</div>}
      {!groups && !error && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> 불러오는 중…</div>
      )}

      {groups && ordered.map((g) => {
        const importable = g.channel_id === "workout_music" ? shorts.filter((s) => !s.imported_id) : []
        return (
          <section key={g.channel_id || "none"} className="flex min-w-0 flex-col gap-3 rounded-xl border border-border bg-card p-4">
            <div className="flex min-w-0 items-center gap-2">
              <h2 className="text-base font-semibold text-foreground">{channelName(g.channel_id)}</h2>
              <span className="text-xs text-muted-foreground">{g.characters.length}명</span>
            </div>
            <div className="grid min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {g.characters.map((c) => (
                <Link key={c.id} href={`/studio?character=${encodeURIComponent(c.id)}`}
                  className="flex min-w-0 items-center gap-3 rounded-xl border border-border bg-background p-3 transition-colors hover:border-primary/40">
                  <Face url={c.face_url} name={c.name} />
                  <div className="min-w-0">
                    <p className="truncate text-base font-medium text-foreground">{c.name}</p>
                    <p className={`mt-1 flex items-center gap-1.5 text-xs ${c.ready ? "text-emerald-400" : "text-amber-400"}`}>
                      <span className={`h-1.5 w-1.5 rounded-full ${c.ready ? "bg-emerald-500" : "bg-amber-400"}`} />
                      {c.ready ? "준비 완료" : "사진이 더 필요해요"}
                    </p>
                  </div>
                </Link>
              ))}
              {importable.map((s) => (
                <div key={s.role} className="flex min-w-0 items-center gap-3 rounded-xl border border-dashed border-border bg-background p-3">
                  <Face url={s.face_url} name={s.name} />
                  <div className="flex min-w-0 flex-col gap-2">
                    <p className="truncate text-base font-medium text-foreground">{s.name}</p>
                    <button onClick={() => importShorts(s.role)} disabled={importing !== null}
                      className="flex min-h-[36px] items-center gap-1.5 self-start rounded-lg border border-border px-3 text-xs font-medium text-foreground hover:border-primary/40 disabled:opacity-50">
                      {importing === s.role ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />} 쇼츠에서 가져오기
                    </button>
                  </div>
                </div>
              ))}
              <button onClick={() => setAdding(g.channel_id || CHANNELS[0].id)}
                className="flex min-h-[120px] min-w-0 items-center justify-center gap-2 rounded-xl border border-dashed border-border text-sm text-muted-foreground hover:border-primary/40 hover:text-foreground">
                <Plus className="h-4 w-4" /> 캐릭터 추가
              </button>
            </div>
          </section>
        )
      })}
    </div>
  )
}
