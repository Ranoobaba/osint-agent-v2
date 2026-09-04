import { Card, CardContent, CardDescription, CardHeader, CardTitle, Separator } from "@/components/atoms"
import { NotFoundRow } from "@/components/molecules"
import type { Report } from "@/lib/api"

export function HonestyPanel({ report }: { report: Report }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>What was not established</CardTitle>
        <CardDescription>Wrong is worse than missing. These were looked for and left empty rather than guessed.</CardDescription>
      </CardHeader>
      <CardContent>
        {report.not_found.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing recorded as not found.</p>
        ) : (
          <ul className="divide-y">
            {report.not_found.map((n, i) => (
              <NotFoundRow key={i} field={n.field} note={n.note} searched={n.searched} />
            ))}
          </ul>
        )}
        {report.conflicts.length > 0 && (
          <>
            <Separator className="my-3" />
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Conflicts between sources</h3>
            <ul className="space-y-1 text-sm">
              {report.conflicts.map((c, i) => (
                <li key={i}>
                  <span className="font-medium">{c.field.replaceAll("_", " ")}</span>: {c.values.join(" vs ")}
                </li>
              ))}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  )
}
