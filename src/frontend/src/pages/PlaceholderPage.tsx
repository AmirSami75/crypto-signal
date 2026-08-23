import { fa } from '../i18n/fa'
import { Badge } from '../components/ui/Badge'
import { EmptyState } from '../components/ui/EmptyState'

/**
 * Stands in for the screens the sidebar links to but that are not built yet.
 *
 * The destinations are routed and permission-gated now rather than later, so the nav is honest: an
 * entry that is visible leads somewhere, and only entries the account is actually entitled to appear
 * at all. A link that 404s reads as a broken build; a link that says "not built yet" reads as a
 * roadmap.
 *
 * It uses the dashed `EmptyState` rather than a solid card for the same reason: the dashes say the
 * space is reserved, where a finished-looking panel would say this is all there will ever be.
 */
export function PlaceholderPage({ title }: { title: string }) {
  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-[1.375rem] font-semibold">{title}</h1>
        <Badge tone="warn">{fa.common.comingSoon}</Badge>
      </header>

      <EmptyState icon={<BlueprintIcon />} title={fa.placeholder.title} body={fa.placeholder.body} />
    </div>
  )
}

function BlueprintIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" className="size-6">
      <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" />
      <path d="M3.5 9.5h17M9 9.5v10" strokeLinecap="round" />
    </svg>
  )
}
