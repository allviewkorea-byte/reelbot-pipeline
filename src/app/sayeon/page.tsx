"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { ChevronDown, ChevronUp, Clapperboard, Sparkles, AlertCircle, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { ProgressTracker } from "@/components/video/ProgressTracker"
import { toast } from "sonner"
import {
  generateSayeon,
  generateSayeonScript,
  pollJobStatus,
  listSayeonCharacters,
  getDefaultSayeonCharacter,
  saveSayeonCharacter,
  updateSayeonCharacterSheet,
  ApiError,
  type JobStatus,
  type SayeonCharacter,
  type SayeonCharacterSpec,
  type SayeonGenerateParams,
  type SayeonResult,
} from "@/lib/api"

const FIELD =
  "w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
const CARD = "rounded-xl border border-border bg-card p-6"

type CharMode = "new" | "existing"
type Mode = "auto" | "semi" | "manual"

const MODE_DESC: Record<Mode, string> = {
  auto: "버튼 한 번 — 사연 자동 작성 + 영상 제작까지 한 번에.",
  semi: "사연을 자동 작성해 채워주면, 검토·수정 후 직접 제작합니다.",
  manual: "사연을 직접 입력·수정한 뒤 제작합니다.",
}

// 자동/반자동에서 캐릭터 미선택 시 쓰는 클라 폴백 스펙(서버 default 와 동일, 고정값).
// 서버/DB 가 없어도 자동 모드가 멈추지 않게 한다. 랜덤 아님 — 일관성 유지.
const FALLBACK_SPEC: SayeonCharacterSpec = {
  gender: "woman",
  age: "early 20s",
  hair: "long straight dark brown hair",
  face: "warm soft features, expressive eyes",
  outfit: "cozy cream knit sweater",
  accessories: "simple small stud earrings",
  signature: "warm relatable everyday girl",
}

