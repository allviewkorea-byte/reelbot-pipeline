import { NextResponse } from "next/server"
import { getSupabaseAdmin, CHARACTER_TABLE } from "@/lib/supabase"

interface CharacterRow {
  id: string
  name: string
  created_at: string
  config: unknown
  images: unknown
}

export async function GET() {
  try {
    const supabase = getSupabaseAdmin()
    const { data, error } = await supabase
      .from(CHARACTER_TABLE)
      .select("id, name, created_at, config, images")
      .order("created_at", { ascending: false })
    if (error) {
      return NextResponse.json({ characters: [] })
    }

    const characters = (data as CharacterRow[]).map((row) => ({
      id: row.id,
      name: row.name,
      createdAt: row.created_at,
      config: row.config,
      images: row.images,
    }))
    return NextResponse.json({ characters })
  } catch {
    return NextResponse.json({ characters: [] })
  }
}
