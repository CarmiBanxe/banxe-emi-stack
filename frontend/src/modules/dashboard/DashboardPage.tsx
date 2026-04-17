/**
 * DashboardPage — BANXE main dashboard
 * KPI cards, transactions table, AML alert feed
 * Dark mode only | IL-ADDS-01
 *
 * STYLE ONLY — business logic and API calls preserved as-is.
 */

import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { type AMLAlert, AMLAlertPanel } from "../../components/ui/AMLAlertPanel";
import { type Column, DataTable } from "../../components/ui/DataTable";
import { KPICard } from "../../components/ui/KPICard";
import { Sidebar } from "../../components/ui/Sidebar";
import { type BadgeStatus, StatusBadge } from "../../components/ui/StatusBadge";

// ─── Mock data types ──────────────────────────────────────────────────────────

interface Transaction {
  id: string;
  date: string;
  account: string;
  description: string;
  amount: string;
  currency: string;
  status: BadgeStatus;
}

// ─── Mock data (replace with real API hooks) ──────────────────────────────────

const mockTransactions: Transaction[] = [
  {
    id: "TX-001",
    date: "2026-04-11 09:14 UTC",
    account: "ACC-7821",
    description: "Wire transfer — London HQ",
    amount: "12,500.00",
    currency: "GBP",
    status: "APPROVED",
  },
  {
    id: "TX-002",
    date: "2026-04-11 08:51 UTC",
    account: "ACC-3409",
    description: "SEPA payment — Berlin",
    amount: "3,200.00",
    currency: "EUR",
    status: "PENDING",
  },
  {
    id: "TX-003",
    date: "2026-04-11 08:22 UTC",
    account: "ACC-9012",
    description: "Inbound FPS — Barclays",
    amount: "850.00",
    currency: "GBP",
    status: "APPROVED",
  },
  {
    id: "TX-004",
    date: "2026-04-11 07:45 UTC",
    account: "ACC-1123",
    description: "Outbound — flagged by AML",
    amount: "55,000.00",
    currency: "USD",
    status: "FLAGGED",
  },
  {
    id: "TX-005",
    date: "2026-04-10 23:59 UTC",
    account: "ACC-4402",
    description: "Safeguarding pool top-up",
    amount: "100,000.00",
    currency: "GBP",
    status: "APPROVED",
  },
];

const mockAlerts: AMLAlert[] = [
  {
    id: "AML-001",
    severity: "CRITICAL",
    title: "Large cross-border transfer exceeds threshold",
    description: "Transaction ACC-1123 — USD 55,000 to high-risk jurisdiction. EDD required.",
    timestamp: "2026-04-11T07:45:00Z",
    accountId: "ACC-1123",
    amount: "55,000.00",
    currency: "USD",
    ruleId: "AML-R-042",
  },
  {
    id: "AML-002",
    severity: "HIGH",
    title: "Structuring pattern detected",
    description: "Multiple transactions just below £10,000 threshold within 24 hours.",
    timestamp: "2026-04-11T06:30:00Z",
    accountId: "ACC-7891",
    ruleId: "AML-R-018",
  },
  {
    id: "AML-003",
    severity: "MEDIUM",
    title: "PEP match — enhanced monitoring",
    description: "Customer flagged as Politically Exposed Person. Ongoing monitoring active.",
    timestamp: "2026-04-10T14:20:00Z",
    accountId: "ACC-3301",
    ruleId: "AML-R-007",
  },
];

const mockSparkline = [
  { value: 80 },
  { value: 85 },
  { value: 78 },
  { value: 92 },
  { value: 88 },
  { value: 95 },
  { value: 100 },
];

// ─── Columns config ────────────────────────────────────────────────────────────

const txColumns: Column<Transaction>[] = [
  {
    key: "date",
    header: "Date",
    sortable: true,
    width: "160px",
    render: (v) => <span className="font-mono text-xs text-[oklch(65%_0_0)]">{String(v)}</span>,
  },
  {
    key: "account",
    header: "Account",
    width: "110px",
    render: (v) => <span className="font-mono text-xs text-[#60a5fa]">{String(v)}</span>,
  },
  {
    key: "description",
    header: "Description",
    render: (v) => <span className="text-sm text-[oklch(95%_0_0)]">{String(v)}</span>,
  },
  {
    key: "amount",
    header: "Amount",
    align: "right",
    sortable: true,
    width: "130px",
    render: (v, row) => (
      <span className="tabular-nums font-semibold text-sm text-[oklch(95%_0_0)]">
        {(row as Transaction).currency}&nbsp;{String(v)}
      </span>
    ),
  },
  {
    key: "status",
    header: "Status",
    width: "130px",
    render: (v) => <StatusBadge status={v as BadgeStatus} />,
  },
];

