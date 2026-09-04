import { Badge, Mono } from "@/components/atoms"
import type { Candidate } from "@/lib/api"

export function CandidateRow({ candidate }: { candidate: Candidate }) {
  const c = candidate
  return (
    <li className="flex flex-wrap items-baseline gap-x-2 gap-y-1 py-2 text-sm">
      <Badge variant={c.status === "resolved" ? "default" : "secondary"}>{c.status}</Badge>
      <span className="font-medium">{c.label}</span>
      <Mono>score {c.score.toFixed(2)}</Mono>
      {c.markers.length > 0 && <Mono>markers {c.markers.join(", ")}</Mono>}
      <span className="basis-full text-xs text-muted-foreground">{c.reason}</span>
    </li>
  )
}
