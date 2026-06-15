"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { toast } from "sonner"
import {
  Play,
  Square,
  Clapperboard,
  Wand2,
  Loader2,
  Eye,
  DollarSign,
  Users,
  Video,
} from "lucide-react"
import { PLATFORM_BADGE, PLATFORM_LABELS, TRACK_BADGE, TRACK_LABELS } from "@/lib/channels"
import { BAEKGOM_CHANNEL_ID } from "@/lib/content-plan"
import { CHANNEL_STATUS_EVENT, type ChannelStatusDetail, type ChannelMode } from "@/lib/channel-status"
import {
  generateSayeon,
  generateSayeonScript,
  getDefaultSayeonCharacter,
  pollJobStatus,
  type SayeonGenerateParams,
} from "@/lib/api"
import { RecentVideosMarquee } from "@/components/dashboard/RecentVideosMarquee"
import { PipelineNodeGraph } from "@/components/dashboard/PipelineNodeGraph"
import { TrendPanel } from "@/components/dashboard/TrendPanel"
import { ContentCalendar } from "@/components/dashboard/ContentCalendar"

// 백곰의 실화보고서 = 유일 운영 채널(트랙 A, /sayeon 엔진). 채널 DB 레코드 없이 고정 표시.
// 관제 대시보드는 UI-2 채널 대시보드 골격(헤더+제어바+지표+최근영상)을 재사용(복제)한다.
const BAEKGOM = {
  name: "백곰의 실화보고서",
  platform: "youtube" as const,
  track: "auto" as const,
}

// 월간 지표 — 백곰 실데이터 연동 전이라 플레이스홀더("—"). UI-5 캘린더/연동에서 연결.
const METRICS = [
  { label: "월 조회수", value: "—", icon: Eye },
  { label: "월 수익", value: "—", icon: DollarSign },
  { label: "구독자", value: "—", icon: Users },
  { label: "평균 조회수", value: "—", icon: Video },
]

