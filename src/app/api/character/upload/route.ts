import { NextRequest, NextResponse } from "next/server"
import { getSupabaseAdmin, CHARACTER_TABLE, uploadCharacterImage } from "@/lib/supabase"

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData()
    const name = formData.get("name") as string
    const frontFile = formData.get("front") as File
    const sideFile = formData.get("side") as File
    const backFile = formData.get("back") as File

    if (!name || !frontFile || !sideFile || !backFile) {
      return NextResponse.json({ error: "Missing required fields" }, { status: 400 })
    }

    const id = `char_${Date.now()}`

    // Vercel 런타임 파일시스템은 읽기 전용이므로 Supabase Storage에 업로드한다.
    const toBuffer = async (file: File) => Buffer.from(await file.arrayBuffer())
    const [front, side, back] = await Promise.all([
      uploadCharacterImage(`${id}/front.png`, await toBuffer(frontFile)),
      uploadCharacterImage(`${id}/side.png`,  await toBuffer(sideFile)),
      uploadCharacterImage(`${id}/back.png`,  await toBuffer(backFile)),
    ])

    const createdAt = new Date().toISOString()
    const config = {
      appearance: "",
      outfit: "",
      accessories: { headwear: "", eyewear: "", bag: "", shoes: "", jewelry: [] },
      hair: "",
    }
    const images = { front, side, back }

    const supabase = getSupabaseAdmin()
    const { error } = await supabase
      .from(CHARACTER_TABLE)
      .insert({ id, name, created_at: createdAt, config, images })
    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 })
    }

    return NextResponse.json({
      success: true,
      character: { id, name, createdAt, config, images },
    })
  } catch (error) {
    console.error("Upload error:", error)
    return NextResponse.json({ error: "Failed to upload character" }, { status: 500 })
  }
}
