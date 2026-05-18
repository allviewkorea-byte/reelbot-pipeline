import { NextRequest, NextResponse } from "next/server"
import OpenAI from "openai"
import fs from "fs"
import path from "path"

const FRONT_PROMPT = (appearance: string, outfit: string, hair: string) =>
  `Photorealistic full-body portrait of a Korean woman in her late 20s. ` +
  `Appearance: ${appearance}. ` +
  `Hair: ${hair}. ` +
  `Outfit: ${outfit}. ` +
  `Front view, facing the camera directly, neutral expression, slight smile. ` +
  `White seamless studio background, sharp soft lighting, 4K detail.`

const SIDE_PROMPT = (outfit: string, hair: string) =>
  `The exact same Korean woman — same face, same ${hair} hairstyle, same ${outfit} outfit — ` +
  `side profile view, facing left 90 degrees, full body. ` +
  `White seamless studio background, sharp soft lighting, 4K detail. ` +
  `Keep face and outfit identical to the reference image.`

const BACK_PROMPT = (outfit: string, hair: string) =>
  `The exact same Korean woman — same ${hair} hairstyle, same ${outfit} outfit — ` +
  `back view, facing completely away from camera, full body. ` +
  `White seamless studio background, sharp soft lighting, 4K detail. ` +
  `Keep hairstyle and outfit identical to the reference image.`

async function generateImage(client: OpenAI, prompt: string): Promise<Buffer> {
  const response = await client.images.generate({
    model: "gpt-image-1",
    prompt,
    size: "1024x1536",
    quality: "medium",
    n: 1,
  })
  const b64 = response.data?.[0]?.b64_json
  if (!b64) throw new Error("No image data returned")
  return Buffer.from(b64, "base64")
}

async function generateImageFromRef(
  client: OpenAI,
  prompt: string,
  refBuffer: Buffer
): Promise<Buffer> {
  const { toFile } = await import("openai")
  const refFile = await toFile(refBuffer, "reference.png", { type: "image/png" })

  const response = await client.images.edit({
    model: "gpt-image-1",
    image: refFile,
    prompt,
    size: "1024x1536",
    quality: "medium",
    n: 1,
  })
  const b64 = response.data?.[0]?.b64_json
  if (!b64) throw new Error("No image data returned from edit")
  return Buffer.from(b64, "base64")
}

export async function POST(req: NextRequest) {
  const apiKey = process.env.OPENAI_API_KEY
  if (!apiKey) {
    return NextResponse.json(
      { success: false, error: "OPENAI_API_KEY not configured" },
      { status: 500 }
    )
  }

  let body: { appearance?: string; outfit?: string; hair?: string }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ success: false, error: "Invalid JSON" }, { status: 400 })
  }

  const appearance = body.appearance?.trim() || "slim build, fair skin, bright eyes"
  const outfit = body.outfit?.trim() || "trendy street fashion"
  const hair = body.hair?.trim() || "long wavy dark hair"

  const client = new OpenAI({ apiKey })

  try {
    // Step 1: front (text only)
    const frontBuf = await generateImage(client, FRONT_PROMPT(appearance, outfit, hair))

    // Step 2: side (reference = front)
    const sideBuf = await generateImageFromRef(client, SIDE_PROMPT(outfit, hair), frontBuf)

    // Step 3: back (reference = front)
    const backBuf = await generateImageFromRef(client, BACK_PROMPT(outfit, hair), frontBuf)

    // Save to public/character-seeds/[timestamp]/
    const id = Date.now().toString()
    const dir = path.join(process.cwd(), "public", "character-seeds", id)
    fs.mkdirSync(dir, { recursive: true })

    fs.writeFileSync(path.join(dir, "front.png"), frontBuf)
    fs.writeFileSync(path.join(dir, "side.png"), sideBuf)
    fs.writeFileSync(path.join(dir, "back.png"), backBuf)

    return NextResponse.json({
      success: true,
      id,
      images: {
        front: `/character-seeds/${id}/front.png`,
        side: `/character-seeds/${id}/side.png`,
        back: `/character-seeds/${id}/back.png`,
      },
    })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
