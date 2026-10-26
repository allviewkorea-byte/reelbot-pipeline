// 캐릭터 스튜디오 공용 — 타입·요청 헬퍼·역할 규칙(백엔드 character_studio*.py 와 같은 규칙).
import { prepareFile } from "@/components/shorts/FamilyCastPanel"

export interface Ref {
  id: number
  role: string
  status: "candidate" | "confirmed" | "discarded"
  source: "upload" | "generated"
  url: string
  w: number | null
  h: number | null
  prompt: string | null
  batch_id: string | null
  created_at: string
}
export interface RoleSlot { role: string; category: string; confirmed: Ref | null; candidates: Ref[] }
export interface Character { id: string; name: string; channel_id: string | null; bible?: Record<string, unknown> }
export interface PresetItem { key: string; line: string; label?: string; role: string }
export interface StudioPresets { hair: PresetItem[]; pose: PresetItem[] }
export interface View {
  character: Character
  roles: RoleSlot[]
  required: string[]
  missing_required: string[]
  ready: boolean
  presets: StudioPresets
}
export interface RolePresets { categories: { key: string; label: string; min: string }[]; required: string[]; pattern: string; examples: string[] }
export interface Job {
  id: string
  state: "queued" | "running" | "done" | "failed"
  roles: string[]
  total: number
  done: number
  failed: number
  errors: string[]
  cost_usd: number
  est_usd: number
}
export interface GenItem { role: string; prompt?: string; count?: number }

export const FACE_ROLE = "01_face"
export const BODY_ROLE = "02_body"
export const USD_PER_IMAGE = 0.011
export const ROLE_FALLBACK = "^[a-z0-9][a-z0-9_]{1,39}$"

export function usd(n: number): string {
  return `$${n.toFixed(3).replace(/0$/, "")}`
}

export async function jsonOrThrow(res: Response) {
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    if (res.status === 413) throw new Error("이미지가 너무 커요 — 4MB 이하로 줄여서 올려 주세요.")
    throw new Error(typeof data?.detail === "string" ? data.detail : `요청 실패(${res.status})`)
  }
  return data
}

/** 백엔드 role_category 와 같은 접두사 규칙(화면 그룹·라벨용). */
export function categoryOf(role: string): string {
  if (/^\d{2}_face$|^face(_|$)/.test(role)) return "face"
  if (/^\d{2}_body$|^body(_|$)/.test(role)) return "body"
  if (role.startsWith("hair_")) return "hair"
  if (role.startsWith("pose_")) return "pose"
  return "other"
}

/** 파일 이름으로 역할 추정 — 확장자는 전부 뗀다("hair_01_straight.png.png" → "hair_01_straight").
 * 얼굴·체형·헤어·포즈 이름이 아니면 ""("IMG_1234.jpg" 같은 이름은 AI 추천으로 넘긴다). */
export function guessRole(name: string, re: RegExp): string {
  const base = name.trim().split(".")[0].toLowerCase().replace(/[\s-]+/g, "_")
  return re.test(base) && categoryOf(base) !== "other" ? base : ""
}

export async function uploadOne(characterId: string, file: File, role: string, confirm: boolean) {
  const prepared = await prepareFile(file, categoryOf(role) === "body" ? 3072 : 2048)
  const fd = new FormData()
  fd.append("file", prepared, prepared.name)
  fd.append("role", role)
  fd.append("confirm", confirm ? "true" : "false")
  return jsonOrThrow(await fetch(`/api/studio/characters/${encodeURIComponent(characterId)}/upload`, { method: "POST", body: fd }))
}

export interface Suggestion { kind: "face" | "body" | "hair" | "pose" | "not_reference"; role: string; confidence: number; reason: string }

export async function suggestRole(characterId: string, file: File): Promise<Suggestion> {
  const prepared = await prepareFile(file, 2048)
  const fd = new FormData()
  fd.append("file", prepared, prepared.name)
  return jsonOrThrow(await fetch(`/api/studio/characters/${encodeURIComponent(characterId)}/suggest-role`, { method: "POST", body: fd }))
}

export async function startGenerate(characterId: string, items: GenItem[]): Promise<Job> {
  return jsonOrThrow(await fetch(`/api/studio/characters/${encodeURIComponent(characterId)}/generate`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ items }),
  }))
}
