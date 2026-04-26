/**
 * BalanceCard — Web unit tests
 * IL-UI-02 | Vitest + @testing-library/react
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { BalanceCard, type BalanceCardProps } from "./index";

afterEach(cleanup);

const BASE_PROPS: BalanceCardProps = {
  balance: "1234.56",
  currency: "GBP",
  accountType: "Current",
  timestamp: new Date("2026-04-27T10:30:00Z"),
};

describe("BalanceCard — rendering", () => {
  it("renders positive balance with success colour token", () => {
    render(<BalanceCard {...BASE_PROPS} />);
    const amount = screen.getByRole("paragraph", {
      name: /Balance: £1,234\.56/i,
    });
    expect(amount).toBeDefined();
    // colour resolved to --color-text-success
    expect(amount.getAttribute("style")).toContain("var(--color-text-success)");
  });

  it("renders negative balance with danger colour token", () => {
    render(<BalanceCard {...BASE_PROPS} balance="-500.00" />);
    const amount = screen.getByLabelText(/Balance: -£500\.00/i);
    expect(amount.getAttribute("style")).toContain("var(--color-text-danger)");
  });

  it("renders zero balance with warning colour token", () => {
    render(<BalanceCard {...BASE_PROPS} balance="0.00" />);
    const amount = screen.getByLabelText(/Balance: £0\.00/i);
    expect(amount.getAttribute("style")).toContain("var(--color-text-warning)");
  });

  it("renders disclosure header with correct UTC timestamp", () => {
    render(<BalanceCard {...BASE_PROPS} />);
    expect(screen.getByText(/Balance as of 2026-04-27 10:30:00 UTC/i)).toBeDefined();
  });

  it("renders account ID in monospace when provided", () => {
    render(<BalanceCard {...BASE_PROPS} accountId="ACC-7821" />);
    const idEl = screen.getByLabelText(/Account ID: ACC-7821/i);
    expect(idEl.getAttribute("style")).toContain("var(--font-mono)");
  });
});

describe("BalanceCard — account types", () => {
  it("renders Savings badge for Savings account", () => {
    render(<BalanceCard {...BASE_PROPS} accountType="Savings" />);
    expect(screen.getAllByText("Savings").length).toBeGreaterThanOrEqual(1);
  });

  it("renders Safeguarding badge for Safeguarding account", () => {
    render(<BalanceCard {...BASE_PROPS} accountType="Safeguarding" />);
    expect(screen.getAllByText("Safeguarding").length).toBeGreaterThanOrEqual(1);
  });
});

describe("BalanceCard — financial invariants", () => {
  it("applies tabular-nums to amount element (I-01)", () => {
    render(<BalanceCard {...BASE_PROPS} />);
    const amount = screen.getByLabelText(/Balance: £1,234\.56/i);
    expect(amount.getAttribute("style")).toContain("tabular-nums");
  });

  it("amount prop is string — never float (I-01)", () => {
    // TypeScript enforces string; this test guards runtime contract
    render(<BalanceCard {...BASE_PROPS} balance="9999999.99" />);
    expect(screen.getByLabelText(/Balance: £9,999,999\.99/i)).toBeDefined();
  });
});

describe("BalanceCard — loading state", () => {
  it("renders skeleton with aria-busy when isLoading", () => {
    render(<BalanceCard {...BASE_PROPS} isLoading />);
    expect(screen.getByRole("article", { name: /Loading balance/i }).getAttribute("aria-busy")).toBe("true");
  });

  it("does not render amount when isLoading", () => {
    render(<BalanceCard {...BASE_PROPS} isLoading />);
    expect(screen.queryByText("£1,234.56")).toBeNull();
  });
});

describe("BalanceCard — accessibility", () => {
  it("has accessible article role with full label", () => {
    render(<BalanceCard {...BASE_PROPS} />);
    expect(
      screen.getByRole("article", { name: /Current account balance: £1,234\.56/i }),
    ).toBeDefined();
  });

  it("disclosure footer has aria-label with timestamp", () => {
    render(<BalanceCard {...BASE_PROPS} />);
    expect(screen.getByLabelText(/Data disclosure: Balance as of 2026-04-27 10:30:00 UTC/i)).toBeDefined();
  });
});
