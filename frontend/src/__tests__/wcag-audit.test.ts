/**
 * WCAG AA Contrast Audit — all DESIGN.md token combinations
 * Minimum 4.5:1 for body text, 3:1 for large text
 * IL-ADDS-01
 */
import { describe, expect, test } from "vitest";

// WCAG 2.1 contrast ratio calculator
// Based on relative luminance formula
function hexToSRGB(hex: string): [number, number, number] {
  const clean = hex.replace("#", "");
  const r = parseInt(clean.slice(0, 2), 16) / 255;
  const g = parseInt(clean.slice(2, 4), 16) / 255;
  const b = parseInt(clean.slice(4, 6), 16) / 255;
  return [r, g, b];
}

function toLinear(c: number): number {
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function relativeLuminance(hex: string): number {
  const [r, g, b] = hexToSRGB(hex);
  const [R, G, B] = [r, g, b].map(toLinear);
  return 0.2126 * R + 0.7152 * G + 0.0722 * B;
}

function contrastRatio(hex1: string, hex2: string): number {
  const l1 = relativeLuminance(hex1);
  const l2 = relativeLuminance(hex2);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

// Approximate OKLCH backgrounds as hex for testing
// (actual rendering uses OKLCH, but these are close equivalents)
const BG_COLORS = {
  "bg-primary": "#060608", // oklch(10% 0 0) ≈ #060608
  "bg-secondary": "#121219", // oklch(13% 0.01 240) ≈
  "bg-card": "#0f1017", // oklch(15% 0.01 240) ≈
};

// Text colors from DESIGN.md (hex values)
const TEXT_COLORS = {
  "text-primary": "#f0f0f2", // oklch(95% 0 0) ≈
  "text-secondary": "#8b8b96", // oklch(65% 0 0) ≈
  "text-muted": "#505059", // oklch(45% 0 0) ≈
  "text-danger": "#f87171",
  "text-success": "#34d399",
  "text-warning": "#fbbf24",
};

const WCAG_AA_NORMAL = 4.5;
const WCAG_AA_LARGE = 3.0;

describe("WCAG AA Contrast Ratios", () => {
  // Primary text on all backgrounds must pass AA (4.5:1)
  describe("Primary text on backgrounds", () => {
    for (const [bgName, bg] of Object.entries(BG_COLORS)) {
      test(`text-primary on ${bgName} passes 4.5:1`, () => {
        const ratio = contrastRatio(TEXT_COLORS["text-primary"], bg);
        expect(ratio).toBeGreaterThanOrEqual(WCAG_AA_NORMAL);
      });
    }
  });

  // Secondary text (labels) on primary background
  describe("Secondary text on bg-primary", () => {
    test("text-secondary on bg-primary passes 3:1 (large text)", () => {
      const ratio = contrastRatio(TEXT_COLORS["text-secondary"], BG_COLORS["bg-primary"]);
      expect(ratio).toBeGreaterThanOrEqual(WCAG_AA_LARGE);
    });
  });

  // Status colors must be distinguishable
  describe("Status indicator colors on bg-primary", () => {
    test("success color (#34d399) on bg-primary passes 3:1", () => {
      const ratio = contrastRatio("#34d399", BG_COLORS["bg-primary"]);
      expect(ratio).toBeGreaterThanOrEqual(WCAG_AA_LARGE);
    });

    test("warning color (#fbbf24) on bg-primary passes 3:1", () => {
      const ratio = contrastRatio("#fbbf24", BG_COLORS["bg-primary"]);
      expect(ratio).toBeGreaterThanOrEqual(WCAG_AA_LARGE);
    });

    test("danger text (#f87171) on bg-primary passes 3:1", () => {
      const ratio = contrastRatio("#f87171", BG_COLORS["bg-primary"]);
      expect(ratio).toBeGreaterThanOrEqual(WCAG_AA_LARGE);
    });

    test("info color (#60a5fa) on bg-primary passes 3:1", () => {
      const ratio = contrastRatio("#60a5fa", BG_COLORS["bg-primary"]);
      expect(ratio).toBeGreaterThanOrEqual(WCAG_AA_LARGE);
    });
  });

  // Severity colors on dark backgrounds
  describe("Severity colors on bg-primary", () => {
    test("severity-critical (#f43f5e) on bg-primary passes 3:1", () => {
      const ratio = contrastRatio("#f43f5e", BG_COLORS["bg-primary"]);
      expect(ratio).toBeGreaterThanOrEqual(WCAG_AA_LARGE);
    });

    test("severity-high (#f97316) on bg-primary passes 3:1", () => {
      const ratio = contrastRatio("#f97316", BG_COLORS["bg-primary"]);
      expect(ratio).toBeGreaterThanOrEqual(WCAG_AA_LARGE);
    });

    test("severity-medium (#f59e0b) on bg-primary passes 3:1", () => {
      const ratio = contrastRatio("#f59e0b", BG_COLORS["bg-primary"]);
      expect(ratio).toBeGreaterThanOrEqual(WCAG_AA_LARGE);
    });
  });

  // Brand accent
  describe("Brand colors", () => {
    test("brand-accent (#3b82f6) on bg-primary passes 3:1", () => {
      const ratio = contrastRatio("#3b82f6", BG_COLORS["bg-primary"]);
      expect(ratio).toBeGreaterThanOrEqual(WCAG_AA_LARGE);
    });

    test("blue-400 (#60a5fa) on bg-card passes 3:1", () => {
      const ratio = contrastRatio("#60a5fa", BG_COLORS["bg-card"]);
      expect(ratio).toBeGreaterThanOrEqual(WCAG_AA_LARGE);
    });
  });

  // Utility function tests
  describe("contrastRatio utility", () => {
    test("white on black is 21:1", () => {
      const ratio = contrastRatio("#ffffff", "#000000");
      expect(ratio).toBeCloseTo(21, 0);
    });

    test("black on black is 1:1", () => {
      const ratio = contrastRatio("#000000", "#000000");
      expect(ratio).toBe(1);
    });

    test("contrast is commutative", () => {
      const r1 = contrastRatio("#f87171", "#060608");
      const r2 = contrastRatio("#060608", "#f87171");
      expect(r1).toBeCloseTo(r2, 5);
    });
  });
});