export default function DashboardPage() {
  // 가동 상태(ON/OFF) — channel_status 저장값. 토글 1개로 제어, 헤더 뱃지·사이드바에 반영.
  // 실제 자동 업로드(스케줄러 연동)는 후속 작업. 지금은 상태 저장·표시까지.
  const [isActive, setIsActive] = useState(false)
  const [busy, setBusy] = useState(false)
  // 업로드 모드 — auto=공개 / semi(반자동)=비공개. 기본 semi(안전). 제작 시 privacy 결정.
  const [mode, setMode] = useState<ChannelMode>("semi")
  const [modeBusy, setModeBusy] = useState(false)
  // 트렌드 패널 + 월간 계획서 공유 펼침 상태(짝으로 동시 펼침/접힘). 기본 접힘.
  const [panelExpanded, setPanelExpanded] = useState(false)
  const togglePanels = () => setPanelExpanded((v) => !v)

  // 마운트 시 현재 상태 로드. setState 는 비동기 콜백에서만(effect 본문 직접 호출 회피).
  useEffect(() => {
    let alive = true
    fetch(`/api/channel-status?channelId=${BAEKGOM_CHANNEL_ID}`)
      .then((r) => r.json())
      .then((d) => {
        if (!alive) return
        setIsActive(Boolean(d?.isActive))
        setMode(d?.mode === "auto" ? "auto" : "semi")
      })
      .catch(() => {
        /* 실패 → 기본(OFF·반자동) 유지 */
      })
    return () => {
      alive = false
    }
  }, [])

  // 업로드 모드 토글(auto↔semi). 저장만 — 사이드바와 무관해 이벤트는 발행 안 함.
  const toggleMode = async () => {
    if (modeBusy) return
    const next: ChannelMode = mode === "auto" ? "semi" : "auto"
    setModeBusy(true)
    try {
      const res = await fetch("/api/channel-status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channelId: BAEKGOM_CHANNEL_ID, mode: next }),
      })
      const d = await res.json()
      if (res.ok && d?.success) setMode(next)
    } catch {
      /* 실패 → 유지 */
    } finally {
      setModeBusy(false)
    }
  }

  // 즉석 제작 — 진행 중이면 버튼 비활성. 진행 중인 job 이 있으면(새로고침 포함) 반영.
  const [producing, setProducing] = useState(false)
  useEffect(() => {
    let stop = () => {}
    fetch("/api/jobs/active")
      .then((r) => r.json())
      .then((d) => {
        if (d && typeof d.job_id === "string" && (d.status === "running" || d.status === "pending")) {
          setProducing(true)
          stop = pollJobStatus(d.job_id, (s) => {
            if (s.status === "completed" || s.status === "failed") setProducing(false)
          })
        }
      })
      .catch(() => {})
    return () => stop()
  }, [])

  // 대시보드 제작 트리거 — 화면 안 거치고 [자동 생성]과 동일한 호출을 한다:
  // 백곰 기본 캐릭터(is_default) 로드 → 랜덤 컨셉 사연 자동작성 → 영상 제작.
  // 캐릭터는 [자동 생성]과 똑같이 getDefaultSayeonCharacter 가 책임진다(별도 발명 X,
  // 여자20대 폴백으로 때우지 않음 — 백곰이 is_default 여야 함). privacy 는 프록시가 모드로 주입(#129).
  const produce = async () => {
    if (producing) return
    setProducing(true)
    try {
      const char = await getDefaultSayeonCharacter()
      if (!char) {
        toast.error("백곰 기본 캐릭터를 불러오지 못했습니다. 사연 제작 화면에서 한 번 제작해 기본 캐릭터를 만들어 주세요.")
        setProducing(false)
        return
      }
      // 사연 자동작성(랜덤 컨셉) — [자동 생성]처럼 화자 성별/나이만 힌트로 전달.
      const { script } = await generateSayeonScript({
        character: char.spec ? { gender: char.spec.gender, age: char.spec.age } : null,
      })
      // [자동 생성] runGenerate 와 동일: 시트 있으면 재사용, 없으면 스펙으로 시트 생성.
      const params: SayeonGenerateParams = { script }
      if (char.sheet_url && char.anchor) {
        params.sheet_url = char.sheet_url
        params.anchor = char.anchor
      } else if (char.spec) {
        params.character_spec = char.spec
      }
      const { job_id } = await generateSayeon(params)
      toast.success("제작을 시작했습니다 — 파이프라인에서 진행 상황을 확인하세요.")
      pollJobStatus(job_id, (s) => {
        if (s.status === "completed") {
          setProducing(false)
          toast.success("영상 제작 완료")
        } else if (s.status === "failed") {
          setProducing(false)
          toast.error(`제작 실패: ${s.error || "알 수 없는 오류"}`)
        }
      })
    } catch (e) {
      setProducing(false)
      toast.error(e instanceof Error ? e.message : "제작 시작 실패")
    }
  }

  // 시작↔중단 토글: 저장(POST) 성공 시 상태 갱신 + 사이드바 즉시 동기화 이벤트 발행.
  const toggle = async () => {
    if (busy) return
    const next = !isActive
    setBusy(true)
    try {
      const res = await fetch("/api/channel-status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channelId: BAEKGOM_CHANNEL_ID, isActive: next }),
      })
      const d = await res.json()
      if (res.ok && d?.success) {
        setIsActive(next)
        const detail: ChannelStatusDetail = { channelId: BAEKGOM_CHANNEL_ID, isActive: next }
        window.dispatchEvent(new CustomEvent(CHANNEL_STATUS_EVENT, { detail }))
      }
    } catch {
      /* 실패 → 상태 유지 */
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-hidden p-4">
      {/* 헤더 — 채널명+뱃지(왼쪽) / 사연 제작·가동 토글(오른쪽). NEXT UP 줄은 제거됨. */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold text-foreground truncate">{BAEKGOM.name}</h1>
            <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${PLATFORM_BADGE[BAEKGOM.platform]}`}>
              {PLATFORM_LABELS[BAEKGOM.platform]}
            </span>
            <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${TRACK_BADGE[BAEKGOM.track]}`}>
              {TRACK_LABELS[BAEKGOM.track]}
            </span>
            {/* 가동 상태 뱃지 — 토글/사이드바와 동일 상태. ON=emerald(맥동), OFF=muted */}
            <span
              className={`flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors duration-200 ${
                isActive ? "bg-emerald-500/15 text-emerald-400" : "bg-secondary/50 text-muted-foreground"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  isActive ? "bg-emerald-500 animate-pulse" : "bg-muted-foreground/50"
                }`}
              />
              {isActive ? "가동 중" : "대기 중"}
            </span>
          </div>
          <p className="mt-0.5 text-sm text-muted-foreground">운영 채널 관제 대시보드</p>
        </div>

        {/* 액션 — 업로드 모드 토글 + 사연 제작 열기 + 가동 시작↔중단 토글 */}
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
          {/* 업로드 모드 — auto(공개)↔semi(비공개) 스위치. 제작 시 이 모드로 유튜브 privacy 결정. */}
          <button
            onClick={toggleMode}
            disabled={modeBusy}
            role="switch"
            aria-checked={mode === "auto"}
            title="자동=유튜브 공개 업로드 / 반자동=비공개 업로드"
            className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-2 text-xs font-medium transition-colors hover:border-primary/40 disabled:opacity-60"
          >
            <span className={mode === "auto" ? "text-emerald-400" : "text-muted-foreground"}>
              {mode === "auto" ? "자동·공개" : "반자동·비공개"}
            </span>
            <span
              className={`relative h-4 w-7 shrink-0 rounded-full transition-colors ${
                mode === "auto" ? "bg-emerald-600" : "bg-secondary"
              }`}
            >
              <span
                className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all ${
                  mode === "auto" ? "left-3.5" : "left-0.5"
                }`}
              />
            </span>
          </button>
          {/* 즉석 제작 — 화면 안 거치고 랜덤 컨셉으로 바로 제작. 진행 중 비활성. */}
          <button
            onClick={produce}
            disabled={producing}
            className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-60"
          >
            {producing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
            {producing ? "제작 중…" : "지금 제작"}
          </button>
          {/* 백곰의 실제 제작 진입점: /sayeon 으로만 이동(파라미터 없음, CLAUDE.md 2단계 원칙) */}
          <Link
            href="/sayeon"
            className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
          >
            <Clapperboard className="h-4 w-4" />
            사연 제작 열기
          </Link>
          {/* 가동 토글 — OFF→[▶ 시작](emerald), ON→[■ 중단](red). 상태 저장(channel_status).
              #112 가동상태 로직(GET/POST + 사이드바 동기화) 그대로 유지. */}
          <button
            onClick={toggle}
            disabled={busy}
            aria-pressed={isActive}
            className={`flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium transition-all duration-200 disabled:opacity-60 ${
              isActive
                ? "border border-red-500/30 text-red-400 hover:bg-red-500/10"
                : "bg-emerald-600 text-white shadow-sm hover:opacity-90"
            }`}
          >
            {isActive ? <Square className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            {isActive ? "중단" : "시작"}
          </button>
        </div>
      </div>

      {/* 월간 지표 줄 (UI-2 지표 재사용, 값은 플레이스홀더) */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {METRICS.map((s) => (
          <div key={s.label} className="rounded-xl border border-border bg-card p-2.5">
            <div className="flex items-center gap-2 text-muted-foreground">
              <s.icon className="h-4 w-4" />
              <span className="text-xs">{s.label}</span>
            </div>
            <p className="mt-1 text-base font-bold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
              {s.value}
            </p>
          </div>
        ))}
      </div>

      {/* 좌우 한 줄 — 왼쪽 트렌드 분석 / 오른쪽 월간계획서·오늘콘텐츠. 정확히 5:5(반반). 같은 높이.
          펼침 상태는 공유(panelExpanded): 어느 버튼을 눌러도 둘 다 동시에 펼침/접힘. */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {/* 트렌드 분석(왼쪽) — 빈 그릇(준비 중). 실제 엔진은 다음 PR. (가짜 데이터 없음) */}
        <div className="[&>div]:h-full">
          <TrendPanel open={panelExpanded} onToggle={togglePanels} />
        </div>
        {/* 콘텐츠 캘린더(오른쪽) — 접힘=오늘의 콘텐츠(3슬롯), 펼침=월간 계획서 */}
        <div className="[&>div]:h-full">
          <ContentCalendar monthOpen={panelExpanded} onToggleMonth={togglePanels} />
        </div>
      </div>

      {/* 파이프라인 노드그래프 — 활성 job 실시간 점등(UI-4a). /api/jobs/active 폴링. */}
      <PipelineNodeGraph />

      {/* 최근 업로드 영상 — 플랫폼 탭 + 우→좌 자동 마퀴(UI-3). 더미 데이터, 실연동은 UI-3b. */}
      <RecentVideosMarquee />
    </div>
  )
}
