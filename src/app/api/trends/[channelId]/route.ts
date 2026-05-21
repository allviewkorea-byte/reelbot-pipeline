import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ channelId: string }> },
) {
  const { channelId } = await params
  const { searchParams } = new URL(request.url)
  const qs = new URLSearchParams()
  const category = searchParams.get("category")
  const format = searchParams.get("format")
  if (category) qs.set("category", category)
  if (format) qs.set("format", format)
  const suffix = qs.toString() ? `?${qs.toString()}` : ""
  return proxyJson(`/trends/${encodeURIComponent(channelId)}${suffix}`, { method: "GET" })
}
