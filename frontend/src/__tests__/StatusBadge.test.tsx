/**
 * StatusBadge Tests — all 5 status variants
 * IL-ADDS-01
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { type BadgeStatus, StatusBadge } from "../components/ui/StatusBadge";

const ALL_STATUSES: BadgeStatus[] = ["APPROVED", "PENDING", "REJECTED", "FLAGGED", "UNDER_REVIEW"];

describe("StatusBadge", () => {
  test.each(ALL_STATUSES)("renders %s status badge", (status) => {
    render(<StatusBadge status={status} />);
    const badge = screen.getByRole("status");
    expect(badge).toBeInTheDocument();
  });

  test('APPROVED badge shows "Approved" text', () => {
    render(<StatusBadge status="APPROVED" />);
    expect(screen.getByText("Approved")).toBeInTheDocument();
  });

  test('PENDING badge shows "Pending" text', () => {
    render(<StatusBadge status="PENDING" />);
    expect(screen.getByText("Pending")).toBeInTheDocument();
  });

  test('REJECTED badge shows "Rejected" text', () => {
    render(<StatusBadge status="REJECTED" />);
    expect(screen.getByText("Rejected")).toBeInTheDocument();
  });

  test('FLAGGED badge shows "Flagged" text', () => {
    render(<StatusBadge status="FLAGGED" />);
    expect(screen.getByText("Flagged")).toBeInTheDocument();
  });

  test('UNDER_REVIEW badge shows "Under Review" text', () => {
    render(<StatusBadge status="UNDER_REVIEW" />);
    expect(screen.getByText("Under Review")).toBeInTheDocument();
  });

  test("renders without icon when showIcon=false", () => {
    render(<StatusBadge status="APPROVED" showIcon={false} />);
    // No SVG icon should be rendered
    const badge = screen.getByRole("status");
    expect(badge.querySelector("svg")).toBeNull();
  });

  test("renders without label when showLabel=false", () => {
    render(<StatusBadge status="APPROVED" showLabel={false} />);
    expect(screen.queryByText("Approved")).toBeNull();
  });

  test("uses custom aria-label", () => {
    render(<StatusBadge status="APPROVED" aria-label="Account verified" />);
    expect(screen.getByRole("status", { name: "Account verified" })).toBeInTheDocument();
  });

  test("APPROVED badge has success green color class", () => {
    render(<StatusBadge status="APPROVED" />);
    const badge = screen.getByRole("status");
    expect(badge.className).toContain("10b981");
  });

  test("REJECTED badge has danger red color class", () => {
    render(<StatusBadge status="REJECTED" />);
    const badge = screen.getByRole("status");
    expect(badge.className).toContain("f43f5e");
  });

  test("PENDING badge has warning amber color class", () => {
    render(<StatusBadge status="PENDING" />);
    const badge = screen.getByRole("status");
    expect(badge.className).toContain("f59e0b");
  });

  test("applies custom className", () => {
    render(<StatusBadge status="APPROVED" className="test-custom" />);
    const badge = screen.getByRole("status");
    expect(badge.className).toContain("test-custom");
  });

  test('badge has role="status" for accessibility', () => {
    render(<StatusBadge status="PENDING" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});
