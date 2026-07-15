/**
 * BalanceCard — Web component
 * IL-UI-02 | Next.js 15 / React 19 / Tailwind v4
 */
"use client";

export interface BalanceCardProps {
  balance: string;
  currency: string;
  accountType: "Current" | "Savings" | "Safeguarding";
  timestamp: Date;
  accountId?: string;
  isLoading?: boolean;
}

const CURRENCY_SYMBOL: Record<string, string> = {
  GBP: "£", EUR: "€", USD: "$", CHF: "CHF ",
};

function formatBalance(balance: string, currency: string): string {
  const sym = CURRENCY_SYMBOL[currency] ?? currency + " ";
  const num = parseFloat(balance);
  const abs = Math.abs(num).toLocaleString("en-GB", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return num < 0 ? `-${sym}${abs}` : `${sym}${abs}`;
}

function formatUTC(d: Date): string {
  return d.toISOString().replace("T", " ").slice(0, 19) + " UTC";
}

function getStatus(balance: string): "positive" | "negative" | "pending" {
  const n = parseFloat(balance);
  if (n > 0) return "positive";
  if (n < 0) return "negative";
  return "pending";
}

export function BalanceCard({
  balance,
  currency,
  accountType,
  timestamp,
  accountId,
  isLoading,
}: BalanceCardProps) {
  const formatted = formatBalance(balance, currency);
  const utcStr = formatUTC(timestamp);
  const status = getStatus(balance);

  if (isLoading) {
    return (
      <article
        aria-label="Loading balance"
        aria-busy="true"
        className="rounded-xl border border-[var(--color-bg-tertiary)] bg-[var(--color-bg-card)] p-5 animate-pulse"
      >
        <div className="h-4 w-32 rounded bg-[var(--color-bg-tertiary)] mb-3" />
        <div className="h-8 w-48 rounded bg-[var(--color-bg-tertiary)] mb-2" />
        <div className="h-3 w-40 rounded bg-[var(--color-bg-tertiary)]" />
      </article>
    );
  }

  const statusColor: Record<string, string> = {
    positive: "var(--color-success)",
    negative: "var(--color-text-danger)",
    pending: "var(--color-warning)",
  };

  return (
    <article
      aria-label={`${accountType} account — ${formatted}`}
      className="rounded-xl border border-[var(--color-bg-tertiary)] bg-[var(--color-bg-card)] p-5"
    >
      {/* Header */}
      <header className="flex items-center justify-between mb-3">
        <span className="text-xs font-semibold uppercase tracking-widest text-[var(--color-text-secondary)]">
          {accountType}
        </span>
        <span className="rounded-full px-2 py-0.5 text-xs font-medium bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)]">
          {accountType}
        </span>
      </header>

      {/* Amount */}
      <p
        aria-label={`Balance: ${formatted}`}
        data-status={status}
        style={{
          fontVariantNumeric: "tabular-nums",
          color: statusColor[status],
          fontVariant: "tabular-nums",
        } as React.CSSProperties}
        className="text-3xl font-bold mb-1"
      >
        {formatted}
      </p>

      {/* Account ID */}
      {accountId && (
        <p
          aria-label={`Account ID: ${accountId}`}
          style={{ fontFamily: "var(--font-mono)" }}
          className="text-xs text-[var(--color-text-muted)] mb-3"
        >
          {accountId}
        </p>
      )}

      {/* Disclosure footer */}
      <footer
        aria-label={`Data disclosure: Balance as of ${utcStr}`}
      >
        <p className="text-xs text-[var(--color-text-muted)]">
          Balance as of {utcStr}
        </p>
      </footer>
    </article>
  );
}

export default BalanceCard;
