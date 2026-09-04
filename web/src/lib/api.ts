// Same-origin client for the osint-agent-v2 API. The built page is served by the FastAPI app, so
// relative URLs work in production; in development Vite proxies these paths to localhost:8000.

export type Finding = {
  id: string
  category: string | null
  field: string
  value: string
  confidence: number
  sensitive: boolean
  source_url: string | null
  source_id: string | null
  excerpt: string | null
  content_hash: string | null
  method: string | null
  candidate_id: string | null
}

export type Candidate = {
  id: string
  label: string
  score: number
  markers: string[]
  status: "resolved" | "rejected"
  reason: string
  profile_urls: string[]
  handles: string[]
}

export type Report = {
  target: string
  identity: {
    status: "resolved" | "ambiguous" | "unresolved"
    name: string | null
    score: number
    markers: string[]
    candidates: Candidate[]
    summary: string
  }
  findings: Finding[]
  excluded_findings: Finding[]
  not_found: { field: string; note: string | null; searched: string[] }[]
  conflicts: { field: string; values: string[] }[]
  synthesis: { claim: string; confidence: number }[]
  entities?: {
    nodes: { id: string; type: string; label: string; explored: boolean; about: string; url: string | null; hints: Record<string, string>; claims: string[] }[]
    edges: { src: string; dst: string; rel: string; claim: string | null }[]
    summary: { nodes: number; edges: number; by_type: Record<string, number>; unexplored: number }
    frontier: { id: string; type: string; label: string; hints: Record<string, string> }[]
  }
  run: {
    stop_reason: string
    duration_s: number
    cost_usd: number | null
    tool_calls: number
    admitted: number
    rejected: number
    budget: { calls: number; max_calls: number; usd: number; max_usd: number }
  }
}

export type Partial = {
  step: number
  status: string
  score: number
  tool_calls: number
  admitted: number
  usd: number
  last_tool: string
}

export type Job =
  | { job_id: string; status: "queued" | "running"; partial: Partial | null }
  | { job_id: string; status: "done"; report: Report; trace_url: string }
  | { job_id: string; status: "failed"; error: { type: string; message: string } }

const KEY_STORAGE = "osint2.apiKey"

export function getApiKey(): string {
  try { return localStorage.getItem(KEY_STORAGE) ?? "" } catch { return "" }
}

export function setApiKey(value: string): void {
  try { value ? localStorage.setItem(KEY_STORAGE, value) : localStorage.removeItem(KEY_STORAGE) } catch { /* storage unavailable */ }
}

export async function health(): Promise<{ locked: boolean }> {
  const r = await fetch("/healthz")
  return r.ok ? r.json() : { locked: false }
}

export async function submit(target: string): Promise<{ job_id: string; poll_url: string }> {
  const headers: Record<string, string> = { "content-type": "application/json" }
  const key = getApiKey()
  if (key) headers["x-api-key"] = key
  const r = await fetch("/investigate", { method: "POST", headers, body: JSON.stringify({ target }) })
  if (r.status === 401) throw new Error("This endpoint is locked. Enter the API key below the form; each investigation spends the operator's budget.")
  if (!r.ok) throw new Error(`submit failed: HTTP ${r.status} ${await r.text()}`)
  return r.json()
}

export async function poll(jobId: string): Promise<Job> {
  const r = await fetch(`/jobs/${jobId}`)
  if (!r.ok) throw new Error(`poll failed: HTTP ${r.status}`)
  return r.json()
}

export function sourceUrl(jobId: string, sourceId: string): string {
  return `/jobs/${jobId}/sources/${sourceId}`
}

export function traceUrl(jobId: string): string {
  return `/jobs/${jobId}/trace`
}
