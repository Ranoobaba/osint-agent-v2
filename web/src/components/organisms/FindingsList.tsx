import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/atoms"
import { FindingRow } from "@/components/molecules"
import type { Report } from "@/lib/api"

export function FindingsList({ report, jobId }: { report: Report; jobId: string }) {
  const groups = new Map<string, typeof report.findings>()
  for (const f of report.findings) {
    const k = f.category ?? "other"
    groups.set(k, [...(groups.get(k) ?? []), f])
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Findings</CardTitle>
        <CardDescription>
          {report.findings.length} attributed to the resolved person. Each links to the live page and to the stored copy the quote was checked against.
          {report.excluded_findings.length > 0 && ` ${report.excluded_findings.length} more were recorded about other candidates and excluded.`}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {report.findings.length === 0 && <p className="text-sm text-muted-foreground">Nothing was attributed. See the honesty panel for what was looked for.</p>}
        {[...groups.entries()].map(([cat, items]) => (
          <section key={cat}>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{cat.replaceAll("_", " ")}</h3>
            <ul className="divide-y">
              {items.map((f) => (
                <FindingRow key={f.id} finding={f} jobId={jobId} />
              ))}
            </ul>
          </section>
        ))}
        {report.synthesis.length > 0 && (
          <section>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Synthesis (inference from the findings above)</h3>
            <ul className="list-disc space-y-1 pl-5 text-sm">
              {report.synthesis.map((s, i) => (
                <li key={i}>
                  {s.claim} <span className="text-muted-foreground">({Math.round(s.confidence * 100)}%)</span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </CardContent>
    </Card>
  )
}
