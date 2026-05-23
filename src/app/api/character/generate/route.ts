import { NextRequest, NextResponse } from "next/server"
import { WavespeedImageAdapter } from "@/lib/wavespeed"
import { uploadCharacterImage } from "@/lib/supabase"

// ── Prompt builders ───────────────────────────────────────────────

const FULL_BODY_SUFFIX =
  `Full body shot from head to toe, including feet and shoes. ` +
  `Subject fits entirely within the frame with generous margin at top and bottom. ` +
  `Standing pose, every body part visible, do not crop any part of the body.`

// 단일 인물 강제 — 측면에서 인물이 2명 그려지는 아티팩트를 막는다.
const SOLO_SUBJECT_CLAUSE =
  `Exactly one person only, a single solo subject, only one figure in the entire frame. ` +
  `No other people, no duplicate of the person, no twins, no split screen, ` +
  `no side-by-side comparison, no reflection, no mirror image.`

function buildAccessoryClause(acc: {
  headwear: string
  eyewear: string
  bag: string
  shoes: string
  jewelry: string[]
}): string {
  const parts: string[] = []
  if (acc.headwear) parts.push(acc.headwear)
  if (acc.eyewear)  parts.push(acc.eyewear)
  if (acc.bag)      parts.push(acc.bag)
  if (acc.shoes)    parts.push(acc.shoes)
  if (acc.jewelry.length) parts.push(acc.jewelry.join(", "))
  return parts.length ? parts.join(", ") + "." : ""
}

type Gender = "female" | "male"

function subjectFor(gender: Gender): string {
  return gender === "male" ? "Korean man in his late 20s" : "Korean woman in her late 20s"
}

// 3면이 동일 인물·동일 의상으로 나오도록, 외모/헤어/의상/액세서리 묘사를
// 세 프롬프트에 글자 그대로 동일하게 넣는다. 면별로 달라지는 건 시점 문구뿐이다.
function buildCharacterBlock(
  appearance: string,
  outfit: string,
  hair: string,
  accClause: string,
  gender: Gender
): string {
  return (
    `Photorealistic full-body portrait of a ${subjectFor(gender)}. ` +
    `Appearance: ${appearance}. ` +
    `Hair: ${hair}. ` +
    `Outfit: ${outfit}. ` +
    (accClause ? `Accessories: ${accClause} ` : ``)
  )
}

const STUDIO_SUFFIX = `White seamless studio background, sharp soft lighting, 4K detail. `

function buildFrontPrompt(
  appearance: string,
  outfit: string,
  hair: string,
  accClause: string,
  gender: Gender
): string {
  return (
    buildCharacterBlock(appearance, outfit, hair, accClause, gender) +
    `Front view, facing the camera directly, neutral expression, slight smile. ` +
    STUDIO_SUFFIX +
    SOLO_SUBJECT_CLAUSE + ` ` +
    FULL_BODY_SUFFIX
  )
}

function buildSidePrompt(
  appearance: string,
  outfit: string,
  hair: string,
  accClause: string,
  gender: Gender
): string {
  return (
    buildCharacterBlock(appearance, outfit, hair, accClause, gender) +
    `Side profile view, the person turned to face left at 90 degrees, neutral expression. ` +
    STUDIO_SUFFIX +
    SOLO_SUBJECT_CLAUSE + ` ` +
    FULL_BODY_SUFFIX
  )
}

function buildBackPrompt(
  appearance: string,
  outfit: string,
  hair: string,
  accClause: string,
  gender: Gender
): string {
  return (
    buildCharacterBlock(appearance, outfit, hair, accClause, gender) +
    `Back view, the person facing completely away from the camera, ` +
    `back of the head and body visible, face not visible. ` +
    STUDIO_SUFFIX +
    SOLO_SUBJECT_CLAUSE + ` ` +
    FULL_BODY_SUFFIX
  )
}

// ── Route handler ─────────────────────────────────────────────────

interface AccessoriesBody {
  headwear?: string
  eyewear?: string
  bag?: string
  shoes?: string
  jewelry?: string[]
}

interface RequestBody {
  appearance?: string
  outfit?: string
  accessories?: AccessoriesBody
  hair?: string
  gender?: Gender
}

export async function POST(req: NextRequest) {
  const apiKey = process.env.WAVESPEED_API_KEY
  if (!apiKey) {
    return NextResponse.json(
      { success: false, error: "WAVESPEED_API_KEY not configured" },
      { status: 500 }
    )
  }

  let body: RequestBody
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ success: false, error: "Invalid JSON" }, { status: 400 })
  }

  const gender: Gender = body.gender === "male" ? "male" : "female"

  const defaultAppearance =
    gender === "male"
      ? "Korean idol-style handsome man with fair clear skin, defined double eyelids, sharp jawline, tall slim proportions. 한국인 남성 비율좋고 잘생긴 연예인상의 외모"
      : "Korean idol-style beauty with fair porcelain skin, defined double eyelids, high nose bridge, small oval face, slim elegant proportions. 한국인 여성 몸매좋고 비율좋은 연예인상의 이쁜 외모"
  const defaultHair =
    gender === "male" ? "short black cropped hair" : "long wavy dark hair flowing past shoulders"

  const appearance = body.appearance?.trim() || defaultAppearance

  const outfit     = body.outfit?.trim()     || "casual travel outfit, comfortable t-shirt and jeans"
  const hair       = body.hair?.trim()       || defaultHair

  const acc: Required<AccessoriesBody> & { jewelry: string[] } = {
    headwear: body.accessories?.headwear || "",
    eyewear:  body.accessories?.eyewear  || "",
    bag:      body.accessories?.bag      || "",
    shoes:    body.accessories?.shoes    || "wearing white sneakers",
    jewelry:  body.accessories?.jewelry  || [],
  }
  const accClause = buildAccessoryClause(acc)

  const adapter = new WavespeedImageAdapter(apiKey)
  // 앞/측/뒷면 3장에 동일한 seed를 사용해 같은 캐릭터 외모를 유지한다.
  const seed = Math.floor(Math.random() * 1_000_000)

  try {
    const frontBuf = await adapter.generate({
      prompt: buildFrontPrompt(appearance, outfit, hair, accClause, gender),
      seed,
    })
    const sideBuf = await adapter.generate({
      prompt: buildSidePrompt(appearance, outfit, hair, accClause, gender),
      seed,
    })
    const backBuf = await adapter.generate({
      prompt: buildBackPrompt(appearance, outfit, hair, accClause, gender),
      seed,
    })

    const id = Date.now().toString()
    // Vercel 런타임 파일시스템은 읽기 전용이므로 Supabase Storage에 업로드한다.
    const [front, side, back] = await Promise.all([
      uploadCharacterImage(`${id}/front.png`, frontBuf),
      uploadCharacterImage(`${id}/side.png`,  sideBuf),
      uploadCharacterImage(`${id}/back.png`,  backBuf),
    ])

    return NextResponse.json({
      success: true,
      id,
      images: { front, side, back },
    })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
