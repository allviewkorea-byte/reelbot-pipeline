import { NextRequest, NextResponse } from "next/server"
import { getSupabaseAdmin, CHARACTER_TABLE } from "@/lib/supabase"

interface CharacterConfig {
  appearance: string
  outfit: string
  accessories: {
    headwear: string
    eyewear: string
    bag: string
    shoes: string
    jewelry: string[]
  }
  hair: string
}

interface CharacterImages {
  front: string
  side: string
  back: string
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const { name, config, images } = body as {
      name?: string
      config?: CharacterConfig
      images?: CharacterImages
    }

    if (!name?.trim()) {
      return NextResponse.json({ success: false, error: "캐릭터 이름이 필요해요" }, { status: 400 })
    }
    if (!config || !images) {
      return NextResponse.json({ success: false, error: "config와 images가 필요해요" }, { status: 400 })
    }

    const id = `char_${Date.now()}`
    const createdAt = new Date().toISOString()

    const supabase = getSupabaseAdmin()
    const { error } = await supabase
      .from(CHARACTER_TABLE)
      .insert({ id, name: name.trim(), created_at: createdAt, config, images })
    if (error) {
      return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    }

    return NextResponse.json({
      success: true,
      character: { id, name: name.trim(), createdAt, config, images },
    })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "알 수 없는 오류"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
