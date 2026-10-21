"use client"

import { Suspense, useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { toast } from "sonner"
import { ArrowLeft, AudioLines, Download, ExternalLink, Link2, Loader2, Music2, Play, Users } from "lucide-react"
import { WORKOUT_CHANNEL_ID, withChannel } from "@/lib/music"

// 쇼츠 hero — 형식 A '원테이크 괴력'. 자막·글자·끝 카드 없음, 목소리 없음.
// 테스트는 유튜브 업로드 없이 미리보기 두 버전(음악 없음 / 후렴 쾅) 비교.
// 쇼츠 → 채널 유입: '관련 동영상'은 API 로 못 붙여서, 연결할 플리 영상 링크 + 곡 위치를 크게 보여준다.

interface Run {
  id: string
  label?: string
  status: string
  created_at: string
  error?: string
  previews?: { sfx?: string; slam?: string }
  cost?: { kling_usd: number; kling_seconds: number; attempts: number; sfx_credits: number; cap_usd: number; stopped_by_cap?: boolean }
  review?: { pass?: boolean; reasons?: string[] }
  impact?: { t: number; guessed: boolean }
  sync?: { crack_err_ms?: number }
  related?: { youtube_url: string; link: string; mmss: string }
  song?: { title?: string; bpm?: number }
  description?: string
}
interface Song {
  audio_id: string
  title?: string
  language?: string
  bpm?: number
  drop?: number
  chorus_start?: number
  chorus_end?: number
  chorus_link?: string
  chorus_mmss?: string
  error?: string
}
interface HeroHome {
  hero: { ready: boolean; reason: string }
  concepts: { id: string; label: string; seconds: number }[]
  runs: Run[]
  run_state: { status?: string; error?: string | null }
  songs: Song[]
  anthem: { status?: string; error?: string | null; tracks?: { title?: string }[] }
  cap_usd: number
}

const LANG_KO: Record<string, string> = { inst: "연주곡", en: "영어", ko: "한국어" }
const sec = (v?: number) => (v == null ? "—" : `${v.toFixed(1)}초`)

async function post(path: string, body: object) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
  const d = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(typeof d?.detail === "string" ? d.detail : `요청 실패(${r.status})`)
  return d
}

