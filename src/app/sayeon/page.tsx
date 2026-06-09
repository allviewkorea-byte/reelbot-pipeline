"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { ChevronDown, ChevronUp, Clapperboard, Sparkles, AlertCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { ProgressTracker } from "@/components/video/ProgressTracker"
import {
  generateSayeon,
  pollJobStatus,
  ApiError,
  type JobStatus,
  type SayeonCharacterSpec,
  type SayeonGenerateParams,
  type SayeonResult,
} from "@/lib/api"

const FIELD =
  "w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
const CARD = "rounded-xl border border-border bg-card p-6"

type CharMode = "new" | "existing"

// CharacterSpec 필드 (백엔드 schemas.py 와 동일) + 한글 라벨/플레이스홀더
const SPEC_FIELDS: {
  key: keyof SayeonCharacterSpec
  label: string
  placeholder: string
}[] = [
  { key: "gender", label: "성별", placeholder: "woman" },
  { key: "age", label: "연령대", placeholder: "early 20s" },
  { key: "hair", label: "헤어", placeholder: "long wavy auburn hair" },
  { key: "face", label: "외모/얼굴", placeholder: "soft round face, gentle eyes" },
  { key: "outfit", label: "의상", placeholder: "beige oversized knit cardigan" },
  { key: "accessories", label: "액세서리", placeholder: "round glasses, star earring" },
  { key: "signature", label: "시그니처", placeholder: "round glasses + star earring" },
  { key: "extra", label: "기타", placeholder: "" },
]

function Field({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {children}
    </label>
  )
}

