/**
 * AMLMonitor — AML alert monitor with dense table, risk heatmap, case detail
 * Filters: severity, date range, status | Bulk actions
 * IL-ADDS-01
 */
import { useState } from 'react'
import { Sidebar } from '../../components/ui/Sidebar'
import { DataTable, type Column, type BatchAction } from '../../components/ui/DataTable'
import { AMLAlertPanel, type AMLAlert, type Severity } from '../../components/ui/AMLAlertPanel'
import { StatusBadge, type BadgeStatus } from '../../components/ui/StatusBadge'
import {
  Filter,
  X as CloseIcon,
  ArrowUpRight,
  Users,
  XCircle,
} from 'lucide-react'

// ─── Extended alert type for table ───────────────────────────────────────────

interface AMLTableRow {
  id: string
  severity: Severity
  title: string
  accountId: string
  amount: string
  currency: string
  timestamp: string
  status: BadgeStatus
  ruleId: string
}

const MOCK_ALERTS: AMLTableRow[] = [
  {
    id: 'AML-001',
    severity: 'CRITICAL',
    title: 'Large cross-border transfer',
    accountId: 'ACC-1123',
    amount: '55,000.00',
    currency: 'USD',
    timestamp: '2026-04-11 07:45 UTC',
    status: 'FLAGGED',
    ruleId: 'AML-R-042',
  },
  {
    id: 'AML-002',
    severity: 'HIGH',
    title: 'Structuring pattern detected',
    accountId: 'ACC-7891',
    amount: '9,800.00',
    currency: 'GBP',
    timestamp: '2026-04-11 06:30 UTC',
    status: 'UNDER_REVIEW',
    ruleId: 'AML-R-018',
  },
  {
    id: 'AML-003',
    severity: 'MEDIUM',
    title: 'PEP match — enhanced monitoring',
    accountId: 'ACC-3301',
    amount: '0.00',
    currency: 'GBP',
    timestamp: '2026-04-10 14:20 UTC',
    status: 'UNDER_REVIEW',
    ruleId: 'AML-R-007',
  },
  {
    id: 'AML-004',
    severity: 'HIGH',
    title: 'Sanctioned country IP access',
    accountId: 'ACC-5512',
    amount: '1,200.00',
    currency: 'EUR',
    timestamp: '2026-04-10 11:05 UTC',
    status: 'PENDING',
    ruleId: 'AML-R-031',
  },
  {
    id: 'AML-005',
    severity: 'LOW',
    title: 'Velocity threshold exceeded',
    accountId: 'ACC-2210',
    amount: '500.00',
    currency: 'GBP',
    timestamp: '2026-04-09 18:00 UTC',
    status: 'APPROVED',
    ruleId: 'AML-R-002',
  },
]

const SEVERITY_ORDER: Record<Severity, number> = {
  CRITICAL: 0,
  HIGH:     1,
  MEDIUM:   2,
  LOW:      3,
}

const SEVERITY_DOT: Record<Severity, string> = {
  CRITICAL: '#f43f5e',
  HIGH:     '#f97316',
  MEDIUM:   '#f59e0b',
  LOW:      'oklch(45% 0 0)',
}

// ─── Risk Heatmap ─────────────────────────────────────────────────────────────

