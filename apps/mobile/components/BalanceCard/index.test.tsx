/**
 * BalanceCard — Mobile unit tests
 * IL-UI-02 | Jest + @testing-library/react-native
 */
import { cleanup, render, screen } from "@testing-library/react-native";
import { afterEach, describe, expect, it } from "@jest/globals";
import { BalanceCard, type BalanceCardProps } from "./index";

afterEach(cleanup);

const BASE_PROPS: BalanceCardProps = {
  balance: "1234.56",
  currency: "GBP",
  accountType: "Current",
  timestamp: new Date("2026-04-27T10:30:00Z"),
};

describe("BalanceCard — rendering", () => {
  it("renders positive balance with success token colour", () => {
    render(<BalanceCard {...BASE_PROPS} />);
    const amount = screen.getByLabelText(/Balance: £1,234\.56/i);
    expect(amount.props.style).toEqual(
      expect.objectContaining({ color: "#34d399" }),
    );
  });

  it("renders negative balance with danger token colour", () => {
    render(<BalanceCard {...BASE_PROPS} balance="-500.00" />);
    const amount = screen.getByLabelText(/Balance: -£500\.00/i);
    expect(amount.props.style).toEqual(
      expect.objectContaining({ color: "#f87171" }),
    );
  });

  it("renders zero balance with warning token colour", () => {
    render(<BalanceCard {...BASE_PROPS} balance="0.00" />);
    const amount = screen.getByLabelText(/Balance: £0\.00/i);
    expect(amount.props.style).toEqual(
      expect.objectContaining({ color: "#fbbf24" }),
    );
  });

  it("renders disclosure header with correct UTC timestamp", () => {
    render(<BalanceCard {...BASE_PROPS} />);
    expect(screen.getByText(/Balance as of 2026-04-27 10:30:00 UTC/i)).toBeDefined();
  });

  it("renders account ID when provided", () => {
    render(<BalanceCard {...BASE_PROPS} accountId="ACC-7821" />);
    expect(screen.getByLabelText(/Account ID: ACC-7821/i)).toBeDefined();
  });
});

describe("BalanceCard — account types", () => {
  it("renders Savings badge text for Savings account", () => {
    render(<BalanceCard {...BASE_PROPS} accountType="Savings" />);
    expect(screen.getAllByText("Savings").length).toBeGreaterThanOrEqual(1);
  });

  it("renders Safeguarding badge for Safeguarding account", () => {
    render(<BalanceCard {...BASE_PROPS} accountType="Safeguarding" />);
    expect(screen.getAllByText("Safeguarding").length).toBeGreaterThanOrEqual(1);
  });
});

describe("BalanceCard — financial invariants", () => {
  it("applies tabular-nums fontVariant to amount (I-01)", () => {
    render(<BalanceCard {...BASE_PROPS} />);
    const amount = screen.getByLabelText(/Balance: £1,234\.56/i);
    expect(amount.props.style).toEqual(
      expect.objectContaining({ fontVariant: ["tabular-nums"] }),
    );
  });

  it("renders large amounts correctly without float precision loss", () => {
    render(<BalanceCard {...BASE_PROPS} balance="9999999.99" />);
    expect(screen.getByLabelText(/Balance: £9,999,999\.99/i)).toBeDefined();
  });
});

describe("BalanceCard — loading state", () => {
  it("renders skeleton with busy accessibility state when isLoading", () => {
    render(<BalanceCard {...BASE_PROPS} isLoading />);
    const skeleton = screen.getByLabelText(/Loading balance/i);
    expect(skeleton.props.accessibilityState).toEqual(
      expect.objectContaining({ busy: true }),
    );
  });

  it("does not render balance amount when isLoading", () => {
    render(<BalanceCard {...BASE_PROPS} isLoading />);
    expect(screen.queryByLabelText(/Balance: £1,234\.56/i)).toBeNull();
  });
});

describe("BalanceCard — accessibility", () => {
  it("has accessibilityLabel with account type and formatted amount", () => {
    render(<BalanceCard {...BASE_PROPS} />);
    expect(screen.getByLabelText(/Current account balance: £1,234\.56/i)).toBeDefined();
  });

  it("disclosure footer has accessibilityLabel with timestamp", () => {
    render(<BalanceCard {...BASE_PROPS} />);
    expect(
      screen.getByLabelText(/Data disclosure: Balance as of 2026-04-27 10:30:00 UTC/i),
    ).toBeDefined();
  });
});
