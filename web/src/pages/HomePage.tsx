import { Mono } from "@/components/atoms"
import { EntitiesPanel, FindingsList, HonestyPanel, IdentityPanel, InvestigationConsole } from "@/components/organisms"
import { ConsoleLayout } from "@/components/templates/ConsoleLayout"
import { useInvestigation } from "@/hooks/useInvestigation"

export function HomePage() {
  const { state, start, reset } = useInvestigation()
  const report = state.phase === "done" ? state.report : null
  return (
    <ConsoleLayout
      header={
        <>
          <span className="font-semibold tracking-tight">osint-agent-v2</span>
          <Mono>people intelligence, scorer first</Mono>
        </>
      }
      console={<InvestigationConsole state={state} onStart={start} onReset={reset} />}
      results={
        report && state.jobId ? (
          <>
            <IdentityPanel report={report} />
            <FindingsList report={report} jobId={state.jobId} />
            <EntitiesPanel report={report} />
            <HonestyPanel report={report} />
          </>
        ) : undefined
      }
    />
  )
}
