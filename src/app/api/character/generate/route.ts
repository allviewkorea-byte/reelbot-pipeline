import { NextRequest, NextResponse } from "next/server"
import fs from "fs"
import path from "path"
import { WavespeedImageAdapter } from "@/lib/wavespeed"

// ── Prompt builders ───────────────────────────────────────────────

const FULL_BODY_SUFFIX =
  `Full body shot from head to toe, including feet and shoes. ` +
  `Subject fits entirely within the frame with generous margin at top and bottom. ` +
  `Standing pose, every body part visible, do not crop any part of the body.`

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

function buildFrontPrompt(
  appearance: string,
  outfit: string,
  hair: string,
  accClause: string
): string {
  return (
    `Photorealistic full-body portrait of a Korean woman in her late 20s. ` +
    `Appearance: ${appearance}. ` +
    `Hair: ${hair}. ` +
    `Outfit: ${outfit}. ` +
    (accClause ? `Accessories: ${accClause} ` : ``) +
    `Front view, facing the camera directly, neutral expression, slight smile. ` +
    `White seamless studio background, sharp soft lighting, 4K detail. ` +
    FULL_BODY_SUFFIX
  )
}

function buildSidePrompt(outfit: string, hair: string, accClause: string): string {
  return (
    `The exact same Korean woman — same face, same ${hair} hairstyle, same ${outfit} outfit` +
    (accClause ? `, ${accClause}` : ``) +
    ` — side profile view, facing left 90 degrees. ` +
    `White seamless studio background, sharp soft lighting, 4K detail. ` +
    `Keep face and outfit identical to the reference image. ` +
    FULL_BODY_SUFFIX
  )
}

function buildBackPrompt(outfit: string, hair: string, accClause: string): string {
  return (
    `The exact same Korean woman — same ${hair} hairstyle, same ${outfit} outfit` +
    (accClause ? `, ${accClause}` : ``) +
    ` — back view, facing completely away from camera. ` +
    `White seamless studio background, sharp soft lighting, 4K detail. ` +
    `Keep hairstyle and outfit identical to the reference image. ` +
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

  const appearance = body.appearance?.trim() || "Korean idol-style beauty with fair porcelain skin, defined double eyelids, high nose bridge, small oval face, slim elegant proportions. 한국인 여성 몸매좋고 비율좋은 연예인상의 이쁜 외모"

  const outfit     = body.outfit?.trim()     || "casual travel outfit, comfortable t-shirt and jeans"
  const hair       = body.hair?.trim()       || "long wavy dark hair flowing past shoulders"

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
      prompt: buildFrontPrompt(appearance, outfit, hair, accClause),
      seed,
    })
    const sideBuf = await adapter.generate({
      prompt: buildSidePrompt(outfit, hair, accClause),
      seed,
    })
    const backBuf = await adapter.generate({
      prompt: buildBackPrompt(outfit, hair, accClause),
      seed,
    })

    const id  = Date.now().toString()
    const dir = path.join(process.cwd(), "public", "character-seeds", id)
    fs.mkdirSync(dir, { recursive: true })
    fs.writeFileSync(path.join(dir, "front.png"), frontBuf)
    fs.writeFileSync(path.join(dir, "side.png"),  sideBuf)
    fs.writeFileSync(path.join(dir, "back.png"),  backBuf)

    return NextResponse.json({
      success: true,
      id,
      images: {
        front: `/character-seeds/${id}/front.png`,
        side:  `/character-seeds/${id}/side.png`,
        back:  `/character-seeds/${id}/back.png`,
      },
    })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
