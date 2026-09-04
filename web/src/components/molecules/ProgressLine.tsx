import { Mono } from "@/components/atoms"
import type { Partial } from "@/lib/api"

export function ProgressLine({ partial, elapsed }: { partial: Partial | null; elapsed: number }) {
  if (!partial) {
    return <p className="text-sm text-muted-foreground">Starting the investigation ({elapsed}s)</p>
  }
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
      <span>Step {partial.step}</span>
      <span>{partial.tool_calls} data calls</span>
      <span>{partial.admitted} claims admitted</span>
      <span>${partial.usd.toFixed(2)}</span>
      <span>{elapsed}s</span>
      <Mono>last tool: {partial.last_tool}</Mono>
    </div>
  )
}
