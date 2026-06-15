import { NextRequest, NextResponse } from "next/server"
import { BAEKGOM_CHANNEL_ID, type ContentPlan } from "@/lib/content-plan"
import { getChannelStatus, listContentPlans, upsertContentPlan } from "@/lib/supabase"
import { todayKST } from "@/lib/trend-concepts"
import { isAuthorizedCron } from "@/lib/cron-auth"

// 2단계: 가동 중인 채널에서 캘린더(content_plans)의 due 슬롯을 시각 맞춰 자동 제작.
// 외부 크론(cron-job.org)이 매시간 호출 → 가동확인 → 일일상한 → due 1개 → 그 컨셉을
// topic 으로 흰곰 제작 → status='done'. privacy 는 /api/sayeon/generate 프록시가 모드로
// 주입(#129). 제작은 Railway 비동기(job_id 즉시). 1회 1개(순차)·멱등.
export const dynamic = "force-dynamic"
export const maxDuration = 60 // generate-script(gpt) 호출 여유(기본 10초)

// 폭주 방지 일일 상한(하루 최대 슬롯 3개 구조라 자연 상한이지만 안전장치로 명시).
const DAILY_PRODUCE_CAP = 3

// 현재 KST 'HH:MM' (scheduled_time 문자열과 직접 비교용).
function nowHHMMKST(): string {
  return new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(11, 16)
}

export async function GET(req: NextRequest) {
  if (!isAuthorizedCron(req)) {
    return NextResponse.json({ success: false, error: "unauthorized" }, { status: 401 })
  }

  const origin = req.nextUrl.origin
  const channelId = BAEKGOM_CHANNEL_ID

  try {
    // ① 가동 게이트 — 가동 중인 채널만 자동 제작(중단=자연 정지 스위치).
    const { isActive } = await getChannelStatus(channelId)
    if (!isActive) {
      return NextResponse.json({ success: true, skipped: "not_active" })
    }

    // ② 오늘 plans 조회(상한·due 판단).
    const today = todayKST()
    const plans = await listContentPlans(channelId, today, today)

    const doneToday = plans.filter((p) => p.status === "done").length
    if (doneToday >= DAILY_PRODUCE_CAP) {
      return NextResponse.json({ success: true, skipped: "cap_reached", doneToday })
    }

    // ③ due 슬롯 1개 — status=planned & scheduled_time 지남. 가장 이른 시각 1개(순차).
    const now = nowHHMMKST()
    const due = plans
      .filter((p) => p.status === "planned" && p.scheduled_time && p.scheduled_time <= now)
      .sort((a, b) => (a.scheduled_time || "").localeCompare(b.scheduled_time || ""))
    const slot = due[0]
    if (!slot) {
      return NextResponse.json({ success: true, skipped: "no_due" })
    }

    // ④ 컨셉 = 슬롯 concept → topic(캘린더가 컨셉 보유 → pick-topic 불필요).
    const topic = slot.concept || ""

    // ⑤ 캐릭터(흰곰 기본) — default 라우트가 시드(없으면 생성). 시트 재사용/스펙.
    const charJson = await fetch(`${origin}/api/sayeon/characters/default`, { cache: "no-store" })
      .then((r) => r.json())
      .catch(() => null)
    const char = charJson?.character
    if (!char || (!(char.sheet_url && char.anchor) && !char.spec)) {
      return NextResponse.json({ success: false, error: "기본 캐릭터를 확보하지 못함" }, { status: 502 })
    }

    // ⑥ 사연 자동작성(컨셉 topic). ⑦ 영상 제작(privacy 는 generate 프록시가 모드로 주입 #129).
    const scriptJson = await fetch(`${origin}/api/sayeon/generate-script`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(topic ? { topic } : {}),
    }).then((r) => r.json())
    const script: string = typeof scriptJson?.script === "string" ? scriptJson.script : ""
    if (!script) {
      return NextResponse.json({ success: false, error: "사연 자동작성 실패" }, { status: 502 })
    }

    const genBody: Record<string, unknown> = { script }
    if (char.sheet_url && char.anchor) {
      genBody.sheet_url = char.sheet_url
      genBody.anchor = char.anchor
    } else {
      genBody.character_spec = char.spec
    }
    const genJson = await fetch(`${origin}/api/sayeon/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(genBody),
    }).then((r) => r.json())
    const jobId: string | undefined = typeof genJson?.job_id === "string" ? genJson.job_id : undefined
    if (!jobId) {
      // 트리거 실패 → done 마킹하지 않음(다음 회차 재시도).
      return NextResponse.json({ success: false, error: "제작 트리거 실패" }, { status: 502 })
    }

    // ⑧ job_id 확인 후 done 마킹(멱등 — planned 만 선별하므로 재호출 시 재선택 안 됨).
    try {
      const done: ContentPlan = { ...slot, status: "done" }
      await upsertContentPlan(done)
    } catch (e) {
      // 마킹 실패는 로깅만 — 일일 상한이 폭주를 막는다.
      console.error("[cron/produce-due] done 마킹 실패(상한이 폭주 차단):", e)
    }

    return NextResponse.json({
      success: true,
      produced: { date: slot.date, slot: slot.slot, concept: slot.concept, scheduled_time: slot.scheduled_time, jobId },
    })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
