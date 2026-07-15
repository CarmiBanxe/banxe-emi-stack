/**
 * BalanceCard — Mobile component
 * IL-UI-02 | Expo SDK 53 / React Native
 */
import React from "react";
import { View, Text, StyleSheet } from "react-native";

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

const TOKEN = {
  success: "#34d399",
  danger: "#f87171",
  warning: "#fbbf24",
  bgCard: "#1a1f2e",
  bgBorder: "#2a3044",
  textSecondary: "#94a3b8",
  textMuted: "#64748b",
  textPrimary: "#f1f5f9",
};

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
  const num = parseFloat(balance);
  const amountColor = num > 0 ? TOKEN.success : num < 0 ? TOKEN.danger : TOKEN.warning;

  if (isLoading) {
    return (
      <View
        accessibilityLabel="Loading balance"
        accessibilityState={{ busy: true }}
        style={styles.card}
      >
        <View style={[styles.skeleton, { width: 128, height: 16, marginBottom: 12 }]} />
        <View style={[styles.skeleton, { width: 192, height: 32, marginBottom: 8 }]} />
        <View style={[styles.skeleton, { width: 160, height: 12 }]} />
      </View>
    );
  }

  return (
    <View
      accessibilityLabel={`${accountType} account — ${formatted}`}
      accessibilityRole="none"
      style={styles.card}
    >
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.accountTypeLabel}>{accountType}</Text>
        <View style={styles.badge}>
          <Text style={styles.badgeText}>{accountType}</Text>
        </View>
      </View>

      {/* Amount */}
      <Text
        accessibilityLabel={`Balance: ${formatted}`}
        style={[styles.amount, { color: amountColor, fontVariant: ["tabular-nums"] }]}
      >
        {formatted}
      </Text>

      {/* Account ID */}
      {accountId && (
        <Text
          accessibilityLabel={`Account ID: ${accountId}`}
          style={styles.accountId}
        >
          {accountId}
        </Text>
      )}

      {/* Disclosure footer */}
      <View accessibilityLabel={`Data disclosure: Balance as of ${utcStr}`}>
        <Text style={styles.disclosure}>Balance as of {utcStr}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: TOKEN.bgBorder,
    backgroundColor: TOKEN.bgCard,
    padding: 20,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 12,
  },
  accountTypeLabel: {
    fontSize: 11,
    fontWeight: "600",
    textTransform: "uppercase",
    letterSpacing: 1.5,
    color: TOKEN.textSecondary,
  },
  badge: {
    borderRadius: 999,
    paddingHorizontal: 8,
    paddingVertical: 2,
    backgroundColor: TOKEN.bgBorder,
  },
  badgeText: {
    fontSize: 11,
    fontWeight: "500",
    color: TOKEN.textSecondary,
  },
  amount: {
    fontSize: 28,
    fontWeight: "700",
    marginBottom: 4,
  },
  accountId: {
    fontSize: 12,
    color: TOKEN.textMuted,
    fontFamily: "monospace",
    marginBottom: 12,
  },
  disclosure: {
    fontSize: 11,
    color: TOKEN.textMuted,
  },
  skeleton: {
    borderRadius: 6,
    backgroundColor: TOKEN.bgBorder,
  },
});

export default BalanceCard;
