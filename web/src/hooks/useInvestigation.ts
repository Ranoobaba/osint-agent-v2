import { useCallback, useEffect, useRef, useState } from "react"
import { poll, submit, type Job, type Partial, type Report } from "@/lib/api"

export type Phase = "idle" | "queued" | "running" | "done" | "failed"

export type InvestigationState = {
  phase: Phase
  target: string
  jobId: string | null
  partial: Partial | null
  report: Report | null
  error: string | null
  elapsed: number
}

const INITIAL: InvestigationState = { phase: "idle", target: "", jobId: null, partial: null, report: null, error: null, elapsed: 0 }

export function useInvestigation() {
  const [state, setState] = useState<InvestigationState>(INITIAL)
  const startedAt = useRef<number>(0)
  const timer = useRef<number | null>(null)

  const stop = () => {
    if (timer.current) window.clearInterval(timer.current)
    timer.current = null
  }

  const start = useCallback(async (target: string) => {
    stop()
    startedAt.current = Date.now()
    setState({ ...INITIAL, phase: "queued", target })
    try {
      const { job_id } = await submit(target)
      setState((s) => ({ ...s, jobId: job_id }))
      timer.current = window.setInterval(async () => {
        try {
          const job: Job = await poll(job_id)
          const elapsed = Math.round((Date.now() - startedAt.current) / 1000)
          if (job.status === "done") {
            stop()
            setState((s) => ({ ...s, phase: "done", report: job.report, elapsed }))
          } else if (job.status === "failed") {
            stop()
            setState((s) => ({ ...s, phase: "failed", error: `${job.error.type}: ${job.error.message}`, elapsed }))
          } else {
            setState((s) => ({ ...s, phase: job.status, partial: job.partial, elapsed }))
          }
        } catch (e) {
          stop()
          setState((s) => ({ ...s, phase: "failed", error: String(e) }))
        }
      }, 4000)
    } catch (e) {
      setState((s) => ({ ...s, phase: "failed", error: String(e) }))
    }
  }, [])

  const reset = useCallback(() => {
    stop()
    setState(INITIAL)
  }, [])

  useEffect(() => stop, [])
  return { state, start, reset }
}
