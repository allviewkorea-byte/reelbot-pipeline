// 서버 전용 Supabase 클라이언트.
// secret key로 동작하므로 절대 클라이언트 번들에 노출되면 안 된다 (NEXT_PUBLIC_ 금지).
import { createClient, type SupabaseClient } from "@supabase/supabase-js"

export const CHARACTER_BUCKET = "character-seeds"
export const CHARACTER_TABLE = "characters"

let cached: SupabaseClient | null = null

// 환경변수가 없으면 호출 시점에 명확한 에러를 던진다 (빌드 타임 크래시 방지).
export function getSupabaseAdmin(): SupabaseClient {
  if (cached) return cached

  const url = process.env.SUPABASE_URL
  const secretKey = process.env.SUPABASE_SECRET_KEY
  if (!url || !secretKey) {
    throw new Error("SUPABASE_URL / SUPABASE_SECRET_KEY 환경변수가 설정되지 않았어요")
  }

  cached = createClient(url, secretKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  })
  return cached
}

// 버퍼 1장을 character-seeds 버킷에 업로드하고 공개 URL을 반환한다.
export async function uploadCharacterImage(
  objectPath: string,
  buffer: Buffer
): Promise<string> {
  const supabase = getSupabaseAdmin()
  const { error } = await supabase.storage
    .from(CHARACTER_BUCKET)
    .upload(objectPath, buffer, { contentType: "image/png", upsert: true })
  if (error) {
    throw new Error(`Supabase 이미지 업로드 실패: ${error.message}`)
  }
  const { data } = supabase.storage.from(CHARACTER_BUCKET).getPublicUrl(objectPath)
  return data.publicUrl
}
