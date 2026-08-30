"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import { ArrowLeft, Loader2, Save, ExternalLink, CheckCircle2, AlertTriangle } from "lucide-react"
import { API_BASE } from "@/lib/proxy"
import {
  MUSIC_CHANNELS,
  MUSIC_CHANNEL_ID,
  MUSIC_CHANNEL_NAME,
  DEFAULT_MUSIC_CONFIG,
  type MusicChannelConfig,
} from "@/lib/music"

interface YtStatus {
  connected: boolean
  channel: string
  channel_id: string
  channel_id_env: string
  channel_id_env_key: string
}

// 채널별 유튜브 연결 카드 — 연결 상태 표시 + 연결(재인증) 버튼.
// 인증은 구글로 리다이렉트돼야 하므로 프록시가 아니라 백엔드 URL 로 직접 이동한다.
function YoutubeConnectCard({ channelKey }: { channelKey: string }) {
  const info = MUSIC_CHANNELS[channelKey]
  const [st, setSt] = useState<YtStatus | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    fetch(`/api/music/youtube/status?channel=${encodeURIComponent(channelKey)}`)
      .then((r) => r.json())
      .then((d) => { if (alive) setSt(d) })
      .catch(() => { if (alive) setSt(null) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [channelKey])

  const hasEnv = Boolean(st?.channel_id_env)
  const connected = Boolean(st?.connected)
  const authUrl = `${API_BASE}/api/music/youtube/auth?channel=${encodeURIComponent(channelKey)}`

  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-background px-3 py-2.5">
      <span className="text-lg">{info.icon}</span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground">{info.name}</p>
        {loading ? (
          <p className="text-xs text-muted-foreground">확인 중…</p>
        ) : !hasEnv ? (
          <p className="flex items-center gap-1 text-xs text-amber-400">
            <AlertTriangle className="h-3 w-3" />
            {st?.channel_id_env_key || "채널 ID env"} 미설정 — 환경변수를 먼저 넣어주세요
          </p>
        ) : connected ? (
          <p className="flex items-center gap-1 text-xs text-emerald-400">
            <CheckCircle2 className="h-3 w-3" /> 연결됨 · {st?.channel_id}
          </p>
        ) : (
          <p className="text-xs text-amber-400">유튜브 연결 필요</p>
        )}
      </div>
      <a
        href={hasEnv ? authUrl : undefined}
        aria-disabled={!hasEnv}
        className={
          hasEnv
            ? "inline-flex h-9 shrink-0 items-center gap-1.5 rounded-md border border-border px-3 text-xs font-medium text-foreground hover:border-primary/40"
            : "pointer-events-none inline-flex h-9 shrink-0 items-center gap-1.5 rounded-md border border-border px-3 text-xs text-muted-foreground/50"
        }
        title={hasEnv ? "구글 인증 화면으로 이동합니다" : "채널 ID 환경변수가 먼저 필요합니다"}
      >
        <ExternalLink className="h-4 w-4" /> {connected ? "재연결" : "연결"}
      </a>
    </div>
  )
}

const FIELDS: { key: keyof MusicChannelConfig; label: string; placeholder: string; hint?: string; area?: boolean }[] = [
  { key: "slogan_en", label: "채널 슬로건 (영문)", placeholder: "예: Out of Office, Into the music", hint: "본문 [1] 환영 멘트 아래에 표시 · 비우면 출력 안 함" },
  { key: "slogan_kr", label: "채널 표어 (한국어)", placeholder: "예: 당신의 하루에 음악 한 스푼", hint: "선택 · 비우면 출력 안 함" },
  { key: "email", label: "채널 이메일", placeholder: "hello@example.com", hint: "본문 [4] 소셜에 표시 · 선택" },
  { key: "instagram", label: "인스타그램 핸들", placeholder: "revezen (@ 제외)", hint: "본문에 @핸들 표시 · 선택" },
  { key: "tiktok", label: "틱톡 핸들", placeholder: "revezen (@ 제외)", hint: "본문에 @핸들 표시 · 선택" },
  { key: "spotify_url", label: "Spotify 아티스트 URL", placeholder: "https://open.spotify.com/artist/…", hint: "본문 [3] 외부 플랫폼 · Spotify 유통 후 · 선택" },
  { key: "ai_disclosure", label: "AI 명시 문구 (한국어)", placeholder: DEFAULT_MUSIC_CONFIG.ai_disclosure, hint: "본문 [2]에 표시 · 비우면 기본 문구 사용", area: true },
]

