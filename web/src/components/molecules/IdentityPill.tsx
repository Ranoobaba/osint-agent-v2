import { Badge, StatusDot } from "@/components/atoms"

const LABEL: Record<string, string> = {
  resolved: "Resolved",
  ambiguous: "Ambiguous",
  unresolved: "Unresolved",
  running: "Running",
  queued: "Queued",
  failed: "Failed",
}

export function IdentityPill({ status, score }: { status: string; score?: number }) {
  return (
    <Badge variant="outline" className="gap-1.5 py-1 pr-2.5 pl-2 text-sm font-medium">
      <StatusDot status={status} />
      {LABEL[status] ?? status}
      {typeof score === "number" && score > 0 && <span className="text-muted-foreground">{score.toFixed(2)}</span>}
    </Badge>
  )
}
