/**
 * DataTable Tests — sorting, zebra rows, batch actions
 * IL-ADDS-01
 */
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, test, expect, vi } from "vitest";
import { DataTable, type Column } from "../components/ui/DataTable";

interface TestRow {
  id: string;
  name: string;
  amount: string;
  status: string;
}

const TEST_DATA: TestRow[] = [
  { id: "R1", name: "Alice", amount: "100.00", status: "active" },
  { id: "R2", name: "Bob", amount: "200.00", status: "pending" },
  { id: "R3", name: "Carol", amount: "150.00", status: "active" },
];

const TEST_COLUMNS: Column<TestRow>[] = [
  { key: "name", header: "Name", sortable: true },
  { key: "amount", header: "Amount", sortable: true, align: "right" },
  { key: "status", header: "Status" },
];

describe("DataTable", () => {
  test("renders all rows", () => {
    render(<DataTable data={TEST_DATA} columns={TEST_COLUMNS} />);
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Bob")).toBeInTheDocument();
    expect(screen.getByText("Carol")).toBeInTheDocument();
  });

  test("renders all column headers", () => {
    render(<DataTable data={TEST_DATA} columns={TEST_COLUMNS} />);
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Amount")).toBeInTheDocument();
    expect(screen.getByText("Status")).toBeInTheDocument();
  });

  test("shows empty message when data is empty", () => {
    render(<DataTable data={[]} columns={TEST_COLUMNS} emptyMessage="No records found." />);
    expect(screen.getByText("No records found.")).toBeInTheDocument();
  });

  test("shows loading skeleton when isLoading=true", () => {
    const { container } = render(<DataTable data={[]} columns={TEST_COLUMNS} isLoading />);
    const loadingEl = container.querySelector('[aria-busy="true"]');
    expect(loadingEl).not.toBeNull();
  });

  test("sortable column has cursor-pointer class", () => {
    render(<DataTable data={TEST_DATA} columns={TEST_COLUMNS} />);
    const nameHeader = screen.getByRole("columnheader", { name: /Name/ });
    expect(nameHeader.className).toContain("cursor-pointer");
  });

  test("non-sortable column does not have cursor-pointer", () => {
    render(<DataTable data={TEST_DATA} columns={TEST_COLUMNS} />);
    const statusHeader = screen.getByRole("columnheader", { name: /Status/ });
    expect(statusHeader.className).not.toContain("cursor-pointer");
  });

  test("batch actions: select all checkbox appears", () => {
    const batchActions = [{ label: "Delete", onClick: vi.fn() }];
    render(<DataTable data={TEST_DATA} columns={TEST_COLUMNS} batchActions={batchActions} />);
    expect(screen.getByLabelText("Select all rows")).toBeInTheDocument();
  });

  test("batch actions: selecting all rows shows batch bar", () => {
    const handleDelete = vi.fn();
    const batchActions = [{ label: "Delete", onClick: handleDelete }];
    render(<DataTable data={TEST_DATA} columns={TEST_COLUMNS} batchActions={batchActions} />);
    const selectAll = screen.getByLabelText("Select all rows");
    fireEvent.click(selectAll);
    expect(screen.getByRole("toolbar")).toBeInTheDocument();
    expect(screen.getByText(/3 selected/)).toBeInTheDocument();
  });

  test("batch action button calls handler with selected IDs", () => {
    const handleEscalate = vi.fn();
    const batchActions = [{ label: "Escalate", onClick: handleEscalate }];
    render(<DataTable data={TEST_DATA.slice(0, 1)} columns={TEST_COLUMNS} batchActions={batchActions} />);
    fireEvent.click(screen.getByLabelText("Select row R1"));
    fireEvent.click(screen.getByText("Escalate"));
    expect(handleEscalate).toHaveBeenCalledWith(["R1"]);
  });

  test("rows have alternating zebra classes", () => {
    render(<DataTable data={TEST_DATA} columns={TEST_COLUMNS} />);
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0].className).not.toBe(rows[1].className);
  });

  test("inline actions: action button calls handler", () => {
    const handleHold = vi.fn();
    render(
      <DataTable
        data={TEST_DATA.slice(0, 1)}
        columns={TEST_COLUMNS}
        inlineActions={[{ label: "Hold", onClick: handleHold }]}
      />,
    );
    const holdBtn = screen.getByLabelText("Hold for row R1");
    fireEvent.click(holdBtn);
    expect(handleHold).toHaveBeenCalledWith(TEST_DATA[0]);
  });

  test("custom render function is called", () => {
    const columns: Column<TestRow>[] = [
      {
        key: "status",
        header: "Status",
        render: (v) => <span data-testid="custom-cell">{String(v).toUpperCase()}</span>,
      },
    ];
    render(<DataTable data={TEST_DATA.slice(0, 1)} columns={columns} />);
    expect(screen.getByTestId("custom-cell")).toHaveTextContent("ACTIVE");
  });

  test("has aria-label on container", () => {
    render(<DataTable data={TEST_DATA} columns={TEST_COLUMNS} aria-label="Transactions table" />);
    expect(screen.getByRole("region", { name: "Transactions table" })).toBeInTheDocument();
  });
});
