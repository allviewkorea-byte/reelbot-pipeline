"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import {
  ApiError,
  pollJobStatus,
  startVideo,
  type JobStatus,
  type VideoStartParams,
} from "@/lib/api"

export function useVideoGeneration() {
  const [job, setJob] = useState<JobStatus | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const cleanupRef = useRef<(() => void) | null>(null)

  useEffect(() => () => cleanupRef.current?.(), [])

  const start = useCallback(async (params: VideoStartParams) => {
    cleanupRef.current?.()
    setError(null)
    setResult(null)
    setIsGenerating(true)
    try {
      const { job_id } = await startVideo(params)
      cleanupRef.current = pollJobStatus(
        job_id,
        (status) => {
          setJob(status)
          if (status.status === "completed") {
            setResult(status.result)
            setIsGenerating(false)
          } else if (status.status === "failed") {
            setError(status.error ?? "영상 생성에 실패했습니다.")
            setIsGenerating(false)
          }
        },
        2000,
        (e) => setError(e.message),
      )
    } catch (e) {
      setIsGenerating(false)
      setError(e instanceof ApiError ? e.message : "영상 생성 요청에 실패했습니다.")
    }
  }, [])

  return { job, isGenerating, result, error, start }
}
