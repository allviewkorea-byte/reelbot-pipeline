"use client"

// 메인 대시보드 상태판(대표 승인 2026-10-19) — 휴대폰으로 열었을 때 3초 안에 "잘 돌고 있나 / 문제 있나 /
// 돈은 얼마 쓰나". /api/music/dashboard/summary(백엔드 요약, 읽기 전용)를 1분마다 다시 읽는다.
// 상태등·알림(MusicStatusLight)은 휴대폰에서 설정 버튼보다 위(제목 바로 아래)에 둔다 — 390px 에선 설정
// 버튼이 첫 화면을 다 채워서, 아래에 두면 스크롤해야 보인다. 나머지(MusicStatusBoard): 오늘 회차 → 숫자 4개 →
// (기존 KPI 한 줄) → 최근 7회차. 데이터는 페이지가 useMusicSummary 로 한 번만 읽어 둘에 나눠 준다.
// 색은 기존 토큰 + 상태색(emerald/amber/red 400·500) 클래스만 — 화이트 모드는 theme-light.css 가 대비를 맞춘다.
// 데이터가 없으면 숫자를 만들지 않는다("—" / "확인 불가").
import { type ReactNode, useEffect, useState } from "react"
import { ExternalLink, Flame, Upload, Coins, Wallet } from "lucide-react"
import { channelParam } from "@/lib/music"

type Light = "green" | "yellow" | "red"
type RoundStatus =
  | "waiting" | "producing" | "retry" | "stalled" | "scheduled" | "published" | "private"
  | "failed" | "skipped" | "off"

interface Round {
  key: string
  publish_at: string | null
  status: RoundStatus
  label: string
  youtube_url?: string | null
  reason?: string | null
  retry?: string | null
  language_label?: string | null
  bg_label?: string | null
}

export interface Summary {
  light: { color: Light; text: string; line: string }
  today: Round[]
  numbers: {
    streak_days: number
    month_uploads: number | null
    credits: { balance: number | null; days_left: number | null; level: "ok" | "yellow" | "red" | "unknown"; basis: string | null }
    month_cost: { usd: number; krw: number; excluded: string[]; estimate: boolean } | null
  }
  recent7: { key: string; ok: boolean | null; text: string }[]
  alerts: { level: "yellow" | "red"; text: string }[]
}

const POLL_MS = 60_000

const LIGHT_STYLE: Record<Light, { box: string; dot: string; text: string }> = {
  green: { box: "border-emerald-500/40 bg-emerald-500/10", dot: "bg-emerald-500", text: "text-emerald-400" },
  yellow: { box: "border-amber-500/30 bg-amber-500/10", dot: "bg-amber-400", text: "text-amber-400" },
  red: { box: "border-red-500/40 bg-red-500/10", dot: "bg-red-500", text: "text-red-400" },
}

const STATUS_TEXT: Record<RoundStatus, string> = {
  published: "text-emerald-400", scheduled: "text-emerald-400", private: "text-amber-400",
  producing: "text-primary", waiting: "text-muted-foreground", off: "text-muted-foreground",
  retry: "text-amber-400", stalled: "text-red-400", failed: "text-red-400", skipped: "text-red-400",
}

const LEVEL_TEXT: Record<string, string> = { ok: "text-foreground", yellow: "text-amber-400", red: "text-red-400", unknown: "text-muted-foreground" }

