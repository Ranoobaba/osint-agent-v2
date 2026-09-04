import { useEffect, useState } from "react"
import { Input, Mono } from "@/components/atoms"
import { getApiKey, health, setApiKey } from "@/lib/api"

export function ApiKeyField() {
  const [locked, setLocked] = useState(false)
  const [value, setValue] = useState(getApiKey())
  useEffect(() => { health().then((h) => setLocked(!!h.locked)).catch(() => setLocked(false)) }, [])
  if (!locked) return null
  return (
    <label className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <Mono>API key</Mono>
      <Input
        type="password"
        value={value}
        onChange={(e) => { setValue(e.target.value); setApiKey(e.target.value.trim()) }}
        placeholder="required: this endpoint is locked"
        aria-label="API key"
        className="h-8 max-w-xs text-xs"
      />
      <span>Stored only in this browser.</span>
    </label>
  )
}
