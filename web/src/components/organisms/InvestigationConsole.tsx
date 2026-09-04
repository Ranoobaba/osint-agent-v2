import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Mono } from "@/components/atoms"
import { ApiKeyField, IdentityPill, ProgressLine, TargetForm } from "@/components/molecules"
import type { InvestigationState } from "@/hooks/useInvestigation"
import { traceUrl } from "@/lib/api"

export function InvestigationConsole({ state, onStart, onReset }: { state: InvestigationState; onStart: (t: string) => void; onReset: () => void }) {
  const busy = state.phase === "queued" || state.phase === "running"
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-2xl">Investigate a person</CardTitle>
        <CardDescription>
          One line in, a strict JSON report out. Every finding carries the sentence it was read from and the hash of that page. Identity is decided in code; someone with the same name is not the same person.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <TargetForm onSubmit={onStart} busy={busy} />
        <ApiKeyField />
        {state.phase !== "idle" && (
          <div className="flex flex-wrap items-center gap-3 rounded-md border bg-muted/40 p-3">
            <IdentityPill status={state.phase === "done" && state.report ? state.report.identity.status : state.phase} score={state.report?.identity.score} />
            <span className="text-sm">{state.target}</span>
            {busy && <ProgressLine partial={state.partial} elapsed={state.elapsed} />}
            {state.phase === "failed" && <span className="text-sm text-destructive">{state.error}</span>}
            {state.phase === "done" && state.report && (
              <span className="flex flex-wrap items-center gap-x-3 text-sm text-muted-foreground">
                <span>{state.report.findings.length} findings</span>
                <span>{state.report.run.budget.calls} data calls</span>
                <span>${(state.report.run.cost_usd ?? 0).toFixed(2)}</span>
                <span>{Math.round(state.report.run.duration_s)}s</span>
                <span>stopped: {state.report.run.stop_reason}</span>
                {state.jobId && (
                  <a href={traceUrl(state.jobId)} target="_blank" rel="noreferrer" className="text-primary underline-offset-2 hover:underline">
                    trace.jsonl
                  </a>
                )}
              </span>
            )}
            {state.jobId && <Mono className="ml-auto">job {state.jobId}</Mono>}
            {!busy && (
              <Button variant="ghost" size="sm" onClick={onReset}>
                New
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
