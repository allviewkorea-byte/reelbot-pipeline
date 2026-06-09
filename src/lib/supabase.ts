// 서버 전용 Supabase 클라이언트.
// secret key로 동작하므로 절대 클라이언트 번들에 노출되면 안 된다 (NEXT_PUBLIC_ 금지).
import { createClient, type SupabaseClient } from "@supabase/supabase-js"
import {
  DEFAULT_CHANNELS,
  channelToRow,
  rowToChannel,
  type Channel,
  type ChannelRow,
} from "./channels"

export const CHARACTER_BUCKET = "character-seeds"
export const CHARACTER_TABLE = "characters"
// 사연 트랙 전용 캐릭터(CharacterSpec + 시트 URL/앵커). 기존 travel 캐릭터
// (config/images, front/side/back)와 스키마가 달라 별도 테이블로 둔다.
export const SAYEON_CHARACTER_TABLE = "sayeon_characters"
export const CHANNELS_TABLE = "channels"

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

// ── 채널 영속화 (Postgres `channels` 테이블) ─────────────────────────

async function upsertChannels(channels: Channel[]): Promise<void> {
  const supabase = getSupabaseAdmin()
  const { error } = await supabase
    .from(CHANNELS_TABLE)
    .upsert(channels.map(channelToRow), { onConflict: "id" })
  if (error) throw new Error(`채널 저장 실패: ${error.message}`)
}

// 채널 목록 조회. 테이블이 비어 있으면(최초 1회) 기본 채널을 멱등(id 고정)으로
// 시드한 뒤 반환해 기존 데모 데이터를 보존한다.
export async function listChannels(): Promise<Channel[]> {
  const supabase = getSupabaseAdmin()
  const { data, error } = await supabase
    .from(CHANNELS_TABLE)
    .select("*")
    .order("created_at", { ascending: true })
  if (error) throw new Error(`채널 목록 조회 실패: ${error.message}`)

  const rows = (data ?? []) as ChannelRow[]
  if (rows.length === 0) {
    await upsertChannels(DEFAULT_CHANNELS)
    return DEFAULT_CHANNELS
  }
  return rows.map(rowToChannel)
}

export async function upsertChannel(channel: Channel): Promise<void> {
  await upsertChannels([channel])
}

export async function deleteChannelRow(id: string): Promise<void> {
  const supabase = getSupabaseAdmin()
  const { error } = await supabase.from(CHANNELS_TABLE).delete().eq("id", id)
  if (error) throw new Error(`채널 삭제 실패: ${error.message}`)
}
