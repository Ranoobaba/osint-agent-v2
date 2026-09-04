import { Badge, Mono } from "@/components/atoms"
import { sourceUrl, type Finding } from "@/lib/api"

export function FindingRow({ finding, jobId }: { finding: Finding; jobId: string }) {
  const f = finding
  return (
    <li className="grid gap-1 py-3">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="text-sm font-medium">{f.field.replaceAll("_", " ")}</span>
        <span className="text-sm">{f.value}</span>
        {f.sensitive && <Badge variant="destructive">sensitive</Badge>}
        <Mono className="ml-auto">
          {f.method} · {Math.round(f.confidence * 100)}%
        </Mono>
      </div>
      {f.excerpt && (
        <blockquote className="border-l-2 pl-3 text-sm text-muted-foreground">“{f.excerpt.length > 240 ? f.excerpt.slice(0, 240) + "…" : f.excerpt}”</blockquote>
      )}
      <div className="flex flex-wrap gap-x-3 text-xs">
        {f.source_url && (
          <a href={f.source_url} target="_blank" rel="noreferrer" className="text-primary underline-offset-2 hover:underline">
            source page
          </a>
        )}
        {f.source_id && (
          <a href={sourceUrl(jobId, f.source_id)} target="_blank" rel="noreferrer" className="text-primary underline-offset-2 hover:underline">
            stored copy {f.source_id}
          </a>
        )}
        {f.content_hash && <Mono>sha256 {f.content_hash.slice(0, 12)}</Mono>}
      </div>
    </li>
  )
}
