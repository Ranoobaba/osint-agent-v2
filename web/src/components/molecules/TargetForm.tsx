import { useState, type FormEvent } from "react"
import { Button, Input } from "@/components/atoms"

const EXAMPLES = ["Michael Jordan, UC Berkeley", "the CTO of Ariglad", "Michael Chen, Stanford"]

export function TargetForm({ onSubmit, busy }: { onSubmit: (target: string) => void; busy: boolean }) {
  const [value, setValue] = useState("")
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const t = value.trim()
    if (t.length >= 2 && !busy) onSubmit(t)
  }
  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <div className="flex gap-2">
        <Input
          autoFocus
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="A name, an email, a handle, or a role at a company"
          aria-label="Target"
          disabled={busy}
          className="h-11 text-base"
        />
        <Button type="submit" size="lg" disabled={busy || value.trim().length < 2} className="h-11">
          {busy ? "Investigating" : "Investigate"}
        </Button>
      </div>
      <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
        <span>Try:</span>
        {EXAMPLES.map((ex) => (
          <button key={ex} type="button" disabled={busy} onClick={() => setValue(ex)} className="underline-offset-2 hover:underline disabled:opacity-50">
            {ex}
          </button>
        ))}
      </div>
    </form>
  )
}
