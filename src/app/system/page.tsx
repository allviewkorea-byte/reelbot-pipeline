"use client"

import { useCallback, useEffect, useState } from "react"
import { RefreshCw } from "lucide-react"

type ServiceStatus = {
  status: "ok" | "warn" | "error"
  message?: string
  latency_ms?: number
  credits?: number
  function?: string
  channel?: string
}

type StatusResponse = {
  railway: ServiceStatus
  supabase: ServiceStatus
  r2: ServiceStatus
  aws_lambda: ServiceStatus
  suno: ServiceStatus
  anthropic: ServiceStatus
  youtube: ServiceStatus
  checked_at: string
}

type ErrorEntry = {
  job_id: string
  type: string
  step: string
  error_message: string
  created_at: string
}

const SERVICE_LABELS: Record<string, { label: string; icon: string }> = {
  railway: { label: "Railway", icon: "🚂" },
  supabase: { label: "Supabase", icon: "🗄️" },
  r2: { label: "Cloudflare R2", icon: "☁️" },
  aws_lambda: { label: "AWS Lambda", icon: "⚡" },
  suno: { label: "Suno API", icon: "🎵" },
  anthropic: { label: "Anthropic", icon: "🤖" },
  youtube: { label: "YouTube", icon: "📺" },
}

const SERVICE_ORDER = [
  "railway",
  "supabase",
  "r2",
  "aws_lambda",
  "suno",
  "anthropic",
  "youtube",
] as const

function StatusDot({ status }: { status: string }) {
  if (status === "ok")
    return <span className="inline-block h-2.5 w-2.5 rounded-full bg-emerald-500" />
  if (status === "warn")
    return <span className="inline-block h-2.5 w-2.5 rounded-full bg-amber-500" />
  return <span className="inline-block h-2.5 w-2.5 rounded-full bg-red-500" />
}

function statusLabel(s: ServiceStatus): string {
  if (s.status === "ok") return "정상"
  if (s.status === "warn") return s.message || "경고"
  return s.message || "에러"
}

function statusDetail(key: string, s: ServiceStatus): string {
  const parts: string[] = []
  if (s.latency_ms !== undefined) parts.push(`응답 ${s.latency_ms}ms`)
  if (s.credits !== undefined) parts.push(`잔액 ${s.credits}크레딧`)
  if (s.function) parts.push(s.function)
  if (s.channel) parts.push(s.channel)
  return parts.join(" · ")
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const sec = Math.floor(diff / 1000)
  if (sec < 10) return "방금"
  if (sec < 60) return `${sec}초 전`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}분 전`
  return `${Math.floor(min / 60)}시간 전`
}

function formatTime(iso: string): string {
  if (!iso) return ""
  const d = new Date(iso)
  return d.toLocaleString("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })
}

export default function SystemPage() {
  const [status, setStatus] = useState<StatusResponse | null>(null)
  const [errors, setErrors] = useState<ErrorEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [checkedAt, setCheckedAt] = useState("")

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const [sRes, eRes] = await Promise.all([
        fetch("/api/system/status").then((r) => r.json()),
        fetch("/api/system/errors?limit=20").then((r) => r.json()),
      ])
      setStatus(sRes)
      setErrors(sRes.errors || eRes.errors || [])
      setCheckedAt(sRes.checked_at || new Date().toISOString())
    } catch {
      /* 네트워크 에러는 기존 상태 유지 */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const run = () => { refresh() }
    run()
    const timer = setInterval(run, 30_000)
    return () => clearInterval(timer)
  }, [refresh])

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">시스템 상태</h1>
          {checkedAt && (
            <p className="mt-0.5 text-xs text-muted-foreground">
              마지막 확인: {timeAgo(checkedAt)}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={refresh}
          disabled={loading}
          className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-sm text-foreground transition hover:bg-white/5 disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          새로고침
        </button>
      </div>

      {/* 서비스 상태 카드 */}
      <div className="rounded-xl border border-border bg-card overflow-hidden">
        {SERVICE_ORDER.map((key, i) => {
          const svc = status?.[key]
          const meta = SERVICE_LABELS[key]
          return (
            <div
              key={key}
              className={`flex items-center gap-3 px-4 py-3 ${
                i > 0 ? "border-t border-border" : ""
              }`}
            >
              <span className="w-6 text-center text-base">{meta.icon}</span>
              <StatusDot status={svc?.status || "error"} />
              <span className="min-w-[110px] text-sm font-medium text-foreground">
                {meta.label}
              </span>
              <span
                className={`text-sm ${
                  svc?.status === "ok"
                    ? "text-emerald-400"
                    : svc?.status === "warn"
                      ? "text-amber-400"
                      : "text-red-400"
                }`}
              >
                {svc ? statusLabel(svc) : "확인 중..."}
              </span>
              <span className="ml-auto text-xs text-muted-foreground">
                {svc ? statusDetail(key, svc) : ""}
              </span>
            </div>
          )
        })}
      </div>

      {/* 최근 에러 */}
      <div className="mt-8">
        <h2 className="mb-3 text-sm font-semibold text-foreground">
          최근 에러 (최근 20개)
        </h2>
        {errors.length === 0 ? (
          <p className="rounded-lg border border-border bg-card px-4 py-6 text-center text-sm text-muted-foreground">
            최근 에러 없음
          </p>
        ) : (
          <div className="space-y-1.5">
            {errors.map((err) => (
              <div
                key={err.job_id + err.created_at}
                className="flex items-start gap-2 rounded-lg border border-border bg-card px-3 py-2"
              >
                <span className="mt-0.5 text-red-400">
                  <span className="inline-block h-2 w-2 rounded-full bg-red-500" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span>{formatTime(err.created_at)}</span>
                    {err.step && (
                      <span className="rounded bg-white/5 px-1.5 py-0.5">
                        {err.step}
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 truncate text-sm text-foreground">
                    {err.error_message || "알 수 없는 오류"}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
