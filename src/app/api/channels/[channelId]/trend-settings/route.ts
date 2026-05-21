import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ channelId: string }> },
) {
  const { channelId } = await params
  const body = await request.json()
  return proxyJson(`/channels/${encodeURIComponent(channelId)}/trend-settings`, {
    method: "PUT",
    body,
  })
}
