import { Mono } from "@/components/atoms"

export function NotFoundRow({ field, note, searched }: { field: string; note: string | null; searched: string[] }) {
  return (
    <li className="py-2 text-sm">
      <span className="font-medium">{field.replaceAll("_", " ")}</span>
      {note && <span className="text-muted-foreground"> · {note}</span>}
      {searched.length > 0 && (
        <div>
          <Mono>looked in: {searched.join(", ")}</Mono>
        </div>
      )}
    </li>
  )
}
