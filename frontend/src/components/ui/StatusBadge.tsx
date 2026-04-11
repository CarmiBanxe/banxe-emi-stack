/**
 * StatusBadge — BANXE compliance status indicator
 * Uses DESIGN.md color tokens + Lucide icons
 * IL-ADDS-01 | WCAG AA compliant
 */
import { cva, type VariantProps } from 'class-variance-authority'
import {
  Shield,
  Clock,
  X,
  AlertTriangle,
  Search,
} from 'lucide-react'

export type BadgeStatus = 'APPROVED' | 'PENDING' | 'REJECTED' | 'FLAGGED' | 'UNDER_REVIEW'

const badgeVariants = cva(
  'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide border',
  {
    variants: {
      status: {
        APPROVED: [
          'bg-[#10b981]/10',
          'text-[#34d399]',
          'border-[#10b981]/30',
        ],
        PENDING: [
          'bg-[#f59e0b]/10',
          'text-[#fbbf24]',
          'border-[#f59e0b]/30',
        ],
        REJECTED: [
          'bg-[#f43f5e]/10',
          'text-[#f87171]',
          'border-[#f43f5e]/30',
        ],
        FLAGGED: [
          'bg-[#f97316]/10',
          'text-[#fb923c]',
          'border-[#f97316]/30',
        ],
        UNDER_REVIEW: [
          'bg-[#3b82f6]/10',
          'text-[#60a5fa]',
          'border-[#3b82f6]/30',
        ],
      },
    },
    defaultVariants: {
      status: 'PENDING',
    },
  }
)

const statusConfig: Record<
  BadgeStatus,
  { icon: React.ComponentType<{ className?: string; size?: number }>; label: string }
> = {
  APPROVED:    { icon: Shield,        label: 'Approved' },
  PENDING:     { icon: Clock,         label: 'Pending' },
  REJECTED:    { icon: X,             label: 'Rejected' },
  FLAGGED:     { icon: AlertTriangle, label: 'Flagged' },
  UNDER_REVIEW:{ icon: Search,        label: 'Under Review' },
}

export interface StatusBadgeProps extends VariantProps<typeof badgeVariants> {
  status: BadgeStatus
  showIcon?: boolean
  showLabel?: boolean
  className?: string
  'aria-label'?: string
}

export function StatusBadge({
  status,
  showIcon = true,
  showLabel = true,
  className,
  'aria-label': ariaLabel,
}: StatusBadgeProps) {
  const { icon: Icon, label } = statusConfig[status]

  return (
    <span
      className={badgeVariants({ status, className })}
      role="status"
      aria-label={ariaLabel ?? `Status: ${label}`}
    >
      {showIcon && (
        <Icon
          size={12}
          className="shrink-0"
          aria-hidden="true"
        />
      )}
      {showLabel && <span>{label}</span>}
    </span>
  )
}

export default StatusBadge
