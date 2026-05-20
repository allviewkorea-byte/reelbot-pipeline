import { NextRequest, NextResponse } from 'next/server'
import OpenAI from 'openai'

const openai = new OpenAI()

// 카테고리별 씬 구성 템플릿. "여행"은 기존 동선 중심 방식을 그대로 유지한다.
const CATEGORY_TEMPLATES: Record<string, { role: string; structure: string }> = {
  "여행":              { role: "여행", structure: "여행지를 동선 순서대로 자연스럽게 이동하며 먹방·체험·감탄·이동 씬을 다양하게 배치" },
  "음식·맛집":         { role: "음식·맛집 리뷰", structure: "방문 → 주문 → 시식 → 리뷰 순서로 구성" },
  "라이프스타일":      { role: "라이프스타일 브이로그", structure: "하루 일과를 따라가는 자연스러운 브이로그 흐름으로 구성" },
  "패션·뷰티":         { role: "패션·뷰티", structure: "소개 → 시연/연출 → 디테일 클로즈업 → 추천 마무리 순서로 구성" },
  "교육·정보":         { role: "교육·정보", structure: "문제 제기 → 설명 → 예시 → 정리 순서로 구성" },
  "유머·엔터테인먼트": { role: "유머·엔터테인먼트", structure: "훅 → 상황 설정 → 반전 → 마무리 순서로 구성" },
  "동기부여":          { role: "동기부여", structure: "공감 → 문제 직시 → 핵심 메시지 → 행동 촉구 순서로 구성" },
  "일상":              { role: "일상 브이로그", structure: "하루 일과를 따라가는 자연스러운 브이로그 흐름으로 구성" },
  "비즈니스":          { role: "비즈니스·자기계발", structure: "핵심 주장 → 근거 → 사례 → 실행 팁 순서로 구성" },
}

// 기존 여행 시나리오 프롬프트 (100% 보존)
function buildTravelPrompt(args: {
  sceneCount: number
  channel: string
  spots: string
  duration: string
  mode: string
}): string {
  const { sceneCount, channel, spots, duration, mode } = args
  return `당신은 유튜브 여행 채널 시나리오 전문 작가입니다.
아래 조건으로 ${sceneCount}개 씬의 시나리오를 만들어주세요.

채널: ${channel}
여행지: ${spots}
영상 길이: ${duration}
모드: ${mode}

규칙:
- 각 씬은 10초
- 첫 씬은 강렬한 훅(시청자 시선 즉시 고정)으로 시작
- 여행지를 순서대로 자연스럽게 이동
- 먹방/체험/감탄/이동 씬 다양하게 배치
- 마지막 씬은 구독/좋아요 CTA 아웃트로

반드시 아래 JSON 형식만 응답 (마크다운, 설명 없이):
{"scenes":[{"id":"S01","title":"씬 제목 — 부제","sec":10,"desc":"씬 핵심 설명 30자 이내"}]}`
}

// 범용 카테고리 시나리오 프롬프트
function buildGenericPrompt(args: {
  category: string
  sceneCount: number
  secPerScene: number
  topic: string
  tone: string
  format: string
  modelCount: string
}): string {
  const { category, sceneCount, secPerScene, topic, tone, format, modelCount } = args
  const tpl = CATEGORY_TEMPLATES[category] ?? CATEGORY_TEMPLATES["일상"]
  return `당신은 유튜브 ${tpl.role} 채널 시나리오 전문 작가입니다.
아래 조건으로 ${sceneCount}개 씬의 시나리오를 만들어주세요.

주제 카테고리: ${category}
소재: ${topic || "(자유 주제)"}
감정·톤: ${tone}
영상 형식: ${format}
출연 모델 수: ${modelCount}

구성 방식: ${tpl.structure}

규칙:
- 각 씬은 ${secPerScene}초 내외
- 첫 씬은 강렬한 훅(시청자 시선 즉시 고정)으로 시작
- "${tone}" 감정·톤을 영상 전체에 일관되게 유지
- 위 "구성 방식"의 흐름을 따라 씬을 배치
- 마지막 씬은 구독/좋아요 CTA 아웃트로

반드시 아래 JSON 형식만 응답 (마크다운, 설명 없이):
{"scenes":[{"id":"S01","title":"씬 제목 — 부제","sec":${secPerScene},"desc":"씬 핵심 설명 30자 이내"}]}`
}

function parseSceneCount(raw: unknown, duration?: string): number {
  if (typeof raw === "number" && raw > 0) return Math.round(raw)
  const match = duration?.match(/(\d+)(?=장면)/) || duration?.match(/\((\d+)씬\)/)
  return match ? parseInt(match[1] ?? match[0]) : 12
}

function parseDurationMin(raw: unknown, duration?: string): number {
  if (typeof raw === "number" && raw > 0) return raw
  const m = duration?.match(/(\d+)\s*분/)
  return m ? parseInt(m[1]) : 4
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const {
      category,
      topic,
      tone,
      format,
      durationMin,
      sceneCount: sceneCountRaw,
      modelCount,
      // 레거시 여행 필드 (하위 호환)
      channel,
      spots,
      duration,
      mode,
    } = body

    const sceneCount = parseSceneCount(sceneCountRaw, duration)
    const isTravel = !category || category === "여행"

    let prompt: string
    if (isTravel) {
      // 기존 여행 시나리오 동작을 그대로 보존
      prompt = buildTravelPrompt({
        sceneCount,
        channel: channel ?? "여행 채널",
        spots: spots || topic || "주요 명소",
        duration: duration ?? `${parseDurationMin(durationMin, duration)}분`,
        mode: mode ?? "B 하이브리드",
      })
    } else {
      const minutes = parseDurationMin(durationMin, duration)
      const secPerScene = Math.max(3, Math.round((minutes * 60) / sceneCount))
      prompt = buildGenericPrompt({
        category,
        sceneCount,
        secPerScene,
        topic: topic ?? "",
        tone: tone ?? "밝고 경쾌",
        format: format === "short" ? "숏폼(9:16)" : format === "long" ? "롱폼(16:9)" : (format ?? "롱폼(16:9)"),
        modelCount: modelCount ?? "1인",
      })
    }

    const response = await openai.chat.completions.create({
      model: 'gpt-4o-mini',
      messages: [{ role: 'user', content: prompt }],
      response_format: { type: 'json_object' },
    })

    const content = response.choices[0].message.content ?? '{}'
    const data = JSON.parse(content)

    if (!Array.isArray(data.scenes)) throw new Error('Invalid response format')

    return NextResponse.json({ success: true, scenes: data.scenes })
  } catch (error) {
    console.error('Scenario generation error:', error)
    return NextResponse.json(
      { error: 'Failed to generate scenario' },
      { status: 500 }
    )
  }
}
