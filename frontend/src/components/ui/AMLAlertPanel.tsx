/**
 * AMLAlertPanel — AML alert with severity left-border accent
 * CRITICAL / HIGH / MEDIUM / LOW severity system from DESIGN.md
 * IL-ADDS-01
 */
import { AlertTriangle, Clock, ArrowRight } from 'lucide-react'

export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'

export interface AMLAlert {
  id: string
  severity: Severity
  title: string
  description: string
  timestamp: string
  accountId?: string
  amount?: string
  currency?: string
  ruleId?: string
}

export interface AMLAlertPanelProps {
  alert: AMLAlert
  onReview?: (alertId: string) => void
  compact?: boolean
  className?: string
}

const severityStyles: Record<Severity, {
  borderColor: string
  bgColor: string
  textColor: string
  label: string
}> = {
  CRITICAL: {
    borderColor: '#f43f5e',
    bgColor:     'rgba(244, 63, 94, 0.10)',
    textColor:   '#f87171',
    label:       'CRITICAL',
  },
  HIGH: {
    borderColor: '#f97316',
    bgColor:     'rgba(249, 115, 22, 0.10)',
    textColor:   '#fb923c',
    label:       'HIGH',
  },
  MEDIUM: {
    borderColor: '#f59e0b',
    bgColor:     'rgba(245, 158, 11, 0.08)',
    textColor:   '#fbbf24',
    label:       'MEDIUM',
  },
  LOW: {
    borderColor: 'oklch(45% 0 0)',
    bgColor:     'rgba(100, 100, 100, 0.05)',
    textColor:   'oklch(65% 0 0)',
    label:       'LOW',
  },
}

function formatTimestamp(ts: string): string {
  try {
    return new Intl.DateTimeFormat('en-GB', {
      day:    '2-digit',
      month:  'short',
      hour:   '2-digit',
      minute: '2-digit',
      hour12: false,
      timeZone: 'UTC',
    }).format(new Date(ts)) + ' UTC'
  } catch {
    return ts
  }
}

export function AMLAlertPanel({
  alert,
  onReview,
  compact = false,
  className,
}: AMLAlertPanelProps) {
  const styles = severityStyles[alert.severity]

  return (
    <article
      data-severity={alert.severity.toLowerCase()}
      className={`rounded-lg overflow-hidden ${className ?? ''}`}
      style={{
        borderLeft: `4px solid ${styles.borderColor}`,
        background: styles.bgColor,
        border:     `1px solid oklch(20% 0.01 240)`,
        borderLeftColor: styles.borderColor,
        borderLeftWidth: '4px',
      }}
      aria-label={`AML alert: ${alert.severity} severity — ${alert.title}`}
    >
      <div className={`px-4 ${compact ? 'py-3' : 'py-4'}`}>
        {/* Header */}
        <div className="flex items-start justify-between gap-2 mb-2">
          <div className="flex items-center gap-2">
            <AlertTriangle
              size={14}
              style={{ color: styles.borderColor }}
              aria-hidden="true"
            />
            <span
              className="text-xs font-bold uppercase tracking-widest"
              style={{ color: styles.textColor }}
            >
              {styles.label}
            </span>
            {alert.ruleId && (
              <span className="text-xs text-[oklch(45%_0_0)] font-mono">
                [{alert.ruleId}]
              </span>
            )}
          </div>
          <div className="flex items-center gap-1 text-xs text-[oklch(45%_0_0)] shrink-0">
            <Clock size={11} aria-hidden="true" />
            <time dateTime={alert.timestamp}>{formatTimestamp(alert.timestamp)}</time>
          </div>
        </div>

        {/* Title */}
        <p className="text-sm font-semibold text-[oklch(95%_0_0)] mb-1">
          {alert.title}
        </p>

        {/* Description */}
        {!compact && (
          <p className="text-xs text-[oklch(65%_0_0)] mb-3 leading-relaxed">
            {alert.description}
          </p>
        )}

        {/* Amount + CTA */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {alert.accountId && (
              <span className="text-xs font-mono text-[oklch(45%_0_0)]">
                {alert.accountId}
              </span>
            )}
            {alert.amount && alert.currency && (
              <span
                className="text-xs font-semibold tabular-nums"
                style={{ color: styles.textColor }}
              >
                {alert.currency}&nbsp;{alert.amount}
              </span>
            )}
          </div>

          {onReview && (
            <button
              onClick={() => onReview(alert.id)}
              className="
                inline-flex items-center gap-1.5 text-xs font-semibold
                px-3 py-1.5 rounded-lg border transition-all duration-150
                text-[#60a5fa] border-[#3b82f6]/30 bg-[#3b82f6]/10
                hover:bg-[#3b82f6]/20 hover:border-[#3b82f6]/50
              "
              aria-label={`Review alert ${alert.id}`}
            >
              Review
              <ArrowRight size={11} aria-hidden="true" />
            </button>
          )}
        </div>
      </div>
    </article>
  )
}

export default AMLAlertPanel
