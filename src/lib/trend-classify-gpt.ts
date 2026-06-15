// GPT 컨셉 분류(서버 전용) — concepts 라우트와 cron finalize 가 공유. (7c 에서 추출)
// 동작 동일: 제목 목록을 9컨셉으로 분류 + 컨셉별 근거. 키 없음/실패 시 null → 호출부 폴백.
import OpenAI from "openai"
import { CONTENT_CONCEPTS } from "./content-plan"
import { normalizeConcept, type ClassifiedItem, type ClassifyInput } from "./trend-concepts"

export async function classifyWithGPT(
  items: ClassifyInput[],
): Promise<{ classified: ClassifiedItem[]; reasons: Record<string, string> } | null> {
  if (!process.env.OPENAI_API_KEY) return null
  try {
    const openai = new OpenAI()
    const list = items.map((it, i) => `${i + 1}. ${it.title}`).join("\n")
    const prompt =
      `너는 한국 사연(감성 스토리) 콘텐츠 분류 전문가다. 아래는 사연 채널들의 최근 영상 제목 목록이다.\n` +
      `각 영상을 다음 9개 컨셉 중 정확히 하나로 분류하라(컨셉 문자열은 정확히 이 목록 그대로): ${CONTENT_CONCEPTS.join(", ")}.\n\n` +
      `[컨셉 정의 — 엄격히 따르라]\n` +
      `- 가족: 부모-자식, 형제·남매, 시댁·고부·처가, 상속·유산, 사별(가족의 죽음), 가족 절연 등 가족 관계 전반(폭넓게).\n` +
      `- 이별: '연인' 간 이별·헤어짐·환승·재회만. 사별·가족 절연은 이별이 아니라 가족.\n` +
      `- 복수: 되갚음·응징·사이다·뒤통수 갚기·고소/신고로 혼내주기.\n` +
      `- 우정/배신: 친구·지인 사이의 우정 또는 배신·손절·뒤통수.\n` +
      `- 연애: 연인·썸·고백·짝사랑·소개팅 등 결혼 전 연애 관계(헤어짐 자체는 '이별').\n` +
      `- 직장/돈: 회사·상사·동료·취업·퇴사, 돈·빚·사기 등 금전 문제.\n` +
      `- 감동: 따뜻함·눈물·효도·선행 등 긍정적 감동(특정 갈등 컨셉에 안 들어갈 때).\n` +
      `- 반전: 결말 반전·알고보니·정체·소름 등 반전이 핵심인 사연.\n` +
      `- 기타: 위 8개 중 어디에도 정말 해당하지 않을 때만.\n\n` +
      `[규칙] 애매하다고 '기타'로 던지지 마라. 반드시 위 8개 중 가장 가까운 컨셉으로 분류하고, 정말 어디에도 안 맞을 때만 '기타'. ` +
      `예: 사별·아픈 부모 돌봄·시댁 갈등=가족, 연인 이별만=이별.\n\n` +
      `[제목 목록]\n${list}\n\n` +
      `반드시 아래 JSON 만 출력(마크다운·설명·코드펜스 금지):\n` +
      `{\n` +
      `  "items": [{"i": 1, "concept": "가족"}],  // 위 모든 번호를 빠짐없이 포함\n` +
      `  "reasons": {"가족": "이 컨셉이 지금 왜 도는지 한 줄"}  // 등장한 컨셉만, 한국어 한 줄\n` +
      `}`
    const resp = await openai.chat.completions.create(
      {
        model: "gpt-4o-mini",
        messages: [{ role: "user", content: prompt }],
        response_format: { type: "json_object" },
      },
      { timeout: 60_000 },
    )
    const content = resp.choices[0]?.message?.content ?? "{}"
    const data = JSON.parse(content) as {
      items?: Array<{ i?: number; concept?: string }>
      reasons?: Record<string, unknown>
    }
    const arr = Array.isArray(data.items) ? data.items : []
    const classified: ClassifiedItem[] = items.map((it, idx) => {
      const found = arr.find((a) => Number(a?.i) === idx + 1)
      const concept = normalizeConcept(typeof found?.concept === "string" ? found.concept : "기타")
      return { concept, title: it.title, viewCount: it.viewCount }
    })
    const reasons: Record<string, string> = {}
    if (data.reasons && typeof data.reasons === "object") {
      for (const [k, v] of Object.entries(data.reasons)) {
        if (typeof v === "string" && (CONTENT_CONCEPTS as readonly string[]).includes(k)) {
          reasons[k] = v
        }
      }
    }
    return { classified, reasons }
  } catch {
    return null // 키 무효·쿼터·파싱 실패 등 → 폴백
  }
}
