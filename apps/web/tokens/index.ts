/**
 * BANXE MD3 Design Tokens — Web (CSS custom property references)
 * Source of truth: DESIGN.md / tokens.css (dark theme OKLCH)
 * IL-UI-03
 */
export const tokens = {
  color: {
    primary: "var(--color-brand-accent)",       // #3b82f6
    surface: "var(--color-bg-card)",             // oklch(15% 0.01 240)
    bgSecondary: "var(--color-bg-secondary)",
    borderDefault: "var(--color-border-default)",
    textPrimary: "var(--color-text-primary)",
    textSecondary: "var(--color-text-secondary)",
    textMuted: "var(--color-text-muted)",
    textSuccess: "var(--color-text-success)",    // #34d399
    textDanger: "var(--color-text-danger)",      // #f87171
    textWarning: "var(--color-text-warning)",    // #fbbf24
  },
  font: {
    mono: "var(--font-mono)",
  },
} as const;
