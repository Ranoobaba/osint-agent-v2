import { cn } from "@/lib/utils"
import type { ReactNode } from "react"

export function Mono({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("font-mono text-xs text-muted-foreground", className)}>{children}</span>
}
