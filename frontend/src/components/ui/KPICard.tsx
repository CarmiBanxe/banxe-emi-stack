/**
 * KPICard — Key Performance Indicator card
 * Tabular-nums, delta indicator, sparkline
 * IL-ADDS-01
 */
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import {
  LineChart,
  Line,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'

export type DeltaDirection = 'up' | 'down' | 'neutral'

export interface SparklinePoint {
  value: number
}

export interface KPICardProps {
  label: string
  value: string | number
  /** Currency prefix, e.g. "GBP" */
  currency?: string
  delta?: number
  deltaDirection?: DeltaDirection
  deltaLabel?: string
  sparklineData?: SparklinePoint[]
  isLoading?: boolean
  className?: string
}

function DeltaIndicator({
  delta,
  direction,
  label,
}: {
  delta: number
  direction: DeltaDirection
  label?: string
}) {
  const icons = {
    up:      <TrendingUp size={14} aria-hidden="true" />,
    down:    <TrendingDown size={14} aria-hidden="true" />,
    neutral: <Minus size={14} aria-hidden="true" />,
  }
  const colors = {
    up:      'text-[#34d399]',
    down:    'text-[#f87171]',
    neutral: 'text-[oklch(65%_0_0)]',
  }

  const sign = direction === 'up' ? '+' : direction === 'down' ? '' : ''
  const ariaLabel = `${direction === 'up' ? 'Increased' : direction === 'down' ? 'Decreased' : 'Unchanged'} by ${Math.abs(delta)}%${label ? ` vs ${label}` : ''}`

  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-medium tabular-nums ${colors[direction]}`}
      aria-label={ariaLabel}
    >
      {icons[direction]}
      <span>{sign}{delta.toFixed(1)}%</span>
      {label && <span className="text-[oklch(45%_0_0)]">{label}</span>}
    </span>
  )
}

export function KPICard({
  label,
  value,
  currency,
  delta,
  deltaDirection = 'neutral',
  deltaLabel,
  sparklineData,
  isLoading = false,
  className,
}: KPICardProps) {
  const sparklineColor =
    deltaDirection === 'up'
      ? '#10b981'
      : deltaDirection === 'down'
        ? '#f43f5e'
        : '#3b82f6'

  if (isLoading) {
    return (
      <div
        className={`
          rounded-xl border border-[oklch(20%_0.01_240)] bg-[oklch(15%_0.01_240)]
          p-6 animate-pulse h-[140px] ${className ?? ''}
        `}
        aria-busy="true"
        aria-label={`Loading ${label}`}
      >
        <div className="h-3 w-20 rounded bg-[oklch(20%_0.01_240)] mb-3" />
        <div className="h-8 w-32 rounded bg-[oklch(20%_0.01_240)] mb-2" />
        <div className="h-3 w-16 rounded bg-[oklch(20%_0.01_240)]" />
      </div>
    )
  }

  return (
    <article
      className={`
        rounded-xl border border-[oklch(20%_0.01_240)] bg-[oklch(15%_0.01_240)]
        p-6 shadow-md flex flex-col gap-2 h-[140px] ${className ?? ''}
      `}
      aria-label={`${label}: ${currency ? `${currency} ` : ''}${value}`}
    >
      <header className="flex items-start justify-between">
        <p className="text-xs uppercase tracking-widest font-semibold text-[oklch(65%_0_0)]">
          {label}
        </p>
        {sparklineData && sparklineData.length > 0 && (
          <div className="w-20 h-8" aria-hidden="true">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={sparklineData}>
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke={sparklineColor}
                  strokeWidth={1.5}
                  dot={false}
                />
                <Tooltip
                  contentStyle={{ display: 'none' }}
                  cursor={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </header>

      <p className="text-3xl font-bold tabular-nums text-[oklch(95%_0_0)] leading-tight">
        {currency && (
          <span className="text-lg font-medium text-[oklch(65%_0_0)] mr-1">
            {currency}
          </span>
        )}
        {value}
      </p>

      {delta !== undefined && (
        <footer>
          <DeltaIndicator
            delta={delta}
            direction={deltaDirection}
            label={deltaLabel}
          />
        </footer>
      )}
    </article>
  )
}

export default KPICard
