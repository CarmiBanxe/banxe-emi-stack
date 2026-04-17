/**
 * DataTable — Dense mode financial data table
 * 14px Inter, 44px row height, zebra rows, sortable columns
 * Batch actions floating bar, inline actions
 * IL-ADDS-01
 */

import { ArrowUpRight, CheckCircle, ChevronDown, ChevronsUpDown, ChevronUp, Download, ShieldAlert } from "lucide-react";
import { useCallback, useState } from "react";

export type SortDirection = "asc" | "desc" | null;

export interface Column<T> {
  key: keyof T;
  header: string;
  sortable?: boolean;
  width?: string;
  render?: (value: T[keyof T], row: T) => React.ReactNode;
  align?: "left" | "right" | "center";
}

export interface InlineAction<T> {
  label: string;
  icon?: React.ComponentType<{ size?: number; className?: string }>;
  onClick: (row: T) => void;
  variant?: "default" | "danger" | "warning";
}

export interface BatchAction {
  label: string;
  icon?: React.ComponentType<{ size?: number; className?: string }>;
  onClick: (selectedIds: string[]) => void;
  variant?: "default" | "danger";
}

export interface DataTableProps<T extends { id: string }> {
  data: T[];
  columns: Column<T>[];
  inlineActions?: InlineAction<T>[];
  batchActions?: BatchAction[];
  isLoading?: boolean;
  emptyMessage?: string;
  "aria-label"?: string;
}

function SortIcon({ direction }: { direction: SortDirection }) {
  if (direction === "asc") return <ChevronUp size={12} aria-hidden="true" />;
  if (direction === "desc") return <ChevronDown size={12} aria-hidden="true" />;
  return <ChevronsUpDown size={12} className="opacity-40" aria-hidden="true" />;
}

const variantActionClass: Record<string, string> = {
  default: "text-[oklch(65%_0_0)] hover:text-[oklch(95%_0_0)]",
  danger: "text-[#f87171] hover:text-[#f43f5e]",
  warning: "text-[#fbbf24] hover:text-[#f59e0b]",
};

const variantBatchClass: Record<string, string> = {
  default: "bg-[#3b82f6] text-white hover:bg-[#2563eb]",
  danger: "bg-[#f43f5e]/20 text-[#f87171] border border-[#f43f5e]/30 hover:bg-[#f43f5e]/30",
};

