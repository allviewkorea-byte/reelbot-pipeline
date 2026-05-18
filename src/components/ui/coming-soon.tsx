import { Construction } from "lucide-react"

interface ComingSoonProps {
  title: string
  description?: string
  step?: string
}

export function ComingSoon({ title, description, step }: ComingSoonProps) {
  return (
    <div className="flex flex-1 flex-col p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-foreground">{title}</h1>
        {description && (
          <p className="mt-1 text-sm text-muted-foreground">{description}</p>
        )}
      </div>

      <div className="flex flex-1 items-center justify-center rounded-xl border border-dashed border-border bg-card/50">
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 border border-primary/20">
            <Construction className="h-6 w-6 text-primary/60" />
          </div>
          <p className="text-sm font-medium text-muted-foreground">Coming Soon</p>
          {step && (
            <p className="mt-1 text-xs text-muted-foreground/60">{step}에서 구현 예정</p>
          )}
        </div>
      </div>
    </div>
  )
}
