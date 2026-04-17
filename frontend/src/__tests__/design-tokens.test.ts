/**
 * Design Tokens — verify all DESIGN.md tokens exist in tokens.css
 * IL-ADDS-01
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

const DESIGN_MD = join(__dirname, "../design-system/DESIGN.md");
const TOKENS_CSS = join(__dirname, "../design-system/tokens.css");

function readFile(path: string): string {
  return readFileSync(path, "utf-8");
}

function extractCSSVars(content: string): Set<string> {
  const matches = content.match(/--[\w-]+(?=\s*:)/g) ?? [];
  return new Set(matches);
}

const designContent = readFile(DESIGN_MD);
const tokensContent = readFile(TOKENS_CSS);
const cssVars = extractCSSVars(tokensContent);

const REQUIRED_TOKENS = [
  // Backgrounds
  "--color-bg-primary",
  "--color-bg-secondary",
  "--color-bg-tertiary",
  "--color-bg-card",
  // Brand
  "--color-brand-primary",
  "--color-brand-accent",
  // Status
  "--color-success",
  "--color-warning",
  "--color-danger",
  "--color-info",
  "--color-alert",
  // AML severity
  "--color-severity-critical",
  "--color-severity-high",
  "--color-severity-medium",
  "--color-severity-low",
  // Text
  "--color-text-primary",
  "--color-text-secondary",
  "--color-text-muted",
  "--color-text-danger",
  "--color-text-success",
  "--color-text-warning",
  // Borders
  "--color-border-default",
  "--color-border-subtle",
  "--color-border-focus",
  // Typography
  "--font-display",
  "--font-body",
  "--font-mono",
  "--font-size-xs",
  "--font-size-sm",
  "--font-size-base",
  "--font-size-lg",
  "--font-size-xl",
  "--font-size-2xl",
  "--font-size-3xl",
  "--font-size-4xl",
  "--font-weight-normal",
  "--font-weight-medium",
  "--font-weight-semibold",
  "--font-weight-bold",
  // Spacing
  "--spacing-1",
  "--spacing-2",
  "--spacing-3",
  "--spacing-4",
  "--spacing-6",
  "--spacing-8",
  // Border radius
  "--radius-sm",
  "--radius-md",
  "--radius-lg",
  "--radius-xl",
  "--radius-full",
  // Shadows
  "--shadow-sm",
  "--shadow-md",
  "--shadow-lg",
  // Dimensions
  "--sidebar-collapsed",
  "--sidebar-expanded",
  "--table-row-height",
  "--table-header-height",
  "--card-padding",
  "--kpi-card-height",
];

describe("Design Token Coverage", () => {
  test("tokens.css file exists and is non-empty", () => {
    expect(tokensContent.length).toBeGreaterThan(100);
  });

  test("DESIGN.md file exists and is non-empty", () => {
    expect(designContent.length).toBeGreaterThan(100);
  });

  test("tokens.css contains :root block", () => {
    expect(tokensContent).toContain(":root");
  });

  test("tokens.css uses @layer base", () => {
    expect(tokensContent).toContain("@layer base");
  });

  test.each(REQUIRED_TOKENS)("token %s is defined in tokens.css", (token) => {
    expect(cssVars.has(token)).toBe(true);
  });

  test("DESIGN.md mentions tabular-nums requirement", () => {
    expect(designContent).toMatch(/tabular-nums/i);
  });

  test("DESIGN.md specifies WCAG AA compliance", () => {
    expect(designContent).toMatch(/WCAG/i);
  });

  test("DESIGN.md defines 5 financial UI rules", () => {
    expect(designContent).toMatch(/Financial UI Rules/);
    // Check for the 5 numbered rules
    for (let i = 1; i <= 5; i++) {
      expect(designContent).toContain(`${i}.`);
    }
  });

  test("DESIGN.md defines all 5 status badges", () => {
    const statuses = ["APPROVED", "PENDING", "REJECTED", "FLAGGED", "UNDER_REVIEW"];
    for (const status of statuses) {
      expect(designContent).toContain(status);
    }
  });

  test("DESIGN.md defines all 4 AML severity levels", () => {
    const severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
    for (const sev of severities) {
      expect(designContent).toContain(sev);
    }
  });

  test("tokens.css includes tabular-nums utility", () => {
    expect(tokensContent).toContain("tabular-nums");
  });

  test("tokens.css sets dark color-scheme", () => {
    expect(tokensContent).toContain("color-scheme: dark");
  });

  test("tokens.css defines severity left-border helpers", () => {
    expect(tokensContent).toContain('[data-severity="critical"]');
    expect(tokensContent).toContain('[data-severity="high"]');
    expect(tokensContent).toContain('[data-severity="medium"]');
    expect(tokensContent).toContain('[data-severity="low"]');
  });
});
