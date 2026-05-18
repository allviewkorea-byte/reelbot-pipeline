import { NextRequest, NextResponse } from "next/server"
import fs from "fs/promises"
import path from "path"

const LIBRARY_PATH = path.join(process.cwd(), "public", "character-library.json")

interface Library {
  characters: { id: string }[]
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

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params

    const lib = await readLibrary()
    const before = lib.characters.length
    lib.characters = lib.characters.filter((c) => c.id !== id)

    if (lib.characters.length === before) {
      return NextResponse.json({ success: false, error: "캐릭터를 찾을 수 없어요" }, { status: 404 })
    }

    await writeLibrary(lib)

    const seedDir = path.join(process.cwd(), "public", "character-seeds", id)
    try {
      await fs.rm(seedDir, { recursive: true, force: true })
    } catch {
      // 폴더가 없어도 메타데이터 삭제는 성공으로 처리
    }

    return NextResponse.json({ success: true })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "알 수 없는 오류"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