function HeroInner() {
  const channel = useSearchParams().get("channel") || WORKOUT_CHANNEL_ID
  const [data, setData] = useState<HeroHome | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [concept, setConcept] = useState("bat_break")
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(
    () =>
      fetch(`/api/shorts/hero?channel=${encodeURIComponent(channel)}`, { cache: "no-store" })
        .then(async (r) => {
          const d = await r.json().catch(() => ({}))
          if (!r.ok) throw new Error(typeof d?.detail === "string" ? d.detail : `불러오기 실패(${r.status})`)
          setData(d)
          setError(null)
        })
        .catch((e) => setError(e instanceof Error ? e.message : "불러오기 실패")),
    [channel],
  )

  const running = data?.run_state?.status === "running" || data?.anthem?.status === "running"
  useEffect(() => {
    load()
    const t = setInterval(load, running ? 5000 : 30000)
    return () => clearInterval(t)
  }, [load, running])

  async function act(key: string, path: string, body: object, ok: string, ask?: string) {
    if (ask && !confirm(ask)) return
    setBusy(key)
    try {
      await post(path, { channel, ...body })
      toast.success(ok)
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "실패")
    } finally {
      setBusy(null)
    }
  }

  const cap = data?.cap_usd ?? 6
  const ready = !!data?.hero.ready

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
            <h1 className="text-lg font-semibold text-foreground">쇼츠 · 운동 자극 (형식 A 원테이크)</h1>
            <p className="text-xs text-muted-foreground">글자·목소리 없음 · 테스트는 미리보기만(유튜브 업로드 없음) · 편당 상한 ${cap}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={concept}
            onChange={(e) => setConcept(e.target.value)}
            className="min-h-[40px] rounded-lg border border-border bg-background px-2 text-sm text-foreground"
          >
            {(data?.concepts ?? []).map((c) => (
              <option key={c.id} value={c.id}>{c.label}</option>
            ))}
          </select>
          <button
            onClick={() => act("test", "/api/shorts/hero/test", { concept }, "테스트 제작 시작 — 수 분 걸려요",
              `형식 A 테스트 1편을 만들어요(Kling Pro 10초 $2.4, 검수 불합격 시 재생성 — 최대 $${cap}). 진행할까요?`)}
            disabled={!ready || running || busy !== null}
            title={ready ? "테스트 1편(미리보기 두 버전)" : data?.hero.reason}
            className="flex min-h-[40px] items-center gap-1.5 rounded-lg bg-emerald-600 px-3 text-sm font-semibold text-white shadow-sm hover:opacity-90 disabled:opacity-40"
          >
            {busy === "test" || data?.run_state?.status === "running" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {data?.run_state?.status === "running" ? "제작 중…" : "테스트 1편 만들기"}
          </button>
        </div>
      </div>

      {error && <div className="rounded-xl border border-border bg-card p-4 text-sm text-red-400">{error}</div>}
      {data && !ready && (
        <div className="flex items-center gap-2 rounded-xl border border-border bg-card p-3 text-sm text-muted-foreground">
          <Users className="h-4 w-4 shrink-0" />
          {data.hero.reason}{" "}
          <Link href={`/shorts/cast?channel=${encodeURIComponent(channel)}`} className="text-primary underline">캐릭터 시트</Link>
        </div>
      )}
      {data?.run_state?.status === "failed" && data.run_state.error && (
        <div className="rounded-xl border border-border bg-card p-3 text-sm text-red-400">최근 제작 실패: {data.run_state.error}</div>
      )}

      {(data?.runs ?? []).map((r) => (
        <div key={r.id} className="flex flex-col gap-3 rounded-xl border border-border bg-card p-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-semibold text-foreground">{r.label ?? r.id}</span>
            <span className="text-xs text-muted-foreground">{new Date(r.created_at).toLocaleString("ko-KR")}</span>
            {r.status === "failed" ? (
              <span className="rounded-full bg-red-500/15 px-2 py-0.5 text-[11px] font-medium text-red-400">실패</span>
            ) : r.review?.pass ? (
              <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-400">검수 통과</span>
            ) : (
              <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[11px] font-medium text-primary">검수 불합격 — 확인 필요</span>
            )}
          </div>
          {r.error && <p className="text-xs text-red-400">{r.error}</p>}
          {r.review && !r.review.pass && r.review.reasons?.length ? (
            <p className="text-xs text-muted-foreground">검수 사유: {r.review.reasons.join(" · ")}</p>
          ) : null}

          {r.previews && (
            <div className="grid grid-cols-2 gap-3 md:max-w-[560px]">
              {([["sfx", "음악 없음 (효과음만 · 인스타용)"], ["slam", "후렴 쾅 (마지막에 우리 곡)"]] as const).map(([k, label]) => (
                <div key={k} className="flex min-w-0 flex-col gap-1.5">
                  <span className="text-xs font-medium text-foreground">{label}</span>
                  {r.previews?.[k] ? (
                    <>
                      <video src={r.previews[k]} controls playsInline preload="metadata" className="aspect-[9/16] w-full rounded-lg bg-black" />
                      <a href={r.previews[k]} download className="flex items-center gap-1 text-[11px] text-primary">
                        <Download className="h-3.5 w-3.5" /> 내려받기
                      </a>
                    </>
                  ) : (
                    <div className="flex aspect-[9/16] w-full items-center justify-center rounded-lg bg-secondary/30 px-2 text-center text-[11px] text-muted-foreground">
                      분석된 우리 곡이 없어 이 버전은 없어요 — 아래 &lsquo;곡 분석&rsquo;을 먼저 눌러 주세요
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {r.related && (
            <div className="flex flex-col gap-1.5 rounded-xl border border-primary/40 bg-primary/10 p-3">
              <span className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
                <Link2 className="h-4 w-4 text-primary" /> 관련 동영상으로 연결할 플리 영상
              </span>
              <a href={r.related.link} target="_blank" rel="noreferrer" className="break-all text-base font-semibold text-primary underline">
                {r.related.youtube_url}
              </a>
              <span className="text-base font-semibold text-foreground">곡 위치 {r.related.mmss}</span>
              <span className="text-[11px] text-muted-foreground">
                업로드 후 YouTube Studio(PC) → 콘텐츠 → Shorts → 이 쇼츠 → 세부정보 → &lsquo;관련 동영상&rsquo;에서 위 영상을 선택해 주세요(API 로는 연결 불가).
              </span>
            </div>
          )}

          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
            {r.cost && (
              <span>
                Kling ${r.cost.kling_usd.toFixed(2)} ({r.cost.kling_seconds}초·{r.cost.attempts}회) · 효과음 {r.cost.sfx_credits}크레딧
                {r.cost.stopped_by_cap ? ` · 상한 $${r.cost.cap_usd}에서 재생성 중단` : ""}
              </span>
            )}
            {r.impact && <span>파열 {sec(r.impact.t)}{r.impact.guessed ? "(추정)" : ""} · 효과음 오차 {r.sync?.crack_err_ms ?? "—"}ms</span>}
            {r.song?.bpm && <span>후렴 곡 {r.song.bpm} BPM</span>}
          </div>
          {r.description && (
            <pre className="whitespace-pre-wrap rounded-lg bg-secondary/30 p-2 text-[11px] text-muted-foreground">{r.description}</pre>
          )}
        </div>
      ))}

      <div className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="flex items-center gap-1.5 text-sm font-semibold text-foreground"><AudioLines className="h-4 w-4" /> 곡 분석 (업로드된 플리 영상 속 우리 곡)</span>
          <button
            onClick={() => act("songs", "/api/shorts/hero/songs/analyze", {}, "곡 분석 시작 — 잠시 후 새로고침돼요")}
            disabled={busy !== null}
            className="flex min-h-[36px] items-center gap-1.5 rounded-lg border border-border px-2.5 text-xs font-medium text-foreground hover:border-primary/40 disabled:opacity-40"
          >
            {busy === "songs" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <AudioLines className="h-3.5 w-3.5" />}
            최근 3곡 분석
          </button>
        </div>
        {(data?.songs ?? []).length === 0 ? (
          <p className="text-xs text-muted-foreground">아직 분석한 곡이 없어요.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-left text-xs">
              <thead className="text-muted-foreground">
                <tr><th className="py-1 pr-2">곡</th><th className="pr-2">언어</th><th className="pr-2">BPM</th><th className="pr-2">드롭</th><th className="pr-2">후렴 구간</th><th>플리 영상 위치</th></tr>
              </thead>
              <tbody className="text-foreground">
                {data?.songs.map((s) => (
                  <tr key={s.audio_id} className="border-t border-border">
                    <td className="py-1 pr-2">{s.title || s.audio_id}</td>
                    <td className="pr-2">{LANG_KO[s.language ?? ""] ?? (s.language || "—")}</td>
                    <td className="pr-2">{s.error ? "실패" : s.bpm}</td>
                    <td className="pr-2">{sec(s.drop)}</td>
                    <td className="pr-2">{s.chorus_start != null ? `${s.chorus_start.toFixed(1)}~${s.chorus_end?.toFixed(1)}초` : "—"}</td>
                    <td>{s.chorus_link ? <a href={s.chorus_link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary">{s.chorus_mmss}<ExternalLink className="h-3 w-3" /></a> : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border bg-card p-3">
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 text-sm font-semibold text-foreground"><Music2 className="h-4 w-4" /> 쿵쿵따 스타디움 운동 앤섬</p>
          <p className="text-[11px] text-muted-foreground">
            연주곡 ~80 BPM · 발 구르기·박수·묵직한 드럼·후반 일렉기타 · Suno 1회 = 2곡 → 운동 채널 라이브러리
            {data?.anthem?.status === "done" ? ` · 완료: ${(data.anthem.tracks ?? []).map((t) => t.title || "제목 없음").join(", ")}` : ""}
            {data?.anthem?.status === "failed" ? ` · 실패: ${data.anthem.error}` : ""}
          </p>
        </div>
        <button
          onClick={() => act("anthem", "/api/shorts/hero/anthem", {}, "앤섬 생성 시작 — 수 분 걸려요", "Suno 로 연주곡을 1회(2곡) 만들어요. 진행할까요?")}
          disabled={busy !== null || data?.anthem?.status === "running"}
          className="flex min-h-[36px] items-center gap-1.5 rounded-lg border border-border px-2.5 text-xs font-medium text-foreground hover:border-primary/40 disabled:opacity-40"
        >
          {data?.anthem?.status === "running" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Music2 className="h-3.5 w-3.5" />}
          {data?.anthem?.status === "running" ? "생성 중…" : "앤섬 만들기"}
        </button>
      </div>
    </div>
  )
}

export default function ShortsHeroPage() {
  return (
    <Suspense fallback={null}>
      <HeroInner />
    </Suspense>
  )
}