export function DataTable<T extends { id: string }>({
  data,
  columns,
  inlineActions,
  batchActions,
  isLoading = false,
  emptyMessage = "No records found.",
  "aria-label": ariaLabel,
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = useState<keyof T | null>(null);
  const [sortDir, setSortDir] = useState<SortDirection>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const handleSort = useCallback(
    (key: keyof T) => {
      if (sortKey === key) {
        setSortDir((prev) => (prev === "asc" ? "desc" : prev === "desc" ? null : "asc"));
        if (sortDir === "desc") setSortKey(null);
      } else {
        setSortKey(key);
        setSortDir("asc");
      }
    },
    [sortKey, sortDir],
  );

  const sortedData = [...data].sort((a, b) => {
    if (!sortKey || !sortDir) return 0;
    const av = a[sortKey];
    const bv = b[sortKey];
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return sortDir === "asc" ? cmp : -cmp;
  });

  const allSelected = data.length > 0 && selected.size === data.length;
  const someSelected = selected.size > 0 && !allSelected;

  const toggleAll = () => {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(data.map((r) => r.id)));
    }
  };

  const toggleRow = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  if (isLoading) {
    return (
      <div
        className="rounded-xl border border-[oklch(20%_0.01_240)] overflow-hidden"
        aria-busy="true"
        aria-label={ariaLabel}
      >
        {[...Array(5)].map((_, i) => (
          <div
            // biome-ignore lint/suspicious/noArrayIndexKey: static skeleton — no stable id
            key={i}
            className="flex gap-4 px-4 animate-pulse border-b border-[oklch(17%_0.01_240)]"
            style={{ height: "44px", alignItems: "center" }}
          >
            <div className="w-4 h-4 rounded bg-[oklch(20%_0.01_240)]" />
            {columns.map((col) => (
              <div
                key={String(col.key)}
                className="h-3 rounded bg-[oklch(20%_0.01_240)]"
                style={{ width: col.width ?? "120px" }}
              />
            ))}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="relative">
      <div
        className="rounded-xl border border-[oklch(20%_0.01_240)] overflow-auto"
        role="region"
        aria-label={ariaLabel}
      >
        <table className="w-full text-sm" style={{ fontVariantNumeric: "tabular-nums" }}>
          <thead>
            <tr
              className="border-b border-[oklch(20%_0.01_240)]"
              style={{ height: "40px", background: "oklch(13% 0.01 240)" }}
            >
              {batchActions && (
                <th className="w-10 px-4 text-left">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    ref={(el) => {
                      if (el) el.indeterminate = someSelected;
                    }}
                    onChange={toggleAll}
                    aria-label="Select all rows"
                    className="accent-[#3b82f6] cursor-pointer"
                  />
                </th>
              )}
              {columns.map((col) => (
                <th
                  key={String(col.key)}
                  className={`
                    px-4 text-xs uppercase tracking-widest font-semibold
                    text-[oklch(65%_0_0)] whitespace-nowrap select-none
                    ${col.align === "right" ? "text-right" : col.align === "center" ? "text-center" : "text-left"}
                    ${col.sortable ? "cursor-pointer hover:text-[oklch(95%_0_0)]" : ""}
                  `}
                  style={{ width: col.width }}
                  onClick={col.sortable ? () => handleSort(col.key) : undefined}
                  aria-sort={
                    col.sortable && sortKey === col.key ? (sortDir === "asc" ? "ascending" : "descending") : undefined
                  }
                  scope="col"
                >
                  <span className="inline-flex items-center gap-1">
                    {col.header}
                    {col.sortable && <SortIcon direction={sortKey === col.key ? sortDir : null} />}
                  </span>
                </th>
              ))}
              {inlineActions && (
                <th
                  className="px-4 text-xs uppercase tracking-widest font-semibold text-[oklch(65%_0_0)] text-right"
                  scope="col"
                >
                  Actions
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {sortedData.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length + (batchActions ? 1 : 0) + (inlineActions ? 1 : 0)}
                  className="px-4 py-8 text-center text-[oklch(45%_0_0)]"
                >
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              sortedData.map((row, idx) => (
                <tr
                  key={row.id}
                  style={{ height: "44px" }}
                  className={`
                    border-b border-[oklch(17%_0.01_240)] last:border-0
                    transition-colors duration-150
                    ${idx % 2 === 0 ? "bg-[oklch(13%_0.01_240)]" : "bg-[oklch(15%_0.01_240)]"}
                    ${selected.has(row.id) ? "bg-[#3b82f6]/10" : "hover:bg-[oklch(17%_0.01_240)]"}
                  `}
                  aria-selected={selected.has(row.id)}
                >
                  {batchActions && (
                    <td className="w-10 px-4">
                      <input
                        type="checkbox"
                        checked={selected.has(row.id)}
                        onChange={() => toggleRow(row.id)}
                        aria-label={`Select row ${row.id}`}
                        className="accent-[#3b82f6] cursor-pointer"
                      />
                    </td>
                  )}
                  {columns.map((col) => (
                    <td
                      key={String(col.key)}
                      className={`
                        px-4 text-sm text-[oklch(95%_0_0)] whitespace-nowrap
                        ${col.align === "right" ? "text-right" : col.align === "center" ? "text-center" : "text-left"}
                      `}
                    >
                      {col.render ? col.render(row[col.key], row) : String(row[col.key] ?? "")}
                    </td>
                  ))}
                  {inlineActions && (
                    <td className="px-4 text-right">
                      <span className="inline-flex items-center gap-2">
                        {inlineActions.map((action) => {
                          const Icon = action.icon;
                          return (
                            <button
                              key={action.label}
                              onClick={() => action.onClick(row)}
                              className={`
                                text-xs font-medium px-2 py-1 rounded transition-colors
                                ${variantActionClass[action.variant ?? "default"]}
                              `}
                              aria-label={`${action.label} for row ${row.id}`}
                            >
                              {Icon ? <Icon size={14} /> : action.label}
                            </button>
                          );
                        })}
                      </span>
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Batch actions floating bar */}
      {batchActions && selected.size > 0 && (
        <div
          className="
            fixed bottom-6 left-1/2 -translate-x-1/2 z-50
            flex items-center gap-3 px-4 py-3 rounded-xl
            bg-[oklch(17%_0.01_240)] border border-[oklch(25%_0.01_240)]
            shadow-lg animate-fade-in
          "
          role="toolbar"
          aria-label={`Batch actions for ${selected.size} selected row${selected.size > 1 ? "s" : ""}`}
        >
          <span className="text-sm text-[oklch(65%_0_0)]">{selected.size} selected</span>
          <div className="w-px h-4 bg-[oklch(25%_0.01_240)]" aria-hidden="true" />
          {batchActions.map((action) => {
            const Icon = action.icon;
            return (
              <button
                key={action.label}
                onClick={() => action.onClick(Array.from(selected))}
                className={`
                  inline-flex items-center gap-1.5 text-xs font-semibold
                  px-3 py-1.5 rounded-lg transition-colors
                  ${variantBatchClass[action.variant ?? "default"]}
                `}
              >
                {Icon && <Icon size={13} />}
                {action.label}
              </button>
            );
          })}
          <button
            onClick={() => setSelected(new Set())}
            className="text-xs text-[oklch(45%_0_0)] hover:text-[oklch(65%_0_0)] ml-1"
            aria-label="Clear selection"
          >
            Clear
          </button>
        </div>
      )}
    </div>
  );
}

export default DataTable;

// ─── Default inline actions ─────────────────────────────────────────────────
export const defaultInlineActions = <T extends { id: string }>(): InlineAction<T>[] => [
  {
    label: "Hold",
    icon: ShieldAlert,
    onClick: () => undefined,
    variant: "warning",
  },
  {
    label: "Verify",
    icon: CheckCircle,
    onClick: () => undefined,
    variant: "default",
  },
  {
    label: "Escalate",
    icon: ArrowUpRight,
    onClick: () => undefined,
    variant: "danger",
  },
  {
    label: "Export",
    icon: Download,
    onClick: () => undefined,
    variant: "default",
  },
];
