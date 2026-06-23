"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import { ArrowLeft, Loader2, Save } from "lucide-react"
import {
  MUSIC_CHANNEL_ID,
  MUSIC_CHANNEL_NAME,
  DEFAULT_MUSIC_CONFIG,
  type MusicChannelConfig,
} from "@/lib/music"

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
      <header className="flex items-center gap-3 pl-10 md:pl-0">
        <Link href="/music" className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground hover:bg-white/5 hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> 대시보드
        </Link>
        <div>
          <h1 className="text-xl font-semibold text-foreground">채널 설정</h1>
          <p className="text-sm text-muted-foreground">공개 업로드 본문·SEO 에 쓰이는 운영 정보입니다. 빈 칸은 본문에 출력되지 않아요.</p>
        </div>
      </header>

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
