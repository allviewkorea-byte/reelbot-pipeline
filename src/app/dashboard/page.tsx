"use client"

import { useState } from "react"
import { TrendingUp, Zap, Clock } from "lucide-react"
import { STATS, CHANNELS, CHART_DATA, PIPELINE_JOBS } from "@/lib/mock-data"
import { RevenueChart } from "@/components/dashboard/revenue-chart"

const TABS = [
  { id: "all", label: "전체 채널" },
  { id: "bangkok", label: "방콕 여행" },
  { id: "tokyo", label: "도쿄 일상" },
  { id: "europe", label: "유럽 감성" },
]

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState("all")

  const activeChannel = CHANNELS.find((c) => c.id === activeTab)

  return (
    <div className="flex flex-1 flex-col gap-6 p-6 overflow-auto">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-foreground">대시보드</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">
          AI 여행 유튜브 자동화 파이프라인 관리
        </p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-4 gap-4">
        {STATS.map((stat) => (
          <div
            key={stat.id}
            className="rounded-xl border border-border bg-card p-4"
          >
            <p className="text-xs text-muted-foreground">{stat.label}</p>
            <p
              className="mt-2 text-3xl font-bold text-foreground"
              style={{ fontFamily: "var(--font-geist-mono)" }}
            >
              {stat.value}
            </p>
            <div className="mt-2 flex items-center gap-1">
              {stat.positive && (
                <TrendingUp className="h-3 w-3 text-emerald-400" />
              )}
              <span className="text-xs text-emerald-400 font-medium">
                {stat.change}
              </span>
              {stat.changeLabel && (
                <span className="text-xs text-muted-foreground">
                  {stat.changeLabel}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Channel Tabs */}
      <div className="flex gap-2">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`rounded-full px-4 py-1.5 text-sm font-medium transition-all ${
              activeTab === tab.id
                ? "bg-primary text-primary-foreground"
                : "bg-card border border-border text-muted-foreground hover:text-foreground"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Channel Grid — 전체 탭 only */}
      {activeTab === "all" && (
        <div className="grid grid-cols-3 gap-4">
          {CHANNELS.map((ch) => (
            <button
              key={ch.id}
              onClick={() => setActiveTab(ch.id)}
              className="rounded-xl border border-border bg-card p-4 text-left transition-all hover:border-primary/40 hover:bg-card/80"
            >
              {/* Name + Badge */}
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-foreground">
                  {ch.name}
                </span>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    ch.statusVariant === "active"
                      ? "bg-emerald-500/15 text-emerald-400"
                      : "bg-sky-500/15 text-sky-400"
                  }`}
                >
                  {ch.status}
                </span>
              </div>

              {/* Stats row */}
              <div className="mt-3 flex gap-4">
                <div>
                  <p className="text-xs text-muted-foreground">월 수익</p>
                  <p
                    className="text-base font-bold text-foreground"
                    style={{ fontFamily: "var(--font-geist-mono)" }}
                  >
                    ${ch.revenue}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">구독자</p>
                  <p
                    className="text-base font-bold text-foreground"
                    style={{ fontFamily: "var(--font-geist-mono)" }}
                  >
                    {ch.subscribers}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">영상</p>
                  <p
                    className="text-base font-bold text-foreground"
                    style={{ fontFamily: "var(--font-geist-mono)" }}
                  >
                    {ch.videos}개
                  </p>
                </div>
              </div>

              {/* Progress bar */}
              <div className="mt-3">
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">
                    목표 ${ch.goal} 달성률
                  </span>
                  <span className="text-xs font-medium text-foreground">
                    {ch.revenue}%
                  </span>
                </div>
                <div className="h-1.5 rounded-full bg-secondary overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${ch.revenue}%`,
                      backgroundColor: ch.color,
                    }}
                  />
                </div>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Single channel detail — non-all tabs */}
      {activeTab !== "all" && activeChannel && (
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold text-foreground">
                {activeChannel.name}
              </h2>
              <p className="text-xs text-muted-foreground mt-0.5">채널 상세 데이터</p>
            </div>
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                activeChannel.statusVariant === "active"
                  ? "bg-emerald-500/15 text-emerald-400"
                  : "bg-sky-500/15 text-sky-400"
              }`}
            >
              {activeChannel.status}
            </span>
          </div>
          <div className="mt-4 grid grid-cols-3 gap-4">
            {[
              { label: "월 수익", value: `$${activeChannel.revenue}` },
              { label: "구독자", value: activeChannel.subscribers },
              { label: "총 영상", value: `${activeChannel.videos}개` },
            ].map((item) => (
              <div key={item.label} className="rounded-lg bg-secondary/40 p-3">
                <p className="text-xs text-muted-foreground">{item.label}</p>
                <p
                  className="mt-1 text-xl font-bold text-foreground"
                  style={{ fontFamily: "var(--font-geist-mono)" }}
                >
                  {item.value}
                </p>
              </div>
            ))}
          </div>
          <div className="mt-4">
            <div className="mb-1.5 flex justify-between text-xs">
              <span className="text-muted-foreground">목표 ${activeChannel.goal} 달성률</span>
              <span className="font-medium text-foreground">{activeChannel.revenue}%</span>
            </div>
            <div className="h-2 rounded-full bg-secondary overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${activeChannel.revenue}%`,
                  backgroundColor: activeChannel.color,
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Bottom row: Chart + Pipeline */}
      <div className="grid grid-cols-5 gap-4">
        {/* Revenue Chart */}
        <div className="col-span-3 rounded-xl border border-border bg-card p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-foreground">
              채널별 월 수익 비교
            </h2>
            <div className="flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1">
              <span className="text-xs text-muted-foreground">합계</span>
              <span
                className="text-xs font-bold text-foreground"
                style={{ fontFamily: "var(--font-geist-mono)" }}
              >
                $127
              </span>
            </div>
          </div>
          <RevenueChart data={CHART_DATA} />
        </div>

        {/* Pipeline Panel */}
        <div className="col-span-2 rounded-xl border border-border bg-card p-5">
          <div className="mb-4 flex items-center gap-2">
            <Zap className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold text-foreground">
              지금 진행 중
            </h2>
          </div>
          <div className="flex flex-col gap-3">
            {PIPELINE_JOBS.map((job) => (
              <div key={job.id} className="rounded-lg bg-secondary/40 p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-foreground truncate">
                      {job.title}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5 truncate">
                      {job.subtitle}
                    </p>
                  </div>
                  {job.status === "waiting" ? (
                    <div className="flex items-center gap-1 shrink-0">
                      <Clock className="h-3 w-3 text-muted-foreground" />
                      <span className="text-xs text-muted-foreground">준비</span>
                    </div>
                  ) : (
                    <span
                      className="text-xs font-bold text-foreground shrink-0"
                      style={{ fontFamily: "var(--font-geist-mono)" }}
                    >
                      {job.progress}%
                    </span>
                  )}
                </div>
                <div className="mt-2 h-1 rounded-full bg-secondary overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      job.status === "running" ? "bg-primary" : "bg-muted"
                    }`}
                    style={{ width: `${job.progress}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
