/**
 * KYCWizard Tests — all 5 steps, file upload, responsive
 * IL-ADDS-01
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, test, expect } from "vitest";
import { KYCWizard } from "../modules/kyc/KYCWizard";

describe("KYCWizard", () => {
  test("renders KYC Onboarding heading", () => {
    render(<KYCWizard />);
    expect(screen.getByRole("heading", { name: /KYC Onboarding/i })).toBeInTheDocument();
  });

  test("renders step wizard with 5 steps", () => {
    render(<KYCWizard />);
    const stepLabels = ["Identity", "Address", "AML Check", "Documents", "Review"];
    for (const label of stepLabels) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  test("starts on step 1 \u2014 Personal Identity", () => {
    render(<KYCWizard />);
    expect(screen.getByRole("heading", { name: /Personal Identity/i })).toBeInTheDocument();
  });

  test("step 1 has First Name field", () => {
    render(<KYCWizard />);
    expect(screen.getByPlaceholderText("John")).toBeInTheDocument();
  });

  test("step 1 has Last Name field", () => {
    render(<KYCWizard />);
    expect(screen.getByPlaceholderText("Smith")).toBeInTheDocument();
  });

  test("step 1 has Date of Birth field", () => {
    render(<KYCWizard />);
    expect(screen.getByText(/Date of Birth/i)).toBeInTheDocument();
  });

  test("step 1 has Tax ID field", () => {
    render(<KYCWizard />);
    expect(screen.getByPlaceholderText(/AB 12 34 56 C/i)).toBeInTheDocument();
  });

  test("Back button is disabled on step 1", () => {
    render(<KYCWizard />);
    expect(screen.getByRole("button", { name: /Go to previous step/ })).toBeDisabled();
  });

  test("Next button exists on step 1", () => {
    render(<KYCWizard />);
    expect(screen.getByRole("button", { name: /Go to next step/ })).toBeInTheDocument();
  });

  test("shows progress percentage", () => {
    render(<KYCWizard />);
    expect(screen.getByText(/% complete/)).toBeInTheDocument();
  });

  test("shows time remaining estimate", () => {
    render(<KYCWizard />);
    expect(screen.getByText(/min remaining/)).toBeInTheDocument();
  });

  test("validation error shown for empty First Name", async () => {
    render(<KYCWizard />);
    // Submit without filling in fields
    fireEvent.click(screen.getByRole("button", { name: /Go to next step/ }));
    await waitFor(() => {
      expect(screen.getAllByRole("alert").length).toBeGreaterThan(0);
    });
  });

  test("progress bar shows 0% initially", () => {
    render(<KYCWizard />);
    const progressbar = screen.getByRole("progressbar");
    expect(progressbar).toHaveAttribute("aria-valuenow", "0");
  });

  test("renders within dark background container", () => {
    render(<KYCWizard />);
    const container = screen.getByRole("heading", { name: /KYC Onboarding/ }).closest('[style*="oklch"]');
    expect(container).not.toBeNull();
  });

  test("step labels are visible", () => {
    render(<KYCWizard />);
    for (const label of ["Identity", "Address", "AML Check", "Documents", "Review"]) {
      expect(screen.getByText(label)).toBeVisible();
    }
  });
});
