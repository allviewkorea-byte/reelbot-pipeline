import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

export async function POST(request: NextRequest) {
  const body = await request.json()
  return proxyJson("/video/start", { method: "POST", body })
}
