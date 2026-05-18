import { NextResponse } from "next/server"
import fs from "fs/promises"
import path from "path"

const LIBRARY_PATH = path.join(process.cwd(), "public", "character-library.json")

export async function GET() {
  try {
    const raw = await fs.readFile(LIBRARY_PATH, "utf-8")
    const lib = JSON.parse(raw) as { characters: { createdAt: string }[] }
    lib.characters.sort(
      (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
    )
    return NextResponse.json({ characters: lib.characters })
  } catch {
    return NextResponse.json({ characters: [] })
  }
}
