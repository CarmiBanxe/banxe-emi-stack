/**
 * BalanceCard — Account balance display (Mobile / React Native)
 * MD3 tokens as StyleSheet constants (mirrors DESIGN.md / tokens.css)
 * Financial invariants: tabular-nums, Decimal-only display, disclosure header
 * IL-UI-02 | WCAG AA
 */
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  View,
  type ViewStyle,
} from "react-native";

// ─── Types (identical to web — single interface per DESIGN.md convention) ─────

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
  style?: ViewStyle;
}

// ─── MD3 token constants (mirrors tokens.css — no CSS vars in React Native) ──

const TOKENS = {
  // Backgrounds
  bgCard: "rgba(38, 40, 46, 1)", // oklch(15% 0.01 240)
  bgSecondary: "rgba(28, 30, 35, 1)", // oklch(13% 0.01 240)
  bgPrimary: "rgba(18, 18, 20, 1)", // oklch(10% 0 0)

  // Borders
  borderDefault: "rgba(42, 46, 55, 1)", // oklch(20% 0.01 240)

  // Text
  textPrimary: "rgba(242, 242, 242, 1)", // oklch(95% 0 0)
  textSecondary: "rgba(148, 148, 148, 1)", // oklch(65% 0 0)
  textMuted: "rgba(100, 100, 100, 1)", // oklch(45% 0 0)
  textDanger: "#f87171",
  textSuccess: "#34d399",
  textWarning: "#fbbf24",
  brandAccent: "#3b82f6",

  // Spacing
  spacing1: 4,
  spacing2: 8,
  spacing3: 12,
  spacing4: 16,
  spacing5: 20,
  spacing6: 24,

  // Radius (MD3 shape)
  radiusSm: 4,
  radiusMd: 6,
  radiusLg: 8,
  radiusXl: 12,
  radiusFull: 9999,
} as const;

// ─── Account type badge colours ───────────────────────────────────────────────

const ACCOUNT_BADGE: Record<AccountType, { bg: string; text: string }> = {
  Current: { bg: "rgba(59, 130, 246, 0.12)", text: TOKENS.brandAccent },
  Savings: { bg: "rgba(16, 185, 129, 0.12)", text: TOKENS.textSuccess },
  Safeguarding: { bg: "rgba(245, 158, 11, 0.12)", text: TOKENS.textWarning },
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

// ─── Skeleton loading state ───────────────────────────────────────────────────

function Skeleton(): React.ReactElement {
  return (
    <View
      style={styles.card}
      accessible
      accessibilityLabel="Loading balance"
      accessibilityState={{ busy: true }}
    >
      <View style={[styles.skeletonLine, { width: "40%" }]} />
      <View style={[styles.skeletonLine, { width: "65%", height: 36, marginVertical: TOKENS.spacing2 }]} />
      <View style={[styles.skeletonLine, { width: "50%" }]} />
    </View>
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
  style,
}: BalanceCardProps): React.ReactElement {
  if (isLoading) return <Skeleton />;

  const resolvedStatus: BalanceStatus = status ?? deriveStatus(balance);
  const formattedAmount = formatAmount(balance, currency);
  const disclosureTs = formatDisclosureTimestamp(timestamp);
  const badge = ACCOUNT_BADGE[accountType];

  const amountColor =
    resolvedStatus === "negative"
      ? TOKENS.textDanger
      : resolvedStatus === "pending"
        ? TOKENS.textWarning
        : TOKENS.textSuccess;

  return (
    <View
      style={[styles.card, style]}
      accessible
      accessibilityRole="none"
      accessibilityLabel={`${accountType} account balance: ${formattedAmount}`}
    >
      {/* Header row */}
      <View style={styles.headerRow}>
        <Text style={styles.accountLabel}>{accountType} Account</Text>
        <View style={[styles.badge, { backgroundColor: badge.bg }]}>
          <Text style={[styles.badgeText, { color: badge.text }]}>{accountType}</Text>
        </View>
      </View>

      {/* Balance amount */}
      <Text
        style={[styles.amountText, { color: amountColor }]}
        accessibilityLabel={`Balance: ${formattedAmount}`}
      >
        {formattedAmount}
      </Text>

      {/* Account ID */}
      {accountId ? (
        <Text
          style={styles.accountIdText}
          accessibilityLabel={`Account ID: ${accountId}`}
        >
          {accountId}
        </Text>
      ) : null}

      {/* Disclosure header (required per DESIGN.md Financial UI Rules §5) */}
      <View style={styles.disclosureContainer}>
        <Text
          style={styles.disclosureText}
          accessibilityLabel={`Data disclosure: Balance as of ${disclosureTs}`}
        >
          Balance as of {disclosureTs}
        </Text>
      </View>
    </View>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  card: {
    backgroundColor: TOKENS.bgCard,
    borderWidth: 1,
    borderColor: TOKENS.borderDefault,
    borderRadius: TOKENS.radiusXl,
    padding: TOKENS.spacing6,
    gap: TOKENS.spacing3,
  },
  headerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  accountLabel: {
    fontSize: 12,
    fontWeight: "600",
    textTransform: "uppercase",
    letterSpacing: 0.8,
    color: TOKENS.textSecondary,
  },
  badge: {
    paddingHorizontal: TOKENS.spacing2,
    paddingVertical: 2,
    borderRadius: TOKENS.radiusFull,
  },
  badgeText: {
    fontSize: 11,
    fontWeight: "600",
  },
  amountText: {
    fontSize: 30,
    fontWeight: "700",
    fontVariant: ["tabular-nums"],
    lineHeight: 36,
  },
  accountIdText: {
    fontFamily: "JetBrains Mono",
    fontSize: 12,
    color: TOKENS.textMuted,
  },
  disclosureContainer: {
    borderTopWidth: 1,
    borderTopColor: TOKENS.borderDefault,
    paddingTop: TOKENS.spacing3,
    marginTop: TOKENS.spacing1,
  },
  disclosureText: {
    fontSize: 11,
    color: TOKENS.textMuted,
  },
  skeletonLine: {
    height: 12,
    borderRadius: TOKENS.radiusSm,
    backgroundColor: TOKENS.bgSecondary,
  },
});

export default BalanceCard;
