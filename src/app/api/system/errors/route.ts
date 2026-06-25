import { proxyJson } from "@/lib/proxy"

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const limit = searchParams.get("limit") || "20"
  return proxyJson(`/api/system/errors?limit=${limit}`, { method: "GET", timeoutMs: 15_000 })
}
