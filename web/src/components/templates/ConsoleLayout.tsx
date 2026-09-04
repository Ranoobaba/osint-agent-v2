import type { ReactNode } from "react"

// Template: the page skeleton. Slots only; no data.
export function ConsoleLayout({ header, console, results }: { header: ReactNode; console: ReactNode; results?: ReactNode }) {
  return (
    <div className="min-h-svh bg-background text-foreground">
      <header className="border-b">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-3">{header}</div>
      </header>
      <main className="mx-auto grid max-w-4xl gap-6 px-4 py-8">
        {console}
        {results}
      </main>
      <footer className="mx-auto max-w-4xl px-4 pb-8 text-xs text-muted-foreground">
        Reports are built from admitted claims only. Open any stored copy to check a quote against the page as it was read.
      </footer>
    </div>
  )
}
