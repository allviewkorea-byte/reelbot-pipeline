import { NextRequest, NextResponse } from "next/server"
import OpenAI from "openai"

// /trends 의 AI 인사이트(/api/trends/youtube/analyze 결과)를 입력받아 시나리오
// 초안(제목 후보·설명·해시태그·권장 길이)을 GPT 로 생성한다. JSON only 강제 후 안전 파싱.

const openai = new OpenAI()

export interface ScenarioSuggestion {
  titles: string[]
  description: string
  hashtags: {
    category: string[]
    topic: string[]
    emotion: string[]
    target: string[]
    trend: string[]
  }
  duration: {
    format: "shorts" | "longform"
    minutes: number
  }
}

// POST /api/trends/scenario  body: { insights: object, category?: string, format?: string }
export async function POST(req: NextRequest) {
  if (!process.env.OPENAI_API_KEY) {
    return NextResponse.json(
      { success: false, error: "OPENAI_API_KEY가 설정되지 않았습니다 (서버 전용)" },
      { status: 500 },
    )
  }

  let body: { insights?: unknown; category?: string; format?: string }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ success: false, error: "Invalid JSON" }, { status: 400 })
  }

  const category = (body.category ?? "전체").trim() || "전체"
  const formatKind: "shorts" | "longform" = body.format === "shorts" ? "shorts" : "longform"
  const formatLabel = formatKind === "shorts" ? "쇼츠(≤180초)" : "롱폼"

  // insights 는 TrendAnalysis(summary/commonThemes/formatTraits/scenarioHints) 형태를
  // 기대하지만, 어떤 구조든 안전하게 직렬화해 프롬프트에 넣는다.
  let insightsText: string
  try {
    insightsText = JSON.stringify(body.insights ?? {}, null, 2).slice(0, 4000)
  } catch {
    insightsText = "{}"
  }
  if (insightsText === "{}" || insightsText === "null") {
    return NextResponse.json(
      { success: false, error: "시나리오 생성에 필요한 인사이트가 없습니다" },
      { status: 400 },
    )
  }

  const lengthHint =
    formatKind === "shorts"
      ? "쇼츠이므로 1분 이하(minutes 는 1)로 결정하라."
      : "롱폼이므로 콘텐츠 특성에 맞춰 2~15분 사이의 적절한 분 단위로 결정하라."

  const prompt =
    `너는 유튜브 콘텐츠 기획자다. 아래는 "${category}" 카테고리 ${formatLabel} 인기 영상의 AI 분석 인사이트(JSON)다.\n` +
    `이 인사이트를 바탕으로 ${formatLabel} 영상 시나리오 초안을 한국어로 만들어라.\n\n` +
    `[인사이트]\n${insightsText}\n\n` +
    `요구사항:\n` +
    `- 제목 후보 3~5개: Power Words(강력한 키워드)를 포함하고, 숫자형·감성어형·질문형을 섞어 다양하게.\n` +
    `- 영상 설명 첫 150자: "후크 → 핵심 내용 → CTA(행동 유도)" 순서로 자연스럽게 (150자 내외).\n` +
    `- 해시태그 5분류(카테고리/주제/감성/타겟/트렌드) 각 3~5개. # 기호 없이 단어만.\n` +
    `- 권장 영상 길이: 포맷 특징 기반. ${lengthHint}\n\n` +
    `반드시 아래 JSON 스키마만 출력하라(추가 텍스트·마크다운·코드펜스 금지):\n` +
    `{\n` +
    `  "titles": ["제목 후보 3~5개"],\n` +
    `  "description": "150자 내외 설명",\n` +
    `  "hashtags": { "category": [], "topic": [], "emotion": [], "target": [], "trend": [] },\n` +
    `  "duration": { "format": "${formatKind}", "minutes": 숫자 }\n` +
    `}`

  try {
    const response = await openai.chat.completions.create(
      {
        model: "gpt-4o",
        messages: [{ role: "user", content: prompt }],
        response_format: { type: "json_object" },
      },
      { timeout: 60_000 },
    )

    const content = response.choices[0]?.message?.content ?? "{}"
    let data: Record<string, unknown>
    try {
      data = JSON.parse(content)
    } catch {
      throw new Error("AI 응답을 해석하지 못했습니다")
    }

    const toStrArr = (v: unknown): string[] =>
      Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []

    const rawHashtags =
      data.hashtags && typeof data.hashtags === "object"
        ? (data.hashtags as Record<string, unknown>)
        : {}
    const rawDuration =
      data.duration && typeof data.duration === "object"
        ? (data.duration as Record<string, unknown>)
        : {}
    const minutesValue =
      typeof rawDuration.minutes === "number" && rawDuration.minutes > 0
        ? rawDuration.minutes
        : formatKind === "shorts"
          ? 1
          : 4

    const suggestion: ScenarioSuggestion = {
      titles: toStrArr(data.titles),
      description: typeof data.description === "string" ? data.description : "",
      hashtags: {
        category: toStrArr(rawHashtags.category),
        topic: toStrArr(rawHashtags.topic),
        emotion: toStrArr(rawHashtags.emotion),
        target: toStrArr(rawHashtags.target),
        trend: toStrArr(rawHashtags.trend),
      },
      // 쇼츠는 1분으로 고정(≤180초), 롱폼은 정수 분으로 보정.
      duration: {
        format: formatKind,
        minutes: formatKind === "shorts" ? 1 : Math.max(1, Math.round(minutesValue)),
      },
    }

    if (suggestion.titles.length === 0) {
      throw new Error("AI가 제목 후보를 생성하지 못했습니다")
    }

    return NextResponse.json({ success: true, suggestion })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
