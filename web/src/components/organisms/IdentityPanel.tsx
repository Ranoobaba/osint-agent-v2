import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/atoms"
import { CandidateRow, IdentityPill } from "@/components/molecules"
import type { Report } from "@/lib/api"

export function IdentityPanel({ report }: { report: Report }) {
  const id = report.identity
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center gap-3">
          <CardTitle>{id.name ?? "No one resolved"}</CardTitle>
          <IdentityPill status={id.status} score={id.score} />
        </div>
        <CardDescription>{id.summary}</CardDescription>
      </CardHeader>
      <CardContent>
        {id.candidates.length === 0 ? (
          <p className="text-sm text-muted-foreground">No candidate profile could be grounded in a page read during this run.</p>
        ) : (
          <ul className="divide-y">
            {id.candidates.map((c) => (
              <CandidateRow key={c.id} candidate={c} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
