import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, Mono } from "@/components/atoms"
import type { Report } from "@/lib/api"

const REL: Record<string, string> = {
  collaborates_with: "collaborates with", works_at: "works at", studied_at: "studied at", owns_account: "account",
  has_email: "email", linked_domain: "domain", contributes_to: "contributes to", authored: "authored", works_on: "works on",
}

export function EntitiesPanel({ report }: { report: Report }) {
  const ent = report.entities
  if (!ent) return null
  const people = ent.nodes.filter((n) => n.type === "person" && n.about === "connection")
  const orgs = ent.nodes.filter((n) => n.type === "org")
  const accounts = ent.nodes.filter((n) => n.type === "account" && n.about === "target")
  const byId = new Map(ent.nodes.map((n) => [n.id, n]))
  return (
    <Card>
      <CardHeader>
        <CardTitle>Entities</CardTitle>
        <CardDescription>
          {ent.summary.nodes} nodes, {ent.summary.edges} edges derived from admitted claims. {ent.summary.unexplored} still unexplored: the frontier a longer run would pivot on.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-5">
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">People connected to the target</h3>
          {people.length === 0 ? (
            <p className="text-sm text-muted-foreground">No connections recorded.</p>
          ) : (
            <ul className="divide-y">
              {people.map((p) => {
                const rels = ent.edges.filter((e) => e.dst === p.id || e.src === p.id).map((e) => REL[e.rel] ?? e.rel.replaceAll("_", " "))
                return (
                  <li key={p.id} className="flex flex-wrap items-baseline gap-x-2 gap-y-1 py-2 text-sm">
                    <span className="font-medium">{p.label}</span>
                    {p.hints.relation && <Mono>{p.hints.relation.replaceAll("_", " ")}</Mono>}
                    {p.hints.via && <Mono>via {p.hints.via}</Mono>}
                    <Badge variant={p.explored ? "secondary" : "outline"}>{p.explored ? "looked into" : "unexplored"}</Badge>
                    {rels.length > 0 && <span className="basis-full text-xs text-muted-foreground">{[...new Set(rels)].join(", ")}</span>}
                  </li>
                )
              })}
            </ul>
          )}
        </section>
        <div className="grid gap-5 md:grid-cols-2">
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Organizations</h3>
            <ul className="flex flex-wrap gap-1.5">
              {orgs.map((o) => (
                <li key={o.id}><Badge variant="outline">{o.label}</Badge></li>
              ))}
            </ul>
          </section>
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Accounts</h3>
            <ul className="grid gap-1 text-sm">
              {accounts.map((a) => (
                <li key={a.id} className="flex items-baseline gap-2">
                  {a.url ? <a href={a.url} target="_blank" rel="noreferrer" className="text-primary underline-offset-2 hover:underline">{a.label}</a> : <span>{a.label}</span>}
                  {!a.explored && <Mono>not read</Mono>}
                </li>
              ))}
            </ul>
          </section>
        </div>
        {ent.frontier.length > 0 && (
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Frontier (unexplored leads)</h3>
            <ul className="flex flex-wrap gap-1.5">
              {ent.frontier.slice(0, 12).map((f) => (
                <li key={f.id}><Badge variant="secondary">{f.type} · {f.label}</Badge></li>
              ))}
            </ul>
          </section>
        )}
        {byId.size === 0 && null}
      </CardContent>
    </Card>
  )
}
