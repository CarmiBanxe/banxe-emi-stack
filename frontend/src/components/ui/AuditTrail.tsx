/**
 * AuditTrail — Append-only, monospace audit log display
 * JetBrains Mono, read-only, 90-day retention indicator
 * IL-ADDS-01 | FCA CASS 15 compliant
 */
import { Lock, Clock, User, Activity } from 'lucide-react'

export interface AuditEntry {
  id: string
  timestamp: string   // ISO 8601 UTC
  userId: string
  action: string
  resource: string
  resourceId?: string
  details?: string
  ipAddress?: string
  outcome: 'SUCCESS' | 'FAILURE' | 'WARNING'
}

export interface AuditTrailProps {
  entries: AuditEntry[]
  retentionDays?: number
  isLoading?: boolean
  maxEntries?: number
  className?: string
}

const outcomeStyles: Record<AuditEntry['outcome'], string> = {
  SUCCESS: 'text-[#34d399]',
  FAILURE: 'text-[#f87171]',
  WARNING: 'text-[#fbbf24]',
}

function formatTimestamp(ts: string): string {
  try {
    return new Date(ts).toISOString().replace('T', ' ').slice(0, 19) + ' UTC'
  } catch {
    return ts
  }
}

function maskUserId(userId: string): string {
  // Show first 4 + last 4 chars, mask middle for privacy
  if (userId.length <= 8) return userId
  return `${userId.slice(0, 4)}****${userId.slice(-4)}`
}

export function AuditTrail({
  entries,
  retentionDays = 90,
  isLoading = false,
  maxEntries = 100,
  className,
}: AuditTrailProps) {
  const displayed = entries.slice(0, maxEntries)

  return (
    <section
      className={`
        rounded-xl border border-[oklch(20%_0.01_240)]
        bg-[oklch(13%_0.01_240)] overflow-hidden ${className ?? ''}
      `}
      aria-label="Audit trail"
    >
      {/* Header */}
      <div
        className="
          flex items-center justify-between px-4 py-3
          border-b border-[oklch(20%_0.01_240)]
          bg-[oklch(15%_0.01_240)]
        "
      >
        <div className="flex items-center gap-2">
          <Lock size={14} className="text-[#60a5fa]" aria-hidden="true" />
          <h2 className="text-xs font-bold uppercase tracking-widest text-[oklch(65%_0_0)]">
            Audit Trail
          </h2>
          <span className="text-xs text-[oklch(45%_0_0)]">(read-only)</span>
        </div>
        <div className="flex items-center gap-1 text-xs text-[oklch(45%_0_0)]">
          <Clock size={11} aria-hidden="true" />
          <span>{retentionDays}-day retention</span>
        </div>
      </div>

      {/* Entries */}
      <div
        className="overflow-y-auto"
        style={{ maxHeight: '400px' }}
        role="log"
        aria-live="polite"
        aria-relevant="additions"
        aria-label={`Audit log with ${entries.length} entries`}
      >
        {isLoading ? (
          <div className="p-4 space-y-2">
            {[...Array(5)].map((_, i) => (
              <div
                key={i}
                className="h-5 rounded animate-pulse bg-[oklch(17%_0.01_240)]"
                aria-hidden="true"
              />
            ))}
          </div>
        ) : displayed.length === 0 ? (
          <p className="px-4 py-8 text-center text-xs text-[oklch(45%_0_0)]">
            No audit entries found.
          </p>
        ) : (
          <ol className="divide-y divide-[oklch(17%_0.01_240)]" reversed>
            {displayed.map(entry => (
              <li
                key={entry.id}
                className="px-4 py-2 hover:bg-[oklch(15%_0.01_240)] transition-colors"
              >
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 font-mono text-xs">
                  {/* Timestamp */}
                  <time
                    dateTime={entry.timestamp}
                    className="text-[oklch(45%_0_0)] shrink-0"
                  >
                    {formatTimestamp(entry.timestamp)}
                  </time>

                  {/* User ID */}
                  <span className="flex items-center gap-1 text-[oklch(55%_0_0)]">
                    <User size={10} aria-hidden="true" />
                    <span aria-label={`User: ${entry.userId}`}>
                      {maskUserId(entry.userId)}
                    </span>
                  </span>

                  {/* Action */}
                  <span className="flex items-center gap-1 text-[#60a5fa] font-semibold">
                    <Activity size={10} aria-hidden="true" />
                    {entry.action}
                  </span>

                  {/* Resource */}
                  <span className="text-[oklch(65%_0_0)]">
                    {entry.resource}
                    {entry.resourceId && (
                      <span className="text-[oklch(45%_0_0)] ml-1">
                        [{entry.resourceId}]
                      </span>
                    )}
                  </span>

                  {/* Outcome */}
                  <span
                    className={`font-bold ${outcomeStyles[entry.outcome]}`}
                    aria-label={`Outcome: ${entry.outcome}`}
                  >
                    {entry.outcome}
                  </span>

                  {/* Details */}
                  {entry.details && (
                    <span className="text-[oklch(45%_0_0)] italic">
                      — {entry.details}
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>

      {/* Footer */}
      {entries.length > maxEntries && (
        <div
          className="
            px-4 py-2 border-t border-[oklch(20%_0.01_240)]
            text-xs text-[oklch(45%_0_0)] text-center
          "
        >
          Showing {maxEntries} of {entries.length} entries.
          Export full log for complete audit history.
        </div>
      )}
    </section>
  )
}

export default AuditTrail