export default function SayeonPage() {
  const [script, setScript] = useState("")
  const [charMode, setCharMode] = useState<CharMode>("new")
  const [spec, setSpec] = useState<SayeonCharacterSpec>({})
  const [sheetUrl, setSheetUrl] = useState("")
  const [anchor, setAnchor] = useState("")

  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [voiceId, setVoiceId] = useState("")
  const [numScenes, setNumScenes] = useState("")
  const [thumbIndex, setThumbIndex] = useState("")
  const [gapSec, setGapSec] = useState("0.4")

  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const stopRef = useRef<(() => void) | null>(null)

  // 언마운트 시 폴링 정리
  useEffect(() => () => stopRef.current?.(), [])

  const reset = useCallback(() => {
    stopRef.current?.()
    stopRef.current = null
    setJobStatus(null)
    setError(null)
    setSubmitting(false)
  }, [])

  const handleSubmit = useCallback(async () => {
    setError(null)
    if (!script.trim()) {
      setError("사연 대본을 입력해주세요.")
      return
    }
    const params: SayeonGenerateParams = {
      script: script.trim(),
      gap_sec: Number(gapSec) || 0.4,
    }
    if (charMode === "existing") {
      if (!sheetUrl.trim() || !anchor.trim()) {
        setError("기존 시트 재사용에는 시트 URL 과 앵커가 모두 필요합니다.")
        return
      }
      params.sheet_url = sheetUrl.trim()
      params.anchor = anchor.trim()
    } else {
      const filled = Object.values(spec).some((v) => v && v.trim())
      if (!filled) {
        setError("새 캐릭터는 최소 한 개 이상의 특징을 입력해주세요.")
        return
      }
      params.character_spec = spec
    }
    if (voiceId.trim()) params.voice_id = voiceId.trim()
    if (numScenes.trim()) params.num_scenes = Number(numScenes)
    if (thumbIndex.trim()) params.thumbnail_scene_index = Number(thumbIndex)

    setSubmitting(true)
    setJobStatus(null)
    try {
      const { job_id } = await generateSayeon(params)
      stopRef.current = pollJobStatus(
        job_id,
        (s) => {
          setJobStatus(s)
          if (s.status === "completed" || s.status === "failed") {
            setSubmitting(false)
          }
        },
        2500,
        (err) => setError(err.message),
      )
    } catch (err) {
      setSubmitting(false)
      setError(err instanceof ApiError ? err.message : "요청에 실패했습니다.")
    }
  }, [script, charMode, spec, sheetUrl, anchor, voiceId, numScenes, thumbIndex, gapSec])

  const completed = jobStatus?.status === "completed"
  const failed = jobStatus?.status === "failed"
  const running = submitting || jobStatus?.status === "running" || jobStatus?.status === "pending"
  const result = (completed ? (jobStatus?.result as SayeonResult | null) : null) ?? null

  return (
    <div className="flex flex-1 flex-col gap-6 overflow-auto p-6">
      <header className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/20 border border-primary/30">
          <Clapperboard className="h-4 w-4 text-primary" />
        </div>
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-foreground">사연 제작</h1>
          <p className="text-sm text-muted-foreground">
            사연 글을 넣으면 캐릭터 일관성 있는 영상과 썸네일을 자동 생성합니다.
          </p>
        </div>
      </header>

      {(failed || error) && (
        <div className="flex items-start gap-3 rounded-xl border border-red-500/40 bg-red-500/10 p-4">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
          <div className="text-sm text-foreground">
            {failed ? (jobStatus?.error ?? "생성에 실패했습니다.") : error}
          </div>
        </div>
      )}

      {running && !completed ? (
        <ProgressTracker jobStatus={jobStatus} title="사연 영상 생성 중" />
      ) : completed && result ? (
        <ResultView result={result} onReset={reset} />
      ) : (
        <div className="flex max-w-3xl flex-col gap-6">
          {/* 사연 대본 */}
          <div className={CARD}>
            <Field label="사연 대본 (필수)">
              <textarea
                className={`${FIELD} min-h-40 resize-y`}
                placeholder="1인칭 감성 사연을 입력하세요. (예: 스무 살 때, 엄마의 낡은 코트가 부끄러웠어요...)"
                value={script}
                onChange={(e) => setScript(e.target.value)}
              />
            </Field>
          </div>

          {/* 캐릭터 */}
          <div className={CARD}>
            <p className="mb-3 text-sm font-semibold text-foreground">캐릭터</p>
            <Tabs value={charMode} onValueChange={(v) => setCharMode(v as CharMode)}>
              <TabsList className="grid w-full max-w-md grid-cols-2">
                <TabsTrigger value="new">새 캐릭터</TabsTrigger>
                <TabsTrigger value="existing">기존 시트 재사용</TabsTrigger>
              </TabsList>

              <TabsContent value="new" className="mt-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  {SPEC_FIELDS.map((f) => (
                    <Field key={f.key} label={f.label}>
                      <input
                        className={FIELD}
                        placeholder={f.placeholder}
                        value={spec[f.key] ?? ""}
                        onChange={(e) =>
                          setSpec((s) => ({ ...s, [f.key]: e.target.value }))
                        }
                      />
                    </Field>
                  ))}
                </div>
                <p className="mt-3 text-xs text-muted-foreground">
                  시트는 1회 생성 후 재사용 권장 — 생성 결과의 시트 URL/앵커를 다음부터 「기존 시트 재사용」에 넣으면 비용을 아낄 수 있습니다.
                </p>
              </TabsContent>

              <TabsContent value="existing" className="mt-4">
                <div className="flex flex-col gap-4">
                  <Field label="시트 URL">
                    <input
                      className={FIELD}
                      placeholder="https://.../sheet.png"
                      value={sheetUrl}
                      onChange={(e) => setSheetUrl(e.target.value)}
                    />
                  </Field>
                  <Field label="앵커 (anchor)">
                    <input
                      className={FIELD}
                      placeholder="early 20s woman, long wavy auburn hair, round glasses..."
                      value={anchor}
                      onChange={(e) => setAnchor(e.target.value)}
                    />
                  </Field>
                </div>
              </TabsContent>
            </Tabs>
          </div>

          {/* 고급 (접이식) */}
          <div className={CARD}>
            <button
              type="button"
              className="flex w-full items-center justify-between text-sm font-semibold text-foreground"
              onClick={() => setAdvancedOpen((v) => !v)}
            >
              <span>고급 설정</span>
              {advancedOpen ? (
                <ChevronUp className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              )}
            </button>
            {advancedOpen && (
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <Field label="보이스 ID (Supertone, 선택)">
                  <input
                    className={FIELD}
                    placeholder="미입력 시 기본/Edge"
                    value={voiceId}
                    onChange={(e) => setVoiceId(e.target.value)}
                  />
                </Field>
                <Field label="씬 개수 (선택)">
                  <input
                    className={FIELD}
                    type="number"
                    min={1}
                    placeholder="6~10 자동"
                    value={numScenes}
                    onChange={(e) => setNumScenes(e.target.value)}
                  />
                </Field>
                <Field label="썸네일 씬 번호 (선택)">
                  <input
                    className={FIELD}
                    type="number"
                    min={1}
                    placeholder="기본 컷"
                    value={thumbIndex}
                    onChange={(e) => setThumbIndex(e.target.value)}
                  />
                </Field>
                <Field label="라인 사이 쉼 (초)">
                  <input
                    className={FIELD}
                    type="number"
                    step={0.1}
                    min={0}
                    value={gapSec}
                    onChange={(e) => setGapSec(e.target.value)}
                  />
                </Field>
              </div>
            )}
          </div>

          <div>
            <Button onClick={handleSubmit} disabled={submitting} className="gap-2">
              <Sparkles className="h-4 w-4" />
              사연 영상 생성
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

function ResultView({
  result,
  onReset,
}: {
  result: SayeonResult
  onReset: () => void
}) {
  const scenes = result.scenes ?? []
  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <div className={CARD}>
          <p className="mb-3 text-sm font-semibold text-foreground">완성 영상</p>
          {result.video_url ? (
            <video
              controls
              className="w-full rounded-lg bg-black"
              src={result.video_url}
            />
          ) : (
            <p className="text-sm text-muted-foreground">영상 URL 없음</p>
          )}
        </div>
        <div className={CARD}>
          <p className="mb-3 text-sm font-semibold text-foreground">썸네일</p>
          {result.thumbnail_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={result.thumbnail_url}
              alt="썸네일"
              className="w-full rounded-lg"
            />
          ) : (
            <p className="text-sm text-muted-foreground">썸네일 URL 없음</p>
          )}
        </div>
      </div>

      {scenes.length > 0 && (
        <div className={CARD}>
          <p className="mb-3 text-sm font-semibold text-foreground">
            씬 {scenes.length}개
          </p>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {scenes.map((s) => (
              <div
                key={s.index}
                className="flex flex-col gap-2 rounded-lg border border-border bg-background p-3"
              >
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">#{s.index}</Badge>
                  {s.motion && (
                    <span className="text-xs text-muted-foreground">{s.motion}</span>
                  )}
                </div>
                {s.image_url && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={s.image_url}
                    alt={`씬 ${s.index}`}
                    className="aspect-[9/16] w-full rounded-md object-cover"
                  />
                )}
                {s.subtitle && (
                  <p className="text-xs text-foreground">{s.subtitle}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <Button variant="outline" onClick={onReset}>
          새로 만들기
        </Button>
      </div>
    </div>
  )
}
