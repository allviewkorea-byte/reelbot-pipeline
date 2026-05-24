import { NextRequest, NextResponse } from "next/server"
import OpenAI from "openai"
import type { TrendItem } from "@/lib/youtube"

// NOTE: 스펙은 /api/trends/analyze 를 제안했으나 그 경로는 이미 백엔드 프록시
// 라우트로 존재하며 channels/[id]·scenario 페이지가 사용 중이라 덮어쓰면 회귀가
// 발생한다. 충돌을 피해 YouTube 탐색 기능 전용으로 이 경로에 둔다.

const openai = new OpenAI()

export interface TrendAnalysis {
  summary: string
  commonThemes: string[]
  formatTraits: string[]
  scenarioHints: string[]
}

// POST /api/trends/youtube/analyze  body: { items: TrendItem[], category?, format? }
export async function POST(req: NextRequest) {
  if (!process.env.OPENAI_API_KEY) {
    return NextResponse.json(
      { success: false, error: "OPENAI_API_KEY가 설정되지 않았습니다 (서버 전용)" },
      { status: 500 },
    )
  }

  let body: { items?: TrendItem[]; category?: string; format?: string }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ success: false, error: "Invalid JSON" }, { status: 400 })
  }

  const items = Array.isArray(body.items) ? body.items.slice(0, 40) : []
  if (items.length === 0) {
    return NextResponse.json(
      { success: false, error: "분석할 트렌드 항목이 없습니다" },
      { status: 400 },
    )
  }
  const category = (body.category ?? "전체").trim() || "전체"
  const format = body.format === "shorts" ? "쇼츠(≤180초)" : "롱폼"

  const list = items
    .map(
      (it, i) =>
        `${i + 1}. "${it.title}" — ${it.channelTitle} · 조회수 ${it.viewCount.toLocaleString()} · ` +
        `좋아요 ${it.likeCount.toLocaleString()} · 댓글 ${it.commentCount.toLocaleString()} · 길이 ${it.durationSec}초`,
    )
    .join("\n")

  const prompt =
    `너는 유튜브 콘텐츠 전략가다. 아래는 "${category}" 카테고리의 ${format} 인기 영상 목록이다.\n` +
    `이 데이터를 분석해 한국어 인사이트를 작성하라.\n\n` +
    `${list}\n\n` +
    `반드시 아래 JSON 스키마만 출력하라(추가 텍스트·마크다운·코드펜스 금지):\n` +
    `{\n` +
    `  "summary": "전체 트렌드를 2~3문장으로 요약",\n` +
    `  "commonThemes": ["공통 주제·소재 3~6개"],\n` +
    `  "formatTraits": ["잘 먹히는 포맷·길이·제목/썸네일 특징 3~6개"],\n` +
    `  "scenarioHints": ["이 트렌드로 만들 수 있는 구체적 영상 아이디어 3~6개"]\n` +
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

    const analysis: TrendAnalysis = {
      summary: typeof data.summary === "string" ? data.summary : "",
      commonThemes: toStrArr(data.commonThemes),
      formatTraits: toStrArr(data.formatTraits),
      scenarioHints: toStrArr(data.scenarioHints),
    }

    return NextResponse.json({ success: true, analysis })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