export default function MusicSettingsPage() {
  const [config, setConfig] = useState<MusicChannelConfig>(DEFAULT_MUSIC_CONFIG)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetch(`/api/music/config?channelId=${MUSIC_CHANNEL_ID}`)
      .then((r) => r.json())
      .then((d) => { if (d?.config) setConfig(d.config) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const update = (key: keyof MusicChannelConfig, v: string) => setConfig((c) => ({ ...c, [key]: v }))

  const save = useCallback(async () => {
    setSaving(true)
    try {
      const res = await fetch("/api/music/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channelId: MUSIC_CHANNEL_ID, config }),
      })
      const d = await res.json()
      if (!d?.success) throw new Error(d?.error || "저장 실패")
      setConfig(d.config)
      toast.success("채널 설정을 저장했습니다.")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "저장 실패")
    } finally {
      setSaving(false)
    }
  }, [config])

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-auto p-4 md:p-6">
      <header className="pl-10 md:pl-0">
        {/* 모바일: 버튼 가로 한 줄(좌/우 정렬, 줄바꿈 없음). 데스크탑은 아래 인라인 행 사용. */}
        <div className="mb-3 flex items-center justify-between gap-2 md:hidden">
          <Link href="/music" className="inline-flex min-h-[44px] items-center gap-1.5 whitespace-nowrap rounded-lg border border-border px-3 text-sm text-muted-foreground hover:bg-white/5 hover:text-foreground">
            <ArrowLeft className="h-4 w-4" /> 대시보드
          </Link>
          <Link href="/music/design" className="inline-flex min-h-[44px] items-center gap-1.5 whitespace-nowrap rounded-lg border border-border px-3 text-sm text-muted-foreground hover:border-primary/40 hover:text-foreground">
            디자인 본부
          </Link>
        </div>
        {/* 데스크탑 인라인 행(기존 그대로) + 제목(모바일 공통) */}
        <div className="flex items-center gap-3">
          <Link href="/music" className="hidden items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground hover:bg-white/5 hover:text-foreground md:inline-flex">
            <ArrowLeft className="h-4 w-4" /> 대시보드
          </Link>
          <div>
            <h1 className="text-xl font-semibold text-foreground">채널 설정</h1>
            <p className="text-sm text-muted-foreground">공개 업로드 본문·SEO 에 쓰이는 운영 정보입니다. 빈 칸은 본문에 출력되지 않아요.</p>
          </div>
          <Link href="/music/design" className="ml-auto hidden items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground hover:border-primary/40 hover:text-foreground md:inline-flex">
            디자인 본부
          </Link>
        </div>
      </header>

      {/* 유튜브 연결(운동 채널 3단계) — 채널별 토큰이 분리돼 각각 인증이 필요하다. */}
      <section className="flex flex-col gap-2 rounded-xl border border-border bg-card p-4">
        <div>
          <h2 className="text-sm font-semibold text-foreground">유튜브 연결</h2>
          <p className="text-xs text-muted-foreground">
            채널마다 토큰이 따로입니다. 연결 버튼을 누르면 구글 인증 화면이 열리고,
            거기서 <strong>해당 채널을 직접 선택</strong>해야 합니다.
          </p>
        </div>
        {Object.keys(MUSIC_CHANNELS).map((k) => (
          <YoutubeConnectCard key={k} channelKey={k} />
        ))}
      </section>

      {loading ? (
        <div className="flex h-40 items-center justify-center text-muted-foreground"><Loader2 className="h-6 w-6 animate-spin" /></div>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* 입력 폼 */}
          <div className="flex flex-col gap-4 rounded-xl border border-border bg-card p-4">
            {FIELDS.map((f) => (
              <label key={f.key} className="flex flex-col gap-1">
                <span className="text-sm font-medium text-foreground">{f.label}</span>
                {f.area ? (
                  <textarea
                    rows={3}
                    value={config[f.key]}
                    onChange={(e) => update(f.key, e.target.value)}
                    placeholder={f.placeholder}
                    className="rounded-md border border-border bg-background px-2.5 py-2 text-sm text-foreground placeholder:text-muted-foreground/60"
                  />
                ) : (
                  <input
                    type="text"
                    value={config[f.key]}
                    onChange={(e) => update(f.key, e.target.value)}
                    placeholder={f.placeholder}
                    className="h-9 rounded-md border border-border bg-background px-2.5 text-sm text-foreground placeholder:text-muted-foreground/60"
                  />
                )}
                {f.hint && <span className="text-[11px] text-muted-foreground">{f.hint}</span>}
              </label>
            ))}
            <button
              type="button"
              onClick={save}
              disabled={saving}
              className="inline-flex items-center justify-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-60"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} 저장
            </button>
          </div>

          {/* 미리보기 — 이 설정으로 본문이 이렇게 올라가요 */}
          <div className="flex flex-col gap-2 rounded-xl border border-border bg-card p-4">
            <h2 className="text-sm font-semibold text-foreground">미리보기 — 본문에 이렇게 들어가요</h2>
            <p className="text-[11px] text-muted-foreground">제목·트랙리스트·해시태그는 곡 분석 기반으로 영상마다 자동 생성됩니다.</p>
            <pre className="mt-1 whitespace-pre-wrap break-words rounded-md border border-border bg-background p-3 text-xs leading-relaxed text-foreground/90">
{previewText(config)}
            </pre>
          </div>
        </div>
      )}
    </div>
  )
}

