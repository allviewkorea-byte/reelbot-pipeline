import { NextRequest, NextResponse } from 'next/server'
import OpenAI from 'openai'

const openai = new OpenAI()

export async function POST(request: NextRequest) {
  try {
    const { channel, spots, duration, mode } = await request.json()

    const match = duration?.match(/(\d+)(?=장면)/) || duration?.match(/\((\d+)씬\)/)
    const sceneCount = match ? parseInt(match[1] ?? match[0]) : 12

    const prompt = `당신은 유튜브 여행 채널 시나리오 전문 작가입니다.
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