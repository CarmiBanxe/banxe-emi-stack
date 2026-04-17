/**
 * BANXE Tailwind Configuration
 * Extends theme with DESIGN.md tokens
 * IL-ADDS-01 | Dark mode: class strategy
 */
import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // ─── Backgrounds ──────────────────────────────────────
        "bg-primary": "var(--color-bg-primary)",
        "bg-secondary": "var(--color-bg-secondary)",
        "bg-tertiary": "var(--color-bg-tertiary)",
        "bg-card": "var(--color-bg-card)",

        // ─── Brand ────────────────────────────────────────────
        "brand-primary": "var(--color-brand-primary)",
        "brand-accent": "var(--color-brand-accent)",

        // ─── Status System ────────────────────────────────────
        success: "var(--color-success)",
        warning: "var(--color-warning)",
        danger: "var(--color-danger)",
        info: "var(--color-info)",
        alert: "var(--color-alert)",

        // ─── AML Severity ─────────────────────────────────────
        severity: {
          critical: "var(--color-severity-critical)",
          high: "var(--color-severity-high)",
          medium: "var(--color-severity-medium)",
          low: "var(--color-severity-low)",
        },

        // ─── Text ─────────────────────────────────────────────
        "text-primary": "var(--color-text-primary)",
        "text-secondary": "var(--color-text-secondary)",
        "text-muted": "var(--color-text-muted)",
        "text-danger": "var(--color-text-danger)",
        "text-success": "var(--color-text-success)",
        "text-warning": "var(--color-text-warning)",

        // ─── Borders ──────────────────────────────────────────
        "border-default": "var(--color-border-default)",
        "border-subtle": "var(--color-border-subtle)",
        "border-focus": "var(--color-border-focus)",
      },

      fontFamily: {
        display: ["DM Serif Display", "Georgia", "serif"],
        body: ["Inter", "system-ui", "-apple-system", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "Cascadia Code", "monospace"],
      },

      fontSize: {
        xs: "var(--font-size-xs)",
        sm: "var(--font-size-sm)",
        base: "var(--font-size-base)",
        lg: "var(--font-size-lg)",
        xl: "var(--font-size-xl)",
        "2xl": "var(--font-size-2xl)",
        "3xl": "var(--font-size-3xl)",
        "4xl": "var(--font-size-4xl)",
      },

      spacing: {
        "1": "var(--spacing-1)",
        "2": "var(--spacing-2)",
        "3": "var(--spacing-3)",
        "4": "var(--spacing-4)",
        "5": "var(--spacing-5)",
        "6": "var(--spacing-6)",
        "8": "var(--spacing-8)",
        "10": "var(--spacing-10)",
        "12": "var(--spacing-12)",
        "16": "var(--spacing-16)",
        "sidebar-collapsed": "var(--sidebar-collapsed)",
        "sidebar-expanded": "var(--sidebar-expanded)",
      },

      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
        full: "var(--radius-full)",
      },

      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        "glow-blue": "var(--shadow-glow-blue)",
      },

      height: {
        "table-row": "var(--table-row-height)",
        "table-header": "var(--table-header-height)",
        "kpi-card": "var(--kpi-card-height)",
        sidebar: "var(--sidebar-expanded)",
      },

      width: {
        "sidebar-collapsed": "var(--sidebar-collapsed)",
        "sidebar-expanded": "var(--sidebar-expanded)",
      },

      transitionDuration: {
        fast: "150",
        normal: "200",
        slow: "300",
      },

      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fadeIn 200ms ease",
        "slide-in": "slideIn 200ms ease",
      },

      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideIn: {
          "0%": { transform: "translateX(-8px)", opacity: "0" },
          "100%": { transform: "translateX(0)", opacity: "1" },
        },
      },
    },
  },
  plugins: [
    // tabular-nums utility
    ({ addUtilities }: { addUtilities: (utils: Record<string, Record<string, string>>) => void }) => {
      addUtilities({
        ".tabular-nums": {
          "font-variant-numeric": "tabular-nums",
          "font-feature-settings": '"tnum" 1',
        },
        ".amount-negative": {
          color: "var(--color-text-danger)",
        },
        ".amount-pending": {
          color: "var(--color-text-warning)",
          "font-style": "italic",
        },
        ".font-display": {
          "font-family": "var(--font-display)",
        },
        ".font-mono": {
          "font-family": "var(--font-mono)",
        },
        ".text-uppercase-label": {
          "font-size": "var(--font-size-xs)",
          "text-transform": "uppercase",
          "letter-spacing": "0.05em",
          "font-weight": "var(--font-weight-semibold)",
          color: "var(--color-text-secondary)",
        },
      });
    },
  ],
};

export default config;
