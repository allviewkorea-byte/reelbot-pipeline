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
import type { ContentPlan } from "./content-plan"
import type { TrendRankingRow, ChannelVideosRow } from "./trend-concepts"

export const CHARACTER_BUCKET = "character-seeds"
export const CONTENT_PLANS_TABLE = "content_plans"
export const CHARACTER_TABLE = "characters"
// 사연 트랙 전용 캐릭터(CharacterSpec + 시트 URL/앵커). 기존 travel 캐릭터
// (config/images, front/side/back)와 스키마가 달라 별도 테이블로 둔다.
export const SAYEON_CHARACTER_TABLE = "sayeon_characters"
export const CHANNELS_TABLE = "channels"
export const CHANNEL_STATUS_TABLE = "channel_status"
export const TREND_RANKINGS_TABLE = "trend_rankings"
export const TREND_CHANNEL_VIDEOS_TABLE = "trend_channel_videos"

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

// ── 콘텐츠 캘린더 (Postgres `content_plans` 테이블) ───────────────────
// ⚠️ 테이블 생성은 코드가 하지 않는다(SQL 은 PR 설명 참고, 대표가 Supabase 에서 실행).
// 조회는 테이블 미존재/에러/환경변수 미설정에도 빈 배열로 방어 → 캘린더가 안 깨짐.

export async function listContentPlans(
  channelId: string,
  fromDate?: string,
  toDate?: string,
): Promise<ContentPlan[]> {
  try {
    const supabase = getSupabaseAdmin()
    let q = supabase
      .from(CONTENT_PLANS_TABLE)
      .select("*")
      .eq("channel_id", channelId)
      .order("date", { ascending: true })
    if (fromDate) q = q.gte("date", fromDate)
    if (toDate) q = q.lte("date", toDate)
    const { data, error } = await q
    if (error) return [] // 테이블 없음/조회 실패 → 빈 캘린더(앱 안 깨짐)
    return (data ?? []) as ContentPlan[]
  } catch {
    return [] // SUPABASE_* 미설정 등 → 빈 배열 방어
  }
}

export async function upsertContentPlan(plan: ContentPlan): Promise<void> {
  const supabase = getSupabaseAdmin()
  const { error } = await supabase
    .from(CONTENT_PLANS_TABLE)
    .upsert(plan, { onConflict: "id" })
  if (error) {
    // Supabase 에러 전문을 로그+메시지에 드러내 다음 원인 파악을 쉽게(삼키지 않음).
    console.error("[content-plans] upsert 실패:", {
      message: error.message,
      details: error.details,
      hint: error.hint,
      code: error.code,
    })
    const extra = error.details ? ` | ${error.details}` : ""
    throw new Error(`콘텐츠 플랜 저장 실패: ${error.message}${extra}`)
  }
}

export async function deleteContentPlan(id: string): Promise<void> {
  const supabase = getSupabaseAdmin()
  const { error } = await supabase.from(CONTENT_PLANS_TABLE).delete().eq("id", id)
  if (error) throw new Error(`콘텐츠 플랜 삭제 실패: ${error.message}`)
}

// 여러 플랜 일괄 upsert(롤링 자동 생성용 — 30일×최대3슬롯을 한 번에). 빈 배열이면 no-op.
export async function upsertContentPlans(plans: ContentPlan[]): Promise<void> {
  if (plans.length === 0) return
  const supabase = getSupabaseAdmin()
  const { error } = await supabase.from(CONTENT_PLANS_TABLE).upsert(plans, { onConflict: "id" })
  if (error) {
    console.error("[content-plans] 일괄 upsert 실패:", {
      message: error.message,
      details: error.details,
      hint: error.hint,
      code: error.code,
    })
    const extra = error.details ? ` | ${error.details}` : ""
    throw new Error(`콘텐츠 플랜 일괄 저장 실패: ${error.message}${extra}`)
  }
}

// ── 채널 가동 상태 (Postgres `channel_status` 테이블) ─────────────────
// ⚠️ 테이블 생성·GRANT 는 코드가 하지 않는다(SQL 은 PR 설명 참고, 대표가 Supabase 에서 실행).
//    GRANT 누락 시 permission denied 500 — content_plans 때의 함정이라 반드시 부여.
// 조회는 테이블 미존재/에러/환경변수 미설정에도 안전 기본값(false) → 앱 안 깨짐.

