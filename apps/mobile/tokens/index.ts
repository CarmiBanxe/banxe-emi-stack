/**
 * BANXE MD3 Design Tokens — React Native
 * Dark theme values (OKLCH → rgba/hex conversion)
 * Source of truth: DESIGN.md | IL-UI-03
 *
 * React Native does not support CSS custom properties.
 * Values here are the resolved dark-theme equivalents of tokens.css.
 */
export const TOKENS = {
  // ─── Backgrounds (oklch → rgba) ───────────────────────────
  bgCard:      "rgba(38, 40, 46, 1)",      // oklch(15% 0.01 240)
  bgSecondary: "rgba(28, 30, 35, 1)",      // oklch(13% 0.01 240)
  bgPrimary:   "rgba(18, 18, 20, 1)",      // oklch(10% 0 0)

  // ─── Borders ──────────────────────────────────────────────
  borderDefault: "rgba(42, 46, 55, 1)",    // oklch(20% 0.01 240)

  // ─── Text ─────────────────────────────────────────────────
  textPrimary:   "rgba(242, 242, 242, 1)", // oklch(95% 0 0)
  textSecondary: "rgba(148, 148, 148, 1)", // oklch(65% 0 0)
  textMuted:     "rgba(100, 100, 100, 1)", // oklch(45% 0 0)
  textDanger:    "#f87171",                // rose-400   (MD3 error)
  textSuccess:   "#34d399",               // emerald-400 (MD3 tertiary)
  textWarning:   "#fbbf24",               // amber-400   (MD3 secondary)
  brandAccent:   "#3b82f6",               // blue-500    (MD3 primary)

  // ─── Spacing (4px grid) ───────────────────────────────────
  spacing1: 4,
  spacing2: 8,
  spacing3: 12,
  spacing4: 16,
  spacing5: 20,
  spacing6: 24,

  // ─── Border Radius (MD3 shape scale) ──────────────────────
  radiusSm:   4,
  radiusMd:   6,
  radiusLg:   8,
  radiusXl:   12,
  radiusFull: 9999,
} as const;
