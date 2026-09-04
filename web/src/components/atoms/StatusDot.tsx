import { cn } from "@/lib/utils"

const COLORS: Record<string, string> = {
  resolved: "bg-emerald-500",
  ambiguous: "bg-amber-500",
  unresolved: "bg-zinc-400",
  running: "bg-sky-500 animate-pulse",
  failed: "bg-red-500",
}

export function StatusDot({ status, className }: { status: string; className?: string }) {
  return <span aria-hidden className={cn("inline-block size-2.5 rounded-full", COLORS[status] ?? "bg-zinc-400", className)} />
}
