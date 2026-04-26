/**
 * BalanceCard — Account balance display (Web / React)
 * MD3 tokens via CSS custom properties (tokens.css required)
 * Financial invariants: tabular-nums, Decimal-only display, disclosure header
 * IL-UI-02 | WCAG AA
 */
import "../../tokens/tokens.css";
import type { CSSProperties } from "react";

// ─── Types ────────────────────────────────────────────────────────────────────

export type AccountType = "Current" | "Savings" | "Safeguarding";
export type BalanceStatus = "positive" | "negative" | "pending";

export interface BalanceCardProps {
  /** DecimalString — always string at component boundary (I-01) */
  balance: string;
  currency: string;
  accountType: AccountType;
  /** UTC timestamp of the balance snapshot */
  timestamp: Date;
  accountId?: string;
  /** Explicit status override; derived from balance sign when omitted */
  status?: BalanceStatus;
  isLoading?: boolean;
  className?: string;
}

// ─── Token map (mirrors DESIGN.md / tokens.css) ──────────────────────────────

const TOKEN = {
  bgCard: "var(--color-bg-card)",
  bgSecondary: "var(--color-bg-secondary)",
  borderDefault: "var(--color-border-default)",
  textPrimary: "var(--color-text-primary)",
  textSecondary: "var(--color-text-secondary)",
  textMuted: "var(--color-text-muted)",
  textSuccess: "var(--color-text-success)",
  textDanger: "var(--color-text-danger)",
  textWarning: "var(--color-text-warning)",
  brandAccent: "var(--color-brand-accent)",
  radiusXl: "var(--radius-xl)",
  shadowMd: "var(--shadow-md)",
  spacingBase: "var(--spacing-6)",
  fontMono: "var(--font-mono)",
} as const;

// ─── Account type badge colours ───────────────────────────────────────────────

const ACCOUNT_BADGE: Record<AccountType, { bg: string; text: string }> = {
  Current: { bg: "rgba(59, 130, 246, 0.12)", text: TOKEN.brandAccent },
  Savings: { bg: "rgba(16, 185, 129, 0.12)", text: TOKEN.textSuccess },
  Safeguarding: { bg: "rgba(245, 158, 11, 0.12)", text: TOKEN.textWarning },
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function deriveStatus(balance: string): BalanceStatus {
  const trimmed = balance.replace(/[,\s]/g, "");
  if (trimmed.startsWith("-")) return "negative";
  if (trimmed === "0" || trimmed === "0.00") return "pending";
  return "positive";
}

function formatAmount(balance: string, currency: string): string {
  try {
    const numeric = Number(balance.replace(/,/g, ""));
    if (Number.isNaN(numeric)) return `${currency} ${balance}`;
    return new Intl.NumberFormat("en-GB", {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(numeric);
  } catch {
    return `${currency}\u00A0${balance}`;
  }
}

function formatDisclosureTimestamp(ts: Date): string {
  return `${ts.toISOString().replace("T", " ").slice(0, 19)} UTC`;
}

// ─── Subcomponents ────────────────────────────────────────────────────────────

function Skeleton(): React.ReactElement {
  const s: CSSProperties = {
    background: `linear-gradient(90deg, ${TOKEN.bgCard} 0%, ${TOKEN.bgSecondary} 50%, ${TOKEN.bgCard} 100%)`,
    backgroundSize: "200% 100%",
    animation: "banxe-shimmer 1.5s infinite",
    borderRadius: "var(--radius-sm)",
  };
  return (
    <article
      style={{
        background: TOKEN.bgCard,
        border: `1px solid ${TOKEN.borderDefault}`,
        borderRadius: TOKEN.radiusXl,
        boxShadow: TOKEN.shadowMd,
        padding: TOKEN.spacingBase,
        display: "flex",
        flexDirection: "column",
        gap: "var(--spacing-4)",
      }}
      aria-busy="true"
      aria-label="Loading balance"
    >
      <div style={{ ...s, height: 12, width: "40%" }} />
      <div style={{ ...s, height: 36, width: "65%" }} />
      <div style={{ ...s, height: 10, width: "50%" }} />
    </article>
  );
}

// ─── BalanceCard ──────────────────────────────────────────────────────────────

export function BalanceCard({
  balance,
  currency,
  accountType,
  timestamp,
  accountId,
  status,
  isLoading = false,
  className,
}: BalanceCardProps): React.ReactElement {
  if (isLoading) return <Skeleton />;

  const resolvedStatus: BalanceStatus = status ?? deriveStatus(balance);
  const formattedAmount = formatAmount(balance, currency);
  const disclosureTs = formatDisclosureTimestamp(timestamp);
  const badge = ACCOUNT_BADGE[accountType];

  const amountColor =
    resolvedStatus === "negative"
      ? TOKEN.textDanger
      : resolvedStatus === "pending"
        ? TOKEN.textWarning
        : TOKEN.textSuccess;

  return (
    <article
      className={className}
      style={{
        background: TOKEN.bgCard,
        border: `1px solid ${TOKEN.borderDefault}`,
        borderRadius: TOKEN.radiusXl,
        boxShadow: TOKEN.shadowMd,
        padding: TOKEN.spacingBase,
        display: "flex",
        flexDirection: "column",
        gap: "var(--spacing-3)",
      }}
      aria-label={`${accountType} account — ${formattedAmount}`}
      data-financial
    >
      {/* Header row */}
      <header
        style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
      >
        <span
          style={{
            fontSize: "var(--font-size-xs)",
            fontWeight: "var(--font-weight-semibold)",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            color: TOKEN.textSecondary,
          }}
        >
          {accountType} Account
        </span>
        <span
          style={{
            fontSize: "var(--font-size-xs)",
            fontWeight: "var(--font-weight-semibold)",
            background: badge.bg,
            color: badge.text,
            padding: "2px 8px",
            borderRadius: "var(--radius-full)",
          }}
        >
          {accountType}
        </span>
      </header>

      {/* Balance amount */}
      <p
        data-status={resolvedStatus}
        style={{
          fontSize: "var(--font-size-3xl)",
          fontWeight: "var(--font-weight-bold)",
          fontVariantNumeric: "tabular-nums",
          fontFeatureSettings: '"tnum" 1',
          color: amountColor,
          lineHeight: "var(--line-height-tight)",
          margin: 0,
        }}
        aria-label={`Balance: ${formattedAmount}`}
      >
        {formattedAmount}
      </p>

      {/* Account ID */}
      {accountId && (
        <p
          style={{
            fontFamily: TOKEN.fontMono,
            fontSize: "var(--font-size-xs)",
            color: TOKEN.textMuted,
            margin: 0,
          }}
          aria-label={`Account ID: ${accountId}`}
        >
          {accountId}
        </p>
      )}

      {/* Disclosure header (required on all financial data components per DESIGN.md) */}
      <footer
        style={{
          fontSize: "var(--font-size-xs)",
          color: TOKEN.textMuted,
          borderTop: `1px solid ${TOKEN.borderDefault}`,
          paddingTop: "var(--spacing-3)",
          marginTop: "auto",
        }}
        aria-label={`Data disclosure: Balance as of ${disclosureTs}`}
      >
        Balance as of {disclosureTs}
      </footer>
    </article>
  );
}

export default BalanceCard;