// 입력값 반영 미리보기(백엔드 music_meta 와 동일 규칙의 축약 버전 — 빈 값은 생략).
function previewText(c: MusicChannelConfig): string {
  const SEP = "━".repeat(20)
  const blocks: string[] = []
  const s1 = ["📍 Dawn Highway 🌍 🌃", "", "오늘 하루도 수고 많으셨어요. (자동 생성 멘트)", "", "오늘도 좋은 음악과 함께하세요 🎧"]
  if (c.slogan_en.trim()) s1.push("", c.slogan_en.trim())
  blocks.push(s1.join("\n"))
  blocks.push((c.ai_disclosure.trim() || DEFAULT_MUSIC_CONFIG.ai_disclosure))
  if (c.spotify_url.trim()) {
    blocks.push("📀 Apple Music · Spotify · YouTube Music · iTunes 에서 감상하실 수 있습니다\nSpotify 🔗 " + c.spotify_url.trim())
  }
  const social: string[] = []
  if (c.email.trim()) social.push("📧 E-mail: " + c.email.trim())
  if (c.instagram.trim()) social.push("📸 Instagram: @" + c.instagram.trim().replace(/^@/, ""))
  if (c.tiktok.trim()) social.push("🎵 TikTok: @" + c.tiktok.trim().replace(/^@/, ""))
  if (social.length) blocks.push(social.join("\n"))
  blocks.push("🎵 Track list\n\n[00:00:00] (곡 제목 자동)\n[00:03:30] (곡 제목 자동)")
  blocks.push("🎵 가장 마음에 드는 노래는 무엇인가요? …\n🔔 채널 구독 …")
  blocks.push(`Copyright Ⓒ ${MUSIC_CHANNEL_NAME} All rights reserved.`)
  blocks.push("#playlist #플레이리스트 #citypop #시티팝 … (30~50개 자동)")
  return blocks.join(`\n\n${SEP}\n\n`)
}