// 자동 확보된 캐릭터(드롭다운 미선택 시 runGenerate 에 넘기는 오버라이드).
type CharSel = {
  id?: string
  spec: SayeonCharacterSpec
  sheet_url: string
  anchor: string
}

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

  // 저장된 사연 캐릭터
  const [savedChars, setSavedChars] = useState<SayeonCharacter[]>([])
  const [selectedCharId, setSelectedCharId] = useState("")
  const [saveName, setSaveName] = useState("")
  const [saving, setSaving] = useState(false)
  const [autoLoading, setAutoLoading] = useState(false)
  const [mode, setMode] = useState<Mode>("auto")

  // 언마운트 시 폴링 정리
  useEffect(() => () => stopRef.current?.(), [])

  const loadChars = useCallback(() => {
    listSayeonCharacters()
      .then(setSavedChars)
      .catch(() => setSavedChars([]))
  }, [])
  useEffect(() => loadChars(), [loadChars])

  // 저장된 캐릭터 선택 → 폼 자동 채움. 시트(URL+앵커) 있으면 재사용 경로로.
  const onSelectChar = useCallback(
    (id: string) => {
      setSelectedCharId(id)
      const c = savedChars.find((x) => x.id === id)
      if (!c) return
      setSpec(c.spec ?? {})
      setSheetUrl(c.sheet_url ?? "")
      setAnchor(c.anchor ?? "")
      setSaveName(c.name)
      setCharMode(c.sheet_url && c.anchor ? "existing" : "new")
    },
    [savedChars],
  )

  const handleAutoScript = useCallback(async () => {
    setAutoLoading(true)
    try {
      // 현재 캐릭터의 gender/age 를 화자 설정으로 함께 전송.
      const res = await generateSayeonScript({
        character: { gender: spec.gender, age: spec.age },
      })
      setScript(res.script)
      if (res.title) toast.success(`사연 생성 완료: ${res.title}`)
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "사연 자동 생성에 실패했어요.",
      )
    } finally {
      setAutoLoading(false)
    }
  }, [spec.gender, spec.age])

  const handleSaveChar = useCallback(async () => {
    if (!saveName.trim()) {
      toast.error("저장할 캐릭터 이름을 입력해주세요.")
      return
    }
    setSaving(true)
    try {
      const res = await saveSayeonCharacter({
        name: saveName.trim(),
        spec,
        sheet_url: sheetUrl.trim() || null,
        anchor: anchor.trim() || null,
      })
      if (res.success && res.character) {
        toast.success("캐릭터를 저장했어요.")
        setSavedChars((prev) => [res.character as SayeonCharacter, ...prev])
        setSelectedCharId(res.character.id)
      } else {
        toast.error(res.error ?? "저장에 실패했어요.")
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "저장에 실패했어요.")
    } finally {
      setSaving(false)
    }
  }, [saveName, spec, sheetUrl, anchor])

  const reset = useCallback(() => {
    stopRef.current?.()
    stopRef.current = null
    setJobStatus(null)
    setError(null)
    setSubmitting(false)
  }, [])

  // 자동/반자동: 캐릭터 미선택·미입력이면 기본 캐릭터를 확보(없으면 시드)해 반환.
  // 선택/입력된 캐릭터가 있으면 null(= runGenerate 가 state 사용). 일관성 위해 랜덤 생성 안 함.
  const ensureCharacter = useCallback(async (): Promise<CharSel | null> => {
    if (selectedCharId) return null
    const hasSpec = Object.values(spec).some((v) => v && v.trim())
    if (hasSpec || (sheetUrl.trim() && anchor.trim())) return null

    const def = await getDefaultSayeonCharacter()
    const sel: CharSel = def
      ? {
          id: def.id,
          spec: def.spec ?? FALLBACK_SPEC,
          sheet_url: def.sheet_url ?? "",
          anchor: def.anchor ?? "",
        }
      : { spec: FALLBACK_SPEC, sheet_url: "", anchor: "" }
    // 화면에도 반영(사용자가 확인 가능)
    setSpec(sel.spec)
    setSheetUrl(sel.sheet_url)
    setAnchor(sel.anchor)
    setCharMode(sel.sheet_url && sel.anchor ? "existing" : "new")
    if (def) {
      setSelectedCharId(def.id)
      setSaveName(def.name)
      loadChars()
    }
    return sel
  }, [selectedCharId, spec, sheetUrl, anchor, loadChars])

  // scriptOverride/charOverride: 자동 모드에서 방금 만든 사연·확보한 캐릭터를
  // state 갱신을 기다리지 않고 즉시 넘길 때 사용.
  const runGenerate = useCallback(
    async (scriptOverride?: string, charOverride?: CharSel) => {
      setError(null)
      const effScript = (scriptOverride ?? script).trim()
      if (!effScript) {
        setError("사연 대본을 입력해주세요.")
        return
      }
      const params: SayeonGenerateParams = {
        script: effScript,
        gap_sec: Number(gapSec) || 0.4,
      }
      if (charOverride) {
        // 자동 확보된 캐릭터: 시트 있으면 재사용, 없으면 스펙으로 생성.
        if (charOverride.sheet_url && charOverride.anchor) {
          params.sheet_url = charOverride.sheet_url
          params.anchor = charOverride.anchor
        } else {
          params.character_spec = charOverride.spec
        }
      } else if (charMode === "existing") {
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
            // 생성된 시트(URL+앵커)를 사용한 캐릭터에 저장 → 다음부터 동일 인물 재사용.
            if (s.status === "completed") {
              const r = s.result as SayeonResult | null
              if (!r?.sheet_url || !r?.anchor) return
              // (a) 자동 확보 캐릭터: 시트 없던 경우 저장 + 세션 상태도 갱신
              if (charOverride?.id && !charOverride.sheet_url) {
                updateSayeonCharacterSheet(charOverride.id, r.sheet_url, r.anchor)
                  .then(() => loadChars())
                  .catch(() => {})
                setSheetUrl(r.sheet_url)
                setAnchor(r.anchor)
                setCharMode("existing")
              } else if (!charOverride) {
                // (b) 드롭다운 선택 캐릭터: 시트 없던 경우 저장
                const c = savedChars.find((x) => x.id === selectedCharId)
                if (c && !c.sheet_url) {
                  updateSayeonCharacterSheet(c.id, r.sheet_url, r.anchor)
                    .then(() => {
                      loadChars()
                      toast.success("생성된 시트를 캐릭터에 저장했어요. 다음부터 재사용됩니다.")
                    })
                    .catch(() => {})
                  setSheetUrl(r.sheet_url)
                  setAnchor(r.anchor)
                  setCharMode("existing")
                }
              }
            }
          },
          2500,
          (err) => setError(err.message),
        )
      } catch (err) {
        setSubmitting(false)
        setError(err instanceof ApiError ? err.message : "요청에 실패했습니다.")
      }
    },
    [script, charMode, spec, sheetUrl, anchor, voiceId, numScenes, thumbIndex, gapSec, selectedCharId, savedChars, loadChars],
  )

  // 자동 모드: 캐릭터 확보 → 사연 자동 작성 → 곧바로 영상 생성까지 한 번에.
  const handleAutoRun = useCallback(async () => {
    setError(null)
    setAutoLoading(true)
    let generated = ""
    let co: CharSel | null = null
    try {
      co = await ensureCharacter()
      const g = co ? co.spec.gender : spec.gender
      const a = co ? co.spec.age : spec.age
      const res = await generateSayeonScript({ character: { gender: g, age: a } })
      generated = res.script
      setScript(generated)
      if (res.title) toast.success(`사연: ${res.title}`)
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "사연 자동 생성에 실패했어요.",
      )
      setAutoLoading(false)
      return
    }
    setAutoLoading(false)
    await runGenerate(generated, co ?? undefined)
  }, [ensureCharacter, spec.gender, spec.age, runGenerate])

  // 반자동: "사연 영상 생성" 시 캐릭터 미선택이면 기본 캐릭터로 자동 확보 후 진행.
  const handleSemiGenerate = useCallback(async () => {
    const co = await ensureCharacter()
    await runGenerate(undefined, co ?? undefined)
  }, [ensureCharacter, runGenerate])

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

      {/* 제작 모드 토글 */}
      <div>
        <Tabs value={mode} onValueChange={(v) => setMode(v as Mode)}>
          <TabsList className="grid w-full max-w-md grid-cols-3">
            <TabsTrigger value="auto">자동</TabsTrigger>
            <TabsTrigger value="semi">반자동</TabsTrigger>
            <TabsTrigger value="manual">수동</TabsTrigger>
          </TabsList>
        </Tabs>
        <p className="mt-2 text-xs text-muted-foreground">{MODE_DESC[mode]}</p>
      </div>

      {(failed || error) && (
        <div className="flex items-start gap-3 rounded-xl border border-red-500/40 bg-red-500/10 p-4">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
          <div className="text-sm text-foreground">
            {failed ? (jobStatus?.error ?? "생성에 실패했습니다.") : error}
          </div>
        </div>
      )}

      {(autoLoading || running) && !completed ? (
        autoLoading ? (
          <div className="mx-auto flex max-w-md flex-col items-center gap-3 rounded-xl border border-border bg-card p-8">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="text-sm font-semibold text-foreground">사연 작성 중…</p>
            <p className="text-xs text-muted-foreground">감성 사연을 만들고 있어요</p>
          </div>
        ) : (
          <ProgressTracker jobStatus={jobStatus} title="사연 영상 생성 중" />
        )
      ) : completed && result ? (
        <ResultView result={result} onReset={reset} />
      ) : (
        <div className="flex max-w-3xl flex-col gap-6">
          {/* 사연 대본 */}
          <div className={CARD}>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">
                사연 대본 (필수)
              </span>
              {mode !== "auto" && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleAutoScript}
                  disabled={autoLoading}
                >
                  {autoLoading ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    "🎲"
                  )}
                  사연 자동 생성
                </Button>
              )}
            </div>
            <textarea
              className={`${FIELD} min-h-40 resize-y`}
              placeholder="1인칭 감성 사연을 입력하세요. (예: 스무 살 때, 엄마의 낡은 코트가 부끄러웠어요...) — 또는 '사연 자동 생성'을 눌러보세요."
              value={script}
              onChange={(e) => setScript(e.target.value)}
            />
          </div>

          {/* 캐릭터 */}
          <div className={CARD}>
            <p className="mb-3 text-sm font-semibold text-foreground">캐릭터</p>

            {/* 저장된 캐릭터 선택 + 현재 캐릭터 저장 */}
            <div className="mb-4 flex flex-wrap items-end gap-3">
              <Field label="저장된 캐릭터">
                <select
                  className={`${FIELD} min-w-[180px]`}
                  value={selectedCharId}
                  onChange={(e) => onSelectChar(e.target.value)}
                >
                  <option value="">— 직접 입력 —</option>
                  {savedChars.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                      {c.sheet_url ? " · 시트✓" : ""}
                    </option>
                  ))}
                </select>
              </Field>
              <input
                className={`${FIELD} max-w-[200px]`}
                placeholder="저장할 이름"
                value={saveName}
                onChange={(e) => setSaveName(e.target.value)}
              />
              <Button variant="outline" onClick={handleSaveChar} disabled={saving}>
                현재 캐릭터 저장
              </Button>
            </div>

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

          <div className="flex flex-wrap gap-3">
            {mode === "auto" && (
              <Button
                onClick={handleAutoRun}
                disabled={autoLoading || submitting}
                className="gap-2"
              >
                <Sparkles className="h-4 w-4" />
                자동 생성 (사연 작성 + 영상)
              </Button>
            )}
            {mode === "semi" && (
              <Button
                variant="outline"
                onClick={handleAutoScript}
                disabled={autoLoading}
                className="gap-2"
              >
                🎲 사연 자동 작성
              </Button>
            )}
            {mode !== "auto" && (
              <Button
                onClick={mode === "semi" ? handleSemiGenerate : () => runGenerate()}
                disabled={submitting}
                className="gap-2"
              >
                <Sparkles className="h-4 w-4" />
                사연 영상 생성
              </Button>
            )}
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
      {/* 영상·썸네일을 폰 프레임처럼 폭 제한 + 높이 캡(데스크톱 한눈에) */}
      <div className="flex flex-col items-center gap-6 lg:flex-row lg:items-start lg:justify-center">
        <div className={`${CARD} w-full max-w-[360px]`}>
          <p className="mb-3 text-sm font-semibold text-foreground">완성 영상</p>
          {result.video_url ? (
            <video
              controls
              className="mx-auto aspect-[9/16] max-h-[70vh] w-full rounded-lg bg-black object-contain"
              src={result.video_url}
            />
          ) : (
            <p className="text-sm text-muted-foreground">영상 URL 없음</p>
          )}
        </div>
        <div className={`${CARD} w-full max-w-[320px]`}>
          <p className="mb-3 text-sm font-semibold text-foreground">썸네일</p>
          {result.thumbnail_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={result.thumbnail_url}
              alt="썸네일"
              className="mx-auto aspect-[9/16] max-h-[70vh] w-full rounded-lg object-cover"
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
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
            {scenes.map((s) => (
              <div key={s.index} className="flex flex-col gap-1.5">
                <div className="relative overflow-hidden rounded-md border border-border bg-background">
                  {s.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={s.image_url}
                      alt={`씬 ${s.index}`}
                      className="aspect-[9/16] w-full object-cover"
                    />
                  ) : (
                    <div className="aspect-[9/16] w-full bg-secondary" />
                  )}
                  <span className="absolute left-1.5 top-1.5">
                    <Badge variant="secondary">#{s.index}</Badge>
                  </span>
                </div>
                {s.subtitle && (
                  <p className="line-clamp-2 text-[11px] text-muted-foreground">
                    {s.subtitle}
                  </p>
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
