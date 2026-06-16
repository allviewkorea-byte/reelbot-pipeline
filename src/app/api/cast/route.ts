import { NextRequest, NextResponse } from "next/server"
import { API_BASE } from "@/lib/proxy"
import { TIMEOUT } from "@/lib/api-timeout"
import { BAEKGOM_CHANNEL_ID } from "@/lib/content-plan"
import { getSupabaseAdmin, SAYEON_CAST_TABLE } from "@/lib/supabase"

// GET /api/cast — 사연 동물 캐스트(8) 통합 조회.
//  · 바이블 메타 + 아스펙트 URL(있으면) + colors + relative_height = 백엔드(/sayeon/cast, R2 소유).
//  · 승인 상태(status) = Supabase(sayeon_cast 테이블, 프론트 소유).
// 둘을 role 로 병합해 한 목록으로 내려준다. 어느 한쪽이 비어도 화면이 깨지지 않게 방어.
export const dynamic = "force-dynamic"

interface CastEntry {
  role: string
  name: string
  animal: string
  personality: string
  colors: string[]
  relative_height: number
  aspects: Record<string, string>
  sheet_url: string | null
  status: "draft" | "approved"
}

// Supabase sayeon_cast 에서 role→status 맵. 테이블 미존재/오류/미설정 → 빈 맵(전부 draft).
async function loadStatusMap(): Promise<Record<string, "draft" | "approved">> {
  try {
    const supabase = getSupabaseAdmin()
    const { data, error } = await supabase.from(SAYEON_CAST_TABLE).select("role, status")
    if (error) return {}
    const map: Record<string, "draft" | "approved"> = {}
    for (const row of data ?? []) {
      const r = row as { role?: string; status?: string }
      if (r.role) map[r.role] = r.status === "approved" ? "approved" : "draft"
    }
    return map
  } catch {
    return {}
  }
}

export async function GET(req: NextRequest) {
  const channelId = req.nextUrl.searchParams.get("channelId") || BAEKGOM_CHANNEL_ID
  try {
    const [castRes, statusMap] = await Promise.all([
      fetch(`${API_BASE}/sayeon/cast?channel_id=${encodeURIComponent(channelId)}`, {
        cache: "no-store",
        signal: AbortSignal.timeout(TIMEOUT.QUICK),
      }).then((r) => r.json()),
      loadStatusMap(),
    ])

    const bible = Array.isArray(castRes?.cast) ? castRes.cast : []
    const cast: CastEntry[] = bible.map((c: Omit<CastEntry, "status">) => ({
      role: c.role,
      name: c.name,
      animal: c.animal,
      personality: c.personality,
      colors: Array.isArray(c.colors) ? c.colors : [],
      relative_height: typeof c.relative_height === "number" ? c.relative_height : 0.6,
      aspects: c.aspects && typeof c.aspects === "object" ? c.aspects : {},
      sheet_url: c.sheet_url ?? null,
      status: statusMap[c.role] ?? "draft",
    }))
    return NextResponse.json({ success: true, cast })
  } catch {
    // 백엔드 미연결 등 → 빈 목록(화면은 안내 문구 표시).
    return NextResponse.json({ success: true, cast: [] })
  }
}