function hm(iso: string | null | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return "—"
  return d.toLocaleTimeString("ko-KR", { timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", hour12: false })
}

function fmtNum(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : n.toLocaleString("ko-KR")
}

/** 요약 1분 폴링. 채널이 바뀌면 이전 채널 값은 버린다(다른 채널 숫자가 잠깐 보이지 않게). */
export function useMusicSummary(channel: string): { data: Summary | null; failed: boolean } {
  const [state, setState] = useState<{ channel: string; data: Summary | null; failed: boolean }>({
    channel, data: null, failed: false,
  })

  useEffect(() => {
    let alive = true // 채널이 바뀌면 부모가 key 로 새로 마운트한다(초기화 불필요)
    const qp = channelParam(channel)
    const load = () => {
      fetch(`/api/music/dashboard/summary${qp ? `?${qp}` : ""}`)
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
        .then((d: Summary) => {
          if (!alive) return
          setState((s) => (d?.light ? { channel, data: d, failed: false } : { ...s, channel, failed: true }))
        })
        .catch(() => alive && setState((s) => ({ ...s, channel, failed: true })))
    }
    load()
    const id = setInterval(load, POLL_MS)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [channel])

  // 채널 전환 직후(새 응답 전)에는 이전 채널 데이터를 쓰지 않는다.
  return state.channel === channel ? { data: state.data, failed: state.failed } : { data: null, failed: false }
}

/** 상태등 + 알림(문제 있을 때만). */
/** className 은 표시 방식(display)까지 정한다 — 예: "flex md:hidden" / "hidden md:flex". */
export function MusicStatusLight({ data, failed, className = "flex" }: { data: Summary | null; failed: boolean; className?: string }) {
  if (!data) {
    return (
      <div className={`flex-col rounded-xl border border-border bg-card p-3 text-sm text-muted-foreground ${className}`}>
        {failed ? "상태 요약을 불러오지 못했습니다 — 백엔드 연결을 확인하세요(1분 뒤 다시 시도)" : "상태 확인 중…"}
      </div>
    )
  }
  const ls = LIGHT_STYLE[data.light.color] ?? LIGHT_STYLE.yellow
  return (
    <div className={`flex-col gap-3 ${className}`}>
      <div className={`rounded-xl border p-3 ${ls.box}`}>
        <div className="flex items-center gap-2">
          <span className={`h-3 w-3 shrink-0 rounded-full ${ls.dot} ${data.light.color === "green" ? "animate-pulse" : ""}`} />
          <span className={`text-lg font-bold ${ls.text}`}>{data.light.text}</span>
        </div>
        <p className="mt-1 text-sm text-foreground">{data.light.line}</p>
      </div>
      {data.alerts.length > 0 && (
        <div className="flex flex-col gap-1.5 rounded-xl border border-border bg-card p-3">
          {data.alerts.map((a, i) => (
            <p key={i} className={`text-sm ${a.level === "red" ? "text-red-400" : "text-amber-400"}`}>
              {a.level === "red" ? "●" : "▲"} {a.text}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}

/** 오늘 회차 → 숫자 4개 → (afterNumbers: 기존 KPI 한 줄) → 최근 7회차. */
export function MusicStatusBoard({ data, afterNumbers }: { data: Summary | null; afterNumbers?: ReactNode }) {
  const [picked, setPicked] = useState<string | null>(null)
  if (!data) return <>{afterNumbers}</>

  const { streak_days, month_uploads, credits, month_cost } = data.numbers
  const pickedItem = data.recent7.find((r) => r.key === picked)

  const cards = [
    { label: "연속 업로드", icon: Flame, value: `${streak_days}일`, sub: "회차를 놓치지 않은 날", tone: "text-foreground" },
    { label: "이번 달 업로드", icon: Upload, value: month_uploads === null ? "—" : `${month_uploads}편`, sub: "", tone: "text-foreground" },
    {
      label: "Suno 크레딧", icon: Coins,
      value: credits.balance === null ? "확인 불가" : fmtNum(credits.balance),
      sub: credits.days_left === null ? "" : `약 ${credits.days_left}일치${credits.basis === "measured" ? " · 실측" : " · 설정 기준"}`,
      tone: LEVEL_TEXT[credits.level] ?? "text-foreground",
    },
    {
      label: "이번 달 비용(추정)", icon: Wallet,
      value: month_cost ? `₩${fmtNum(month_cost.krw)}` : "—",
      sub: month_cost
        ? `$${month_cost.usd.toFixed(2)} · 두 채널 합계${month_cost.excluded.length ? ` · ${month_cost.excluded.map((x) => (x === "lambda" ? "Lambda" : x === "openai" ? "OpenAI" : x)).join("·")} 제외` : ""}`
        : "",
      tone: "text-foreground",
    },
  ]

  return (
    <div className="flex flex-col gap-3">
      {/* 오늘 현황 */}
      <div className="rounded-xl border border-border bg-card p-3">
        <h2 className="text-sm font-semibold text-foreground">오늘</h2>
        {data.today.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">오늘 회차 없음</p>
        ) : (
          <ul className="mt-2 flex flex-col gap-2">
            {data.today.map((r) => (
              <li key={r.key} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm">
                <span className="font-mono text-foreground">{hm(r.publish_at)}</span>
                <span className={`font-medium ${STATUS_TEXT[r.status] ?? "text-foreground"}`}>{r.retry || r.label}</span>
                {[r.language_label, r.bg_label].filter(Boolean).map((t) => (
                  <span key={t} className="text-xs text-muted-foreground">· {t}</span>
                ))}
                {r.youtube_url && (
                  <a
                    href={r.youtube_url}
                    target="_blank"
                    rel="noreferrer"
                    className="ml-auto flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-xs text-foreground hover:border-primary/40"
                  >
                    유튜브 <ExternalLink className="h-3 w-3" />
                  </a>
                )}
                {r.reason && ["failed", "skipped", "stalled", "retry"].includes(r.status) && (
                  <span className="w-full text-xs text-muted-foreground">{r.reason}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* 숫자 4개 */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {cards.map((c) => (
          <div key={c.label} className="rounded-xl border border-border bg-card p-2.5">
            <div className="flex items-center gap-2 text-muted-foreground">
              <c.icon className="h-4 w-4" />
              <span className="text-xs">{c.label}</span>
            </div>
            <p className={`mt-1 text-base font-bold ${c.tone}`} style={{ fontFamily: "var(--font-geist-mono)" }}>
              {c.value}
            </p>
            {c.sub && <p className="text-[11px] leading-tight text-muted-foreground">{c.sub}</p>}
          </div>
        ))}
      </div>

      {afterNumbers}

      {/* 최근 7회차 */}
      <div className="rounded-xl border border-border bg-card p-3">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-foreground">최근 7회차</h2>
          <div className="flex gap-1.5">
            {data.recent7.length === 0 && <span className="text-xs text-muted-foreground">기록 없음</span>}
            {data.recent7.map((r) => (
              <button
                key={r.key}
                type="button"
                title={r.text}
                aria-label={r.text}
                onClick={() => setPicked((p) => (p === r.key ? null : r.key))}
                className={`h-5 w-5 rounded ${
                  r.ok === true ? "bg-emerald-500" : r.ok === false ? "bg-red-500" : "bg-muted-foreground/40"
                } ${picked === r.key ? "ring-2 ring-primary ring-offset-1 ring-offset-background" : ""}`}
              />
            ))}
          </div>
        </div>
        {pickedItem && <p className="mt-2 text-xs text-muted-foreground">{pickedItem.text}</p>}
      </div>
    </div>
  )
}
