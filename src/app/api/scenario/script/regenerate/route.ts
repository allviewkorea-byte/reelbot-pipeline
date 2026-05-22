import { NextRequest, NextResponse } from 'next/server'
import OpenAI from 'openai'
import { TIMEOUT } from '@/lib/api-timeout'

const openai = new OpenAI()

interface RegenerateBody {
  scene: { title: string; description: string }
  sceneIndex: number
  totalScenes: number
  format: 'shorts' | 'longform'
  targetLengthSec: number
  trendContext?: {
    powerWords?: string[]
    titleCandidates?: string[]
    category?: string
  }
  characterContext?: { name: string; tone?: string }
  channelContext?: { stack?: string; track?: string }
}

// 씬 위치(첫/중간/끝)에 따라 후크/메인/CTA 톤을 자동 분기한다.
function roleGuide(index: number, total: number): string {
  if (index === 0) return '이 씬은 첫 씬입니다. 3초 안에 시선을 사로잡는 강력한 후크로 작성하세요.'
  if (index >= total - 1) return '이 씬은 마지막 씬입니다. 구독/좋아요/저장을 자연스럽게 유도하는 CTA로 작성하세요.'
  return '이 씬은 중간 씬입니다. 핵심 메시지를 자연스러운 흐름으로 전달하세요.'
}

function buildPrompt(body: RegenerateBody): string {
  const { scene, sceneIndex, totalScenes, format, targetLengthSec, trendContext, characterContext, channelContext } = body
  const isShorts = format === 'shorts'
  const lines: string[] = [
    '당신은 유튜브 영상 내레이션 작가입니다.',
    '아래 씬에 어울리는 자연스러운 한국어 내레이션(TTS용 멘트)을 작성하세요.',
    '',
    `씬 제목: ${scene.title}`,
    `씬 설명: ${scene.description}`,
    `씬 위치: ${sceneIndex + 1} / ${totalScenes}`,
    `권장 발화 길이: 약 ${targetLengthSec}초`,
    '',
    roleGuide(sceneIndex, totalScenes),
    isShorts ? '형식: 숏폼 — 임팩트 있게 짧고 강하게.' : '형식: 롱폼 — 충분히 자세하게.',
    '한국어 발화 속도는 1초당 약 4~5자. 권장 길이에 맞춰 분량을 조절하세요.',
  ]

  if (characterContext?.name) {
    const tone = characterContext.tone ? ` (${characterContext.tone} 톤)` : ''
    lines.push(`출연 캐릭터: ${characterContext.name}${tone}처럼 말하듯 작성하세요.`)
  }
  if (channelContext?.stack || channelContext?.track) {
    lines.push(`채널 톤 가이드: ${[channelContext.stack, channelContext.track].filter(Boolean).join(' / ')}`)
  }
  if (trendContext?.powerWords?.length) {
    lines.push(`참고용 Power Words(강요 금지, 자연스럽게만): ${trendContext.powerWords.slice(0, 8).join(', ')}`)
  }
  if (trendContext?.category) {
    lines.push(`카테고리: ${trendContext.category}`)
  }

  lines.push(
    '',
    '반드시 아래 JSON 형식만 응답 (마크다운, 설명 없이):',
    '{"script":"실제 내레이션 텍스트(한국어)","durationSec":12}',
  )
  return lines.join('\n')
}

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as RegenerateBody
    if (!body?.scene?.title) {
      return NextResponse.json({ error: 'scene is required' }, { status: 400 })
    }

    const response = await openai.chat.completions.create({
      model: 'gpt-4o-mini',
      messages: [{ role: 'user', content: buildPrompt(body) }],
      response_format: { type: 'json_object' },
    }, { timeout: TIMEOUT.QUICK })

    const content = response.choices[0].message.content ?? '{}'
    const data = JSON.parse(content)

    const script = typeof data.script === 'string' ? data.script : ''
    const durationSec =
      typeof data.durationSec === 'number' ? data.durationSec : body.targetLengthSec

    if (!script) throw new Error('Invalid response format')

    return NextResponse.json({ script, durationSec })
  } catch (error) {
    console.error('Script regeneration error:', error)
    return NextResponse.json(
      { error: 'Failed to regenerate script' },
      { status: 500 },
    )
  }
}
