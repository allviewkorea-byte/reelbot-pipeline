import { proxyJson } from "@/lib/proxy"

export async function GET() {
  return proxyJson("/api/system/status", { method: "GET", timeoutMs: 30_000 })
}
