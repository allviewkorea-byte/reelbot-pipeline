import { NextRequest, NextResponse } from 'next/server';
import { writeFile, mkdir, readFile } from 'fs/promises';
import { existsSync } from 'fs';
import path from 'path';

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const name = formData.get('name') as string;
    const frontFile = formData.get('front') as File;
    const sideFile = formData.get('side') as File;
    const backFile = formData.get('back') as File;

    if (!name || !frontFile || !sideFile || !backFile) {
      return NextResponse.json(
        { error: 'Missing required fields' },
        { status: 400 }
      );
    }

    // Generate unique ID
    const id = `char_${Date.now()}`;
    const seedDir = path.join(process.cwd(), 'public', 'character-seeds', id);

    // Create directory
    await mkdir(seedDir, { recursive: true });

    // Save files
    const files = [
      { file: frontFile, name: 'front.png' },
      { file: sideFile, name: 'side.png' },
      { file: backFile, name: 'back.png' },
    ];

    for (const { file, name: fileName } of files) {
      const bytes = await file.arrayBuffer();
      const buffer = Buffer.from(bytes);
      await writeFile(path.join(seedDir, fileName), buffer);
    }

    // Update character-library.json
    const libraryPath = path.join(process.cwd(), 'public', 'character-library.json');
    let characters = [];

    if (existsSync(libraryPath)) {
      const content = await readFile(libraryPath, 'utf-8');
      characters = JSON.parse(content);
    }

    const newCharacter = {
      id,
      name,
      createdAt: new Date().toISOString(),
      config: {
        appearance: '',
        outfit: '',
        accessories: {},
        hair: '',
      },
      images: {
        front: `/character-seeds/${id}/front.png`,
        side: `/character-seeds/${id}/side.png`,
        back: `/character-seeds/${id}/back.png`,
      },
    };

    characters.unshift(newCharacter);
    await writeFile(libraryPath, JSON.stringify(characters, null, 2));

    return NextResponse.json({ success: true, character: newCharacter });
  } catch (error) {
    console.error('Upload error:', error);
    return NextResponse.json(
      { error: 'Failed to upload character' },
      { status: 500 }
    );
  }
}