// ─── Page ─────────────────────────────────────────────────────────────────────

export function DashboardPage() {
  const [activeNav, setActiveNav] = useState("overview");
  const [isRefreshing, setIsRefreshing] = useState(false);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    // Placeholder: replace with real data refresh
    await new Promise((resolve) => setTimeout(resolve, 1000));
    setIsRefreshing(false);
  };

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: "oklch(10% 0 0)" }}>
      {/* Sidebar */}
      <Sidebar activeId={activeNav} onNavigate={(item) => setActiveNav(item.id)} />

      {/* Main content */}
      <main className="flex-1 overflow-y-auto flex flex-col">
        {/* Top bar */}
        <header
          className="
            sticky top-0 z-10 flex items-center justify-between px-6
            border-b border-[oklch(20%_0.01_240)]
            bg-[oklch(10%_0_0)]/80 backdrop-blur-sm
          "
          style={{ height: "56px" }}
        >
          <div>
            <h1 className="text-base font-bold text-[oklch(95%_0_0)]">Overview</h1>
            <p className="text-xs text-[oklch(45%_0_0)]">
              Safeguarding Dashboard — {new Date().toLocaleDateString("en-GB", { timeZone: "UTC" })} UTC
            </p>
          </div>

          <button
            onClick={handleRefresh}
            className="
              inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium
              border border-[oklch(25%_0.01_240)] text-[oklch(65%_0_0)]
              hover:text-[oklch(95%_0_0)] hover:border-[oklch(35%_0.01_240)]
              transition-colors duration-150
            "
            aria-label="Refresh dashboard data"
            disabled={isRefreshing}
          >
            <RefreshCw size={13} className={isRefreshing ? "animate-spin" : ""} aria-hidden="true" />
            {isRefreshing ? "Refreshing..." : "Refresh"}
          </button>
        </header>

        <div className="flex-1 p-6 flex flex-col gap-6">
          {/* KPI Cards row */}
          <section aria-label="Key performance indicators">
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
              <KPICard
                label="Total Safeguarded"
                value="2,847,320.00"
                currency="GBP"
                delta={3.2}
                deltaDirection="up"
                deltaLabel="vs yesterday"
                sparklineData={mockSparkline}
              />
              <KPICard
                label="Active Accounts"
                value="1,247"
                delta={1.8}
                deltaDirection="up"
                deltaLabel="vs last week"
                sparklineData={mockSparkline}
              />
              <KPICard
                label="Pending Transactions"
                value="23"
                delta={-12.5}
                deltaDirection="down"
                deltaLabel="vs yesterday"
                sparklineData={[...mockSparkline].reverse()}
              />
              <KPICard
                label="Open AML Alerts"
                value="3"
                delta={50.0}
                deltaDirection="up"
                deltaLabel="vs yesterday"
                sparklineData={[{ value: 1 }, { value: 2 }, { value: 2 }, { value: 3 }]}
              />
            </div>
          </section>

          {/* Transactions + AML feed */}
          <section className="flex flex-col xl:flex-row gap-6" aria-label="Recent activity">
            {/* Transactions table */}
            <div className="flex-1 flex flex-col gap-2">
              <h2 className="text-sm font-semibold text-[oklch(95%_0_0)]">Recent Transactions</h2>
              <DataTable
                data={mockTransactions}
                columns={txColumns}
                aria-label="Recent transactions"
                emptyMessage="No recent transactions."
              />
            </div>

            {/* AML Alert feed */}
            <aside className="xl:w-80 shrink-0 flex flex-col gap-2" aria-label="AML alert feed">
              <h2 className="text-sm font-semibold text-[oklch(95%_0_0)]">AML Alerts</h2>
              <div className="flex flex-col gap-3">
                {mockAlerts.map((alert) => (
                  <AMLAlertPanel
                    key={alert.id}
                    alert={alert}
                    // biome-ignore lint/suspicious/noConsole: mock placeholder — wire to review modal
                    onReview={(id) => console.log("Review alert:", id)}
                  />
                ))}
              </div>
            </aside>
          </section>
        </div>
      </main>
    </div>
  );
}

export default DashboardPage;
