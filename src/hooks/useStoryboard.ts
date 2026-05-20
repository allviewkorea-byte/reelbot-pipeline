"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import {
  ApiError,
  generateStoryboard,
  pollJobStatus,
  regenerateScene,
  type JobStatus,
  type Storyboard,
  type StoryboardGenerateParams,
  type SceneRegenerateParams,
} from "@/lib/api"

export function useStoryboard() {
  const [job, setJob] = useState<JobStatus | null>(null)
  const [storyboards, setStoryboards] = useState<Storyboard[]>([])
  const [isGenerating, setIsGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const cleanupRef = useRef<(() => void) | null>(null)

  // 언마운트 시 진행 중인 폴링 정리
  useEffect(() => () => cleanupRef.current?.(), [])

  const stopPolling = useCallback(() => {
    cleanupRef.current?.()
    cleanupRef.current = null
  }, [])

  const generate = useCallback(
    async (params: StoryboardGenerateParams) => {
      stopPolling()
      setError(null)
      setIsGenerating(true)
      setStoryboards([])
      try {
        const { job_id } = await generateStoryboard(params)
        cleanupRef.current = pollJobStatus(
          job_id,
          (status) => {
            setJob(status)
            if (status.status === "completed") {
              const result = status.result as { storyboards?: Storyboard[] } | null
              setStoryboards(result?.storyboards ?? [])
              setIsGenerating(false)
            } else if (status.status === "failed") {
              setError(status.error ?? "콘티 생성에 실패했습니다.")
              setIsGenerating(false)
            }
          },
          2000,
          (e) => setError(e.message),
        )
      } catch (e) {
        setIsGenerating(false)
        setError(e instanceof ApiError ? e.message : "콘티 생성 요청에 실패했습니다.")
      }
    },
    [stopPolling],
  )

  // 단일 씬 재생성. storyboardJobId 는 generate 가 만든 출력 폴더 식별자.
  const regenerate = useCallback(
    async (
      sceneId: number,
      scene: Record<string, unknown>,
      opts?: {
        storyboardJobId?: string
        characterImagePath?: string | null
        extraInstructions?: string | null
        onDone?: (sb: Storyboard) => void
      },
    ) => {
      setError(null)
      try {
        const params: SceneRegenerateParams = {
          job_id: opts?.storyboardJobId ?? job?.job_id ?? "",
          scene_id: sceneId,
          scene,
          character_image_path: opts?.characterImagePath ?? null,
          extra_instructions: opts?.extraInstructions ?? null,
        }
        const { job_id } = await regenerateScene(params)
        return await new Promise<Storyboard | null>((resolve) => {
          pollJobStatus(
            job_id,
            (status) => {
              if (status.status === "completed") {
                const result = status.result as { storyboard?: Storyboard } | null
                const sb = result?.storyboard ?? null
                if (sb) {
                  setStoryboards((prev) =>
                    prev.map((p) => (String(p.scene_id) === String(sceneId) ? sb : p)),
                  )
                  opts?.onDone?.(sb)
                }
                resolve(sb)
              } else if (status.status === "failed") {
                setError(status.error ?? "씬 재생성에 실패했습니다.")
                resolve(null)
              }
            },
            2000,
            (e) => setError(e.message),
          )
        })
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "씬 재생성 요청에 실패했습니다.")
        return null
      }
    },
    [job],
  )

  return { job, storyboards, isGenerating, error, generate, regenerate, stopPolling }
}
