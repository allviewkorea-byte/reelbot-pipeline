import { NextRequest, NextResponse } from "next/server"
import fs from "fs/promises"
import path from "path"

const LIBRARY_PATH = path.join(process.cwd(), "public", "character-library.json")

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

interface Character {
  id: string
  name: string
  createdAt: string
  config: CharacterConfig
  images: CharacterImages
}

interface Library {
  characters: Character[]
}

async function readLibrary(): Promise<Library> {
  try {
    const raw = await fs.readFile(LIBRARY_PATH, "utf-8")
    return JSON.parse(raw) as Library
  } catch {
    return { characters: [] }
  }
}

async function writeLibrary(lib: Library): Promise<void> {
  await fs.writeFile(LIBRARY_PATH, JSON.stringify(lib, null, 2), "utf-8")
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
    const character: Character = {
      id,
      name: name.trim(),
      createdAt: new Date().toISOString(),
      config,
      images,
    }

    const lib = await readLibrary()
    lib.characters.push(character)
    await writeLibrary(lib)

    return NextResponse.json({ success: true, character })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "알 수 없는 오류"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
