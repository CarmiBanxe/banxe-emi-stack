/**
 * Sidebar — Left navigation, 64px collapsed / 240px expanded
 * 7 sections with Lucide icons, active state indicator
 * IL-ADDS-01
 */

import {
  AlertOctagon,
  ArrowLeftRight,
  ChevronLeft,
  ChevronRight,
  CreditCard,
  LayoutDashboard,
  Settings,
  ShieldCheck,
  UserCheck,
} from "lucide-react";
import { useState } from "react";

export interface NavItem {
  id: string;
  label: string;
  href: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  badge?: number;
}

const navItems: NavItem[] = [
  { id: "overview", label: "Overview", href: "/dashboard", icon: LayoutDashboard },
  { id: "accounts", label: "Accounts", href: "/accounts", icon: CreditCard },
  { id: "transactions", label: "Transactions", href: "/transactions", icon: ArrowLeftRight },
  { id: "aml", label: "AML", href: "/aml", icon: AlertOctagon },
  { id: "kyc", label: "KYC", href: "/kyc", icon: UserCheck },
  { id: "compliance", label: "Compliance", href: "/compliance", icon: ShieldCheck },
  { id: "settings", label: "Settings", href: "/settings", icon: Settings },
];

export interface SidebarProps {
  activeId?: string;
  onNavigate?: (item: NavItem) => void;
  defaultExpanded?: boolean;
}

export function Sidebar({ activeId = "overview", onNavigate, defaultExpanded = true }: SidebarProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  const handleNav = (item: NavItem, e: React.MouseEvent) => {
    e.preventDefault();
    onNavigate?.(item);
  };

  return (
    <nav
      className="
        flex flex-col h-full
        border-r border-[oklch(20%_0.01_240)]
        bg-[oklch(13%_0.01_240)]
        transition-[width] duration-200 ease-in-out
        relative shrink-0
      "
      style={{ width: expanded ? "240px" : "64px" }}
      aria-label="Main navigation"
    >
      {/* Logo / Brand */}
      <div className="flex items-center px-4 border-b border-[oklch(20%_0.01_240)]" style={{ height: "56px" }}>
        <div className="w-8 h-8 rounded-lg bg-[#3b82f6] flex items-center justify-center shrink-0" aria-hidden="true">
          <span className="text-white font-bold text-sm">B</span>
        </div>
        {expanded && <span className="ml-3 font-bold text-[oklch(95%_0_0)] text-sm truncate">BANXE</span>}
      </div>

      {/* Nav Items */}
      <ul className="flex-1 py-2 space-y-0.5 px-2" role="list">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeId === item.id;

          return (
            <li key={item.id}>
              <a
                href={item.href}
                onClick={(e) => handleNav(item, e)}
                className={`
                  relative flex items-center rounded-lg
                  transition-colors duration-150
                  ${expanded ? "gap-3 px-3 py-2" : "justify-center p-0"}
                  ${
                    isActive
                      ? "bg-[#3b82f6]/15 text-[oklch(95%_0_0)]"
                      : "text-[oklch(65%_0_0)] hover:bg-[oklch(17%_0.01_240)] hover:text-[oklch(95%_0_0)]"
                  }
                `}
                style={{ height: "40px" }}
                aria-current={isActive ? "page" : undefined}
                title={!expanded ? item.label : undefined}
              >
                {/* Active indicator */}
                {isActive && (
                  <span
                    className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-5 rounded-full bg-[#3b82f6]"
                    aria-hidden="true"
                  />
                )}

                <Icon size={18} className={`shrink-0 ${isActive ? "text-[#60a5fa]" : ""}`} aria-hidden="true" />

                {expanded && <span className="flex-1 text-sm font-medium truncate">{item.label}</span>}

                {expanded && item.badge && item.badge > 0 && (
                  <span
                    className="ml-auto text-xs font-bold px-1.5 py-0.5 rounded-full bg-[#f43f5e]/20 text-[#f87171]"
                    aria-label={`${item.badge} alerts`}
                  >
                    {item.badge > 99 ? "99+" : item.badge}
                  </span>
                )}

                {!expanded && item.badge && item.badge > 0 && (
                  <span
                    className="absolute top-1 right-1 w-2 h-2 rounded-full bg-[#f43f5e]"
                    aria-label={`${item.badge} alerts`}
                  />
                )}
              </a>
            </li>
          );
        })}
      </ul>

      {/* Toggle button */}
      <div className="px-2 pb-4">
        <button
          onClick={() => setExpanded((prev) => !prev)}
          className="
            flex items-center justify-center w-full rounded-lg
            h-8 text-[oklch(45%_0_0)] hover:text-[oklch(65%_0_0)]
            hover:bg-[oklch(17%_0.01_240)] transition-colors
          "
          aria-label={expanded ? "Collapse sidebar" : "Expand sidebar"}
          aria-expanded={expanded}
        >
          {expanded ? <ChevronLeft size={16} aria-hidden="true" /> : <ChevronRight size={16} aria-hidden="true" />}
        </button>
      </div>
    </nav>
  );
}

export default Sidebar;
export { navItems };