function RiskHeatmap({ rows }: { rows: AMLTableRow[] }) {
  const bySeverity = Object.entries(
    rows.reduce<Record<Severity, number>>((acc, r) => {
      acc[r.severity] = (acc[r.severity] ?? 0) + 1
      return acc
    }, {} as Record<Severity, number>)
  ).sort(([a], [b]) => SEVERITY_ORDER[a as Severity] - SEVERITY_ORDER[b as Severity])

  const maxCount = Math.max(...bySeverity.map(([, n]) => n), 1)

  return (
    <div
      className="rounded-xl border border-[oklch(20%_0.01_240)] bg-[oklch(13%_0.01_240)] p-4"
      aria-label="Risk heatmap by severity"
    >
      <h3 className="text-xs uppercase tracking-widest font-semibold text-[oklch(65%_0_0)] mb-3">
        Risk Distribution
      </h3>
      <div className="space-y-2" role="list">
        {bySeverity.map(([severity, count]) => (
          <div key={severity} className="flex items-center gap-3" role="listitem">
            <span
              className="text-xs font-bold w-16 shrink-0"
              style={{ color: SEVERITY_DOT[severity as Severity] }}
            >
              {severity}
            </span>
            <div className="flex-1 h-5 rounded-full bg-[oklch(17%_0.01_240)] overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${(count / maxCount) * 100}%`,
                  background: SEVERITY_DOT[severity as Severity],
                  opacity: 0.7,
                }}
                aria-label={`${count} ${severity} alerts`}
              />
            </div>
            <span className="text-xs tabular-nums text-[oklch(65%_0_0)] w-4 text-right">
              {count}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Case Detail Slide-out ────────────────────────────────────────────────────

function CaseDetailPanel({
  alert,
  onClose,
}: {
  alert: AMLTableRow | null
  onClose: () => void
}) {
  if (!alert) return null

  const fullAlert: AMLAlert = {
    id: alert.id,
    severity: alert.severity,
    title: alert.title,
    description: `Account ${alert.accountId} flagged by rule ${alert.ruleId}. Amount: ${alert.currency} ${alert.amount}. Review required per FCA CASS 15 / MLR 2017.`,
    timestamp: new Date().toISOString(),
    accountId: alert.accountId,
    amount: alert.amount,
    currency: alert.currency,
    ruleId: alert.ruleId,
  }

  return (
    <aside
      className="
        fixed inset-y-0 right-0 w-80 z-40
        border-l border-[oklch(20%_0.01_240)]
        bg-[oklch(13%_0.01_240)] flex flex-col
        shadow-lg
      "
      aria-label={`Case detail: ${alert.id}`}
      role="dialog"
      aria-modal="true"
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-[oklch(20%_0.01_240)]">
        <h2 className="text-sm font-bold text-[oklch(95%_0_0)]">Case Detail</h2>
        <button
          onClick={onClose}
          className="text-[oklch(45%_0_0)] hover:text-[oklch(65%_0_0)] transition-colors"
          aria-label="Close case detail"
        >
          <CloseIcon size={16} aria-hidden="true" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <AMLAlertPanel alert={fullAlert} />

        <div className="rounded-lg border border-[oklch(20%_0.01_240)] bg-[oklch(15%_0.01_240)] p-3 space-y-2">
          <p className="text-xs uppercase tracking-widest font-semibold text-[oklch(45%_0_0)]">
            Case Info
          </p>
          <div className="space-y-1.5 text-xs">
            <div className="flex justify-between">
              <span className="text-[oklch(65%_0_0)]">Case ID</span>
              <span className="font-mono text-[oklch(95%_0_0)]">{alert.id}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[oklch(65%_0_0)]">Rule</span>
              <span className="font-mono text-[oklch(95%_0_0)]">{alert.ruleId}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[oklch(65%_0_0)]">Account</span>
              <span className="font-mono text-[#60a5fa]">{alert.accountId}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[oklch(65%_0_0)]">Amount</span>
              <span className="tabular-nums font-semibold text-[oklch(95%_0_0)]">
                {alert.currency}&nbsp;{alert.amount}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-[oklch(65%_0_0)]">Status</span>
              <StatusBadge status={alert.status} />
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="space-y-2">
          <button className="w-full py-2 px-3 rounded-lg text-sm font-medium bg-[#3b82f6] text-white hover:bg-[#2563eb] transition-colors">
            Escalate to MLRO
          </button>
          <button className="w-full py-2 px-3 rounded-lg text-sm font-medium border border-[oklch(25%_0.01_240)] text-[oklch(65%_0_0)] hover:text-[oklch(95%_0_0)] transition-colors">
            Assign to Officer
          </button>
          <button className="w-full py-2 px-3 rounded-lg text-sm font-medium border border-[#f43f5e]/30 text-[#f87171] hover:bg-[#f43f5e]/10 transition-colors">
            Close Case
          </button>
        </div>
      </div>
    </aside>
  )
}

// ─── Main AMLMonitor ──────────────────────────────────────────────────────────

export function AMLMonitor() {
  const [activeNav, setActiveNav] = useState('aml')
  const [selectedAlert, setSelectedAlert] = useState<AMLTableRow | null>(null)
  const [severityFilter, setSeverityFilter] = useState<Severity | 'ALL'>('ALL')
  const [statusFilter, setStatusFilter] = useState<BadgeStatus | 'ALL'>('ALL')

  const filteredAlerts = MOCK_ALERTS
    .filter(a => severityFilter === 'ALL' || a.severity === severityFilter)
    .filter(a => statusFilter === 'ALL' || a.status === statusFilter)
    .sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity])

  const batchActions: BatchAction[] = [
    {
      label: 'Escalate',
      icon: ArrowUpRight,
      onClick: (ids) => console.log('Escalate:', ids),
      variant: 'danger',
    },
    {
      label: 'Assign',
      icon: Users,
      onClick: (ids) => console.log('Assign:', ids),
    },
    {
      label: 'Close',
      icon: XCircle,
      onClick: (ids) => console.log('Close:', ids),
    },
  ]

  const columns: Column<AMLTableRow>[] = [
    {
      key: 'severity',
      header: 'Severity',
      width: '110px',
      sortable: true,
      render: (v) => {
        const sev = v as Severity
        return (
          <span
            className="inline-flex items-center gap-1.5 text-xs font-bold uppercase"
            style={{ color: SEVERITY_DOT[sev] }}
          >
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ background: SEVERITY_DOT[sev] }}
              aria-hidden="true"
            />
            {sev}
          </span>
        )
      },
    },
    {
      key: 'id',
      header: 'Case ID',
      width: '100px',
      render: (v) => (
        <span className="font-mono text-xs text-[#60a5fa]">{String(v)}</span>
      ),
    },
    {
      key: 'title',
      header: 'Alert',
      render: (v) => (
        <span className="text-sm text-[oklch(95%_0_0)]">{String(v)}</span>
      ),
    },
    {
      key: 'accountId',
      header: 'Account',
      width: '100px',
      render: (v) => (
        <span className="font-mono text-xs text-[oklch(65%_0_0)]">{String(v)}</span>
      ),
    },
    {
      key: 'amount',
      header: 'Amount',
      align: 'right',
      width: '130px',
      render: (v, row) => (
        <span className="tabular-nums text-sm font-semibold text-[oklch(95%_0_0)]">
          {(row as AMLTableRow).currency}&nbsp;{String(v)}
        </span>
      ),
    },
    {
      key: 'timestamp',
      header: 'Timestamp',
      width: '150px',
      render: (v) => (
        <span className="font-mono text-xs text-[oklch(45%_0_0)]">{String(v)}</span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      width: '130px',
      render: (v) => <StatusBadge status={v as BadgeStatus} />,
    },
  ]

  return (
    <div
      className="flex h-screen overflow-hidden"
      style={{ background: 'oklch(10% 0 0)' }}
    >
      <Sidebar
        activeId={activeNav}
        onNavigate={(item) => setActiveNav(item.id)}
      />

      <main className="flex-1 overflow-y-auto flex flex-col">
        {/* Header */}
        <header
          className="
            sticky top-0 z-10 flex items-center justify-between px-6
            border-b border-[oklch(20%_0.01_240)]
            bg-[oklch(10%_0_0)]/80 backdrop-blur-sm
          "
          style={{ height: '56px' }}
        >
          <div>
            <h1 className="text-base font-bold text-[oklch(95%_0_0)]">AML Monitor</h1>
            <p className="text-xs text-[oklch(45%_0_0)]">
              {filteredAlerts.length} alerts — sorted by severity
            </p>
          </div>

          {/* Filters */}
          <div className="flex items-center gap-2" role="toolbar" aria-label="Alert filters">
            <Filter size={13} className="text-[oklch(45%_0_0)]" aria-hidden="true" />
            <select
              value={severityFilter}
              onChange={e => setSeverityFilter(e.target.value as Severity | 'ALL')}
              className="text-xs bg-[oklch(15%_0.01_240)] border border-[oklch(25%_0.01_240)] text-[oklch(95%_0_0)] rounded-lg px-2 py-1"
              aria-label="Filter by severity"
            >
              <option value="ALL">All Severities</option>
              <option value="CRITICAL">Critical</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>
            <select
              value={statusFilter}
              onChange={e => setStatusFilter(e.target.value as BadgeStatus | 'ALL')}
              className="text-xs bg-[oklch(15%_0.01_240)] border border-[oklch(25%_0.01_240)] text-[oklch(95%_0_0)] rounded-lg px-2 py-1"
              aria-label="Filter by status"
            >
              <option value="ALL">All Statuses</option>
              <option value="FLAGGED">Flagged</option>
              <option value="UNDER_REVIEW">Under Review</option>
              <option value="PENDING">Pending</option>
              <option value="APPROVED">Approved</option>
            </select>
          </div>
        </header>

        <div className="flex-1 p-6 flex flex-col gap-6">
          {/* Risk heatmap */}
          <RiskHeatmap rows={MOCK_ALERTS} />

          {/* Alert table */}
          <section aria-label="AML alert table">
            <DataTable
              data={filteredAlerts}
              columns={columns}
              batchActions={batchActions}
              inlineActions={[
                {
                  label: 'Review',
                  onClick: (row) => setSelectedAlert(row),
                  variant: 'default',
                },
              ]}
              aria-label="AML alerts"
              emptyMessage="No alerts match the current filters."
            />
          </section>
        </div>
      </main>

      {/* Case detail slide-out */}
      {selectedAlert && (
        <>
          <div
            className="fixed inset-0 bg-black/40 z-30"
            onClick={() => setSelectedAlert(null)}
            aria-hidden="true"
          />
          <CaseDetailPanel
            alert={selectedAlert}
            onClose={() => setSelectedAlert(null)}
          />
        </>
      )}
    </div>
  )
}

export default AMLMonitor
