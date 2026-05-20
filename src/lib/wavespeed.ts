// WaveSpeed Z-Image Turbo 이미지 생성 어댑터.
// 같은 seed로 여러 장을 생성하면 동일 캐릭터 외모가 유지된다.

const WAVESPEED_BASE = "https://api.wavespeed.ai/api/v3"
const Z_IMAGE_TURBO_PATH = "/wavespeed-ai/z-image/turbo"

// $0.005/장 — gpt-image-1 대비 약 50배 절감
export const Z_IMAGE_COST_PER_IMAGE = 0.005

const POLL_INTERVAL_MS = 1500
const POLL_TIMEOUT_MS = 120_000

export interface ZImageOptions {
  prompt: string
  seed: number
  // WaveSpeed size 표기는 "1024*1536" 형식
  size?: string
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export class WavespeedImageAdapter {
  constructor(private readonly apiKey: string) {
    if (!apiKey) throw new Error("WAVESPEED_API_KEY not configured")
  }

  private authHeaders(): Record<string, string> {
    return { Authorization: `Bearer ${this.apiKey}` }
  }

  // 프롬프트 → 이미지 1장 (PNG Buffer). seed 고정으로 외모 일관성 유지.
  async generate({ prompt, seed, size = "1024*1536" }: ZImageOptions): Promise<Buffer> {
    const requestId = await this.submit({ prompt, seed, size })
    const outputUrl = await this.poll(requestId)
    return this.download(outputUrl)
  }

  private async submit({ prompt, seed, size }: Required<ZImageOptions>): Promise<string> {
    const res = await fetch(`${WAVESPEED_BASE}${Z_IMAGE_TURBO_PATH}`, {
      method: "POST",
      headers: { ...this.authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        seed,
        size,
        enable_base64_output: false,
        enable_sync_mode: false,
      }),
    })
    if (!res.ok) {
      const detail = await res.text()
      throw new Error(`WaveSpeed 제출 실패: ${res.status} ${detail.slice(0, 300)}`)
    }
    const data = await res.json()
    const requestId = data?.data?.id
    if (!requestId) throw new Error("WaveSpeed: request id가 반환되지 않음")
    return requestId
  }

  private async poll(requestId: string): Promise<string> {
    const resultUrl = `${WAVESPEED_BASE}/predictions/${requestId}/result`
    const deadline = Date.now() + POLL_TIMEOUT_MS

    while (Date.now() < deadline) {
      await sleep(POLL_INTERVAL_MS)
      const res = await fetch(resultUrl, { headers: this.authHeaders() })
      if (!res.ok) continue

      const { data } = await res.json()
      const status = data?.status
      if (status === "completed") {
        const url = data?.outputs?.[0]
        if (!url) throw new Error("WaveSpeed: 출력 URL이 없음")
        return url
      }
      if (status === "failed") {
        throw new Error(`WaveSpeed 생성 실패: ${data?.error ?? "알 수 없는 오류"}`)
      }
    }
    throw new Error(`WaveSpeed 폴링 타임아웃 (${POLL_TIMEOUT_MS / 1000}s 초과)`)
  }

  private async download(url: string): Promise<Buffer> {
    const res = await fetch(url)
    if (!res.ok) throw new Error(`WaveSpeed 이미지 다운로드 실패: ${res.status}`)
    return Buffer.from(await res.arrayBuffer())
  }
}