export async function getChannelStatus(channelId: string): Promise<boolean> {
  try {
    const supabase = getSupabaseAdmin()
    const { data, error } = await supabase
      .from(CHANNEL_STATUS_TABLE)
      .select("is_active")
      .eq("channel_id", channelId)
      .maybeSingle()
    if (error) return false // 테이블 없음/조회 실패 → 기본 OFF
    return Boolean(data?.is_active)
  } catch {
    return false // SUPABASE_* 미설정 등 → 기본 OFF
  }
}

export async function setChannelStatus(channelId: string, isActive: boolean): Promise<void> {
  const supabase = getSupabaseAdmin()
  const { error } = await supabase
    .from(CHANNEL_STATUS_TABLE)
    .upsert(
      { channel_id: channelId, is_active: isActive, updated_at: new Date().toISOString() },
      { onConflict: "channel_id" },
    )
  if (error) {
    // Supabase 에러 전문을 로그+메시지에 드러내 원인 파악을 쉽게(삼키지 않음).
    console.error("[channel-status] upsert 실패:", {
      message: error.message,
      details: error.details,
      hint: error.hint,
      code: error.code,
    })
    const extra = error.details ? ` | ${error.details}` : ""
    throw new Error(`채널 상태 저장 실패: ${error.message}${extra}`)
  }
}

// ── 트렌드 컨셉 랭킹 캐시 (Postgres `trend_rankings` 테이블) ──────────
// ⚠️ 테이블 생성·GRANT 는 코드가 하지 않는다(SQL 은 PR 설명, 대표가 Supabase 에서 실행).
//    GRANT 누락 시 permission denied — 반드시 부여. 조회는 미존재/에러에도 null 방어.

export async function getTrendRanking(channelId: string, date: string): Promise<TrendRankingRow | null> {
  try {
    const supabase = getSupabaseAdmin()
    const { data, error } = await supabase
      .from(TREND_RANKINGS_TABLE)
      .select("*")
      .eq("channel_id", channelId)
      .eq("date", date)
      .maybeSingle()
    if (error) return null // 테이블 없음/조회 실패 → 캐시 미스로 처리
    return (data as TrendRankingRow) ?? null
  } catch {
    return null // SUPABASE_* 미설정 등 → 캐시 미스
  }
}

export async function saveTrendRanking(row: TrendRankingRow): Promise<void> {
  const supabase = getSupabaseAdmin()
  const { error } = await supabase
    .from(TREND_RANKINGS_TABLE)
    .upsert(row, { onConflict: "id" })
  if (error) {
    console.error("[trend-rankings] upsert 실패:", {
      message: error.message,
      details: error.details,
      hint: error.hint,
      code: error.code,
    })
    const extra = error.details ? ` | ${error.details}` : ""
    throw new Error(`트렌드 랭킹 저장 실패: ${error.message}${extra}`)
  }
}

// ── 채널별 부분결과 (Postgres `trend_channel_videos` 테이블) ─────────
// 7c 채널별 분할 수집의 임시 저장. ⚠️ 테이블·GRANT 는 대표가 SQL 로 실행(아래 PR).
// 조회는 미존재/에러에도 빈 배열 방어.

export async function saveChannelVideos(row: ChannelVideosRow): Promise<void> {
  const supabase = getSupabaseAdmin()
  const { error } = await supabase
    .from(TREND_CHANNEL_VIDEOS_TABLE)
    .upsert(row, { onConflict: "id" })
  if (error) {
    console.error("[trend-channel-videos] upsert 실패:", {
      message: error.message,
      details: error.details,
      hint: error.hint,
      code: error.code,
    })
    const extra = error.details ? ` | ${error.details}` : ""
    throw new Error(`채널 부분결과 저장 실패: ${error.message}${extra}`)
  }
}

export async function listChannelVideos(channelId: string, date: string): Promise<ChannelVideosRow[]> {
  try {
    const supabase = getSupabaseAdmin()
    const { data, error } = await supabase
      .from(TREND_CHANNEL_VIDEOS_TABLE)
      .select("*")
      .eq("channel_id", channelId)
      .eq("date", date)
    if (error) return []
    return (data ?? []) as ChannelVideosRow[]
  } catch {
    return []
  }
}

// 오래된 부분결과 정리(finalize 후 호출). 실패해도 무시(베스트 에포트).
export async function deleteOldChannelVideos(channelId: string, beforeDate: string): Promise<void> {
  try {
    const supabase = getSupabaseAdmin()
    await supabase
      .from(TREND_CHANNEL_VIDEOS_TABLE)
      .delete()
      .eq("channel_id", channelId)
      .lt("date", beforeDate)
  } catch {
    /* 정리는 실패해도 무시 */
  }
}
