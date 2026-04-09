"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Bot, TrendingUp, Wallet, BarChart3, Terminal } from "lucide-react";
import { clsx } from "clsx";
import { useAtlasStore } from "../../store";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/agents", label: "Agents", icon: Bot },
  { href: "/trades", label: "Trades", icon: TrendingUp },
  { href: "/portfolio", label: "Portfolio", icon: Wallet },
  { href: "/strategies", label: "Strategies", icon: BarChart3 },
  { href: "/terminal", label: "Terminal", icon: Terminal },
];

export function Sidebar() {
  const pathname = usePathname();
  const { openTradeCount, alerts } = useAtlasStore();

  return (
    <aside className="fixed left-0 top-0 h-full w-64 bg-gray-900 border-r border-gray-800 flex flex-col z-50">
      {/* Logo */}
      <div className="p-6 border-b border-gray-800">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-violet-600 flex items-center justify-center font-bold text-sm">A</div>
          <div>
            <div className="font-bold text-white tracking-wide">ATLAS</div>
            <div className="text-xs text-gray-400">Trading System</div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-4 space-y-1">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || (href !== "/" && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors relative",
                active
                  ? "bg-violet-600/20 text-violet-300 border border-violet-600/30"
                  : "text-gray-400 hover:text-gray-200 hover:bg-gray-800"
              )}
            >
              <Icon size={16} />
              {label}
              {label === "Trades" && openTradeCount > 0 && (
                <span className="ml-auto bg-emerald-600 text-white text-xs rounded-full px-1.5 py-0.5">
                  {openTradeCount}
                </span>
              )}
              {label === "Overview" && alerts.length > 0 && (
                <span className="ml-auto bg-red-600 text-white text-xs rounded-full px-1.5 py-0.5">
                  {alerts.length}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Status */}
      <div className="p-4 border-t border-gray-800">
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className="live-dot w-2 h-2 rounded-full bg-emerald-400 inline-block" />
          Paper Trading Mode
        </div>
      </div>
    </aside>
  );
}
